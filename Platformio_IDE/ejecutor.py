"""Ejecucion de comandos de PlatformIO en WSL (desde Windows), en Linux nativo
o directamente en Windows.

Modo WSL:     wsl.exe [-d distro] --cd <carpeta> --exec bash -lc "<script>"
Modo Linux:   bash -lc "<script>"   (con la carpeta como directorio de trabajo)
Modo Windows: pio.exe ...           (PlatformIO instalado en Windows)

En los modos con bash cada tarea se lanza en su propia sesion (setsid) y
guarda su PID en /tmp, para poder detenerla con Ctrl+C a todo el grupo
(pio, scons, compilador, esptool...).
"""
from __future__ import annotations

import codecs
import locale
import os
import re
import shlex
import subprocess
import sys
import time

from PyQt5.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

ES_WINDOWS = sys.platform.startswith("win")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_SIN_VENTANA = 0x08000000  # CREATE_NO_WINDOW


class ConfigEjecucion:
    def __init__(self, modo: str = "wsl", distro: str = ""):
        self.modo = modo
        self.distro = distro

    @property
    def usa_wsl(self) -> bool:
        return ES_WINDOWS and self.modo == "wsl"

    @property
    def usa_bash(self) -> bool:
        return (not ES_WINDOWS) or self.modo == "wsl"

    def descripcion(self) -> str:
        if self.usa_wsl:
            return f"WSL: {self.distro or 'predeterminada'}"
        return "Windows" if ES_WINDOWS else "Linux"


def _entorno() -> QProcessEnvironment:
    env = QProcessEnvironment.systemEnvironment()
    env.insert("WSL_UTF8", "1")            # wsl.exe escribe sus mensajes en UTF-8
    env.insert("PYTHONUNBUFFERED", "1")
    env.insert("PLATFORMIO_DISABLE_PROGRESSBAR", "true")
    return env


def _archivo_pid(etiqueta: str) -> str:
    return f'/tmp/jojop_pio_${{USER}}_{etiqueta}.pid'


def preparar_script(cfg: ConfigEjecucion, script: str, cwd: str | None,
                    etiqueta: str | None = None):
    """Devuelve (programa, argumentos, cwd_para_QProcess) para un script de bash."""
    pre = "export PYTHONUNBUFFERED=1 PLATFORMIO_DISABLE_PROGRESSBAR=true; "
    if etiqueta:
        interno = f'echo $$ > "{_archivo_pid(etiqueta)}"; {script}'
        script = f"exec setsid -w bash -c {shlex.quote(interno)}"
    script = pre + script
    if cfg.usa_wsl:
        args = []
        if cfg.distro:
            args += ["-d", cfg.distro]
        if cwd:
            args += ["--cd", cwd]
        return "wsl.exe", args + ["--exec", "bash", "-lc", script], None
    return "bash", ["-lc", script], cwd


def preparar(cfg: ConfigEjecucion, args: list[str], cwd: str | None,
             etiqueta: str | None = None):
    """Igual que preparar_script pero a partir de una lista de argumentos."""
    if not cfg.usa_bash:
        return args[0], args[1:], cwd
    return preparar_script(cfg, "exec " + " ".join(shlex.quote(a) for a in args), cwd, etiqueta)


def decodificar(datos: bytes) -> str:
    if not datos:
        return ""
    if datos.count(b"\x00") > len(datos) // 4:
        try:
            return datos.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return datos.decode(locale.getpreferredencoding(False) or "latin-1", "replace")


