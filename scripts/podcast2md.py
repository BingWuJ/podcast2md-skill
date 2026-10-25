# -*- coding: utf-8 -*-
"""
podcast2md.py — 播客单集链接转写 CLI（单文件，仅标准库）

流水线：独立探测字幕 → 有可用轨道则保存原件并生成文字稿；只有确认无可用轨道才下载音频并走 CapsWriter
安装说明：README.md；使用说明：PODCAST2MD.md

边界：
- 只做 CLI；转录只走 start_server.exe / start_client.exe（引擎 fun_asr_nano）。
- 不读 API Key、不调云端模型；无本地润色模型时交付「未润色」原文。
- 不包含说话人分离；多说话人处理不在默认路径内。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from bisect import bisect_right
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SERVER_EXE = BASE_DIR / "start_server.exe"
CLIENT_EXE = BASE_DIR / "start_client.exe"
CONFIG_SERVER = BASE_DIR / "config_server.py"
DEFAULT_WORK = BASE_DIR / "work"

# 退出码：0 成功；2 用法错误；3 下载失败；4 服务端失败；5 转录失败；6 成品已存在；7 切分/校验失败
EX_OK, EX_USAGE, EX_DOWNLOAD, EX_SERVER, EX_TRANSCRIBE, EX_EXISTS, EX_SPLIT = 0, 2, 3, 4, 5, 6, 7

AUDIO_EXTS = [".mp3", ".m4a", ".wav", ".opus", ".ogg", ".aac", ".flac", ".webm", ".mp4", ".mkv", ".mov"]
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 转录产物等待参数
POLL_INTERVAL = 3.0          # 轮询间隔（秒）
STABLE_POLLS = 2             # 产物大小连续稳定次数


class PodError(Exception):
    """带退出码的任务错误，main 统一转成友好报错"""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def log(msg: str) -> None:
    print(f"[podcast2md] {msg}", flush=True)


def tail_text(path: Path, limit: int = 1200) -> str:
    """读日志文件末尾若干字符，用于报错定位"""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
        return data[-limit:].strip() or "（日志为空）"
    except OSError:
        return "（日志不可读）"


# ---------------------------------------------------------------- 服务端管理

def read_server_port() -> int:
    """从 config_server.py 读端口，避免 import 项目配置"""
    try:
        m = re.search(r"port\s*=\s*['\"]?(\d+)", CONFIG_SERVER.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    except OSError:
        pass
    return 6016


def probe_server(port: int, timeout: float = 2.0) -> bool:
    """探测 127.0.0.1:port 是否有服务端监听"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_server(port: int, wait_s: float, log_path: Path):
    """确认服务端可用；未运行则拉起 start_server.exe。失败必须明确报错，不静默成功。"""
    if probe_server(port):
        log(f"服务端已在运行（127.0.0.1:{port}），直接复用")
        return None
    if not SERVER_EXE.exists():
        raise PodError(EX_SERVER, f"服务端未运行，且找不到 {SERVER_EXE}")
    log(f"服务端未运行，正在拉起 {SERVER_EXE.name}（等待最长 {wait_s:.0f}s）...")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "wb") as lf:
        proc = subprocess.Popen(
            [str(SERVER_EXE)], cwd=str(BASE_DIR),
            stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        deadline = time.time() + wait_s
        while time.time() < deadline:
            if probe_server(port):
                log(f"服务端已就绪（127.0.0.1:{port}），进程 PID={proc.pid}")
                time.sleep(3)  # 端口开启后稍候，给模型收尾
                return proc
            if proc.poll() is not None:
                raise PodError(EX_SERVER,
                               f"服务端进程提前退出（code={proc.returncode}）。日志末尾：\n{tail_text(log_path)}")
            time.sleep(2)
    try:
        proc.terminate()
    except OSError:
        pass
    raise PodError(EX_SERVER,
                   f"等待服务端就绪超时（{wait_s:.0f}s）。日志末尾：\n{tail_text(log_path)}")


# ---------------------------------------------------------------- 下载

def slugify(title: str, fallback: str = "podcast") -> str:
    """标题转安全目录名：保留中英文数字-_，压缩其余为 _，限 40 字符"""
    s = re.sub(r"[^\w\-一-鿿]+", "_", (title or "").strip(), flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = re.sub(r"[^\w\-]+", "_", fallback).strip("_") or "podcast"
    return s[:40].strip("_") or "podcast"


def run_ytdlp(args: list[str], log_path: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    """调用本机 yt-dlp；capture=True 时捕获输出（-J 用），否则写入日志文件"""
    exe = shutil.which("yt-dlp")
    if not exe:
        raise PodError(EX_DOWNLOAD, "未找到 yt-dlp，请先安装（pip install yt-dlp）并加入 PATH")
    if capture:
        return subprocess.run([exe, *args], capture_output=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "wb") as lf:
        return subprocess.run([exe, *args], stdout=lf, stderr=subprocess.STDOUT)


def ytdlp_dump_info(url: str, log_path: Path) -> dict:
    """yt-dlp -J 取单集信息（含标题、章节、描述）"""
    r = run_ytdlp(["-J", "--no-playlist", url], capture=True)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or b"").decode("utf-8", "replace")[-1200:]
        raise PodError(EX_DOWNLOAD, f"yt-dlp 读取单集信息失败：\n{err.strip()}")
    try:
        return json.loads(r.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(r.stdout.decode("utf-8", "replace"), encoding="utf-8")
        raise PodError(EX_DOWNLOAD, f"yt-dlp 返回的 JSON 解析失败：{e}；原始输出已存 {log_path}")


def download_audio(url: str, out_dir: Path, slug: str, log_path: Path) -> Path:
    """yt-dlp 下载音频并保存 info json，返回音频路径"""
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"开始下载音频：{url}")
    r = run_ytdlp([
        "--no-playlist", "--write-info-json", "--no-overwrites",
        "-f", "bestaudio/best",
        "-o", str(out_dir / (slug + ".%(ext)s")),
        url,
    ], log_path=log_path)
    if r.returncode != 0:
        raise PodError(EX_DOWNLOAD, f"yt-dlp 下载失败。日志末尾：\n{tail_text(log_path)}")
    audio = find_audio(out_dir, slug)
    if audio is None:
        raise PodError(EX_DOWNLOAD, f"下载命令成功但未找到音频文件（slug={slug}）。日志末尾：\n{tail_text(log_path)}")
    log(f"下载完成：{audio.name}（{audio.stat().st_size / 1e6:.1f} MB）")
    return audio


def find_audio(out_dir: Path, slug: str) -> Path | None:
    """在目录里找下载的音频：排除 info json / 分片临时文件，按扩展名优先级取最新"""
    cands = []
    for f in out_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() in (".json", ".part", ".ytdl", ".txt", ".srt"):
            continue
        if f.stem == slug or f.stem.startswith(slug + "."):
            cands.append(f)
    if not cands:
        return None
    prio = {ext: i for i, ext in enumerate(AUDIO_EXTS)}
    cands.sort(key=lambda f: (prio.get(f.suffix.lower(), 99), -f.stat().st_mtime))
    return cands[0]


# ---------------------------------------------------------------- 章节目录

TS_LINE = re.compile(r"^\s*[\(\[]?((?:\d{1,3}:)?\d{1,2}:\d{2})[\)\]]?\s*[-–—:·.\s]*(\S.*?)\s*$")


def extract_toc_from_html(html_text: str) -> list[dict]:
    """
    从单集页 HTML 提取时间戳目录（SPA 页面里 shownotes 以 JSON 字符串内嵌，
    换行是字面 \n）。优先扫「时间轴」区块，遇到非时间戳行（下一区块头，如
    「猜你想看」注释/推荐）即停；无标记时全文扫描兑底。按秒去重。
    """
    entry_re = re.compile(r"^[\(（\[]?((?:\d{1,2}:)?\d{1,2}:\d{2})[\)）\]]?\s*(.+)$")

    def scan(segment: str, stop_on_plain_line: bool) -> list[dict]:
        out = []
        for line in segment.split("\\n"):  # JSON 内嵌换行
            m = entry_re.match(line.strip())
            if m:
                start, title = parse_ts(m.group(1)), m.group(2).strip()
                if title and start <= 12 * 3600:
                    out.append({"title": title, "start": float(start)})
            elif stop_on_plain_line and out:
                break
        return out

    marker = -1
    for kw in ("时间轴", "时间点", "Timeline", "timeline"):
        marker = html_text.find(kw)
        if marker >= 0:
            marker += len(kw)
            break
    entries = scan(html_text[marker:marker + 20000], True) if marker >= 0 else []
    if len(entries) < 2:  # 无标记或区块太短 → 全文扫描兑底
        entries = scan(html_text, False)

    ded, seen = [], set()
    for e in sorted(entries, key=lambda c: c["start"]):
        if e["start"] not in seen:  # 同一秒只留首条（页面 shownotes 常内嵌两份）
            seen.add(e["start"])
            ded.append(e)
    return ded


def fetch_html(url: str, timeout: float = 30) -> str:
    """拉取单集页 HTML（带 UA），失败返回空串（调用方回退到无目录）"""
    try:
        from urllib.request import Request, urlopen
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except OSError:
        return ""


def extract_toc(info: dict) -> dict:
    """
    章节目录：yt-dlp chapters 优先；否则解析描述里的时间戳标题；
    都没有则只放一章「全文」，不发明章节。
    """
    url = info.get("webpage_url") or info.get("original_url") or ""
    title = info.get("title") or "未命名单集"
    base = {"url": url, "title": title,
            "duration": info.get("duration"), "extractor": info.get("extractor")}

    chapters = info.get("chapters") or []
    if chapters:
        toc = [{"title": (c.get("title") or f"章节 {i + 1}").strip(),
                "start": float(c.get("start_time") or 0.0)}
               for i, c in enumerate(chapters)]
        toc.sort(key=lambda c: c["start"])
        return {**base, "source": "yt-dlp", "chapters": toc}

    desc = info.get("description") or ""
    entries = []
    for line in desc.splitlines():
        m = TS_LINE.match(line)
        if m:
            entries.append({"title": m.group(2).strip() or f"章节 {len(entries) + 1}",
                            "start": parse_ts(m.group(1))})
    if len(entries) >= 2:  # 单条时间戳不足以构成目录，视为没有
        entries.sort(key=lambda c: c["start"])
        return {**base, "source": "description", "chapters": entries}

    # 描述无目录 → 抓单集页 HTML 提取时间轴（SPA 页面 shownotes 内嵌 JSON）
    html = fetch_html(url) if url.startswith("http") else ""
    if html:
        entries = extract_toc_from_html(html)
        if len(entries) >= 2:
            log(f"从页面 HTML 提取到 {len(entries)} 条时间轴目录")
            return {**base, "source": "html", "chapters": entries}

    return {**base, "source": "none", "chapters": [{"title": "全文", "start": 0.0}]}


def parse_ts(text: str) -> float:
    """'M:SS' / 'H:MM:SS' → 秒"""
    parts = [int(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def fmt_ts(sec: float | None) -> str:
    if sec is None:
        return "?"
    sec = int(round(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


# ---------------------------------------------------------------- 转录

def run_client(audio: Path, log_path: Path, timeout_s: float):
    """
    调 start_client.exe 转录。文件模式结束会停在「按回车退出」，
    产物齐备后 CLI 代写回车，再等待/终止进程。
    """
    outputs = [audio.with_suffix(s) for s in (".txt", ".srt", ".json")]
    for f in outputs:  # 防旧产物干扰完成判定
        if f.exists():
            f.unlink()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"启动客户端转录：{audio.name}（等待最长 {timeout_s / 3600:.1f}h）")
    with open(log_path, "wb") as lf:
        proc = subprocess.Popen(
            [str(CLIENT_EXE), str(audio)], cwd=str(BASE_DIR),
            stdin=subprocess.PIPE, stdout=lf, stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        last_sizes, stable = [-1] * 3, 0
        deadline = time.time() + timeout_s
        try:
            while time.time() < deadline:
                if proc.poll() is not None:
                    got = [f for f in outputs if f.exists() and f.stat().st_size > 0]
                    if len(got) < 3:
                        raise PodError(EX_TRANSCRIBE,
                                       f"客户端提前退出且产物不全（{len(got)}/3）。日志末尾：\n{tail_text(log_path)}")
                    break
                sizes = [f.stat().st_size if f.exists() and f.stat().st_size > 0 else -1 for f in outputs]
                if sizes == last_sizes and -1 not in sizes:
                    stable += 1
                    if stable >= STABLE_POLLS:
                        log("转录产物已齐备且稳定")
                        break
                else:
                    stable = 0
                last_sizes = sizes
                time.sleep(POLL_INTERVAL)
            else:
                raise PodError(EX_TRANSCRIBE,
                               f"等待转录产物超时（{timeout_s:.0f}s）。日志末尾：\n{tail_text(log_path)}")
        finally:
            finish_client(proc)

    missing = [f.name for f in outputs if not f.exists() or f.stat().st_size == 0]
    if missing:
        raise PodError(EX_TRANSCRIBE, f"转录产物缺失：{missing}。日志末尾：\n{tail_text(log_path)}")
    log("转录完成：" + "、".join(f.name for f in outputs))


def finish_client(proc: subprocess.Popen):
    """代客户端结束：写回车（越过「按回车退出」），等待后兜底 terminate/kill"""
    if proc.poll() is not None:
        return
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.write(b"\n")
            proc.stdin.flush()
            proc.stdin.close()
    except OSError:
        pass
    try:
        proc.wait(timeout=30)
        log(f"客户端已自行退出（PID={proc.pid}）")
        return
    except subprocess.TimeoutExpired:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log(f"客户端进程已终止（PID={proc.pid}）")


# ---------------------------------------------------------------- 切分与校验

SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
EMPTY_CHAPTER_MARK = "（本章无字幕内容）"  # 结构标记，非转录句，验收比对时排除


def parse_srt(path: Path) -> list[dict]:
    """解析 CapsWriter 生成的 srt（由字级时间戳对齐生成）→ [{start,end,text}]"""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    cues, cur = [], None
    for line in text.splitlines():
        m = SRT_TIME.search(line)
        if m:
            g = [int(x) for x in m.groups()]
            if cur:
                cues.append(cur)
            cur = {"start": g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                   "end": g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000, "text": ""}
        elif cur is not None:
            if line.strip() and not line.strip().isdigit():
                cur["text"] += (("\n" if cur["text"] else "") + line.strip())
    if cur:
        cues.append(cur)
    cues = [c for c in cues if c["text"]]
    if not cues:
        raise PodError(EX_SPLIT, f"未能从 {path.name} 解析出任何字幕条目")
    return cues


UNLOCATED_NOTE = "以下条目没有可靠时间戳，保留原有顺序，不伪造时间。时间轴未通过。"
IGNORED_LANGS = {"danmaku", "live_chat"}
LANG_PREFERENCE = ["zh-hans", "zh-cn", "zh", "chi", "zh-hant", "zh-tw", "zh-hk"]


def source_label(kind: str, lang: str | None = None) -> str:
    """文字来源只使用这三类。语言附在后面，不另造第四类。"""
    if kind == "平台AI":
        return f"平台AI（{lang}）" if lang else "平台AI"
    if kind == "普通CC":
        return f"普通CC（{lang}）" if lang else "普通CC"
    return "本机ASR（CapsWriter-Offline / fun_asr_nano）"


def build_chapters_md(toc: dict, cues: list[dict], txt_text: str, polish_mode: str,
                       origin: dict | None = None, unlocated: list[str] | None = None) -> str:
    """按目录时间把字幕条目切进章节。无效时间的文本单列，不丢、不伪造时间。"""
    status = {"off": "未润色（未检测到本地润色模型，以下为转录原文）",
              "basic": "基础规则润色（仅去语气词与相邻重复；无模型、无云端调用）"}[polish_mode]
    src = {"yt-dlp": "yt-dlp chapters", "description": "页面描述时间戳目录",
           "html": "页面 HTML 时间轴", "none": "无目录，整篇一章"}[toc["source"]]
    origin = origin or {
        "text_source": source_label("本机ASR"),
        "generator": "podcast2md.py（CapsWriter-Offline / fun_asr_nano）",
        "probe_note": "not_requested",
    }
    lines = [f"# {toc['title']}", "",
             f"> 来源：{toc['url']}",
             f"> 文字来源：{origin['text_source']}",
             f"> 生成：{origin['generator']}",
             f"> 状态：{status}",
             f"> 章节来源：{src}",
             f"> 字幕探测：{origin['probe_note']}",
             "> 边界：正文与原件一致只说明转换没有丢改，不能证明字幕覆盖整段音频，也不能证明识别准确。普通CC不保证人工校对。",
             ""]
    unlocated = [item.strip() for item in (unlocated or []) if item and item.strip()]
    timed = [cue for cue in cues if isinstance(cue.get("start"), (int, float))]

    if toc["source"] == "none" or not timed:
        body = apply_polish(txt_text, polish_mode)
        lines += [f"## {fmt_ts(0)} 全文", "", body.rstrip(), ""]
    else:
        starts = [c["start"] for c in toc["chapters"]]
        buckets = [[] for _ in toc["chapters"]]
        for cue in timed:  # 按条目起点归章：start <= cue.start < 下一章 start
            idx = bisect_right(starts, cue["start"]) - 1
            buckets[max(0, idx)].append(cue["text"])
        last_end = timed[-1].get("end")
        for i, chap in enumerate(toc["chapters"]):
            end = toc["chapters"][i + 1]["start"] if i + 1 < len(toc["chapters"]) else last_end
            chap["end"] = end
            body = "\n".join("\n".join(b.splitlines()) for b in buckets[i]).strip()
            body = apply_polish(body, polish_mode) or EMPTY_CHAPTER_MARK
            lines += [f"## {fmt_ts(chap['start'])} {chap['title']}", "", body, ""]
    if unlocated:
        lines += ["## 未定位文本", "", UNLOCATED_NOTE, "", *unlocated, ""]
    return "\n".join(lines)


FILLERS = "嗯呃啊哦噢喔诶欸哎"  # basic 润色可去除的段首尾语气词
FILLER_HEAD = re.compile(f"^[{FILLERS}]+")
FILLER_TAIL = re.compile(f"[{FILLERS}]+$")
PUNCT_SET = set("。？！，,.?!；;：:")


def apply_polish(text: str, mode: str) -> str:
    """off：原样；basic：仅去段首尾语气词、收敛同字 3 连以上为 1 字，不加任何内容"""
    if mode != "basic":
        return text
    out_lines = []
    for line in text.splitlines():
        line = re.sub(r"(.)\1{2,}", r"\1", line)  # 重复收敛：嗯嗯嗯→嗯、2连不动
        segs = re.split(r"([。？！，,.?!；;：:])", line)  # 段首尾语气词
        built = []
        for j, seg in enumerate(segs):
            if j % 2 == 0:  # 文字段：去首尾语气词
                seg = FILLER_HEAD.sub("", seg.strip()).strip()
                seg = FILLER_TAIL.sub("", seg)
                if seg:
                    built.append(seg)
            else:  # 标点段：前一个文字段非空才保留，避免清空后出现连续标点
                if built and built[-1] not in PUNCT_SET:
                    built.append(seg)
        out_lines.append("".join(built).strip())
    return "\n".join(ln for ln in out_lines if ln)


def normalize(s: str) -> str:
    """校验用归一化：去空白与标点，仅留文字数字字母"""
    return re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)


def first_missing_index(needle: str, haystack: str) -> int:
    """返回 needle 中第一个无法在 haystack 里延续的位置。"""
    if needle in haystack:
        return -1
    lo, hi = 0, len(needle)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if needle[:mid] in haystack:
            lo = mid
        else:
            hi = mid - 1
    return lo


CONTRACT_RATIO = 0.99


def missing_preview(left: str, right: str) -> str:
    """定位第一个对不上的位置，取其后 30 字。"""
    if left in right:
        return right[len(left):len(left) + 30]
    at = first_missing_index(left, right)
    return left[at:at + 30]


def check_srt_txt_contract(cues: list[dict], txt_text: str, unlocated: list[str] | None = None) -> dict:
    """切章前确认 srt 没有相对 txt 截断。正常产物应完全相等，不是接近。"""
    srt_norm = normalize("".join(c["text"] for c in cues) + "".join(unlocated or []))
    txt_norm = normalize(txt_text)
    ratio = (len(srt_norm) / len(txt_norm)) if txt_norm else 0.0
    contained = bool(srt_norm) and srt_norm in txt_norm
    return {"ok": contained and ratio >= CONTRACT_RATIO,
            "srt_len": len(srt_norm), "txt_len": len(txt_norm),
            "ratio": ratio, "preview": missing_preview(srt_norm, txt_norm)}


def require_srt_txt_contract(cues: list[dict], txt_text: str, unlocated: list[str] | None = None) -> dict:
    result = check_srt_txt_contract(cues, txt_text, unlocated)
    if not result["ok"]:
        raise PodError(
            EX_TRANSCRIBE,
            "srt/txt 不一致：srt 归一化长度 {srt_len} / txt 归一化长度 {txt_len} / 比值 {ratio:.4f} / 首个缺失位置前30字：{preview}。未写入 chapters.md".format(**result),
        )
    return result


def check_json_tokens(json_path: Path, txt_text: str) -> dict | None:
    """没有 tokens 字段就跳过。有 timestamps 时数量必须与 tokens 相同。"""
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tokens"), list):
        return None
    tokens = data["tokens"]
    timestamps = data.get("timestamps")
    count_ok = not isinstance(timestamps, list) or len(tokens) == len(timestamps)
    joined = "".join(item if isinstance(item, str) else str(item) for item in tokens)
    token_norm = normalize(joined)
    txt_norm = normalize(txt_text)
    ratio = (len(token_norm) / len(txt_norm)) if txt_norm else 0.0
    contained = bool(token_norm) and token_norm in txt_norm
    return {"ok": count_ok and contained and ratio >= CONTRACT_RATIO,
            "count_ok": count_ok, "token_count": len(tokens),
            "timestamp_count": len(timestamps) if isinstance(timestamps, list) else None,
            "token_len": len(token_norm), "txt_len": len(txt_norm),
            "ratio": ratio, "preview": missing_preview(token_norm, txt_norm)}


def require_json_tokens(json_path: Path, txt_text: str) -> None:
    result = check_json_tokens(json_path, txt_text)
    if result is None or result["ok"]:
        return
    if not result["count_ok"]:
        raise PodError(
            EX_TRANSCRIBE,
            "json tokens 与 timestamps 数量不一致：tokens {token_count} / timestamps {timestamp_count}。未写入 chapters.md".format(**result),
        )
    raise PodError(
        EX_TRANSCRIBE,
        "json tokens 与 txt 不一致：tokens 归一化长度 {token_len} / txt 归一化长度 {txt_len} / 比值 {ratio:.4f} / 首个缺失位置前30字：{preview}。未写入 chapters.md".format(**result),
    )


def probe_audio_duration(audio: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        duration = float((result.stdout or "").strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def compute_transcribe_timeout(duration: float | None, explicit: float | None) -> float:
    if explicit is not None:
        return explicit
    if duration is None or duration <= 0:
        return 7200.0
    return max(600.0, duration * 4 + 120)


def srt_fingerprint(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha1(data).hexdigest(), len(data)


def mark_stale_toc(out_dir: Path) -> None:
    """已有 toc 与当前 srt 指纹不一致时只标记，不重跑转录。"""
    toc_path = out_dir / "toc.json"
    if not toc_path.exists():
        return
    try:
        toc = json.loads(toc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"警告：无法读取已有 toc.json，不自动重跑：{toc_path}")
        return
    if not isinstance(toc, dict):
        return
    name = (toc.get("transcript") or {}).get(".srt") if isinstance(toc.get("transcript"), dict) else None
    srt_path = out_dir / name if name else None
    if srt_path is None or not srt_path.exists():
        found = [p for p in out_dir.glob("*.srt")]
        srt_path = found[0] if len(found) == 1 else None
    if srt_path is None or not srt_path.exists():
        return
    current, _ = srt_fingerprint(srt_path)
    stored = toc.get("source_fingerprint")
    if not isinstance(stored, str) or stored == current:
        return
    print(f"警告：toc.json 指纹与当前 srt 不一致，已标记 stale，不自动重跑：{srt_path.name}")
    toc["stale"] = True
    toc_path.write_text(json.dumps(toc, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_srt_document(text: str) -> tuple[list[dict], list[str]]:
    """解析字幕正文。无效时间不丢文本、不伪造时间。parse_srt 的返回签名保持不变。"""
    cues, unlocated, pending = [], [], []
    cur = None

    def flush_pending() -> None:
        nonlocal pending
        for line in pending:
            stripped = line.strip()
            if stripped and not stripped.isdigit():
                unlocated.append(stripped)
        pending = []

    for line in text.splitlines():
        matched = SRT_TIME.search(line)
        if matched:
            flush_pending()
            if cur and cur.get("text") and not cur.get("invalid_time"):
                cues.append(cur)
            groups = [int(item) for item in matched.groups()]
            start = groups[0] * 3600 + groups[1] * 60 + groups[2] + groups[3] / 1000
            end = groups[4] * 3600 + groups[5] * 60 + groups[6] + groups[7] / 1000
            cur = {"start": start, "end": end, "text": "", "invalid_time": end < start}
            continue
        stripped = line.strip()
        if not stripped or stripped.isdigit():
            continue
        if cur is None:
            pending.append(line)
        elif cur.get("invalid_time"):
            unlocated.append(stripped)
        else:
            cur["text"] += ("\n" if cur["text"] else "") + stripped
    if cur and cur.get("text") and not cur.get("invalid_time"):
        cues.append(cur)
    flush_pending()
    return [cue for cue in cues if cue.get("text")], unlocated


def text_units(*parts: str) -> list[str]:
    units = []
    for part in parts:
        units.extend(line.strip() for line in (part or "").splitlines() if line.strip())
    return units


def chapter_body_units(md_text: str) -> list[str]:
    ignored = {EMPTY_CHAPTER_MARK, UNLOCATED_NOTE}
    return [line.strip() for line in md_text.splitlines()
            if line.strip() and not line.startswith("#") and not line.startswith(">")
            and line.strip() not in ignored]


def coverage_report(source_units: list[str], derived_units: list[str], faithful: bool = True) -> dict:
    """按顺序对齐全文。包含检查不能当通过条件；等长替换、漏段、重复和乱序都要报出。"""
    source = [re.sub(r"\s+", "", item.strip()) for item in source_units if item and item.strip()]
    derived = [re.sub(r"\s+", "", item.strip()) for item in derived_units if item and item.strip()]
    source_keys = [normalize(item) for item in source]
    derived_keys = [normalize(item) for item in derived]
    punctuation = []
    missing, added, replaced, duplicate = [], [], [], []
    reordered = False
    if source_keys == derived_keys:
        punctuation = [{"source": left, "derived": right}
                       for left, right in zip(source, derived) if left != right]
    else:
        source_count, derived_count = Counter(source_keys), Counter(derived_keys)
        if source_count == derived_count:
            reordered = True
        else:
            for key, count in source_count.items():
                gap = count - derived_count.get(key, 0)
                if gap > 0:
                    missing.extend([key] * gap)
            for key, count in derived_count.items():
                gap = count - source_count.get(key, 0)
                if gap > 0:
                    added.extend([key] * gap)
                    if key in source_count:
                        duplicate.extend([key] * gap)
            if len(source_keys) == len(derived_keys):
                replaced = [{"source": left, "derived": right}
                            for left, right in zip(source_keys, derived_keys) if left != right]
    source_join = "".join(source_keys)
    content_ok = source_keys == derived_keys
    return {
        "ok": content_ok and not (punctuation and faithful),
        "content_ok": content_ok,
        "missing": missing[:8], "added": added[:8], "duplicate": duplicate[:8],
        "replaced": replaced[:8], "punctuation": punctuation[:8],
        "missing_count": len(missing), "added_count": len(added),
        "duplicate_count": len(duplicate), "replaced_count": len(replaced),
        "punctuation_count": len(punctuation), "reordered": reordered,
        "containment_would_pass": all(key in source_join for key in derived_keys) if derived_keys else not source_keys,
    }


def json_subtitle_langs(info: dict) -> list[str]:
    langs = []
    for key in ("subtitles", "automatic_captions"):
        value = info.get(key) or {}
        if isinstance(value, dict):
            langs.extend(str(lang) for lang in value)
    return langs


def parse_list_subs(text: str) -> list[dict]:
    tracks, section = [], None
    for line in text.splitlines():
        if "Available subtitles for" in line:
            section = "manual"
            continue
        if "Available automatic captions for" in line:
            section = "auto"
            continue
        if "has no subtitles" in line or "has no automatic captions" in line:
            section = None
            continue
        if section is None or not line.strip() or line.strip().startswith("Language") or line.startswith("["):
            continue
        lang = line.split()[0]
        if lang.lower() == "language":
            continue
        tracks.append({"lang": lang, "automatic": section == "auto", "formats": line.split()[-1]})
    return tracks


def choose_track(tracks: list[dict]) -> dict:
    def rank(track: dict) -> tuple[int, int]:
        lang = track["lang"].lower()
        try:
            preferred = LANG_PREFERENCE.index(lang)
        except ValueError:
            preferred = 100
        return preferred, 1 if track.get("automatic") else 0
    return sorted(tracks, key=rank)[0]


def classify_subtitle_probe(stdout: str, stderr: str, returncode: int,
                            json_langs: list[str], requested_lang: str | None = None) -> dict:
    """独立列字幕的结果才是状态。普通 JSON 字幕字段为空不能当成确认无字幕。"""
    text = f"{stdout}\n{stderr}"
    tracks = parse_list_subs(text)
    real = [track for track in tracks if track["lang"].lower() not in IGNORED_LANGS]
    login = bool(re.search(r"only available when logged in|need_login_subtitle", text, re.I))
    real_json = [lang for lang in json_langs if lang.lower() not in IGNORED_LANGS]
    result = {
        "json_subtitle_field_empty": not real_json,
        "json_field_used_as_verdict": False,
        "tracks": real,
        "danmaku_ignored": any(track["lang"].lower() in IGNORED_LANGS for track in tracks),
        "login_warning": login,
        "returncode": returncode,
    }
    explicit_absence = "has no subtitles" in text or "has no automatic captions" in text or result["danmaku_ignored"]
    if returncode != 0 and not (login and not real):
        return {**result, "status": "request_failed"}
    if login and not real:
        return {**result, "status": "login_required"}
    matched = real
    if requested_lang:
        wanted = requested_lang.lower()
        matched = [track for track in real if track["lang"].lower() == wanted]
        if real and not matched:
            return {**result, "status": "filter_no_match"}
    if matched:
        return {**result, "status": "found", "chosen": choose_track(matched)}
    if returncode == 0 and not login and explicit_absence:
        return {**result, "status": "confirmed_none"}
    return {**result, "status": "request_failed"}


def has_protected_output(out_dir: Path) -> bool:
    """只有探测日志时允许重试。音频、字幕原件和章节稿仍受保护。"""
    if not out_dir.exists():
        return False
    for item in out_dir.rglob("*"):
        if not item.is_file() or item.parent.name == "logs" or item.name == "subtitle-probe.json":
            continue
        return True
    return False


def probe_subtitles(url: str, info: dict, log_path: Path, requested_lang: str | None = None) -> dict:
    result = run_ytdlp(["--list-subs", "--no-playlist", "--skip-download", url], capture=True)
    stdout = (result.stdout or b"").decode("utf-8", "replace")
    stderr = (result.stderr or b"").decode("utf-8", "replace")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(stdout + "\n" + stderr, encoding="utf-8")
    probe = classify_subtitle_probe(
        stdout, stderr, result.returncode, json_subtitle_langs(info), requested_lang)
    probe["part"] = {
        "id": info.get("id"), "title": info.get("title"),
        "playlist_index": info.get("playlist_index"), "n_entries": info.get("n_entries"),
    }
    return probe


def write_probe(out_dir: Path, probe: dict) -> None:
    public = {key: probe.get(key) for key in (
        "status", "json_subtitle_field_empty", "json_field_used_as_verdict",
        "tracks", "danmaku_ignored", "login_warning", "returncode", "part", "chosen")}
    (out_dir / "subtitle-probe.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")


def download_subtitle_original(url: str, dest_dir: Path, slug: str, lang: str, log_path: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    result = run_ytdlp([
        "--no-playlist", "--skip-download", "--write-subs", "--write-auto-subs",
        "--sub-langs", lang, "--convert-subs", "srt", "--no-overwrites",
        "-o", str(dest_dir / f"{slug}.%(ext)s"), url,
    ], log_path=log_path)
    if result.returncode != 0:
        raise PodError(EX_DOWNLOAD, f"字幕轨道已发现，但原件下载失败。不能改记为无字幕。日志末尾：\n{tail_text(log_path)}")
    saved = [item for item in dest_dir.iterdir() if item.is_file() and slug in item.name]
    srt_files = [item for item in saved if item.suffix.lower() == ".srt"]
    if srt_files:
        srt_files.sort(key=lambda item: item.name)
        return srt_files[0]
    others = [item.name for item in saved if item.suffix.lower() in {".vtt", ".ass", ".json"}]
    if others:
        raise PodError(EX_DOWNLOAD, f"字幕原件不是 SRT：{', '.join(others)}。格式不支持，不能改记为无字幕。")
    raise PodError(EX_DOWNLOAD, "字幕轨道已发现，但没有保存到原件。不能改记为无字幕。")


def cue_source_units(cues: list[dict], unlocated: list[str]) -> list[str]:
    units = []
    for cue in cues:
        units.extend(text_units(cue.get("text") or ""))
    units.extend(item.strip() for item in unlocated if item and item.strip())
    return units


def probe_block_message(status: str) -> str:
    meaning = {
        "login_required": "需要登录",
        "request_failed": "请求失败",
        "filter_no_match": "筛选无匹配",
    }[status]
    return f"字幕探测状态：{status}（{meaning}）。不能写成确认无字幕，也未选择音频 ASR。"


# ---------------------------------------------------------------- 主流程

def write_chapters(out_dir: Path, toc: dict, slug: str, cues: list[dict], unlocated: list[str],
                   polish: str, source_path: Path, origin: dict, asr: bool,
                   txt_text: str | None = None, json_path: Path | None = None) -> int:
    """全文覆盖不通过就不写 chapters.md。包含检查只作对照，不能单独放行。"""
    if txt_text is None:
        txt_text = "\n".join(cue.get("text") or "" for cue in cues)
    md_text = build_chapters_md(toc, cues, txt_text, polish, origin=origin, unlocated=unlocated)
    derived = chapter_body_units(md_text)
    timed = toc.get("source") != "none" and any(isinstance(cue.get("start"), (int, float)) for cue in cues)
    source_units = cue_source_units(cues, unlocated) if timed else text_units(apply_polish(txt_text, polish)) + unlocated
    if timed and polish == "basic":
        source_units = text_units(apply_polish("\n".join(source_units), polish))
    report = coverage_report(source_units, derived, faithful=polish == "off")
    print(
        "全文覆盖："
        f"缺失 {report['missing_count']}，增加 {report['added_count']}，"
        f"重复 {report['duplicate_count']}，乱序 {report['reordered']}，"
        f"替换 {report['replaced_count']}，标点 {report['punctuation_count']}。"
        f"仅包含检查会通过：{report['containment_would_pass']}"
    )
    if not report["ok"]:
        raise PodError(EX_SPLIT, "全文覆盖未通过：漏段、增加、重复、乱序、替换或忠实模式下的标点改动。未写入 chapters.md")
    if unlocated:
        print("时间轴未通过：无效时间戳已单列，未伪造时间，也未丢文本。")
    tmp_path = out_dir / "chapters.md.tmp"
    tmp_path.write_text(md_text, encoding="utf-8")
    tmp_path.replace(out_dir / "chapters.md")
    fingerprint, source_bytes = srt_fingerprint(source_path)
    toc["slug"] = slug
    toc["text_source"] = {"kind": origin["kind"], "lang": origin.get("lang"), "probe_status": origin["probe_status"]}
    relative = source_path.relative_to(out_dir).as_posix()
    toc["transcript"] = {".srt": relative}
    if asr:
        toc["transcript"][".txt"] = source_path.with_suffix(".txt").name
    if json_path is not None:
        toc["transcript"][".json"] = json_path.name
    toc["verify"] = {
        "body_lines": len(derived), "coverage_ok": report["ok"],
        "missing_count": report["missing_count"], "added_count": report["added_count"],
        "duplicate_count": report["duplicate_count"], "reordered": report["reordered"],
        "replaced_count": report["replaced_count"], "punctuation_count": report["punctuation_count"],
        "timeline_ok": not unlocated, "containment_is_not_acceptance": True,
    }
    toc["source_fingerprint"] = fingerprint
    toc["srt_bytes"] = source_bytes
    (out_dir / "toc.json").write_text(json.dumps(toc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"完成。文字来源：{origin['text_source']}\n  {out_dir / 'chapters.md'}\n  {source_path}")
    return EX_OK


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="podcast2md.py",
        description="播客或视频 URL → 独立探测字幕；有可用轨道则保存原件并生成文字稿，确认无可用轨道才转写",
        epilog="探测失败或需登录时停止，不回退 ASR，也不写成确认无字幕。使用说明见 PODCAST2MD.md。")
    p.add_argument("url", help="单集页面或音频直链 URL")
    p.add_argument("--out-dir", default=str(DEFAULT_WORK), help="输出根目录（默认 <脚本目录>/work）")
    p.add_argument("--force", action="store_true", help="目标成品目录已存在时删除重建")
    p.add_argument("--polish", choices=["off", "basic"], default="off",
                   help="off=未润色原文（默认）；basic=保守规则清理（去语气词、相邻重复）")
    p.add_argument("--port", type=int, default=None, help="服务端端口（默认读 config_server.py）")
    p.add_argument("--server-timeout", type=float, default=600, help="等服务端就绪秒数（默认 600）")
    p.add_argument("--transcribe-timeout", type=float, default=None,
               help="等转录完成秒数。未传时按 max(600, 音频秒数×4+120) 计算；取不到时长或时长为 0 则用 7200。显式传入后不被覆盖")
    p.add_argument("--sub-lang", default=None,
                   help="只接受该语言字幕轨。有其他轨道但没有这一轨时状态为 filter_no_match，停止且不转写")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    port = args.port or read_server_port()
    out_root = Path(args.out_dir).resolve()
    print(f"输入 URL：{args.url}")
    print(f"输出根目录：{out_root}｜服务端端口：{port}｜润色：{args.polish}")
    home = os.environ.get("CAPSWRITER_HOME")
    if not home:
        print(f"警告：CAPSWRITER_HOME 未设置。实际输出根目录：{out_root}")
        print("[Environment]::SetEnvironmentVariable('CAPSWRITER_HOME','" + str(BASE_DIR) + "','User')")
        print("上面这行可直接复制。它只写入用户变量，重开终端后生效；本进程不会替你设置。")
    elif Path(home).resolve() != BASE_DIR:
        print(f"警告：脚本目录 {BASE_DIR} 与 CAPSWRITER_HOME（{home}）不一致。实际输出根目录：{out_root}")
    if out_root != DEFAULT_WORK.resolve():
        print(f"警告：原件默认集中存放在部署副本 work（{DEFAULT_WORK}）。确认你要改根目录：{out_root}")

    # 1) 信息 + slug。失败时的原始 JSON 落到本次 --out-dir，不写死脚本目录。
    info_log = out_root / "logs" / "_podcast2md_info.json"
    info = ytdlp_dump_info(args.url, info_log)
    slug = slugify(info.get("title") or "", info.get("id") or args.url)
    out_dir = Path(args.out_dir) / slug
    print(f"单集标题：{info.get('title')}\nslug：{slug}\n成品目录：{out_dir}")

    # 2) 成品保护。只有探测日志时允许重试；原件和章节稿仍要 --force。
    if out_dir.exists() and not args.force:
        mark_stale_toc(out_dir)
    if has_protected_output(out_dir):
        if not args.force:
            raise PodError(EX_EXISTS, f"目录已有原件或章节稿：{out_dir}（覆盖请加 --force）")
        try:
            shutil.rmtree(out_dir)
        except PermissionError as e:
            raise PodError(EX_EXISTS,
                           f"--force 清空目录失败，文件被占用（常驻服务端日志已移至 work 根目录，重启后旧句柄可释放）：{e}")
        print(f"--force：已清空重建 {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    logs = out_dir / "logs"
    toc = extract_toc(info)

    # 3) 独立探测。JSON 字幕字段为空不是结论，失败状态不回退 ASR。
    probe = probe_subtitles(args.url, info, logs / "list-subs.log", args.sub_lang)
    write_probe(out_dir, probe)
    print(f"字幕探测：{probe['status']}｜JSON 字幕字段为空：{probe['json_subtitle_field_empty']}（不作结论）")
    if probe["status"] in {"login_required", "request_failed", "filter_no_match"}:
        raise PodError(EX_DOWNLOAD, probe_block_message(probe["status"]))
    if probe["status"] == "found":
        chosen = probe["chosen"]
        kind = "平台AI" if chosen.get("automatic") else "普通CC"
        print(f"使用字幕原件：{source_label(kind, chosen['lang'])}。不转写。")
        subtitle = download_subtitle_original(
            args.url, out_dir / "original-subs", slug, chosen["lang"], logs / "subtitle-download.log")
        cues, unlocated = parse_srt_document(subtitle.read_text(encoding="utf-8-sig", errors="replace"))
        if not cues and not unlocated:
            raise PodError(EX_SPLIT, f"已保存字幕原件，但没有解析出文本：{subtitle.name}。不能改记为无字幕。")
        return write_chapters(
            out_dir, toc, slug, cues, unlocated, args.polish, subtitle, {
                "kind": kind, "lang": chosen["lang"], "probe_status": probe["status"],
                "text_source": source_label(kind, chosen["lang"]),
                "generator": "podcast2md.py（平台字幕原件，未跑 CapsWriter）",
                "probe_note": probe["status"],
            }, asr=False)

    if probe["status"] != "confirmed_none":
        raise PodError(EX_DOWNLOAD, probe_block_message("request_failed"))
    print("字幕探测：confirmed_none。已明确选择音频 ASR。")
    if not shutil.which("ffmpeg"):
        raise PodError(EX_USAGE, "ffmpeg 不在 PATH，先装再跑")
    for exe in (SERVER_EXE, CLIENT_EXE):
        if not exe.exists():
            raise PodError(EX_USAGE, f"缺少 {exe}，请在 CapsWriter-Offline 根目录运行本脚本")

    # 4) 只有确认无可用轨道才下载并转写。
    audio = download_audio(args.url, out_dir, slug, logs / "ytdlp.log")
    n = len(toc["chapters"])
    print(f"章节：{n} 章（来源：{toc['source']}）" +
          ("；仅一章「全文」" if toc["source"] == "none" else
           "；" + " / ".join(c["title"][:12] for c in toc["chapters"][:5])))
    duration = probe_audio_duration(audio)
    budget = compute_transcribe_timeout(duration, args.transcribe_timeout)
    shown_duration = "未知" if duration is None else f"{duration:.1f}s"
    print(f"音频时长：{shown_duration}｜本次超时预算：{budget:.0f}s")
    server_log = Path(args.out_dir) / "_podcast2md_server.log"
    server_proc = ensure_server(port, args.server_timeout, server_log)
    try:
        run_client(audio, logs / "client.log", budget)
    finally:
        if server_proc is not None and server_proc.poll() is None:
            log("服务端保持运行（复用加速下次转录）；如需停止请托盘退出或结束 start_server.exe")

    txt_text = audio.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")
    srt_path = audio.with_suffix(".srt")
    cues, unlocated = parse_srt_document(srt_path.read_text(encoding="utf-8-sig", errors="replace"))
    if not cues and not unlocated:
        raise PodError(EX_SPLIT, f"未能从 {srt_path.name} 解析出任何字幕条目")
    require_srt_txt_contract(cues, txt_text, unlocated)
    require_json_tokens(audio.with_suffix(".json"), txt_text)
    return write_chapters(
        out_dir, toc, slug, cues, unlocated, args.polish, srt_path, {
            "kind": "本机ASR", "lang": None, "probe_status": "confirmed_none",
            "text_source": source_label("本机ASR"),
            "generator": "podcast2md.py（CapsWriter-Offline / fun_asr_nano）",
            "probe_note": "confirmed_none；已明确选择音频 ASR",
        }, asr=True, txt_text=txt_text, json_path=audio.with_suffix(".json"))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PodError as e:
        print(f"[podcast2md] 失败（exit {e.code}）：{e}", file=sys.stderr)
        sys.exit(e.code)
    except KeyboardInterrupt:
        print("[podcast2md] 用户中断", file=sys.stderr)
        sys.exit(130)
