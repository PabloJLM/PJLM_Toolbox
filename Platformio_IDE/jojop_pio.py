"""JoJoP PIO - IDE liviano sobre PlatformIO Core.

Windows: compila y sube a traves de WSL (o pio de Windows) y pasa la placa con usbipd-win.
Linux:   llama a pio directamente.

Uso:  python jojop_pio.py [carpeta_del_proyecto]
"""
from __future__ import annotations

import base64
import configparser
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

from PyQt5.QtCore import (QFileSystemWatcher, QModelIndex, QSettings, QSize,
                          QSortFilterProxyModel, Qt, QTimer, QUrl, pyqtSignal)
from PyQt5.QtGui import QDesktopServices, QFont, QFontDatabase, QKeySequence
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QComboBox, QFileDialog,
                             QFileSystemModel, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                             QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter,
                             QStackedWidget, QTabWidget, QToolBar, QToolButton, QTreeView,
                             QVBoxLayout, QWidget)

import temas as T
from dialogos import DialogoAjustes, DialogoNuevoProyecto
from editor import BarraBuscar, EditorCodigo
from ejecutor import (ES_WINDOWS, ConfigEjecucion, Proceso, correr_pio_rapido,
                      lanzar_silencioso)
from iconos import icono
from paneles import PanelDescanso, PanelMonitor, PanelSalida, PanelUSB
from terminal import Terminal

APP = "JoJoP PIO"
VERSION = "1.0"
BASE = Path(__file__).resolve().parent
SCRIPT_MONITOR = BASE / "monitor_serie.py"
OCULTOS = {".pio", ".git", "__pycache__", ".vscode", ".idea", ".DS_Store"}
RX_USO = re.compile(r"^(RAM|Flash):\s*\[.*?\]\s*([\d.]+%)")
MAX_RECIENTES = 8


def fuente_mono_predeterminada() -> str:
    familias = set(QFontDatabase().families())
    for f in ("Consolas", "Cascadia Mono", "JetBrains Mono", "DejaVu Sans Mono",
              "Ubuntu Mono", "Liberation Mono", "Courier New"):
        if f in familias:
            return f
    return "Monospace"


