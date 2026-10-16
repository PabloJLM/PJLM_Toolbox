"""Editor de codigo: numeros de linea, resaltado C/C++/INI/Python, autoindentado,
comentar lineas, busqueda e imagen de fondo opcional."""
from __future__ import annotations

import re
from pathlib import Path

from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QPainter, QPixmap, QSyntaxHighlighter,
                         QTextCharFormat, QTextCursor, QTextDocument, QTextFormat)
from PyQt5.QtWidgets import (QCheckBox, QHBoxLayout, QLineEdit, QPlainTextEdit,
                             QPushButton, QTextEdit, QToolButton, QWidget)

# --------------------------------------------------------------- resaltado

_CPP_PALABRAS = (
    "alignas alignof asm auto break case catch class const constexpr const_cast continue "
    "decltype default delete do dynamic_cast else enum explicit export extern false final for "
    "friend goto if inline mutable namespace new noexcept nullptr operator override private "
    "protected public register reinterpret_cast return sizeof static static_assert static_cast "
    "struct switch template this throw true try typedef typeid typename union using virtual "
    "volatile while HIGH LOW INPUT OUTPUT INPUT_PULLUP INPUT_PULLDOWN LED_BUILTIN NULL"
).split()
_CPP_TIPOS = (
    "void bool char short int long float double signed unsigned size_t wchar_t "
    "String byte word boolean uint8_t uint16_t uint32_t uint64_t int8_t int16_t int32_t "
    "int64_t uintptr_t intptr_t esp_err_t TaskHandle_t QueueHandle_t SemaphoreHandle_t"
).split()
_PY_PALABRAS = (
    "and as assert async await break class continue def del elif else except False finally "
    "for from global if import in is lambda None nonlocal not or pass raise return True try "
    "while with yield self"
).split()


def _rx_palabras(lista):
    return re.compile(r"\b(?:" + "|".join(lista) + r")\b")


_RX_NUM = re.compile(r"\b(?:0[xX][0-9A-Fa-f']+|0[bB][01']+|\d[\d']*(?:\.\d+)?(?:[eE][+-]?\d+)?)[uUlLfF]*\b")
_RX_FUNC = re.compile(r"\b[A-Za-z_]\w*(?=\s*\()")
_RX_CPP_PAL = _rx_palabras(_CPP_PALABRAS)
_RX_CPP_TIP = _rx_palabras(_CPP_TIPOS)
_RX_PRE = re.compile(r"^\s*#\s*[A-Za-z_]+")
_RX_INCLUDE = re.compile(r"^\s*#\s*include\s*(<[^>]*>)")
_RX_CPP_TOK = re.compile(r'"(?:\\.|[^"\\])*"?|\'(?:\\.|[^\'\\])*\'?|//|/\*')
_RX_INI_SEC = re.compile(r"^\s*\[[^\]]*\]")
_RX_INI_CLAVE = re.compile(r"^\s*[\w.\-]+(?=\s*=)")
_RX_INI_VAR = re.compile(r"\$\{[^}]*\}")
_RX_INI_COM = re.compile(r"(?:^|\s)[;#].*$")
_RX_PY_PAL = _rx_palabras(_PY_PALABRAS)
_RX_PY_TOK = re.compile(r'"(?:\\.|[^"\\])*"?|\'(?:\\.|[^\'\\])*\'?|#')

_EXT_CPP = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".ino", ".s", ".S"}
_EXT_INI = {".ini", ".cfg", ".conf", ".properties", ".csv"}


def lenguaje_por_ruta(ruta: str | None) -> str:
    if not ruta:
        return "cpp"
    suf = Path(ruta).suffix
    if suf in _EXT_CPP or suf.lower() in _EXT_CPP:
        return "cpp"
    if suf.lower() in _EXT_INI:
        return "ini"
    if suf.lower() == ".py":
        return "py"
    return "texto"


