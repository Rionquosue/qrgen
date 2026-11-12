$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot 'QRGen.exe'
if (-not (Test-Path $exe)) { throw 'Extract the entire ZIP before creating a shortcut.' }
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'QRGen.lnk'))
$link.TargetPath = $exe
$link.WorkingDirectory = $PSScriptRoot
$link.IconLocation = "$exe,0"
$link.Save()
Write-Host 'QRGen desktop shortcut created.'
