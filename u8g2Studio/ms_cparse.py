# -*- coding: utf-8 -*-
"""
ms_cparse.py - Lector del codigo de dibujo que YA existe.

No genera codigo: lee tus .ino/.cpp/.h, interpreta las funciones que
dibujan (u8g2/U8x8/Adafruit_GFX) y devuelve una lista de operaciones de
dibujo, cada una con el TRAMO EXACTO del archivo de donde salio cada
argumento. Eso es lo que permite arrastrar un texto en el canvas y que
se reescriba solo el numero dentro de `drawStr(2, 9, "Hola")`,
dejando bucles, snprintf, comentarios y todo lo demas intactos.

Cubre: literales, #define, enum, arreglos de strings, variables locales,
aritmetica, ?:, if/else, for/while (desenrollados), snprintf, llamadas a
funciones del propio proyecto (se inlinean) y getStrWidth (se calcula de
verdad con las metricas de la fuente).

u8g2 Studio - MIT License
"""

import re

import ms_fonts as fonts


# ============================================================
#  Utilidades de texto que preservan offsets
# ============================================================

def blank_comments(s):
    """Sustituye comentarios por espacios sin mover ningun offset."""
    out = list(s)
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in '"\'':
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


def blank_preproc(s):
    """Sustituye lineas de preprocesador por espacios (offsets intactos)."""
    out = list(s)
    for m in re.finditer(r"^[ \t]*#.*(?:\\\n.*)*", s, re.MULTILINE):
        for k in range(m.start(), m.end()):
            if out[k] != "\n":
                out[k] = " "
    return "".join(out)


def match_brace(text, open_idx):
    """Indice de la '}' que cierra la '{' de open_idx. text ya sin comentarios."""
    depth = 0
    i, n = open_idx, len(text)
    while i < n:
        c = text[i]
        if c in '"\'':
            q = c
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == q:
                    break
                i += 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# ============================================================
#  Tokenizer
# ============================================================

class Tok(object):
    __slots__ = ("kind", "val", "pos", "end")

    def __init__(self, kind, val, pos, end):
        self.kind = kind      # num str chr id op eof
        self.val = val
        self.pos = pos
        self.end = end

    def __repr__(self):
        return "Tok(%s,%r)" % (self.kind, self.val)


_PUNCT = [
    ">>=", "<<=", "...",
    "->", "++", "--", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||",
    "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "::",
    "+", "-", "*", "/", "%", "=", "<", ">", "!", "~", "&", "|", "^",
    "?", ":", ";", ",", ".", "(", ")", "[", "]", "{", "}",
]

_NUM_RE = re.compile(r"0[xX][0-9a-fA-F]+[uUlL]*|0[bB][01]+[uUlL]*|\d+\.\d*[fF]?|\.\d+[fF]?|\d+[uUlLfF]*")
_ID_RE = re.compile(r"[A-Za-z_]\w*")


def tokenize(text, start=0, end=None):
    """text debe venir ya sin comentarios ni preprocesador."""
    if end is None:
        end = len(text)
    toks = []
    i = start
    while i < end:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < end and text[j] != '"':
                if text[j] == "\\" and j + 1 < end:
                    esc = text[j + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r", "0": "\0",
                                "\\": "\\", '"': '"', "'": "'"}.get(esc, esc))
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            toks.append(Tok("str", "".join(buf), i, min(j + 1, end)))
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            v = 0
            if j < end and text[j] == "\\":
                v = ord({"n": "\n", "t": "\t", "0": "\0", "r": "\r"}.get(text[j + 1], text[j + 1]))
                j += 2
            elif j < end:
                v = ord(text[j])
                j += 1
            while j < end and text[j] != "'":
                j += 1
            toks.append(Tok("num", v, i, min(j + 1, end)))
            i = j + 1
            continue
        m = _NUM_RE.match(text, i)
        if m and (c.isdigit() or (c == "." and i + 1 < end and text[i + 1].isdigit())):
            raw = m.group(0)
            body = raw.rstrip("uUlLfF")
            try:
                if body[:2].lower() == "0x":
                    val = int(body, 16)
                elif body[:2].lower() == "0b":
                    val = int(body, 2)
                elif "." in body:
                    val = float(body)
                elif len(body) > 1 and body[0] == "0":
                    val = int(body, 8)
                else:
                    val = int(body)
            except ValueError:
                val = 0
            toks.append(Tok("num", val, i, m.end()))
            i = m.end()
            continue
        m = _ID_RE.match(text, i)
        if m:
            toks.append(Tok("id", m.group(0), i, m.end()))
            i = m.end()
            continue
        for p in _PUNCT:
            if text.startswith(p, i):
                toks.append(Tok("op", p, i, i + len(p)))
                i += len(p)
                break
        else:
            i += 1
    toks.append(Tok("eof", None, end, end))
    return toks


