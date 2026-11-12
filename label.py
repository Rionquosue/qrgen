"""Printer-resolution label rendering and ZPL serialization."""
from pathlib import Path
import barcode
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
from fontTools.ttLib import TTFont

DPI = 203
FONT = Path(__file__).parent / 'assets' / 'Roboto.ttf'
with TTFont(FONT) as _font:
    GLYPHS = set(_font.getBestCmap())
PRESETS = {'1 × 1.5 in': (1, 1.5), '1 × 1 in': (1, 1),
           '1.5 × 1 in': (1.5, 1), '2 × 1 in': (2, 1),
           '2 × 1.25 in': (2, 1.25), '2 × 2 in': (2, 2),
           '3 × 1 in': (3, 1), '3 × 2 in': (3, 2),
           '4 × 2 in': (4, 2), '4 × 6 in': (4, 6)}
KINDS = ('QR', 'Code 128', 'UPC-A', 'EAN-13')


def caption(text, width, max_height):
    if any(ord(c) not in GLYPHS for c in text):
        raise ValueError('The caption contains characters unavailable in Roboto.')
    for size in range(22, 13, -1):
        font = ImageFont.truetype(str(FONT), size)
        lines, line = [], ''
        for char in text:
            if font.getlength(line + char) > width:
                lines.append(line)
                line = ''
            line += char
        lines.append(line)
        step = sum(font.getmetrics()) + 2
        if len(lines) * step <= max_height:
            return font, lines, step
    raise ValueError('Caption is too long. Shorten the text or choose a larger label.')


def render(text, kind='QR', width=1, height=1.5, orientation=None):
    """Width/height always describe loaded media; orientation only turns artwork."""
    if not text or text.isspace():
        raise ValueError('Enter text to generate a label.')
    if len(text) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError('Use a single line of printable text (maximum 1,000 characters).')
    if kind not in KINDS:
        raise ValueError('Unsupported code type.')
    if not 0.5 <= width <= 4.09 or not 0.5 <= height <= 39:
        raise ValueError('Label dimensions exceed the GC420d print area.')
    if orientation not in (None, 'Portrait', 'Landscape'):
        raise ValueError('Choose Portrait or Landscape.')
    w, h = round(width * DPI), round(height * DPI)
    rotate = (orientation == 'Portrait' and w > h) or (
        orientation == 'Landscape' and w <= h)
    if rotate:
        w, h = h, w
    margin = 8
    font, lines, step = caption(text, w - margin * 2, h // 3)
    cap_h = len(lines) * step
    area_w, area_h = w - margin * 2, h - margin * 2 - cap_h - 6
    result = Image.new('L', (w, h), 255)
    draw = ImageDraw.Draw(result)
    if kind == 'QR':
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4)
        qr.add_data(text)
        try:
            qr.make(fit=True)
        except qrcode.exceptions.DataOverflowError as exc:
            raise ValueError('Text is too long for QR.') from exc
        matrix = qr.get_matrix()
        module = min(area_w, area_h) // len(matrix)
        if module < 3:
            raise ValueError('QR is too dense for this label. Use a larger size or shorter text.')
        sw = sh = len(matrix) * module
        x, y = (w - sw) // 2, margin + (area_h - sh) // 2
        for row, values in enumerate(matrix):
            for col, black in enumerate(values):
                if black:
                    draw.rectangle((x+col*module, y+row*module,
                                    x+(col+1)*module-1, y+(row+1)*module-1), fill=0)
    else:
        name = {'Code 128': 'code128', 'UPC-A': 'upc', 'EAN-13': 'ean13'}[kind]
        if kind in ('UPC-A', 'EAN-13'):
            digits = 12 if kind == 'UPC-A' else 13
            if len(text) != digits or not text.isascii() or not text.isdigit():
                raise ValueError(f'{kind} requires exactly {digits} digits, including its check digit.')
        try:
            code = barcode.get(name, text)
            if kind != 'Code 128' and code.get_fullcode() != text:
                raise ValueError('Incorrect check digit.')
            bits = code.build()[0]
        except Exception as exc:
            raise ValueError(f'Invalid {kind}: {exc}') from exc
        # Preserve integral module widths and at least ten modules of quiet zone.
        module = area_w // (len(bits) + 20)
        if module < 2:
            raise ValueError('Barcode needs a wider label. Choose Landscape or a larger label; keep media dimensions matched to the roll.')
        x = (w - len(bits) * module) // 2
        for i, bit in enumerate(bits):
            if bit == '1':
                draw.rectangle((x+i*module, margin, x+(i+1)*module-1,
                                margin+area_h-1), fill=0)
    y = h - margin - cap_h
    for line in lines:
        draw.text((w/2, y), line, font=font, fill=0, anchor='mt')
        y += step
    result = result.point(lambda v: 255 if v >= 128 else 0, mode='1')
    # Turn every pixel, including the caption, onto the fixed physical canvas.
    return result.transpose(Image.Transpose.ROTATE_270) if rotate else result


def to_zpl(image, copies=1):
    if not isinstance(copies, int) or not 1 <= copies <= 999:
        raise ValueError('Copies must be 1–999.')
    if image.mode != '1':
        raise ValueError('Expected a monochrome label.')
    # Pillow packs each row MSB-first; ZPL uses 1 for black, Pillow uses 0.
    black = ImageOps.invert(image.convert('L')).convert('1')
    data = black.tobytes()
    stride = (image.width + 7) // 8
    return (f'^XA^CI0^PW{image.width}^LL{image.height}^LH0,0^LS0^LT0^FWN^PON^PMN'
            f'^FO0,0^GFA,{len(data)},{len(data)},{stride},{data.hex().upper()}'
            f'^FS^PQ{copies},0,1,N^XZ\r\n').encode('ascii')