def _formato(color: str, cursiva: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if cursiva:
        f.setFontItalic(True)
    return f


class Resaltador(QSyntaxHighlighter):
    def __init__(self, documento, lenguaje: str, colores: dict):
        super().__init__(documento)
        self.lenguaje = lenguaje
        self.f: dict[str, QTextCharFormat] = {}
        self.reglas: list = []
        self.set_colores(colores)

    def set_colores(self, c: dict):
        self.f = {k: _formato(v, cursiva=(k == "comentarios")) for k, v in c.items()}
        f = self.f
        if self.lenguaje == "cpp":
            self.reglas = [(_RX_FUNC, f["funciones"], 0), (_RX_CPP_TIP, f["tipos"], 0),
                           (_RX_CPP_PAL, f["palabras_clave"], 0), (_RX_NUM, f["numeros"], 0),
                           (_RX_PRE, f["preprocesador"], 0), (_RX_INCLUDE, f["cadenas"], 1)]
        elif self.lenguaje == "ini":
            self.reglas = [(_RX_INI_CLAVE, f["tipos"], 0), (_RX_NUM, f["numeros"], 0),
                           (_RX_INI_VAR, f["preprocesador"], 0), (_RX_INI_SEC, f["palabras_clave"], 0)]
        elif self.lenguaje == "py":
            self.reglas = [(_RX_FUNC, f["funciones"], 0), (_RX_PY_PAL, f["palabras_clave"], 0),
                           (_RX_NUM, f["numeros"], 0)]
        else:
            self.reglas = []
        self.rehighlight()

    def highlightBlock(self, texto: str):
        for rx, fmt, grupo in self.reglas:
            for m in rx.finditer(texto):
                self.setFormat(m.start(grupo), m.end(grupo) - m.start(grupo), fmt)
        if self.lenguaje == "cpp":
            self._tokens_cpp(texto)
        elif self.lenguaje == "ini":
            m = _RX_INI_COM.search(texto)
            if m:
                self.setFormat(m.start(), len(texto) - m.start(), self.f["comentarios"])
        elif self.lenguaje == "py":
            self._tokens_simples(texto, _RX_PY_TOK, "#")

    def _tokens_simples(self, texto, rx, marca_com):
        i = 0
        while True:
            m = rx.search(texto, i)
            if not m:
                return
            if m.group() == marca_com:
                self.setFormat(m.start(), len(texto) - m.start(), self.f["comentarios"])
                return
            self.setFormat(m.start(), m.end() - m.start(), self.f["cadenas"])
            i = m.end()

    def _tokens_cpp(self, texto):
        com, cad = self.f["comentarios"], self.f["cadenas"]
        i = 0
        if self.previousBlockState() == 1:
            fin = texto.find("*/")
            if fin < 0:
                self.setFormat(0, len(texto), com)
                self.setCurrentBlockState(1)
                return
            self.setFormat(0, fin + 2, com)
            i = fin + 2
        self.setCurrentBlockState(0)
        while i < len(texto):
            m = _RX_CPP_TOK.search(texto, i)
            if not m:
                return
            tok, ini = m.group(), m.start()
            if tok == "/*":
                fin = texto.find("*/", ini + 2)
                if fin < 0:
                    self.setFormat(ini, len(texto) - ini, com)
                    self.setCurrentBlockState(1)
                    return
                self.setFormat(ini, fin + 2 - ini, com)
                i = fin + 2
            elif tok == "//":
                self.setFormat(ini, len(texto) - ini, com)
                return
            else:
                self.setFormat(ini, len(tok), cad)
                i = m.end()


# --------------------------------------------------------------- editor

class _Margen(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.ancho_margen(), 0)

    def paintEvent(self, evento):
        self.editor.pintar_margen(evento)


_COMENTARIO = {"cpp": "//", "ini": ";", "py": "#", "texto": "#"}


class EditorCodigo(QPlainTextEdit):
    posicion = pyqtSignal(int, int)

    def __init__(self, ruta: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("editor")
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFrameShape(QPlainTextEdit.NoFrame)
        self.ruta = ruta
        self.fin_linea = "\n"
        self.lenguaje = lenguaje_por_ruta(ruta)
        self.sangria = 2
        self.colores = {"fondo_editor": "#0F111A", "texto_editor": "#D6DEEB",
                        "linea_actual": "#161A28", "num_linea": "#3B4261"}
        self._bg_origen: QPixmap | None = None
        self._bg_cache: QPixmap | None = None
        self._bg_activo = False
        self._bg_opacidad = 0.15

        self.margen = _Margen(self)
        self.resaltador = Resaltador(self.document(), self.lenguaje,
                                     {"palabras_clave": "#BB9AF7", "tipos": "#7AA2F7",
                                      "funciones": "#7DCFFF", "numeros": "#FF9E64",
                                      "cadenas": "#9ECE6A", "preprocesador": "#F7768E",
                                      "comentarios": "#565F89"})
        self.blockCountChanged.connect(self._ajustar_margen)
        self.updateRequest.connect(self._actualizar_margen)
        self.cursorPositionChanged.connect(self._linea_actual)
        self.verticalScrollBar().valueChanged.connect(self._repintar_si_fondo)
        self.horizontalScrollBar().valueChanged.connect(self._repintar_si_fondo)
        self._ajustar_margen()
        self._linea_actual()

    # ---- archivo
    def cargar(self):
        crudo = Path(self.ruta).read_bytes()
        self.fin_linea = "\r\n" if b"\r\n" in crudo else "\n"
        texto = crudo.decode("utf-8", errors="replace").replace("\r\n", "\n")
        self.setPlainText(texto)
        self.document().setModified(False)

    def recargar(self):
        cur = self.textCursor().position()
        barra = self.verticalScrollBar().value()
        self.cargar()
        c = self.textCursor()
        c.setPosition(min(cur, len(self.toPlainText())))
        self.setTextCursor(c)
        self.verticalScrollBar().setValue(barra)

    def guardar(self, ruta: str | None = None):
        if ruta:
            self.ruta = ruta
            nuevo = lenguaje_por_ruta(ruta)
            if nuevo != self.lenguaje:
                self.lenguaje = nuevo
                self.resaltador.lenguaje = nuevo
                self.resaltador.set_colores({k: f.foreground().color().name()
                                             for k, f in self.resaltador.f.items()})
        with open(self.ruta, "w", encoding="utf-8", newline=self.fin_linea) as f:
            f.write(self.toPlainText())
        self.document().setModified(False)

    def texto_en_disco_igual(self) -> bool:
        try:
            crudo = Path(self.ruta).read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return True
        return crudo.replace("\r\n", "\n") == self.toPlainText()

    # ---- apariencia
    def set_tema(self, t: dict):
        self.colores = {k: t[k] for k in ("fondo_editor", "texto_editor", "linea_actual", "num_linea")}
        self.resaltador.set_colores(t["hl"])
        self._linea_actual()
        self.margen.update()

    def set_fuente(self, fuente: QFont, sangria: int):
        self.setFont(fuente)
        self.sangria = sangria
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * sangria)
        self._ajustar_margen()

    def set_fondo(self, ruta: str | None, activo: bool, opacidad: float):
        self._bg_activo = bool(activo and ruta)
        self._bg_opacidad = opacidad
        if self._bg_activo:
            if self._bg_origen is None or getattr(self, "_bg_ruta", None) != ruta:
                self._bg_origen = QPixmap(ruta)
                self._bg_ruta = ruta
        else:
            self._bg_origen = None
            self._bg_ruta = None
        self._bg_cache = None
        self.viewport().update()

    def _repintar_si_fondo(self, *_):
        if self._bg_activo:
            self.viewport().update()

    # ---- margen de numeros de linea
    def ancho_margen(self) -> int:
        digitos = max(3, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digitos

    def _ajustar_margen(self, *_):
        ancho = self.ancho_margen()
        self.setViewportMargins(ancho, 0, 0, 0)
        cr = self.contentsRect()
        self.margen.setGeometry(QRect(cr.left(), cr.top(), ancho, cr.height()))

    def _actualizar_margen(self, rect, dy):
        if dy:
            self.margen.scroll(0, dy)
        else:
            self.margen.update(0, rect.y(), self.margen.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._ajustar_margen()

    def resizeEvent(self, evento):
        super().resizeEvent(evento)
        cr = self.contentsRect()
        self.margen.setGeometry(QRect(cr.left(), cr.top(), self.ancho_margen(), cr.height()))
        self._bg_cache = None

    def pintar_margen(self, evento):
        p = QPainter(self.margen)
        p.setFont(self.font())
        p.fillRect(evento.rect(), QColor(self.colores["fondo_editor"]))
        bloque = self.firstVisibleBlock()
        numero = bloque.blockNumber()
        arriba = round(self.blockBoundingGeometry(bloque).translated(self.contentOffset()).top())
        abajo = arriba + round(self.blockBoundingRect(bloque).height())
        actual = self.textCursor().blockNumber()
        alto = self.fontMetrics().height()
        ancho = self.margen.width() - 8
        normal, resaltado = QColor(self.colores["num_linea"]), QColor(self.colores["texto_editor"])
        while bloque.isValid() and arriba <= evento.rect().bottom():
            if bloque.isVisible() and abajo >= evento.rect().top():
                p.setPen(resaltado if numero == actual else normal)
                p.drawText(0, arriba, ancho, alto, Qt.AlignRight, str(numero + 1))
            bloque = bloque.next()
            arriba = abajo
            abajo = arriba + round(self.blockBoundingRect(bloque).height())
            numero += 1

    def _linea_actual(self):
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor(self.colores["linea_actual"]))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        self.setExtraSelections([sel])
        c = self.textCursor()
        self.posicion.emit(c.blockNumber() + 1, c.positionInBlock() + 1)
        self.margen.update()

    # ---- pintado con fondo
    def paintEvent(self, evento):
        if self._bg_activo and self._bg_origen and not self._bg_origen.isNull():
            vp = self.viewport()
            if self._bg_cache is None or self._bg_cache.size() != vp.size():
                esc = self._bg_origen.scaled(vp.size(), Qt.KeepAspectRatioByExpanding,
                                             Qt.SmoothTransformation)
                x = (esc.width() - vp.width()) // 2
                y = (esc.height() - vp.height()) // 2
                self._bg_cache = esc.copy(x, y, vp.width(), vp.height())
            p = QPainter(vp)
            p.setOpacity(self._bg_opacidad)
            p.drawPixmap(0, 0, self._bg_cache)
            p.end()
        super().paintEvent(evento)

    # ---- teclado
    def keyPressEvent(self, e):
        k, mod = e.key(), e.modifiers()
        c = self.textCursor()
        if k == Qt.Key_Tab and not (mod & Qt.ControlModifier):
            if c.hasSelection() and "\u2029" in c.selectedText():
                self._sangrar(+1)
            else:
                c.insertText(" " * self.sangria)
            return
        if k == Qt.Key_Backtab:
            self._sangrar(-1)
            return
        if k in (Qt.Key_Return, Qt.Key_Enter) and not (mod & (Qt.ControlModifier | Qt.ShiftModifier)):
            linea = c.block().text()
            col = c.positionInBlock()
            sangria = re.match(r"[ \t]*", linea).group()
            antes, despues = linea[:col].rstrip(), linea[col:].lstrip()
            extra = " " * self.sangria if antes.endswith(("{", "(", "[", ":")) and self.lenguaje in ("cpp", "py") else ""
            if self.lenguaje == "py" and not antes.endswith(":"):
                extra = ""
            c.beginEditBlock()
            c.insertText("\n" + sangria + extra)
            if extra and despues.startswith(("}", ")", "]")):
                pos = c.position()
                c.insertText("\n" + sangria)
                c.setPosition(pos)
            c.endEditBlock()
            self.setTextCursor(c)
            self.ensureCursorVisible()
            return
        if e.text() == "}" and self.lenguaje == "cpp":
            antes = c.block().text()[:c.positionInBlock()]
            if antes.strip() == "" and len(antes) >= self.sangria:
                c.beginEditBlock()
                for _ in range(self.sangria):
                    c.deletePreviousChar()
                c.insertText("}")
                c.endEditBlock()
                return
        super().keyPressEvent(e)

    def _bloques_seleccion(self):
        c = self.textCursor()
        doc = self.document()
        ini = doc.findBlock(c.selectionStart())
        fin = doc.findBlock(c.selectionEnd())
        if c.hasSelection() and fin.position() == c.selectionEnd() and fin != ini:
            fin = fin.previous()
        bloques = []
        b = ini
        while b.isValid():
            bloques.append(b)
            if b == fin:
                break
            b = b.next()
        return bloques

    def _sangrar(self, direccion: int):
        c = self.textCursor()
        c.beginEditBlock()
        for b in self._bloques_seleccion():
            cb = QTextCursor(b)
            if direccion > 0:
                cb.insertText(" " * self.sangria)
            else:
                quitar = len(b.text()) - len(b.text().lstrip(" "))
                for _ in range(min(quitar, self.sangria)):
                    cb.deleteChar()
        c.endEditBlock()

    def alternar_comentario(self):
        marca = _COMENTARIO.get(self.lenguaje, "#")
        bloques = [b for b in self._bloques_seleccion()]
        con_texto = [b for b in bloques if b.text().strip()]
        if not con_texto:
            return
        todos = all(b.text().lstrip().startswith(marca) for b in con_texto)
        minimo = min(len(b.text()) - len(b.text().lstrip()) for b in con_texto)
        c = self.textCursor()
        c.beginEditBlock()
        for b in con_texto:
            cb = QTextCursor(b)
            if todos:
                idx = b.text().find(marca)
                cb.setPosition(b.position() + idx)
                n = len(marca) + (1 if b.text()[idx + len(marca):idx + len(marca) + 1] == " " else 0)
                cb.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, n)
                cb.removeSelectedText()
            else:
                cb.setPosition(b.position() + minimo)
                cb.insertText(marca + " ")
        c.endEditBlock()

    def ir_a(self, linea: int, columna: int = 1):
        bloque = self.document().findBlockByNumber(max(0, linea - 1))
        c = QTextCursor(bloque)
        c.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor,
                       max(0, min(columna - 1, len(bloque.text()))))
        self.setTextCursor(c)
        self.centerCursor()
        self.setFocus()

    # ---- busqueda
    def buscar(self, texto: str, atras: bool = False, mayus: bool = False) -> bool:
        if not texto:
            return False
        flags = QTextDocument.FindFlags()
        if atras:
            flags |= QTextDocument.FindBackward
        if mayus:
            flags |= QTextDocument.FindCaseSensitively
        if self.find(texto, flags):
            return True
        c = self.textCursor()
        c.movePosition(QTextCursor.End if atras else QTextCursor.Start)
        self.setTextCursor(c)
        return self.find(texto, flags)

    def reemplazar(self, buscar: str, nuevo: str, mayus: bool = False):
        c = self.textCursor()
        sel = c.selectedText()
        if sel and (sel == buscar if mayus else sel.lower() == buscar.lower()):
            c.insertText(nuevo)
        self.buscar(buscar, mayus=mayus)

    def reemplazar_todo(self, buscar: str, nuevo: str, mayus: bool = False) -> int:
        if not buscar:
            return 0
        flags = QTextDocument.FindCaseSensitively if mayus else QTextDocument.FindFlags()
        c = QTextCursor(self.document())
        n = 0
        c.beginEditBlock()
        while True:
            c = self.document().find(buscar, c, flags)
            if c.isNull():
                break
            c.insertText(nuevo)
            n += 1
        c.endEditBlock()
        return n