# ============================================================
#  AST de expresiones
#    ('num', v, pos, end)
#    ('str', v, pos, end)
#    ('id', name, pos, end)
#    ('un', op, x, pos, end)
#    ('bin', op, l, r, op_pos, pos, end)
#    ('cond', c, a, b, pos, end)
#    ('call', callee, args, pos, end)
#    ('member', obj, name, pos, end)
#    ('index', arr, idx, pos, end)
#    ('cast', x, pos, end)
# ============================================================

class ParseError(Exception):
    pass


_BIN_PREC = [
    ("||",), ("&&",), ("|",), ("^",), ("&",),
    ("==", "!="), ("<", ">", "<=", ">="), ("<<", ">>"),
    ("+", "-"), ("*", "/", "%"),
]

_TYPE_WORDS = {
    "int", "char", "unsigned", "signed", "long", "short", "float", "double",
    "void", "bool", "size_t", "const", "static", "volatile", "auto", "register",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t", "int8_t", "int16_t",
    "int32_t", "int64_t", "u8g2_uint_t", "byte", "word", "String", "boolean",
}


class Parser(object):

    def __init__(self, toks):
        self.t = toks
        self.i = 0

    # ---- helpers ----
    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else self.t[-1]

    def at(self, val):
        t = self.peek()
        return t.kind == "op" and t.val == val

    def at_id(self, val):
        t = self.peek()
        return t.kind == "id" and t.val == val

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def expect(self, val):
        if not self.at(val):
            raise ParseError("esperaba %r, hay %r" % (val, self.peek().val))
        return self.next()

    def accept(self, val):
        if self.at(val):
            self.next()
            return True
        return False

    # ---- expresiones ----
    def parse_expr(self):
        return self.parse_assign()

    def parse_assign(self):
        left = self.parse_cond()
        t = self.peek()
        if t.kind == "op" and t.val in ("=", "+=", "-=", "*=", "/=", "%=",
                                        "&=", "|=", "^=", "<<=", ">>="):
            op_pos = t.pos
            self.next()
            right = self.parse_assign()
            return ("assign", t.val, left, right, op_pos, left[-2], right[-1])
        return left

    def parse_cond(self):
        c = self.parse_bin(0)
        if self.at("?"):
            self.next()
            a = self.parse_assign()
            self.expect(":")
            b = self.parse_cond()
            return ("cond", c, a, b, c[-2], b[-1])
        return c

    def parse_bin(self, level):
        if level >= len(_BIN_PREC):
            return self.parse_unary()
        left = self.parse_bin(level + 1)
        while True:
            t = self.peek()
            if t.kind == "op" and t.val in _BIN_PREC[level]:
                # no confundir '>' de plantillas: aqui no hay plantillas
                self.next()
                right = self.parse_bin(level + 1)
                left = ("bin", t.val, left, right, t.pos, left[-2], right[-1])
            else:
                return left

    def parse_unary(self):
        t = self.peek()
        if t.kind == "op" and t.val in ("-", "+", "!", "~", "*", "&", "++", "--"):
            self.next()
            x = self.parse_unary()
            return ("un", t.val, x, t.pos, x[-1])
        # cast:  (int)x   (uint8_t)(...)
        if t.kind == "op" and t.val == "(":
            save = self.i
            self.next()
            if self.peek().kind == "id" and self.peek().val in _TYPE_WORDS:
                depth = 1
                while depth and self.peek().kind != "eof":
                    n = self.next()
                    if n.kind == "op" and n.val == "(":
                        depth += 1
                    elif n.kind == "op" and n.val == ")":
                        depth -= 1
                if self.peek().kind != "eof" and not (
                        self.peek().kind == "op" and self.peek().val in (")", ",", ";")):
                    x = self.parse_unary()
                    return ("cast", x, t.pos, x[-1])
            self.i = save
        return self.parse_postfix()

    def parse_postfix(self):
        x = self.parse_primary()
        while True:
            t = self.peek()
            if t.kind == "op" and t.val == "(":
                self.next()
                args = []
                if not self.at(")"):
                    while True:
                        args.append(self.parse_assign())
                        if not self.accept(","):
                            break
                endt = self.peek()
                self.expect(")")
                x = ("call", x, args, x[-2], endt.end)
            elif t.kind == "op" and t.val == "[":
                self.next()
                idx = self.parse_expr()
                endt = self.peek()
                self.expect("]")
                x = ("index", x, idx, x[-2], endt.end)
            elif t.kind == "op" and t.val in (".", "->"):
                self.next()
                nm = self.next()
                x = ("member", x, nm.val, x[-2], nm.end)
            elif t.kind == "op" and t.val in ("++", "--"):
                self.next()
                x = ("un", "post" + t.val, x, x[-2], t.end)
            else:
                return x

    def parse_primary(self):
        t = self.peek()
        if t.kind == "num":
            self.next()
            return ("num", t.val, t.pos, t.end)
        if t.kind == "str":
            self.next()
            parts = [t.val]
            end = t.end
            while self.peek().kind == "str":     # concatenacion "a" "b"
                nt = self.next()
                parts.append(nt.val)
                end = nt.end
            return ("str", "".join(parts), t.pos, end)
        if t.kind == "id":
            self.next()
            return ("id", t.val, t.pos, t.end)
        if t.kind == "op" and t.val == "(":
            self.next()
            x = self.parse_expr()
            self.expect(")")
            return x
        if t.kind == "op" and t.val == "{":       # initializer list
            self.next()
            items = []
            while not self.at("}") and self.peek().kind != "eof":
                items.append(self.parse_assign())
                if not self.accept(","):
                    break
            endt = self.peek()
            self.accept("}")
            return ("list", items, t.pos, endt.end)
        raise ParseError("token inesperado %r" % (t.val,))


