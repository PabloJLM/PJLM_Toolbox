# -*- coding: utf-8 -*-
"""
ms_project.py - El proyecto ES el modelo.

Carga una carpeta de sketch (.ino/.cpp/.h), encuentra las funciones que
dibujan y los bitmaps, y mantiene el texto de cada archivo en memoria.
Cada edicion es un parche sobre ese texto seguido de un re-analisis, asi
que lo que ves en el canvas siempre es lo que dice el codigo. No hay
formato propio ni base de datos: Ctrl+S escribe los archivos y ya.

u8g2 Studio - MIT License
"""

import os
import re

import ms_core as core
import ms_cparse as cp
import ms_fonts as fonts


SOURCE_EXT = (".ino", ".cpp", ".cc", ".c", ".h", ".hpp")

# Argumentos de posicion por tipo de primitiva:
#   nombre -> lista de (indice, papel)
ARG_ROLES = {
    "text":     [(0, "x"), (1, "y"), (2, "text")],
    "box":      [(0, "x"), (1, "y"), (2, "w"), (3, "h")],
    "frame":    [(0, "x"), (1, "y"), (2, "w"), (3, "h")],
    "rbox":     [(0, "x"), (1, "y"), (2, "w"), (3, "h"), (4, "r")],
    "rframe":   [(0, "x"), (1, "y"), (2, "w"), (3, "h"), (4, "r")],
    "line":     [(0, "x"), (1, "y"), (2, "x2"), (3, "y2")],
    "hline":    [(0, "x"), (1, "y"), (2, "w")],
    "vline":    [(0, "x"), (1, "y"), (2, "h")],
    "pixel":    [(0, "x"), (1, "y")],
    "circle":   [(0, "x"), (1, "y"), (2, "r")],
    "disc":     [(0, "x"), (1, "y"), (2, "r")],
    "triangle": [(0, "x"), (1, "y"), (2, "x2"), (3, "y2"), (4, "x3"), (5, "y3")],
    "xbm":      [(0, "x"), (1, "y"), (2, "w"), (3, "h"), (4, "array")],
    "glyph":    [(0, "x"), (1, "y"), (2, "enc")],
}

# que argumentos mueve un arrastre
DRAG_ARGS = {
    "text":     {"x": [0], "y": [1]},
    "box":      {"x": [0], "y": [1]},
    "frame":    {"x": [0], "y": [1]},
    "rbox":     {"x": [0], "y": [1]},
    "rframe":   {"x": [0], "y": [1]},
    "line":     {"x": [0, 2], "y": [1, 3]},
    "hline":    {"x": [0], "y": [1]},
    "vline":    {"x": [0], "y": [1]},
    "pixel":    {"x": [0], "y": [1]},
    "circle":   {"x": [0], "y": [1]},
    "disc":     {"x": [0], "y": [1]},
    "triangle": {"x": [0, 2, 4], "y": [1, 3, 5]},
    "xbm":      {"x": [0], "y": [1]},
    "glyph":    {"x": [0], "y": [1]},
}

# que argumento cambia el tirador de tamano
RESIZE_ARGS = {
    "box": ("w", "h"), "frame": ("w", "h"), "rbox": ("w", "h"),
    "rframe": ("w", "h"), "xbm": ("w", "h"),
    "hline": ("w", None), "vline": (None, "h"),
    "circle": ("r", "r"), "disc": ("r", "r"),
    "line": ("x2", "y2"),
}


# ============================================================
#  Elemento = un sitio de llamada en el codigo
# ============================================================

