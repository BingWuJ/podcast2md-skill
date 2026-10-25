---
name: podcast2md
description: 把播客或 B 站单集链接转成按章节整理的完整文字稿（产出 chapters.md，非摘要）。用户要求转录、转文字稿、提取字幕或整理成文，或按网页目录写成论文式文字稿、摘要卡片时使用。只说转文字稿时不要自动写论文稿。B 站先由 CLI 独立探测字幕并标明普通CC、平台AI或本机ASR；JSON 字幕字段为空、需登录或请求失败都不能写成确认无字幕，也不能静默改跑 ASR。不接收 Cookie，不安装下载器。音频、转录和中间产物默认放在部署副本所在目录的 work\<slug>\。用户明确要求把最终论文或摘要另存到安全目录时再复制，不搬动原始转录，不无提示覆盖已有文件。本地无链接音频走 FunASR-Nano。不要字幕、只讨论节目内容时不触发。
---

# podcast2md — 播客单集链接 → 章节文字稿

## 缺依赖时先安装

运行前先检查 `python`、`ffmpeg`、`ffprobe`、`yt-dlp`，以及 `start_server.exe` 所在目录和 Fun-ASR-Nano 的四个模型文件。缺任何一项时，读取 [references/install.md](references/install.md)，只执行其中的 Agent 命令；不要从软件名称猜测下载地址，也不要把 FFmpeg 只下载不解压、不加入 PATH。安装脚本退出码不是 0 时停止，不能声称已安装。

CapsWriter 目录用 `$env:CAPSWRITER_HOME`。未设置时，以安装脚本 JSON 的 `capswriter.detail` 为准，不要写死某一台电脑的磁盘路径。

## 定位

- 输入：yt-dlp 支持的播客单集页面或音频直链
- 输出：部署副本所在目录的 `work\<slug>\chapters.md`。`$env:CAPSWRITER_HOME` 应指向该部署副本；两者不一致时，以脚本所在目录为准，并查看启动警告。
- 引擎：本机 CapsWriter-Offline（fun_asr_nano），脚本自动拉起 server/client

## 运行（用部署副本，必须与 start_server.exe 同目录）

部署目录就是 `start_server.exe` 所在目录。先确认实际路径，不要猜，也不要在变量为空时执行 `python "$env:CAPSWRITER_HOME\podcast2md.py"`，那会变成 `python "\podcast2md.py"`。

`CAPSWRITER_HOME` 有值时：

```powershell
python "$env:CAPSWRITER_HOME\podcast2md.py" "单集URL"
python "$env:CAPSWRITER_HOME\podcast2md.py" "单集URL" --transcribe-timeout 10800
```

没有值时，先进入部署目录，再用相对路径：

```powershell
Set-Location '<start_server.exe 所在目录>'
python .\podcast2md.py "单集URL"
python .\podcast2md.py "单集URL" --transcribe-timeout 10800
```

尖括号内容要换成已确认的部署目录，不要原样执行。

默认不要加 `--out-dir`。输出根目录是部署副本所在目录的 `work`。`--out-dir` 只作为逃生口；传入非默认值时，脚本会警告实际根目录已改变。最终论文或摘要的另存仍是复制，不要用这个参数搬走原始音频和转录。

- **部署副本**：就是 `start_server.exe` 所在目录，`podcast2md.py` 必须放在同一目录。改脚本先改仓库版，再复制到该目录；不要写死仓库磁盘位置。
- 完整参数表、流水线细节、退出码：按需读部署目录的 `PODCAST2MD.md`，或本 Skill 的 `scripts/PODCAST2MD.md`，不要默认整读。

## 成品目录（默认集中，2026-10-24 修订）

音频、转录和中间产物默认放在部署副本所在目录的 `work\<slug>\`。这些原件留在该集目录，不搬动、不删除：

- `chapters.md`、音频、`.txt` / `.srt` / `.json` / `toc.json`

没有明确另存要求时，论文式文字稿和摘要卡片也只写在该集目录，不要复制到项目目录、桌面或其他 work。

用户明确要求把最终论文式文字稿或摘要卡片复制、另存到本次允许的安全目录时，执行复制。保留原件。目标里已有同名文件时，不要无提示覆盖；先说明并停下，除非用户明确允许覆盖。不要把另存扩大到本次允许范围之外。

## 关键参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--out-dir` | 部署副本所在目录的 `work` | 默认不要传。非默认值是逃生口，脚本会警告。最终稿另存不改这个根目录。 |
| `--force` | 关 | 删除已有单集目录重跑；会丢手动修改 |
| `--polish` | `off` | `basic` 只是规则去语气词，非模型润色；要忠实原稿用 `off` |
| `--server-timeout` | 600s | server 拉起等待 |
| `--transcribe-timeout` | `max(600, 音频秒数×4+120)` | 未传时按 ffprobe 时长计算；取不到时长用 7200。显式传入后不被覆盖 |

## 坑（先读再跑）

