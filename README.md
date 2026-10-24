# podcast2md-skill

Claude Code / pi 的 Skill：把播客单集链接变成可直接阅读的章节文字稿。

## 它做什么

输入一个 yt-dlp 支持的播客单集链接，自动完成：下载音频 → 本机 CapsWriter-Offline 语音识别 → 按节目已有章节切分 → 产出 `chapters.md`（完整转录稿，非摘要）。

## Skill 内容

`SKILL.md` 是给 AI 助手看的使用说明，包含：

- 运行命令与参数（`--transcribe-timeout`、`--force`、`--polish` 等）
- 常见坑（长音频后台跑、ffmpeg PATH、退出码语义）
- 相邻场景分流：本地音频文件走 FunASR-Nano、B 站视频先探测字幕再决定拉字幕还是转录
- 只要文字稿时默认交付 `chapters.md`，不自动生成论文或摘要
- 明确要求论文式文字稿时，按节目目录分章，使用配套脚本保留正文与片尾文本；摘要事实以转录为准
- 音频、转录和中间产物默认集中保存；明确要求安全另存时，只复制指定的最终论文或摘要，保留原件，不静默覆盖已有文件

## 前置依赖

- Windows + [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline)（含 fun_asr_nano 模型）
- yt-dlp、ffmpeg 在 PATH
- 本机 FunASR-Nano venv（处理本地音频文件时）

> **注意：** `SKILL.md` 中的路径（`D:\iStall\...`）是作者本机的安装位置。
> 复用此 Skill 请按自己的环境修改对应路径。

## 安装

把 Skill 安装到 `~/.agents/skills/podcast2md/`，保留 `SKILL.md`、`references/` 和 `scripts/` 的相对目录结构。多个客户端共用时，可让 `~/.claude/skills/podcast2md/`、`~/.pi/agent/skills/podcast2md/` 通过 Junction 指向该唯一源，不必维护多份副本。安装位置与实际加载方式以客户端配置为准。

## 仓库内容

- `SKILL.md` — Skill 本体（给 AI 助手的说明书）
- `references/paper-transcript.md` — 论文式文字稿、摘要事实边界与安全另存规则
- `scripts/build_paper_transcript.py` — 从既有转录和摘要卡片机械拼装正文，不调用模型改写识别词
- `scripts/podcast2md.py` — 配套转录 CLI；`scripts/README.md` / `scripts/PODCAST2MD.md` 为安装与完整参数文档（双语）

## 本轮验证范围

2026-10-24 的离线配对回归覆盖默认文字稿、论文正文保留、明确安全另存、已有同名文件保护四个场景，新版冻结检查 18/18 通过。每场景每版本仅运行一次，不代表普遍成功率或重复稳定性；没有在本轮重跑下载、ASR 或线上网页目录解析。仓库不包含这些评测的转录夹具、个人反馈、运行日志或本机备份。
