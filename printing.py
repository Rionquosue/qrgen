"""Direct printer-port transport: bytes go to the printer's port, not through the spooler."""
import re
import sys


def api():
    if sys.platform != 'win32':
        raise RuntimeError('Direct printing requires Windows. Preview and export work here.')
    import win32print
    return win32print


def device():
    import win32file
    return win32file


def printers():
    p = api()
    return sorted({item[2] for item in p.EnumPrinters(
        p.PRINTER_ENUM_LOCAL | p.PRINTER_ENUM_CONNECTIONS)})


def port_of(name):
    """Return the port (for example USB001) that the printer queue is attached to."""
    p = api()
    handle = p.OpenPrinter(name)
    try:
        port = p.GetPrinter(handle, 2)['pPortName']
    finally:
        p.ClosePrinter(handle)
    port = port.split(',')[0].strip().rstrip(':')
    if not re.fullmatch(r'(USB|LPT|COM)\d+', port, re.IGNORECASE):
        raise RuntimeError(f'Printer port {port!r} is not a local USB, LPT or COM port.')
    return port


def send_raw(name, payload):
    if not name:
        raise ValueError('Select the installed Zebra printer.')
    port = port_of(name)
    f = device()
    handle = f.CreateFile(f'\\\\.\\{port}', f.GENERIC_WRITE, 0, None, f.OPEN_EXISTING, 0, None)
    try:
        offset = 0
        while offset < len(payload):
            _, written = f.WriteFile(handle, payload[offset:])
            if not written:
                raise RuntimeError('Printer accepted no data.')
            offset += written
    finally:
        handle.Close()
    return port