def lanzar_silencioso(argumentos: list[str], cwd: str | None = None):
    """Lanza un proceso sin ventana y sin esperarlo (sobrevive al cierre del IDE)."""
    env = os.environ.copy()
    env["WSL_UTF8"] = "1"
    extra = {"creationflags": _SIN_VENTANA} if ES_WINDOWS else {"start_new_session": True}
    try:
        subprocess.Popen(argumentos, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
    except OSError:
        pass


def correr_sincrono(argumentos: list[str], timeout: float = 5.0) -> tuple[int, str]:
    env = os.environ.copy()
    env["WSL_UTF8"] = "1"
    extra = {"creationflags": _SIN_VENTANA} if ES_WINDOWS else {}
    try:
        r = subprocess.run(argumentos, env=env, capture_output=True, timeout=timeout, **extra)
        return r.returncode, decodificar(r.stdout + r.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)


_VIVOS: set = set()


def correr_rapido(programa: str, args: list[str], callback, cwd: str | None = None):
    """Ejecuta un comando corto sin bloquear la interfaz; callback(codigo, texto)."""
    p = QProcess()
    p.setProcessEnvironment(_entorno())
    p.setProcessChannelMode(QProcess.MergedChannels)
    if cwd:
        p.setWorkingDirectory(cwd)
    _VIVOS.add(p)
    hecho = {"ok": False}

    def fin(codigo=-1, _estado=None):
        if hecho["ok"]:
            return
        hecho["ok"] = True
        texto = decodificar(bytes(p.readAll()))
        _VIVOS.discard(p)
        p.deleteLater()
        callback(codigo, texto)

    p.finished.connect(fin)
    p.errorOccurred.connect(lambda e: fin(-1) if e == QProcess.FailedToStart else None)
    p.start(programa, args)


def correr_pio_rapido(cfg: ConfigEjecucion, args: list[str], cwd: str | None, callback):
    programa, a, wd = preparar(cfg, args, cwd)
    correr_rapido(programa, a, callback, wd)


class Proceso(QObject):
    """Proceso largo con salida en vivo (compilar, subir, monitor serie)."""

    linea = pyqtSignal(str)        # modo texto: cada linea de salida
    datos = pyqtSignal(bytes)      # modo crudo: bytes de stdout
    aviso = pyqtSignal(str)        # modo crudo: lineas de stderr
    terminado = pyqtSignal(int, float)

    def __init__(self, cfg: ConfigEjecucion, etiqueta: str, crudo: bool = False, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.etiqueta = etiqueta
        self.crudo = crudo
        self.p: QProcess | None = None
        self.fue_detenido = False
        self._t0 = 0.0
        self._buf = ""
        self._buf_err = ""
        self._dec = None
        self._dec_err = None

    def activo(self) -> bool:
        return self.p is not None and self.p.state() != QProcess.NotRunning

    def iniciar(self, args: list[str] | None = None, cwd: str | None = None,
                script: str | None = None) -> bool:
        if self.activo():
            return False
        if script is not None:
            programa, a, wd = preparar_script(self.cfg, script, cwd, self.etiqueta)
        else:
            programa, a, wd = preparar(self.cfg, args, cwd, self.etiqueta)
        p = QProcess(self)
        p.setProcessEnvironment(_entorno())
        if wd:
            p.setWorkingDirectory(wd)
        p.setProcessChannelMode(QProcess.SeparateChannels if self.crudo else QProcess.MergedChannels)
        p.readyReadStandardOutput.connect(self._leer_out)
        p.readyReadStandardError.connect(self._leer_err)
        p.finished.connect(self._fin)
        p.errorOccurred.connect(self._error)
        self.p = p
        self.fue_detenido = False
        self._buf = self._buf_err = ""
        self._dec = codecs.getincrementaldecoder("utf-8")("replace")
        self._dec_err = codecs.getincrementaldecoder("utf-8")("replace")
        self._t0 = time.monotonic()
        p.start(programa, a)
        return True

    def escribir(self, datos: bytes):
        if self.activo():
            self.p.write(datos)

    def detener(self):
        if not self.activo():
            return
        self.fue_detenido = True
        p = self.p
        p.closeWriteChannel()
        if self.cfg.usa_bash:
            script = f'kill -INT -- -$(cat "{_archivo_pid(self.etiqueta)}") 2>/dev/null'
            programa, a, wd = preparar_script(self.cfg, script, None)
            lanzar_silencioso([programa] + a, wd)
        elif ES_WINDOWS:
            lanzar_silencioso(["taskkill", "/PID", str(p.processId()), "/T", "/F"])
        QTimer.singleShot(2500, lambda: self._forzar(p))

    def _forzar(self, p):
        if self.p is p and self.activo():
            if self.cfg.usa_bash:
                script = f'kill -KILL -- -$(cat "{_archivo_pid(self.etiqueta)}") 2>/dev/null'
                programa, a, wd = preparar_script(self.cfg, script, None)
                lanzar_silencioso([programa] + a, wd)
            p.kill()

    def _partir(self, buf: str, nuevo: str, senal):
        buf += _ANSI.sub("", nuevo).replace("\r\n", "\n").replace("\r", "\n")
        *lineas, resto = buf.split("\n")
        for l in lineas:
            if l.strip():
                senal.emit(l)
        return resto

    def _leer_out(self):
        if not self.p:
            return
        crudo = bytes(self.p.readAllStandardOutput())
        if self.crudo:
            self.datos.emit(crudo)
        else:
            self._buf = self._partir(self._buf, self._dec.decode(crudo), self.linea)

    def _leer_err(self):
        if not self.p:
            return
        crudo = bytes(self.p.readAllStandardError())
        senal = self.aviso if self.crudo else self.linea
        self._buf_err = self._partir(self._buf_err, self._dec_err.decode(crudo), senal)

    def _vaciar(self):
        if self._buf.strip() and not self.crudo:
            self.linea.emit(self._buf)
        if self._buf_err.strip():
            (self.aviso if self.crudo else self.linea).emit(self._buf_err)
        self._buf = self._buf_err = ""

    def _fin(self, codigo, _estado):
        self._leer_out()
        self._leer_err()
        self._vaciar()
        segundos = time.monotonic() - self._t0
        p, self.p = self.p, None
        if p:
            p.deleteLater()
        self.terminado.emit(codigo, segundos)

    def _error(self, error):
        if error == QProcess.FailedToStart and self.p:
            programa = self.p.program()
            p, self.p = self.p, None
            p.deleteLater()
            msj = f"No se pudo iniciar '{programa}'. Revisa que este instalado y en el PATH."
            (self.aviso if self.crudo else self.linea).emit(msj)
            self.terminado.emit(-1, 0.0)