- 长音频仍然后台跑并轮询日志，别前台干等撞工具超时。这是为避开工具超时，不是因为 CapsWriter 一定要跑几十分钟。耗时用下面 2026-10-24 的实测，不要拿 FunASR-Nano 的 40–90 分钟去估 CapsWriter。
- server 转录完保持常驻（复用加速下次）；停止走托盘退出。
- 退出码：3=下载失败，4=server 失败，5=转录失败，6=成品已存在/占用，7=切分或校验失败。
- 日志：`<out-dir>\_podcast2md_server.log` 和 `<slug>\logs\`。
- ffmpeg 不在 PATH 时，脚本在下载前以退出码 2 停止，不会先下载或拉起服务端。
- 端口探测只看本机 TCP 能否连通，不能确认对方是 CapsWriter。配置端口通常是 6016；若被其他程序占用，会误判服务已就绪，最后变成退出码 5。先确认该端口属于 `start_server.exe`，或改用与 `config_server.py` 一致的空闲 `--port`。
- 说话人分离不做；多说话人稿需后处理。

## 两种交付

默认只交 `chapters.md`。用户只说转录、转文字稿时，停在这一步。不要自动写论文稿或摘要。

用户明确要论文式、摘要卡片，或按播客网页目录分章节时，再在同一集目录写 `论文式文字稿.md`。先读 [references/paper-transcript.md](references/paper-transcript.md)，再用 `scripts/build_paper_transcript.py` 拼正文。正文不手改识别词。目录只决定怎么切，转录决定能写进摘要的事实。用户随后明确要求把最终论文或摘要另存时，按该参考的步骤 5 复制，不把默认集中存放理解成拒绝所有安全另存。

参照样稿在 `$env:CAPSWRITER_HOME\work\<slug>\论文式文字稿.md`。学结构，不要把别的节目结论套过来。

## 小宇宙

截至 2026-10-24，本机 yt-dlp 2026.08.19 没有小宇宙专用提取器，但 generic 仍能解析到 `media.xyzcdn.net` 的 m4a。把单集页面 URL 交给脚本，不要改成音频直链；直链下得到音频，丢掉页面时间戳目录。小宇宙目录标记常是「时间戳」而不是「时间轴」。出稿后核对章节数和网页目录；不一致时以网页目录的标题和时间为准重切，不改识别词。

## 本机实测事实

- ffmpeg 8.1.2 已在 PATH（2026-10-19）。不确定时先 `ffmpeg -version` 实测，不要写成推断。
- 本机无独立 NVIDIA GPU。CapsWriter 走 CPU。2026-10-24 两集：服务端冷启动时，约 69 分钟节目约 6 分钟出识别稿；服务端已热时，约 80 分钟节目约 7 分钟出识别稿。这不是 FunASR-Nano 的速度。
- FunASR-Nano 另一条路径：95 分钟录音纯转写约 46 分钟（约 0.5 倍实时，含模型加载，见 work\full.out.log 2026-10-17）。15 秒分段，60 秒整段会重复「嗯」。JSONL 逐段落盘，静音段按能量阈值跳过。
- B 站字幕覆盖不是规律。CLI 会独立执行 `yt-dlp --list-subs`，不要再凭 `-J` 的字幕字段为空断言无字幕。

## B 站字幕与文字来源

只要文字稿时，运行本 CLI，不要把字幕转文章改交给 srt-translator。srt-translator 仍只处理用户单独给出的字幕文件或那个工作流自己的输入，不改它的归属。

CLI 先独立探测，并把状态写入 `subtitle-probe.json`。状态只有这些含义：

- `found`：有可用轨道。保存原件，生成 `chapters.md`，不转写。来源标成 `普通CC` 或 `平台AI`。
- `confirmed_none`：确认没有可用轨道（弹幕不算）。这时才明确选择本机 ASR，并标成 `本机ASR`。
- `login_required`、`request_failed`、`filter_no_match`：停止。不能写成确认无字幕，也不能改跑 ASR。`filter_no_match` 只在传入 `--sub-lang` 且没有该语言轨道时出现；这个参数不是 ASR 开关。

普通 JSON 的字幕字段为空不是结论。需要登录或请求失败也不是结论。不要把 Cookie、密码粘贴进对话，也不要加 `--cookies-from-browser`。浏览器导出只接受用户自己已登录后交出的本地文件，这条路径还没有接到 CLI。

正文和原件一致，只说明转换没有丢改。它不能证明字幕覆盖整段音频，也不能证明识别准确。长度比例不能代替逐段覆盖。已有且覆盖通过的转录，用户只补论文或摘要时不要重新下载或转写；同 URL 或旧的“通过”不够，要核对当前文件和本次请求。

不要安装 Bili23 或其他下载器 GUI，不做 OCR，不接付费解析 API，不重写平台接口。只有画面硬字幕时说明现有字幕轨道无效，继续用已有 ASR，不新增 OCR。

## 本地音频 / 相邻场景分工

- **本地音频文件**（录音、已下载的 mp3/wav，无链接）：不走本 CLI。用 FunASR-Nano：venv `<FunASR目录>\.venv`，权重 `<模型缓存>\Fun-ASR-Nano-2512-hf`；长音频必须分段逐段识别（60s 整段会重复"嗯"），参考 `<FunASR目录>\work\full_transcribe.py`。
- **用户单独给出 srt/vtt 要求翻译或成文**：那是 srt-translator。播客或 B 站链接的文字稿，即使来自字幕，仍留在本 Skill。
