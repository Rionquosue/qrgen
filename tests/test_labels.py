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
    ('5901234123458', 'EAN-13'), ('', 'QR'), ('a\tb', 'QR'), ('😀', 'QR')])
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

def _port_mocks(monkeypatch, port='USB001'):
    p, f = Mock(), Mock()
    p.GetPrinter.return_value = {'pPortName': port}
    monkeypatch.setattr(printing, 'api', lambda: p)
    monkeypatch.setattr(printing, 'device', lambda: f)
    monkeypatch.setattr(printing, 'usb_paths', lambda: ['\\\\?\\usb#vid_0a5f&pid_0001#x#{guid}', '\\\\?\\usb#vid_1111&pid_2#y#{guid}'])
    return p, f

def test_direct_port_partial_write(monkeypatch):
    p, f = _port_mocks(monkeypatch)
    f.WriteFile.side_effect = [(0, 2), (0, 3)]
    assert printing.send_raw('Zebra', b'12345') == 'USB001'
    assert f.CreateFile.call_args.args[0] == '\\\\?\\usb#vid_0a5f&pid_0001#x#{guid}'
    assert f.WriteFile.call_args_list[1].args[1] == b'345'
    f.CreateFile.return_value.Close.assert_called_once()
    p.StartDocPrinter.assert_not_called()  # the spooler is never used

def test_failed_write_closes_port(monkeypatch):
    p, f = _port_mocks(monkeypatch)
    f.WriteFile.return_value = (0, 0)
    with pytest.raises(RuntimeError):
        printing.send_raw('Zebra', b'123')
    f.CreateFile.return_value.Close.assert_called_once()

def test_non_local_port_rejected(monkeypatch):
    _port_mocks(monkeypatch, 'IP_192.168.0.5')
    with pytest.raises(RuntimeError, match='local'):
        printing.send_raw('Zebra', b'123')

@pytest.mark.parametrize('w,h', [(1, 1.5), (1.5, 1), (2, 2), (3, 4)])
@pytest.mark.parametrize('orientation', ['Portrait', 'Landscape'])
def test_orientation_preserves_media_and_all_pixels(w, h, orientation):
    text = 'TURN ME'
    actual = render(text, width=w, height=h, orientation=orientation)
    rotate = (orientation == 'Portrait' and w > h) or (orientation == 'Landscape' and w <= h)
    # Reconstruct the logical artwork, then compare every pixel (caption included).
    logical = render(text, width=h if rotate else w, height=w if rotate else h)
    expected = logical.transpose(Image.Transpose.ROTATE_270) if rotate else logical
    assert actual.size == (round(w * 203), round(h * 203))
    assert actual.tobytes() == expected.tobytes()
    assert zxingcpp.read_barcode(actual.convert('L')).text == text
    zpl = to_zpl(actual).decode()
    assert f'^PW{actual.width}^LL{actual.height}' in zpl
    total, count, stride, data = re.search(r'\^GFA,(\d+),(\d+),(\d+),([0-9A-F]+)', zpl).groups()
    packed = Image.frombytes('1', actual.size, bytes.fromhex(data))
    assert ImageOps.invert(packed.convert('L')).convert('1').tobytes() == actual.tobytes()


def test_landscape_barcode_on_fixed_portrait_stock():
    image = render('036000291452', 'UPC-A', 1, 1.5, 'Landscape')
    assert image.size == (203, 304)
    assert zxingcpp.read_barcode(image.convert('L')).text in ('036000291452', '0036000291452')


def test_orientation_does_not_bypass_printhead_width_limit():
    with pytest.raises(ValueError, match='print area'):
        render('TEST', width=6, height=4, orientation='Portrait')


def test_large_landscape_uses_length_without_exceeding_printhead():
    image = render('TURN ME', width=4, height=6, orientation='Landscape')
    assert image.size == (812, 1218)
    assert zxingcpp.read_barcode(image.convert('L')).text == 'TURN ME'

