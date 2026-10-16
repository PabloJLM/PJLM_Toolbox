"""Dialogos: ajustes y nuevo proyecto de PlatformIO."""
from __future__ import annotations

import re
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                             QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QSlider, QSpinBox, QVBoxLayout)

from ejecutor import ES_WINDOWS, correr_sincrono

PIOARDUINO = "https://github.com/pioarduino/platform-espressif32/releases/download/stable/platform-espressif32.zip"

PLACAS = [
    ("esp32-s3-devkitc-1", "espressif32"),
    ("esp32dev", "espressif32"),
    ("esp32-c3-devkitm-1", "espressif32"),
    ("esp32-c6-devkitc-1", "espressif32"),
    ("nucleo_f303k8", "ststm32"),
    ("nucleo_f401re", "ststm32"),
    ("bluepill_f103c8", "ststm32"),
    ("uno", "atmelavr"),
    ("nanoatmega328", "atmelavr"),
    ("pico", "raspberrypi"),
]
FRAMEWORKS = ["arduino", "espidf", "stm32cube", "libopencm3", "zephyr"]

_PLANTILLAS = {
    "arduino": '#include <Arduino.h>\n\nvoid setup() {\n  Serial.begin({baud});\n}\n\nvoid loop() {\n}\n',
    "espidf": '#include <stdio.h>\n#include "freertos/FreeRTOS.h"\n#include "freertos/task.h"\n\n'
              'extern "C" void app_main(void) {\n  while (true) {\n    vTaskDelay(pdMS_TO_TICKS(1000));\n  }\n}\n',
}
_PLANTILLA_C = 'int main(void) {\n  while (1) {\n  }\n}\n'


class DialogoAjustes(QDialog):
    def __init__(self, valores: dict, temas: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)

        ap = QGroupBox("Apariencia")
        f = QFormLayout(ap)
        self.tema = QComboBox()
        self.tema.addItems(temas)
        self.tema.setCurrentText(valores["tema"])
        f.addRow("Tema:", self.tema)
        self.fuente = QComboBox()
        db = QFontDatabase()
        fijas = [fam for fam in db.families() if db.isFixedPitch(fam)]
        self.fuente.addItems(fijas or [valores["fuente"]])
        self.fuente.setCurrentText(valores["fuente"])
        f.addRow("Fuente:", self.fuente)
        self.tam = QSpinBox()
        self.tam.setRange(7, 32)
        self.tam.setValue(valores["tam"])
        f.addRow("Tamano:", self.tam)
        self.sangria = QSpinBox()
        self.sangria.setRange(1, 8)
        self.sangria.setValue(valores["sangria"])
        f.addRow("Espacios por Tab:", self.sangria)
        self.fondo = QCheckBox("Imagen de fondo en el editor (si el tema tiene una)")
        self.fondo.setChecked(valores["fondo"])
        f.addRow(self.fondo)
        fila = QHBoxLayout()
        self.opacidad = QSlider(Qt.Horizontal)
        self.opacidad.setRange(3, 40)
        self.opacidad.setValue(valores["opacidad"])
        lbl = QLabel(f"{valores['opacidad']}%")
        self.opacidad.valueChanged.connect(lambda v: lbl.setText(f"{v}%"))
        fila.addWidget(self.opacidad)
        fila.addWidget(lbl)
        f.addRow("Opacidad del fondo:", fila)
        lay.addWidget(ap)

        gen = QGroupBox("Compilacion")
        g = QFormLayout(gen)
        self.guardar_antes = QCheckBox("Guardar todo antes de compilar o subir")
        self.guardar_antes.setChecked(valores["guardar_antes"])
        self.verbose = QCheckBox("Salida detallada (-v)")
        self.verbose.setChecked(valores["verbose"])
        g.addRow(self.guardar_antes)
        g.addRow(self.verbose)
        lay.addWidget(gen)

        self.modo = QComboBox()
        self.distro = QComboBox()
        if ES_WINDOWS:
            ej = QGroupBox("Ejecucion de PlatformIO")
            e = QFormLayout(ej)
            self.modo.addItem("WSL (recomendado)", "wsl")
            self.modo.addItem("Windows (pio instalado en Windows)", "local")
            self.modo.setCurrentIndex(0 if valores["modo"] == "wsl" else 1)
            e.addRow("Ejecutar en:", self.modo)
            self.distro.setEditable(True)
            self.distro.addItem("")
            self.distro.setCurrentText(valores["distro"])
            self.distro.lineEdit().setPlaceholderText("(predeterminada)")
            detectar = QPushButton("Detectar")
            detectar.clicked.connect(self._detectar)
            fila_d = QHBoxLayout()
            fila_d.addWidget(self.distro, 1)
            fila_d.addWidget(detectar)
            e.addRow("Distribucion:", fila_d)
            lay.addWidget(ej)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)
        self._valores = valores

    def _detectar(self):
        codigo, texto = correr_sincrono(["wsl.exe", "-l", "-q"])
        nombres = [l.strip().strip("\x00") for l in texto.splitlines() if l.strip().strip("\x00")]
        if codigo != 0 or not nombres:
            QMessageBox.warning(self, "WSL", "No se encontraron distribuciones de WSL.")
            return
        actual = self.distro.currentText()
        self.distro.clear()
        self.distro.addItems([""] + nombres)
        self.distro.setCurrentText(actual if actual in nombres else nombres[0])

    def valores(self) -> dict:
        v = dict(self._valores)
        v.update(tema=self.tema.currentText(), fuente=self.fuente.currentText(),
                 tam=self.tam.value(), sangria=self.sangria.value(),
                 fondo=self.fondo.isChecked(), opacidad=self.opacidad.value(),
                 guardar_antes=self.guardar_antes.isChecked(), verbose=self.verbose.isChecked())
        if ES_WINDOWS:
            v.update(modo=self.modo.currentData(), distro=self.distro.currentText().strip())
        return v


