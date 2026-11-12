$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$exe = (Resolve-Path 'dist/QRGen/QRGen.exe').Path
$result = Join-Path $env:RUNNER_TEMP 'qrgen-self-test.json'
if (Test-Path $result) { Remove-Item $result }
$p = Start-Process -FilePath $exe -ArgumentList @('--self-test', "`"$result`"") -PassThru
if (-not $p.WaitForExit(60000)) { $p.Kill(); throw 'Executable self-test timed out.' }
if ($p.ExitCode -ne 0) { throw "Executable self-test failed: $($p.ExitCode)" }
if (-not (Test-Path $result)) { throw 'Executable produced no self-test report.' }
$report = Get-Content $result -Raw | ConvertFrom-Json
if (-not $report.ok) { throw 'Invalid self-test report.' }
$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($exe)
if ($null -eq $icon) { throw 'Missing executable icon.' }
$icon.Dispose()
# Verify the shipped shortcut helper in the disposable CI user desktop.
& ./dist/QRGen/Create-Desktop-Shortcut.ps1
$shell = New-Object -ComObject WScript.Shell
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'QRGen.lnk'
if ($shell.CreateShortcut($shortcut).TargetPath -ne $exe) { throw 'Incorrect shortcut target.' }
Remove-Item $shortcut
Compress-Archive -Path dist/QRGen -DestinationPath dist/QRGen-Windows-x64.zip -Force
