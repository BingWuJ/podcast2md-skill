# 安装 podcast2md

这里分成两份说明。人看上面的步骤和成功标志；Agent 不根据散文猜测，只执行下面给出的命令。

已核对的来源：

- Python：本机 `winget search --id Python.Python.3.12`，包 ID 为 `Python.Python.3.12`
- FFmpeg：本机 `winget search` 确认 `Gyan.FFmpeg.Essentials`；官方构建页也给出 winget 安装方式，<https://www.gyan.dev/ffmpeg/builds/>
- yt-dlp：官方安装文档的命令是 `winget install --source winget --id yt-dlp.yt-dlp`，<https://github.com/yt-dlp/yt-dlp/wiki/Installation>
- VC++ 与 FFmpeg：CapsWriter 官方依赖说明，<https://github.com/HaujetZhao/CapsWriter-Offline/blob/master/docs/环境依赖安装说明.md>
- CapsWriter 程序：`v2.6` 的 `CapsWriter-Offline-20260914.zip`，<https://github.com/HaujetZhao/CapsWriter-Offline/releases/tag/v2.6>
- Fun-ASR-Nano 模型及四个必要文件：官方模型说明，<https://github.com/HaujetZhao/CapsWriter-Offline/blob/master/docs/模型下载的若干问题.md>

## 给人看

按顺序做。每一步都先看“成功标志”，没看到就不要进入下一步。

1. 安装 Python 3.12。成功标志：新开的 PowerShell 里 `python --version` 能显示版本。
2. 安装 Microsoft Visual C++ 2015–2022 x64 运行库。成功标志：安装程序结束，没有缺少 DLL 的提示。下载地址：<https://aka.ms/vs/17/release/vc_redist.x64.exe>
3. 安装 FFmpeg Essentials，并确认它进入 PATH。成功标志：新开的 PowerShell 里 `ffmpeg -version` 和 `ffprobe -version` 都能运行。只把压缩包解压、没有把 `bin` 加入 PATH，不算安装完成。
4. 安装 yt-dlp。成功标志：`yt-dlp --version` 能显示版本。
5. 安装 CapsWriter-Offline 程序，再放入 Fun-ASR-Nano 模型。成功标志：安装目录有 `start_server.exe`、`start_client.exe`，并且有这四个文件：
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\Fun-ASR-Nano-Encoder-Adaptor.fp16.onnx`
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\Fun-ASR-Nano-CTC.fp16.onnx`
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\Fun-ASR-Nano-Decoder.q5_k.gguf`
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\tokens.txt`
6. 安装 Skill。成功标志：`%USERPROFILE%\.agents\skills\podcast2md\SKILL.md` 存在。Pi 或 Claude 要共用时，对应目录应指向这一个目录，不复制第二份。
7. 把 `scripts\podcast2md.py` 复制到 `start_server.exe` 同一目录。成功标志：该目录能运行 `python .\podcast2md.py --help`。

模型压缩包约 800 MB。已有上述四个文件时不要重新下载。

## 给 Agent

不要从软件名称猜测下载地址，不要把“安装 FFmpeg”理解成只下载压缩包。把下面这一整段交给 Agent；它会检查现有安装，只补缺失项，并以最后的 JSON 判断结果。JSON 里有任意 `ok=false` 或进程退出码不是 0，就停止，不能报告安装成功。

```powershell
$script = Join-Path $env:TEMP 'install-podcast2md.ps1'
curl.exe -L --fail --retry 3 -o $script https://raw.githubusercontent.com/BingWuJ/podcast2md-skill/main/references/install-agent.ps1
if ($LASTEXITCODE -ne 0) { throw '安装脚本下载失败，停止' }
powershell -NoProfile -ExecutionPolicy Bypass -File $script
if ($LASTEXITCODE -ne 0) { throw '安装脚本未通过，停止' }
```

脚本固定使用这些地址和包 ID：

- `winget install --id Python.Python.3.12 --exact`
- `winget install --id Gyan.FFmpeg.Essentials --exact`
- `winget install --id yt-dlp.yt-dlp --exact`
- <https://aka.ms/vs/17/release/vc_redist.x64.exe>
- <https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/v2.6/CapsWriter-Offline-20260914.zip>
- <https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/models/Fun-ASR-Nano-GGUF.zip>
- <https://github.com/BingWuJ/podcast2md-skill/archive/refs/heads/main.zip>

安装后的通过条件是新的 PowerShell 进程中以下命令都成功：

```powershell
python --version
ffmpeg -version
ffprobe -version
yt-dlp --version
python 'D:\iStall\CapsWriter-Offline\podcast2md.py' --help
```

最后一条里的目录以脚本 JSON 中 `capswriter.detail` 的实际路径为准。本机已安装在 `D:\iStall\CapsWriter-Offline` 时，脚本不会重新下载程序或模型。
