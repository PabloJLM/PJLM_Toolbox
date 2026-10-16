"""Paneles inferiores: salida de compilacion, monitor serie y USB (usbipd-win)."""
from __future__ import annotations

import codecs
import html
import re
import time

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ejecutor import correr_rapido, correr_sincrono, decodificar

_RX_ERR = re.compile(r"(?i)\b(error|fatal|failed|traceback|no such file)\b")
_RX_AVISO = re.compile(r"(?i)\bwarning\b")
_RX_OK = re.compile(r"\[SUCCESS\]|\bSUCCESS\b|Hard resetting|Leaving\.\.\.")
_RX_UBICACION = re.compile(r"^(?P<f>(?:[A-Za-z]:)?[^:\n]+?):(?P<l>\d+)(?::(?P<c>\d+))?:")


class PanelSalida(QPlainTextEdit):
    """Consola de salida de PlatformIO. Doble clic en un error abre el archivo."""

    ir_a = pyqtSignal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("salida")
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.colores = {"ok": "#9ECE6A", "error": "#F7768E", "aviso": "#E0AF68",
                        "info": "#7AA2F7", "normal": "#C3CCE3"}
        self._lineas: list[tuple[str, str]] = []

    def set_tema(self, t: dict):
        self.colores = dict(t["consola"])
        self.colores["normal"] = t["texto_consola"]
        # vuelve a pintar lo que ya habia con los colores nuevos
        lineas, self._lineas = self._lineas, []
        super().clear()
        for texto, tipo in lineas:
            self.agregar(texto, tipo)

    def clear(self):
        self._lineas = []
        super().clear()

    def agregar(self, texto: str, tipo: str | None = None):
        if tipo is None:
            if _RX_ERR.search(texto):
                tipo = "error"
            elif _RX_AVISO.search(texto):
                tipo = "aviso"
            elif _RX_OK.search(texto):
                tipo = "ok"
            else:
                tipo = "normal"
        self._lineas.append((texto, tipo))
        if len(self._lineas) > 5000:
            del self._lineas[:1000]
        color = self.colores.get(tipo, self.colores["normal"])
        peso = "font-weight:bold;" if texto.startswith(("$", "✔", "✖")) else ""
        self.appendHtml(f'<span style="color:{color};{peso}white-space:pre">{html.escape(texto)}</span>')

    def mouseDoubleClickEvent(self, e):
        linea = self.cursorForPosition(e.pos()).block().text().strip()
        m = _RX_UBICACION.match(linea)
        if m:
            self.ir_a.emit(m.group("f"), int(m.group("l")), int(m.group("c") or 1))
            return
        super().mouseDoubleClickEvent(e)


_BAUDIOS = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 74880, 115200,
            230400, 250000, 460800, 500000, 921600, 1000000, 2000000]
_FINES = [("Sin ajuste de linea", b""), ("Nueva linea (LF)", b"\n"),
          ("Retorno de carro (CR)", b"\r"), ("CR + LF", b"\r\n")]


