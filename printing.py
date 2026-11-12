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


def usb_paths():
    """Device paths of all present USB printers (Windows has no \\\\.\\USB001 name for them)."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [('a', wintypes.DWORD), ('b', wintypes.WORD), ('c', wintypes.WORD),
                    ('d', ctypes.c_ubyte * 8)]

    class Interface(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('guid', GUID), ('flags', wintypes.DWORD),
                    ('reserved', ctypes.c_size_t)]

    guid = GUID(0x28D78FAD, 0x5A12, 0x11D1, (ctypes.c_ubyte * 8)(0xAE, 0x5B, 0, 0, 0xF8, 3, 0xA8, 0xC2))
    api = ctypes.WinDLL('setupapi', use_last_error=True)
    api.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    api.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    api.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                wintypes.DWORD, ctypes.POINTER(Interface)]
    api.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(Interface), ctypes.c_void_p,
                                                     wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    api.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    devices = api.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x2 | 0x10)  # PRESENT | DEVICEINTERFACE
    if devices in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    paths = []
    try:
        index = 0
        while True:
            item = Interface()
            item.size = ctypes.sizeof(Interface)
            if not api.SetupDiEnumDeviceInterfaces(devices, None, ctypes.byref(guid), index, ctypes.byref(item)):
                break
            index += 1
            needed = wintypes.DWORD()
            api.SetupDiGetDeviceInterfaceDetailW(devices, ctypes.byref(item), None, 0, ctypes.byref(needed), None)
            buffer = ctypes.create_string_buffer(needed.value)
            ctypes.c_uint32.from_address(ctypes.addressof(buffer)).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if api.SetupDiGetDeviceInterfaceDetailW(devices, ctypes.byref(item), buffer, needed, None, None):
                paths.append(ctypes.wstring_at(ctypes.addressof(buffer) + 4))
    finally:
        api.SetupDiDestroyDeviceInfoList(devices)
    return paths


def device_path(port):
    if not port.upper().startswith('USB'):
        return f'\\\\.\\{port}'
    paths = usb_paths()
    zebra = [p for p in paths if 'vid_0a5f' in p.lower()]
    paths = zebra or paths
    if len(paths) != 1:
        raise RuntimeError(f'Expected one connected USB printer, found {len(paths)}.')
    return paths[0]


def send_raw(name, payload):
    if not name:
        raise ValueError('Select the installed Zebra printer.')
    port = port_of(name)
    f = device()
    handle = f.CreateFile(device_path(port), f.GENERIC_WRITE, 3, None, f.OPEN_EXISTING, 0, None)
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
