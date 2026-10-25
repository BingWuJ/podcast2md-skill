# podcast2md-skill

Claude Code / pi 的 Skill：把播客或 B 站单集链接变成可直接阅读的章节文字稿。

**当前版本 v2.0.0（2026-10-25）。** 这一版把默认流水线反过来：先独立探测字幕，有可用轨道就直接出稿、不下载音频也不跑语音识别；只有确认没有可用轨道才下载音频转写。更新原因、改动清单和兼容性见 [CHANGELOG.md](CHANGELOG.md)。

安装不要只看本页的简介。给人看的步骤、给 Agent 的单段命令、每个依赖的官方链接和通过条件都在 [references/install.md](references/install.md)。Agent 执行 [references/install-agent.ps1](references/install-agent.ps1)，不要自己猜测安装包地址。

## 它做什么

输入一个 yt-dlp 支持的播客或 B 站单集链接，先独立探测字幕，再走两条路线之一：

- **有可用字幕轨道**：保存字幕原件到 `original-subs/`，按节目已有章节切分，产出 `chapters.md`，不下载音频、不跑语音识别。来源标注 `普通CC` 或 `平台AI`。
- **确认没有可用轨道**（弹幕不算）：下载音频 → 本机 CapsWriter-Offline 语音识别 → 按节目已有章节切分 → 产出 `chapters.md`。来源标注 `本机ASR`。

需要登录、请求失败、`--sub-lang` 无匹配时脚本停止，不写成「确认无字幕」，也不静默改跑语音识别。探测结果写入 `subtitle-probe.json`。产出是完整转录稿，不是摘要。

## Skill 内容

`SKILL.md` 是给 AI 助手看的使用说明，包含：

- 运行命令与参数（`--transcribe-timeout`、`--sub-lang`、`--force`、`--polish` 等）
- 常见坑（长音频后台跑、ffmpeg PATH、退出码语义、端口误判）
- B 站字幕三种来源标注与探测状态语义；失败状态不得写成「确认无字幕」
- 相邻场景分流：本地音频文件走 FunASR-Nano、用户单独给出的 srt/vtt 走 srt-translator
- 只要文字稿时默认交付 `chapters.md`，不自动生成论文或摘要
- 明确要求论文式文字稿时，按节目目录分章，使用配套脚本保留正文与片尾文本；摘要事实以转录为准
- 音频、转录和中间产物默认集中保存；明确要求安全另存时，只复制指定的最终论文或摘要，保留原件，不静默覆盖已有文件

## 前置依赖

- Windows + Python 3.10+ + yt-dlp
- 仅语音识别路线需要：ffmpeg 在 PATH、[CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline)（含 fun_asr_nano 模型）
- 本机 FunASR-Nano venv（处理本地音频文件时）

> **注意：** CapsWriter 目录使用 `$env:CAPSWRITER_HOME`，不要抄某一台电脑的固定路径。
> 安装步骤见 [references/install.md](references/install.md)。

## 安装

先按 [references/install.md](references/install.md) 安装 Python、VC++ 运行库、FFmpeg、yt-dlp、CapsWriter-Offline 和 Fun-ASR-Nano 模型，再安装 Skill。Skill 目录是 `~/.agents/skills/podcast2md/`，必须保留 `SKILL.md`、`references/` 和 `scripts/`。多个客户端共用时，让 `~/.claude/skills/podcast2md/`、`~/.pi/agent/skills/podcast2md/` 通过 Junction 指向该目录，不复制第二份。

## 仓库内容

- `SKILL.md` — Skill 本体（给 AI 助手的说明书）
- `CHANGELOG.md` — 版本历史：每次更新为什么改、改了什么、兼容性与验证范围
- `references/paper-transcript.md` — 论文式文字稿、摘要事实边界与安全另存规则
- `scripts/build_paper_transcript.py` — 从既有转录和摘要卡片机械拼装正文，不调用模型改写识别词；写盘前自检正文覆盖
- `scripts/podcast2md.py` — 配套转录 CLI；`scripts/README.md` / `scripts/PODCAST2MD.md` 为安装与完整参数文档（双语）
- `scripts/test_transcript_checks.py` — 字幕探测状态与全文覆盖校验的确定性单测（15 条，不下载、不写 `work/`）

## 本轮验证范围

2026-10-25（v2.0.0）：`python -m unittest test_transcript_checks -v` → **15 tests, OK**（Python 3.14.6 / Windows），覆盖全文覆盖对齐（完全一致、删尾、重复、乱序、等长替换、标点）与探测状态分类（JSON 字段为空不作结论、AI 轨、CC 轨、需登录、请求失败、仅弹幕、空输出、`--sub-lang` 不匹配、无效时间戳保留文本）。

2026-10-24 的离线配对回归覆盖默认文字稿、论文正文保留、明确安全另存、已有同名文件保护四个场景，冻结检查 18/18 通过。每场景每版本仅运行一次，不代表普遍成功率或重复稳定性；**v2.0.0 未在本轮重跑真实下载、平台字幕下载或 ASR 转录**，因此平台字幕实际覆盖率与 AI 字幕质量对比都没有实测结论。仓库不包含这些评测的转录夹具、个人反馈、运行日志或本机备份。
