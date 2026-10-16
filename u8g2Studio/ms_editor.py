# -*- coding: utf-8 -*-
"""
ms_editor.py - Editor de pixel art 1-bit tipo Paint, con escritura
               directa sobre el arreglo XBM de un archivo .h.

u8g2 Studio - MIT License
"""

import os

from PyQt5.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal, QTimer
from PyQt5.QtGui import (QImage, QPainter, QColor, QPen, QBrush, QCursor,
                         QKeySequence, QIcon, QPixmap)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel,
    QPushButton, QToolButton, QButtonGroup, QSpinBox, QCheckBox, QComboBox,
    QLineEdit, QFileDialog, QMessageBox, QGroupBox, QSlider, QDialog,
    QDialogButtonBox, QSizePolicy, QScrollArea, QFrame, QInputDialog,
    QApplication, QSplitter
)

import ms_core as core
import ms_fonts as fonts


# ============================================================
#  Paletas
# ============================================================

THEMES = {
    "OLED azul": ("#0a0f1c", "#5ad8ff", "#16243a"),
    "OLED blanco": ("#000000", "#ffffff", "#1e1e1e"),
    "Papel": ("#ffffff", "#000000", "#c8c8c8"),
    "Ambar": ("#120b00", "#ffb400", "#332200"),
}


# ============================================================
#  Lienzo de pixeles
# ============================================================

