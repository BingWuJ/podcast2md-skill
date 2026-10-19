# podcast2md

**把播客链接变成可以直接阅读的分章节文字稿。**

**Turn a podcast link into a readable, chaptered transcript.**

[中文](#中文) · [English](#english) · [完整参数 / All options](PODCAST2MD.md)

## 中文

### 它是做什么的？

给它一个播客单集链接，它会下载音频，调用本机的语音识别工具转成文字，再按节目已有的章节整理成一份文档。你可以用来读稿、搜索内容，或者继续做笔记。

```text
单集链接 → 下载音频 → 本机语音转文字 → 按已有章节整理 → chapters.md
```

**得到的是完整转录稿，不是摘要，也不会替你编写节目里没说过的内容。** 语音识别可能听错，重要内容仍需对照音频核实。

> **使用前提：Windows + 已安装的 CapsWriter-Offline。**
> 本项目负责把下载、转录和整理串起来，不自带语音识别程序或模型。下载本仓库并不能直接开始转录。

### 怎么开始？

**1. 准备环境**

- Windows 10/11、Python 3.10+。
- 安装 [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline/releases) 及它需要的模型和运行库，先确认它能转录音频文件。
- 安装 `yt-dlp` 和 FFmpeg，并确保能在终端调用。FFmpeg 按[官方说明](https://ffmpeg.org/download.html)安装；`yt-dlp` 可以这样安装：

```powershell
python -m pip install --upgrade yt-dlp
```

**2. 放好脚本**

下载本仓库的 [`podcast2md.py`](podcast2md.py)，放进 CapsWriter-Offline 安装目录，与 `start_server.exe`、`start_client.exe` 和 `config_server.py` 放在一起。

**3. 运行并读稿**

在该安装目录打开 PowerShell，把下面的示例链接换成你要转录的单集链接：

```powershell
python .\podcast2md.py "https://www.youtube.com/watch?v=jNQXAC9IVRw"
```

完成后，打开脚本目录下的 **`work/<单集目录>/chapters.md`**。同一目录还会保留音频、原始文字、字幕和时间戳文件。

### 不想记命令，可以直接对 AI 说吗？

可以。把链接发给**有本机命令执行权限**的 AI 助手，例如：

> 用 podcast2md 把这个链接转成完整文字稿，按节目已有章节整理，不要总结，也不要覆盖已有文件：链接。

AI 助手替你运行命令并检查结果。**自然语言交互由助手提供，不是这个脚本自带聊天功能；仅能聊天、不能运行本机命令的 AI 无法直接操作它。**

### 给 AI 助手的调用规则

| 项目 | 规则 |
|---|---|
| 输入 | 一个 yt-dlp 支持的单集页面或音频直链 URL；当前入口不是本地文件路径 |
| 运行位置 | CapsWriter-Offline 安装目录；脚本、服务端和客户端程序必须在同一目录 |
| 前置检查 | `python`、`yt-dlp`、`ffmpeg` 可调用，CapsWriter 及模型已安装；不要把仓库克隆目录当成完整运行环境 |
| 默认命令 | `python .\podcast2md.py "EPISODE_URL"`；使用参数数组传递用户 URL，不拼接未经转义的 shell 命令 |
| 成功判定 | 退出码为 `0`，并确认本次输出目录的 `chapters.md`、`toc.json` 及 `.txt/.srt/.json` 均存在且非空 |
| 失败处理 | 非零退出码就报告错误，不宣称完成；含个人路径或链接的日志先脱敏再分享 |
| 覆盖限制 | 不自行添加 `--force`：它会删除同名单集的输出目录，须先得到用户明确允许 |
| 内容要求 | 默认保留转录原文；没有章节就保留「全文」，不要自行编章节或把正文换成摘要 |

全部参数、退出码和输出结构见 [详细使用说明](PODCAST2MD.md)。

### 用之前还需要知道什么？

- **不是任意链接都支持。** 下载取决于 yt-dlp 对该网站和链接的支持，以及网络、登录和站点限制。
- **转录在本机进行，下载仍需联网。** 已验证的语音引擎配置是 CapsWriter 的 `fun_asr_nano`；脚本不会替你安装模型或修改引擎。
- **章节来自节目，不由 AI 生成。** 优先读取 yt-dlp 章节，其次描述时间戳，再尝试网页时间轴；找不到就生成一章「全文」。网页解析不保证对所有网站有效。
- **按字幕条目的起点分章，不是逐字切章。** 跨章节的同一条字幕不会从中间拆开。
- **默认不润色、不覆盖。** `--polish basic` 只是可能误删有效重复字符的规则清理，不是模型润色，建议先用默认原稿。
- **没有说话人分离、图形界面或 MCP 服务。** 启动的 CapsWriter 服务端会保留运行，可从托盘退出。
- 仓库不包含模型、运行配置、录音或个人转录内容。请只处理你有权下载和转录的内容。

## English

### What does it do?

Give it a link to a podcast episode. It downloads the audio, transcribes it using a locally installed speech recognition tool, and organizes the transcript into a document using the episode's existing chapters. You can read the transcript, search its contents, or use it as a starting point for your notes.

```text
Episode link → Download audio → Transcribe locally → Organize by existing chapters → chapters.md
```

**The result is a full transcript, not a summary. It does not invent content that was never said in the episode.** Speech recognition can make mistakes, so check important details against the audio.

> **Requirements: Windows + an existing CapsWriter-Offline installation.**
> This project connects the download, transcription, and formatting steps. It does not include a speech recognition engine or models. Downloading this repository alone is not enough to start transcribing.

### How do I get started?

**1. Set up the environment**

- Windows 10/11 and Python 3.10+.
- Install [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline/releases), along with its required models and runtime dependencies. First, make sure it can transcribe audio files.
- Install `yt-dlp` and FFmpeg, and make sure both are available from your terminal. Follow the [official instructions](https://ffmpeg.org/download.html) to install FFmpeg. You can install `yt-dlp` with:

```powershell
python -m pip install --upgrade yt-dlp
```

**2. Put the script in place**

Download [`podcast2md.py`](podcast2md.py) from this repository and place it in your CapsWriter-Offline installation directory, alongside `start_server.exe`, `start_client.exe`, and `config_server.py`.

**3. Run it and read the transcript**

Open PowerShell in that installation directory and replace the example URL below with the link to the episode you want to transcribe:

```powershell
python .\podcast2md.py "https://www.youtube.com/watch?v=jNQXAC9IVRw"
```

When it finishes, open **`work/<episode-directory>/chapters.md`** under the script directory. The same output directory also keeps the audio, raw transcript, subtitles, and timestamp files.

### Can I just ask an AI instead of remembering the command?

Yes. Send the link to an AI assistant **that can execute commands on your computer**, for example:

> Use podcast2md to turn this link into a full transcript, organized by the episode's existing chapters. Do not summarize or overwrite existing files: [link].

The AI assistant runs the command and checks the results for you. **The assistant provides the natural-language interface; the script itself has no built-in chat feature. An AI that can only chat, but cannot execute local commands, cannot operate it directly.**

### Invocation rules for AI assistants

| Item | Rule |
|---|---|
| Input | A URL for an episode page or a direct audio link supported by yt-dlp; the current entry point does not accept local file paths |
| Working directory | The CapsWriter-Offline installation directory; the script, server, and client executables must be in the same directory |
| Prerequisite checks | Ensure `python`, `yt-dlp`, and `ffmpeg` are available, and CapsWriter and its models are installed; do not treat a clone of this repository as a complete runtime environment |
| Default command | `python .\podcast2md.py "EPISODE_URL"`; pass the user's URL through an argument array rather than concatenating it into an unescaped shell command |
| Success criteria | The exit code is `0`, and `chapters.md`, `toc.json`, and the `.txt/.srt/.json` transcription files in this run's output directory all exist and are nonempty |
| Failure handling | Report any nonzero exit code as an error; do not claim completion. Redact personal paths and links from logs before sharing them |
| Overwrite restrictions | Do not add `--force` on your own: it deletes the output directory for an episode with the same name and requires the user's explicit permission first |
| Content requirements | Preserve the original transcript by default. If no chapters are available, keep the single “全文” (“Full text”) chapter; do not invent chapters or replace the transcript with a summary |

See the [detailed usage guide](PODCAST2MD.md) for all options, exit codes, and the output directory structure.

### What else should I know before using it?

- **Not every link is supported.** Downloads depend on yt-dlp's support for the site and URL, as well as network conditions, login requirements, and site restrictions.
- **Transcription runs locally, but downloading still requires an internet connection.** The verified speech engine configuration is CapsWriter's `fun_asr_nano`; the script does not install models or change the engine for you.
- **Chapters come from the episode, not from AI.** The script first looks for chapters provided by yt-dlp, then timestamps in the description, and finally a timeline on the webpage. If none are found, it creates a single “全文” (“Full text”) chapter. Webpage parsing is not guaranteed to work on every site.
- **Chapter boundaries follow subtitle entry start times, not individual words.** A subtitle entry that spans a chapter boundary is not split in the middle.
- **No polishing or overwriting by default.** `--polish basic` only applies rule-based cleanup, which may accidentally remove meaningful repeated characters. It is not model-based polishing; start with the default, unpolished transcript.
- **There is no speaker diarization, graphical interface, or MCP service.** The CapsWriter server started by the script remains running afterward; you can exit it from the system tray.
- The repository contains no models, runtime configuration, recordings, or personal transcripts. Only process content you have permission to download and transcribe.

## 致谢 / Acknowledgments

语音转录由 [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline) 提供，下载使用 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，媒体处理依赖 [FFmpeg](https://ffmpeg.org/)。上游组件适用各自的许可证。

Transcription is provided by CapsWriter-Offline, downloads by yt-dlp, and media processing by FFmpeg. Each upstream component is subject to its own license.