def parse_expression(text, start, end):
    return Parser(tokenize(text, start, end)).parse_expr()


# ============================================================
#  Ajuste de literales (para poder arrastrar)
# ============================================================

def find_adjustable(ast, sign=1):
    """
    Busca un literal entero al que se le pueda sumar un delta para
    mover el elemento. Devuelve (span, valor, signo, op_span) o None.

    op_span es el tramo del operador '-' que hay que voltear a '+' si el
    resultado se vuelve negativo (o None).
    """
    kind = ast[0]
    if kind == "num" and isinstance(ast[1], int):
        return ((ast[2], ast[3]), ast[1], sign, None)
    if kind == "bin" and ast[1] in ("+", "-"):
        op = ast[1]
        l, r, op_pos = ast[2], ast[3], ast[4]
        got = find_adjustable(l, sign)
        if got:
            return got
        rsign = sign if op == "+" else -sign
        got = find_adjustable(r, rsign)
        if got:
            span, val, sg, _ = got
            # solo el operando derecho inmediato puede voltear ESTE operador,
            # y se voltea al CONTRARIO del que hay ahora
            if r is ast[3] and r[0] == "num":
                flip = "+" if op == "-" else "-"
                return (span, val, sg, (op_pos, op_pos + len(op), flip))
            return got
        return None
    if kind == "un" and ast[1] == "-":
        return find_adjustable(ast[2], -sign)
    if kind == "un" and ast[1] in ("+",):
        return find_adjustable(ast[2], sign)
    if kind == "cast":
        return find_adjustable(ast[1], sign)
    return None


def plan_delta(ast, delta):
    """
    Devuelve una lista de parches [(start, end, texto)] para mover el valor
    de `ast` en `delta`, o None si no se puede tocar (expresion sin literal).
    """
    if delta == 0:
        return []
    got = find_adjustable(ast)
    if not got:
        return None
    (s, e), val, sign, op_span = got
    newval = val + sign * delta
    if newval < 0 and op_span is not None:
        # `a - 2` con delta +3  ->  `a + 1`   (y al reves)
        return [(op_span[0], op_span[1], op_span[2]), (s, e, str(-newval))]
    return [(s, e, str(newval))]


# ============================================================
#  Valores de muestra para lo que no se puede calcular
# ============================================================

_SAMPLES = {
    "meshnodecount": 6, "meshdirectcount": 3, "meshpingresponders": 4,
    "collectnodes": 6, "rssi": -58, "lastrssi": -58, "pps": 12,
    "tx": 128, "rx": 96, "relay": 34, "dup": 5, "hops": 2,
    "millis": 12345, "meshmyid": 0xA1B2, "menuidx": 0, "listoffset": 0,
    "n": 6, "w": 30, "h": 10, "x": 8, "y": 24, "i": 0, "idx": 0,
    "count": 4, "len": 8, "size": 16, "value": 42, "temp": 25,
}


def sample_for(name):
    key = str(name).lower()
    if key in _SAMPLES:
        return _SAMPLES[key]
    for frag, v in (("count", 5), ("rssi", -58), ("width", 30), ("len", 8),
                    ("num", 4), ("id", 0xA1B2), ("time", 1200), ("ms", 500)):
        if frag in key:
            return v
    return (abs(hash(key)) % 40) + 3


class Unknown(object):
    """Valor no calculable; se comporta como su muestra en aritmetica."""
    __slots__ = ("name", "value")

    def __init__(self, name):
        self.name = name
        self.value = sample_for(name)

    def __int__(self):
        return int(self.value)

    def __repr__(self):
        return "?%s=%s" % (self.name, self.value)