def leer_ini(ruta: Path):
    """Entornos, entorno por defecto y monitor_speed de cada entorno."""
    cp = configparser.ConfigParser(interpolation=None, strict=False,
                                   inline_comment_prefixes=(";", "#"))
    try:
        cp.read(ruta, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return [], None, {}
    envs = [s[4:] for s in cp.sections() if s.startswith("env:")]
    defecto = None
    if cp.has_option("platformio", "default_envs"):
        valores = re.split(r"[,\s]+", cp.get("platformio", "default_envs").strip())
        defecto = valores[0] if valores and valores[0] else None
    comun = cp.get("env", "monitor_speed", fallback=None) if cp.has_section("env") else None
    velocidades = {}
    for e in envs:
        v = cp.get(f"env:{e}", "monitor_speed", fallback=None) or comun
        if v and v.strip().isdigit():
            velocidades[e] = int(v.strip())
    return envs, defecto, velocidades


class FiltroArbol(QSortFilterProxyModel):
    """Oculta .pio, .git, etc. y ordena carpetas primero."""

    def filterAcceptsRow(self, fila, padre):
        modelo = self.sourceModel()
        return modelo.fileName(modelo.index(fila, 0, padre)) not in OCULTOS

    def lessThan(self, a, b):
        m = self.sourceModel()
        da, db = m.isDir(a), m.isDir(b)
        if da != db:
            return da
        return m.fileName(a).lower() < m.fileName(b).lower()


class ComboPuertos(QComboBox):
    abriendo = pyqtSignal()

    def showPopup(self):
        self.abriendo.emit()
        super().showPopup()


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.s = QSettings("PabloJLM", "JoJoP_PIO")
        self.temas = T.cargar_temas()
        self.cfg = ConfigEjecucion(self.s.value("modo", "wsl"), self.s.value("distro", ""))
        self.aj = {
            "tema": self.s.value("tema", T.PREDETERMINADO),
            "fuente": self.s.value("fuente", fuente_mono_predeterminada()),
            "tam": self.s.value("tam", 11, type=int),
            "sangria": self.s.value("sangria", 2, type=int),
            "fondo": self.s.value("fondo", True, type=bool),
            "opacidad": self.s.value("opacidad", 12, type=int),
            "guardar_antes": self.s.value("guardar_antes", True, type=bool),
            "verbose": self.s.value("verbose", False, type=bool),
            "modo": self.cfg.modo, "distro": self.cfg.distro,
        }
        if self.aj["tema"] not in self.temas:
            self.aj["tema"] = T.PREDETERMINADO if T.PREDETERMINADO in self.temas else next(iter(self.temas))
        self.t = T.tema(self.temas, self.aj["tema"])

        self.proyecto: str | None = None
        self.puertos: list[str] = []
        self._buscando_puertos = False
        self._pendiente = None
        self._reabrir_monitor = False
        self._tarea_info = ("", "")
        self._al_terminar = None
        self._uso: dict[str, str] = {}
        self._t0 = 0.0

        self.tarea = Proceso(self.cfg, "tarea", parent=self)
        self.tarea.linea.connect(self._linea_tarea)
        self.tarea.terminado.connect(self._fin_tarea)
        self.monitor = Proceso(self.cfg, "monitor", crudo=True, parent=self)
        self.monitor.terminado.connect(self._fin_monitor)

        self.vigilante = QFileSystemWatcher(self)
        self.vigilante.fileChanged.connect(self._archivo_cambiado)
        self._reloj = QTimer(self)
        self._reloj.setInterval(1000)
        self._reloj.timeout.connect(self._tic)

        self.setWindowTitle(APP)
        self.resize(1200, 800)
        self._construir()
        self._menus()
        self.aplicar_tema(self.aj["tema"])
        self._aplicar_fuente()
        self._habilitar()

    # ================================================================ interfaz
    def _construir(self):
        self.barra = QToolBar("Principal")
        self.barra.setMovable(False)
        self.barra.setIconSize(QSize(18, 18))
        self.addToolBar(self.barra)

        self.btn_verificar = self._redondo("verificar", "Verificar / compilar (Ctrl+R)", self.verificar)
        self.btn_subir = self._redondo("subir", "Subir (Ctrl+U)", lambda: self.subir())
        self.btn_detener = self._redondo("detener", "Detener (Ctrl+.)", self.detener)
        for b in (self.btn_verificar, self.btn_subir, self.btn_detener):
            self.barra.addWidget(b)
        self.barra.addSeparator()

        self.combo_env = QComboBox()
        self.combo_env.setMinimumWidth(190)
        self.combo_env.setToolTip("Entorno [env:...] de platformio.ini")
        self.combo_env.currentIndexChanged.connect(self._env_cambiado)
        self.barra.addWidget(self.combo_env)

        self.combo_puerto = ComboPuertos()
        self.combo_puerto.setMinimumWidth(200)
        self.combo_puerto.setToolTip("Puerto de subida y del monitor")
        self.combo_puerto.abriendo.connect(self.refrescar_puertos)
        self.combo_puerto.currentIndexChanged.connect(lambda _: self._contexto())
        self.barra.addWidget(self.combo_puerto)
        self.btn_refrescar = QToolButton()
        self.btn_refrescar.setToolTip("Buscar puertos")
        self.btn_refrescar.clicked.connect(self.refrescar_puertos)
        self.barra.addWidget(self.btn_refrescar)

        relleno = QWidget()
        relleno.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        relleno.setStyleSheet("background:transparent;")
        self.barra.addWidget(relleno)
        self.btn_monitor = QToolButton()
        self.btn_monitor.setToolTip("Monitor serie (Ctrl+Shift+M)")
        self.btn_monitor.clicked.connect(self.alternar_monitor)
        self.barra.addWidget(self.btn_monitor)

        # explorador
        self.modelo = QFileSystemModel(self)
        self.modelo.setReadOnly(True)
        self.filtro = FiltroArbol(self)
        self.filtro.setSourceModel(self.modelo)
        self.arbol = QTreeView()
        self.arbol.setModel(self.filtro)
        self.arbol.setHeaderHidden(True)
        for col in (1, 2, 3):
            self.arbol.hideColumn(col)
        self.arbol.setSortingEnabled(True)
        self.arbol.sortByColumn(0, Qt.AscendingOrder)
        self.arbol.setAnimated(False)
        self.arbol.setIndentation(14)
        self.arbol.doubleClicked.connect(self._abrir_desde_arbol)
        self.arbol.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arbol.customContextMenuRequested.connect(self._menu_arbol)
        self.arbol.setMinimumWidth(170)

        # editores
        self.pestanas = QTabWidget()
        self.pestanas.setDocumentMode(True)
        self.pestanas.setTabsClosable(True)
        self.pestanas.setMovable(True)
        self.pestanas.tabCloseRequested.connect(self.cerrar_pestana)
        self.pestanas.currentChanged.connect(self._pestana_cambiada)
        self.buscador = BarraBuscar(self.editor_actual)
        zona_editor = QWidget()
        ze = QVBoxLayout(zona_editor)
        ze.setContentsMargins(0, 0, 0, 0)
        ze.setSpacing(0)
        ze.addWidget(self.pestanas, 1)
        ze.addWidget(self.buscador)

        self.pila = QStackedWidget()
        self.inicio = self._pantalla_inicio()
        self.pila.addWidget(self.inicio)
        self.pila.addWidget(zona_editor)

        # paneles inferiores
        self.inferior = QTabWidget()
        self.inferior.setDocumentMode(True)
        self.salida = PanelSalida()
        self.salida.ir_a.connect(self._ir_a_error)
        self.panel_monitor = PanelMonitor()
        self.panel_monitor.conectar.connect(lambda on: self.conectar_monitor() if on else self.monitor.detener())
        self.panel_monitor.enviar.connect(self.monitor.escribir)
        self.panel_monitor.baudios_cambiados.connect(self._baudios_cambiados)
        self.monitor.datos.connect(self.panel_monitor.recibir)
        self.monitor.aviso.connect(self.panel_monitor.mostrar_estado)
        self.terminal = Terminal(self.cfg)
        self.terminal.salida.ir_a.connect(self._ir_a_error)
        self.inferior.addTab(self.salida, "Salida")
        self.inferior.addTab(self.panel_monitor, "Serial")
        self.inferior.addTab(self.terminal, "PowerShell" if ES_WINDOWS else "Terminal")
        self.panel_usb = None
        self.term_usb = None
        if ES_WINDOWS:
            # pestana USB: lista con botones arriba y una PowerShell abajo
            self.panel_usb = PanelUSB(self.s)
            self.term_usb = Terminal(self.cfg, fijo="powershell")
            self.panel_usb.log.connect(lambda t, tipo: self.term_usb.salida.agregar(t, tipo or None))
            self.panel_usb.cambio.connect(lambda: QTimer.singleShot(800, self.refrescar_puertos))
            self.div_usb = QSplitter(Qt.Vertical)
            self.div_usb.addWidget(self.panel_usb)
            self.div_usb.addWidget(self.term_usb)
            self.div_usb.setSizes([120, 120])
            self.inferior.addTab(self.div_usb, "USB (usbipd)")
        self.descanso = PanelDescanso(BASE / "imgs" / "descanso", self.s)
        self.inferior.addTab(self.descanso, "Descanso")

        self.div_v = QSplitter(Qt.Vertical)
        self.div_v.addWidget(self.pila)
        self.div_v.addWidget(self.inferior)
        self.div_v.setStretchFactor(0, 3)
        self.div_v.setStretchFactor(1, 1)
        self.div_v.setSizes([560, 220])
        self.div_h = QSplitter(Qt.Horizontal)
        self.div_h.addWidget(self.arbol)
        self.div_h.addWidget(self.div_v)
        self.div_h.setStretchFactor(1, 1)
        self.div_h.setSizes([230, 970])
        self.setCentralWidget(self.div_h)

        # barra de estado
        self.lbl_estado = QLabel("Listo")
        self.lbl_uso = QLabel("")
        self.lbl_pos = QLabel("")
        self.lbl_ctx = QLabel("")
        self.statusBar().addWidget(self.lbl_estado, 1)
        self.statusBar().addPermanentWidget(self.lbl_uso)
        self.statusBar().addPermanentWidget(self.lbl_pos)
        self.statusBar().addPermanentWidget(self.lbl_ctx)
        self.statusBar().setSizeGripEnabled(False)

    def _redondo(self, nombre, ayuda, accion) -> QToolButton:
        b = QToolButton()
        b.setObjectName("redondo")
        b.setFixedSize(32, 32)
        b.setIconSize(QSize(18, 18))
        b.setToolTip(ayuda)
        b.setProperty("icono", nombre)
        b.clicked.connect(accion)
        return b

    def _pantalla_inicio(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        titulo = QLabel(APP)
        titulo.setObjectName("titulo")
        titulo.setAlignment(Qt.AlignCenter)
        sub = QLabel("IDE liviano para PlatformIO  ·  Pablo Jose Lopez Mazariegos  ·  github.com/PabloJLM")
        sub.setObjectName("tenue")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(titulo)
        lay.addWidget(sub)
        lay.addSpacing(12)
        fila = QHBoxLayout()
        fila.setAlignment(Qt.AlignCenter)
        for texto, fn in (("Abrir proyecto", self.abrir_proyecto_dialogo), ("Nuevo proyecto", self.nuevo_proyecto)):
            b = QPushButton(texto)
            b.setMinimumWidth(150)
            b.clicked.connect(fn)
            fila.addWidget(b)
        lay.addLayout(fila)
        lay.addSpacing(8)
        self.caja_recientes = QVBoxLayout()
        self.caja_recientes.setAlignment(Qt.AlignCenter)
        lay.addLayout(self.caja_recientes)
        return w

    def _accion(self, menu, texto, fn, atajo=None, proyecto=False, checable=False):
        a = QAction(texto, self)
        if atajo:
            a.setShortcut(QKeySequence(atajo))
        a.setCheckable(checable)
        a.triggered.connect(fn)
        menu.addAction(a)
        if proyecto:
            self._acc_proyecto.append(a)
        return a

    def _menus(self):
        self._acc_proyecto: list[QAction] = []
        self._acc_tarea: list[QAction] = []
        mb = self.menuBar()

        m = mb.addMenu("&Archivo")
        self._accion(m, "Nuevo proyecto...", self.nuevo_proyecto, "Ctrl+Shift+N")
        self._accion(m, "Abrir proyecto...", self.abrir_proyecto_dialogo, "Ctrl+O")
        self.menu_recientes = m.addMenu("Proyectos recientes")
        m.addSeparator()
        self._accion(m, "Nuevo archivo...", lambda: self.nuevo_archivo(), "Ctrl+N", proyecto=True)
        self._accion(m, "Abrir archivo...", self.abrir_archivo_dialogo, "Ctrl+Shift+O")
        self._accion(m, "Guardar", lambda: self.guardar(), "Ctrl+S")
        self._accion(m, "Guardar como...", lambda: self.guardar_como(), "Ctrl+Shift+S")
        self._accion(m, "Guardar todo", lambda: self.guardar_todo(), "Ctrl+Alt+S")
        self._accion(m, "Cerrar pestana", lambda: self.cerrar_pestana(self.pestanas.currentIndex()), "Ctrl+W")
        m.addSeparator()
        self._accion(m, "Ajustes...", self.abrir_ajustes, "Ctrl+,")
        m.addSeparator()
        self._accion(m, "Salir", self.close, "Ctrl+Q")

        m = mb.addMenu("&Editar")
        ed = lambda f: (lambda: (lambda e: e and f(e))(self.editor_actual()))
        # sin atajo propio: los widgets de texto ya manejan Ctrl+Z/X/C/V/A
        self._accion(m, "Deshacer\tCtrl+Z", ed(lambda e: e.undo()))
        self._accion(m, "Rehacer\tCtrl+Y", ed(lambda e: e.redo()))
        m.addSeparator()
        self._accion(m, "Cortar\tCtrl+X", ed(lambda e: e.cut()))
        self._accion(m, "Copiar\tCtrl+C", ed(lambda e: e.copy()))
        self._accion(m, "Pegar\tCtrl+V", ed(lambda e: e.paste()))
        self._accion(m, "Seleccionar todo\tCtrl+A", ed(lambda e: e.selectAll()))
        m.addSeparator()
        self._accion(m, "Comentar / descomentar", ed(lambda e: e.alternar_comentario()), "Ctrl+/")
        self._accion(m, "Buscar / reemplazar", self.buscador.mostrar, "Ctrl+F")
        self._accion(m, "Ir a linea...", self.ir_a_linea, "Ctrl+G")

        m = mb.addMenu("&Proyecto")
        self._acc_tarea += [
            self._accion(m, "Verificar / compilar", self.verificar, "Ctrl+R", proyecto=True),
            self._accion(m, "Subir", lambda: self.subir(), "Ctrl+U", proyecto=True),
            self._accion(m, "Subir y abrir monitor", lambda: self.subir(True), "Ctrl+Shift+U", proyecto=True),
        ]
        m.addSeparator()
        self._acc_tarea += [
            self._accion(m, "Construir sistema de archivos (buildfs)", lambda: self._run(["-t", "buildfs"], "Construyendo FS", "Imagen FS lista"), proyecto=True),
            self._accion(m, "Subir sistema de archivos (uploadfs)", self.subir_fs, proyecto=True),
            self._accion(m, "Tamano del programa", lambda: self._run(["-t", "size"], "Calculando tamano", "Listo"), proyecto=True),
            self._accion(m, "Borrar flash completa...", self.borrar_flash, proyecto=True),
        ]
        m.addSeparator()
        self._acc_tarea += [
            self._accion(m, "Limpiar (clean)", lambda: self._run(["-t", "clean"], "Limpiando", "Limpio"), proyecto=True),
            self._accion(m, "Limpieza total (fullclean)", self.limpieza_total, proyecto=True),
        ]
        m.addSeparator()
        self._acc_tarea += [
            self._accion(m, "Agregar libreria...", self.agregar_libreria, proyecto=True),
            self._accion(m, "Buscar libreria...", self.buscar_libreria),
            self._accion(m, "Actualizar plataformas y librerias", lambda: self._pio(["pkg", "update"], "Actualizando", "Actualizado"), proyecto=True),
            self._accion(m, "Ver configuracion resuelta", lambda: self._pio(["project", "config"], "Leyendo configuracion", "Listo"), proyecto=True),
            self._accion(m, "Comando pio personalizado...", self.comando_personalizado),
        ]
        m.addSeparator()
        self._accion(m, "Detener tarea", self.detener, "Ctrl+.")
        m.addSeparator()
        self._accion(m, "Editar platformio.ini", self.abrir_ini, proyecto=True)
        self._accion(m, "Abrir carpeta del proyecto", self.abrir_carpeta, proyecto=True)
        self._accion(m, "Abrir en VS Code", self.abrir_vscode, proyecto=True)
        self._accion(m, "Abrir terminal aqui", self.abrir_terminal, proyecto=True)

        m = mb.addMenu("&Herramientas")
        self._accion(m, "Monitor serie", self.alternar_monitor, "Ctrl+Shift+M")
        self._accion(m, "Terminal", self.mostrar_terminal, "Ctrl+`")
        self._accion(m, "Buscar puertos", self.refrescar_puertos, "F5")
        self._acc_tarea.append(self._accion(m, "Listar dispositivos (pio device list)", lambda: self._pio(["device", "list"], "Buscando dispositivos", "Listo")))
        if ES_WINDOWS:
            m.addSeparator()
            self._accion(m, "Panel USB (usbipd)", lambda: (self.inferior.show(), self.inferior.setCurrentWidget(self.div_usb), self.panel_usb.refrescar()))

        m = mb.addMenu("&Ver")
        self.menu_temas = m.addMenu("Tema")
        grupo = QActionGroup(self)
        self._acc_temas = {}
        for nombre in self.temas:
            a = QAction(nombre, self, checkable=True)
            a.triggered.connect(lambda _, n=nombre: self.aplicar_tema(n))
            grupo.addAction(a)
            self.menu_temas.addAction(a)
            self._acc_temas[nombre] = a
        self.acc_fondo = self._accion(m, "Imagen de fondo", self._alternar_fondo, checable=True)
        self.acc_fondo.setChecked(self.aj["fondo"])
        m.addSeparator()
        self._accion(m, "Acercar", lambda: self._zoom(+1), "Ctrl++")
        self._accion(m, "Alejar", lambda: self._zoom(-1), "Ctrl+-")
        self._accion(m, "Tamano normal", lambda: self._zoom(0), "Ctrl+0")
        m.addSeparator()
        self._accion(m, "Mostrar/ocultar explorador", lambda: self.arbol.setVisible(not self.arbol.isVisible()), "Ctrl+B")
        self._accion(m, "Mostrar/ocultar panel inferior", lambda: self.inferior.setVisible(not self.inferior.isVisible()), "Ctrl+J")

        m = mb.addMenu("A&yuda")
        self._accion(m, "Documentacion de platformio.ini", lambda: QDesktopServices.openUrl(QUrl("https://docs.platformio.org/en/latest/projectconf/index.html")))
        self._accion(m, "Buscar placas (boards)", lambda: QDesktopServices.openUrl(QUrl("https://docs.platformio.org/en/latest/boards/index.html")))
        self._accion(m, "Acerca de", self.acerca_de)
        self._actualizar_recientes()

    # ================================================================ apariencia
    def aplicar_tema(self, nombre: str):
        self.aj["tema"] = nombre
        self.t = T.tema(self.temas, nombre)
        QApplication.instance().setStyleSheet(T.hoja_estilo(self.t))
        for b in (self.btn_verificar, self.btn_subir, self.btn_detener):
            b.setIcon(icono(b.property("icono"), self.t["texto_acento"]))
        self.btn_refrescar.setIcon(icono("refrescar", self.t["texto"]))
        self.btn_monitor.setIcon(icono("monitor", self.t["texto"]))
        self.setWindowIcon(icono("app", self.t["acento"], 32))
        self.salida.set_tema(self.t)
        for term in (self.terminal, self.term_usb):
            if term:
                term.set_tema(self.t)
        for ed in self.editores():
            self._estilo_editor(ed)
        if nombre in getattr(self, "_acc_temas", {}):
            self._acc_temas[nombre].setChecked(True)
        self.s.setValue("tema", nombre)
        self._aplicar_fuente()  # setStyleSheet reinicia las fuentes de algunos widgets

    def _estilo_editor(self, ed: EditorCodigo):
        ed.set_tema(self.t)
        ed.set_fondo(T.ruta_bg(self.t), self.aj["fondo"], self.aj["opacidad"] / 100)

    def _aplicar_fuente(self):
        f = QFont(self.aj["fuente"], self.aj["tam"])
        f.setStyleHint(QFont.Monospace)
        chica = QFont(f)
        chica.setPointSize(max(7, self.aj["tam"] - 1))
        for ed in self.editores():
            ed.set_fuente(f, self.aj["sangria"])
        self.salida.setFont(chica)
        self.panel_monitor.salida.setFont(chica)
        for term in (self.terminal, self.term_usb):
            if term:
                term.salida.setFont(chica)

    def _zoom(self, paso: int):
        self.aj["tam"] = 11 if paso == 0 else max(7, min(32, self.aj["tam"] + paso))
        self.s.setValue("tam", self.aj["tam"])
        self._aplicar_fuente()

    def _alternar_fondo(self, on: bool):
        self.aj["fondo"] = on
        self.s.setValue("fondo", on)
        for ed in self.editores():
            self._estilo_editor(ed)
        if on and not T.ruta_bg(self.t):
            self._estado(f"El tema '{self.aj['tema']}' no tiene imagen (o falta en imgs/bg)")

    def abrir_ajustes(self):
        d = DialogoAjustes(self.aj, list(self.temas), self)
        if not d.exec_():
            return
        v = d.valores()
        cambio_modo = (v["modo"], v["distro"]) != (self.cfg.modo, self.cfg.distro)
        self.aj.update(v)
        for k in ("tema", "fuente", "tam", "sangria", "fondo", "opacidad", "guardar_antes", "verbose", "modo", "distro"):
            self.s.setValue(k, self.aj[k])
        self.cfg.modo, self.cfg.distro = self.aj["modo"], self.aj["distro"]
        self.acc_fondo.setChecked(self.aj["fondo"])
        self.aplicar_tema(self.aj["tema"])
        self._aplicar_fuente()
        self._contexto()
        if cambio_modo:
            self.refrescar_puertos()

    # ================================================================ proyecto
    def abrir_proyecto_dialogo(self):
        d = QFileDialog.getExistingDirectory(self, "Abrir proyecto PlatformIO", self.proyecto or str(Path.home()))
        if d:
            self.abrir_proyecto(d)

    def nuevo_proyecto(self):
        base = str(Path(self.proyecto).parent) if self.proyecto else str(Path.home())
        d = DialogoNuevoProyecto(base, self.cfg.usa_wsl, self)
        if d.exec_() and d.ruta_creada:
            self.abrir_proyecto(d.ruta_creada)

    def abrir_proyecto(self, ruta: str, archivos: list[str] | None = None):
        ruta = str(Path(ruta).resolve())
        if not Path(ruta).is_dir():
            QMessageBox.warning(self, APP, f"No existe la carpeta:\n{ruta}")
            return
        if not (Path(ruta) / "platformio.ini").exists():
            r = QMessageBox.question(self, APP, "Esa carpeta no tiene platformio.ini.\n¿Abrirla de todos modos?")
            if r != QMessageBox.Yes:
                return
        if self.proyecto and os.path.normcase(ruta) != os.path.normcase(self.proyecto):
            if not self._cerrar_todas():
                return
        if self.proyecto:
            ini_viejo = str(Path(self.proyecto) / "platformio.ini")
            if ini_viejo in self.vigilante.files():
                self.vigilante.removePath(ini_viejo)
        self.proyecto = ruta
        self.modelo.setRootPath(ruta)
        self.arbol.setRootIndex(self.filtro.mapFromSource(self.modelo.index(ruta)))
        ini = Path(ruta) / "platformio.ini"
        if ini.exists():
            self.vigilante.addPath(str(ini))
        self.cargar_envs()
        self._agregar_reciente(ruta)
        self.setWindowTitle(f"{Path(ruta).name} - {APP}")
        self.s.setValue("ultimo_proyecto", ruta)
        abrir = [a for a in (archivos or []) if Path(a).exists()]
        if not abrir:
            src = Path(ruta) / "src"
            candidatos = [src / "main.cpp", src / "main.c"] + sorted(src.glob("*.cpp")) + sorted(src.glob("*.c"))
            abrir = [str(c) for c in candidatos if c.exists()][:1]
        for a in abrir:
            self.abrir_archivo(a)
        if not abrir:
            self.pila.setCurrentIndex(1)
        self._habilitar()
        self.refrescar_puertos()
        self.terminal.ir_a(ruta)

    def cargar_envs(self):
        if not self.proyecto:
            return
        envs, defecto, self._velocidades = leer_ini(Path(self.proyecto) / "platformio.ini")
        anterior = self.combo_env.currentData()
        guardado = self.s.value(f"env/{self.proyecto}", "")
        self.combo_env.blockSignals(True)
        self.combo_env.clear()
        if len(envs) > 1:
            self.combo_env.addItem("Todos los entornos", None)
        for e in envs:
            self.combo_env.addItem(e, e)
        if not envs:
            self.combo_env.addItem("(sin entornos)", None)
        for preferido in (anterior, guardado, defecto):
            i = self.combo_env.findData(preferido) if preferido else -1
            if i >= 0:
                self.combo_env.setCurrentIndex(i)
                break
        else:
            if len(envs) > 1:
                self.combo_env.setCurrentIndex(1)
        self.combo_env.blockSignals(False)
        self._env_cambiado()

    def _env_cambiado(self, *_):
        e = self.env_actual()
        if self.proyecto and e:
            self.s.setValue(f"env/{self.proyecto}", e)
        v = getattr(self, "_velocidades", {}).get(e) if e else None
        if v is None and getattr(self, "_velocidades", None):
            v = next(iter(self._velocidades.values()))
        if v:
            self.panel_monitor.set_baudios(v)
        self._contexto()

    def env_actual(self) -> str | None:
        return self.combo_env.currentData()

    def puerto_actual(self) -> str | None:
        return self.combo_puerto.currentData()

    def _agregar_reciente(self, ruta):
        rec = self._recientes()
        rec = [ruta] + [r for r in rec if os.path.normcase(r) != os.path.normcase(ruta)]
        self.s.setValue("recientes", json.dumps(rec[:MAX_RECIENTES]))
        self._actualizar_recientes()

    def _recientes(self) -> list[str]:
        try:
            return [r for r in json.loads(self.s.value("recientes", "[]")) if isinstance(r, str)]
        except (TypeError, ValueError):
            return []

    def _actualizar_recientes(self):
        self.menu_recientes.clear()
        while self.caja_recientes.count():
            w = self.caja_recientes.takeAt(0).widget()
            if w:
                w.deleteLater()
        rec = [r for r in self._recientes() if Path(r).is_dir()]
        if not rec:
            a = self.menu_recientes.addAction("(vacio)")
            a.setEnabled(False)
            return
        etiqueta = QLabel("Recientes")
        etiqueta.setObjectName("tenue")
        etiqueta.setAlignment(Qt.AlignCenter)
        self.caja_recientes.addWidget(etiqueta)
        for r in rec:
            self.menu_recientes.addAction(r, lambda r=r: self.abrir_proyecto(r))
        for r in rec[:5]:
            b = QPushButton(f"{Path(r).name}    {r}")
            b.setFlat(True)
            b.setStyleSheet("text-align:left; border:none; padding:3px 8px;")
            b.clicked.connect(lambda _, r=r: self.abrir_proyecto(r))
            self.caja_recientes.addWidget(b)

    # ================================================================ archivos
    def editores(self) -> list[EditorCodigo]:
        return [self.pestanas.widget(i) for i in range(self.pestanas.count())]

    def editor_actual(self) -> EditorCodigo | None:
        w = self.pestanas.currentWidget()
        return w if isinstance(w, EditorCodigo) else None

    def _buscar_editor(self, ruta: str):
        clave = os.path.normcase(os.path.abspath(ruta))
        for i, ed in enumerate(self.editores()):
            if ed.ruta and os.path.normcase(os.path.abspath(ed.ruta)) == clave:
                return i, ed
        return -1, None

    def abrir_archivo(self, ruta: str, linea: int | None = None, col: int = 1):
        ruta = str(Path(ruta).resolve())
        i, ed = self._buscar_editor(ruta)
        if ed is None:
            ed = EditorCodigo(ruta)
            try:
                ed.cargar()
            except OSError as e:
                QMessageBox.warning(self, APP, f"No se pudo abrir:\n{e}")
                ed.deleteLater()
                return None
            f = QFont(self.aj["fuente"], self.aj["tam"])
            f.setStyleHint(QFont.Monospace)
            ed.set_fuente(f, self.aj["sangria"])
            self._estilo_editor(ed)
            ed.document().modificationChanged.connect(lambda _, e=ed: self._titulo_pestana(e))
            ed.posicion.connect(lambda l, c: self.lbl_pos.setText(f"Ln {l}, Col {c}"))
            i = self.pestanas.addTab(ed, Path(ruta).name)
            self.pestanas.setTabToolTip(i, ruta)
            if ruta not in self.vigilante.files():
                self.vigilante.addPath(ruta)
        self.pestanas.setCurrentIndex(i)
        self.pila.setCurrentIndex(1)
        if linea:
            ed.ir_a(linea, col)
        else:
            ed.setFocus()
        return ed

    def abrir_archivo_dialogo(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Abrir archivo", self.proyecto or str(Path.home()),
                                              "Codigo (*.c *.cpp *.h *.hpp *.ino *.ini *.py *.txt *.md *.json);;Todos (*)")
        if ruta:
            self.abrir_archivo(ruta)

    def _titulo_pestana(self, ed: EditorCodigo):
        i = self.pestanas.indexOf(ed)
        if i >= 0:
            nombre = Path(ed.ruta).name if ed.ruta else "sin titulo"
            self.pestanas.setTabText(i, nombre + ("  *" if ed.document().isModified() else ""))

    def _pestana_cambiada(self, _i):
        ed = self.editor_actual()
        if ed:
            c = ed.textCursor()
            self.lbl_pos.setText(f"Ln {c.blockNumber() + 1}, Col {c.positionInBlock() + 1}")
        else:
            self.lbl_pos.setText("")

    def guardar(self, ed: EditorCodigo | None = None) -> bool:
        ed = ed or self.editor_actual()
        if not ed:
            return False
        if not ed.ruta:
            return self.guardar_como(ed)
        try:
            ed.guardar()
        except OSError as e:
            QMessageBox.critical(self, APP, f"No se pudo guardar:\n{e}")
            return False
        self._titulo_pestana(ed)
        self._estado(f"Guardado {Path(ed.ruta).name}")
        if Path(ed.ruta).name == "platformio.ini":
            self.cargar_envs()
        return True

    def guardar_como(self, ed: EditorCodigo | None = None) -> bool:
        ed = ed or self.editor_actual()
        if not ed:
            return False
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar como", ed.ruta or self.proyecto or str(Path.home()))
        if not ruta:
            return False
        viejo = ed.ruta
        try:
            ed.guardar(ruta)
        except OSError as e:
            QMessageBox.critical(self, APP, f"No se pudo guardar:\n{e}")
            return False
        if viejo and viejo in self.vigilante.files():
            self.vigilante.removePath(viejo)
        self.vigilante.addPath(ed.ruta)
        self.pestanas.setTabToolTip(self.pestanas.indexOf(ed), ed.ruta)
        self._titulo_pestana(ed)
        return True

    def guardar_todo(self):
        for ed in self.editores():
            if ed.document().isModified() and ed.ruta:
                self.guardar(ed)

    def nuevo_archivo(self, carpeta: str | None = None):
        if not self.proyecto:
            return
        carpeta = carpeta or str(Path(self.proyecto) / "src")
        nombre, ok = QInputDialog.getText(self, "Nuevo archivo", f"Nombre (en {carpeta}):", text="nuevo.cpp")
        if not ok or not nombre.strip():
            return
        ruta = Path(carpeta) / nombre.strip()
        if ruta.exists():
            QMessageBox.warning(self, APP, "Ese archivo ya existe.")
            return
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            if ruta.suffix in (".h", ".hpp"):
                guarda = re.sub(r"\W", "_", ruta.name).upper()
                ruta.write_text(f"#ifndef {guarda}\n#define {guarda}\n\n\n\n#endif\n", encoding="utf-8")
            else:
                ruta.write_text("", encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, APP, str(e))
            return
        self.abrir_archivo(str(ruta))

    def cerrar_pestana(self, i: int) -> bool:
        if i < 0:
            return True
        ed = self.pestanas.widget(i)
        if ed.document().isModified():
            self.pestanas.setCurrentIndex(i)
            r = QMessageBox.question(self, APP, f"¿Guardar cambios en {Path(ed.ruta).name if ed.ruta else 'sin titulo'}?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel or (r == QMessageBox.Save and not self.guardar(ed)):
                return False
        if ed.ruta and ed.ruta in self.vigilante.files() and not ed.ruta.endswith("platformio.ini"):
            self.vigilante.removePath(ed.ruta)
        self.pestanas.removeTab(i)
        ed.deleteLater()
        if self.pestanas.count() == 0 and not self.proyecto:
            self.pila.setCurrentIndex(0)
        return True

    def _cerrar_todas(self) -> bool:
        while self.pestanas.count():
            if not self.cerrar_pestana(0):
                return False
        return True

    def _archivo_cambiado(self, ruta: str):
        # algunos editores (VS Code) reemplazan el archivo: hay que volver a vigilarlo
        QTimer.singleShot(150, lambda: Path(ruta).exists() and ruta not in self.vigilante.files()
                          and self.vigilante.addPath(ruta))
        if self.proyecto and os.path.normcase(ruta) == os.path.normcase(str(Path(self.proyecto) / "platformio.ini")):
            QTimer.singleShot(200, self.cargar_envs)
        _, ed = self._buscar_editor(ruta)
        if not ed or not Path(ruta).exists() or ed.texto_en_disco_igual():
            return
        if not ed.document().isModified():
            ed.recargar()
            self._estado(f"Recargado {Path(ruta).name} (cambiado fuera del IDE)")
            return
        r = QMessageBox.question(self, APP, f"{Path(ruta).name} cambio fuera del IDE y tienes cambios sin guardar.\n"
                                 "¿Recargar desde el disco y perder tus cambios?")
        if r == QMessageBox.Yes:
            ed.recargar()

    def _abrir_desde_arbol(self, indice: QModelIndex):
        fuente = self.filtro.mapToSource(indice)
        if not self.modelo.isDir(fuente):
            self.abrir_archivo(self.modelo.filePath(fuente))

    def _menu_arbol(self, pos):
        indice = self.arbol.indexAt(pos)
        ruta = self.modelo.filePath(self.filtro.mapToSource(indice)) if indice.isValid() else self.proyecto
        if not ruta:
            return
        carpeta = ruta if Path(ruta).is_dir() else str(Path(ruta).parent)
        m = QMenu(self)
        m.addAction("Nuevo archivo aqui...", lambda: self.nuevo_archivo(carpeta))
        m.addAction("Nueva carpeta aqui...", lambda: self._nueva_carpeta(carpeta))
        m.addSeparator()
        m.addAction("Mostrar en el explorador", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(carpeta)))
        m.exec_(self.arbol.viewport().mapToGlobal(pos))

    def _nueva_carpeta(self, carpeta):
        nombre, ok = QInputDialog.getText(self, "Nueva carpeta", "Nombre:")
        if ok and nombre.strip():
            try:
                (Path(carpeta) / nombre.strip()).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                QMessageBox.critical(self, APP, str(e))

    def ir_a_linea(self):
        ed = self.editor_actual()
        if not ed:
            return
        n, ok = QInputDialog.getInt(self, "Ir a linea", "Linea:", ed.textCursor().blockNumber() + 1, 1, ed.blockCount())
        if ok:
            ed.ir_a(n)

    def _ir_a_error(self, archivo: str, linea: int, col: int):
        ruta = self._ruta_local(archivo)
        if ruta:
            self.abrir_archivo(ruta, linea, col)
        else:
            self._estado(f"No se encontro {archivo}")

    def _ruta_local(self, f: str) -> str | None:
        f = f.strip()
        if ES_WINDOWS and self.cfg.usa_wsl:
            m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", f)
            if m:
                f = f"{m.group(1).upper()}:\\" + m.group(2).replace("/", "\\")
            elif f.startswith("/"):
                if not self.cfg.distro:
                    return None
                f = f"\\\\wsl.localhost\\{self.cfg.distro}" + f.replace("/", "\\")
        p = Path(f)
        if not p.is_absolute() and self.proyecto:
            p = Path(self.proyecto) / p
        return str(p) if p.exists() else None

    # ================================================================ tareas pio
    def _sin_proyecto(self) -> bool:
        if not self.proyecto:
            QMessageBox.information(self, APP, "Primero abre o crea un proyecto.")
            return True
        return False

    def _args_env(self) -> list[str]:
        e = self.env_actual()
        return ["-e", e] if e else []

    def _args_puerto(self) -> list[str]:
        p = self.puerto_actual()
        return ["--upload-port", p] if p else []

    def _pio(self, args: list[str], titulo: str, ok: str, al_terminar=None, cwd_requerido=True):
        if cwd_requerido and self._sin_proyecto():
            return
        if self.tarea.activo():
            self._estado("Ya hay una tarea en curso (Ctrl+. para detenerla)")
            return
        if self.aj["guardar_antes"]:
            self.guardar_todo()
        comando = ["pio"] + args
        if self.aj["verbose"] and args[:1] == ["run"]:
            comando.append("-v")
        self.salida.clear()
        self.inferior.setCurrentWidget(self.salida)
        self.inferior.show()
        self.salida.agregar("$ " + " ".join(shlex.quote(a) for a in comando), "info")
        self._tarea_info = (titulo, ok)
        self._al_terminar = al_terminar
        self._uso = {}
        self.lbl_uso.setText("")
        self._t0 = time.monotonic()
        self.tarea.iniciar(comando, self.proyecto or str(Path.home()))
        self._reloj.start()
        self._tic()
        self._habilitar()

    def _run(self, extra: list[str], titulo: str, ok: str, al_terminar=None):
        self._pio(["run"] + self._args_env() + extra, titulo, ok, al_terminar)

    def verificar(self):
        self._run([], "Compilando", "Compilacion completa")

    def subir(self, monitorear: bool = False):
        if self._sin_proyecto():
            return
        self._con_puerto_libre(lambda: self._run(["-t", "upload"] + self._args_puerto(), "Subiendo",
                                                 "Subida completa", self._tras_subir), monitorear)

    def subir_fs(self):
        if self._sin_proyecto():
            return
        self._con_puerto_libre(lambda: self._run(["-t", "uploadfs"] + self._args_puerto(), "Subiendo FS",
                                                 "Sistema de archivos subido", self._tras_subir), False)

    def borrar_flash(self):
        if self._sin_proyecto():
            return
        r = QMessageBox.warning(self, APP, "Esto borra TODA la flash de la placa (programa y datos).\n¿Continuar?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            self._con_puerto_libre(lambda: self._run(["-t", "erase"] + self._args_puerto(), "Borrando flash",
                                                     "Flash borrada", self._tras_subir), False)

    def limpieza_total(self):
        r = QMessageBox.question(self, APP, "fullclean borra la compilacion y las librerias descargadas del proyecto.\n¿Continuar?")
        if r == QMessageBox.Yes:
            self._run(["-t", "fullclean"], "Limpieza total", "Limpio")

    def agregar_libreria(self):
        nombre, ok = QInputDialog.getText(self, "Agregar libreria",
                                          "Libreria (ej. lovyan03/LovyanGFX o bblanchon/ArduinoJson@^7):")
        if ok and nombre.strip():
            self._pio(["pkg", "install"] + self._args_env() + ["-l", nombre.strip()],
                      "Instalando libreria", "Libreria agregada a lib_deps")

    def buscar_libreria(self):
        texto, ok = QInputDialog.getText(self, "Buscar libreria", "Buscar en el registro de PlatformIO:")
        if ok and texto.strip():
            self._pio(["pkg", "search", texto.strip()], "Buscando", "Busqueda terminada", cwd_requerido=False)

    def comando_personalizado(self):
        ultimo = self.s.value("ultimo_comando", "run -t upload")
        texto, ok = QInputDialog.getText(self, "Comando pio", "pio ", text=ultimo)
        if ok and texto.strip():
            self.s.setValue("ultimo_comando", texto.strip())
            try:
                args = shlex.split(texto.strip())
            except ValueError as e:
                QMessageBox.warning(self, APP, str(e))
                return
            if args and args[0] == "pio":
                args = args[1:]
            self._pio(args, "Ejecutando", "Terminado", cwd_requerido=False)

    def detener(self):
        if self.tarea.activo():
            self.salida.agregar("Deteniendo...", "aviso")
            self.tarea.detener()

    def _con_puerto_libre(self, fn, reabrir: bool):
        """El monitor ocupa el puerto: se cierra antes de subir y se reabre despues."""
        if self.tarea.activo():
            self._estado("Ya hay una tarea en curso (Ctrl+. para detenerla)")
            return
        self._reabrir_monitor = reabrir or self.monitor.activo()
        if self.monitor.activo():
            self._pendiente = fn
            self.monitor.detener()
        else:
            fn()

    def _tras_subir(self, codigo: int):
        if self._reabrir_monitor:
            self._reabrir_monitor = False
            if codigo == 0:
                self.inferior.setCurrentWidget(self.panel_monitor)
                QTimer.singleShot(600, self.conectar_monitor)

    def _linea_tarea(self, linea: str):
        self.salida.agregar(linea)
        m = RX_USO.match(linea.strip())
        if m:
            self._uso[m.group(1)] = m.group(2)

    def _fin_tarea(self, codigo: int, segundos: float):
        self._reloj.stop()
        titulo, ok = self._tarea_info
        if self.tarea.fue_detenido:
            self.salida.agregar("[STOP] Detenido", "aviso")
            self._estado("Detenido")
        elif codigo == 0:
            self.salida.agregar(f"[OK] {ok}  ({segundos:.1f} s)", "ok")
            self._estado(f"{ok}  ({segundos:.1f} s)")
        else:
            self.salida.agregar(f"[ERROR] Error (codigo {codigo}). Doble clic en una linea de error para ir al archivo.", "error")
            self._estado(f"Error en: {titulo.lower()}")
        if self._uso:
            self.lbl_uso.setText("   ".join(f"{k} {v}" for k, v in self._uso.items()))
        fn, self._al_terminar = self._al_terminar, None
        self._habilitar()
        if fn:
            fn(codigo)

    def _tic(self):
        titulo, _ = self._tarea_info
        self._estado(f"{titulo}...  {int(time.monotonic() - self._t0)} s")

    # ================================================================ puertos y monitor
    def refrescar_puertos(self):
        if self._buscando_puertos:
            return
        self._buscando_puertos = True
        self.btn_refrescar.setEnabled(False)
        correr_pio_rapido(self.cfg, ["pio", "device", "list", "--json-output"], self.proyecto, self._puertos_listos)

    def _puertos_listos(self, codigo: int, texto: str):
        self._buscando_puertos = False
        self.btn_refrescar.setEnabled(True)
        datos = []
        inicio = texto.find("[")
        if codigo == 0 and inicio >= 0:
            try:
                datos = json.loads(texto[inicio:])
            except ValueError:
                datos = []
        elif codigo != 0:
            self._estado("No se pudo ejecutar 'pio device list'. ¿Esta instalado PlatformIO?")
        encontrados = [(d.get("port", ""), d.get("description", "")) for d in datos
                       if d.get("port") and str(d.get("hwid", "n/a")).lower() != "n/a"]
        actual = self.puerto_actual() or self.s.value("puerto", "")
        self.puertos = [p for p, _ in encontrados]
        self.combo_puerto.blockSignals(True)
        self.combo_puerto.clear()
        self.combo_puerto.addItem("Puerto: automatico", None)
        for p, desc in encontrados:
            self.combo_puerto.addItem(f"{p}   {desc}" if desc and desc != "n/a" else p, p)
        i = self.combo_puerto.findData(actual) if actual else -1
        self.combo_puerto.setCurrentIndex(max(0, i))
        self.combo_puerto.blockSignals(False)
        self._contexto()

    def alternar_monitor(self):
        self.inferior.show()
        if self.inferior.currentWidget() is self.panel_monitor and self.monitor.activo():
            self.monitor.detener()
            return
        self.inferior.setCurrentWidget(self.panel_monitor)
        if not self.monitor.activo():
            self.conectar_monitor()

    def conectar_monitor(self):
        if self.monitor.activo():
            return
        puerto = self.puerto_actual() or (self.puertos[0] if self.puertos else None)
        if not puerto:
            self.panel_monitor.set_conectado(False)
            ayuda = " Conecta la placa en la pestana USB." if self.panel_usb else ""
            self.panel_monitor.mostrar_estado("No hay puerto." + ayuda + " Luego busca puertos (F5).")
            self.refrescar_puertos()
            return
        baud = self.panel_monitor.baudios()
        codigo = 'import base64;exec(base64.b64decode("%s"))' % base64.b64encode(SCRIPT_MONITOR.read_bytes()).decode()
        if self.cfg.usa_bash:
            script = ('PY="$HOME/.platformio/penv/bin/python"; [ -x "$PY" ] || PY=python3; '
                      f'exec "$PY" -u -c {shlex.quote(codigo)} {shlex.quote(puerto)} {baud}')
            self.monitor.iniciar(script=script, cwd=None)
        else:
            py = Path.home() / ".platformio" / "penv" / "Scripts" / "python.exe"
            self.monitor.iniciar(args=[str(py) if py.exists() else sys.executable, "-u", "-c", codigo, puerto, str(baud)])
        self.panel_monitor.set_conectado(True, puerto, baud)
        self.s.setValue("puerto", puerto)

    def _fin_monitor(self, _codigo, _segundos):
        self.panel_monitor.set_conectado(False)
        fn, self._pendiente = self._pendiente, None
        if fn:
            fn()

    def _baudios_cambiados(self, _baud):
        if self.monitor.activo():
            self._pendiente = self.conectar_monitor
            self.monitor.detener()

    # ================================================================ externos
    def abrir_ini(self):
        ini = Path(self.proyecto) / "platformio.ini"
        if ini.exists():
            self.abrir_archivo(str(ini))

    def abrir_carpeta(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.proyecto))

    def abrir_vscode(self):
        if ES_WINDOWS:
            lanzar_silencioso(["cmd", "/c", "code", self.proyecto])
        else:
            lanzar_silencioso(["code", self.proyecto])

    def mostrar_terminal(self):
        self.inferior.show()
        self.inferior.setCurrentWidget(self.terminal)
        self.terminal.entrada.setFocus()

    def abrir_terminal(self):
        from PyQt5.QtCore import QProcess
        if ES_WINDOWS:
            if self.cfg.usa_wsl:
                args = (["-d", self.cfg.distro] if self.cfg.distro else []) + ["--cd", self.proyecto]
                QProcess.startDetached("wsl.exe", args, self.proyecto)
            else:
                QProcess.startDetached("cmd.exe", [], self.proyecto)
            return
        for term, args in (("x-terminal-emulator", []), ("gnome-terminal", [f"--working-directory={self.proyecto}"]),
                           ("konsole", ["--workdir", self.proyecto]), ("xterm", [])):
            if QProcess.startDetached(term, args, self.proyecto):
                return
        self._estado("No se encontro una terminal")

    def acerca_de(self):
        QMessageBox.about(self, APP, f"<b>{APP} {VERSION}</b><br>IDE liviano sobre PlatformIO Core.<br><br>"
                                     "Pablo Jose Lopez Mazariegos<br>Guatemala, 2026<br>"
                                     "<a href='https://github.com/PabloJLM'>github.com/PabloJLM</a>")

    # ================================================================ estado
    def _estado(self, texto: str):
        self.lbl_estado.setText(texto)

    def _contexto(self):
        e = self.env_actual() or ("todos" if self.combo_env.count() > 1 else "-")
        p = self.puerto_actual() or "auto"
        self.lbl_ctx.setText(f"{e}  ·  {p}  ·  {self.cfg.descripcion()}")

    def _habilitar(self):
        corriendo = self.tarea.activo()
        hay = self.proyecto is not None
        for a in self._acc_proyecto:
            a.setEnabled(hay)
        for a in self._acc_tarea:
            if a in self._acc_proyecto:
                a.setEnabled(hay and not corriendo)
            else:
                a.setEnabled(not corriendo)
        self.btn_verificar.setEnabled(hay and not corriendo)
        self.btn_subir.setEnabled(hay and not corriendo)
        self.btn_detener.setEnabled(corriendo)

    # ================================================================ sesion
    def restaurar(self, proyecto_cli: str | None = None):
        geo = self.s.value("geometria")
        if geo is not None:
            self.restoreGeometry(geo)
        for clave, div in (("div_h", self.div_h), ("div_v", self.div_v)):
            v = self.s.value(clave)
            if v is not None:
                div.restoreState(v)
        proyecto = proyecto_cli or self.s.value("ultimo_proyecto", "")
        if proyecto and Path(proyecto).is_dir():
            try:
                abiertos = json.loads(self.s.value("abiertos", "[]")) if not proyecto_cli else []
            except (TypeError, ValueError):
                abiertos = []
            self.abrir_proyecto(proyecto, abiertos)
        else:
            self.refrescar_puertos()
        if self.panel_usb:
            if self.s.value("usb/hwid", ""):
                self.panel_usb.auto_conectar()
            else:
                self.panel_usb.refrescar()

    def closeEvent(self, e):
        sucios = [ed for ed in self.editores() if ed.document().isModified()]
        if sucios:
            r = QMessageBox.question(self, APP, f"Hay {len(sucios)} archivo(s) sin guardar.",
                                     QMessageBox.SaveAll | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                e.ignore()
                return
            if r == QMessageBox.SaveAll:
                for ed in sucios:
                    if not self.guardar(ed):
                        e.ignore()
                        return
        self.s.setValue("abiertos", json.dumps([ed.ruta for ed in self.editores() if ed.ruta]))
        self.s.setValue("geometria", self.saveGeometry())
        self.s.setValue("div_h", self.div_h.saveState())
        self.s.setValue("div_v", self.div_v.saveState())
        self.tarea.detener()
        self.monitor.detener()
        if self.panel_usb:
            self.panel_usb.cerrar()
        for term in (self.terminal, self.term_usb):
            if term:
                term.cerrar()
        e.accept()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setStyle("Fusion")
    v = Ventana()
    v.show()
    proyecto = sys.argv[1] if len(sys.argv) > 1 else None
    QTimer.singleShot(0, lambda: v.restaurar(proyecto))
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
