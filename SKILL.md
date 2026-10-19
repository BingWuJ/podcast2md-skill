---
name: podcast2md
description: 把播客单集链接转成按章节整理的完整文字稿（本机 CapsWriter-Offline 语音识别，产出 chapters.md，非摘要）。用户给出播客/音频链接要求转录、转文字稿、整理成文，或问"那个播客转文字的 CLI 叫什么"时使用。本地音频文件（无链接）转写走 FunASR-Nano，见文内参考。
---

# podcast2md — 播客单集链接 → 章节文字稿

## 定位

- 输入：yt-dlp 支持的播客单集页面或音频直链
- 输出：`<out-dir>\<slug>\chapters.md`——完整转录稿按节目已有章节切分；非摘要、不发明内容
- 引擎：本机 CapsWriter-Offline（fun_asr_nano），脚本自动拉起 server/client

## 运行（用部署副本，必须与 start_server.exe 同目录）

```powershell
python "D:\iStall\CapsWriter-Offline\podcast2md.py" "单集URL"
python "D:\iStall\CapsWriter-Offline\podcast2md.py" "单集URL" --transcribe-timeout 10800
```

- **源仓库**：`D:\iStall\podcast2md\`（podcast2md.py + README.md + PODCAST2MD.md）。改脚本只改仓库版，改完复制到 `D:\iStall\CapsWriter-Offline\` 部署。
- 完整参数表、流水线细节、退出码：按需读 `D:\iStall\podcast2md\PODCAST2MD.md`，不要默认整读。

## 关键参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--out-dir` | `<脚本目录>\work` | 成品在 `work\<slug>\chapters.md` |
| `--force` | 关 | 删除已有单集目录重跑；会丢手动修改 |
| `--polish` | `off` | `basic` 只是规则去语气词，非模型润色；要忠实原稿用 `off` |
| `--server-timeout` | 600s | server 拉起等待 |
| `--transcribe-timeout` | 7200s | 转录等待；长节目调大（如 10800） |

## 坑（先读再跑）

- 长音频（>1h）转录几十分钟起步：**后台进程跑 + 轮询日志**，别前台干等撞工具超时。
- server 转录完保持常驻（复用加速下次）；停止走托盘退出。
- 退出码：3=下载失败，4=server 失败，5=转录失败，6=成品已存在/占用，7=切分或校验失败。
- 日志：`<out-dir>\_podcast2md_server.log` 和 `<slug>\logs\`。
- ffmpeg 必须在 PATH，否则 client 转录必失败。
- 说话人分离不做；多说话人稿需后处理。

## 本机实测事实（2026-10-19 验证，直接引用不必重新探测）

- ffmpeg 8.1.2 已在 PATH——client 文件转录的前提已满足；不确定时先 `ffmpeg -version` 实测再说，不要写成推断
- 本机无独立 NVIDIA GPU，转录走 CPU：30–60 分钟的节目约 10–30 分钟出稿，1 小时以上 40–90 分钟；FunASR-Nano 实测 95 分钟录音纯转写约 46 分钟（约 0.5 倍实时速度，含模型加载，见 work\full.out.log 2026-10-17）
- FunASR-Nano 参考脚本实测特性：15 秒分段（60s 整段会重复"嗯"）、JSONL 逐段落盘断点续跑、静音段按能量阈值跳过
- B 站字幕覆盖：官方/UP 主 CC 字幕并非全覆盖，AI 字幕更常见——先 `yt-dlp --list-subs` 探测再定路线，不要凭假设断言覆盖率

## 本地音频 / 相邻场景分工

- **本地音频文件**（录音、已下载的 mp3/wav，无链接）：不走本 CLI。用 FunASR-Nano：venv `D:\iStall\FunASR-Nano\.venv`，权重 `D:\iStall\model-cache\huggingface\local\Fun-ASR-Nano-2512-hf`；长音频必须分段逐段识别（60s 整段会重复"嗯"），参考 `D:\iStall\FunASR-Nano\work\full_transcribe.py`。
- **B站等有字幕的视频**：先探测字幕（`yt-dlp --list-subs`），有 CC/AI 字幕就直接拉字幕成文，不必跑语音转写。
- 字幕转文章（去时间轴、成文）：那是 srt-translator 工作流，不是本 CLI。
