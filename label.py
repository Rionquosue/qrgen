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
# Label rectangle on the page, as mm insets: (left, first-out edge, right, last-out edge).
# Row 0 of the bitmap is the first part out of the printer. The 26 mm label sits 2 mm from
# row 0 and ends 28 mm down, past the end of the 1 in (25.4 mm) page, hence a negative bottom.
INSETS = {'1.5 × 1 in': (2, 2, 2, 25.4 - 28)}
KINDS = ('QR', 'Code 128', 'UPC-A', 'EAN-13')


def wrap_words(text, font, width):
    """Wrap whole words; split only tokens wider than an entire line."""
    lines, line = [], ''
    for word in text.split():
        candidate = f'{line} {word}' if line else word
        if font.getlength(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ''
        for char in word:
            if font.getlength(char) > width:
                raise ValueError('Font is too large for this label.')
            if font.getlength(line + char) > width:
                lines.append(line)
                line = ''
            line += char
    if line:
        lines.append(line)
    return lines


def caption(text, width, max_height, font_size=8, dpi=203):
    if any(ord(c) not in GLYPHS for c in text.replace('\n', '')):
        raise ValueError('The caption contains characters unavailable in Roboto.')
    font = ImageFont.truetype(str(FONT), max(1, round(font_size * dpi / 72)))
    lines = []
    for paragraph in text.split('\n'):
        lines += wrap_words(paragraph, font, width) or ['']
    step = sum(font.getmetrics()) + max(1, round(dpi / 100))
    layer = Image.new('L', (width, len(lines) * step), 255)
    draw = ImageDraw.Draw(layer)
    for i, line in enumerate(lines):
        draw.text((width / 2, i * step), line, font=font, fill=0, anchor='mt')
    bounds = ImageOps.invert(layer).getbbox()
    if bounds is None:
        raise ValueError('Caption has no visible characters.')
    layer = layer.crop(bounds)
    if layer.height > max_height:
        raise ValueError('Caption is too large. Reduce font size or choose a larger label.')
    return layer


def render(text, kind='QR', width=1, height=1.5, orientation=None,
           font_size=8, dpi=203, inset=None):
    """Center the complete design; width/height always describe loaded media.

    inset=(left, top, right, bottom) in mm centers the design within the label
    printed on the backing, not within the full media."""
    if not text or text.isspace():
        raise ValueError('Enter text to generate a label.')
    if len(text) > 1000 or any((ord(c) < 32 and c != '\n') or ord(c) == 127 for c in text):
        raise ValueError('Use printable text and returns only (maximum 1,000 characters).')
    if kind not in KINDS:
        raise ValueError('Unsupported code type.')
    if dpi not in (203, 300, 600):
        raise ValueError('Resolution must be 203, 300 or 600 DPI.')
    if not 4 <= font_size <= 36:
        raise ValueError('Font size must be 4–36 points.')
    if not 0.5 <= width <= 4.09 or not 0.5 <= height <= 39:
        raise ValueError('Label dimensions exceed the supported print area.')
    if orientation not in (None, 'Portrait', 'Landscape'):
        raise ValueError('Choose Portrait or Landscape.')
    w, h = round(width * dpi), round(height * dpi)
    page = (w, h)
    pl = pt = 0
    if inset:
        pl, pt, pr, pb = (round(v / 25.4 * dpi) for v in inset)
        w, h = w - pl - pr, h - pt - pb
        if w < 1 or h < 1:
            raise ValueError('Label offsets exceed the media size.')
    rotate = (orientation == 'Portrait' and w > h) or (
        orientation == 'Landscape' and w <= h)
    if rotate:
        w, h = h, w
    margin = max(1, round(8 * dpi / 203))
    gap = max(1, round(6 * dpi / 203))
    cap = caption(text, w - margin * 2, h // 3, font_size, dpi)
    result = Image.new('L', (w, h), 255)
    draw = ImageDraw.Draw(result)
    if kind == 'QR':
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
        qr.add_data(text)
        try:
            qr.make(fit=True)
        except qrcode.exceptions.DataOverflowError as exc:
            raise ValueError('Text is too long for QR.') from exc
        matrix = qr.get_matrix()
        n = len(matrix)
        module = min((w - 2 * margin) // (n + 8),
                     (h - 2 * margin - cap.height - gap) // (n + 12))
        if module < max(3, round(3 * dpi / 203)):
            raise ValueError('QR and caption do not fit. Reduce font size/text or enlarge the label.')
        symbol_height = n * module
        caption_gap = 4 * module + gap  # Keep the four-module quiet zone intact.
        group_height = symbol_height + caption_gap + cap.height
        x, y = (w - symbol_height) // 2, (h - group_height) // 2
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
        module = (w - 2 * margin) // (len(bits) + 20)
        if module < max(2, round(2 * dpi / 203)):
            raise ValueError('Barcode needs a wider label. Choose Landscape or a larger label.')
        symbol_height = h - 2 * margin - cap.height - gap
        caption_gap = gap
        y = margin
        x = (w - len(bits) * module) // 2
        for i, bit in enumerate(bits):
            if bit == '1':
                draw.rectangle((x+i*module, y, x+(i+1)*module-1,
                                y+symbol_height-1), fill=0)
    result.paste(cap, ((w - cap.width) // 2, y + symbol_height + caption_gap))
    result = result.point(lambda v: 255 if v >= 128 else 0, mode='1')
    if rotate:
        result = result.transpose(Image.Transpose.ROTATE_270)
    if inset:
        box = ImageOps.invert(result.convert('L')).getbbox()
        if box and (pl + box[2] > page[0] or pt + box[3] > page[1]):
            raise ValueError('Design does not fit the printable area. Reduce font size or text.')
        sheet = Image.new('1', page, 1)
        sheet.paste(result, (pl, pt))
        return sheet
    return result


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