def as_num(v):
    if isinstance(v, Unknown):
        return v.value
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        return len(v)
    return 0


def as_int(v):
    try:
        return int(as_num(v))
    except (TypeError, ValueError):
        return 0


def as_str(v):
    if isinstance(v, str):
        return v
    if isinstance(v, Unknown):
        return str(v.value)
    if isinstance(v, float):
        return "%g" % v
    return str(v)


# ============================================================
#  printf -> texto de muestra
# ============================================================

_FMT_RE = re.compile(r"%[-+ #0]*(\d+|\*)?(?:\.(\d+|\*))?(?:hh|h|ll|l|L|z|j|t)?([diuoxXfFeEgGcsp%])")


def format_sample(fmt, args):
    out = []
    ai = 0
    pos = 0
    for m in _FMT_RE.finditer(fmt):
        out.append(fmt[pos:m.start()])
        pos = m.end()
        conv = m.group(3)
        if conv == "%":
            out.append("%")
            continue
        width = m.group(1)
        arg = args[ai] if ai < len(args) else Unknown("arg%d" % ai)
        ai += 1
        if conv == "s":
            if isinstance(arg, Unknown):
                # texto que el firmware arma en vivo: muestra del ancho tipico
                alpha = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
                h = abs(hash(arg.name))
                s = "".join(alpha[(h >> (5 * k)) % len(alpha)] for k in range(4))
            else:
                s = as_str(arg)
        elif conv == "c":
            n = as_int(arg)
            s = chr(n) if 32 <= n < 127 else "?"
        elif conv in "xX":
            n = as_int(arg) & 0xFFFFFFFF
            s = ("%X" if conv == "X" else "%x") % n
            if width and width != "*" and m.group(0).lstrip("%")[0] == "0":
                s = s.rjust(int(width), "0")
        elif conv in "fFeEgG":
            prec = m.group(2)
            prec = int(prec) if prec and prec != "*" else 2
            try:
                s = ("%." + str(prec) + conv.lower()) % as_num(arg)
            except (TypeError, ValueError):
                s = "%.2f" % as_num(arg)
        elif conv == "p":
            s = "0x3FC0"
        else:
            s = str(as_int(arg))
        if width and width != "*" and len(s) < int(width):
            s = s.rjust(int(width))
        out.append(s)
    out.append(fmt[pos:])
    return "".join(out)


# ============================================================
#  Interprete
# ============================================================

DRAW_FUNCS = {
    # nombre u8g2/Adafruit -> (tipo interno, indices de args de posicion)
    "drawStr": "text", "drawUTF8": "text", "print": "text",
    "drawBox": "box", "fillRect": "box",
    "drawFrame": "frame", "drawRect": "frame",
    "drawRBox": "rbox", "fillRoundRect": "rbox",
    "drawRFrame": "rframe", "drawRoundRect": "rframe",
    "drawLine": "line", "drawHLine": "hline", "drawFastHLine": "hline",
    "drawVLine": "vline", "drawFastVLine": "vline",
    "drawPixel": "pixel", "drawCircle": "circle", "drawDisc": "disc",
    "fillCircle": "disc", "drawTriangle": "triangle", "fillTriangle": "triangle",
    "drawXBM": "xbm", "drawXBMP": "xbm", "drawBitmap": "xbm",
    "drawGlyph": "glyph",
}

MAX_ITERS = 64
MAX_OPS = 3000


class Signal(Exception):
    pass


class BreakSig(Signal):
    pass


class ContinueSig(Signal):
    pass


class ReturnSig(Signal):
    pass