class BarraBuscar(QWidget):
    """Barra de buscar/reemplazar que actua sobre el editor activo."""

    def __init__(self, obtener_editor, parent=None):
        super().__init__(parent)
        self.setObjectName("barra_buscar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._editor = obtener_editor
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)
        self.campo = QLineEdit()
        self.campo.setPlaceholderText("Buscar")
        self.campo.returnPressed.connect(lambda: self._buscar(False))
        self.campo_r = QLineEdit()
        self.campo_r.setPlaceholderText("Reemplazar")
        self.mayus = QCheckBox("Aa")
        self.mayus.setToolTip("Distinguir mayusculas")
        lay.addWidget(self.campo, 2)
        for txt, fn in (("Anterior", lambda: self._buscar(True)), ("Siguiente", lambda: self._buscar(False))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            lay.addWidget(b)
        lay.addWidget(self.mayus)
        lay.addWidget(self.campo_r, 2)
        b1 = QPushButton("Reemplazar")
        b1.clicked.connect(self._reemplazar)
        b2 = QPushButton("Todo")
        b2.clicked.connect(self._reemplazar_todo)
        cerrar = QToolButton()
        cerrar.setText("\u2715")
        cerrar.clicked.connect(self.hide)
        for w in (b1, b2, cerrar):
            lay.addWidget(w)
        self.hide()

    def mostrar(self):
        ed = self._editor()
        if ed and ed.textCursor().hasSelection():
            self.campo.setText(ed.textCursor().selectedText())
        self.show()
        self.campo.setFocus()
        self.campo.selectAll()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.hide()
            ed = self._editor()
            if ed:
                ed.setFocus()
            return
        super().keyPressEvent(e)

    def _buscar(self, atras: bool):
        ed = self._editor()
        if ed:
            ok = ed.buscar(self.campo.text(), atras, self.mayus.isChecked())
            self.campo.setStyleSheet("" if ok or not self.campo.text() else "color:#F44747;")

    def _reemplazar(self):
        ed = self._editor()
        if ed:
            ed.reemplazar(self.campo.text(), self.campo_r.text(), self.mayus.isChecked())

    def _reemplazar_todo(self):
        ed = self._editor()
        if ed:
            ed.reemplazar_todo(self.campo.text(), self.campo_r.text(), self.mayus.isChecked())
