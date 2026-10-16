import sys
import json
import subprocess
from pathlib import Path

from PyQt5.QtCore import Qt, QRegExp, QPoint, QSize
from PyQt5.QtGui import QColor, QFont, QPixmap, QTextCharFormat, QSyntaxHighlighter, QPainter
from PyQt5.QtGui import QMovie
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QFileDialog, QTextEdit, QPlainTextEdit,
    QLabel, QComboBox, QSplitter, QMessageBox,
    QSpinBox, QGroupBox, QLineEdit, QListWidget, QListWidgetItem,
    QButtonGroup, QScrollArea, QFrame, QCheckBox, QSlider
)

try:
    import serial.tools.list_ports
    tiene_serial = True
except ImportError:
    tiene_serial = False

_BASE           = Path(__file__).parent
_TEMAS_PATH     = _BASE / "temas.json"
_EJEMPLOS_PATH  = _BASE / "ejemplos.json"
_MASCOTAS_PATH  = _BASE / "mascotas.json"
_BG_PATH        = _BASE / "imgs" / "bg"
_MASCOTAS_DIR   = _BASE / "imgs" / "mascotas"

def cargar_temas() -> dict:
    with _TEMAS_PATH.open(encoding="utf-8") as f:
        return json.load(f)

def cargar_ejemplos() -> dict:
    with _EJEMPLOS_PATH.open(encoding="utf-8") as f:
        return json.load(f)

def cargar_mascotas() -> dict:
    with _MASCOTAS_PATH.open(encoding="utf-8") as f:
        return json.load(f)

TEMAS: dict    = cargar_temas()
EJEMPLOS: dict = cargar_ejemplos()
MASCOTAS: dict = cargar_mascotas()

def buscar_tema(nombre: str) -> dict:
    # busca el tema por nombre en todas las categorias
    for categoria in TEMAS.values():
        if nombre in categoria:
            return categoria[nombre]
    return TEMAS["Reze"]["Reze"]  

