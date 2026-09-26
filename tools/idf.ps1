<#
  Build/flash wrapper for the PS26172 firmware. Pins the toolchain (ESP-IDF v5.5.5 at D:\esp),
  runs the X25 forbidden-dependency gate, and keeps one build directory per console variant.

  Usage (from any directory):
    powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console uart build
    powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console uart -Port COM5 flash
    powershell -ExecutionPolicy Bypass -File D:\ps26172\tools\idf.ps1 -Console uart size-components
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("uart", "usbjtag")][string]$Console = "uart",
    [string]$Port = "",
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$IdfArgs
)
if (-not $IdfArgs) { Write-Error "No idf.py action given (e.g. build, flash, size)."; exit 2 }
$Repo = Split-Path -Parent $PSScriptRoot
$py312 = "C:\Users\user\AppData\Local\Programs\Python\Python312"
$env:PATH = "$py312;$py312\Scripts;" + $env:PATH
$env:IDF_TOOLS_PATH = "D:\esp\.espressif"
$env:IDF_PATH = "D:\esp\esp-idf-v5.5.5"
# Dot-source with redirection, not a pipeline: piping a dot-sourced script drops what it defines.
. "$env:IDF_PATH\export.ps1" *> $null
$IdfPython = (Get-Command python).Source  # the IDF virtualenv python after export

& "$Repo\.venv-host\Scripts\python.exe" "$PSScriptRoot\forbidden_deps.py" $Repo
if ($LASTEXITCODE -ne 0) { exit 1 }

$fw = "$Repo\firmware"
$bdir = "$fw\build_$Console"
$defaults = "sdkconfig.defaults;sdkconfig.board;sdkconfig.console_$Console"
$portArgs = @()
if ($Port) { $portArgs = @("-p", $Port) }
Push-Location $fw
try {
    & $IdfPython "$env:IDF_PATH\tools\idf.py" -B $bdir -D "SDKCONFIG=$bdir\sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" @portArgs @IdfArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
