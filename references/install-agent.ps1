# 安装 podcast2md 及其已核对的 Windows 依赖。
# 已存在且检查通过的组件不重复下载。任一步失败即停止，退出码为 1。
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$checks = [ordered]@{}
function Set-Check([string]$name, [bool]$ok, [string]$detail) {
  $script:checks[$name] = [ordered]@{ ok = $ok; detail = $detail }
  if (-not $ok) {
    Write-Host ("FAIL {0}: {1}" -f $name, $detail)
    $script:checks | ConvertTo-Json -Depth 4
    exit 1
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

function Install-Winget([string]$id, [string]$commandName) {
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

if (-not (Test-Command 'python')) { Install-Winget 'Python.Python.3.12' 'python' }
Set-Check 'python' (Test-Command 'python') $(if (Test-Command 'python') { (& python --version) } else { 'python 不在 PATH' })

$vcKey = 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
if (-not (Test-Path -LiteralPath $vcKey)) {
  $vc = Join-Path $env:TEMP 'vc_redist.x64.exe'
  & curl.exe -L --fail --retry 3 -o $vc 'https://aka.ms/vs/17/release/vc_redist.x64.exe'
  if ($LASTEXITCODE -ne 0) { Set-Check 'vc_redist' $false 'VC++ 官方安装包下载失败：https://aka.ms/vs/17/release/vc_redist.x64.exe' }
  $install = Start-Process -FilePath $vc -ArgumentList '/install','/passive','/norestart' -Wait -PassThru
  if ($install.ExitCode -ne 0 -and $install.ExitCode -ne 1638 -and $install.ExitCode -ne 3010) {
    Set-Check 'vc_redist' $false ("VC++ 安装退出码 {0}。1638=已安装，3010=需要重启。" -f $install.ExitCode)
  }
}
Set-Check 'vc_redist' (Test-Path -LiteralPath $vcKey) 'https://aka.ms/vs/17/release/vc_redist.x64.exe'

if (-not (Test-Command 'ffmpeg') -or -not (Test-Command 'ffprobe')) {
  Install-Winget 'Gyan.FFmpeg.Essentials' 'ffmpeg'
}
Set-Check 'ffmpeg' ((Test-Command 'ffmpeg') -and (Test-Command 'ffprobe')) $(if (Test-Command 'ffmpeg') { (& ffmpeg -version | Select-Object -First 1) } else { 'ffmpeg 或 ffprobe 不在 PATH。winget 包 Gyan.FFmpeg.Essentials 会注册 PATH；当前进程已刷新，新终端也必须重开。' })

if (-not (Test-Command 'yt-dlp')) { Install-Winget 'yt-dlp.yt-dlp' 'yt-dlp' }
Set-Check 'yt-dlp' (Test-Command 'yt-dlp') $(if (Test-Command 'yt-dlp') { (& yt-dlp --version) } else { 'yt-dlp 不在 PATH。官方命令：winget install --id yt-dlp.yt-dlp --exact' })

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
$requiredExe = @('start_server.exe','start_client.exe','config_server.py') | ForEach-Object { Test-Path -LiteralPath (Join-Path $caps $_) }
Set-Check 'capswriter' (-not ($requiredExe -contains $false)) $caps

$modelDir = Join-Path $caps 'models\Fun-ASR-Nano\Fun-ASR-Nano-GGUF'
$requiredModel = @(
  'Fun-ASR-Nano-Encoder-Adaptor.fp16.onnx',
  'Fun-ASR-Nano-CTC.fp16.onnx',
  'Fun-ASR-Nano-Decoder.q5_k.gguf',
  'tokens.txt'
)
$missingModel = @($requiredModel | Where-Object { -not (Test-Path -LiteralPath (Join-Path $modelDir $_)) })
if ($missingModel.Count -gt 0) {
  $modelZip = Join-Path $env:TEMP 'Fun-ASR-Nano-GGUF.zip'
  $modelUrl = 'https://github.com/HaujetZhao/CapsWriter-Offline/releases/download/models/Fun-ASR-Nano-GGUF.zip'
  & curl.exe -L --fail --retry 3 -o $modelZip $modelUrl
  if ($LASTEXITCODE -ne 0) { Set-Check 'model_download' $false "模型下载失败，不要猜其他地址：$modelUrl" }
  $modelExtract = Join-Path $env:TEMP 'Fun-ASR-Nano-extract'
  if (Test-Path $modelExtract) { Remove-Item -LiteralPath $modelExtract -Recurse -Force }
  Expand-Archive -LiteralPath $modelZip -DestinationPath $modelExtract -Force
  $token = Get-ChildItem -LiteralPath $modelExtract -Recurse -Filter 'tokens.txt' | Select-Object -First 1
  if (-not $token) { Set-Check 'model_layout' $false '模型压缩包内没有 tokens.txt' }
  New-Item -ItemType Directory -Force -Path (Split-Path $modelDir) | Out-Null
  if (Test-Path $modelDir) { Remove-Item -LiteralPath $modelDir -Recurse -Force }
  Move-Item -LiteralPath $token.Directory.FullName -Destination $modelDir
}
$missingModel = @($requiredModel | Where-Object { -not (Test-Path -LiteralPath (Join-Path $modelDir $_)) })
Set-Check 'fun_asr_nano_model' ($missingModel.Count -eq 0) $(if ($missingModel.Count) { ($missingModel -join ',') } else { $modelDir })

$skill = Join-Path $env:USERPROFILE '.agents\skills\podcast2md'
if (-not (Test-Path -LiteralPath (Join-Path $skill 'SKILL.md'))) {
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
Set-Check 'skill' (Test-Path -LiteralPath (Join-Path $skill 'SKILL.md')) $skill

$cliSource = Join-Path $skill 'scripts\podcast2md.py'
$cliTarget = Join-Path $caps 'podcast2md.py'
if (-not (Test-Path -LiteralPath $cliTarget)) {
  Copy-Item -LiteralPath $cliSource -Destination $cliTarget
}
Set-Check 'cli_copy' (Test-Path -LiteralPath $cliTarget) $cliTarget

foreach ($client in @('.pi\agent\skills\podcast2md', '.claude\skills\podcast2md')) {
  $link = Join-Path $env:USERPROFILE $client
  if (-not (Test-Path -LiteralPath $link)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $link) | Out-Null
    New-Item -ItemType Junction -Path $link -Target $skill | Out-Null
  }
  $item = Get-Item -LiteralPath $link -Force
  $targetOk = $item.LinkType -eq 'Junction' -and @($item.Target) -contains $skill
  $existsOk = Test-Path -LiteralPath (Join-Path $link 'SKILL.md')
  Set-Check ("link_" + ($client.Split('\')[0].TrimStart('.'))) ($targetOk -or $existsOk) $link
}

$checks['result'] = 'installed'
$checks | ConvertTo-Json -Depth 4
exit 0
