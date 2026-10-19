# PODCAST2MD 使用说明 / Usage Guide

[中文](#中文) · [English](#english) · [项目摘要 / Project summary](README.md)

## 中文

输入一个播客单集链接，得到按节目已有章节整理的完整文字稿，而不是摘要。本工具在 Windows 上调用已安装的 CapsWriter-Offline 完成语音转文字。
首次使用请先看 [README](README.md)；本文列出全部参数、输出文件和错误码。

### 用法

先按 [README 安装说明](README.md#中文) 准备环境，将脚本放在 CapsWriter-Offline 根目录，再运行：

```powershell
python .\podcast2md.py "单集URL"
python .\podcast2md.py "单集URL" --force
python .\podcast2md.py "单集URL" --polish basic
python .\podcast2md.py "单集URL" --server-timeout 900 --transcribe-timeout 10800
python .\podcast2md.py --help
```

默认不覆盖已有成品。**`--force` 会删除已有单集成品目录后重跑，不会保留手动修改。**

| 参数 | 默认 | 说明 |
|---|---|---|
| `url` | 必填 | 单集页面或音频直链（须为 yt-dlp 支持的地址） |
| `--out-dir` | `<脚本目录>/work` | 输出根目录，成品在 `<输出根目录>/<slug>/` |
| `--force` | 关 | 已有成品目录非空时，删除重建 |
| `--polish` | `off` | `off`=未润色原文；`basic`=去段首尾语气词、同字 3 连及以上收敛为 1 字 |
| `--port` | 读 `config_server.py`，失败回退 6016 | 服务端监听探测端口；不会改写 CapsWriter 客户端/服务端配置 |
| `--server-timeout` | 600 秒 | 拉起 `start_server.exe` 后等待就绪的时长 |
| `--transcribe-timeout` | 7200 秒 | 等待转录产物完成的时长 |

`--polish basic` 不是模型润色：规则可能影响有意义的重复字符或数字，也可能因正文校验失败而退出。需要忠实原稿时使用默认 `off`，保留 `.txt` 后再人工或由 AI 助手校对。`--port` 应与现有 CapsWriter 配置一致，不能单靠此参数更改转录服务地址。

### 流水线

1. **下载**：本机 `yt-dlp -J` 取单集信息（标题、章节、描述），`-f bestaudio/best --write-info-json` 下载音频。
2. **章节目录**：优先 yt-dlp chapters；否则解析描述中 `M:SS 标题` 时间戳行（至少 2 条）；再尝试单集页 HTML 时间轴区块。全部失败则只放一章「全文」，不发明章节。首章之前的内容并入第一章。HTML 提取是格式相关的尽力回退，不保证任意网站通用。
3. **转录**：探测本地服务端端口；未运行则拉起 `start_server.exe`，不改引擎配置。启动 `start_client.exe <音频>` 转录，产物齐备后 CLI 代写回车越过「按回车退出」，再等待/终止客户端进程。
4. **切分**：解析 `.srt`，按条目起点时间归入章节，写入 `chapters.md`。不会在跨章字幕条目内部逐字切分。
5. **校验**：`chapters.md` 每行正文必须在 `.txt` 中能找到；字面匹配优先，去标点空白后兜底，失败则报错退出。

### 成品目录 `<输出根目录>/<slug>/`

```text
<slug>.<ext>           下载的音频
<slug>.info.json       yt-dlp 单集信息
<slug>.txt             CapsWriter 原文
<slug>.srt             CapsWriter 字幕
<slug>.json            CapsWriter 时间戳数据
toc.json               章节目录、来源、校验摘要
chapters.md            按章节整理的文字稿
logs/                  yt-dlp、客户端日志
```

服务端日志位于输出根目录的 `_podcast2md_server.log`，不在单集目录内。

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 2 | 用法错误或缺少必要程序文件 |
| 3 | 下载失败 |
| 4 | 服务端失败 |
| 5 | 转录失败 |
| 6 | 成品已存在，或覆盖目录时被占用 |
| 7 | 切分或正文校验失败 |
| 130 | 用户中断 |

### 使用边界

- 只做 CLI；脚本不读取 API Key、不调云端润色模型、不改 `LLM/` 角色配置。
- 默认 `chapters.md` 只放按时间切开的原文，并标注未润色；后续润色应忠于原文、不加事实、不缩成摘要。
- 可以让有本机命令执行权限的 AI 助手代为运行；CLI 本身没有自然语言输入解析功能。
- 服务端就绪后保持运行，托盘退出即可停止；CLI 不保证清理整个服务端进程树。
- 多人对话的说话人分离不在本次范围。
- 本机验收环境为 `fun_asr_nano`，需要上游要求的 Visual C++ 运行库与模型。下载需要网络，转录走本地。
- 超过 2 小时录音、任意站点 HTML 提取及 `--polish basic` 完整端到端链路仍需进一步验证。

## English

Give the tool a podcast episode link and get a full transcript organized by the show's existing chapters—not a summary. It runs on Windows and uses an installed copy of CapsWriter-Offline for speech recognition.
Start with the [README](README.md) if you are new to the tool. This guide lists all options, output files, and exit codes.

### Usage

Follow the [README installation instructions](README.md#english), place the script in the CapsWriter-Offline root directory, and run:

```powershell
python .\podcast2md.py "EPISODE_URL"
python .\podcast2md.py "EPISODE_URL" --force
python .\podcast2md.py "EPISODE_URL" --polish basic
python .\podcast2md.py "EPISODE_URL" --server-timeout 900 --transcribe-timeout 10800
python .\podcast2md.py --help
```

Existing output is protected by default. **`--force` deletes the existing episode output directory before rerunning, including any manual edits.**

| Argument | Default | Description |
|---|---|---|
| `url` | Required | Episode page or direct audio URL supported by yt-dlp |
| `--out-dir` | `<script directory>/work` | Output root; each episode is saved under `<output root>/<slug>/` |
| `--force` | Disabled | Delete and recreate an existing nonempty episode output directory |
| `--polish` | `off` | `off` preserves the transcript; `basic` removes boundary fillers and collapses three or more identical consecutive characters to one |
| `--port` | Read from `config_server.py`, falling back to 6016 | Port used to probe the server; does not rewrite CapsWriter client or server configuration |
| `--server-timeout` | 600 seconds | Maximum wait for the launched server to become ready |
| `--transcribe-timeout` | 7200 seconds | Maximum wait for transcription output |

`--polish basic` is not model-based editing. Its rules can affect meaningful repeated characters or digits, and the result may fail transcript validation. For a faithful source transcript, keep the default `off` and proofread a copy of the `.txt` file manually or with an AI assistant. `--port` must match the existing CapsWriter setup; this flag alone cannot change the transcription service address.

### Pipeline

1. **Download:** run `yt-dlp -J` to retrieve episode metadata, then download audio with `-f bestaudio/best --write-info-json`.
2. **Chapter outline:** prefer yt-dlp chapters, then description timestamp lines such as `M:SS Title` (at least two entries), then an HTML timeline. If none is available, use a single full-transcript chapter. Content before the first chapter is included in that chapter. HTML extraction is format-dependent and best-effort.
3. **Transcribe:** probe the local server port and launch `start_server.exe` if needed without changing its engine configuration. Invoke `start_client.exe <audio>`. Once the output files are ready, send a newline to dismiss the exit prompt, then wait for or terminate the client process.
4. **Segment:** parse `.srt` and assign each cue to a chapter using its start time. Cues crossing a chapter boundary are not split character by character.
5. **Validate:** check every transcript body line in `chapters.md` against `.txt`, using literal matching first and a punctuation/whitespace-normalized fallback. Exit with an error if validation fails.

### Output directory: `<output root>/<slug>/`

```text
<slug>.<ext>           Downloaded audio
<slug>.info.json       yt-dlp metadata
<slug>.txt             Original CapsWriter transcript
<slug>.srt             CapsWriter subtitles
<slug>.json            CapsWriter timestamp data
toc.json               Chapters, sources, and validation summary
chapters.md            Chapter-organized transcript
logs/                  yt-dlp and client logs
```

The server log is stored at `<output root>/_podcast2md_server.log`, outside the episode directory.

| Exit code | Meaning |
|---|---|
| 0 | Success |
| 2 | Usage error or missing required application files |
| 3 | Download failure |
| 4 | Server failure |
| 5 | Transcription failure |
| 6 | Output already exists, or files are locked during replacement |
| 7 | Segmentation or transcript validation failure |
| 130 | Interrupted by the user |

### Scope and constraints

- CLI only. The script does not read API keys, invoke cloud polishing models, or modify role configuration under `LLM/`.
- By default, `chapters.md` contains the original transcript organized by timestamp and is labeled unpolished. Subsequent editing must remain faithful: no added facts and no summarization.
- An AI assistant with local command execution access can run the tool for you. The CLI itself does not interpret natural-language requests.
- The server remains running for reuse. Exit through its tray menu; the CLI does not guarantee cleanup of the entire server process tree.
- Speaker diarization is out of scope.
- The validated setup uses `fun_asr_nano` and the upstream project's required Visual C++ runtime and model files. Downloads require network access; transcription runs locally.
- Audio longer than two hours, arbitrary-site HTML extraction, and the complete `--polish basic` workflow need further validation.
