# -*- coding: utf-8 -*-
"""
ms_core.py - Modelo de bitmap 1-bit, parser/escritor de arreglos C (XBM)
             y utilidades de importacion de imagenes.

Formato XBM (el que usa u8g2.drawXBMP):
    - horizontal, LSB first
    - cada fila ocupa ceil(W/8) bytes
    - pixel(x, y) = (data[y*bpr + x//8] >> (x%8)) & 1

u8g2 Studio - MIT License
"""

import os
import re
import json

# ============================================================
#  Bitmap 1 bit
# ============================================================


class Bitmap(object):
    """Imagen monocromatica empaquetada en formato XBM (LSB first)."""

    def __init__(self, width=128, height=64, data=None):
        self.width = int(width)
        self.height = int(height)
        if data is None:
            self.data = bytearray(self.bytes_per_row * self.height)
        else:
            need = self.bytes_per_row * self.height
            d = bytearray(data[:need])
            if len(d) < need:
                d.extend(b"\x00" * (need - len(d)))
            self.data = d

    # ---- geometria ----
    @property
    def bytes_per_row(self):
        return (self.width + 7) // 8

    def in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    # ---- acceso a pixeles ----
    def get(self, x, y):
        if not self.in_bounds(x, y):
            return 0
        return (self.data[y * self.bytes_per_row + (x >> 3)] >> (x & 7)) & 1

    def set(self, x, y, value):
        if not self.in_bounds(x, y):
            return
        i = y * self.bytes_per_row + (x >> 3)
        m = 1 << (x & 7)
        if value:
            self.data[i] |= m
        else:
            self.data[i] &= 0xFF ^ m

    def toggle(self, x, y):
        self.set(x, y, 0 if self.get(x, y) else 1)

    # ---- copia / estado ----
    def clone(self):
        return Bitmap(self.width, self.height, bytearray(self.data))

    def snapshot(self):
        return (self.width, self.height, bytes(self.data))

    def restore(self, snap):
        self.width, self.height, d = snap
        self.data = bytearray(d)

    def resize(self, width, height, anchor="topleft"):
        """Cambia el lienzo conservando el arte (recorta o rellena)."""
        nb = Bitmap(width, height)
        ox = oy = 0
        if anchor == "center":
            ox = (width - self.width) // 2
            oy = (height - self.height) // 2
        for y in range(self.height):
            for x in range(self.width):
                if self.get(x, y):
                    nb.set(x + ox, y + oy, 1)
        self.width, self.height, self.data = nb.width, nb.height, nb.data

    # ---- operaciones globales ----
    def clear(self, value=0):
        fill = 0xFF if value else 0x00
        self.data = bytearray([fill] * (self.bytes_per_row * self.height))
        if value:
            self._mask_tail()

    def _mask_tail(self):
        """Pone en 0 los bits de relleno del final de cada fila."""
        extra = self.bytes_per_row * 8 - self.width
        if extra <= 0:
            return
        mask = (0xFF >> extra) & 0xFF
        for y in range(self.height):
            i = y * self.bytes_per_row + self.bytes_per_row - 1
            self.data[i] &= mask

    def invert(self):
        for i in range(len(self.data)):
            self.data[i] ^= 0xFF
        self._mask_tail()

    def flip_h(self):
        out = Bitmap(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                if self.get(x, y):
                    out.set(self.width - 1 - x, y, 1)
        self.data = out.data

    def flip_v(self):
        out = Bitmap(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                if self.get(x, y):
                    out.set(x, self.height - 1 - y, 1)
        self.data = out.data

    def shift(self, dx, dy, wrap=False):
        out = Bitmap(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                if not self.get(x, y):
                    continue
                nx, ny = x + dx, y + dy
                if wrap:
                    nx %= self.width
                    ny %= self.height
                out.set(nx, ny, 1)
        self.data = out.data

    # ---- primitivas de dibujo ----
    def draw_line(self, x0, y0, x1, y1, v=1):
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set(x0, y0, v)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def draw_rect(self, x0, y0, x1, y1, v=1, fill=False):
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        if fill:
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    self.set(x, y, v)
        else:
            for x in range(x0, x1 + 1):
                self.set(x, y0, v)
                self.set(x, y1, v)
            for y in range(y0, y1 + 1):
                self.set(x0, y, v)
                self.set(x1, y, v)

    def draw_ellipse(self, x0, y0, x1, y1, v=1, fill=False):
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        a = (x1 - x0) / 2.0
        b = (y1 - y0) / 2.0
        cx = x0 + a
        cy = y0 + b
        if a <= 0 or b <= 0:
            self.draw_line(x0, y0, x1, y1, v)
            return
        if fill:
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    if ((x - cx) / a) ** 2 + ((y - cy) / b) ** 2 <= 1.0:
                        self.set(x, y, v)
        else:
            steps = int(max(a, b) * 8) + 8
            prev = None
            import math
            for i in range(steps + 1):
                t = 2 * math.pi * i / steps
                px = int(round(cx + a * math.cos(t)))
                py = int(round(cy + b * math.sin(t)))
                if prev is not None:
                    self.draw_line(prev[0], prev[1], px, py, v)
                prev = (px, py)

    def flood_fill(self, x, y, v=1):
        if not self.in_bounds(x, y):
            return
        target = self.get(x, y)
        if target == v:
            return
        stack = [(x, y)]
        seen = set()
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in seen or not self.in_bounds(cx, cy):
                continue
            if self.get(cx, cy) != target:
                continue
            seen.add((cx, cy))
            self.set(cx, cy, v)
            stack.append((cx + 1, cy))
            stack.append((cx - 1, cy))
            stack.append((cx, cy + 1))
            stack.append((cx, cy - 1))

    def blit(self, other, ox, oy, mode="or"):
        for y in range(other.height):
            for x in range(other.width):
                p = other.get(x, y)
                if mode == "or":
                    if p:
                        self.set(x + ox, y + oy, 1)
                elif mode == "set":
                    self.set(x + ox, y + oy, p)
                elif mode == "xor":
                    if p:
                        self.toggle(x + ox, y + oy)

    def sub(self, x0, y0, w, h):
        out = Bitmap(w, h)
        for y in range(h):
            for x in range(w):
                if self.get(x0 + x, y0 + y):
                    out.set(x, y, 1)
        return out

    # ---- serializacion ----
    def to_c_array(self, name="bitmap_bits", per_line=16, progmem=True,
                   indent="  ", static=True):
        bpr = self.bytes_per_row
        lines = []
        for i in range(0, len(self.data), per_line):
            chunk = self.data[i:i + per_line]
            lines.append(indent + ", ".join("0x%02x" % b for b in chunk))
        head = "%sconst unsigned char %s[]%s = {" % (
            "static " if static else "",
            name,
            " PROGMEM" if progmem else "",
        )
        return head + "\n" + ",\n".join(lines) + "\n};"

    def to_bytes_body(self, per_line=16, indent="  "):
        """Solo el cuerpo (lo que va entre llaves), sin head ni '};'."""
        lines = []
        for i in range(0, len(self.data), per_line):
            chunk = self.data[i:i + per_line]
            lines.append(indent + ", ".join("0x%02x" % b for b in chunk))
        return "\n" + ",\n".join(lines) + "\n"

    def to_rows_text(self):
        """Representacion ASCII para depurar ('#' encendido, '.' apagado)."""
        out = []
        for y in range(self.height):
            out.append("".join("#" if self.get(x, y) else "." for x in range(self.width)))
        return "\n".join(out)


# ============================================================
#  Parser de arreglos C
# ============================================================

# Acepta las formas reales que salen de image2cpp, GIMP, LCD Assistant,
# Adafruit_GFX y u8g2, en .h / .hpp / .c / .cpp / .ino:
#
#   static const unsigned char bitmap_bits[] PROGMEM = { ... };
#   const uint8_t PROGMEM logo[] = { ... };          <- PROGMEM antes del nombre
#   static const unsigned char PROGMEM frames[3][1024] = {{..},{..},{..}};
#   const unsigned char myBitmap [] PROGMEM = { ... };
#   uint8_t buf[1024] __attribute__((aligned(4))) = { ... };
#
_QUALS = r"(?:static|const|extern|PROGMEM|U8X8_PROGMEM|U8G2_PROGMEM|inline|constexpr)"
_TYPES = r"(?:unsigned\s+char|signed\s+char|unsigned\s+int8_t|uint8_t|int8_t|char|u8|byte|BYTE)"

_DECL_RE = re.compile(r"""
    (?P<decl>
        (?:%(q)s\s+)*                       # static / const / PROGMEM ...
        %(t)s                               # el tipo
        (?:\s+%(q)s)*                       # mas calificadores tras el tipo
        \s+
        (?P<name>[A-Za-z_]\w*)              # nombre
        \s*
        (?:\[[^\];{]*\]\s*)+                # una o mas dimensiones
        (?:(?:%(q)s|__attribute__\s*\(\((?:[^()]|\([^()]*\))*\)\))\s*)*
        =\s*
    )
    \{
""" % {"q": _QUALS, "t": _TYPES}, re.VERBOSE)


def strip_comments(s):
    """Quita // y /* */ sin tocar la longitud del texto (los cambia por espacios)."""
    out = list(s)
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == '"' or c == "'":
            q = c
            i += 1
            while i < n:
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if c == "/" and i + 1 < n:
            if s[i + 1] == "/":
                j = s.find("\n", i)
                j = n if j == -1 else j
                for k in range(i, j):
                    out[k] = " "
                i = j
                continue
            if s[i + 1] == "*":
                j = s.find("*/", i + 2)
                j = n if j == -1 else j + 2
                for k in range(i, j):
                    if out[k] != "\n":
                        out[k] = " "
                i = j
                continue
        i += 1
    return "".join(out)


def _match_brace(text, open_idx):
    """Indice de la '}' que cierra la '{' en open_idx (ignora comentarios)."""
    clean = strip_comments(text)
    depth = 0
    i = open_idx
    n = len(clean)
    while i < n:
        c = clean[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _split_frames(text, body_start, body_end):
    """
    Si el cuerpo es {{...},{...}} devuelve los spans de cada sub-bloque.
    Si es plano devuelve [(body_start, body_end)].
    """
    clean = strip_comments(text)
    frames = []
    i = body_start
    while i < body_end:
        if clean[i] == "{":
            j = _match_brace(text, i)
            if j == -1 or j > body_end:
                break
            frames.append((i + 1, j))
            i = j + 1
        else:
            i += 1
    if not frames:
        return [(body_start, body_end)]
    return frames


def find_arrays(text):
    """
    Devuelve [(nombre, n_bytes, n_frames, decl_span)] de cada arreglo de bytes.
    n_bytes es el tamano de UN frame (o del arreglo entero si es plano).
    """
    out = []
    for m in _DECL_RE.finditer(strip_comments(text)):
        open_idx = m.end() - 1
        close_idx = _match_brace(text, open_idx)
        if close_idx == -1:
            continue
        frames = _split_frames(text, open_idx + 1, close_idx)
        n = len(parse_bytes(text[frames[0][0]:frames[0][1]]))
        if n == 0:
            continue
        out.append((m.group("name"), n, len(frames), (m.start(), close_idx + 1)))
    return out


def locate_array(text, name, frame=0):
    """Devuelve (body_start, body_end, n_frames) del arreglo `name`."""
    for m in _DECL_RE.finditer(strip_comments(text)):
        if m.group("name") != name:
            continue
        open_idx = m.end() - 1
        close_idx = _match_brace(text, open_idx)
        if close_idx == -1:
            continue
        frames = _split_frames(text, open_idx + 1, close_idx)
        if frame >= len(frames):
            raise ValueError("'%s' tiene %d frame(s); pediste el %d"
                             % (name, len(frames), frame))
        s, e = frames[frame]
        return s, e, len(frames)
    return None


def parse_array_ref(ref):
    """'frames[2]' -> ('frames', 2)   |   'logo' -> ('logo', 0)"""
    ref = (ref or "").strip()
    m = re.match(r"^([A-Za-z_]\w*)\s*(?:\[\s*(\d+)\s*\])?$", ref)
    if not m:
        return ref, 0
    return m.group(1), int(m.group(2) or 0)


def parse_bytes(body):
    """Extrae los enteros de un cuerpo de arreglo C, ignorando comentarios."""
    body = strip_comments(body)
    vals = []
    for tok in re.findall(r"0[xX][0-9a-fA-F]+|0[bB][01]+|\d+", body):
        try:
            if tok[:2].lower() == "0x":
                vals.append(int(tok, 16) & 0xFF)
            elif tok[:2].lower() == "0b":
                vals.append(int(tok, 2) & 0xFF)
            else:
                vals.append(int(tok) & 0xFF)
        except ValueError:
            pass
    return vals


def find_define(text, name):
    m = re.search(r"#define\s+%s\s+(\d+)" % re.escape(name), text)
    return int(m.group(1)) if m else None


def replace_define(text, name, value):
    rx = re.compile(r"(#define\s+%s\s+)(\d+)" % re.escape(name))
    if rx.search(text):
        return rx.sub(lambda m: m.group(1) + str(value), text, count=1)
    return text


def load_bitmap_from_header(path, array_name=None, width=None, height=None):
    """
    Lee cualquier archivo C/C++ (.h .hpp .c .cpp .ino) y devuelve
    (Bitmap, nombre_arreglo, info).

    array_name acepta 'logo' o 'frames[2]' para hojas de sprites.
    Si no se dan width/height intenta con los #define *_W / *_H,
    y si no, asume ancho 128.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    arrays = find_arrays(text)
    if not arrays:
        raise ValueError("No se encontro ningun arreglo de bytes en %s"
                         % os.path.basename(path))

    frame = 0
    if array_name:
        array_name, frame = parse_array_ref(array_name)
        cand = [a for a in arrays if a[0] == array_name]
        if not cand:
            raise ValueError(
                "No existe el arreglo '%s'.\nEn el archivo hay: %s"
                % (array_name, ", ".join(a[0] for a in arrays)))
        name, nbytes = cand[0][0], cand[0][1]
    else:
        # el mas grande suele ser el arte
        best = max(arrays, key=lambda a: a[1])
        name, nbytes = best[0], best[1]

    if width is None:
        for cand_name in (name.replace("_bits", "").upper() + "_W", "EASTER_W",
                          name.upper() + "_W", "IMG_W", "LOGO_W"):
            v = find_define(text, cand_name)
            if v:
                width = v
                break
    if height is None:
        for cand_name in (name.replace("_bits", "").upper() + "_H", "EASTER_H",
                          name.upper() + "_H", "IMG_H", "LOGO_H"):
            v = find_define(text, cand_name)
            if v:
                height = v
                break

    if not width:
        width = 128
    if not height:
        bpr = (width + 7) // 8
        height = max(1, nbytes // bpr)

    loc = locate_array(text, name, frame)
    if loc is None:
        raise ValueError("No pude localizar el arreglo '%s'" % name)
    s, e, nframes = loc
    data = parse_bytes(text[s:e])

    bm = Bitmap(width, height, bytearray(data))
    ref = name if nframes == 1 else "%s[%d]" % (name, frame)
    info = {"path": path, "array": name, "ref": ref, "frame": frame,
            "frames": nframes, "bytes": nbytes,
            "arrays": [(a[0], a[1], a[2]) for a in arrays]}
    return bm, ref, info


def save_bitmap_to_header(path, bitmap, array_name="bitmap_bits",
                          w_define=None, h_define=None,
                          per_line=16, create_if_missing=True):
    """
    Reescribe SOLO los bytes del arreglo dentro del archivo (.h .cpp .ino),
    dejando comentarios, defines y todo lo demas intacto.
    No crea copias .bak: la red de seguridad es tu control de versiones.

    array_name acepta 'logo' o 'frames[2]' para hojas de sprites.
    """
    array_name, frame = parse_array_ref(array_name)
    exists = os.path.exists(path)
    if exists:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        if not create_if_missing:
            raise IOError("No existe %s" % path)
        text = _new_header_template(array_name, bitmap.width, bitmap.height)

    # defines de tamano
    if w_define:
        text = replace_define(text, w_define, bitmap.width)
    if h_define:
        text = replace_define(text, h_define, bitmap.height)

    body = bitmap.to_bytes_body(per_line=per_line)
    loc = locate_array(text, array_name, frame)
    if loc is not None:
        s, e, _ = loc
        text = text[:s] + body + text[e:]
    else:
        text = text.rstrip() + "\n\n" + bitmap.to_c_array(array_name, per_line) + "\n"

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def _new_header_template(array_name, w, h):
    base = array_name.replace("_bits", "").upper()
    return (
        "#pragma once\n"
        "#include <Arduino.h>\n\n"
        "// Generado por u8g2 Studio\n"
        "#define %s_W %d\n"
        "#define %s_H %d\n\n"
        "static const unsigned char %s[] PROGMEM = {\n};\n" % (base, w, base, h, array_name)
    )


# ============================================================
#  Insercion de codigo entre marcadores
# ============================================================

# ============================================================
#  Importacion de imagenes (Pillow opcional)
# ============================================================

try:
    from PIL import Image
    HAS_PIL = True
except Exception:      # pragma: no cover
    Image = None
    HAS_PIL = False


def image_to_bitmap(path, width=128, height=64, threshold=128,
                    dither=False, invert=False, fit="contain"):
    """
    Convierte PNG/JPG/BMP/GIF a Bitmap 1-bit.
      fit: 'contain' (mantiene proporcion, centra) | 'stretch' | 'cover'
      dither: Floyd-Steinberg (ignora threshold)
    """
    if not HAS_PIL:
        raise RuntimeError("Se necesita Pillow: pip install Pillow")

    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = im.convert("RGBA")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im = im.convert("L")

    if fit == "stretch":
        im = im.resize((width, height), Image.LANCZOS)
    else:
        sw, sh = im.size
        if fit == "cover":
            scale = max(width / float(sw), height / float(sh))
        else:
            scale = min(width / float(sw), height / float(sh))
        nw = max(1, int(round(sw * scale)))
        nh = max(1, int(round(sh * scale)))
        im = im.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("L", (width, height), 255)
        canvas.paste(im, ((width - nw) // 2, (height - nh) // 2))
        im = canvas

    if dither:
        im = im.convert("1")           # Floyd-Steinberg por defecto
    else:
        im = im.point(lambda p: 0 if p < threshold else 255, mode="1")

    bm = Bitmap(width, height)
    px = im.load()
    for y in range(height):
        for x in range(width):
            on = 0 if px[x, y] else 1        # negro = pixel encendido
            if invert:
                on = 1 - on
            if on:
                bm.set(x, y, 1)
    return bm


def bitmap_to_qimage(bitmap, bg_rgb, fg_rgb):
    """Convierte el Bitmap 1-bit a un QImage de una sola pasada.

    Evita el patron 'for y: for x: img.setPixel(...)' -- cada llamada a
    setPixel tiene overhead de Python + validacion de limites, y con un
    lienzo de 128x64 son 8192 llamadas por repintado. Al arrastrar un
    elemento eso se repite en cada mouseMoveEvent y es lo que se siente
    'pesado'/lento en el editor.

    En vez de eso, el bitmap YA esta empacado 1bpp LSB-first por fila
    (formato XBM), que es exactamente QImage.Format_MonoLSB. Solo hay que
    alinear cada fila a 4 bytes (lo que exige QImage) y dejar que Qt haga
    la conversion a RGB de un tiron con la tabla de colores.
    """
    from PyQt5.QtGui import QImage
    w, h = bitmap.width, bitmap.height
    bpr = bitmap.bytes_per_row
    stride = ((w + 31) // 32) * 4
    if stride == bpr:
        buf = bytes(bitmap.data)
    else:
        tmp = bytearray(stride * h)
        for y in range(h):
            o = y * bpr
            tmp[y * stride: y * stride + bpr] = bitmap.data[o:o + bpr]
        buf = bytes(tmp)
    img = QImage(buf, w, h, stride, QImage.Format_MonoLSB)
    img.setColorTable([bg_rgb & 0xFFFFFF, fg_rgb & 0xFFFFFF])
    # convertToFormat copia los datos a un buffer propio de Qt (RGB32);
    # a partir de aqui 'buf' puede salir de scope sin problema.
    return img.convertToFormat(QImage.Format_RGB32)


def bitmap_to_png(bitmap, path, scale=1, invert=False):
    if not HAS_PIL:
        raise RuntimeError("Se necesita Pillow: pip install Pillow")
    im = Image.new("1", (bitmap.width, bitmap.height), 0)
    px = im.load()
    for y in range(bitmap.height):
        for x in range(bitmap.width):
            v = bitmap.get(x, y)
            if invert:
                v = 1 - v
            px[x, y] = 1 if v else 0
    if scale > 1:
        im = im.resize((bitmap.width * scale, bitmap.height * scale), Image.NEAREST)
    im.save(path)
    return path


# ============================================================
#  Proyecto (JSON)
# ============================================================

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
