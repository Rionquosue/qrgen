import re
import sys
from unittest.mock import Mock
import pytest
import zxingcpp
from PIL import Image, ImageOps
from label import render, to_zpl
import printing

@pytest.mark.parametrize('kind,text,w,h', [
    ('QR', 'Hello Zebra', 1, 1.5), ('QR', 'https://example.com', 1, 1.5),
    ('Code 128', 'ABC-123', 2, 1), ('UPC-A', '036000291452', 2, 1.25),
    ('EAN-13', '5901234123457', 2, 1.25)])
def test_scannable(kind, text, w, h):
    image = render(text, kind, w, h)
    decoded = zxingcpp.read_barcode(image.convert('L'))
    assert decoded is not None
    # ZXing may report UPC-A as its equivalent leading-zero EAN-13.
    assert decoded.text in ([text, '0' + text] if kind == 'UPC-A' else [text])

@pytest.mark.parametrize('text,kind', [('036000291453', 'UPC-A'), ('123', 'UPC-A'),
    ('5901234123458', 'EAN-13'), ('', 'QR'), ('a\nb', 'QR'), ('😀', 'QR')])
def test_invalid(text, kind):
    with pytest.raises(ValueError):
        render(text, kind, 2, 2)

def test_barcode_cannot_be_squeezed():
    with pytest.raises(ValueError, match='wider'):
        render('036000291452', 'UPC-A')

def test_zpl_roundtrip():
    original = render('Exact pixels')
    zpl = to_zpl(original, 3).decode()
    total, count, stride, data = re.search(r'\^GFA,(\d+),(\d+),(\d+),([0-9A-F]+)', zpl).groups()
    assert int(total) == int(count) == int(stride) * original.height
    packed = Image.frombytes('1', (original.width, original.height), bytes.fromhex(data))
    restored = ImageOps.invert(packed.convert('L')).convert('1')
    assert restored.tobytes() == original.tobytes()
    assert '^PW203^LL304' in zpl and '^PQ3,0,1,N' in zpl

@pytest.mark.parametrize('copies', [0, -1, 1000, '2'])
def test_invalid_copies(copies):
    with pytest.raises(ValueError):
        to_zpl(render('test'), copies)

def test_raw_partial_write(monkeypatch):
    p = Mock()
    p.WritePrinter.side_effect = [2, 3]
    p.StartDocPrinter.return_value = 42
    monkeypatch.setattr(printing, 'api', lambda: p)
    assert printing.send_raw('Zebra', b'12345') == 42
    assert p.WritePrinter.call_args_list[1].args[1] == b'345'
    assert p.StartDocPrinter.call_args.args[2][2] == 'RAW'
    p.ClosePrinter.assert_called_once()
    p.AbortPrinter.assert_not_called()

def test_failed_write_aborts(monkeypatch):
    p = Mock()
    p.WritePrinter.return_value = 0
    monkeypatch.setattr(printing, 'api', lambda: p)
    with pytest.raises(RuntimeError):
        printing.send_raw('Zebra', b'123')
    p.AbortPrinter.assert_called_once()
    p.ClosePrinter.assert_called_once()
