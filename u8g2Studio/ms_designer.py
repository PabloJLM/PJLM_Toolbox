# -*- coding: utf-8 -*-
"""
ms_designer.py - Editor visual de las pantallas que YA existen en el codigo.

Carga la carpeta del sketch, lista las funciones que dibujan, las renderiza
y deja moverlas con el mouse. Cada arrastre reescribe el numero exacto
dentro de la llamada (o de la variable de la que sale), en memoria. Nada
toca el disco hasta Ctrl+S.

u8g2 Studio - MIT License
"""

import os

from PyQt5.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPainter, QColor, QPen, QBrush, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QPushButton, QSpinBox, QCheckBox, QComboBox, QLineEdit, QListWidget,
    QGroupBox, QMessageBox, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QPlainTextEdit, QInputDialog, QSizePolicy
)

import ms_core as core
import ms_cparse as cp
import ms_project as mpj
import ms_fonts as fonts
from ms_editor import THEMES


ADDABLE = [
    ("text", "Texto"), ("frame", "Marco"),
    ("box", "Caja llena"), ("rframe", "Marco red."),
    ("rbox", "Caja red."), ("line", "Linea"),
    ("hline", "Linea H"), ("vline", "Linea V"),
    ("circle", "Circulo"), ("disc", "Disco"),
    ("pixel", "Pixel"), ("triangle", "Triangulo"),
    ("xbm", "Bitmap XBM"),
]


# ============================================================
#  Render de operaciones
# ============================================================

