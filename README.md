# podcast2md-skill

Claude Code / pi 的 Skill：把播客单集链接变成可直接阅读的章节文字稿。

## 它做什么

输入一个 yt-dlp 支持的播客单集链接，自动完成：下载音频 → 本机 CapsWriter-Offline 语音识别 → 按节目已有章节切分 → 产出 `chapters.md`（完整转录稿，非摘要）。

## Skill 内容

`SKILL.md` 是给 AI 助手看的使用说明，包含：

- 运行命令与参数（`--transcribe-timeout`、`--force`、`--polish` 等）
- 常见坑（长音频后台跑、ffmpeg PATH、退出码语义）
- 相邻场景分流：本地音频文件走 FunASR-Nano、B 站视频先探测字幕再决定拉字幕还是转录

## 前置依赖

- Windows + [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline)（含 fun_asr_nano 模型）
- yt-dlp、ffmpeg 在 PATH
- 本机 FunASR-Nano venv（处理本地音频文件时）

> **注意：** `SKILL.md` 中的路径（`D:\iStall\...`）是作者本机的安装位置。
> 复用此 Skill 请按自己的环境修改对应路径。

## 安装

把整个目录放进 `~/.claude/skills/` 或 `~/.agents/skills/`（推荐 Junction 共享）即可被自动发现。

## 仓库内容

- `SKILL.md` — Skill 本体（给 AI 助手的说明书）
- `scripts/` — 配套 CLI 脚本源码：`podcast2md.py`（主脚本）、`README.md` / `PODCAST2MD.md`（安装与完整参数文档，双语）
