# -*- coding: utf-8 -*-
"""
podcast2md.py — 播客单集链接转写 CLI（单文件，仅标准库）

流水线：yt-dlp 下载 → CapsWriter-Offline 转录 → 按章节切分 → 交付 chapters.md
安装说明：README.md；使用说明：PODCAST2MD.md

边界：
- 只做 CLI；转录只走 start_server.exe / start_client.exe（引擎 fun_asr_nano）。
- 不读 API Key、不调云端模型；无本地润色模型时交付「未润色」原文。
- 不包含说话人分离；多说话人处理不在默认路径内。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
import time
from bisect import bisect_right
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


def build_chapters_md(toc: dict, cues: list[dict], txt_text: str, polish_mode: str) -> str:
    """按目录时间把 srt 条目切进章节；无目录时整篇 txt 直接交付"""
    status = {"off": "未润色（未检测到本地润色模型，以下为转录原文）",
              "basic": "基础规则润色（仅去语气词与相邻重复；无模型、无云端调用）"}[polish_mode]
    src = {"yt-dlp": "yt-dlp chapters", "description": "页面描述时间戳目录",
           "html": "页面 HTML 时间轴", "none": "无目录，整篇一章"}[toc["source"]]
    lines = [f"# {toc['title']}", "",
             f"> 来源：{toc['url']}",
             f"> 生成：podcast2md.py（CapsWriter-Offline / fun_asr_nano）",
             f"> 状态：{status}",
             f"> 章节来源：{src}", ""]

    if toc["source"] == "none":
        body = apply_polish(txt_text, polish_mode)
        lines += [f"## {fmt_ts(0)} 全文", "", body.rstrip(), ""]
        return "\n".join(lines)

    starts = [c["start"] for c in toc["chapters"]]
    buckets = [[] for _ in toc["chapters"]]
    for cue in cues:  # 按条目起点归章：start <= cue.start < 下一章 start
        idx = bisect_right(starts, cue["start"]) - 1
        buckets[max(0, idx)].append(cue["text"])

    for i, chap in enumerate(toc["chapters"]):
        end = toc["chapters"][i + 1]["start"] if i + 1 < len(toc["chapters"]) else cues[-1]["end"]
        chap["end"] = end
        body = "\n".join("\n".join(b.splitlines()) for b in buckets[i]).strip()
        body = apply_polish(body, polish_mode) or EMPTY_CHAPTER_MARK
        lines += [f"## {fmt_ts(chap['start'])} {chap['title']}", "", body, ""]
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


def verify_chapters(md_text: str, txt_text: str) -> dict:
    """验收核心：chapters.md 的正文句必须能在 .txt 里找到（字面优先，归一化兜底）"""
    body_lines = [ln for ln in md_text.splitlines()
                  if ln.strip() and not ln.startswith("#") and not ln.startswith(">")
                  and ln.strip() != EMPTY_CHAPTER_MARK]
    txt_norm = normalize(txt_text)
    miss_literal, miss_all = [], []
    for ln in body_lines:
        if ln in txt_text:
            continue
        miss_literal.append(ln)
        if normalize(ln) not in txt_norm:
            miss_all.append(ln)
    return {"total": len(body_lines), "literal_miss": len(miss_literal),
            "miss_examples": miss_all[:5], "ok": not miss_all}


# ---------------------------------------------------------------- 主流程

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="podcast2md.py",
        description="播客单集 URL → 下载、CapsWriter 转录、按章节切分 → work/<slug>/chapters.md",
        epilog="使用说明见 PODCAST2MD.md；不读 API Key，不调云端模型。")
    p.add_argument("url", help="单集页面或音频直链 URL")
    p.add_argument("--out-dir", default=str(DEFAULT_WORK), help="输出根目录（默认 <脚本目录>/work）")
    p.add_argument("--force", action="store_true", help="目标成品目录已存在时删除重建")
    p.add_argument("--polish", choices=["off", "basic"], default="off",
                   help="off=未润色原文（默认）；basic=保守规则清理（去语气词、相邻重复）")
    p.add_argument("--port", type=int, default=None, help="服务端端口（默认读 config_server.py）")
    p.add_argument("--server-timeout", type=float, default=600, help="等服务端就绪秒数（默认 600）")
    p.add_argument("--transcribe-timeout", type=float, default=7200, help="等转录完成秒数（默认 7200）")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    port = args.port or read_server_port()
    print(f"输入 URL：{args.url}")
    print(f"输出根目录：{args.out_dir}｜服务端端口：{port}｜润色：{args.polish}")

    # 前置检查
    if not shutil.which("ffmpeg"):
        print("警告：ffmpeg 不在 PATH，start_client.exe 文件转录会失败（安装说明见 README.md）")
    for exe in (SERVER_EXE, CLIENT_EXE):
        if not exe.exists():
            raise PodError(EX_USAGE, f"缺少 {exe}，请在 CapsWriter-Offline 根目录运行本脚本")

    # 1) 信息 + slug
    info_log = DEFAULT_WORK / "_podcast2md_info.json"
    info = ytdlp_dump_info(args.url, info_log)
    slug = slugify(info.get("title") or "", info.get("id") or args.url)
    out_dir = Path(args.out_dir) / slug
    print(f"单集标题：{info.get('title')}\nslug：{slug}\n成品目录：{out_dir}")

    # 2) 成品保护：已有则拒绝，除非 --force
    if out_dir.exists() and any(out_dir.iterdir()):
        if not args.force:
            raise PodError(EX_EXISTS, f"目录已存在且非空：{out_dir}（覆盖请加 --force）")
        try:
            shutil.rmtree(out_dir)
        except PermissionError as e:
            raise PodError(EX_EXISTS,
                           f"--force 清空目录失败，文件被占用（常驻服务端日志已移至 work 根目录，重启后旧句柄可释放）：{e}")
        print(f"--force：已清空重建 {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    logs = out_dir / "logs"

    # 3) 下载
    audio = download_audio(args.url, out_dir, slug, logs / "ytdlp.log")

    # 4) 目录
    toc = extract_toc(info)
    n = len(toc["chapters"])
    print(f"章节：{n} 章（来源：{toc['source']}）" +
          ("；仅一章「全文」" if toc["source"] == "none" else
           "；" + " / ".join(c["title"][:12] for c in toc["chapters"][:5])))

    # 5) 转录（服务端按需拉起，客户端结束代答回车）；服务端日志放 work 根目录共享，避免锁住单集目录
    server_log = Path(args.out_dir) / "_podcast2md_server.log"
    server_proc = ensure_server(port, args.server_timeout, server_log)
    try:
        run_client(audio, logs / "client.log", args.transcribe_timeout)
    finally:
        if server_proc is not None and server_proc.poll() is None:
            log("服务端保持运行（复用加速下次转录）；如需停止请托盘退出或结束 start_server.exe")

    # 6) 切分 + 校验 + 落盘
    txt_text = audio.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")
    cues = parse_srt(audio.with_suffix(".srt"))
    md_text = build_chapters_md(toc, cues, txt_text, args.polish)
    v = verify_chapters(md_text, txt_text)

    (out_dir / "chapters.md").write_text(md_text, encoding="utf-8")
    toc["slug"] = slug
    toc["transcript"] = {f"{ext}": audio.with_suffix(ext).name for ext in (".txt", ".srt", ".json")}
    toc["verify"] = {"body_lines": v["total"], "literal_miss": v["literal_miss"],
                     "normalized_miss": 0 if v["ok"] else len(v["miss_examples"])}
    (out_dir / "toc.json").write_text(json.dumps(toc, ensure_ascii=False, indent=2), encoding="utf-8")

    # 7) 汇报
    print(f"章节句校验：{v['total']} 行，字面缺失 {v['literal_miss']}，归一化后缺失 {0 if v['ok'] else len(v['miss_examples'])}")
    if not v["ok"]:
        print("缺失示例：" + " ｜ ".join(v["miss_examples"]))
        raise PodError(EX_SPLIT, "chapters.md 校验未通过：存在 .txt 中找不到的句子（见上方示例）")
    print("完成。产物：\n  " + "\n  ".join(str(f) for f in [
        audio, out_dir / "toc.json", audio.with_suffix(".txt"),
        audio.with_suffix(".srt"), audio.with_suffix(".json"), out_dir / "chapters.md"]))
    return EX_OK


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PodError as e:
        print(f"[podcast2md] 失败（exit {e.code}）：{e}", file=sys.stderr)
        sys.exit(e.code)
    except KeyboardInterrupt:
        print("[podcast2md] 用户中断", file=sys.stderr)
        sys.exit(130)