class PanelMonitor(QWidget):
    """Monitor serie estilo Arduino IDE."""

    conectar = pyqtSignal(bool)
    enviar = pyqtSignal(bytes)
    baudios_cambiados = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dec = codecs.getincrementaldecoder("utf-8")("replace")
        self._pendiente: list[str] = []
        self._inicio_linea = True
        self._historial: list[str] = []
        self._idx_hist = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        barra = QWidget()
        barra.setObjectName("barra_panel")
        barra.setAttribute(Qt.WA_StyledBackground, True)
        b = QHBoxLayout(barra)
        b.setContentsMargins(8, 4, 8, 4)
        b.setSpacing(8)
        self.btn = QPushButton("Conectar")
        self.btn.setCheckable(True)
        self.btn.clicked.connect(lambda on: self.conectar.emit(on))
        self.estado = QLabel("Desconectado")
        self.estado.setObjectName("tenue")
        self.chk_auto = QCheckBox("Autoscroll")
        self.chk_auto.setChecked(True)
        self.chk_hora = QCheckBox("Marca de tiempo")
        self.combo_fin = QComboBox()
        for nombre, valor in _FINES:
            self.combo_fin.addItem(nombre, valor)
        self.combo_fin.setCurrentIndex(1)
        self.combo_baud = QComboBox()
        for v in _BAUDIOS:
            self.combo_baud.addItem(f"{v} baudios", v)
        self.combo_baud.setCurrentIndex(_BAUDIOS.index(115200))
        self.combo_baud.currentIndexChanged.connect(lambda _: self.baudios_cambiados.emit(self.baudios()))
        limpiar = QPushButton("Limpiar")
        limpiar.clicked.connect(self.limpiar)
        for w in (self.btn, self.estado):
            b.addWidget(w)
        b.addStretch()
        for w in (self.chk_auto, self.chk_hora, self.combo_fin, self.combo_baud, limpiar):
            b.addWidget(w)
        lay.addWidget(barra)

        self.salida = QPlainTextEdit()
        self.salida.setObjectName("monitor")
        self.salida.setReadOnly(True)
        self.salida.setMaximumBlockCount(10000)
        lay.addWidget(self.salida, 1)

        fila = QWidget()
        fila.setObjectName("barra_panel")
        fila.setAttribute(Qt.WA_StyledBackground, True)
        f = QHBoxLayout(fila)
        f.setContentsMargins(8, 4, 8, 4)
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Mensaje (Enter para enviar, flechas para historial)")
        self.entrada.returnPressed.connect(self._enviar)
        self.entrada.installEventFilter(self)
        self.btn_enviar = QPushButton("Enviar")
        self.btn_enviar.clicked.connect(self._enviar)
        f.addWidget(self.entrada, 1)
        f.addWidget(self.btn_enviar)
        lay.addWidget(fila)

        # agrupa los datos que llegan para repintar como mucho ~25 veces por segundo
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._volcar)
        self.set_conectado(False)

    def baudios(self) -> int:
        return int(self.combo_baud.currentData())

    def set_baudios(self, valor: int):
        if valor not in _BAUDIOS:
            self.combo_baud.addItem(f"{valor} baudios", valor)
        i = self.combo_baud.findData(valor)
        self.combo_baud.blockSignals(True)
        self.combo_baud.setCurrentIndex(i)
        self.combo_baud.blockSignals(False)

    def set_conectado(self, on: bool, puerto: str = "", baud: int = 0):
        self.btn.setChecked(on)
        self.btn.setText("Desconectar" if on else "Conectar")
        self.entrada.setEnabled(on)
        self.btn_enviar.setEnabled(on)
        if on:
            self.estado.setText(f"{puerto} @ {baud}")
            self._timer.start()
        else:
            self._volcar()
            self._timer.stop()
            self.estado.setText("Desconectado")

    def mostrar_estado(self, texto: str):
        self.estado.setText(texto)

    def limpiar(self):
        self.salida.clear()
        self._inicio_linea = True

    def recibir(self, datos: bytes):
        texto = self._dec.decode(datos).replace("\r\n", "\n").replace("\r", "")
        if texto:
            self._pendiente.append(texto)

    def _volcar(self):
        if not self._pendiente:
            return
        texto = "".join(self._pendiente)
        self._pendiente.clear()
        if self.chk_hora.isChecked():
            hora = time.strftime("%H:%M:%S") + f".{int(time.time() * 1000) % 1000:03d} -> "
            partes = texto.split("\n")
            salida = []
            for i, parte in enumerate(partes):
                if i > 0:
                    salida.append("\n")
                    self._inicio_linea = True
                if parte:
                    if self._inicio_linea:
                        salida.append(hora)
                        self._inicio_linea = False
                    salida.append(parte)
            texto = "".join(salida)
        else:
            self._inicio_linea = texto.endswith("\n")
        barra = self.salida.verticalScrollBar()
        c = QTextCursor(self.salida.document())
        c.movePosition(QTextCursor.End)
        c.insertText(texto)
        if self.chk_auto.isChecked():
            barra.setValue(barra.maximum())

    def _enviar(self):
        texto = self.entrada.text()
        if not texto and not self.combo_fin.currentData():
            return
        if texto and (not self._historial or self._historial[-1] != texto):
            self._historial.append(texto)
        self._idx_hist = len(self._historial)
        self.enviar.emit(texto.encode("utf-8") + self.combo_fin.currentData())
        self.entrada.clear()

    def eventFilter(self, obj, ev):
        if obj is self.entrada and ev.type() == ev.KeyPress and self._historial:
            if ev.key() == Qt.Key_Up:
                self._idx_hist = max(0, self._idx_hist - 1)
                self.entrada.setText(self._historial[self._idx_hist])
                return True
            if ev.key() == Qt.Key_Down:
                self._idx_hist = min(len(self._historial), self._idx_hist + 1)
                self.entrada.setText(self._historial[self._idx_hist] if self._idx_hist < len(self._historial) else "")
                return True
        return super().eventFilter(obj, ev)


