# Yap installer. One line in PowerShell:
#   irm https://raw.githubusercontent.com/anhnguyendj/yap/main/install.ps1 | iex
#
# Running it again updates the code and keeps your key and settings.
#
# Knobs (environment variables, all optional):
#   YAP_DIR           install folder             (default %LOCALAPPDATA%\Yap)
#   YAP_SOURCE        local folder to install from instead of GitHub - for
#                     testing a change before it is pushed
#   YAP_SHORTCUT_DIR  put the shortcut here instead of Desktop + Start Menu,
#                     so a test install cannot hijack the real shortcut
#
# Everything lives inside a script block: under "irm | iex" a bare `exit` would
# close the user's PowerShell window, so failures `throw` instead.

& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # PS 5.1 download bar is 10x slower
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Repo    = 'anhnguyendj/yap'
$ZipUrl  = "https://github.com/$Repo/archive/refs/heads/main.zip"
$KeysUrl = 'https://console.groq.com/keys'
$Dir     = if ($env:YAP_DIR) { $env:YAP_DIR } else { Join-Path $env:LOCALAPPDATA 'Yap' }

function Say($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# Returns the command (as an array) of a working Python >= 3.10, or $null.
# `py -3` first: a bare `python` may be the Microsoft Store stub, or some
# unrelated venv that happens to be first on PATH.
function Find-Python {
    $candidates = @(@('py', '-3'), @('python'))
    $launcher = Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe'
    if (Test-Path $launcher) { $candidates += , @($launcher, '-3') }
    foreach ($c in $candidates) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        $args_ = @($c | Select-Object -Skip 1) + @('-c', 'import sys; print(sys.version_info >= (3, 10))')
        try { $ok = & $c[0] @args_ 2>$null } catch { continue }
        if ($LASTEXITCODE -eq 0 -and "$ok".Trim() -eq 'True') { return , $c }
    }
    return $null
}

# --- 1. Python -----------------------------------------------------------
$py = Find-Python
if (-not $py) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host 'Python 3.10+ is required. Install it from https://www.python.org/downloads/'
        Write-Host '(tick "Add python.exe to PATH"), then run this command again.'
        throw 'Python not found'
    }
    $ans = Read-Host 'Python 3.10+ not found. Install Python 3.13 with winget now? [Y/n]'
    if ($ans -and $ans -notmatch '^[Yy]') { throw 'Python is required - cancelled' }
    winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
    # winget does not refresh PATH in this window; pick up the new entries.
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $py = Find-Python
    if (-not $py) { throw 'Python installed but not found - open a new PowerShell window and run the command again' }
}
Say ("Python: " + (& $py[0] @($py | Select-Object -Skip 1) --version))

