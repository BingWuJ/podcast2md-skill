# 安装 podcast2md

这里分成两份说明。人看上面的步骤和成功标志；Agent 不根据散文猜测，只执行下面给出的命令。

已核对的来源：

- Python：<https://www.python.org/downloads/windows/>；winget 包清单：<https://github.com/microsoft/winget-pkgs/tree/master/manifests/p/Python/Python/3/3.12>
- FFmpeg：<https://www.gyan.dev/ffmpeg/builds/>，包 ID 为 `Gyan.FFmpeg.Essentials`
- yt-dlp：<https://github.com/yt-dlp/yt-dlp/wiki/Installation>，命令是 `winget install --source winget --id yt-dlp.yt-dlp`
- VC++ 与 FFmpeg：<https://github.com/HaujetZhao/CapsWriter-Offline/blob/master/docs/环境依赖安装说明.md>
- CapsWriter 程序：<https://github.com/HaujetZhao/CapsWriter-Offline/releases/tag/v2.6>
- Fun-ASR-Nano 模型及四个必要文件：<https://github.com/HaujetZhao/CapsWriter-Offline/blob/master/docs/模型下载的若干问题.md>

## 给人看

按顺序做。每一步都先看“成功标志”，没看到就不要进入下一步。不要在变量还是空的时候使用 `$env:CAPSWRITER_HOME`，否则命令会变成 `python "\podcast2md.py"`。

