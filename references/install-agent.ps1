# 安装 podcast2md 的 Windows 依赖。-CheckOnly 只检查，不安装、不下载、不改文件或 PATH。
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$checks = [ordered]@{}
$failed = $false
function Set-Check([string]$name, [bool]$ok, [string]$detail) {
  $script:checks[$name] = [ordered]@{ ok = $ok; detail = $detail }
  if (-not $ok) {
    $script:failed = $true
    Write-Host ("FAIL {0}: {1}" -f $name, $detail)
    if (-not $script:CheckOnly) {
      $script:checks | ConvertTo-Json -Depth 4
      exit 1
    }
    return
  }
  Write-Host ("OK   {0}: {1}" -f $name, $detail)
}

function Update-ProcessPath {
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = (@($machine, $user) | Where-Object { $_ }) -join ';'
}

function Test-Command([string]$name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Get-RealPython {
  if (-not (Test-Command 'python')) { return $null }
  $exe = & python -c "import sys; print(sys.executable)"
  if ($LASTEXITCODE -ne 0) { return $null }
  $exe = ($exe | Out-String).Trim()
  if (-not $exe) { return $null }
  if ($exe -like '*\WindowsApps\*') { return "STORE:$exe" }
  return $exe
}

function Install-Winget([string]$id, [string]$commandName) {
  if ($script:CheckOnly) { return }
  if (-not (Test-Command 'winget')) {
    Set-Check 'winget' $false '未找到 winget。先安装 Microsoft App Installer：https://apps.microsoft.com/detail/9NBLGGH4NNS1'
  }
  & winget install --id $id --exact --scope user --accept-package-agreements --accept-source-agreements
  $userExit = $LASTEXITCODE
  Update-ProcessPath
  if ($commandName -and (Test-Command $commandName)) { return }
  if ($userExit -ne 0) {
    & winget install --id $id --exact --accept-package-agreements --accept-source-agreements
    Update-ProcessPath
  }
  if ($commandName -and -not (Test-Command $commandName)) {
    Set-Check $id $false ("已执行 winget install --id {0} --exact，但 {1} 仍不在 PATH。不要改用未知下载地址。" -f $id, $commandName)
  }
}

Update-ProcessPath
Set-Check 'windows' ($env:OS -eq 'Windows_NT') $env:OS

$pythonExe = Get-RealPython
if (-not $pythonExe) {
  if ($CheckOnly) {
    Set-Check 'python' $false '没有可用的 python，或路径含 \WindowsApps\。CheckOnly 不安装。'
  } else {
    Install-Winget 'Python.Python.3.12' 'python'
    $pythonExe = Get-RealPython
  }
}
if ($pythonExe -like 'STORE:*') {
  Set-Check 'python' $false ("Microsoft Store 别名，不能当作已安装：{0}" -f $pythonExe.Substring(6))
} elseif ($pythonExe) {
  Set-Check 'python' $true $pythonExe
}

$vcKey = 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
if (-not (Test-Path -LiteralPath $vcKey)) {
  if ($CheckOnly) {
    Set-Check 'vc_redist' $false '未检测到 VC++ x64 运行库。CheckOnly 不下载安装包。'
  } else {
    $vc = Join-Path $env:TEMP 'vc_redist.x64.exe'
    & curl.exe -L --fail --retry 3 -o $vc 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
    if ($LASTEXITCODE -ne 0) { Set-Check 'vc_redist' $false 'VC++ 官方安装包下载失败：https://aka.ms/vs/17/release/vc_redist.x64.exe' }
    $install = Start-Process -FilePath $vc -ArgumentList '/install','/passive','/norestart' -Wait -PassThru
    if ($install.ExitCode -ne 0 -and $install.ExitCode -ne 1638 -and $install.ExitCode -ne 3010) {
      Set-Check 'vc_redist' $false ("VC++ 安装退出码 {0}。1638=已安装，3010=需要重启。" -f $install.ExitCode)
    }
  }
}
if (-not $checks.Contains('vc_redist')) {
  Set-Check 'vc_redist' (Test-Path -LiteralPath $vcKey) 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
}

if (-not (Test-Command 'ffmpeg') -or -not (Test-Command 'ffprobe')) {
  if ($CheckOnly) {
    Set-Check 'ffmpeg' $false 'ffmpeg 或 ffprobe 不在 PATH。CheckOnly 不安装、不改 PATH。'
  } else {
    Install-Winget 'Gyan.FFmpeg.Essentials' 'ffmpeg'
  }
}
if (-not $checks.Contains('ffmpeg')) {
  $ffmpegOk = (Test-Command 'ffmpeg') -and (Test-Command 'ffprobe')
  $ffmpegDetail = $(if (Test-Command 'ffmpeg') { (& ffmpeg -version | Select-Object -First 1) } else { 'ffmpeg 或 ffprobe 不在 PATH' })
  Set-Check 'ffmpeg' $ffmpegOk $ffmpegDetail
}

if (-not (Test-Command 'yt-dlp')) {
  if ($CheckOnly) {
    Set-Check 'yt-dlp' $false 'yt-dlp 不在 PATH。CheckOnly 不安装。'
  } else {
    Install-Winget 'yt-dlp.yt-dlp' 'yt-dlp'
  }
}
if (-not $checks.Contains('yt-dlp')) {
  Set-Check 'yt-dlp' (Test-Command 'yt-dlp') $(if (Test-Command 'yt-dlp') { (& yt-dlp --version) } else { 'yt-dlp 不在 PATH' })
}

function Find-CapsRoot {
  $candidates = @(
    $env:CAPSWRITER_HOME,
    'D:\iStall\CapsWriter-Offline',
    (Join-Path $env:LOCALAPPDATA 'CapsWriter-Offline')
  ) | Where-Object { $_ }
  foreach ($dir in $candidates) {
    if (Test-Path -LiteralPath (Join-Path $dir 'start_server.exe')) { return (Resolve-Path -LiteralPath $dir).Path }
  }
  return $null
}

$caps = Find-CapsRoot
if (-not $caps) {
  if ($CheckOnly) {
    Set-Check 'capswriter' $false '未找到 start_server.exe。设置 CAPSWRITER_HOME 后再检查。CheckOnly 不下载。'
  } else {
    $capsParent = $(if (Test-Path 'D:\') { 'D:\iStall' } else { $env:LOCALAPPDATA })
    New-Item -ItemType Directory -Force -Path $capsParent | Out-Null
    $zip = Join-Path $env:TEMP 'CapsWriter-Offline-v2.6.zip'
    $url = 'https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/v2.6/CapsWriter-Offline-20260914.zip'
    & curl.exe -L --fail --retry 3 -o $zip $url
    if ($LASTEXITCODE -ne 0) { Set-Check 'capswriter_download' $false "程序包下载失败，不要猜其他地址：$url" }
    $extract = Join-Path $env:TEMP 'CapsWriter-Offline-v2.6'
    if (Test-Path $extract) { Remove-Item -LiteralPath $extract -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $server = Get-ChildItem -LiteralPath $extract -Recurse -Filter 'start_server.exe' | Select-Object -First 1
    if (-not $server) { Set-Check 'capswriter_layout' $false '压缩包内没有 start_server.exe' }
    $caps = Join-Path $capsParent 'CapsWriter-Offline'
    if (Test-Path $caps) { Set-Check 'capswriter_target' $false "目标已存在但没有 start_server.exe，不覆盖：$caps" }
    Move-Item -LiteralPath $server.Directory.FullName -Destination $caps
  }
}
if ($caps) {
  $requiredExe = @('start_server.exe','start_client.exe','config_server.py') | ForEach-Object { Test-Path -LiteralPath (Join-Path $caps $_) }
  Set-Check 'capswriter' (-not ($requiredExe -contains $false)) $caps
  if (-not $CheckOnly) {
    [Environment]::SetEnvironmentVariable('CAPSWRITER_HOME', $caps, 'User')
    $env:CAPSWRITER_HOME = $caps
    Set-Check 'capswriter_home' $true "已写入用户环境变量 CAPSWRITER_HOME。其他终端要重开才能看到：$caps"
  }
}

$requiredModel = @(
  'Fun-ASR-Nano-Encoder-Adaptor.fp16.onnx',
  'Fun-ASR-Nano-CTC.fp16.onnx',
  'Fun-ASR-Nano-Decoder.q5_k.gguf',
  'tokens.txt'
)
if (-not $caps) {
  Set-Check 'fun_asr_nano_model' $false '无 CapsWriter 目录，未检查模型。CheckOnly 不下载。'
} else {
  $modelDir = Join-Path $caps 'models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF'
  $missingModel = @($requiredModel | Where-Object { -not (Test-Path -LiteralPath (Join-Path $modelDir $_)) })
  if ($missingModel.Count -gt 0 -and -not $CheckOnly) {
    $modelZip = Join-Path $env:TEMP 'Fun-ASR-Nano-GGUF.zip'
    $modelUrl = 'https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/models/Fun-ASR-Nano-GGUF.zip'
    & curl.exe -L --fail --retry 3 -o $modelZip $modelUrl
    if ($LASTEXITCODE -ne 0) { Set-Check 'model_download' $false "模型下载失败，不要猜其他地址：$modelUrl" }
    $modelExtract = Join-Path $env:TEMP 'Fun-ASR-Nano-extract'
    if (Test-Path $modelExtract) { Remove-Item -LiteralPath $modelExtract -Recurse -Force }
    Expand-Archive -LiteralPath $modelZip -DestinationPath $modelExtract -Force
    $token = Get-ChildItem -LiteralPath $modelExtract -Recurse -Filter 'tokens.txt' | Select-Object -First 1
    if (-not $token) { Set-Check 'model_layout' $false '模型压缩包内没有 tokens.txt' }
    $sourceDir = $token.Directory.FullName
    New-Item -ItemType Directory -Force -Path (Split-Path $modelDir) | Out-Null
    if (-not (Test-Path -LiteralPath $modelDir)) {
      New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
    }
    foreach ($name in $missingModel) {
      $from = Join-Path $sourceDir $name
      if (-not (Test-Path -LiteralPath $from)) { Set-Check 'model_file' $false "压缩包缺少 $name" }
      Copy-Item -LiteralPath $from -Destination (Join-Path $modelDir $name)
    }
    $stillMissing = @($requiredModel | Where-Object { -not (Test-Path -LiteralPath (Join-Path $modelDir $_)) })
    if ($stillMissing.Count -gt 0) {
      $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
      $backup = "$modelDir.bak-$stamp"
      Rename-Item -LiteralPath $modelDir -NewName (Split-Path $backup -Leaf)
      Move-Item -LiteralPath $sourceDir -Destination $modelDir
      Set-Check 'model_backup' $true "无法只补缺文件，原目录已改名为 $backup，没有删除。"
    }
  }
  $missingModel = @($requiredModel | Where-Object { -not (Test-Path -LiteralPath (Join-Path $modelDir $_)) })
  $modelDetail = $(if ($missingModel.Count) { ($missingModel -join ',') } else { $modelDir })
  if ($CheckOnly -and $missingModel.Count -gt 0) { $modelDetail = "CheckOnly 不下载、不改目录。缺少：$modelDetail" }
  Set-Check 'fun_asr_nano_model' ($missingModel.Count -eq 0) $modelDetail
}

$skill = Join-Path $env:USERPROFILE '.agents\skills\podcast2md'
if (-not (Test-Path -LiteralPath (Join-Path $skill 'SKILL.md'))) {
  if ($CheckOnly) {
    Set-Check 'skill' $false 'Skill 未安装。CheckOnly 不下载、不移动目录。'
  } else {
    New-Item -ItemType Directory -Force -Path (Split-Path $skill) | Out-Null
    $skillZip = Join-Path $env:TEMP 'podcast2md-skill-main.zip'
    & curl.exe -L --fail --retry 3 -o $skillZip 'https://github.com/BingWuJ/podcast2md-skill/archive/refs/heads/main.zip'
    if ($LASTEXITCODE -ne 0) { Set-Check 'skill_download' $false 'https://github.com/BingWuJ/podcast2md-skill/archive/refs/heads/main.zip' }
    $skillExtract = Join-Path $env:TEMP 'podcast2md-skill-main-extract'
    if (Test-Path $skillExtract) { Remove-Item -LiteralPath $skillExtract -Recurse -Force }
    Expand-Archive -LiteralPath $skillZip -DestinationPath $skillExtract -Force
    $skillRoot = Get-ChildItem -LiteralPath $skillExtract -Directory | Select-Object -First 1
    Move-Item -LiteralPath $skillRoot.FullName -Destination $skill
  }
}
if (-not $checks.Contains('skill')) {
  Set-Check 'skill' (Test-Path -LiteralPath (Join-Path $skill 'SKILL.md')) $skill
}

if ($caps) {
  $cliTarget = Join-Path $caps 'podcast2md.py'
  if (-not (Test-Path -LiteralPath $cliTarget)) {
    if ($CheckOnly) {
      Set-Check 'cli_copy' $false 'CapsWriter 目录没有 podcast2md.py。CheckOnly 不复制。'
    } else {
      Copy-Item -LiteralPath (Join-Path $skill 'scripts\podcast2md.py') -Destination $cliTarget
      Set-Check 'cli_copy' (Test-Path -LiteralPath $cliTarget) $cliTarget
    }
  } else {
    Set-Check 'cli_copy' $true $cliTarget
  }
} else {
  Set-Check 'cli_copy' $false '无 CapsWriter 目录，不能检查 podcast2md.py。'
}

foreach ($client in @('.pi\agent\skills\podcast2md', '.claude\skills\podcast2md')) {
  $link = Join-Path $env:USERPROFILE $client
  $checkName = "link_" + ($client.Split('\')[0].TrimStart('.'))
  if (-not (Test-Path -LiteralPath $link)) {
    if ($CheckOnly) {
      Set-Check $checkName $false "入口不存在。CheckOnly 不创建 Junction：$link"
      continue
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $link) | Out-Null
    New-Item -ItemType Junction -Path $link -Target $skill | Out-Null
  }
  $item = Get-Item -LiteralPath $link -Force
  $targetOk = $item.LinkType -eq 'Junction' -and @($item.Target) -contains $skill
  $existsOk = Test-Path -LiteralPath (Join-Path $link 'SKILL.md')
  Set-Check $checkName ($targetOk -or $existsOk) $link
}

$checks['result'] = [ordered]@{ ok = (-not $failed); detail = $(if ($CheckOnly) { 'check-only' } else { 'installed' }) }
$checks | ConvertTo-Json -Depth 4
if ($failed) { exit 1 }
exit 0