class Element(object):

    def __init__(self, ops, gen=0):
        first = ops[0]
        self.gen = gen
        self.ops = ops                       # una por iteracion del bucle
        self.kind = first["kind"]
        self.fn = first["fn"]
        self.file = first["file"]
        self.site = first["site"]
        self.font = first["font"]
        self.color = first["color"]
        self.asts = first["asts"]
        self.origins = first.get("origins") or [None] * len(self.asts)
        self.origin_files = first.get("origin_files") or [None] * len(self.asts)
        self.names = first.get("names") or [None] * len(self.asts)
        self.vals = first["vals"]
        self.call_span = first["call_span"]

    @property
    def key(self):
        return (self.file, self.site)

    @property
    def repeats(self):
        return len(self.ops)

    def role_index(self, role):
        for i, r in ARG_ROLES.get(self.kind, []):
            if r == role:
                return i
        return None

    def ident(self, role):
        """Nombre del identificador de ese argumento (p.ej. el arreglo XBM)."""
        i = self.role_index(role)
        if i is None or i >= len(self.names):
            return None
        return self.names[i]

    def value(self, role, op=None):
        i = self.role_index(role)
        vals = (op or self.ops[0])["vals"]
        if i is None or i >= len(vals):
            return 0
        return vals[i]

    def ast(self, role):
        i = self.role_index(role)
        if i is None or i >= len(self.asts):
            return None
        return self.asts[i]

    def edit_target(self, role):
        """
        (ast, archivo) que hay que tocar para cambiar ese argumento.
        Si el argumento es una variable suelta (`drawStr(6, y, ...)`),
        apunta a su asignacion (`int y = 24 + i * 10;`).
        """
        i = self.role_index(role)
        if i is None or i >= len(self.asts):
            return None, None
        a = self.asts[i]
        if a[0] == "id" and self.origins[i] is not None:
            return self.origins[i], (self.origin_files[i] or self.file)
        return a, self.file

    def indirect(self, role):
        """True si editar este argumento toca una variable, no la llamada."""
        i = self.role_index(role)
        if i is None or i >= len(self.asts):
            return False
        return self.asts[i][0] == "id" and self.origins[i] is not None

    def var_name(self, role):
        i = self.role_index(role)
        if i is None or i >= len(self.asts):
            return None
        a = self.asts[i]
        return a[1] if a[0] == "id" else None

    def locked(self, role):
        """True si ese argumento no tiene ningun literal que se pueda mover."""
        a, _ = self.edit_target(role)
        if a is None:
            return True
        return cp.find_adjustable(a) is None

    def is_literal_text(self):
        a, _ = self.edit_target("text")
        return a is not None and a[0] == "str"

    def label(self):
        if self.kind == "text":
            t = cp.as_str(self.value("text"))
            t = t if len(t) <= 22 else t[:21] + "…"
            base = '"%s"' % t
        else:
            base = self.fn
        extra = ""
        if self.repeats > 1:
            extra += "  x%d" % self.repeats
        if self.color == 0:
            extra += "  [inv]"
        return base + extra

    def source_line(self, text):
        ls = text.rfind("\n", 0, self.call_span[0]) + 1
        le = text.find("\n", self.call_span[1])
        le = len(text) if le == -1 else le
        return text[ls:le].strip()


class Screen(object):

    def __init__(self, name, file, fn_info, ops, gen=0):
        self.gen = gen
        self.name = name
        self.file = file
        self.fn = fn_info
        self.ops = ops
        groups = {}
        order = []
        for o in ops:
            k = (o["file"], o["site"])
            if k not in groups:
                groups[k] = []
                order.append(k)
            groups[k].append(o)
        self.elements = [Element(groups[k], gen) for k in order]

    @property
    def foreign(self):
        """Elementos que viven en OTRA funcion (p.ej. header())."""
        return any(e.file != self.file or
                   not (self.fn["body_start"] <= e.site <= self.fn["body_end"])
                   for e in self.elements)

    def label(self):
        n = len(self.elements)
        return "%s()  -  %d elem" % (self.name, n)


# ============================================================
#  Proyecto
# ============================================================

_FUNC_RE = re.compile(r"""
    (?:^|[};])\s*
    (?:(?:static|inline|virtual|extern|const|constexpr)\s+)*
    (?P<ret>[A-Za-z_]\w*(?:\s*[*&])?)\s+
    (?P<name>[A-Za-z_]\w*)\s*
    \(\s*(?P<params>[^);]*)\)\s*
    (?:const\s*)?
    \{
""", re.VERBOSE | re.MULTILINE)