# --- 2. Stop a running copy, or the update cannot replace its files -------
$running = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Dir*app.py*" })
foreach ($p in $running) {
    Say "Stopping running Yap (pid $($p.ProcessId))"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

# --- 3. Get the code -------------------------------------------------------
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("yap-install-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    if ($env:YAP_SOURCE) {
        Say "Copying from $env:YAP_SOURCE"
        $src = (Resolve-Path $env:YAP_SOURCE).Path
    } else {
        Say "Downloading $ZipUrl"
        $zip = Join-Path $tmp 'yap.zip'
        Invoke-WebRequest -Uri $ZipUrl -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tmp
        $src = (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName
    }
    if (-not (Test-Path (Join-Path $src 'app.py'))) { throw "No app.py in $src" }

    # Never carry a key file, a venv or git history across. The GitHub ZIP has
    # none of these; a local YAP_SOURCE (a dev checkout) usually has all three,
    # and copying its .env would overwrite the key in the install folder.
    Say "Installing to $Dir"
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    $skipDirs = '.git', '.venv', 'venv', '__pycache__'
    Get-ChildItem $src -Recurse -File -Force | ForEach-Object {
        $rel = $_.FullName.Substring($src.Length).TrimStart('\')
        $parts = $rel -split '\\'
        if ($parts | Where-Object { $skipDirs -contains $_ }) { return }
        if ($_.Name -like '.env*' -and $_.Name -ne '.env.example') { return }
        if ($_.Name -like '*.bak' -or $_.Name -like '*.bak-*') { return }
        $dest = Join-Path $Dir $rel
        New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
        Copy-Item $_.FullName $dest -Force
    }
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# --- 4. Private venv + packages ------------------------------------------
$venvPy  = Join-Path $Dir '.venv\Scripts\python.exe'
$venvPyw = Join-Path $Dir '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $venvPy)) {
    Say 'Creating virtual environment'
    & $py[0] @($py | Select-Object -Skip 1) -m venv (Join-Path $Dir '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment' }
}
Say 'Installing packages (first time takes a minute)'
& $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Dir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install failed - see the messages above' }

# --- 5. Shortcuts ------------------------------------------------------------
# Points at the venv's pythonw, not tao-shortcut.py's system pyw.exe: the
# system Python does not have Yap's packages.
$linkDirs = if ($env:YAP_SHORTCUT_DIR) { @($env:YAP_SHORTCUT_DIR) } else {
    @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
}
$shell = New-Object -ComObject WScript.Shell
foreach ($d in $linkDirs) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
    $lnk = $shell.CreateShortcut((Join-Path $d 'Yap.lnk'))
    $lnk.TargetPath       = $venvPyw
    $lnk.Arguments        = '"' + (Join-Path $Dir 'app.py') + '"'
    $lnk.WorkingDirectory = $Dir
    $lnk.IconLocation     = (Join-Path $Dir 'yap_icon.ico') + ',0'
    $lnk.Description      = 'Yap - hold Right Ctrl and speak'
    $lnk.Save()
    Say "Shortcut: $(Join-Path $d 'Yap.lnk')"
}

# --- 6. Key file: create once, names only, never touch an existing one -----
# Only for the dev / override path: normal users paste the key in Settings,
# so nothing here tells them about this file.
# FileMode.CreateNew fails if the file exists, so even a bug above cannot
# turn this into an overwrite of someone's real key.
# -Encoding UTF8: PS 5.1 otherwise reads the file as ANSI and a dash in a
# comment comes out as mojibake in the new file.
$envFile = Join-Path $Dir '.env'
if (-not (Test-Path $envFile)) {
    $lines = Get-Content (Join-Path $Dir '.env.example') -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') { "$($Matches[1])=" } else { $_ }
    }
    $fs = [IO.File]::Open($envFile, [IO.FileMode]::CreateNew)
    try {
        $w = New-Object IO.StreamWriter($fs, (New-Object Text.UTF8Encoding($false)))
        $lines | ForEach-Object { $w.WriteLine($_) }
        $w.Flush()
    } finally { $fs.Dispose() }
}

# --- 7. Start --------------------------------------------------------------
# Same test as the app's own "no key -> open Settings" check (.env, then
# config.json), so this only says "paste your key" when Settings really opens.
function Test-HasKey {
    $hasEnvKey = Get-Content $envFile -Encoding UTF8 -ErrorAction SilentlyContinue |
        Where-Object { $_ -match '^\s*[A-Z_]+_API_KEY\s*=\s*\S' }
    if ($hasEnvKey) { return $true }
    $cfgFile = Join-Path $env:APPDATA 'YapWindows\config.json'
    try { return [bool]"$((Get-Content $cfgFile -Raw -Encoding UTF8 | ConvertFrom-Json).api_key)".Trim() }
    catch { return $false }
}
$needKey = -not (Test-HasKey)
Start-Process -FilePath $venvPyw -ArgumentList ('"' + (Join-Path $Dir 'app.py') + '"') -WorkingDirectory $Dir
if ($needKey) {
    Start-Process $KeysUrl
    Write-Host ''
    Write-Host 'Last step: Yap just opened its Settings window.' -ForegroundColor Yellow
    Write-Host "  1. Create a free key on the page that just opened ($KeysUrl)"
    Write-Host '  2. Paste it into the API KEY box in Settings'
    Write-Host '  3. Press Save & Apply'
    Write-Host 'Settings later: right-click the Yap icon in the tray -> Settings.'
}
Write-Host ''
Write-Host 'Yap is running. Hold Right Ctrl, speak, let go.' -ForegroundColor Green
}