class MascotaWidget(QLabel):
    # label flotante con gif o png, arrastrable con mouse

    SIZEE = 96  

    def __init__(self, parent=None):
        super().__init__(parent)
        self._movie    = None
        self._drag_pos = QPoint()
        self.setFixedSize(self.SIZEE, self.SIZEE)
        self.setScaledContents(True)
        self.setCursor(Qt.SizeAllCursor)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setToolTip("Arrastra para mover")
        self.hide()

    def cargar(self, archivo: str | None):
        if self._movie:
            self._movie.stop()
            self._movie = None

        if not archivo:
            self.hide()
            return

        ruta = _MASCOTAS_DIR / archivo
        if not ruta.exists():
            self.hide()
            return

        if ruta.suffix.lower() == ".gif":
            self._movie = QMovie(str(ruta))
            self._movie.setScaledSize(QSize(self.SIZEE, self.SIZEE))
            self.setMovie(self._movie)
            self._movie.start()
        else:
            # png, jpg, etc
            self.setPixmap(
                QPixmap(str(ruta)).scaled(
                    self.SIZEE, self.SIZEE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )
        self.show()
        self._ir_esquina()

    def _ir_esquina(self):
        if self.parent():
            pw = self.parent().width()
            ph = self.parent().height()
            self.move(pw - self.SIZEE - 8, ph - self.SIZEE - 8)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            nueva = self.mapToParent(event.pos() - self._drag_pos)

            if self.parent():
                pw = self.parent().width()
                ph = self.parent().height()
                nueva.setX(max(0, min(nueva.x(), pw - self.width())))
                nueva.setY(max(0, min(nueva.y(), ph - self.height())))
            self.move(nueva)

    def cambiar_tamano(self, px: int):
        self.SIZEE = px
        self.setFixedSize(px, px)
        if self._movie:
            self._movie.setScaledSize(QSize(px, px))


class EditorConFondo(QPlainTextEdit):
    # sobreescribe 
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap   = None
        self._opacidad = 0.15
        self._activo   = False
        
        self.mascota = MascotaWidget(self.viewport())

    def set_fondo(self, ruta: str | None, activo: bool, opacidad: float):
        self._activo   = activo
        self._opacidad = opacidad
        if ruta and Path(ruta).exists() and activo:
            self._pixmap = QPixmap(ruta)
        else:
            self._pixmap = None
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.mascota.isVisible():
            self.mascota._ir_esquina()

    def paintEvent(self, event):
        
        if self._pixmap and self._activo:
            painter = QPainter(self.viewport())
            painter.setOpacity(self._opacidad)
            scaled = self._pixmap.scaled(
                self.viewport().size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            x = (self.viewport().width()  - scaled.width())  // 2
            y = (self.viewport().height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()
        super().paintEvent(event)

class VentanaConFondo(QMainWindow):
    def __init__(self):
        super().__init__()
        self._pixmap   = None
        self._opacidad = 0.08
        self._activo   = False

    def set_fondo_ventana(self, ruta: str | None, activo: bool, opacidad: float):
        self._activo   = activo
        self._opacidad = opacidad
        if ruta and Path(ruta).exists() and activo:
            self._pixmap = QPixmap(ruta)
        else:
            self._pixmap = None
        self.update()

    def paintEvent(self, event):
        if self._pixmap and self._activo:
            painter = QPainter(self)
            painter.setOpacity(self._opacidad)
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            x = (self.width()  - scaled.width())  // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.end()
        super().paintEvent(event)

class BotonTema(QPushButton):
    # boton con nombre del tema y 5 bolitas de colores del hl
    def __init__(self, nombre: str, datos: dict, parent=None):
        super().__init__(parent)
        self.nombre = nombre
        self.datos  = datos
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self._construir()

    def _construir(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        lbl = QLabel(self.nombre)
        lbl.setFont(QFont("Courier New", 9))
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(lbl)
        layout.addStretch()

        colores_hl = self.datos.get("hl", {})
        orden = ["instrucciones", "registros", "inmediatos", "etiquetas", "comentarios"]
        for clave in orden:
            color = colores_hl.get(clave, "#444444")
            bolita = QLabel()
            bolita.setFixedSize(12, 12)
            bolita.setStyleSheet(
                f"background:{color}; border-radius:6px; border:1px solid rgba(255,255,255,0.15);"
            )
            bolita.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(bolita)

        franja = QLabel()
        franja.setFixedSize(18, 28)
        franja.setStyleSheet(
            f"background:{self.datos.get('fondo_editor','#1E1E1E')};"
            f"border:1px solid {self.datos.get('tab_sel','#555')};"
            f"border-radius:3px;"
        )
        franja.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(franja)


class SelectorTemas(QWidget):
    def __init__(self, ide):
        super().__init__()
        self.ide = ide
        self._botones: dict[str, BotonTema] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.lista_cats = QListWidget()
        self.lista_cats.setFixedWidth(110)
        self.lista_cats.setFont(QFont("Courier New", 9))
        for cat in TEMAS:
            item = QListWidgetItem(cat)
            item.setTextAlignment(Qt.AlignCenter)
            self.lista_cats.addItem(item)
        self.lista_cats.currentRowChanged.connect(self._cambiar_categoria)
        layout.addWidget(self.lista_cats)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        layout.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        self.contenedor_temas = QWidget()
        self.layout_temas = QVBoxLayout(self.contenedor_temas)
        self.layout_temas.setContentsMargins(6, 6, 6, 6)
        self.layout_temas.setSpacing(4)
        self.layout_temas.addStretch()

        scroll.setWidget(self.contenedor_temas)
        layout.addWidget(scroll)

        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)

        # construir todos los botones
        for cat, temas in TEMAS.items():
            for nombre, datos in temas.items():
                btn = BotonTema(nombre, datos)
                self.grupo.addButton(btn)
                self.layout_temas.insertWidget(self.layout_temas.count() - 1, btn)
                btn.clicked.connect(lambda checked, n=nombre: self._seleccionar(n))
                self._botones[nombre] = btn

        cats = list(TEMAS.keys())
        self.lista_cats.setCurrentRow(cats.index("Reze"))
        self._marcar_tema("Reze")

    def _cambiar_categoria(self, idx: int):
        # muestra solo los botones de la categoria seleccionada
        cats = list(TEMAS.keys())
        if idx < 0 or idx >= len(cats):
            return
        cat_sel = cats[idx]
        for cat, temas in TEMAS.items():
            for nombre in temas:
                self._botones[nombre].setVisible(cat == cat_sel)

    def _seleccionar(self, nombre: str):
        self.ide.aplicar_tema(nombre)

    def _marcar_tema(self, nombre: str):
        if nombre in self._botones:
            self._botones[nombre].setChecked(True)


# Resaltador 
class ResaltadorAsm(QSyntaxHighlighter):
    def __init__(self, documento):
        super().__init__(documento)  # inicia lo que resalta el ide de sintaxis
        self.reglas = []
        self.recargar(TEMAS["Reze"]["Reze"]["hl"])  # reze al iniciar JSJS

    def recargar(self, colores):
        self.reglas = []

        def hl(patron, clave, negrita=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(colores[clave]))
            if negrita:
                fmt.setFontWeight(QFont.Bold)
            self.reglas.append((QRegExp(patron, Qt.CaseInsensitive), fmt))

        hl(
            r"\b(ADDI|SUBI|ANDI|ORI|XORI|SLLI|SRLI|SLTI|"
            r"ADD|SUB|AND|OR|XOR|SLL|SRL|SLT|"
            r"LOAD|STORE|BEQ|JUMP|JAL|OUT|NOP|MOV)\b",
            "instrucciones", negrita=True
        )  # reglas de regex y formato
        hl(r"\br[0-7]\b",                              "registros")
        hl(r"\b(0x[0-9a-fA-F]+|0b[01]+|-?\d+)\b",     "inmediatos")
        hl(r"^\s*\w+:",                                 "etiquetas")
        hl(r";[^\n]*",                                  "comentarios")
        self.rehighlight()

    def highlightBlock(self, texto):  
        for patron, fmt in self.reglas:
            idx = patron.indexIn(texto)
            while idx >= 0:
                largo = patron.matchedLength()
                self.setFormat(idx, largo, fmt)
                idx = patron.indexIn(texto, idx + largo)


class PantallaWelcome(QWidget):  
    def __init__(self):
        super().__init__()
        diseno = QVBoxLayout(self)
        diseno.setAlignment(Qt.AlignCenter)
        diseno.setSpacing(12)

        img_path = _BASE / "imgs/resee.jpeg"  # imagen inicial igual inicia si hay o no xd
        if img_path.exists():
            lbl_img = QLabel()
            lbl_img.setPixmap(
                QPixmap(str(img_path)).scaled(300, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            lbl_img.setAlignment(Qt.AlignCenter)
            diseno.addWidget(lbl_img)

        titulo = QLabel("JoJoP IDE")
        titulo.setFont(QFont("Courier New", 28, QFont.Bold))
        titulo.setAlignment(Qt.AlignCenter)
        diseno.addWidget(titulo)

        subtitulo = QLabel("IDE de Risc V para Zenith-Core")  # ¿cambiar nombre?
        subtitulo.setFont(QFont("Courier New", 13))
        subtitulo.setAlignment(Qt.AlignCenter)
        diseno.addWidget(subtitulo)

        creditos = QLabel(
            "Desarrollado por Pablo Jose Lopez Mazariegos.\n"
            #"Hecho con amor y monster ultra\n"
            "Guatemala, 2026\n\n"
            "https://github.com/PabloJLM"
        )
        creditos.setFont(QFont("Courier New", 10))
        creditos.setAlignment(Qt.AlignCenter)
        diseno.addWidget(creditos)

class PestanaEjemplos(QWidget):
    def __init__(self, ide):
        super().__init__()
        self.ide = ide
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.lista = QListWidget()
        self.lista.setFixedWidth(160)
        self.lista.setFont(QFont("Courier New", 9))
        for nombre in EJEMPLOS.get("snippets", {}):
            self.lista.addItem(nombre)
        self.lista.currentTextChanged.connect(self._mostrar)
        layout.addWidget(self.lista)

        panel = QVBoxLayout()

        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setFont(QFont("Courier New", 9))
        panel.addWidget(self.desc)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("Courier New", 9))
        panel.addWidget(self.preview)

        btn = QPushButton("Cargar en editor")
        btn.clicked.connect(self._cargar)
        panel.addWidget(btn)

        layout.addLayout(panel)

    def _mostrar(self, nombre: str):
        datos = EJEMPLOS.get("snippets", {}).get(nombre, {})
        self.desc.setText(datos.get("desc", ""))
        self.preview.setPlainText(datos.get("code", ""))

    def _cargar(self):
        item = self.lista.currentItem()
        if not item:
            return
        code = EJEMPLOS.get("snippets", {}).get(item.text(), {}).get("code", "")
        self.ide.editor.setPlainText(code)
        self.ide.archivo_actual = None
        self.ide.setWindowTitle("JoJoP_IDE  —  sin guardar")
        self.ide.pestanas.setCurrentIndex(1)  # ir al editor

class PestanaAjustes(QWidget):
    def __init__(self, ide):  
        super().__init__()
        self.ide = ide
        diseno = QVBoxLayout(self)
        diseno.setAlignment(Qt.AlignTop)
        diseno.setSpacing(10)
        diseno.setContentsMargins(16, 16, 16, 16)

        # apariencia y temas
        grupo_ap = QGroupBox("Apariencia")
        layout_ap = QVBoxLayout(grupo_ap)

        self.selector_temas = SelectorTemas(ide)
        self.selector_temas.setMinimumHeight(200)
        layout_ap.addWidget(self.selector_temas)

        fila_fuente = QHBoxLayout()
        self.combo_fuente = QComboBox()
        self.combo_fuente.addItems(["Courier New", "Consolas", "Fira Code", "Monospace"])
        self.combo_fuente.currentTextChanged.connect(self.cambiar_fuente)
        fila_fuente.addWidget(QLabel("Fuente:"))
        fila_fuente.addWidget(self.combo_fuente)

        self.spin_tamanio = QSpinBox()
        self.spin_tamanio.setRange(8, 24)
        self.spin_tamanio.setValue(10)
        self.spin_tamanio.valueChanged.connect(self.cambiar_tamanio)
        fila_fuente.addWidget(QLabel("Tamaño:"))
        fila_fuente.addWidget(self.spin_tamanio)
        fila_fuente.addStretch()
        layout_ap.addLayout(fila_fuente)

        diseno.addWidget(grupo_ap)

        # mascota
        grupo_mascota = QGroupBox("Mascota")
        layout_mascota = QVBoxLayout(grupo_mascota)

        fila_m = QHBoxLayout()
        fila_m.addWidget(QLabel("Mascota:"))
        self.combo_mascota = QComboBox()
        self.combo_mascota.addItems(MASCOTAS.keys())
        self.combo_mascota.currentTextChanged.connect(self._cambiar_mascota)
        fila_m.addWidget(self.combo_mascota)
        layout_mascota.addLayout(fila_m)

        fila_t = QHBoxLayout()
        fila_t.addWidget(QLabel("Tamaño:"))
        self.slider_mascota = QSlider(Qt.Horizontal)
        self.slider_mascota.setRange(48, 200)
        self.slider_mascota.setValue(96)
        self.slider_mascota.valueChanged.connect(self._cambiar_tamano_mascota)
        fila_t.addWidget(self.slider_mascota)
        self.lbl_mascota_tam = QLabel("96px")
        self.slider_mascota.valueChanged.connect(
            lambda v: self.lbl_mascota_tam.setText(f"{v}px")
        )
        fila_t.addWidget(self.lbl_mascota_tam)
        layout_mascota.addLayout(fila_t)

        diseno.addWidget(grupo_mascota)

        # imagen de fondo
        grupo_bg = QGroupBox("Imagen de fondo")
        layout_bg = QVBoxLayout(grupo_bg)

        self.check_bg_editor = QCheckBox("Fondo en el editor")
        self.check_bg_editor.stateChanged.connect(self._actualizar_fondo)
        layout_bg.addWidget(self.check_bg_editor)

        self.check_bg_ventana = QCheckBox("Fondo en la ventana")
        self.check_bg_ventana.stateChanged.connect(self._actualizar_fondo)
        layout_bg.addWidget(self.check_bg_ventana)

        fila_op = QHBoxLayout()
        fila_op.addWidget(QLabel("Opacidad:"))
        self.slider_opacidad = QSlider(Qt.Horizontal)
        self.slider_opacidad.setRange(1, 40)
        self.slider_opacidad.setValue(15)
        self.slider_opacidad.valueChanged.connect(self._actualizar_fondo)
        fila_op.addWidget(self.slider_opacidad)
        self.lbl_opacidad = QLabel("15%")
        self.slider_opacidad.valueChanged.connect(
            lambda v: self.lbl_opacidad.setText(f"{v}%")
        )
        fila_op.addWidget(self.lbl_opacidad)
        layout_bg.addLayout(fila_op)

        diseno.addWidget(grupo_bg)

        # rutas de asm
        grupo_rutas = QGroupBox("Rutas de asm")
        forma_rutas = QFormLayout(grupo_rutas)

        self.campo_ensamblador = QLineEdit(self.ide.ruta_ensamblador)
        btn_ens = QPushButton("...")
        btn_ens.setFixedWidth(28)
        btn_ens.clicked.connect(lambda: self.elegir_ruta(self.campo_ensamblador))
        fila_ens = QHBoxLayout()
        fila_ens.addWidget(self.campo_ensamblador)
        fila_ens.addWidget(btn_ens)
        forma_rutas.addRow("assembler.py:", fila_ens)

        self.campo_flasher = QLineEdit(self.ide.ruta_flasher)
        btn_fl = QPushButton("...")
        btn_fl.setFixedWidth(28)
        btn_fl.clicked.connect(lambda: self.elegir_ruta(self.campo_flasher))
        fila_fl = QHBoxLayout()
        fila_fl.addWidget(self.campo_flasher)
        fila_fl.addWidget(btn_fl)
        forma_rutas.addRow("uart_flash.py:", fila_fl)

        btn_aplicar = QPushButton("Aplicar rutas")
        btn_aplicar.clicked.connect(self.aplicar_rutas)
        forma_rutas.addRow("", btn_aplicar)

        diseno.addWidget(grupo_rutas)
        diseno.addStretch()

    def _cambiar_mascota(self, nombre: str):
        archivo = MASCOTAS.get(nombre)
        self.ide.editor.mascota.cargar(archivo)

    def _cambiar_tamano_mascota(self, px: int):
        self.ide.editor.mascota.cambiar_tamano(px)

    def _actualizar_fondo(self):

        op = self.slider_opacidad.value() / 100
        bg = self.ide._bg_actual
        self.ide.editor.set_fondo(bg, self.check_bg_editor.isChecked(), op)
        self.ide.set_fondo_ventana(bg, self.check_bg_ventana.isChecked(), op)

    def elegir_ruta(self, campo):  # abre un dialogo y la guarda (busca archivos .py)
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir script", "", "Python (*.py)")
        if ruta:
            campo.setText(ruta)

    def cambiar_fuente(self, nombre):  # cambia la fuente del ide y consola
        tam = self.spin_tamanio.value()
        self.ide.editor.setFont(QFont(nombre, tam))
        self.ide.consola.setFont(QFont(nombre, tam - 1))

    def cambiar_tamanio(self, tam):  # cambia el tamaño de la fuente, la consola siempre es mas pequeña
        nombre = self.combo_fuente.currentText()
        self.ide.editor.setFont(QFont(nombre, tam))
        self.ide.consola.setFont(QFont(nombre, tam - 1))

    def aplicar_rutas(self):  # guarda las rutas de assembler.py y flasher uart
        self.ide.ruta_ensamblador = self.campo_ensamblador.text()
        self.ide.ruta_flasher     = self.campo_flasher.text()
        self.ide.escribir_consola("Rutas actualizadas.", "#4EC9B0")

class JoJoPIDE(VentanaConFondo):  
    def __init__(self):  
        super().__init__()
        self.setWindowTitle("JoJoP_IDE")
        self.resize(960, 680)
        self.archivo_actual   = None
        self.ruta_ensamblador = str(_BASE / "tools" / "assembler.py")
        self.ruta_flasher     = str(_BASE / "tools" / "uart_flash.py")
        self._bg_actual       = None  
        self.construir_ui()
        self.aplicar_tema("Reze")  # default jsjs

    def construir_ui(self):  # crea las pestañas de arriba
        self.pestanas = QTabWidget()
        self.setCentralWidget(self.pestanas)
        self._tab_ajustes = PestanaAjustes(self)
        self.pestanas.addTab(PantallaWelcome(),      "Inicio")
        self.pestanas.addTab(self.crear_editor(),    "Editor")
        self.pestanas.addTab(PestanaEjemplos(self),  "Ejemplos")
        self.pestanas.addTab(self._tab_ajustes,      "Ajustes")

    def crear_editor(self):  # pone la barra, selector de puerto, editor de texto, consola
        contenedor = QWidget()
        diseno = QVBoxLayout(contenedor)
        diseno.setSpacing(4)
        diseno.setContentsMargins(6, 6, 6, 6)

        barra = QHBoxLayout()
        for etiqueta, accion in [
            ("Nuevo",        self.nuevo),
            ("Abrir",        self.abrir),
            ("Guardar",      self.guardar),
            ("Guardar como", self.guardar_como),
        ]:
            btn = QPushButton(etiqueta)
            btn.clicked.connect(accion)
            barra.addWidget(btn)

        barra.addSpacing(12)

        btn_bin = QPushButton("Compilar .bin")
        btn_bin.clicked.connect(self.compilar_bin)
        barra.addWidget(btn_bin)

        barra.addSpacing(12)

        barra.addWidget(QLabel("Puerto:"))
        self.selector_puerto = QComboBox()
        self.selector_puerto.setMinimumWidth(110)
        barra.addWidget(self.selector_puerto)

        btn_r = QPushButton("R")
        btn_r.setFixedWidth(26)
        btn_r.setToolTip("Refrescar puertos")
        btn_r.clicked.connect(self.get_puertos)
        barra.addWidget(btn_r)

        btn_flash = QPushButton("Flash")
        btn_flash.clicked.connect(self.flashear)
        barra.addWidget(btn_flash)

        barra.addStretch()
        diseno.addLayout(barra)

        divisor = QSplitter(Qt.Vertical)

        # editor con soporte de imagen de fondo y mascota flotante
        self.editor = EditorConFondo()
        self.editor.setFont(QFont("Courier New", 10))
        self.editor.setTabStopDistance(28)
        self.resaltador = ResaltadorAsm(self.editor.document())
        divisor.addWidget(self.editor)

        self.consola = QTextEdit()
        self.consola.setReadOnly(True)
        self.consola.setFont(QFont("Courier New", 9))
        self.consola.setMaximumHeight(160)
        divisor.addWidget(self.consola)

        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 1)
        diseno.addWidget(divisor)

        self.etiqueta_estado = QLabel("Listo")
        diseno.addWidget(self.etiqueta_estado)

        self.get_puertos()
        return contenedor

    def aplicar_tema(self, nombre):  # aplica los temas segun elegidos por default esta reze
        t = buscar_tema(nombre)

        # imagen de fondo del tema
        bg_file = t.get("bg")
        bg_path = str(_BG_PATH / bg_file) if bg_file else None
        self._bg_actual = bg_path

        aj = self._tab_ajustes
        op = aj.slider_opacidad.value() / 100
        self.editor.set_fondo(bg_path, aj.check_bg_editor.isChecked(), op)
        self.set_fondo_ventana(bg_path, aj.check_bg_ventana.isChecked(), op)

        # colores del tema
        self.editor.setStyleSheet(
            f"QPlainTextEdit {{ background:{t['fondo_editor']}; color:{t['texto_editor']}; }}"
        )
        self.consola.setStyleSheet(
            f"QTextEdit {{ background:{t['fondo_consola']}; color:{t['texto_consola']}; }}"
        )

        qss = f"QMainWindow, QWidget {{ background:{t['fondo_app']}; color:{t['texto_consola']}; }}"
        if t["qss_extra"]:
            q = t["qss_extra"]
            qss += (
                f" QPushButton {{ {q} border-radius:3px; padding:3px 8px; }}"
                f" QPushButton:checked {{ background:{t['tab_sel']}; color:white; }}"
                f" QComboBox   {{ {q} }}"
                f" QSpinBox    {{ {q} }}"
                f" QLineEdit   {{ {q} }}"
                f" QGroupBox   {{ color:{t['texto_consola']}; }}"
                f" QTabBar::tab {{ {q} padding:5px 12px; }}"
                f" QTabBar::tab:selected {{ background:{t['tab_sel']}; color:white; }}"
                f" QListWidget {{ {q} }}"
                f" QListWidget::item:selected {{ background:{t['tab_sel']}; color:white; }}"
                f" QScrollArea {{ border:none; }}"
            )
        self.setStyleSheet(qss)
        self.resaltador.recargar(t["hl"])

    # funciones

    def escribir_consola(self, texto, color="#d4d4d4"):  # texto en la consola xd
        self.consola.append(f'<span style="color:{color}">{texto}</span>')

    def actualizar_estado(self, texto):  # actualiza el label de estado abajo
        self.etiqueta_estado.setText(texto)

    def pedir_guardar(self):  # salta opcion de guardar sino hay archivo
        if not self.archivo_actual:
            self.guardar_como()
        if not self.archivo_actual:
            return None
        self.guardar()
        return Path(self.archivo_actual)

    # archivos

    def nuevo(self):  # limpia el editor y borra el texto actual
        self.editor.clear()
        self.archivo_actual = None
        self.setWindowTitle("JoJoP_IDE")

    def abrir(self):  # abre archivos buscando .asm y lo carga en el editor
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Abrir archivo", "", "Assembly (*.asm);;Todos (*)"
        )
        if ruta:
            self.archivo_actual = ruta
            self.editor.setPlainText(Path(ruta).read_text(encoding="utf-8"))
            self.setWindowTitle(f"JoJoP_IDE  —  {Path(ruta).name}")
            self.actualizar_estado(ruta)
            self.pestanas.setCurrentIndex(1)

    def guardar(self):  # guarda el contenido actual xd
        if not self.archivo_actual:
            return self.guardar_como()
        Path(self.archivo_actual).write_text(
            self.editor.toPlainText(), encoding="utf-8"
        )
        self.actualizar_estado(f"Guardado: {self.archivo_actual}")

    def guardar_como(self):  # guarda el archivo como el nombre que se quiere
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar como", "", "Assembly (*.asm);;Todos (*)"
        )
        if ruta:
            self.archivo_actual = ruta
            self.guardar()
            self.setWindowTitle(f"JoJoP_IDE  —  {Path(ruta).name}")

    # compile

    def run_risc(self):  # guarda archivo - ejecuta assembler como sub proceso - genera el binario - muestra el output
        origen = self.pedir_guardar()
        if not origen:
            return None
        bin_path = origen.with_suffix(".bin")
        comando = [
            sys.executable, self.ruta_ensamblador,
            str(origen),
            "-o", str(origen.with_suffix(".hex")),
            "--binary"
        ]
        self.escribir_consola(f"$ {' '.join(comando)}", "#569CD6")
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.stdout:
            self.escribir_consola(resultado.stdout.strip())
        if resultado.stderr:
            self.escribir_consola(resultado.stderr.strip(), "#F44747")
        if resultado.returncode != 0:
            self.escribir_consola("FAIL", "#F44747")
            return None
        self.escribir_consola(f"OK  →  {bin_path}", "#4EC9B0")
        return bin_path

    def compilar_bin(self):  # llama a la funcion run risc (arriba)
        self.run_risc()

    def get_puertos(self):  # lista los puertos seriales disponibles con pyserial
        self.selector_puerto.clear()
        if tiene_serial:
            for p in serial.tools.list_ports.comports():
                self.selector_puerto.addItem(p.device)
        if self.selector_puerto.count() == 0:
            self.selector_puerto.addItem("(ninguno)")

    def flashear(self):  # verifica si existe .bin - sino hay compila el actual - ejecuta el flasher - muestra estado si se carga
        origen = self.pedir_guardar()
        if not origen:
            return
        bin_path = origen.with_suffix(".bin")
        if not bin_path.exists():
            self.escribir_consola("Sin .bin — compilando primero...", "#DCDCAA")
            if not self.run_risc():
                return
        puerto = self.selector_puerto.currentText()
        if not puerto or puerto == "(ninguno)":
            QMessageBox.warning(self, "Flash", "Selecciona un puerto serie.")
            return
        comando = [sys.executable, self.ruta_flasher, str(bin_path), "--port", puerto]
        self.escribir_consola(f"$ {' '.join(comando)}", "#569CD6")
        resultado = subprocess.run(comando, capture_output=True, text=True)
        if resultado.stdout:
            self.escribir_consola(resultado.stdout.strip())
        if resultado.stderr:
            self.escribir_consola(resultado.stderr.strip(), "#F44747")
        if resultado.returncode == 0:
            self.escribir_consola("Flash OK", "#4EC9B0")
        else:
            self.escribir_consola("Flash FAIL", "#F44747")


if __name__ == "__main__":  
    app = QApplication(sys.argv)
    ventana = JoJoPIDE()
    ventana.show()
    sys.exit(app.exec_())