class PixelCanvas(QWidget):

    statusChanged = pyqtSignal(str)
    modified = pyqtSignal()
    colorPicked = pyqtSignal(int)

    TOOLS = ("pencil", "eraser", "line", "rect", "rectfill",
             "ellipse", "ellipsefill", "bucket", "text", "select", "picker")

    def __init__(self, bitmap=None, parent=None):
        QWidget.__init__(self, parent)
        self.bm = bitmap or core.Bitmap(128, 64)
        self.zoom = 6
        self.show_grid = True
        self.show_ruler8 = True
        self.tool = "pencil"
        self.draw_value = 1
        self.theme = "OLED azul"
        self.text_value = "TEXTO"
        self.text_font = fonts.DEFAULT_FONT

        self._img = None
        self._dirty = True
        self._drag = None          # (x0,y0) inicio de la figura
        self._last = None          # ultimo pixel pintado (lapiz)
        self._preview = None       # Bitmap temporal mientras se arrastra
        self._sel = None           # QRect de seleccion (en pixeles)
        self._sel_drag = None
        self._sel_buf = None       # Bitmap flotante que se mueve
        self._clip = None          # portapapeles interno

        self._undo = []
        self._redo = []
        self._undo_limit = 120

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        self._update_size()

    # ---------- geometria ----------
    def _update_size(self):
        w = self.bm.width * self.zoom + 1
        h = self.bm.height * self.zoom + 1
        self.setFixedSize(w, h)
        self._dirty = True
        self.update()

    def set_zoom(self, z):
        self.zoom = max(1, min(40, int(z)))
        self._update_size()

    def pix_at(self, pos):
        x = int(pos.x() // self.zoom)
        y = int(pos.y() // self.zoom)
        return x, y

    # ---------- undo ----------
    def push_undo(self):
        self._undo.append(self.bm.snapshot())
        if len(self._undo) > self._undo_limit:
            self._undo.pop(0)
        self._redo = []

    def undo(self):
        if not self._undo:
            return
        self._redo.append(self.bm.snapshot())
        self.bm.restore(self._undo.pop())
        self._after_change()

    def redo(self):
        if not self._redo:
            return
        self._undo.append(self.bm.snapshot())
        self.bm.restore(self._redo.pop())
        self._after_change()

    def _after_change(self):
        self._dirty = True
        self._update_size()
        self.modified.emit()
        self.update()

    # ---------- bitmap ----------
    def set_bitmap(self, bm, keep_undo=False):
        if keep_undo:
            self.push_undo()
        self.bm = bm
        self._sel = None
        self._sel_buf = None
        self._after_change()

    def active_bitmap(self):
        return self._preview if self._preview is not None else self.bm

    # ---------- pintado ----------
    def _build_image(self):
        bg, fg, _ = THEMES.get(self.theme, THEMES["OLED azul"])
        src = self.active_bitmap()
        self._img = core.bitmap_to_qimage(src, QColor(bg).rgb(), QColor(fg).rgb())
        self._dirty = False

    def paintEvent(self, ev):
        if self._dirty or self._img is None or self._preview is not None:
            self._build_image()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        src = self.active_bitmap()
        target = QRect(0, 0, src.width * self.zoom, src.height * self.zoom)
        p.drawImage(target, self._img)

        _, _, grid = THEMES.get(self.theme, THEMES["OLED azul"])
        if self.show_grid and self.zoom >= 4:
            p.setPen(QPen(QColor(grid), 1))
            for x in range(src.width + 1):
                p.drawLine(x * self.zoom, 0, x * self.zoom, src.height * self.zoom)
            for y in range(src.height + 1):
                p.drawLine(0, y * self.zoom, src.width * self.zoom, y * self.zoom)

        if self.show_ruler8 and self.zoom >= 3:
            p.setPen(QPen(QColor(120, 160, 200, 170), 1))
            for x in range(0, src.width + 1, 8):
                p.drawLine(x * self.zoom, 0, x * self.zoom, src.height * self.zoom)
            for y in range(0, src.height + 1, 8):
                p.drawLine(0, y * self.zoom, src.width * self.zoom, y * self.zoom)

        # seleccion
        if self._sel is not None:
            r = QRect(self._sel.x() * self.zoom, self._sel.y() * self.zoom,
                      self._sel.width() * self.zoom, self._sel.height() * self.zoom)
            pen = QPen(QColor(255, 200, 0), 1, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)

        p.end()

    # ---------- eventos ----------
    def mousePressEvent(self, ev):
        x, y = self.pix_at(ev.pos())
        val = 1 if ev.button() == Qt.LeftButton else 0
        if ev.button() == Qt.MiddleButton:
            return
        self.draw_value = val

        if self.tool == "picker":
            self.colorPicked.emit(self.bm.get(x, y))
            return

        if self.tool == "select":
            if (self._sel is not None and self._sel.contains(x, y)
                    and ev.button() == Qt.LeftButton):
                # empezar a mover el contenido de la seleccion
                self.push_undo()
                r = self._sel
                self._sel_buf = self.bm.sub(r.x(), r.y(), r.width(), r.height())
                self.bm.draw_rect(r.x(), r.y(), r.right(), r.bottom(), 0, fill=True)
                self._sel_drag = (x, y, r.x(), r.y())
            else:
                self._sel = QRect(x, y, 1, 1)
                self._drag = (x, y)
            self._dirty = True
            self.update()
            return

        if self.tool == "text":
            self.push_undo()
            fonts.draw_text_on_bitmap(self.bm, self.text_value, x, y,
                                      self.text_font, val)
            self._after_change()
            return

        self.push_undo()

        if self.tool == "pencil":
            self.bm.set(x, y, val)
            self._last = (x, y)
            self._after_change()
        elif self.tool == "eraser":
            self.bm.set(x, y, 0)
            self._last = (x, y)
            self._after_change()
        elif self.tool == "bucket":
            self.bm.flood_fill(x, y, val)
            self._after_change()
        else:
            self._drag = (x, y)
            self._preview = self.bm.clone()

    def mouseMoveEvent(self, ev):
        x, y = self.pix_at(ev.pos())
        self.statusChanged.emit("x=%d  y=%d   (%dx%d)" % (x, y, self.bm.width, self.bm.height))

        buttons = ev.buttons()
        if not (buttons & (Qt.LeftButton | Qt.RightButton)):
            return

        if self.tool in ("pencil", "eraser") and self._last is not None:
            v = 0 if self.tool == "eraser" else self.draw_value
            self.bm.draw_line(self._last[0], self._last[1], x, y, v)
            self._last = (x, y)
            self._dirty = True
            self.update()
            return

        if self.tool == "select":
            if self._sel_drag is not None and self._sel_buf is not None:
                sx, sy, rx, ry = self._sel_drag
                self._sel = QRect(rx + (x - sx), ry + (y - sy),
                                  self._sel.width(), self._sel.height())
                self._preview = self.bm.clone()
                self._preview.blit(self._sel_buf, self._sel.x(), self._sel.y(), "or")
                self._dirty = True
                self.update()
            elif self._drag is not None:
                x0, y0 = self._drag
                self._sel = QRect(min(x0, x), min(y0, y),
                                  abs(x - x0) + 1, abs(y - y0) + 1)
                self._dirty = True
                self.update()
            return

        if self._drag is not None and self._preview is not None:
            x0, y0 = self._drag
            self._preview = self.bm.clone()
            v = self.draw_value
            if self.tool == "line":
                self._preview.draw_line(x0, y0, x, y, v)
            elif self.tool == "rect":
                self._preview.draw_rect(x0, y0, x, y, v, fill=False)
            elif self.tool == "rectfill":
                self._preview.draw_rect(x0, y0, x, y, v, fill=True)
            elif self.tool == "ellipse":
                self._preview.draw_ellipse(x0, y0, x, y, v, fill=False)
            elif self.tool == "ellipsefill":
                self._preview.draw_ellipse(x0, y0, x, y, v, fill=True)
            self._dirty = True
            self.update()

    def mouseReleaseEvent(self, ev):
        if self.tool == "select":
            if self._sel_drag is not None and self._sel_buf is not None:
                self.bm.blit(self._sel_buf, self._sel.x(), self._sel.y(), "or")
                self._sel_drag = None
                self._sel_buf = None
                self._preview = None
                self._after_change()
            self._drag = None
            return

        if self._preview is not None:
            self.bm = self._preview
            self._preview = None
            self._after_change()
        self._drag = None
        self._last = None

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom + (1 if ev.angleDelta().y() > 0 else -1))
            ev.accept()
        else:
            ev.ignore()

    def keyPressEvent(self, ev):
        k = ev.key()
        if k == Qt.Key_Delete and self._sel is not None:
            self.push_undo()
            r = self._sel
            self.bm.draw_rect(r.x(), r.y(), r.right(), r.bottom(), 0, fill=True)
            self._after_change()
        elif ev.matches(QKeySequence.Copy) and self._sel is not None:
            r = self._sel
            self._clip = self.bm.sub(r.x(), r.y(), r.width(), r.height())
        elif ev.matches(QKeySequence.Cut) and self._sel is not None:
            r = self._sel
            self._clip = self.bm.sub(r.x(), r.y(), r.width(), r.height())
            self.push_undo()
            self.bm.draw_rect(r.x(), r.y(), r.right(), r.bottom(), 0, fill=True)
            self._after_change()
        elif ev.matches(QKeySequence.Paste) and self._clip is not None:
            self.push_undo()
            ox = self._sel.x() if self._sel else 0
            oy = self._sel.y() if self._sel else 0
            self.bm.blit(self._clip, ox, oy, "or")
            self._after_change()
        elif k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            d = 1 if not (ev.modifiers() & Qt.ShiftModifier) else 8
            dx = -d if k == Qt.Key_Left else (d if k == Qt.Key_Right else 0)
            dy = -d if k == Qt.Key_Up else (d if k == Qt.Key_Down else 0)
            self.push_undo()
            self.bm.shift(dx, dy, wrap=bool(ev.modifiers() & Qt.AltModifier))
            self._after_change()
        else:
            QWidget.keyPressEvent(self, ev)


# ============================================================
#  Vista previa 1:1
# ============================================================

class PreviewWidget(QWidget):
    def __init__(self, canvas, scale=1, parent=None):
        QWidget.__init__(self, parent)
        self.canvas = canvas
        self.scale = scale
        self.setFixedSize(canvas.bm.width * scale + 8, canvas.bm.height * scale + 8)

    def sizeHint(self):
        return QSize(self.canvas.bm.width * self.scale + 8,
                     self.canvas.bm.height * self.scale + 8)

    def paintEvent(self, ev):
        bm = self.canvas.active_bitmap()
        self.setFixedSize(bm.width * self.scale + 8, bm.height * self.scale + 8)
        bg, fg, _ = THEMES.get(self.canvas.theme, THEMES["OLED azul"])
        img = core.bitmap_to_qimage(bm, QColor(bg).rgb(), QColor(fg).rgb())
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(self.rect(), QColor(bg))
        target = QRect(4, 4, bm.width * self.scale, bm.height * self.scale)
        p.drawImage(target, img)
        p.end()


# ============================================================
#  Dialogo de importacion de imagen
# ============================================================

class ImportImageDialog(QDialog):

    def __init__(self, width, height, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("Importar imagen")
        self.resize(560, 480)
        self.path = None
        self.result_bitmap = None
        self.w = width
        self.h = height

        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.ed_path = QLineEdit()
        self.ed_path.setPlaceholderText("PNG / JPG / BMP / GIF ...")
        b = QPushButton("Abrir...")
        b.clicked.connect(self.pick)
        row.addWidget(self.ed_path, 1)
        row.addWidget(b)
        lay.addLayout(row)

        form = QFormLayout()
        self.sp_w = QSpinBox(); self.sp_w.setRange(1, 512); self.sp_w.setValue(width)
        self.sp_h = QSpinBox(); self.sp_h.setRange(1, 512); self.sp_h.setValue(height)
        self.cb_fit = QComboBox(); self.cb_fit.addItems(["contain", "cover", "stretch"])
        self.sl_th = QSlider(Qt.Horizontal); self.sl_th.setRange(1, 254); self.sl_th.setValue(128)
        self.lb_th = QLabel("128")
        self.ck_dither = QCheckBox("Dithering Floyd-Steinberg")
        self.ck_invert = QCheckBox("Invertir")

        hb = QHBoxLayout(); hb.addWidget(self.sl_th, 1); hb.addWidget(self.lb_th)
        form.addRow("Ancho", self.sp_w)
        form.addRow("Alto", self.sp_h)
        form.addRow("Ajuste", self.cb_fit)
        form.addRow("Umbral", hb)
        form.addRow("", self.ck_dither)
        form.addRow("", self.ck_invert)
        lay.addLayout(form)

        self.preview = QLabel("sin imagen")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(180)
        self.preview.setStyleSheet("background:#0a0f1c;border:1px solid #24344c;")
        lay.addWidget(self.preview, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

        for w in (self.sp_w, self.sp_h):
            w.valueChanged.connect(self.refresh)
        self.cb_fit.currentIndexChanged.connect(self.refresh)
        self.sl_th.valueChanged.connect(self.refresh)
        self.ck_dither.toggled.connect(self.refresh)
        self.ck_invert.toggled.connect(self.refresh)

    def pick(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Imagen", "", "Imagenes (*.png *.jpg *.jpeg *.bmp *.gif);;Todos (*)")
        if p:
            self.path = p
            self.ed_path.setText(p)
            self.refresh()

    def refresh(self):
        self.lb_th.setText(str(self.sl_th.value()))
        if not self.path:
            return
        try:
            bm = core.image_to_bitmap(
                self.path, self.sp_w.value(), self.sp_h.value(),
                threshold=self.sl_th.value(), dither=self.ck_dither.isChecked(),
                invert=self.ck_invert.isChecked(), fit=self.cb_fit.currentText())
        except Exception as e:
            self.preview.setText(str(e))
            return
        self.result_bitmap = bm

        img = core.bitmap_to_qimage(bm, QColor("#0a0f1c").rgb(), QColor("#5ad8ff").rgb())
        scale = max(1, min(6, 640 // max(1, bm.width)))
        pm = QPixmap.fromImage(img).scaled(bm.width * scale, bm.height * scale,
                                           Qt.KeepAspectRatio, Qt.FastTransformation)
        self.preview.setPixmap(pm)


# ============================================================
#  Pestana completa del editor
# ============================================================

class EditorTab(QWidget):

    TOOL_LABELS = [
        ("pencil",      "Lapiz",        "P"),
        ("eraser",      "Borrador",     "E"),
        ("line",        "Linea",        "L"),
        ("rect",        "Rect",         "R"),
        ("rectfill",    "Rect lleno",   "F"),
        ("ellipse",     "Elipse",       "O"),
        ("ellipsefill", "Elipse llena", "D"),
        ("bucket",      "Relleno",      "B"),
        ("text",        "Texto",        "T"),
        ("select",      "Seleccion",    "S"),
        ("picker",      "Cuentagotas",  "I"),
    ]

    bitmapChanged = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.project = None
        self.cur_file = None
        self.cur_array = None
        self._loading = False
        self._dirty = False

        self.canvas = PixelCanvas(core.Bitmap(128, 64))
        self.canvas.modified.connect(self._on_modified)

        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # ---------- columna izquierda: herramientas ----------
        left = QVBoxLayout()
        gb_tools = QGroupBox("Herramientas")
        gl = QGridLayout(gb_tools)
        gl.setSpacing(3)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        for i, (tid, label, key) in enumerate(self.TOOL_LABELS):
            b = QToolButton()
            b.setText("%s  (%s)" % (label, key))
            b.setCheckable(True)
            b.setMinimumWidth(140)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setProperty("tool", tid)
            if tid == "pencil":
                b.setChecked(True)
            self.tool_group.addButton(b, i)
            gl.addWidget(b, i, 0)
        self.tool_group.buttonClicked.connect(self._tool_clicked)
        left.addWidget(gb_tools)

        gb_text = QGroupBox("Herramienta texto")
        fl = QFormLayout(gb_text)
        self.ed_text = QLineEdit("Texto")
        self.cb_font = QComboBox()
        for f in fonts.U8G2_FONTS:
            self.cb_font.addItem(f[0])
        self.cb_font.setCurrentText(fonts.DEFAULT_FONT)
        self.ed_text.textChanged.connect(
            lambda s: setattr(self.canvas, "text_value", s))
        self.cb_font.currentTextChanged.connect(
            lambda s: setattr(self.canvas, "text_font", s))
        fl.addRow("Texto", self.ed_text)
        fl.addRow("Fuente", self.cb_font)
        left.addWidget(gb_text)
        left.addStretch(1)

        lw = QWidget(); lw.setLayout(left); lw.setFixedWidth(196)
        root.addWidget(lw)

        # ---------- centro: lienzo ----------
        center = QVBoxLayout()

        bar = QHBoxLayout()
        self.sp_zoom = QSpinBox(); self.sp_zoom.setRange(1, 40); self.sp_zoom.setValue(6)
        self.sp_zoom.setPrefix("zoom x")
        self.sp_zoom.valueChanged.connect(self.canvas.set_zoom)
        self.ck_grid = QCheckBox("Rejilla"); self.ck_grid.setChecked(True)
        self.ck_grid.toggled.connect(self._set_grid)
        self.ck_r8 = QCheckBox("Guias /8"); self.ck_r8.setChecked(True)
        self.ck_r8.toggled.connect(self._set_ruler)
        self.cb_theme = QComboBox(); self.cb_theme.addItems(list(THEMES.keys()))
        self.cb_theme.currentTextChanged.connect(self._set_theme)
        bar.addWidget(self.sp_zoom)
        bar.addWidget(self.ck_grid)
        bar.addWidget(self.ck_r8)
        bar.addWidget(QLabel("Tema:"))
        bar.addWidget(self.cb_theme)
        bar.addStretch(1)
        b_undo = QPushButton("Deshacer"); b_undo.clicked.connect(self.canvas.undo)
        b_redo = QPushButton("Rehacer"); b_redo.clicked.connect(self.canvas.redo)
        bar.addWidget(b_undo); bar.addWidget(b_redo)
        center.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setAlignment(Qt.AlignCenter)
        scroll.setBackgroundRole(scroll.backgroundRole())
        center.addWidget(scroll, 1)

        self.lb_status = QLabel("listo")
        self.canvas.statusChanged.connect(self.lb_status.setText)
        center.addWidget(self.lb_status)

        root.addLayout(center, 1)

        # ---------- columna derecha ----------
        right = QVBoxLayout()

        gb_prev = QGroupBox("Vista 1:1")
        pv = QVBoxLayout(gb_prev)
        self.preview = PreviewWidget(self.canvas, 1)
        self.preview2 = PreviewWidget(self.canvas, 2)
        pv.addWidget(self.preview, 0, Qt.AlignCenter)
        pv.addWidget(self.preview2, 0, Qt.AlignCenter)
        right.addWidget(gb_prev)

        gb_img = QGroupBox("Lienzo")
        il = QFormLayout(gb_img)
        self.sp_w = QSpinBox(); self.sp_w.setRange(1, 512); self.sp_w.setValue(128)
        self.sp_h = QSpinBox(); self.sp_h.setRange(1, 512); self.sp_h.setValue(64)
        b_res = QPushButton("Redimensionar")
        b_res.clicked.connect(self.do_resize)
        il.addRow("Ancho", self.sp_w)
        il.addRow("Alto", self.sp_h)
        il.addRow(b_res)
        right.addWidget(gb_img)

        gb_ops = QGroupBox("Operaciones")
        og = QGridLayout(gb_ops)
        ops = [
            ("Invertir", self.op_invert),
            ("Limpiar", self.op_clear),
            ("Llenar", self.op_fill),
            ("Espejo H", self.op_fliph),
            ("Espejo V", self.op_flipv),
            ("Desplazar...", self.op_shift),
        ]
        for i, (label, fn) in enumerate(ops):
            b = QPushButton(label)
            b.clicked.connect(fn)
            og.addWidget(b, i // 2, i % 2)
        right.addWidget(gb_ops)

        gb_io = QGroupBox("Bitmaps del proyecto")
        iol = QVBoxLayout(gb_io)
        self.cb_bitmap = QComboBox()
        self.cb_bitmap.setToolTip("Todos los arreglos de bytes que encontre "
                                  "en la carpeta del sketch")
        self.cb_bitmap.currentIndexChanged.connect(self._bitmap_selected)
        iol.addWidget(self.cb_bitmap)
        self.lb_where = QLabel("sin proyecto")
        self.lb_where.setWordWrap(True)
        self.lb_where.setStyleSheet("color:#8fb7d9;")
        iol.addWidget(self.lb_where)
        right.addWidget(gb_io)

        gb_ie = QGroupBox("Importar / Exportar")
        iel = QVBoxLayout(gb_ie)
        for label, fn in [("Importar imagen...", self.import_image),
                          ("Exportar PNG...", self.export_png),
                          ("Copiar arreglo C", self.copy_array),
                          ("Pegar arreglo C...", self.paste_array)]:
            b = QPushButton(label); b.clicked.connect(fn)
            iel.addWidget(b)
        right.addWidget(gb_ie)
        right.addStretch(1)

        rw = QWidget(); rw.setLayout(right); rw.setFixedWidth(270)
        root.addWidget(rw)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_previews)
        self._timer.start(120)

    # ---------- helpers ----------
    def _refresh_previews(self):
        self.preview.update()
        self.preview2.update()

    def _tool_clicked(self, btn):
        self.canvas.tool = btn.property("tool")

    def set_tool(self, tid):
        for b in self.tool_group.buttons():
            if b.property("tool") == tid:
                b.setChecked(True)
                self.canvas.tool = tid
                return

    def _set_grid(self, v):
        self.canvas.show_grid = v
        self.canvas.update()

    def _set_ruler(self, v):
        self.canvas.show_ruler8 = v
        self.canvas.update()

    def _set_theme(self, name):
        self.canvas.theme = name
        self.canvas._dirty = True
        self.canvas.update()

    def _on_modified(self):
        if self._loading:
            return
        self._dirty = True
        self.bitmapChanged.emit()

    def bitmap(self):
        return self.canvas.bm

    # ---------- operaciones ----------
    def op_invert(self):
        self.canvas.push_undo(); self.canvas.bm.invert(); self.canvas._after_change()

    def op_clear(self):
        self.canvas.push_undo(); self.canvas.bm.clear(0); self.canvas._after_change()

    def op_fill(self):
        self.canvas.push_undo(); self.canvas.bm.clear(1); self.canvas._after_change()

    def op_fliph(self):
        self.canvas.push_undo(); self.canvas.bm.flip_h(); self.canvas._after_change()

    def op_flipv(self):
        self.canvas.push_undo(); self.canvas.bm.flip_v(); self.canvas._after_change()

    def op_shift(self):
        dx, ok = QInputDialog.getInt(self, "Desplazar", "dx (pixeles)", 0, -256, 256)
        if not ok:
            return
        dy, ok = QInputDialog.getInt(self, "Desplazar", "dy (pixeles)", 0, -256, 256)
        if not ok:
            return
        self.canvas.push_undo()
        self.canvas.bm.shift(dx, dy)
        self.canvas._after_change()

    def do_resize(self):
        self.canvas.push_undo()
        self.canvas.bm.resize(self.sp_w.value(), self.sp_h.value())
        self.canvas._after_change()

    # ---------- proyecto / bitmaps ----------
    def set_project(self, project):
        self.project = project
        self.refresh_bitmap_list()

    def refresh_bitmap_list(self):
        self._loading = True
        self.cb_bitmap.clear()
        if self.project:
            for path, name, nbytes, nframes in self.project.bitmaps:
                if nframes == 1:
                    self.cb_bitmap.addItem(
                        "%s   -   %s  (%d B)" % (name, os.path.basename(path), nbytes),
                        (path, name))
                else:
                    for k in range(nframes):
                        self.cb_bitmap.addItem(
                            "%s[%d]   -   %s  (%d B)"
                            % (name, k, os.path.basename(path), nbytes),
                            (path, "%s[%d]" % (name, k)))
        self._loading = False
        if self.cb_bitmap.count():
            self.cb_bitmap.setCurrentIndex(self._best_index())
            self._bitmap_selected(self.cb_bitmap.currentIndex())
        else:
            self.lb_where.setText("no encontre arreglos de bytes en la carpeta")

    def _best_index(self):
        """El arreglo mas grande suele ser el arte."""
        best, bestn = 0, -1
        for i in range(self.cb_bitmap.count()):
            path, ref = self.cb_bitmap.itemData(i)
            name, _f = core.parse_array_ref(ref)
            for p, n, nb, nf in self.project.bitmaps:
                if p == path and n == name and nb > bestn:
                    bestn, best = nb, i
        return best

    def _bitmap_selected(self, idx):
        if self._loading or idx < 0 or not self.project:
            return
        data = self.cb_bitmap.itemData(idx)
        if not data:
            return
        path, ref = data
        try:
            bm, nframes = self.project.load_bitmap(path, ref)
        except Exception as e:
            self.lb_where.setText("error: %s" % e)
            return
        self.cur_file, self.cur_array = path, ref
        self._loading = True
        self.sp_w.setValue(bm.width)
        self.sp_h.setValue(bm.height)
        self.canvas.set_bitmap(bm)
        self.canvas._undo = []
        self.canvas._redo = []
        self._loading = False
        self._dirty = False          # cargar no es editar
        self.lb_where.setText("%s  en  %s\n%dx%d  -  %d bytes"
                              % (ref, os.path.basename(path),
                                 bm.width, bm.height, len(bm.data)))

    def commit(self):
        """Escribe el bitmap actual al buffer del proyecto (no al disco)."""
        if not self.project or not self.cur_file or not self.cur_array:
            return False
        try:
            self.project.save_bitmap(self.cur_file, self.cur_array, self.canvas.bm)
        except Exception as e:
            QMessageBox.critical(self, "Aplicar", str(e))
            return False
        self.lb_where.setText("%s  en  %s   (pendiente de Ctrl+S)"
                              % (self.cur_array, os.path.basename(self.cur_file)))
        return True

    def reload_current(self):
        self._bitmap_selected(self.cb_bitmap.currentIndex())

    def import_image(self):
        if not core.HAS_PIL:
            QMessageBox.warning(self, "Importar",
                                "Falta Pillow.\n\npip install Pillow")
            return
        d = ImportImageDialog(self.canvas.bm.width, self.canvas.bm.height, self)
        if d.exec_() == QDialog.Accepted and d.result_bitmap is not None:
            self.canvas.set_bitmap(d.result_bitmap, keep_undo=True)
            self.sp_w.setValue(d.result_bitmap.width)
            self.sp_h.setValue(d.result_bitmap.height)

    def export_png(self):
        if not core.HAS_PIL:
            QMessageBox.warning(self, "Exportar", "Falta Pillow.\n\npip install Pillow")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Exportar PNG", "pixelart.png",
                                           "PNG (*.png)")
        if not p:
            return
        core.bitmap_to_png(self.canvas.bm, p, scale=4)
        QMessageBox.information(self, "Exportar", "Guardado:\n%s" % p)

    def copy_array(self):
        name = core.parse_array_ref(self.cur_array or "bitmap")[0]
        txt = self.canvas.bm.to_c_array(name)
        QApplication.clipboard().setText(txt)
        self.lb_status.setText("Arreglo C copiado al portapapeles")

    def paste_array(self):
        txt, ok = QInputDialog.getMultiLineText(
            self, "Pegar arreglo C",
            "Pega aqui los bytes (con o sin llaves):", "")
        if not ok or not txt.strip():
            return
        vals = core.parse_bytes(txt)
        if not vals:
            QMessageBox.warning(self, "Pegar", "No encontre bytes validos.")
            return
        w = self.sp_w.value()
        h = self.sp_h.value()
        bpr = (w + 7) // 8
        if len(vals) != bpr * h:
            guess_h = len(vals) // bpr if bpr else 0
            r = QMessageBox.question(
                self, "Pegar",
                "Recibi %d bytes; para %dx%d esperaba %d.\n"
                "Uso alto = %d?" % (len(vals), w, h, bpr * h, guess_h),
                QMessageBox.Yes | QMessageBox.No)
            if r == QMessageBox.Yes and guess_h > 0:
                h = guess_h
                self.sp_h.setValue(h)
        self.canvas.set_bitmap(core.Bitmap(w, h, bytearray(vals)), keep_undo=True)
