# QRGen

Small Python/Tkinter desktop label maker for the Zebra GC420d on Windows.

- Live QR, Code 128, UPC-A and EAN-13 preview.
- Exact input caption in bundled Google Roboto, wrapped without truncation.
- Common label presets; default **1 inch wide × 1.5 inches tall**. Set physical width/feed length to match the loaded roll; select Portrait or Landscape separately.
- Direct RAW ZPL printing with copies; no Windows print dialog, page margins or driver scaling.
- PNG and ZPL export.

## Portable Windows package

Download **QRGen-Windows-x64.zip** from [Releases](https://github.com/Rionquosue/qrgen/releases/latest), extract the entire ZIP, and run `QRGen.exe`. Python is included. Keep the `_internal` folder beside the executable. Optionally run `Create-Desktop-Shortcut.cmd`. Packages are unsigned.

The build workflow follows the webcam_capture release pattern: Windows x64 portable ZIP, desktop shortcut helper, SHA-256 checksums and an automatically numbered release after successful tests and executable smoke checks. Every main-branch push publishes a new version. Pull requests build and test without publishing.

Build locally on Windows with Python 3.12:

```powershell
py -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1
```

The unpacked app appears in `dist/QRGen`. CI additionally runs `packaging/verify_windows.ps1` to verify and ZIP it. This script uses `RUNNER_TEMP` for its smoke-test report.

## Run from source on Windows

Install Python 3.11 or newer from python.org with Tcl/Tk enabled. Install the Zebra printer as a Windows printer queue and connect it, normally via USB. Extract this entire folder, then open a terminal in it:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Enter text, choose a format and the physical label dimensions, select the Zebra printer, then click **Print directly**. The app only automatically selects a printer whose name contains GC420. Other Zebra queue names can be selected manually. Send only to a ZPL-compatible printer.

The app renders at 203 dots/inch and sends the same monochrome bitmap using ZPL `^GFA`, `^PW` and `^LL`. The entire label—including Roboto—is rasterized, so no printer font installation is needed. Windows' RAW spooler transports the commands but does not lay out the page. A queued job is not confirmation that paper physically printed.

## Label and code limits

Dimensions are width across the printhead × length along the feed direction. A 1 × 1.5 inch label becomes 203 × 304 dots after rounding. Eight dots of internal padding protect the design; QR has a four-module quiet zone, and linear codes have at least ten modules at each end. QR modules are at least three dots and barcode modules at least two. The selected font point size is preserved; excessive text or dense codes are rejected, never clipped or stretched.

A UPC-A barcode needs more width than the default portrait label offers: select Landscape or a larger label. Only swap physical dimensions if this matches how the roll is loaded. Supply all 12 UPC-A or 13 EAN-13 digits, including a valid check digit. These barcode types are numeric; use QR or Code 128 for general text. Captions support characters present in Roboto; unsupported glyphs are rejected. Long captions wrap by character. Retail barcode certification is outside this utility's scope.

Load matching stock and calibrate the printer's gap/black-mark sensor using Zebra's instructions. RAW printing avoids driver margin/crop issues, but cannot correct misloaded media, incorrect sensor configuration, mechanical alignment or unsuitable darkness. Media sensing, print speed and darkness use the printer's existing configuration. Label origin, shift, orientation, width and length are explicitly set for each job; these may affect subsequent raw jobs that omit their own settings.

## Development

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

Tests independently decode rendered codes with ZXing, round-trip ZPL bitmap bytes, validate checksums and sizing, and mock RAW transport including partial writes and aborts. Preview/export also work on Linux/macOS with Tk installed; direct printing requires Windows and pywin32.

Physical GC420d output and the Windows spooler require verification on your machine. No printer was available during development.

Files: `app.py` UI, `label.py` rendering/ZPL, `printing.py` transport, `tests/` automated checks. Source: https://github.com/Rionquosue/qrgen.

## References and font licensing

- [Zebra GC420d user guide](https://www.zebra.com/content/dam/support-dam/en/documentation/unrestricted/guide/product/gc420d-ug-en.pdf)
- [Microsoft RAW printing](https://learn.microsoft.com/en-us/windows-hardware/drivers/print/raw-data-type)
- [python-barcode](https://python-barcode.readthedocs.io/en/stable/)
- [qrcode](https://pypi.org/project/qrcode/)
- [Google Fonts Roboto](https://github.com/google/fonts/tree/main/ofl/roboto): distributed under the SIL Open Font License; see `assets/OFL.txt`. The included variable font is rendered at its default regular weight. Font downloaded from this source during development.

## Physical stock and artwork orientation

Physical dimensions always control the printer: **width across the printhead × feed length**. If your 1 × 1.5 inch stock is loaded 1.5 inches across with a 1 inch feed length, enable **Swap physical width / feed length**. The printer then receives 304 dots of width and 203 dots of length.

**Portrait / Landscape** changes only the artwork. The code and Roboto caption are laid out together and rotated as one bitmap to fit the fixed physical stock. The preview and PNG show exactly the bitmap sent to the printer, with feed direction running top to bottom. Switching artwork orientation never changes the ZPL print width or feed length. The application cannot detect roll dimensions automatically.

## Caption size and resolution

Font size is adjustable from 4–36 points; the selected size is used without automatic shrinking. QR and caption are centered together using visible caption bounds, with a four-module QR quiet zone.

Resolution choices are 203, 300 and 600 DPI. Use **203 DPI for the GC420d**. Higher values are for printers with matching printheads, not a quality boost for a 203-DPI printer. Dimensions, padding, font point sizes and PNG metadata follow the selected resolution. A mismatched DPI causes incorrect physical size and clipping.
