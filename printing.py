"""Windows RAW spooler transport: no print dialog or GDI page layout."""
import sys


def api():
    if sys.platform != 'win32':
        raise RuntimeError('Direct printing requires Windows. Preview and export work here.')
    import win32print
    return win32print


def printers():
    p = api()
    return sorted({item[2] for item in p.EnumPrinters(
        p.PRINTER_ENUM_LOCAL | p.PRINTER_ENUM_CONNECTIONS)})


def send_raw(name, payload):
    if not name:
        raise ValueError('Select the installed Zebra printer.')
    p = api()
    handle = p.OpenPrinter(name)
    started = False
    try:
        job = p.StartDocPrinter(handle, 1, ('Zebra Label', None, 'RAW'))
        started = True
        p.StartPagePrinter(handle)
        offset = 0
        while offset < len(payload):
            written = p.WritePrinter(handle, payload[offset:])
            if not written:
                raise RuntimeError('Printer accepted no data; job aborted.')
            offset += written
        p.EndPagePrinter(handle)
        p.EndDocPrinter(handle)
        started = False
        return job
    except Exception:
        if started:
            p.AbortPrinter(handle)
        raise
    finally:
        p.ClosePrinter(handle)
