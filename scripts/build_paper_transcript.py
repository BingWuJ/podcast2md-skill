# -*- coding: utf-8 -*-
"""把 chapters.md 和摘要卡片拼成论文式文字稿。不改识别词。"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from podcast2md import chapter_body_units, coverage_report, text_units

NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
        "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]


def is_tail_line(text: str) -> bool:
    text = text.strip()
    if text and all(ord(ch) < 128 for ch in text):
        return True
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 8:
        return False
    latin = sum(1 for ch in letters if ord(ch) < 128)
    return latin / len(letters) > 0.8


def close_sentence(text: str) -> str:
    text = text.strip().lstrip("，、；：。")
    if not text or is_tail_line(text):
        return text
    if text[-1] in "。！？…":
        return text
    if text[-1] in "，、；：":
        text = text[:-1]
    return text + "。"


def paragraphs(lines):
    talk, tail = [], []
    seen_tail = False
    for line in lines:
        if is_tail_line(line):
            seen_tail = True
        if seen_tail:
            tail.append(line)
        else:
            sent = close_sentence(line)
            if sent:
                talk.append(sent)
    paras, buf, size = [], [], 0
    for sent in talk:
        buf.append(sent)
        size += len(sent)
        if len(buf) >= 4 or size >= 180:
            paras.append("".join(buf))
            buf, size = [], 0
    if buf:
        paras.append("".join(buf))
    return paras, tail


def parse_chapters(text: str):
    parts = text.split("\n## ")
    sections = []
    for part in parts[1:]:
        lines = part.splitlines()
        title = lines[0].strip()
        body = [line.strip() for line in lines[1:] if line.strip()]
        sections.append((title, body))
    if not sections:
        raise SystemExit("chapters.md 里没有 ## 章节")
    return sections


def verify_note(episode_dir: Path) -> str:
    toc = episode_dir / "toc.json"
    if not toc.exists():
        return "校验结果见转录日志。旧的包含检查不能证明全文完整。"
    data = json.loads(toc.read_text(encoding="utf-8"))
    verify = data.get("verify") or {}
    if "coverage_ok" not in verify:
        return "这份转录只有旧校验，不能把包含检查当成全文覆盖通过。"
    return (
        f"全文覆盖 {'通过' if verify.get('coverage_ok') else '未通过'}，"
        f"缺失 {verify.get('missing_count')}，增加 {verify.get('added_count')}，"
        f"重复 {verify.get('duplicate_count')}，乱序 {verify.get('reordered')}，"
        f"替换 {verify.get('replaced_count')}。时间轴 {'通过' if verify.get('timeline_ok') else '未通过'}。"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode-dir", required=True)
    parser.add_argument("--card", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--subtitle", required=True)
    parser.add_argument("--url", default="")
    args = parser.parse_args()

    episode = Path(args.episode_dir)
    chapters_path = episode / "chapters.md"
    card_path = Path(args.card)
    if not chapters_path.exists():
        raise SystemExit(f"缺少 {chapters_path}")
    if not card_path.exists():
        raise SystemExit(f"缺少摘要卡片 {card_path}")

    sections = parse_chapters(chapters_path.read_text(encoding="utf-8"))
    card = card_path.read_text(encoding="utf-8").strip()
    if not card.startswith("## 摘要卡片"):
        card = "## 摘要卡片\n\n" + card
    url = args.url
    if not url and (episode / "toc.json").exists():
        url = json.loads((episode / "toc.json").read_text(encoding="utf-8")).get("url") or ""

    out = [
        f"# {args.title}",
        "",
        f"**——{args.subtitle}**",
        "",
        f"来源页面：{url or '见 toc.json'}",
        "",
        f"原始转录：同目录 `chapters.md`。{verify_note(episode)}",
        "",
        "---",
        "",
        card,
        "",
        f"整理方式：正文 {len(sections)} 节标题与时间沿用节目目录。文字来自 `chapters.md`，不删句、不换词；只在句末补标点，并按约四句或约 180 字分成段落。片尾非对谈文本另附，标明不是对谈。",
        "",
        "---",
        "",
        "## 正文",
        "",
    ]
    for index, (title, lines) in enumerate(sections):
        label = NUMS[index] if index < len(NUMS) else str(index + 1)
        out.append(f"### {label}、{title}")
        out.append("")
        paras, tail = paragraphs(lines)
        for para in paras:
            out.append(para)
            out.append("")
        if tail:
            out.append("以下为该节末尾识别出的非对谈文本，原文保留，未并入上面的段落。")
            out.append("")
            out.extend(tail)
            out.append("")

    generated = "\n".join(out)
    body = generated.split("## 正文", 1)[-1]
    derived = [line for line in text_units(body)
               if not line.startswith("### ") and "非对谈文本" not in line
               and line != "（本章无字幕内容）"]
    report = coverage_report(chapter_body_units(chapters_path.read_text(encoding="utf-8")),
                             derived, faithful=False)
    print(
        "论文正文覆盖："
        f"缺失 {report['missing_count']}，增加 {report['added_count']}，"
        f"重复 {report['duplicate_count']}，乱序 {report['reordered']}，"
        f"替换 {report['replaced_count']}，标点 {report['punctuation_count']}。"
    )
    if not report["content_ok"]:
        raise SystemExit("论文正文没有覆盖章节原稿。未写入论文式文字稿.md")
    dest = episode / "论文式文字稿.md"
    dest.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"sections={len(sections)}")
    print(dest)


if __name__ == "__main__":
    main()
