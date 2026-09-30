<#
  Build/flash wrapper for the PS26172 firmware. Pins the toolchain (ESP-IDF v5.5.5 at D:\esp),
  runs the X25 forbidden-dependency gate, and keeps one build directory per console variant.

  Locations can be overridden with environment variables (defaults in brackets):
    PS26172_IDF_PATH        ESP-IDF v5.5.5 checkout            [D:\esp\esp-idf-v5.5.5]
    PS26172_IDF_TOOLS_PATH  ESP-IDF tools directory            [D:\esp\.espressif]
    PS26172_PY312           folder of a CPython 3.12 install   [found with "py -3.12"]

  Usage (from any directory):
    powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console uart build
    powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console uart -Port COM5 flash
    powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console uart size-components
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("uart", "usbjtag")][string]$Console = "uart",
    [string]$Port = "",
    [string]$ExtraDefaults = "",   # absolute path of an additional sdkconfig defaults file (e.g. compile checks)
    [string]$BuildTag = "",        # suffix for a separate build directory
    [switch]$NoNet,                # ignore sdkconfig.wifi (build without networking)
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$IdfArgs
)
if (-not $IdfArgs) { Write-Error "No idf.py action given (e.g. build, flash, size)."; exit 2 }
$Repo = Split-Path -Parent $PSScriptRoot
# ESP-IDF's export script needs CPython 3.12 first on PATH (a newer default Python broke it).
$py312 = $env:PS26172_PY312
if (-not $py312) {
    try { $py312 = Split-Path -Parent (& py -3.12 -c "import sys; print(sys.executable)") } catch { $py312 = "" }
}
if ($py312) { $env:PATH = "$py312;$py312\Scripts;" + $env:PATH }
$env:IDF_TOOLS_PATH = if ($env:PS26172_IDF_TOOLS_PATH) { $env:PS26172_IDF_TOOLS_PATH } else { "D:\esp\.espressif" }
$env:IDF_PATH = if ($env:PS26172_IDF_PATH) { $env:PS26172_IDF_PATH } else { "D:\esp\esp-idf-v5.5.5" }
# Dot-source with redirection, not a pipeline: piping a dot-sourced script drops what it defines.
. "$env:IDF_PATH\export.ps1" *> $null
$IdfPython = (Get-Command python).Source  # the IDF virtualenv python after export

& "$Repo\.venv-host\Scripts\python.exe" "$PSScriptRoot\forbidden_deps.py" $Repo
if ($LASTEXITCODE -ne 0) { exit 1 }
# frontend.json -> firmware header (single source of truth, architecture §7.3)
& "$Repo\.venv-host\Scripts\python.exe" "$PSScriptRoot\gen_frontend_config.py"
if ($LASTEXITCODE -ne 0) { exit 1 }

$fw = "$Repo\firmware"
$bdir = "$fw\build_$Console"
$defaults = "sdkconfig.defaults;sdkconfig.board;sdkconfig.console_$Console"
# Model operating point generated with the model (tools/gen_model_source.py).
if (Test-Path "$fw\sdkconfig.model") { $defaults += ";sdkconfig.model" }
# Local network credentials (gitignored, never committed): enables M5 streaming when present.
if ((Test-Path "$fw\sdkconfig.wifi") -and -not $NoNet) { $defaults += ";sdkconfig.wifi" }
if ($NoNet) { $bdir = "$bdir`_nonet" }
if ($ExtraDefaults) { $defaults += ";$ExtraDefaults" }
if ($BuildTag) { $bdir = "$bdir`_$BuildTag" }
# An existing sdkconfig wins over sdkconfig.defaults*, so a changed wiring/policy file would be
# silently ignored. Regenerate whenever any defaults file is newer than the build's sdkconfig.
$sdk = "$bdir\sdkconfig"
if (Test-Path $sdk) {
    $stamp = (Get-Item $sdk).LastWriteTime
    $newer = @($defaults.Split(";") + "main\Kconfig.projbuild") | Where-Object {
        $p = if ([IO.Path]::IsPathRooted($_)) { $_ } else { "$fw\$_" }
        (Get-Item $p).LastWriteTime -gt $stamp
    }
    if ($newer) {
        Write-Host "Config changed ($($newer -join ', ')): regenerating $sdk"
        Remove-Item $sdk
    }
}
$portArgs = @()
if ($Port) { $portArgs = @("-p", $Port) }
Push-Location $fw
try {
    & $IdfPython "$env:IDF_PATH\tools\idf.py" -B $bdir -D "SDKCONFIG=$bdir\sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" @portArgs @IdfArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
