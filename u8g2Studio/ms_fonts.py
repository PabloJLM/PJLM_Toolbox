# -*- coding: utf-8 -*-
"""
ms_fonts.py - Fuente 5x7 embebida + registro de fuentes u8g2.

La vista previa NO renderiza los glifos reales de u8g2 (esas fuentes viven
compiladas dentro de la libreria). Lo que hace es:

  * usar el ANCHO DE AVANCE y la ALTURA real de cada fuente u8g2, para que
    la posicion y el tamano de las cajas de texto en el canvas coincidan
    con lo que veras en el OLED;
  * dibujar los glifos con una fuente 5x7 clasica escalada a esa caja.

Para las fuentes monoespaciadas (5x7, 6x10, 4x6, 7x13...) el resultado es
practicamente identico. Para las proporcionales (ncenB*, helv*) el ancho
es una estimacion.

u8g2 Studio - MIT License
"""

# ============================================================
#  Fuente 5x7 (column-major, bit0 = fila superior)
# ============================================================

FONT5X7 = {
    ' ': (0x00, 0x00, 0x00, 0x00, 0x00),
    '!': (0x00, 0x00, 0x5F, 0x00, 0x00),
    '"': (0x00, 0x07, 0x00, 0x07, 0x00),
    '#': (0x14, 0x7F, 0x14, 0x7F, 0x14),
    '$': (0x24, 0x2A, 0x7F, 0x2A, 0x12),
    '%': (0x23, 0x13, 0x08, 0x64, 0x62),
    '&': (0x36, 0x49, 0x55, 0x22, 0x50),
    "'": (0x00, 0x05, 0x03, 0x00, 0x00),
    '(': (0x00, 0x1C, 0x22, 0x41, 0x00),
    ')': (0x00, 0x41, 0x22, 0x1C, 0x00),
    '*': (0x14, 0x08, 0x3E, 0x08, 0x14),
    '+': (0x08, 0x08, 0x3E, 0x08, 0x08),
    ',': (0x00, 0x50, 0x30, 0x00, 0x00),
    '-': (0x08, 0x08, 0x08, 0x08, 0x08),
    '.': (0x00, 0x60, 0x60, 0x00, 0x00),
    '/': (0x20, 0x10, 0x08, 0x04, 0x02),
    '0': (0x3E, 0x51, 0x49, 0x45, 0x3E),
    '1': (0x00, 0x42, 0x7F, 0x40, 0x00),
    '2': (0x42, 0x61, 0x51, 0x49, 0x46),
    '3': (0x21, 0x41, 0x45, 0x4B, 0x31),
    '4': (0x18, 0x14, 0x12, 0x7F, 0x10),
    '5': (0x27, 0x45, 0x45, 0x45, 0x39),
    '6': (0x3C, 0x4A, 0x49, 0x49, 0x30),
    '7': (0x01, 0x71, 0x09, 0x05, 0x03),
    '8': (0x36, 0x49, 0x49, 0x49, 0x36),
    '9': (0x06, 0x49, 0x49, 0x29, 0x1E),
    ':': (0x00, 0x36, 0x36, 0x00, 0x00),
    ';': (0x00, 0x56, 0x36, 0x00, 0x00),
    '<': (0x00, 0x08, 0x14, 0x22, 0x41),
    '=': (0x14, 0x14, 0x14, 0x14, 0x14),
    '>': (0x41, 0x22, 0x14, 0x08, 0x00),
    '?': (0x02, 0x01, 0x51, 0x09, 0x06),
    '@': (0x32, 0x49, 0x79, 0x41, 0x3E),
    'A': (0x7E, 0x11, 0x11, 0x11, 0x7E),
    'B': (0x7F, 0x49, 0x49, 0x49, 0x36),
    'C': (0x3E, 0x41, 0x41, 0x41, 0x22),
    'D': (0x7F, 0x41, 0x41, 0x22, 0x1C),
    'E': (0x7F, 0x49, 0x49, 0x49, 0x41),
    'F': (0x7F, 0x09, 0x09, 0x01, 0x01),
    'G': (0x3E, 0x41, 0x41, 0x51, 0x32),
    'H': (0x7F, 0x08, 0x08, 0x08, 0x7F),
    'I': (0x00, 0x41, 0x7F, 0x41, 0x00),
    'J': (0x20, 0x40, 0x41, 0x3F, 0x01),
    'K': (0x7F, 0x08, 0x14, 0x22, 0x41),
    'L': (0x7F, 0x40, 0x40, 0x40, 0x40),
    'M': (0x7F, 0x02, 0x04, 0x02, 0x7F),
    'N': (0x7F, 0x04, 0x08, 0x10, 0x7F),
    'O': (0x3E, 0x41, 0x41, 0x41, 0x3E),
    'P': (0x7F, 0x09, 0x09, 0x09, 0x06),
    'Q': (0x3E, 0x41, 0x51, 0x21, 0x5E),
    'R': (0x7F, 0x09, 0x19, 0x29, 0x46),
    'S': (0x46, 0x49, 0x49, 0x49, 0x31),
    'T': (0x01, 0x01, 0x7F, 0x01, 0x01),
    'U': (0x3F, 0x40, 0x40, 0x40, 0x3F),
    'V': (0x1F, 0x20, 0x40, 0x20, 0x1F),
    'W': (0x7F, 0x20, 0x18, 0x20, 0x7F),
    'X': (0x63, 0x14, 0x08, 0x14, 0x63),
    'Y': (0x03, 0x04, 0x78, 0x04, 0x03),
    'Z': (0x61, 0x51, 0x49, 0x45, 0x43),
    '[': (0x00, 0x00, 0x7F, 0x41, 0x41),
    '\\': (0x02, 0x04, 0x08, 0x10, 0x20),
    ']': (0x41, 0x41, 0x7F, 0x00, 0x00),
    '^': (0x04, 0x02, 0x01, 0x02, 0x04),
    '_': (0x40, 0x40, 0x40, 0x40, 0x40),
    '`': (0x00, 0x01, 0x02, 0x04, 0x00),
    'a': (0x20, 0x54, 0x54, 0x54, 0x78),
    'b': (0x7F, 0x48, 0x44, 0x44, 0x38),
    'c': (0x38, 0x44, 0x44, 0x44, 0x20),
    'd': (0x38, 0x44, 0x44, 0x48, 0x7F),
    'e': (0x38, 0x54, 0x54, 0x54, 0x18),
    'f': (0x08, 0x7E, 0x09, 0x01, 0x02),
    'g': (0x0C, 0x52, 0x52, 0x52, 0x3E),
    'h': (0x7F, 0x08, 0x04, 0x04, 0x78),
    'i': (0x00, 0x44, 0x7D, 0x40, 0x00),
    'j': (0x20, 0x40, 0x44, 0x3D, 0x00),
    'k': (0x7F, 0x10, 0x28, 0x44, 0x00),
    'l': (0x00, 0x41, 0x7F, 0x40, 0x00),
    'm': (0x7C, 0x04, 0x18, 0x04, 0x78),
    'n': (0x7C, 0x08, 0x04, 0x04, 0x78),
    'o': (0x38, 0x44, 0x44, 0x44, 0x38),
    'p': (0x7C, 0x14, 0x14, 0x14, 0x08),
    'q': (0x08, 0x14, 0x14, 0x18, 0x7C),
    'r': (0x7C, 0x08, 0x04, 0x04, 0x08),
    's': (0x48, 0x54, 0x54, 0x54, 0x20),
    't': (0x04, 0x3F, 0x44, 0x40, 0x20),
    'u': (0x3C, 0x40, 0x40, 0x20, 0x7C),
    'v': (0x1C, 0x20, 0x40, 0x20, 0x1C),
    'w': (0x3C, 0x40, 0x30, 0x40, 0x3C),
    'x': (0x44, 0x28, 0x10, 0x28, 0x44),
    'y': (0x0C, 0x50, 0x50, 0x50, 0x3C),
    'z': (0x44, 0x64, 0x54, 0x4C, 0x44),
    '{': (0x00, 0x08, 0x36, 0x41, 0x00),
    '|': (0x00, 0x00, 0x7F, 0x00, 0x00),
    '}': (0x00, 0x41, 0x36, 0x08, 0x00),
    '~': (0x08, 0x08, 0x2A, 0x1C, 0x08),
}