def _rounded_rect(bm, x, y, w, h, r, v, fill):
    r = max(0, min(int(r), min(w, h) // 2))
    if fill:
        bm.draw_rect(x + r, y, x + w - 1 - r, y + h - 1, v, fill=True)
        bm.draw_rect(x, y + r, x + w - 1, y + h - 1 - r, v, fill=True)
    else:
        bm.draw_line(x + r, y, x + w - 1 - r, y, v)
        bm.draw_line(x + r, y + h - 1, x + w - 1 - r, y + h - 1, v)
        bm.draw_line(x, y + r, x, y + h - 1 - r, v)
        bm.draw_line(x + w - 1, y + r, x + w - 1, y + h - 1 - r, v)
    if r > 0:
        for cx, cy, sx, sy in ((x + r, y + r, -1, -1),
                               (x + w - 1 - r, y + r, 1, -1),
                               (x + r, y + h - 1 - r, -1, 1),
                               (x + w - 1 - r, y + h - 1 - r, 1, 1)):
            for dy in range(r + 1):
                for dx in range(r + 1):
                    d2 = dx * dx + dy * dy
                    if fill:
                        if d2 <= r * r:
                            bm.set(cx + sx * dx, cy + sy * dy, v)
                    elif abs(d2 - r * r) <= r:
                        bm.set(cx + sx * dx, cy + sy * dy, v)


def _triangle(bm, x0, y0, x1, y1, x2, y2, v):
    minx, maxx = min(x0, x1, x2), max(x0, x1, x2)
    miny, maxy = min(y0, y1, y2), max(y0, y1, y2)
    if (maxx - minx) * (maxy - miny) > 40000:
        return

    def sign(ax, ay, bx, by, cx, cy):
        return (ax - cx) * (by - cy) - (bx - cx) * (ay - cy)

    for py in range(miny, maxy + 1):
        for px in range(minx, maxx + 1):
            d1 = sign(px, py, x0, y0, x1, y1)
            d2 = sign(px, py, x1, y1, x2, y2)
            d3 = sign(px, py, x2, y2, x0, y0)
            if not (((d1 < 0) or (d2 < 0) or (d3 < 0)) and
                    ((d1 > 0) or (d2 > 0) or (d3 > 0))):
                bm.set(px, py, v)


def _args(op, n):
    v = [cp.as_int(x) for x in op["vals"][:n]]
    while len(v) < n:
        v.append(0)
    return v


def op_bounds(op):
    k = op["kind"]
    if k == "text":
        x, y = _args(op, 2)
        s = cp.as_str(op["vals"][2]) if len(op["vals"]) > 2 else ""
        w = max(1, fonts.text_width(s, op["font"]))
        h = fonts.text_height(op["font"])
        return QRect(x, y - h + 1, w, h)
    if k in ("box", "frame", "rbox", "rframe", "xbm"):
        x, y, w, h = _args(op, 4)
        return QRect(x, y, max(1, w), max(1, h))
    if k == "line":
        x, y, x2, y2 = _args(op, 4)
        return QRect(min(x, x2), min(y, y2), abs(x2 - x) + 1, abs(y2 - y) + 1)
    if k == "hline":
        x, y, w = _args(op, 3)
        return QRect(x, y, max(1, w), 1)
    if k == "vline":
        x, y, h = _args(op, 3)
        return QRect(x, y, 1, max(1, h))
    if k in ("circle", "disc"):
        x, y, r = _args(op, 3)
        return QRect(x - r, y - r, 2 * r + 1, 2 * r + 1)
    if k == "triangle":
        a = _args(op, 6)
        xs, ys = a[0::2], a[1::2]
        return QRect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
    if k == "glyph":
        x, y = _args(op, 2)
        h = fonts.text_height(op["font"])
        return QRect(x, y - h + 1, max(1, fonts.font_metrics(op["font"])[0]), h)
    x, y = _args(op, 2)
    return QRect(x, y, 1, 1)


def element_bounds(el):
    r = None
    for op in el.ops:
        b = op_bounds(op)
        r = b if r is None else r.united(b)
    return r or QRect(0, 0, 1, 1)


def render_ops(ops, width, height, bitmaps=None):
    bm = core.Bitmap(width, height)
    for op in ops:
        k = op["kind"]
        v = 1 if op.get("color", 1) else 0
        try:
            if k == "text":
                x, y = _args(op, 2)
                s = cp.as_str(op["vals"][2]) if len(op["vals"]) > 2 else ""
                fonts.draw_text_on_bitmap(bm, s, x, y, op["font"], v)
            elif k == "box":
                x, y, w, h = _args(op, 4)
                bm.draw_rect(x, y, x + w - 1, y + h - 1, v, fill=True)
            elif k == "frame":
                x, y, w, h = _args(op, 4)
                bm.draw_rect(x, y, x + w - 1, y + h - 1, v, fill=False)
            elif k in ("rbox", "rframe"):
                a = _args(op, 5)
                _rounded_rect(bm, a[0], a[1], a[2], a[3], a[4], v, k == "rbox")
            elif k == "line":
                x, y, x2, y2 = _args(op, 4)
                bm.draw_line(x, y, x2, y2, v)
            elif k == "hline":
                x, y, w = _args(op, 3)
                bm.draw_line(x, y, x + w - 1, y, v)
            elif k == "vline":
                x, y, h = _args(op, 3)
                bm.draw_line(x, y, x, y + h - 1, v)
            elif k == "pixel":
                x, y = _args(op, 2)
                bm.set(x, y, v)
            elif k in ("circle", "disc"):
                x, y, r = _args(op, 3)
                bm.draw_ellipse(x - r, y - r, x + r, y + r, v, fill=(k == "disc"))
            elif k == "triangle":
                a = _args(op, 6)
                _triangle(bm, a[0], a[1], a[2], a[3], a[4], a[5], v)
            elif k == "glyph":
                x, y = _args(op, 2)
                fonts.draw_text_on_bitmap(bm, "?", x, y, op["font"], v)
            elif k == "xbm":
                x, y, w, h = _args(op, 4)
                names = op.get("names") or []
                name = names[4] if len(names) > 4 and names[4] else ""
                art = (bitmaps or {}).get(name)
                if art is not None:
                    bm.blit(art, x, y, "or")
                else:
                    bm.draw_rect(x, y, x + w - 1, y + h - 1, v, fill=False)
                    bm.draw_line(x, y, x + w - 1, y + h - 1, v)
                    bm.draw_line(x + w - 1, y, x, y + h - 1, v)
        except Exception:
            continue
    return bm


# ============================================================
#  Lienzo
# ============================================================

class ScreenCanvas(QWidget):

    selectionChanged = pyqtSignal(int)
    edited = pyqtSignal()
    statusChanged = pyqtSignal(str)

    HANDLE = 7

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.project = None
        self.screen = None
        self.bitmaps = {}
        self.zoom = 6
        self.theme = "OLED azul"
        self.show_grid = True
        self.show_outline = True
        self.selected = -1

        self._mode = None
        self._start = None
        self._acc = None
        self._pending = None
        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.setInterval(16)
        self._drag_timer.timeout.connect(self._apply_drag)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._resize_widget()

    # ---- estado ----
    def set_screen(self, project, screen):
        self.project = project
        self.screen = screen
        self.selected = -1
        self._resize_widget()

    def refresh(self, keep=None):
        """Vuelve a tomar la pantalla del proyecto (tras un re-analisis)."""
        if self.project is None or self.screen is None:
            return
        s = self.project.screen_by_name(self.screen.name)
        if s is not None:
            self.screen = s
            if keep is not None:
                self.selected = min(keep, len(s.elements) - 1)
        self._resize_widget()

    @property
    def W(self):
        return self.project.screen_w if self.project else 128

    @property
    def H(self):
        return self.project.screen_h if self.project else 64

    def _resize_widget(self):
        self.setFixedSize(self.W * self.zoom + 1, self.H * self.zoom + 1)
        self.update()

    def set_zoom(self, z):
        self.zoom = max(1, min(24, int(z)))
        self._resize_widget()

    def elements(self):
        return self.screen.elements if self.screen else []

    def current(self):
        els = self.elements()
        if 0 <= self.selected < len(els):
            return els[self.selected]
        return None

    # ---- pintado ----
    def paintEvent(self, ev):
        bg, fg, grid = THEMES.get(self.theme, THEMES["OLED azul"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(self.rect(), QColor(bg))
        if self.screen is None:
            p.setPen(QColor(fg))
            p.drawText(self.rect(), Qt.AlignCenter, "Abre la carpeta del sketch")
            p.end()
            return

        bm = render_ops(self.screen.ops, self.W, self.H, self.bitmaps)
        img = core.bitmap_to_qimage(bm, QColor(bg).rgb(), QColor(fg).rgb())
        p.drawImage(QRect(0, 0, bm.width * self.zoom, bm.height * self.zoom), img)

        if self.show_grid and self.zoom >= 4:
            p.setPen(QPen(QColor(grid), 1))
            for x in range(0, bm.width + 1, 8):
                p.drawLine(x * self.zoom, 0, x * self.zoom, bm.height * self.zoom)
            for y in range(0, bm.height + 1, 8):
                p.drawLine(0, y * self.zoom, bm.width * self.zoom, y * self.zoom)

        if self.show_outline:
            p.setBrush(Qt.NoBrush)
            for i, el in enumerate(self.elements()):
                foreign = el.file != self.screen.file
                for op in el.ops:
                    b = op_bounds(op)
                    qr = QRect(b.x() * self.zoom, b.y() * self.zoom,
                               b.width() * self.zoom, b.height() * self.zoom)
                    if i == self.selected:
                        p.setPen(QPen(QColor(255, 190, 0), 2))
                    elif foreign:
                        p.setPen(QPen(QColor(180, 120, 255, 80), 1, Qt.DotLine))
                    else:
                        p.setPen(QPen(QColor(90, 216, 255, 70), 1, Qt.DotLine))
                    p.drawRect(qr)
                if i == self.selected:
                    b = element_bounds(el)
                    qr = QRect(b.x() * self.zoom, b.y() * self.zoom,
                               b.width() * self.zoom, b.height() * self.zoom)
                    if el.kind in mpj.RESIZE_ARGS:
                        p.setBrush(QBrush(QColor(255, 190, 0)))
                        p.drawRect(qr.right() - self.HANDLE // 2,
                                   qr.bottom() - self.HANDLE // 2,
                                   self.HANDLE, self.HANDLE)
                        p.setBrush(Qt.NoBrush)
        p.end()

    # ---- interaccion ----
    def _pix(self, pos):
        return int(pos.x() // self.zoom), int(pos.y() // self.zoom)

    def _hit(self, x, y):
        els = self.elements()
        for i in range(len(els) - 1, -1, -1):
            for op in els[i].ops:
                if op_bounds(op).adjusted(-1, -1, 1, 1).contains(x, y):
                    return i
        return -1

    def _on_handle(self, pos):
        el = self.current()
        if el is None or el.kind not in mpj.RESIZE_ARGS:
            return False
        b = element_bounds(el)
        return (abs(pos.x() - b.right() * self.zoom) <= self.HANDLE and
                abs(pos.y() - b.bottom() * self.zoom) <= self.HANDLE)

    def mousePressEvent(self, ev):
        if self.screen is None or ev.button() != Qt.LeftButton:
            return
        self._pending = None
        x, y = self._pix(ev.pos())
        if self._on_handle(ev.pos()):
            self._mode = "resize"
            self._start = (x, y)
            self._acc = [0, 0]
            self.project.push_undo()
            return
        i = self._hit(x, y)
        if i != self.selected:
            self.selected = i
            self.selectionChanged.emit(i)
            self.update()
        if i >= 0:
            self._mode = "move"
            self._start = (x, y)
            self._acc = [0, 0]
            self.project.push_undo()

    def mouseMoveEvent(self, ev):
        x, y = self._pix(ev.pos())
        self.statusChanged.emit("x=%d  y=%d" % (x, y))
        if self._mode is None:
            return
        self._pending = (x, y)
        if not self._drag_timer.isActive():
            self._drag_timer.start()

    def _apply_drag(self):
        if self._mode is None or self._pending is None:
            return
        x, y = self._pending
        self._pending = None
        el = self.current()
        if el is None:
            return
        dx = x - self._start[0] - self._acc[0]
        dy = y - self._start[1] - self._acc[1]
        if dx == 0 and dy == 0:
            return
        ok = True
        if self._mode == "move":
            ok = self.project.move_element(el, dx, dy, record_undo=False)
        else:
            rw, rh = mpj.RESIZE_ARGS[el.kind]
            steps = []
            if rw and dx:
                steps.append((rw, dx))
            if rh and dy and (rh != rw or not dx):
                steps.append((rh, dy))
            for role, delta in steps:
                el = self.current()
                if el is None:
                    break
                ok = self._bump(el, role, delta) and ok
                self.refresh(keep=self.selected)
        if ok:
            self._acc[0] += dx
            self._acc[1] += dy
            self.refresh(keep=self.selected)
            self.edited.emit()
        else:
            self.statusChanged.emit(
                "ese valor no es un numero en el codigo, no se puede arrastrar")

    def _bump(self, el, role, delta):
        cur = cp.as_int(el.value(role))
        return self.project.set_arg(el, role, max(0, cur + delta), record_undo=False)

    def mouseReleaseEvent(self, ev):
        if self._drag_timer.isActive():
            self._drag_timer.stop()
        self._apply_drag()
        self._mode = None
        self._start = None
        self._pending = None

    def keyPressEvent(self, ev):
        el = self.current()
        if el is None or self.project is None:
            return QWidget.keyPressEvent(self, ev)
        k = ev.key()
        d = 1 if not (ev.modifiers() & Qt.ShiftModifier) else 5
        dx = -d if k == Qt.Key_Left else (d if k == Qt.Key_Right else 0)
        dy = -d if k == Qt.Key_Up else (d if k == Qt.Key_Down else 0)
        if dx or dy:
            if self.project.move_element(el, dx, dy):
                self.refresh(keep=self.selected)
                self.edited.emit()
            return
        QWidget.keyPressEvent(self, ev)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom + (1 if ev.angleDelta().y() > 0 else -1))
            ev.accept()
        else:
            ev.ignore()


# ============================================================
#  Pestana
# ============================================================

class _SelectAllSpinBox(QSpinBox):
    """QSpinBox que selecciona todo el numero al enfocar (para sobreescribir
    escribiendo directo en vez de borrar digito por digito)."""

    def focusInEvent(self, ev):
        QSpinBox.focusInEvent(self, ev)
        self.selectAll()


class DesignerTab(QWidget):

    projectEdited = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.project = None
        self.canvas = ScreenCanvas()

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # ---------- izquierda ----------
        left = QVBoxLayout()
        gb_s = QGroupBox("Pantallas encontradas")
        vs = QVBoxLayout(gb_s)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._tree_changed)
        vs.addWidget(self.tree)
        b_new = QPushButton("Nueva funcion de pantalla...")
        b_new.clicked.connect(self.new_screen)
        vs.addWidget(b_new)
        left.addWidget(gb_s, 1)

        gb_a = QGroupBox("Agregar a esta pantalla")
        ga = QGridLayout(gb_a)
        for i, (kind, label) in enumerate(ADDABLE):
            b = QPushButton(label)
            b.clicked.connect(lambda _, k=kind: self.add_element(k))
            ga.addWidget(b, i // 2, i % 2)
        left.addWidget(gb_a)
        lw = QWidget(); lw.setLayout(left); lw.setFixedWidth(250)
        root.addWidget(lw)

        # ---------- centro ----------
        center = QVBoxLayout()
        bar = QHBoxLayout()
        self.sp_zoom = QSpinBox(); self.sp_zoom.setRange(1, 24); self.sp_zoom.setValue(6)
        self.sp_zoom.setPrefix("zoom x")
        self.sp_zoom.valueChanged.connect(self.canvas.set_zoom)
        self.ck_grid = QCheckBox("Guias /8"); self.ck_grid.setChecked(True)
        self.ck_grid.toggled.connect(
            lambda v: (setattr(self.canvas, "show_grid", v), self.canvas.update()))
        self.ck_out = QCheckBox("Contornos"); self.ck_out.setChecked(True)
        self.ck_out.toggled.connect(
            lambda v: (setattr(self.canvas, "show_outline", v), self.canvas.update()))
        self.cb_theme = QComboBox(); self.cb_theme.addItems(list(THEMES.keys()))
        self.cb_theme.currentTextChanged.connect(
            lambda s: (setattr(self.canvas, "theme", s), self.canvas.update()))
        bar.addWidget(self.sp_zoom); bar.addWidget(self.ck_grid); bar.addWidget(self.ck_out)
        bar.addWidget(QLabel("Tema:")); bar.addWidget(self.cb_theme)
        bar.addStretch(1)
        center.addLayout(bar)

        sc = QScrollArea()
        sc.setWidget(self.canvas)
        sc.setAlignment(Qt.AlignCenter)
        center.addWidget(sc, 1)

        gb_src = QGroupBox("Linea de codigo del elemento seleccionado")
        vsrc = QVBoxLayout(gb_src)
        self.src = QPlainTextEdit()
        self.src.setReadOnly(True)
        self.src.setMaximumHeight(76)
        self.src.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        vsrc.addWidget(self.src)
        center.addWidget(gb_src)

        self.lb_status = QLabel("listo")
        self.canvas.statusChanged.connect(self.lb_status.setText)
        center.addWidget(self.lb_status)
        root.addLayout(center, 1)

        # ---------- derecha ----------
        right = QVBoxLayout()
        gb_l = QGroupBox("Elementos (orden de dibujo)")
        vl = QVBoxLayout(gb_l)
        self.lst = QListWidget()
        self.lst.currentRowChanged.connect(self._row_changed)
        vl.addWidget(self.lst)
        hb = QHBoxLayout()
        for label, fn, tip in [("Duplicar", self.duplicate, "copia la linea"),
                               ("Borrar", self.delete, "borra la linea del codigo")]:
            b = QPushButton(label); b.setToolTip(tip); b.clicked.connect(fn)
            hb.addWidget(b)
        vl.addLayout(hb)
        right.addWidget(gb_l, 1)

        self.gb_props = QGroupBox("Propiedades")
        self.props = QFormLayout(self.gb_props)
        right.addWidget(self.gb_props)
        right.addStretch(1)
        rw = QWidget(); rw.setLayout(right); rw.setFixedWidth(310)
        root.addWidget(rw)

        self.canvas.selectionChanged.connect(self.on_select)
        self.canvas.edited.connect(self._after_edit)

    # ---------- proyecto ----------
    def set_project(self, project):
        self.project = project
        self.canvas.project = project
        self._reload_bitmaps()
        self.refresh_tree()
        if self.project.screens:
            self.select_screen(self.project.screens[0].name)

    def _reload_bitmaps(self):
        self.canvas.bitmaps = {}
        if not self.project:
            return
        for path, name, nbytes, nframes in self.project.bitmaps:
            if nbytes < 32:
                continue
            try:
                bm, _ = self.project.load_bitmap(path, name)
                self.canvas.bitmaps[name] = bm
            except Exception:
                pass

    def refresh_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        if self.project:
            by_file = {}
            for s in self.project.screens:
                by_file.setdefault(s.file, []).append(s)
            for path in sorted(by_file):
                top = QTreeWidgetItem([os.path.basename(path)])
                top.setFlags(Qt.ItemIsEnabled)
                f = top.font(0); f.setBold(True); top.setFont(0, f)
                self.tree.addTopLevelItem(top)
                for s in by_file[path]:
                    it = QTreeWidgetItem([s.label()])
                    it.setData(0, Qt.UserRole, s.name)
                    top.addChild(it)
                top.setExpanded(True)
        self.tree.blockSignals(False)

    def select_screen(self, name):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                it = top.child(j)
                if it.data(0, Qt.UserRole) == name:
                    self.tree.setCurrentItem(it)
                    return

    def _tree_changed(self, cur, _prev):
        if cur is None:
            return
        name = cur.data(0, Qt.UserRole)
        if not name or not self.project:
            return
        s = self.project.screen_by_name(name)
        if s is None:
            return
        self.canvas.set_screen(self.project, s)
        self.refresh_list()
        self.on_select(-1)

    # ---------- lista ----------
    def refresh_list(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        scr = self.canvas.screen
        if scr:
            for el in scr.elements:
                txt = el.label()
                if el.file != scr.file:
                    txt += "   ← %s()" % _owner_name(self.project, el)
                self.lst.addItem(txt)
        if 0 <= self.canvas.selected < self.lst.count():
            self.lst.setCurrentRow(self.canvas.selected)
        self.lst.blockSignals(False)

    def _row_changed(self, row):
        self.canvas.selected = row
        self.canvas.update()
        self.on_select(row)

    def _after_edit(self):
        self.refresh_list()
        self.on_select(self.canvas.selected)
        self.projectEdited.emit()

    # ---------- propiedades ----------
    def on_select(self, idx):
        while self.props.count():
            it = self.props.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        el = self.canvas.current()
        if el is None:
            self.src.setPlainText("")
            self.refresh_list()
            return

        self.src.setPlainText(_source_context(self.project, el))

        self.props.addRow("Llamada", QLabel(el.fn))
        if el.file != self.canvas.screen.file:
            lb = QLabel("vive en %s() de %s" %
                        (_owner_name(self.project, el), os.path.basename(el.file)))
            lb.setWordWrap(True)
            lb.setStyleSheet("color:#c39bff;")
            self.props.addRow("", lb)
        if el.repeats > 1:
            lb = QLabel("se dibuja %d veces (bucle); mover cambia las %d"
                        % (el.repeats, el.repeats))
            lb.setWordWrap(True)
            lb.setStyleSheet("color:#8fb7d9;")
            self.props.addRow("", lb)

        for _i, role in mpj.ARG_ROLES.get(el.kind, []):
            if role == "text":
                if el.is_literal_text():
                    ed = QLineEdit(cp.as_str(el.value("text")))
                    ed.editingFinished.connect(
                        lambda e=ed, r=role: self._set_text(r, e.text()))
                    self.props.addRow("texto", ed)
                else:
                    v = cp.as_str(el.value("text"))
                    lb = QLabel('%s  (calculado)' % v)
                    lb.setStyleSheet("color:#8a97a8;")
                    self.props.addRow("texto", lb)
                continue
            if role == "array":
                ed = QLineEdit(el.ident("array") or "")
                ed.editingFinished.connect(
                    lambda e=ed: self._set_text("array", e.text()))
                self.props.addRow("bitmap", ed)
                continue
            locked = el.locked(role)
            sp = _SelectAllSpinBox()
            sp.setRange(-512, 512)
            sp.setKeyboardTracking(False)
            sp.setValue(cp.as_int(el.value(role)))
            if locked:
                sp.setEnabled(False)
                sp.setToolTip("ese argumento no tiene ningun numero editable")
            else:
                sp.valueChanged.connect(lambda v, r=role: self._set_num(r, v))
            label = role
            if el.indirect(role):
                label += "  (via %s)" % el.var_name(role)
            self.props.addRow(label + ("  [fijo]" if locked else ""), sp)

        cb = QComboBox()
        for f in fonts.U8G2_FONTS:
            cb.addItem(f[0])
        cb.setCurrentText(el.font)
        cb.currentTextChanged.connect(self._set_font)
        if el.kind in ("text", "glyph"):
            self.props.addRow("fuente", cb)

        ck = QCheckBox("Color 1 (encendido)")
        ck.setChecked(bool(el.color))
        ck.toggled.connect(self._set_color)
        self.props.addRow("", ck)

    def _cur(self):
        return self.canvas.current()

    def _set_num(self, role, value):
        el = self._cur()
        if el is None:
            return
        if self.project.set_arg(el, role, value):
            self.canvas.refresh(keep=self.canvas.selected)
            self._after_edit()

    def _set_text(self, role, value):
        el = self._cur()
        if el is None:
            return
        if self.project.set_arg(el, role, value):
            self.canvas.refresh(keep=self.canvas.selected)
            self._reload_bitmaps()
            self._after_edit()

    def _set_font(self, name):
        el = self._cur()
        if el is None or name == el.font:
            return
        if self.project.set_font(el, name):
            self.canvas.refresh(keep=self.canvas.selected)
            self._after_edit()
        else:
            self.lb_status.setText("no encontre un setFont() que tocar antes de esa linea")

    def _set_color(self, on):
        el = self._cur()
        if el is None:
            return
        if self.project.set_color(el, 1 if on else 0):
            self.canvas.refresh(keep=self.canvas.selected)
            self._after_edit()

    # ---------- estructura ----------
    def add_element(self, kind):
        if not self.canvas.screen:
            return
        self.project.add_element(self.canvas.screen, kind, 4, 12 + 6 * (
            len(self.canvas.screen.elements) % 6))
        self.project.analyze()
        self.canvas.refresh()
        self.canvas.selected = len(self.canvas.elements()) - 1
        self._after_edit()
        self.canvas.update()

    def duplicate(self):
        el = self._cur()
        if el is None:
            return
        self.project.duplicate_element(el)
        self.canvas.refresh(keep=self.canvas.selected)
        self._after_edit()

    def delete(self):
        el = self._cur()
        if el is None:
            return
        if el.file != self.canvas.screen.file:
            r = QMessageBox.question(
                self, "Borrar",
                "Ese elemento vive en %s(). Borrarlo lo quita de TODAS las "
                "pantallas que llaman a esa funcion.\n\nSeguir?"
                % _owner_name(self.project, el),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        self.project.delete_element(el)
        self.canvas.refresh()
        self.canvas.selected = -1
        self._after_edit()
        self.canvas.update()

    def new_screen(self):
        if not self.project:
            return
        files = sorted(self.project.files, key=lambda p: (not p.endswith(".cpp"), p))
        if not files:
            return
        path, ok = QInputDialog.getItem(
            self, "Nueva pantalla", "En que archivo:",
            [os.path.basename(f) for f in files], 0, False)
        if not ok:
            return
        target = [f for f in files if os.path.basename(f) == path][0]
        name, ok = QInputDialog.getText(self, "Nueva pantalla",
                                        "Nombre de la funcion:", text="drawMiPantalla")
        if not ok or not name.strip():
            return
        self.project.add_screen_function(target, name.strip())
        self.refresh_tree()
        self.select_screen(name.strip())
        self.projectEdited.emit()


def _owner_name(project, el):
    if not project:
        return "?"
    best = None
    for name, fn in project.functions.items():
        if fn["file"] == el.file and fn["body_start"] <= el.site <= fn["body_end"]:
            if best is None or fn["body_start"] > project.functions[best]["body_start"]:
                best = name
    return best or "?"


def _source_context(project, el):
    if not project:
        return ""
    text = project.files.get(el.file, "")
    s, e = el.call_span
    ls = text.rfind("\n", 0, s) + 1
    le = text.find("\n", e)
    le = len(text) if le == -1 else le
    line_no = text.count("\n", 0, ls) + 1
    out = ["%s:%d" % (os.path.basename(el.file), line_no), text[ls:le].rstrip()]
    for role in ("x", "y"):
        if el.indirect(role):
            ast, fpath = el.edit_target(role)
            t2 = project.files.get(fpath, "")
            s2 = ast[-2]
            ls2 = t2.rfind("\n", 0, s2) + 1
            le2 = t2.find("\n", ast[-1])
            le2 = len(t2) if le2 == -1 else le2
            out.append("  %s viene de:  %s" % (role, t2[ls2:le2].strip()))
    return "\n".join(out)