class DialogoNuevoProyecto(QDialog):
    """Crea la estructura de un proyecto PlatformIO sin descargar nada."""

    def __init__(self, carpeta_inicial: str, usa_wsl: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nuevo proyecto")
        self.setMinimumWidth(520)
        self.ruta_creada: str | None = None
        self._usa_wsl = usa_wsl
        lay = QVBoxLayout(self)
        f = QFormLayout()

        self.nombre = QLineEdit()
        self.nombre.setPlaceholderText("mi_proyecto")
        f.addRow("Nombre:", self.nombre)
        fila = QHBoxLayout()
        self.carpeta = QLineEdit(carpeta_inicial)
        examinar = QPushButton("...")
        examinar.setFixedWidth(32)
        examinar.clicked.connect(self._examinar)
        fila.addWidget(self.carpeta, 1)
        fila.addWidget(examinar)
        f.addRow("Crear en:", fila)

        self.placa = QComboBox()
        self.placa.setEditable(True)
        for placa, _ in PLACAS:
            self.placa.addItem(placa)
        self.placa.currentTextChanged.connect(self._placa_cambiada)
        f.addRow("Placa (board):", self.placa)
        self.plataforma = QLineEdit()
        f.addRow("Plataforma:", self.plataforma)
        self.framework = QComboBox()
        self.framework.setEditable(True)
        self.framework.addItems(FRAMEWORKS)
        self.framework.currentTextChanged.connect(lambda _: self._placa_cambiada(self.placa.currentText()))
        f.addRow("Framework:", self.framework)
        self.baud = QSpinBox()
        self.baud.setRange(300, 4000000)
        self.baud.setValue(115200)
        f.addRow("monitor_speed:", self.baud)
        lay.addLayout(f)

        self.pioarduino = QCheckBox("Arduino-ESP32 3.x (plataforma pioarduino)")
        self.usb_cdc = QCheckBox("Serial por USB nativo (ESP32-S3/C3/C6: ARDUINO_USB_CDC_ON_BOOT=1)")
        self.workspace = QCheckBox("Compilar en el disco de Linux (workspace_dir en ~/.pio_workspaces)")
        self.workspace.setChecked(usa_wsl)
        self.workspace.setVisible(usa_wsl)
        for w in (self.pioarduino, self.usb_cdc, self.workspace):
            lay.addWidget(w)

        nota = QLabel("Solo se crean platformio.ini, src/, include/, lib/ y test/. "
                      "La plataforma se descarga en la primera compilacion.")
        nota.setObjectName("tenue")
        nota.setWordWrap(True)
        lay.addWidget(nota)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Crear")
        botones.accepted.connect(self._crear)
        botones.rejected.connect(self.reject)
        lay.addWidget(botones)
        self._placa_cambiada(self.placa.currentText())

    def _examinar(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta donde crear el proyecto", self.carpeta.text())
        if d:
            self.carpeta.setText(d)

    def _placa_cambiada(self, placa: str):
        plataforma = dict(PLACAS).get(placa)
        if plataforma:
            self.plataforma.setText(plataforma)
        es_esp = self.plataforma.text() == "espressif32" or placa.startswith("esp32")
        es_arduino = self.framework.currentText() == "arduino"
        self.pioarduino.setEnabled(es_esp and es_arduino)
        self.usb_cdc.setEnabled(es_esp and es_arduino)
        if not (es_esp and es_arduino):
            self.pioarduino.setChecked(False)
            self.usb_cdc.setChecked(False)

    def _crear(self):
        nombre = self.nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Nuevo proyecto", "Escribe un nombre.")
            return
        if not self.carpeta.text().strip():
            QMessageBox.warning(self, "Nuevo proyecto", "Elige la carpeta donde crearlo.")
            return
        raiz = Path(self.carpeta.text().strip()) / nombre
        ini = raiz / "platformio.ini"
        if ini.exists():
            QMessageBox.warning(self, "Nuevo proyecto", f"Ya existe {ini}")
            return
        env = re.sub(r"[^a-z0-9_]+", "_", nombre.lower()).strip("_") or "main"
        placa = self.placa.currentText().strip()
        framework = self.framework.currentText().strip()
        plataforma = PIOARDUINO if self.pioarduino.isChecked() else (self.plataforma.text().strip() or "espressif32")

        lineas = []
        if self._usa_wsl and self.workspace.isChecked():
            lineas += ["[platformio]",
                       "; fuentes en Windows, compilacion y librerias en el disco de Linux",
                       f"workspace_dir = ${{sysenv.HOME}}/.pio_workspaces/{env}", ""]
        lineas += [f"[env:{env}]", f"platform = {plataforma}", f"board = {placa}",
                   f"framework = {framework}", f"monitor_speed = {self.baud.value()}"]
        if self.usb_cdc.isChecked():
            lineas += ["build_flags =", "    -DARDUINO_USB_CDC_ON_BOOT=1"]
        try:
            for sub in ("src", "include", "lib", "test"):
                (raiz / sub).mkdir(parents=True, exist_ok=True)
            ini.write_text("\n".join(lineas) + "\n", encoding="utf-8")
            if not any((raiz / "src").iterdir()):
                if framework in _PLANTILLAS:
                    principal = raiz / "src" / "main.cpp"
                    principal.write_text(_PLANTILLAS[framework].replace("{baud}", str(self.baud.value())),
                                         encoding="utf-8")
                else:
                    (raiz / "src" / "main.c").write_text(_PLANTILLA_C, encoding="utf-8")
            gi = raiz / ".gitignore"
            if not gi.exists():
                gi.write_text(".pio/\n.vscode/\n", encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "Nuevo proyecto", f"No se pudo crear el proyecto:\n{e}")
            return
        self.ruta_creada = str(raiz)
        self.accept()
