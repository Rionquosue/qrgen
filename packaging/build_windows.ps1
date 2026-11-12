$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m PyInstaller --noconfirm --clean --windowed --onedir --name QRGen --icon assets/app.ico --add-data "assets;assets" --collect-all barcode --collect-all fontTools --hidden-import win32print app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
Copy-Item README.md, LICENSE dist/QRGen/
Copy-Item packaging/Create-Desktop-Shortcut.* dist/QRGen/
Copy-Item assets/OFL.txt dist/QRGen/Roboto-OFL.txt
