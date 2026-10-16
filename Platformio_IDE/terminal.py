"""Terminal liviana por lineas: PowerShell, bash de WSL o bash de Linux.

Mantiene un shell vivo leyendo comandos por stdin. Despues de cada comando se
envia un marcador que imprime la carpeta actual; asi se sabe cuando termino y
se actualiza el prompt. No emula una terminal completa (sin colores ANSI ni
programas a pantalla completa como nano o htop).
"""
from __future__ import annotations

import codecs
import re
import shutil

from PyQt5.QtCore import QProcess, Qt, QTimer
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QWidget)

from ejecutor import ES_WINDOWS, ConfigEjecucion, _entorno, lanzar_silencioso
from paneles import PanelSalida

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
_MARCA = "__JJP_CWD__"
_MARCA_PID = "__JJP_PID__"


def shells_disponibles() -> list[tuple[str, str]]:
    if ES_WINDOWS:
        lista = [("PowerShell", "powershell")]
        if shutil.which("pwsh"):
            lista.append(("PowerShell 7", "pwsh"))
        lista.append(("WSL (bash)", "wsl"))
        return lista
    return [("bash", "bash")]


class Terminal(QWidget):
    """Una pestana de terminal. `fijo` obliga un shell (p. ej. 'powershell' para usbipd)."""

    def __init__(self, cfg: ConfigEjecucion, fijo: str | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.fijo = fijo
        self.p: QProcess | None = None
        self.tipo = fijo or shells_disponibles()[0][1]
        self.cwd: str | None = None          # carpeta con la que arranca
        self.cwd_shell = ""                  # carpeta que reporta el shell
        self.pid_shell = ""
        self.ocupado = False
        self._buf_out = ""
        self._buf_err = ""
        self._dec_out = None
        self._dec_err = None
        self._historial: list[str] = []
        self._idx = 0
        self._reiniciando = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.salida = PanelSalida()
        self.salida.setMaximumBlockCount(4000)
        lay.addWidget(self.salida, 1)

        fila = QWidget()
        fila.setObjectName("barra_panel")
        fila.setAttribute(Qt.WA_StyledBackground, True)
        f = QHBoxLayout(fila)
        f.setContentsMargins(8, 4, 8, 4)
        f.setSpacing(6)
        self.prompt = QLabel("")
        self.prompt.setObjectName("prompt")
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Comando (Enter para ejecutar, flechas para historial)")
        self.entrada.returnPressed.connect(self._enviar)
        self.entrada.installEventFilter(self)
        self.combo = QComboBox()
        for nombre, clave in shells_disponibles():
            self.combo.addItem(nombre, clave)
        self.combo.setCurrentIndex(max(0, self.combo.findData(self.tipo)))
        self.combo.currentIndexChanged.connect(self._cambiar_shell)
        self.combo.setVisible(fijo is None and self.combo.count() > 1)
        self.btn_int = QPushButton("Interrumpir")
        self.btn_int.setToolTip("Ctrl+C al comando en curso (en PowerShell reinicia el shell)")
        self.btn_int.clicked.connect(self.interrumpir)
        limpiar = QPushButton("Limpiar")
        limpiar.clicked.connect(self.salida.clear)
        f.addWidget(self.prompt)
        f.addWidget(self.entrada, 1)
        f.addWidget(self.btn_int)
        f.addWidget(limpiar)
        f.addWidget(self.combo)
        lay.addWidget(fila)

        self._timer_parcial = QTimer(self)
        self._timer_parcial.setSingleShot(True)
        self._timer_parcial.setInterval(150)
        self._timer_parcial.timeout.connect(self._volcar_parcial)
        self._actualizar_prompt()

    # ------------------------------------------------------------ ciclo de vida
    def activo(self) -> bool:
        return self.p is not None and self.p.state() != QProcess.NotRunning

    def asegurar(self):
        """Arranca el shell la primera vez que se usa."""
        if not self.activo():
            self.iniciar()

    def iniciar(self):
        programa, args, wd, init = self._comando()
        p = QProcess(self)
        p.setProcessEnvironment(_entorno())
        if wd:
            p.setWorkingDirectory(wd)
        p.setProcessChannelMode(QProcess.SeparateChannels)
        p.readyReadStandardOutput.connect(self._leer_out)
        p.readyReadStandardError.connect(self._leer_err)
        p.finished.connect(self._fin)
        p.errorOccurred.connect(self._error)
        self.p = p
        self._buf_out = self._buf_err = ""
        self._dec_out = codecs.getincrementaldecoder("utf-8")("replace")
        self._dec_err = codecs.getincrementaldecoder("utf-8")("replace")
        self.pid_shell = ""
        p.start(programa, args)
        for linea in init:
            p.write((linea + "\n").encode("utf-8"))
        self.ocupado = True
        self._marcar()

    def cerrar(self):
        if self.activo():
            self._reiniciando = True
            self.p.closeWriteChannel()
            if not self.p.waitForFinished(800):
                self.p.kill()
                self.p.waitForFinished(500)

    def _comando(self):
        t = self.tipo
        if t in ("powershell", "pwsh"):
            init = ["[Console]::OutputEncoding=[System.Text.Encoding]::UTF8",
                    "$OutputEncoding=[System.Text.Encoding]::UTF8",
                    "$ProgressPreference='SilentlyContinue'"]
            exe = "powershell.exe" if t == "powershell" else "pwsh"
            return exe, ["-NoLogo", "-NoProfile", "-Command", "-"], self.cwd, init
        init = ["export TERM=dumb PYTHONUNBUFFERED=1", f"printf '{_MARCA_PID}%s\\n' $$"]
        if t == "wsl":
            args = (["-d", self.cfg.distro] if self.cfg.distro else [])
            if self.cwd:
                args += ["--cd", self.cwd]
            return "wsl.exe", args + ["--exec", "bash", "-l"], None, init
        return "bash", ["-l"], self.cwd, init

    def _es_ps(self) -> bool:
        return self.tipo in ("powershell", "pwsh")

    def _marcar(self):
        if not self.activo():
            return
        if self._es_ps():
            orden = f'Write-Output ("{_MARCA}" + (Get-Location).Path)'
        else:
            orden = f"printf '\\n{_MARCA}%s\\n' \"$PWD\""
        self.p.write((orden + "\n").encode("utf-8"))

    def ir_a(self, carpeta: str):
        """Cambia de carpeta (al abrir otro proyecto)."""
        self.cwd = carpeta
        if not self.activo() or self.ocupado:
            return
        if self._es_ps():
            orden = "Set-Location -LiteralPath '" + carpeta.replace("'", "''") + "'"
        elif self.tipo == "wsl":
            orden = "cd \"$(wslpath '" + carpeta.replace("'", "'\\''") + "')\""
        else:
            orden = "cd '" + carpeta.replace("'", "'\\''") + "'"
        self.ejecutar(orden, eco=False)

    def _cambiar_shell(self, _i):
        self.tipo = self.combo.currentData()
        if self.activo():
            self.cerrar()
            self.salida.agregar(f"--- {self.combo.currentText()} ---", "info")
            self.iniciar()
        self._actualizar_prompt()

    # ------------------------------------------------------------ comandos
    def ejecutar(self, orden: str, eco: bool = True):
        self.asegurar()
        if eco:
            self.salida.agregar(f"{self._texto_prompt()} {orden}", "info")
        self.p.write((orden + "\n").encode("utf-8"))
        if not self.ocupado:
            self.ocupado = True
            self._marcar()
        self._actualizar_prompt()

    def _enviar(self):
        orden = self.entrada.text()
        self.entrada.clear()
        if orden.strip() and (not self._historial or self._historial[-1] != orden):
            self._historial.append(orden)
        self._idx = len(self._historial)
        if orden.strip().lower() in ("cls", "clear") and not self.ocupado:
            self.salida.clear()
            return
        if self.ocupado and self.activo():
            # hay algo corriendo: la linea va como entrada a ese programa
            self.salida.agregar(orden, "normal")
            self.p.write((orden + "\n").encode("utf-8"))
            return
        self.ejecutar(orden)

    def interrumpir(self):
        if not self.activo():
            return
        if self.pid_shell and not self._es_ps():
            if self.tipo == "wsl":
                args = ["wsl.exe"] + (["-d", self.cfg.distro] if self.cfg.distro else [])
                lanzar_silencioso(args + ["--exec", "pkill", "-INT", "-P", self.pid_shell])
            else:
                lanzar_silencioso(["pkill", "-INT", "-P", self.pid_shell])
            self.salida.agregar("^C", "aviso")
            return
        self.salida.agregar("^C  (reiniciando el shell)", "aviso")
        cwd = self.cwd_shell or self.cwd
        self.cerrar()
        self.cwd = cwd
        self.iniciar()

    # ------------------------------------------------------------ salida
    def _procesar(self, texto: str, error: bool):
        tipo = "error" if error else None
        for linea in texto.split("\n"):
            if linea.startswith(_MARCA):
                self.cwd_shell = linea[len(_MARCA):].strip()
                self.ocupado = False
                self._actualizar_prompt()
                continue
            if linea.startswith(_MARCA_PID):
                self.pid_shell = linea[len(_MARCA_PID):].strip()
                continue
            if linea.strip():
                self.salida.agregar(linea, tipo)

    def _leer(self, crudo: bytes, error: bool):
        dec = self._dec_err if error else self._dec_out
        texto = _ANSI.sub("", dec.decode(crudo)).replace("\r\n", "\n").replace("\r", "\n")
        buf = (self._buf_err if error else self._buf_out) + texto
        *completas, resto = buf.split("\n")
        if completas:
            self._procesar("\n".join(completas), error)
        if error:
            self._buf_err = resto
        else:
            self._buf_out = resto
        if resto:
            self._timer_parcial.start()

    def _leer_out(self):
        if self.p:
            self._leer(bytes(self.p.readAllStandardOutput()), False)

    def _leer_err(self):
        if self.p:
            self._leer(bytes(self.p.readAllStandardError()), True)

    def _volcar_parcial(self):
        # texto sin salto de linea (p. ej. "Password:") que se quedo esperando
        for error in (False, True):
            resto = self._buf_err if error else self._buf_out
            if resto and not resto.startswith(_MARCA[:4]):
                self._procesar(resto, error)
                if error:
                    self._buf_err = ""
                else:
                    self._buf_out = ""

    def _fin(self, codigo, _estado):
        self._leer_out()
        self._leer_err()
        p, self.p = self.p, None
        if p:
            p.deleteLater()
        self.ocupado = False
        if self._reiniciando:
            self._reiniciando = False
        else:
            self.salida.agregar(f"(el shell termino con codigo {codigo}; escribe algo para reiniciarlo)", "aviso")
        self._actualizar_prompt()

    def _error(self, error):
        if error == QProcess.FailedToStart and self.p:
            programa = self.p.program()
            p, self.p = self.p, None
            p.deleteLater()
            self.ocupado = False
            self.salida.agregar(f"No se pudo iniciar {programa}", "error")
            self._actualizar_prompt()

    # ------------------------------------------------------------ prompt
    def _texto_prompt(self) -> str:
        carpeta = self.cwd_shell or self.cwd or "~"
        if self._es_ps():
            return f"PS {carpeta}>"
        return f"{carpeta}$"

    def _actualizar_prompt(self):
        texto = self._texto_prompt()
        if len(texto) > 48:
            texto = "…" + texto[-47:]
        self.prompt.setText(texto + ("  ⏳" if self.ocupado and self.activo() else ""))
        self.btn_int.setEnabled(self.activo())

    def set_tema(self, t: dict):
        self.salida.set_tema(t)
        self.prompt.setStyleSheet(f"color:{t['acento']}; font-weight:bold;")

    def eventFilter(self, obj, ev):
        if obj is self.entrada and ev.type() == ev.KeyPress and self._historial:
            if ev.key() == Qt.Key_Up:
                self._idx = max(0, self._idx - 1)
                self.entrada.setText(self._historial[self._idx])
                return True
            if ev.key() == Qt.Key_Down:
                self._idx = min(len(self._historial), self._idx + 1)
                self.entrada.setText(self._historial[self._idx] if self._idx < len(self._historial) else "")
                return True
        return super().eventFilter(obj, ev)

    def showEvent(self, e):
        super().showEvent(e)
        self.asegurar()
        self.entrada.setFocus()