@pytest.mark.parametrize('dpi', [203, 300, 600])
@pytest.mark.parametrize('orientation', ['Portrait', 'Landscape'])
def test_centered_group_and_resolution(dpi, orientation):
    image = render('Hello Zebra', width=1.5, height=1, orientation=orientation, dpi=dpi)
    assert image.size == (round(1.5*dpi), dpi)
    left, top, right, bottom = ImageOps.invert(image.convert('L')).getbbox()
    assert abs(left - (image.width-right)) <= 2
    assert abs(top - (image.height-bottom)) <= 2
    assert zxingcpp.read_barcode(image.convert('L')).text == 'Hello Zebra'
    assert f'^PW{image.width}^LL{image.height}'.encode() in to_zpl(image)


def test_font_size_is_honored():
    from label import caption
    small = caption('Hello Zebra', 400, 200, font_size=6)
    large = caption('Hello Zebra', 400, 200, font_size=12)
    assert large.height > small.height * 1.7
    assert large.width > small.width * 1.7

@pytest.mark.parametrize('kwargs', [{'dpi': 72}, {'font_size': 0}, {'font_size': float('nan')}])
def test_invalid_typography(kwargs):
    with pytest.raises(ValueError):
        render('Hello Zebra', **kwargs)


def test_caption_wraps_words():
    from label import wrap_words, FONT
    from PIL import ImageFont
    font = ImageFont.truetype(str(FONT), 22)
    width = max(font.getlength('Hello Zebra'), font.getlength('label maker')) + 1
    assert wrap_words('Hello Zebra label maker', font, width) == ['Hello Zebra', 'label maker']
    assert wrap_words('  Hello   Zebra  ', font, width) == ['Hello Zebra']
    token = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    lines = wrap_words(token, font, width)
    assert ''.join(lines) == token
    assert all(font.getlength(line) <= width for line in lines)


@pytest.mark.parametrize('orientation', ['Portrait', 'Landscape'])
def test_profile_centered_within_offsets(orientation):
    from label import PRESETS, INSETS
    name = '1.5 × 1 in'
    w, h = PRESETS[name]
    image = render('Hello Zebra', width=w, height=h, orientation=orientation, inset=INSETS[name])
    assert image.size == (round(42 / 25.4 * 203), round(29 / 25.4 * 203))
    l, t, r, b = (round(v / 25.4 * 203) for v in INSETS[name])
    left, top, right, bottom = ImageOps.invert(image.convert('L')).getbbox()
    assert left >= l and top >= t and image.width - right >= r and image.height - bottom >= b
    assert abs((left - l) - (image.width - r - right)) <= 2
    assert abs((top - t) - (image.height - b - bottom)) <= 2
    assert zxingcpp.read_barcode(image.convert('L')).text == 'Hello Zebra'


@pytest.mark.parametrize('kind', ['QR', 'Code 128'])
def test_wrap_does_not_change_scanned_text_but_returns_do(kind):
    from label import caption
    text = 'Hello Zebra'
    narrow = render(text, kind, 3, 2, font_size=14)
    assert zxingcpp.read_barcode(narrow.convert('L')).text == text
    assert caption(text, 60, 200, 14).height > caption(text, 400, 200, 14).height  # wraps
    with_return = 'Hello\nZebra'
    image = render(with_return, kind, 3, 2)
    assert zxingcpp.read_barcode(image.convert('L')).text == with_return
    assert caption(with_return, 400, 200).height > caption(text, 400, 200).height  # forced break


def test_gap_sensing_and_pitch_length_for_backing_profile():
    from label import PRESETS, INSETS
    name = '1.5 × 1 in'
    image = render('Hello Zebra', width=PRESETS[name][0], height=PRESETS[name][1], inset=INSETS[name])
    zpl = to_zpl(image, web=True).decode()
    assert zpl.startswith('^XA^MNY') and '^PW336^LL232' in zpl  # 29 mm feed pitch
    assert '^MN' not in to_zpl(image).decode()