1. 安装 Python 3.12。成功标志：`python -c "import sys; print(sys.executable)"` 打印真实解释器，路径不含 `\WindowsApps\`。
2. 安装 Microsoft Visual C++ 2015–2022 x64 运行库。成功标志：安装程序结束，没有缺少 DLL 的提示。下载地址：<https://aka.ms/vs/17/release/vc_redist.x64.exe>
3. 安装 FFmpeg Essentials，并确认它进入 PATH。成功标志：新开的 PowerShell 里 `ffmpeg -version` 和 `ffprobe -version` 都能运行。只把压缩包解压、没有把 `bin` 加入 PATH，不算安装完成。
4. 安装 yt-dlp。成功标志：`yt-dlp --version` 能显示版本。
5. 先设置 CapsWriter 目录，再下载程序和模型。有 D 盘时用 `D:\iStall\CapsWriter-Offline`，没有就用 `%LOCALAPPDATA%\CapsWriter-Offline`。新开的终端才能看到持久化后的用户变量。

   ```powershell
   $env:CAPSWRITER_HOME = $(if (Test-Path 'D:\') { 'D:\iStall\CapsWriter-Offline' } else { Join-Path $env:LOCALAPPDATA 'CapsWriter-Offline' })
   [Environment]::SetEnvironmentVariable('CAPSWRITER_HOME', $env:CAPSWRITER_HOME, 'User')
   if (Test-Path -LiteralPath (Join-Path $env:CAPSWRITER_HOME 'start_server.exe')) { throw '已有 CapsWriter，不覆盖' }
   New-Item -ItemType Directory -Force -Path $env:CAPSWRITER_HOME | Out-Null
   $zip = Join-Path $env:TEMP 'CapsWriter-Offline-v2.6.zip'
   curl.exe -L --fail --retry 3 -o $zip https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/v2.6/CapsWriter-Offline-20260914.zip
   if ($LASTEXITCODE -ne 0) { throw 'CapsWriter 程序包下载失败，停止' }
   $extract = Join-Path $env:TEMP 'CapsWriter-Offline-v2.6'
   if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
   Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
   $server = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'start_server.exe' | Select-Object -First 1
   if (-not $server) { throw '压缩包内没有 start_server.exe，停止' }
   Get-ChildItem -LiteralPath $server.Directory.FullName -Force | Move-Item -Destination $env:CAPSWRITER_HOME
   $modelZip = Join-Path $env:TEMP 'Fun-ASR-Nano-GGUF.zip'
   curl.exe -L --fail --retry 3 -o $modelZip https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/models/Fun-ASR-Nano-GGUF.zip
   if ($LASTEXITCODE -ne 0) { throw 'Fun-ASR-Nano 模型下载失败，停止' }
   $modelExtract = Join-Path $env:TEMP 'Fun-ASR-Nano-extract'
   if (Test-Path $modelExtract) { Remove-Item -LiteralPath $modelExtract -Recurse -Force }
   Expand-Archive -LiteralPath $modelZip -DestinationPath $modelExtract -Force
   $token = Get-ChildItem -LiteralPath $modelExtract -Recurse -Filter 'tokens.txt' | Select-Object -First 1
   if (-not $token) { throw '模型压缩包内没有 tokens.txt，停止' }
   $modelDir = Join-Path $env:CAPSWRITER_HOME 'models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF'
   New-Item -ItemType Directory -Force -Path (Split-Path $modelDir) | Out-Null
   if (Test-Path -LiteralPath $modelDir) { throw '模型目录已存在，不覆盖' }
   Move-Item -LiteralPath $token.Directory.FullName -Destination $modelDir
   ```

   成功标志：`$env:CAPSWRITER_HOME` 有 `start_server.exe`、`start_client.exe`，并且有这四个文件：
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\Fun-ASR-Nano-Encoder-Adaptor.fp16.onnx`
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\Fun-ASR-Nano-CTC.fp16.onnx`
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\Fun-ASR-Nano-Decoder.q5_k.gguf`
   - `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF\tokens.txt`
6. 安装 Skill。成功标志：`%USERPROFILE%\.agents\skills\podcast2md\SKILL.md`、`references\` 和 `scripts\` 都存在。

   有 Git：

   ```powershell
   git clone https://github.com/BingWuJ/podcast2md-skill.git "$env:USERPROFILE\.agents\skills\podcast2md"
   ```

   没有 Git：

   ```powershell
   $dest = Join-Path $env:USERPROFILE '.agents\skills\podcast2md'
   $zip = Join-Path $env:TEMP 'podcast2md-skill-main.zip'
   curl.exe -L --fail --retry 3 -o $zip https://github.com/BingWuJ/podcast2md-skill/archive/refs/heads/main.zip
   if ($LASTEXITCODE -ne 0) { throw 'Skill 压缩包下载失败，停止' }
   $extract = Join-Path $env:TEMP 'podcast2md-skill-main-extract'
   if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
   Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
   $root = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
   New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
   Move-Item -LiteralPath $root.FullName -Destination $dest
   ```

7. 把 `scripts\podcast2md.py` 复制到第 5 步设置的目录。变量为空就停止，不要继续。

   ```powershell
   if (-not $env:CAPSWRITER_HOME) {
     $env:CAPSWRITER_HOME = [Environment]::GetEnvironmentVariable('CAPSWRITER_HOME', 'User')
   }
   if (-not $env:CAPSWRITER_HOME) { throw 'CAPSWRITER_HOME 未设置。先完成第 5 步' }
   Copy-Item -LiteralPath "$env:USERPROFILE\.agents\skills\podcast2md\scripts\podcast2md.py" -Destination "$env:CAPSWRITER_HOME\podcast2md.py"
   python "$env:CAPSWRITER_HOME\podcast2md.py" --help
   ```

模型压缩包约 800 MB。四个模型文件都在时不要重新下载。

## 脚本会改哪些目录

只有不带 `-CheckOnly` 的安装模式才会改动：

- 用 winget 安装缺失的 Python、FFmpeg 或 yt-dlp，安装程序可能修改用户或系统 PATH。
- 缺少 VC++ 运行库时，下载并运行官方 `vc_redist.x64.exe`。
- 找不到 CapsWriter 时，下载程序包并放到 `D:\iStall\CapsWriter-Offline`；没有 D 盘则放到 `%LOCALAPPDATA%\CapsWriter-Offline`。找到或装完后，把该目录写入用户环境变量 `CAPSWRITER_HOME`。其他终端要重开。
- 模型缺文件时，只把缺少的文件复制进 `models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF`。不删除该目录。只有缺文件无法补进现有目录时，才把原目录改名为 `Fun-ASR-Nano-GGUF.bak-<时间戳>`，再放入新目录。
- Skill 目录没有 `SKILL.md` 时，下载仓库到 `%USERPROFILE%\.agents\skills\podcast2md`。已有 Skill 不覆盖。
- CapsWriter 目录没有 `podcast2md.py` 时复制一份。已有文件不覆盖。
- `%USERPROFILE%\.pi\agent\skills\podcast2md` 或 `%USERPROFILE%\.claude\skills\podcast2md` 不存在时，创建指向 Skill 目录的 Junction。已存在的入口不重建。

`-CheckOnly` 只读取并输出 JSON。它会把当前进程的 PATH 刷新为已经保存的用户和系统 PATH，但不写入 PATH，也不写 `CAPSWRITER_HOME`。不执行 winget、下载、解压、移动、删除、改名、复制或创建 Junction。

## 给 Agent

不要从软件名称猜测下载地址，不要把“安装 FFmpeg”理解成只下载压缩包。下面先试 GitHub raw，失败再试 jsDelivr。两条都失败就停止，不要换别的地址。

```powershell
$script = Join-Path $env:TEMP 'install-podcast2md.ps1'
curl.exe -L --fail --retry 3 -o $script https://raw.githubusercontent.com/BingWuJ/podcast2md-skill/main/references/install-agent.ps1
if ($LASTEXITCODE -ne 0) {
  curl.exe -L --fail --retry 3 -o $script https://cdn.jsdelivr.net/gh/BingWuJ/podcast2md-skill@main/references/install-agent.ps1
}
if ($LASTEXITCODE -ne 0) { throw 'raw.githubusercontent.com 与 jsDelivr 都失败，停止' }
powershell -NoProfile -ExecutionPolicy Bypass -File $script -CheckOnly
if ($LASTEXITCODE -ne 0) { throw '只读检查未通过，停止，不要安装' }
```

用户明确允许安装时，把最后的 `-CheckOnly` 去掉。JSON 里有任意 `ok=false`，或退出码不是 0，都不能报告成功。

脚本固定使用这些地址和包 ID：

- `winget install --id Python.Python.3.12 --exact`
- `winget install --id Gyan.FFmpeg.Essentials --exact`
- `winget install --id yt-dlp.yt-dlp --exact`
- <https://aka.ms/vs/17/release/vc_redist.x64.exe>
- <https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/v2.6/CapsWriter-Offline-20260914.zip>
- <https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/models/Fun-ASR-Nano-GGUF.zip>
- <https://github.com/BingWuJ/podcast2md-skill/archive/refs/heads/main.zip>

通过条件：

```powershell
python -c "import sys; print(sys.executable)"
ffmpeg -version
ffprobe -version
yt-dlp --version
# 把尖括号内容替换成 capswriter.detail 的实际路径，不要原样执行。
$caps = '<脚本 JSON 的 capswriter.detail>'
if ($caps -like '<*') { throw '尖括号内容还没替换成实际路径，停止' }
if (-not $caps) { throw '没有 CapsWriter 目录，停止' }
python "$caps\podcast2md.py" --help
```

尖括号内容必须替换成实际路径，不是原样执行。安装模式会把 `capswriter.detail` 写入用户变量 `CAPSWRITER_HOME`，但当前终端之外的程序要重开才能读到。变量仍为空时，用 JSON 里的路径，不要执行 `python "\podcast2md.py"`。