_DEFINE_RE = re.compile(r"^[ \t]*#define[ \t]+(\w+)[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_ENUM_RE = re.compile(r"\benum\s+(?:class\s+)?(\w+)?\s*(?::\s*\w+\s*)?\{", re.MULTILINE)

# El nombre de clase de u8g2/u8x8 codifica la resolucion real del panel,
# p.ej. U8G2_SSD1306_128X32_UNIVISION_F_HW_I2C o U8X8_SH1106_128X64_NONAME_HW_I2C.
# Es el dato mas confiable: no depende de que el proyecto defina nada.
_CTOR_RE = re.compile(r"\bU8[GX]2?_\w*?_(\d+)X(\d+)_\w+\s+\w+\s*\(")

# nombres de #define de tamano de pantalla que se ven en distintos proyectos
_SCREEN_W_NAMES = ("SCREEN_W", "SCREEN_WIDTH", "DISPLAY_WIDTH", "OLED_WIDTH",
                   "LCD_WIDTH", "SSD1306_LCDWIDTH", "TFT_WIDTH")
_SCREEN_H_NAMES = ("SCREEN_H", "SCREEN_HEIGHT", "DISPLAY_HEIGHT", "OLED_HEIGHT",
                   "LCD_HEIGHT", "SSD1306_LCDHEIGHT", "TFT_HEIGHT")


class Project(object):

    def __init__(self, root=None):
        self.root = None
        self.files = {}            # path -> texto en memoria
        self.disk = {}             # path -> texto tal como esta en disco
        self.globals = {}
        self.functions = {}
        self.screens = []
        self.bitmaps = []          # (file, nombre, bytes, frames)
        self.screen_w = 128
        self.screen_h = 64
        self.generation = 0
        self.last_error = ""
        self._undo = []
        self._redo = []
        if root:
            self.load(root)

    # ---------- carga ----------
    def load(self, root):
        if os.path.isfile(root):
            paths = [root]
            self.root = os.path.dirname(root)
        else:
            self.root = root
            paths = []
            for name in sorted(os.listdir(root)):
                p = os.path.join(root, name)
                if os.path.isfile(p) and name.lower().endswith(SOURCE_EXT):
                    paths.append(p)
        self.files = {}
        self.disk = {}
        for p in paths:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                t = f.read()
            self.files[p] = t
            self.disk[p] = t
        self._undo = []
        self._redo = []
        self.analyze()

    def add_file(self, path):
        if path in self.files:
            return
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            t = f.read()
        self.files[path] = t
        self.disk[path] = t
        self.analyze()

    # ---------- analisis ----------
    def analyze(self):
        self.generation += 1
        self.globals = {}
        self.functions = {}
        self.bitmaps = []

        clean = {}
        for p, text in self.files.items():
            c = cp.blank_preproc(cp.blank_comments(text))
            clean[p] = c

        # 1) #define numericos / simples
        for p, text in self.files.items():
            src = cp.blank_comments(text)
            for m in _DEFINE_RE.finditer(src):
                name, body = m.group(1), m.group(2).strip()
                if "(" in name:
                    continue
                try:
                    toks = cp.tokenize(body, 0, len(body))
                    ast = cp.Parser(toks).parse_expr()
                    self.globals[name] = _const_eval(ast, self.globals)
                except Exception:
                    pass

        # 2) enums
        for p, text in self.files.items():
            c = clean[p]
            for m in _ENUM_RE.finditer(c):
                ob = c.find("{", m.start())
                cb = cp.match_brace(c, ob)
                if cb == -1:
                    continue
                nxt = 0
                for part in _split_top(c[ob + 1:cb]):
                    part = part.strip()
                    if not part:
                        continue
                    if "=" in part:
                        nm, _, v = part.partition("=")
                        try:
                            toks = cp.tokenize(v, 0, len(v))
                            nxt = int(cp.as_num(_const_eval(
                                cp.Parser(toks).parse_expr(), self.globals)))
                        except Exception:
                            pass
                        self.globals[nm.strip()] = nxt
                    else:
                        self.globals[part] = nxt
                    nxt += 1

        # 3) arreglos y constantes globales (fuera de funciones)
        for p, text in self.files.items():
            self._scan_globals(p, clean[p])

        # 4) bitmaps
        for p, text in self.files.items():
            for name, nbytes, nframes, _span in core.find_arrays(text):
                self.bitmaps.append((p, name, nbytes, nframes))

        self.screen_w, self.screen_h = self._detect_screen_size()

        # 5) funciones
        for p, text in self.files.items():
            c = clean[p]
            for m in _FUNC_RE.finditer(c):
                if m.group("ret") in ("return", "else", "case"):
                    continue
                ob = c.index("{", m.end() - 1)
                cb = cp.match_brace(c, ob)
                if cb == -1:
                    continue
                params = []
                for part in _split_top(m.group("params")):
                    part = part.strip()
                    if not part or part == "void":
                        continue
                    pm = re.search(r"(\w+)\s*(?:\[\s*\w*\s*\])?$", part)
                    if pm:
                        params.append(pm.group(1))
                self.functions[m.group("name")] = {
                    "name": m.group("name"),
                    "file": p,
                    "params": params,
                    "body_start": ob + 1,
                    "body_end": cb,
                    "decl_start": m.start(),
                    "body_toks": cp.tokenize(c, ob + 1, cb),
                }

        # 6) pantallas = funciones que producen dibujo
        self.screens = []
        for name, fn in sorted(self.functions.items(),
                               key=lambda kv: (kv[1]["file"], kv[1]["decl_start"])):
            ops = self.run_function(name)
            if ops:
                self.screens.append(
                    Screen(name, fn["file"], fn, ops, self.generation))

    def _detect_screen_size(self):
        """
        Orden de confianza:
          1) el nombre de clase del objeto u8g2/u8x8 (U8G2_..._128X64_...) -
             es el dato real del panel, no depende de que el proyecto defina nada.
          2) un #define de tamano con alguno de los nombres usuales.
          3) 128x64, el tamano de OLED mas comun.
        Si hay varios objetos de display con tamanos distintos, se usa el
        primero que aparece.
        """
        for text in self.files.values():
            m = _CTOR_RE.search(cp.blank_comments(text))
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                if w > 0 and h > 0:
                    return w, h
        w = h = None
        for cand in _SCREEN_W_NAMES:
            v = self.globals.get(cand)
            if isinstance(v, (int, float)) and v > 0:
                w = int(v)
                break
        for cand in _SCREEN_H_NAMES:
            v = self.globals.get(cand)
            if isinstance(v, (int, float)) and v > 0:
                h = int(v)
                break
        return (w or 128), (h or 64)

    def _scan_globals(self, path, c):
        """const char* X[] = {...};  static const int N = 5;  (nivel de archivo)"""
        for m in re.finditer(
                r"(?:static\s+|const\s+|constexpr\s+)*"
                r"(?:char|int|uint8_t|int8_t|uint16_t|long|short|float|double|bool|\w+)"
                r"\s*[*&]?\s*(?:const\s*[*&]?\s*)?"
                r"(\w+)\s*(\[[^\];]*\])?\s*=\s*", c):
            name = m.group(1)
            pos = m.end()
            if pos >= len(c):
                continue
            # no entrar a cuerpos de funcion: comprobamos que no estemos dentro de {}
            if _inside_braces(c, m.start()):
                continue
            if c[pos] == "{":
                cb = cp.match_brace(c, pos)
                if cb == -1:
                    continue
                items = []
                for part in _split_top(c[pos + 1:cb]):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        toks = cp.tokenize(part, 0, len(part))
                        items.append(_const_eval(cp.Parser(toks).parse_expr(),
                                                 self.globals))
                    except Exception:
                        items.append(cp.Unknown(name))
                if items and any(isinstance(x, str) for x in items):
                    self.globals[name] = items
                elif items and len(items) <= 64:
                    self.globals[name] = items
            else:
                end = c.find(";", pos)
                if end == -1:
                    continue
                seg = c[pos:end]
                try:
                    toks = cp.tokenize(seg, 0, len(seg))
                    v = _const_eval(cp.Parser(toks).parse_expr(), self.globals)
                    if isinstance(v, (int, float, str)):
                        self.globals.setdefault(name, v)
                except Exception:
                    pass

    def run_function(self, name):
        fn = self.functions.get(name)
        if not fn:
            return []
        it = cp.Interpreter(self, fn["file"])
        it.run_function(fn)
        return it.ops

    def screen_by_name(self, name):
        for s in self.screens:
            if s.name == name:
                return s
        return None

    # ---------- edicion ----------
    def snapshot(self):
        return dict(self.files)

    def push_undo(self):
        self._undo.append(self.snapshot())
        if len(self._undo) > 80:
            self._undo.pop(0)
        self._redo = []

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self.snapshot())
        self.files = self._undo.pop()
        self.analyze()
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self.snapshot())
        self.files = self._redo.pop()
        self.analyze()
        return True

    def apply(self, path, patches, record_undo=True):
        """patches: [(start, end, texto)] sobre el archivo `path`."""
        patches = [p for p in patches if p is not None]
        if not patches:
            return False
        if record_undo:
            self.push_undo()
        text = self.files[path]
        for s, e, t in sorted(patches, key=lambda p: -p[0]):
            text = text[:s] + t + text[e:]
        self.files[path] = text
        self.analyze()
        return True

    # ---------- movimiento / tamano ----------
    def _fresh(self, obj):
        """
        Un Element/Screen deja de ser valido en cuanto se re-analiza: sus
        spans apuntan a un texto que ya cambio. Escribir con uno viejo
        corrompe el archivo, asi que se rechaza.
        """
        if getattr(obj, "gen", None) == self.generation:
            return True
        self.last_error = ("elemento obsoleto: vuelve a tomarlo del proyecto "
                           "despues de cada edicion")
        return False

    def move_element(self, el, dx, dy, record_undo=True):
        """
        Mueve el elemento. Todos los parches de un mismo arrastre se aplican
        juntos, y por archivo, porque un elemento puede tomar la X de la
        llamada y la Y de una variable declarada en otro lado.
        """
        if not self._fresh(el):
            return False
        by_file = {}
        seen = set()
        roles = ARG_ROLES.get(el.kind, [])
        idx2role = dict((i, r) for i, r in roles)
        for role_key, delta in (("x", dx), ("y", dy)):
            if delta == 0:
                continue
            for idx in DRAG_ARGS.get(el.kind, {}).get(role_key, []):
                if idx >= len(el.asts):
                    continue
                role = idx2role.get(idx, role_key)
                ast, fpath = el.edit_target(role)
                if ast is None:
                    return False
                # si dos argumentos vienen de la MISMA variable, un solo parche
                key = (fpath, ast[-2], ast[-1])
                if key in seen:
                    continue
                seen.add(key)
                p = cp.plan_delta(ast, delta)
                if p is None:
                    return False
                by_file.setdefault(fpath, []).extend(p)
        if not by_file:
            return False
        if record_undo:
            self.push_undo()
        for fpath, patches in by_file.items():
            self.apply(fpath, patches, record_undo=False)
        return True

    def set_arg(self, el, role, new_value, record_undo=True):
        if not self._fresh(el):
            return False
        i = el.role_index(role)
        if i is None or i >= len(el.asts):
            return False
        ast, fpath = el.edit_target(role)
        if ast is None:
            return False
        if role == "text":
            if ast[0] == "str":
                return self.apply(fpath,
                                  [(ast[2], ast[3], '"%s"' % _cesc(new_value))],
                                  record_undo)
            return False
        if role == "array":
            if ast[0] == "id":
                return self.apply(fpath, [(ast[2], ast[3], str(new_value))],
                                  record_undo)
            return False
        cur = cp.as_int(el.vals[i]) if i < len(el.vals) else 0
        plan = cp.plan_delta(ast, int(new_value) - cur)
        if plan is None:
            return False
        return self.apply(fpath, plan, record_undo)

    def set_font(self, el, font_name, record_undo=True):
        """Cambia el setFont que afecta a este elemento (el mas cercano antes)."""
        if not self._fresh(el):
            return False
        text = self.files[el.file]
        c = cp.blank_preproc(cp.blank_comments(text))
        best = None
        for m in re.finditer(r"\.\s*setFont\s*\(\s*([A-Za-z_]\w*)\s*\)", c):
            if m.end() <= el.call_span[0]:
                best = m
        if best is None:
            return False
        return self.apply(el.file, [(best.start(1), best.end(1), font_name)],
                          record_undo)

    def set_color(self, el, color, record_undo=True):
        """Envuelve la llamada en setDrawColor(n) ... setDrawColor(1)."""
        if not self._fresh(el):
            return False
        if color == el.color:
            return True
        text = self.files[el.file]
        s, e = el.call_span
        line_start = text.rfind("\n", 0, s) + 1
        indent = re.match(r"[ \t]*", text[line_start:]).group(0)
        stmt_end = text.find(";", e)
        stmt_end = e if stmt_end == -1 else stmt_end + 1
        obj = _display_obj(text, s) or "u8g2"
        if color == 0:
            block = ("%s.setDrawColor(0);\n%s%s\n%s%s.setDrawColor(1);"
                     % (obj, indent, text[s:stmt_end], indent, obj))
        else:
            block = text[s:stmt_end]
        return self.apply(el.file, [(s, stmt_end, block)], record_undo)

    # ---------- agregar / borrar ----------
    def statement_span(self, el):
        text = self.files[el.file]
        s, e = el.call_span
        stmt_end = text.find(";", e)
        stmt_end = e if stmt_end == -1 else stmt_end + 1
        line_start = text.rfind("\n", 0, s) + 1
        if text[line_start:s].strip() == "":
            s = line_start
            if stmt_end < len(text) and text[stmt_end] == "\n":
                stmt_end += 1
        return s, stmt_end

    def delete_element(self, el, record_undo=True):
        if not self._fresh(el):
            return False
        s, e = self.statement_span(el)
        return self.apply(el.file, [(s, e, "")], record_undo)

    def duplicate_element(self, el, record_undo=True):
        if not self._fresh(el):
            return False
        text = self.files[el.file]
        s, e = self.statement_span(el)
        return self.apply(el.file, [(e, e, text[s:e])], record_undo)

    def add_element(self, screen, kind, x=4, y=12, record_undo=True):
        """Agrega una llamada nueva al final del cuerpo de la funcion."""
        if not self._fresh(screen):
            return False
        path = screen.file
        text = self.files[path]
        fn = screen.fn
        body_end = fn["body_end"]
        # indentacion: la de la ultima linea con contenido del cuerpo
        head = text[fn["body_start"]:body_end]
        indent = "  "
        for line in reversed(head.splitlines()):
            if line.strip():
                indent = re.match(r"[ \t]*", line).group(0) or "  "
                break
        obj = _display_obj(text, fn["body_start"]) or "u8g2"
        call = _new_call(obj, kind, x, y, self)
        ins = text.rfind("\n", 0, body_end) + 1
        block = indent + call + "\n"
        return self.apply(path, [(ins, ins, block)], record_undo)

    def add_screen_function(self, path, name, record_undo=True):
        text = self.files[path]
        obj = _display_obj(text, len(text)) or "u8g2"
        code = ("\nvoid %s() {\n"
                "  %s.setFont(u8g2_font_6x10_tr);\n"
                "  %s.drawStr(2, 12, \"%s\");\n"
                "}\n" % (name, obj, obj, name))
        return self.apply(path, [(len(text), len(text), code)], record_undo)

    # ---------- estado / guardado ----------
    def is_dirty(self, path=None):
        if path:
            return self.files.get(path) != self.disk.get(path)
        return any(self.files[p] != self.disk.get(p) for p in self.files)

    def dirty_files(self):
        return [p for p in self.files if self.files[p] != self.disk.get(p)]

    def save(self, paths=None):
        written = []
        for p in (paths or self.dirty_files()):
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.files[p])
            self.disk[p] = self.files[p]
            written.append(p)
        return written

    def reload_from_disk(self):
        for p in list(self.files):
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    t = f.read()
                self.files[p] = t
                self.disk[p] = t
        self.analyze()

    def externally_changed(self):
        """Archivos que cambiaron en disco desde que los leimos."""
        out = []
        for p in self.files:
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    if f.read() != self.disk.get(p):
                        out.append(p)
            except OSError:
                pass
        return out

    # ---------- bitmaps ----------
    def load_bitmap(self, path, array_ref, width=None, height=None):
        text = self.files[path]
        name, frame = core.parse_array_ref(array_ref)
        loc = core.locate_array(text, name, frame)
        if loc is None:
            raise ValueError("no encontre '%s' en %s" % (name, os.path.basename(path)))
        s, e, nframes = loc
        data = core.parse_bytes(text[s:e])
        if width is None or height is None:
            width, height = self.guess_bitmap_size(name, len(data))
        bm = core.Bitmap(width, height, bytearray(data))
        return bm, nframes

    def guess_bitmap_size(self, name, nbytes):
        """
        Orden de confianza:
          1) una llamada real drawXBMP(x, y, W, H, nombre) en el codigo -
             es el dato exacto que usa el firmware, no una conjetura.
          2) un #define <BASE>_W / <BASE>_H (BASE = nombre del arreglo sin
             el sufijo _bits/_bitmap), con variantes de nombre comunes.
          3) ancho 128 (el mas comun) y alto derivado de los bytes.
        """
        w = h = None
        for scr in self.screens:
            for el in scr.elements:
                if el.kind == "xbm" and el.ident("array") == name:
                    cw, ch = cp.as_int(el.value("w")), cp.as_int(el.value("h"))
                    if cw > 0 and ch > 0:
                        w, h = cw, ch
                        break
            if w and h:
                break

        base = name.replace("_bits", "").replace("_bitmap", "").upper()
        if w is None:
            for cand in (base + "_W", base + "_WIDTH", "IMG_W", "LOGO_W", "EASTER_W"):
                v = self.globals.get(cand)
                if isinstance(v, (int, float)) and v > 0:
                    w = int(v)
                    break
        if h is None:
            for cand in (base + "_H", base + "_HEIGHT", "IMG_H", "LOGO_H", "EASTER_H"):
                v = self.globals.get(cand)
                if isinstance(v, (int, float)) and v > 0:
                    h = int(v)
                    break
        if not w:
            w = 128
        if not h:
            h = max(1, nbytes // ((w + 7) // 8))
        return w, h

    def save_bitmap(self, path, array_ref, bitmap, record_undo=True):
        text = self.files[path]
        name, frame = core.parse_array_ref(array_ref)
        loc = core.locate_array(text, name, frame)
        if loc is None:
            raise ValueError("no encontre '%s'" % name)
        s, e, _ = loc
        body = bitmap.to_bytes_body(per_line=16)
        patches = [(s, e, body)]
        # actualizar los #define de tamano si existen
        base = name.replace("_bits", "").replace("_bitmap", "").upper()
        for cand, val in ((base + "_W", bitmap.width), (base + "_H", bitmap.height)):
            m = re.search(r"(#define\s+%s\s+)(\d+)" % re.escape(cand), text)
            if m:
                patches.append((m.start(2), m.end(2), str(val)))
        return self.apply(path, patches, record_undo)


# ============================================================
#  helpers
# ============================================================

def _cesc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _split_top(s):
    """Divide por comas de nivel superior."""
    out = []
    depth = 0
    cur = []
    i = 0
    while i < len(s):
        c = s[i]
        if c in "({[":
            depth += 1
        elif c in ")}]":
            depth -= 1
        elif c in '"\'':
            q = c
            cur.append(c)
            i += 1
            while i < len(s) and s[i] != q:
                if s[i] == "\\":
                    cur.append(s[i])
                    i += 1
                if i < len(s):
                    cur.append(s[i])
                    i += 1
            if i < len(s):
                cur.append(s[i])
                i += 1
            continue
        if c == "," and depth == 0:
            out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur))
    return out