class Interpreter(object):
    """
    Ejecuta el cuerpo de una funcion de dibujo y va acumulando
    operaciones (self.ops) con los spans de cada argumento.
    """

    def __init__(self, project, file_path):
        self.project = project      # da acceso a defines, funciones, arreglos
        self.file = file_path
        self.ops = []
        self.font = fonts.DEFAULT_FONT
        self.color = 1
        self.depth = 0
        self.budget = MAX_OPS
        # nombre de variable -> AST de su ultima asignacion, para poder
        # seguir `drawStr(6, y, ...)` hasta `int y = 24 + i * 10;`
        self.origin = {}
        self.origin_file = {}

    # ---------- entorno ----------
    def new_scope(self, parent=None):
        return dict(parent) if parent else {}

    # ---------- evaluacion ----------
    def eval(self, ast, env):
        k = ast[0]
        if k == "num":
            return ast[1]
        if k == "str":
            return ast[1]
        if k == "id":
            name = ast[1]
            if name in env:
                return env[name]
            g = self.project.globals
            if name in g:
                return g[name]
            if name.startswith("u8g2_font_") or name.startswith("u8x8_font_"):
                return name
            if name in ("true", "TRUE", "HIGH"):
                return 1
            if name in ("false", "FALSE", "LOW"):
                return 0
            if name in ("NULL", "nullptr"):
                return 0
            return Unknown(name)
        if k == "cast":
            return self.eval(ast[1], env)
        if k == "un":
            op = ast[1]
            if op.startswith("post"):
                base = op[4:]
                v = as_int(self.eval(ast[2], env))
                self.assign_to(ast[2], v + (1 if base == "++" else -1), env)
                return v
            if op in ("++", "--"):
                v = as_int(self.eval(ast[2], env)) + (1 if op == "++" else -1)
                self.assign_to(ast[2], v, env)
                return v
            v = self.eval(ast[2], env)
            if op == "-":
                return -as_num(v)
            if op == "+":
                return as_num(v)
            if op == "!":
                return 0 if as_num(v) else 1
            if op == "~":
                return ~as_int(v)
            return v
        if k == "bin":
            op = ast[1]
            if op == "&&":
                return 1 if (as_num(self.eval(ast[2], env)) and
                             as_num(self.eval(ast[3], env))) else 0
            if op == "||":
                return 1 if (as_num(self.eval(ast[2], env)) or
                             as_num(self.eval(ast[3], env))) else 0
            a = self.eval(ast[2], env)
            b = self.eval(ast[3], env)
            if op == "+" and (isinstance(a, str) or isinstance(b, str)):
                if isinstance(a, str) and isinstance(b, str):
                    return a + b
            x, y = as_num(a), as_num(b)
            try:
                if op == "+":
                    return x + y
                if op == "-":
                    return x - y
                if op == "*":
                    return x * y
                if op == "/":
                    if y == 0:
                        return 0
                    return x // y if (isinstance(x, int) and isinstance(y, int)) else x / y
                if op == "%":
                    return x % y if y else 0
                if op == "<<":
                    return int(x) << int(y)
                if op == ">>":
                    return int(x) >> int(y)
                if op == "&":
                    return int(x) & int(y)
                if op == "|":
                    return int(x) | int(y)
                if op == "^":
                    return int(x) ^ int(y)
                if op == "<":
                    return 1 if x < y else 0
                if op == ">":
                    return 1 if x > y else 0
                if op == "<=":
                    return 1 if x <= y else 0
                if op == ">=":
                    return 1 if x >= y else 0
                if op == "==":
                    if isinstance(a, str) or isinstance(b, str):
                        return 1 if as_str(a) == as_str(b) else 0
                    return 1 if x == y else 0
                if op == "!=":
                    if isinstance(a, str) or isinstance(b, str):
                        return 1 if as_str(a) != as_str(b) else 0
                    return 1 if x != y else 0
            except (TypeError, ValueError, OverflowError):
                return 0
            return 0
        if k == "cond":
            return self.eval(ast[2], env) if as_num(self.eval(ast[1], env)) \
                else self.eval(ast[3], env)
        if k == "assign":
            op = ast[1]
            rhs = self.eval(ast[3], env)
            if op == "=":
                val = rhs
            else:
                cur = as_num(self.eval(ast[2], env))
                r = as_num(rhs)
                val = {"+=": cur + r, "-=": cur - r, "*=": cur * r,
                       "/=": (cur // r if r else 0), "%=": (cur % r if r else 0),
                       "&=": int(cur) & int(r), "|=": int(cur) | int(r),
                       "^=": int(cur) ^ int(r),
                       "<<=": int(cur) << int(r), ">>=": int(cur) >> int(r)}.get(op, r)
            self.assign_to(ast[2], val, env, ast[3] if op == "=" else None)
            return val
        if k == "index":
            arr = self.eval(ast[1], env)
            idx = as_int(self.eval(ast[2], env))
            if isinstance(arr, list):
                return arr[idx] if 0 <= idx < len(arr) else Unknown("idx")
            return Unknown("elem")
        if k == "member":
            return Unknown(ast[2])
        if k == "list":
            return [self.eval(x, env) for x in ast[1]]
        if k == "call":
            return self.do_call(ast, env)
        return Unknown("?")

    def assign_to(self, target, value, env, rhs_ast=None):
        if target[0] == "id":
            env[target[1]] = value
            if rhs_ast is not None:
                self.origin[target[1]] = rhs_ast
                self.origin_file[target[1]] = self.file
            else:
                self.origin.pop(target[1], None)
        # index/member: no lo seguimos

    # ---------- llamadas ----------
    def call_name(self, callee):
        """Devuelve (objeto, nombre) de la cosa llamada."""
        if callee[0] == "member":
            obj = callee[1]
            objname = obj[1] if obj[0] == "id" else None
            return objname, callee[2]
        if callee[0] == "id":
            return None, callee[1]
        return None, None

    def do_call(self, ast, env):
        callee, args = ast[1], ast[2]
        objname, name = self.call_name(callee)

        # --- dibujo ---
        if name in DRAW_FUNCS:
            self.emit_draw(name, args, env, ast)
            return 0

        # --- estado del display ---
        if name == "setFont":
            v = self.eval(args[0], env) if args else fonts.DEFAULT_FONT
            self.font = v if isinstance(v, str) else fonts.DEFAULT_FONT
            return 0
        if name in ("setDrawColor", "setColor"):
            self.color = as_int(self.eval(args[0], env)) if args else 1
            return 0
        if name in ("getStrWidth", "getUTF8Width"):
            s = as_str(self.eval(args[0], env)) if args else ""
            return fonts.text_width(s, self.font)
        if name in ("getMaxCharHeight", "getAscent", "getFontAscent"):
            return fonts.text_height(self.font)
        if name in ("getDisplayWidth",):
            return self.project.screen_w
        if name in ("getDisplayHeight",):
            return self.project.screen_h
        if name in ("clearBuffer", "sendBuffer", "firstPage", "nextPage",
                    "begin", "setFontMode", "setBitmapMode", "setCursor",
                    "display", "clearDisplay", "setTextSize", "setTextColor"):
            return 0

        # --- formato de texto ---
        if name in ("snprintf", "sprintf"):
            if name == "snprintf" and len(args) >= 3:
                buf_ast, fmt_ast, rest = args[0], args[2], args[3:]
            elif len(args) >= 2:
                buf_ast, fmt_ast, rest = args[0], args[1], args[2:]
            else:
                return 0
            fmt = self.eval(fmt_ast, env)
            vals = [self.eval(a, env) for a in rest]
            s = format_sample(as_str(fmt), vals)
            # el origen del texto es la cadena de formato: asi se puede
            # editar "%d nodos" desde el panel de propiedades
            self.assign_to(buf_ast, s, env, fmt_ast)
            return len(s)
        if name in ("strncpy", "strcpy"):
            if len(args) >= 2:
                v = as_str(self.eval(args[1], env))
                if name == "strncpy" and len(args) >= 3:
                    n = as_int(self.eval(args[2], env))
                    v = v[:max(0, n - 1)]
                self.assign_to(args[0], v, env, args[1])
                return v
            return ""
        if name == "strlen":
            return len(as_str(self.eval(args[0], env))) if args else 0
        if name in ("strcmp", "strncmp"):
            return 0
        if name == "F":
            return self.eval(args[0], env) if args else ""

        # --- utilidades ---
        if name == "millis" or name == "micros":
            return 12345
        if name == "random":
            vals = [as_int(self.eval(a, env)) for a in args]
            return vals[0] if vals else 0
        if name in ("min",):
            vals = [as_num(self.eval(a, env)) for a in args]
            return min(vals) if vals else 0
        if name in ("max",):
            vals = [as_num(self.eval(a, env)) for a in args]
            return max(vals) if vals else 0
        if name in ("abs",):
            return abs(as_num(self.eval(args[0], env))) if args else 0
        if name in ("constrain",):
            v = [as_num(self.eval(a, env)) for a in args]
            return min(max(v[0], v[1]), v[2]) if len(v) >= 3 else (v[0] if v else 0)

        # --- funcion del propio proyecto: inlinear ---
        fn = self.project.functions.get(name)
        if fn is not None and self.depth < 4 and self.budget > 0:
            argv = [self.eval(a, env) for a in args]
            self.run_function(fn, argv)
            return 0

        for a in args:
            self.eval(a, env)
        return Unknown(name or "call")

    # ---------- emision de operaciones ----------
    def emit_draw(self, name, args, env, call_ast):
        if self.budget <= 0:
            return
        self.budget -= 1
        kind = DRAW_FUNCS[name]
        vals = [self.eval(a, env) for a in args]
        # si el argumento es una variable suelta, guardamos de donde salio
        origins = []
        ofiles = []
        names = []
        for a in args:
            names.append(a[1] if a[0] == "id" else None)
            if a[0] == "id" and a[1] in self.origin:
                origins.append(self.origin[a[1]])
                ofiles.append(self.origin_file.get(a[1], self.file))
            else:
                origins.append(None)
                ofiles.append(None)
        self.ops.append({
            "kind": kind,
            "fn": name,
            "vals": vals,
            "asts": list(args),
            "origins": origins,
            "origin_files": ofiles,
            "names": names,          # nombre del identificador, si el arg lo es
            "font": self.font,
            "color": self.color,
            "file": self.file,
            "call_span": (call_ast[3], call_ast[4]),
            "site": call_ast[3],          # identidad estable del call site
        })

    # ---------- sentencias ----------
    def run_function(self, fn, argv=()):
        env = {}
        for i, p in enumerate(fn["params"]):
            env[p] = argv[i] if i < len(argv) else Unknown(p)
        saved_file = self.file
        self.file = fn["file"]
        self.depth += 1
        try:
            self.exec_block(fn["body_toks"], env)
        except ReturnSig:
            pass
        except Signal:
            pass
        except Exception:
            pass
        finally:
            self.depth -= 1
            self.file = saved_file

    def exec_block(self, toks, env):
        p = Parser(toks)
        while p.peek().kind != "eof":
            self.exec_stmt(p, env)

    def exec_stmt(self, p, env):
        if self.budget <= 0:
            raise ReturnSig()
        t = p.peek()

        if t.kind == "op" and t.val == ";":
            p.next()
            return
        if t.kind == "op" and t.val == "{":
            p.next()
            inner = dict(env)
            while not p.at("}") and p.peek().kind != "eof":
                self.exec_stmt(p, inner)
            p.accept("}")
            env.update({k: v for k, v in inner.items() if k in env})
            return

        if t.kind == "id":
            kw = t.val
            if kw == "if":
                return self.exec_if(p, env)
            if kw == "for":
                return self.exec_for(p, env)
            if kw == "while":
                return self.exec_while(p, env)
            if kw == "do":
                p.next()
                self.skip_stmt(p)
                self.skip_to_semicolon(p)
                return
            if kw == "switch":
                return self.exec_switch(p, env)
            if kw == "return":
                p.next()
                if not p.at(";"):
                    try:
                        p.parse_expr()
                    except ParseError:
                        pass
                p.accept(";")
                raise ReturnSig()
            if kw == "break":
                p.next()
                p.accept(";")
                raise BreakSig()
            if kw == "continue":
                p.next()
                p.accept(";")
                raise ContinueSig()
            if kw in ("case", "default"):
                p.next()
                while not p.at(":") and p.peek().kind != "eof":
                    p.next()
                p.accept(":")
                return
            if kw == "else":
                p.next()
                return self.exec_stmt(p, env)

        # declaracion?
        decl = self.try_decl(p, env)
        if decl:
            return

        # expresion suelta
        try:
            e = p.parse_expr()
            self.eval(e, env)
        except ParseError:
            p.next()
        self.skip_to_semicolon(p)

    def try_decl(self, p, env):
        """Reconoce `int y = ...;`, `char l[26];`, `const char* s = "x";`"""
        save = p.i
        t = p.peek()
        if t.kind != "id":
            return False
        if t.val not in _TYPE_WORDS:
            # tipo definido por el usuario:  MeshMetrics m = ...;
            nxt = p.peek(1)
            is_userdecl = (nxt.kind == "id") or (
                nxt.kind == "op" and nxt.val in ("*", "&") and p.peek(2).kind == "id")
            if not is_userdecl:
                return False
        # consumir calificadores/tipo
        while p.peek().kind == "id" and (p.peek().val in _TYPE_WORDS or
                                         p.peek(1).kind == "id" or
                                         (p.peek(1).kind == "op" and p.peek(1).val in ("*", "&"))):
            p.next()
            while p.at("*") or p.at("&"):
                p.next()
            if p.peek().kind == "id" and p.peek(1).kind == "op" and \
                    p.peek(1).val in ("=", ";", "[", ","):
                break
        if p.peek().kind != "id":
            p.i = save
            return False
        # declaradores
        while True:
            nm = p.next()
            if nm.kind != "id":
                break
            is_array = False
            dims = []
            while p.at("["):
                is_array = True
                p.next()
                if not p.at("]"):
                    try:
                        dims.append(as_int(self.eval(p.parse_expr(), env)))
                    except ParseError:
                        pass
                p.accept("]")
            if p.accept("="):
                try:
                    rhs = p.parse_assign()
                    val = self.eval(rhs, env)
                except ParseError:
                    rhs, val = None, Unknown(nm.val)
                env[nm.val] = val
                if rhs is not None:
                    self.origin[nm.val] = rhs
                    self.origin_file[nm.val] = self.file
            else:
                env[nm.val] = "" if is_array else Unknown(nm.val)
                self.origin.pop(nm.val, None)
            if not p.accept(","):
                break
            while p.at("*") or p.at("&"):
                p.next()
        p.accept(";")
        return True

    def exec_if(self, p, env):
        p.next()
        p.expect("(")
        try:
            cond = p.parse_expr()
        except ParseError:
            cond = ("num", 1, 0, 0)
        p.expect(")")
        truthy = as_num(self.eval(cond, env))
        if truthy:
            self.exec_stmt(p, env)
            if p.at_id("else"):
                p.next()
                self.skip_stmt(p)
        else:
            self.skip_stmt(p)
            if p.at_id("else"):
                p.next()
                self.exec_stmt(p, env)

    def exec_for(self, p, env):
        p.next()
        p.expect("(")
        inner = dict(env)
        if not p.at(";"):
            if not self.try_decl_inline(p, inner):
                try:
                    self.eval(p.parse_expr(), inner)
                except ParseError:
                    pass
                p.accept(";")
        else:
            p.next()
        cond_start = p.i
        cond_ast = None
        if not p.at(";"):
            try:
                cond_ast = p.parse_expr()
            except ParseError:
                cond_ast = None
        p.accept(";")
        inc_ast = None
        if not p.at(")"):
            try:
                inc_ast = p.parse_expr()
            except ParseError:
                inc_ast = None
        p.expect(")")
        body_start = p.i
        iters = 0
        while iters < MAX_ITERS and self.budget > 0:
            if cond_ast is not None and not as_num(self.eval(cond_ast, inner)):
                break
            p.i = body_start
            try:
                self.exec_stmt(p, inner)
            except BreakSig:
                p.i = body_start
                self.skip_stmt(p)
                break
            except ContinueSig:
                p.i = body_start
                self.skip_stmt(p)
            if inc_ast is not None:
                self.eval(inc_ast, inner)
            iters += 1
        else:
            p.i = body_start
            self.skip_stmt(p)
            return
        if iters == 0:
            p.i = body_start
            self.skip_stmt(p)
        else:
            p.i = body_start
            self.skip_stmt(p)
        for k in env:
            if k in inner:
                env[k] = inner[k]

    def try_decl_inline(self, p, env):
        save = p.i
        if self.try_decl(p, env):
            return True
        p.i = save
        return False

    def exec_while(self, p, env):
        p.next()
        p.expect("(")
        try:
            cond = p.parse_expr()
        except ParseError:
            cond = ("num", 0, 0, 0)
        p.expect(")")
        body = p.i
        iters = 0
        while iters < MAX_ITERS and self.budget > 0 and as_num(self.eval(cond, env)):
            p.i = body
            try:
                self.exec_stmt(p, env)
            except BreakSig:
                break
            except ContinueSig:
                pass
            iters += 1
        p.i = body
        self.skip_stmt(p)

    def exec_switch(self, p, env):
        p.next()
        p.expect("(")
        try:
            sel = self.eval(p.parse_expr(), env)
        except ParseError:
            sel = Unknown("sel")
        p.expect(")")
        # ejecutamos solo la rama que coincide; si no se sabe, ninguna
        p.expect("{")
        depth = 1
        chosen = False
        while p.peek().kind != "eof":
            if p.at("{"):
                depth += 1
                p.next()
                continue
            if p.at("}"):
                depth -= 1
                p.next()
                if depth == 0:
                    break
                continue
            if p.at_id("case") or p.at_id("default"):
                is_def = p.at_id("default")
                p.next()
                lbl = None
                if not is_def:
                    try:
                        lbl = self.eval(p.parse_expr(), env)
                    except ParseError:
                        lbl = None
                p.accept(":")
                chosen = (lbl is not None and as_num(lbl) == as_num(sel))
                continue
            if chosen:
                try:
                    self.exec_stmt(p, env)
                except BreakSig:
                    chosen = False
                except Signal:
                    raise
            else:
                p.next()

    # ---------- saltar sentencias sin ejecutarlas ----------
    def skip_stmt(self, p):
        if p.at("{"):
            depth = 0
            while p.peek().kind != "eof":
                if p.at("{"):
                    depth += 1
                elif p.at("}"):
                    depth -= 1
                    p.next()
                    if depth == 0:
                        return
                    continue
                p.next()
            return
        depth = 0
        while p.peek().kind != "eof":
            if p.at("("):
                depth += 1
            elif p.at(")"):
                depth -= 1
            elif p.at(";") and depth <= 0:
                p.next()
                return
            elif p.at("{"):
                self.skip_stmt(p)
                return
            p.next()

    def skip_to_semicolon(self, p):
        depth = 0
        while p.peek().kind != "eof":
            if p.at("(") or p.at("["):
                depth += 1
            elif p.at(")") or p.at("]"):
                depth -= 1
            elif p.at(";") and depth <= 0:
                p.next()
                return
            elif p.at("}") and depth <= 0:
                return
            p.next()