# ------------------------------------------------------------------ USB

_RX_USB = re.compile(r"^(\d+-\d+)\s+([0-9A-Fa-f]{4}:[0-9A-Fa-f]{4})\s+(.*?)\s{2,}(\S.*?)\s*$")
_ESTADOS = {"Not shared": "Sin compartir", "Shared": "Compartido",
            "Attached": "Conectado a WSL", "Shared (forced)": "Compartido (forzado)"}


class PanelUSB(QWidget):
    """Pasa placas USB de Windows a WSL con usbipd-win."""

    log = pyqtSignal(str, str)      # texto, tipo ("" = automatico)
    cambio = pyqtSignal()           # algo se conecto o desconecto

    def __init__(self, ajustes, parent=None):
        super().__init__(parent)
        self.s = ajustes
        self.procesos: dict[str, object] = {}   # busid -> QProcess de attach --auto-attach
        self.dispositivos: list[tuple[str, str, str, str]] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        barra = QWidget()
        barra.setObjectName("barra_panel")
        barra.setAttribute(Qt.WA_StyledBackground, True)
        b = QHBoxLayout(barra)
        b.setContentsMargins(8, 4, 8, 4)
        b.setSpacing(8)
        self.btn_refrescar = QPushButton("Refrescar")
        self.btn_compartir = QPushButton("Compartir (admin)")
        self.btn_compartir.setToolTip("usbipd bind: solo se hace una vez por placa y pide permisos de administrador")
        self.btn_conectar = QPushButton("Conectar a WSL")
        self.btn_conectar.setToolTip("usbipd attach --wsl --auto-attach (se reconecta solo si la placa se reinicia)")
        self.btn_desconectar = QPushButton("Devolver a Windows")
        self.btn_refrescar.clicked.connect(self.refrescar)
        self.btn_compartir.clicked.connect(self.compartir)
        self.btn_conectar.clicked.connect(self.conectar)
        self.btn_desconectar.clicked.connect(self.desconectar)
        for w in (self.btn_refrescar, self.btn_compartir, self.btn_conectar, self.btn_desconectar):
            b.addWidget(w)
        b.addStretch()
        self.chk_recordar = QCheckBox("Conectar esta placa al abrir")
        self.chk_recordar.setToolTip("Guarda el VID:PID de la placa seleccionada")
        self.chk_recordar.clicked.connect(self._recordar)
        self.chk_devolver = QCheckBox("Devolver a Windows al cerrar")
        self.chk_devolver.setChecked(self.s.value("usb/devolver", True, type=bool))
        self.chk_devolver.toggled.connect(lambda v: self.s.setValue("usb/devolver", v))
        b.addWidget(self.chk_recordar)
        b.addWidget(self.chk_devolver)
        lay.addWidget(barra)

        self.lista = QTreeWidget()
        self.lista.setHeaderLabels(["BUSID", "VID:PID", "Dispositivo", "Estado"])
        self.lista.setRootIsDecorated(False)
        self.lista.setAlternatingRowColors(False)
        h = self.lista.header()
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setStretchLastSection(False)
        self.lista.itemSelectionChanged.connect(self._seleccion)
        self.lista.itemDoubleClicked.connect(lambda *_: self.conectar())
        lay.addWidget(self.lista, 1)
        self._seleccion()

    # ---- utilidades
    def _actual(self):
        it = self.lista.currentItem()
        if not it:
            return None
        return it.data(0, Qt.UserRole)

    def _seleccion(self):
        d = self._actual()
        hay = d is not None
        for w in (self.btn_compartir, self.btn_conectar, self.btn_desconectar, self.chk_recordar):
            w.setEnabled(hay)
        if hay:
            self.chk_recordar.setChecked(self.s.value("usb/hwid", "") == d[1])

    def _recordar(self, on: bool):
        d = self._actual()
        if d:
            self.s.setValue("usb/hwid", d[1] if on else "")

    # ---- acciones
    def refrescar(self, despues=None):
        self.btn_refrescar.setEnabled(False)

        def listo(codigo, texto):
            self.btn_refrescar.setEnabled(True)
            if codigo != 0 and "Connected" not in texto:
                self.log.emit("usbipd no respondio. Instala usbipd-win: winget install usbipd", "error")
                return
            self._parsear(texto)
            if despues:
                despues()

        correr_rapido("usbipd", ["list"], listo)

    def _parsear(self, texto: str):
        seleccionado = self._actual()
        self.dispositivos = []
        en_conectados = False
        for linea in texto.splitlines():
            if linea.strip().startswith("Connected"):
                en_conectados = True
                continue
            if linea.strip().startswith("Persisted"):
                break
            m = _RX_USB.match(linea.strip()) if en_conectados else None
            if m:
                self.dispositivos.append(m.groups())
        self.lista.clear()
        for busid, hwid, nombre, estado in self.dispositivos:
            it = QTreeWidgetItem([busid, hwid, nombre, _ESTADOS.get(estado, estado)])
            it.setData(0, Qt.UserRole, (busid, hwid, nombre, estado))
            self.lista.addTopLevelItem(it)
            if seleccionado and seleccionado[1] == hwid:
                self.lista.setCurrentItem(it)
        for i in range(4):
            if i != 2:
                self.lista.resizeColumnToContents(i)

    def compartir(self):
        d = self._actual()
        if not d:
            return
        self.log.emit(f"usbipd bind --busid {d[0]}  (acepta el aviso de administrador)", "info")
        cmd = ("Start-Process usbipd -Verb RunAs -Wait -WindowStyle Hidden "
               f"-ArgumentList 'bind','--busid','{d[0]}'")
        correr_rapido("powershell", ["-NoProfile", "-Command", cmd],
                      lambda c, t: (self.log.emit(t.strip(), "error") if t.strip() else None, self.refrescar()))

    def conectar(self, d=None):
        d = d or self._actual()
        if not d:
            return
        busid, hwid, nombre, estado = d
        if estado == "Not shared":
            r = QMessageBox.question(self, "USB", f"'{nombre}' aun no esta compartido.\n"
                                     "¿Compartirlo ahora? (pide permisos de administrador una sola vez)")
            if r == QMessageBox.Yes:
                self.compartir()
            return
        if busid in self.procesos:
            self.log.emit(f"{busid} ya se esta conectando a WSL", "aviso")
            return
        from PyQt5.QtCore import QProcess
        p = QProcess(self)
        p.setProcessChannelMode(QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(
            lambda: [self.log.emit("[usbipd] " + l, "") for l in
                     decodificar(bytes(p.readAllStandardOutput())).splitlines() if l.strip()])
        p.finished.connect(lambda *_: self._fin_attach(busid))
        self.procesos[busid] = p
        self.log.emit(f"usbipd attach --wsl --busid {busid} --auto-attach", "info")
        p.start("usbipd", ["attach", "--wsl", "--busid", busid, "--auto-attach"])
        QTimer.singleShot(2500, lambda: self.refrescar(self.cambio.emit))

    def _fin_attach(self, busid):
        p = self.procesos.pop(busid, None)
        if p:
            p.deleteLater()
        self.refrescar(self.cambio.emit)

    def desconectar(self):
        d = self._actual()
        if not d:
            return
        busid = d[0]
        p = self.procesos.pop(busid, None)
        if p:
            p.kill()
        correr_rapido("usbipd", ["detach", "--busid", busid],
                      lambda c, t: (self.log.emit(t.strip(), "error") if c != 0 and t.strip() else None,
                                    self.refrescar(self.cambio.emit)))

    def auto_conectar(self):
        hwid = self.s.value("usb/hwid", "")
        if not hwid:
            return

        def tras_lista():
            for d in self.dispositivos:
                if d[1].lower() == hwid.lower() and d[3] != "Attached":
                    self.conectar(d)
                    return

        self.refrescar(tras_lista)

    def cerrar(self):
        for p in self.procesos.values():
            p.kill()
        busids = list(self.procesos.keys())
        self.procesos.clear()
        if self.chk_devolver.isChecked():
            for busid in busids:
                correr_sincrono(["usbipd", "detach", "--busid", busid], timeout=4)


# ------------------------------------------------------------------ descanso

_EXT_IMG = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class PanelDescanso(QWidget):
    """Pestana de descanso: una imagen o GIF de imgs/descanso. Clic = siguiente."""

    def __init__(self, carpeta, ajustes, parent=None):
        super().__init__(parent)
        from PyQt5.QtWidgets import QSizePolicy
        self.carpeta = carpeta
        self.s = ajustes
        self.imagenes = []
        self.idx = self.s.value("descanso/idx", 0, type=int)
        self._pixmap = None
        self._movie = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.lbl.setObjectName("tenue")
        self.lbl.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.lbl)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _listar(self):
        try:
            self.carpeta.mkdir(parents=True, exist_ok=True)
            self.imagenes = sorted(p for p in self.carpeta.iterdir() if p.suffix.lower() in _EXT_IMG)
        except OSError:
            self.imagenes = []

    def _parar(self):
        if self._movie:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        self._pixmap = None
        self.lbl.clear()

    def _cargar(self):
        from PyQt5.QtGui import QMovie, QPixmap
        self._parar()
        self._listar()
        if not self.imagenes:
            self.lbl.setText(f"Pon imagenes o GIFs en:\n{self.carpeta}\n\n(clic derecho para abrir la carpeta)")
            return
        self.idx %= len(self.imagenes)
        ruta = self.imagenes[self.idx]
        if ruta.suffix.lower() == ".gif":
            self._movie = QMovie(str(ruta))
            self._movie.setCacheMode(QMovie.CacheAll)
            self._movie.jumpToFrame(0)
            self._tam_original = self._movie.currentImage().size()
            self.lbl.setMovie(self._movie)
            self._escalar()
            self._movie.start()
        else:
            self._pixmap = QPixmap(str(ruta))
            self._escalar()

    def _escalar(self):
        area = self.lbl.size()
        if self._pixmap and not self._pixmap.isNull():
            self.lbl.setPixmap(self._pixmap.scaled(area, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif self._movie and self._tam_original.isValid():
            self._movie.setScaledSize(self._tam_original.scaled(area, Qt.KeepAspectRatio))

    def siguiente(self, paso=1):
        self.idx += paso
        self.s.setValue("descanso/idx", self.idx)
        self._cargar()

    def _menu(self, pos):
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Siguiente", lambda: self.siguiente(1))
        m.addAction("Anterior", lambda: self.siguiente(-1))
        m.addSeparator()
        m.addAction("Abrir carpeta", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.carpeta))))
        m.exec_(self.mapToGlobal(pos))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.siguiente(1)
        super().mousePressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._escalar()

    def showEvent(self, e):
        super().showEvent(e)
        self._cargar()          # solo consume algo mientras se ve

    def hideEvent(self, e):
        super().hideEvent(e)
        self._parar()