def _inside_braces(c, pos):
    depth = 0
    for ch in c[:pos]:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return depth > 0


def _const_eval(ast, glob):
    it = _ConstCtx(glob)
    return it.eval(ast, {})


class _ConstCtx(cp.Interpreter):
    def __init__(self, glob):
        class _P(object):
            pass
        p = _P()
        p.globals = glob
        p.functions = {}
        p.screen_w = 128
        p.screen_h = 64
        cp.Interpreter.__init__(self, p, "")


def _display_obj(text, before):
    """Adivina el nombre del objeto de display (u8g2, display, oled...)."""
    c = cp.blank_comments(text)
    names = re.findall(r"\b([A-Za-z_]\w*)\s*\.\s*(?:drawStr|drawBox|drawFrame|"
                       r"drawLine|drawXBMP|drawXBM|sendBuffer|clearBuffer|setFont)\s*\(",
                       c[:before] if before else c)
    if names:
        return names[-1]
    names = re.findall(r"\b([A-Za-z_]\w*)\s*\.\s*(?:drawStr|sendBuffer|setFont)\s*\(", c)
    return names[0] if names else None


def _new_call(obj, kind, x, y, project):
    w = min(40, project.screen_w - x - 2)
    h = 16
    if kind == "text":
        return '%s.drawStr(%d, %d, "Texto");' % (obj, x, y)
    if kind == "frame":
        return "%s.drawFrame(%d, %d, %d, %d);" % (obj, x, y, w, h)
    if kind == "box":
        return "%s.drawBox(%d, %d, %d, %d);" % (obj, x, y, w, h)
    if kind == "rframe":
        return "%s.drawRFrame(%d, %d, %d, %d, 3);" % (obj, x, y, w, h)
    if kind == "rbox":
        return "%s.drawRBox(%d, %d, %d, %d, 3);" % (obj, x, y, w, h)
    if kind == "line":
        return "%s.drawLine(%d, %d, %d, %d);" % (obj, x, y, x + 30, y + 10)
    if kind == "hline":
        return "%s.drawHLine(%d, %d, %d);" % (obj, x, y, w)
    if kind == "vline":
        return "%s.drawVLine(%d, %d, %d);" % (obj, x, y, 20)
    if kind == "pixel":
        return "%s.drawPixel(%d, %d);" % (obj, x, y)
    if kind == "circle":
        return "%s.drawCircle(%d, %d, 10);" % (obj, x + 10, y + 10)
    if kind == "disc":
        return "%s.drawDisc(%d, %d, 10);" % (obj, x + 10, y + 10)
    if kind == "triangle":
        return "%s.drawTriangle(%d, %d, %d, %d, %d, %d);" % (
            obj, x, y, x + 24, y, x + 12, y + 18)
    if kind == "xbm":
        name = project.bitmaps[0][1] if project.bitmaps else "bitmap_bits"
        bw, bh = project.guess_bitmap_size(name, 1024)
        return "%s.drawXBMP(%d, %d, %d, %d, %s);" % (obj, x, y, bw, bh, name)
    return "%s.drawPixel(%d, %d);" % (obj, x, y)