# acentos comunes -> letra base (u8g2 *_tr tampoco los trae)
_FOLD = {
    'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u', 'ñ': 'n',
    'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U', 'Ñ': 'N',
    '¿': '?', '¡': '!', '°': 'o',
}

GLYPH_W = 5
GLYPH_H = 7      # filas 0..6, baseline = fila 6


def glyph(ch):
    """Devuelve las 5 columnas del caracter (o un cuadro si no existe)."""
    if ch in FONT5X7:
        return FONT5X7[ch]
    ch = _FOLD.get(ch)
    if ch and ch in FONT5X7:
        return FONT5X7[ch]
    return (0x7F, 0x41, 0x41, 0x41, 0x7F)      # cuadro = glifo faltante


# ============================================================
#  Registro de fuentes u8g2
#    name: (advance_px, cap_height_px, bold, descripcion)
#    advance = ancho total por caracter incluyendo el espaciado
#    cap_height = alto del glifo desde la baseline hacia arriba
# ============================================================

U8G2_FONTS = [
    # (nombre u8g2, avance, alto, bold, nota)
    ("u8g2_font_4x6_tr",        4,  5, False, "mono 4x6 - la mas chica legible"),
    ("u8g2_font_5x7_tr",        5,  7, False, "mono 5x7 - muy comun en proyectos ESP32/Arduino"),
    ("u8g2_font_5x8_tr",        5,  7, False, "mono 5x8"),
    ("u8g2_font_6x10_tr",       6,  7, False, "mono 6x10 - buena para titulos"),
    ("u8g2_font_6x12_tr",       6,  8, False, "mono 6x12"),
    ("u8g2_font_6x13_tr",       6,  9, False, "mono 6x13"),
    ("u8g2_font_6x13B_tr",      6,  9, True,  "mono 6x13 negrita"),
    ("u8g2_font_7x13_tr",       7,  9, False, "mono 7x13"),
    ("u8g2_font_7x13B_tr",      7,  9, True,  "mono 7x13 negrita"),
    ("u8g2_font_8x13_tr",       8,  9, False, "mono 8x13"),
    ("u8g2_font_8x13B_tr",      8,  9, True,  "mono 8x13 negrita"),
    ("u8g2_font_9x15_tr",       9, 11, False, "mono 9x15"),
    ("u8g2_font_10x20_tr",     10, 14, False, "mono 10x20"),
    ("u8g2_font_ncenB08_tr",    6,  8, True,  "New Century negrita 8"),
    ("u8g2_font_ncenB10_tr",    8, 10, True,  "New Century negrita 10 - buena para splash screens"),
    ("u8g2_font_ncenB12_tr",    9, 12, True,  "New Century negrita 12"),
    ("u8g2_font_ncenB14_tr",   11, 14, True,  "New Century negrita 14"),
    ("u8g2_font_ncenR10_tr",    7, 10, False, "New Century regular 10"),
    ("u8g2_font_helvB08_tr",    6,  8, True,  "Helvetica negrita 8"),
    ("u8g2_font_helvB10_tr",    7, 10, True,  "Helvetica negrita 10"),
    ("u8g2_font_helvR08_tr",    5,  8, False, "Helvetica regular 8"),
    ("u8g2_font_helvR10_tr",    7, 10, False, "Helvetica regular 10"),
    ("u8g2_font_profont11_tr",  6,  8, False, "ProFont 11"),
    ("u8g2_font_profont12_tr",  6,  9, False, "ProFont 12"),
    ("u8g2_font_profont15_tr",  7, 11, False, "ProFont 15"),
    ("u8g2_font_profont22_tr", 11, 15, False, "ProFont 22 - numeros grandes"),
    ("u8g2_font_logisoso16_tn", 11, 16, True, "Logisoso 16 (solo digitos)"),
    ("u8g2_font_logisoso20_tn", 14, 20, True, "Logisoso 20 (solo digitos)"),
    ("u8g2_font_logisoso24_tn", 16, 24, True, "Logisoso 24 (solo digitos)"),
    ("u8g2_font_open_iconic_all_1x_t",  8,  8, False, "iconos 8x8"),
    ("u8g2_font_open_iconic_all_2x_t", 16, 16, False, "iconos 16x16"),
]

FONT_BY_NAME = {f[0]: f for f in U8G2_FONTS}
DEFAULT_FONT = "u8g2_font_6x10_tr"


def font_metrics(name):
    """(advance, cap_height, bold)"""
    f = FONT_BY_NAME.get(name)
    if not f:
        return (6, 7, False)
    return (f[1], f[2], f[3])


def text_width(text, font_name):
    adv, _, _ = font_metrics(font_name)
    return len(text) * adv


def text_height(font_name):
    _, cap, _ = font_metrics(font_name)
    return cap


# ============================================================
#  Render de texto a pixeles
# ============================================================

def render_text_pixels(text, font_name=DEFAULT_FONT, x=0, y=0):
    """
    Genera las coordenadas (px, py) encendidas para dibujar `text`
    con la baseline en `y` y el borde izquierdo en `x`
    (misma convencion que u8g2.drawStr).
    """
    adv, cap, bold = font_metrics(font_name)
    # las fuentes chicas de u8g2 no dejan espacio entre glifos;
    # las grandes si, asi que el glifo ocupa una columna menos.
    gw = adv if adv <= 5 else adv - 1
    gh = cap
    pts = set()

    cx = x
    for ch in text:
        cols = glyph(ch)
        # escala nearest-neighbor de la celda 5x7 a gw x gh
        for tx in range(gw):
            sx = int(tx * GLYPH_W / float(gw))
            if sx >= GLYPH_W:
                sx = GLYPH_W - 1
            col = cols[sx]
            for ty in range(gh):
                sy = int(ty * GLYPH_H / float(gh))
                if sy >= GLYPH_H:
                    sy = GLYPH_H - 1
                if (col >> sy) & 1:
                    px = cx + tx
                    py = y - (gh - 1) + ty
                    pts.add((px, py))
                    if bold:
                        pts.add((px + 1, py))
        cx += adv
    return pts


def draw_text_on_bitmap(bitmap, text, x, y, font_name=DEFAULT_FONT, value=1):
    for px, py in render_text_pixels(text, font_name, x, y):
        bitmap.set(px, py, value)
    return bitmap
