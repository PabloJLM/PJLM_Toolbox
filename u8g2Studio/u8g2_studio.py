#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
u8g2 Studio
===========
Editor visual de interfaces para displays monocromaticos, local y open source,
para cualquier proyecto que use la libreria u8g2 (o U8x8 / Adafruit_GFX).

Abre la carpeta de tu sketch, encuentra las funciones que dibujan y los
bitmaps, los muestra y te deja editarlos con el mouse. Cada cambio reescribe
el numero exacto dentro de la llamada en el codigo. No hay formato propio ni
proyecto aparte: el codigo ES el modelo. Nada toca el disco hasta Ctrl+S.

No es especifico de ningun proyecto: detecta el objeto de display, el
tamano real de la pantalla (leyendo la clase del constructor, p.ej.
U8G2_SSD1306_128X32_...), y las funciones de dibujo por su cuenta.

    python u8g2_studio.py [carpeta_del_sketch]

Requisitos:  PyQt5    (obligatorio)
             Pillow   (opcional, para importar/exportar imagenes)

MIT License
"""

import os
import sys

from PyQt5.QtCore import Qt, QSettings, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QAction, QMessageBox, QFileDialog,
    QShortcut, QLabel
)

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import ms_core as core            # noqa: E402
import ms_project as mpj          # noqa: E402
from ms_editor import EditorTab   # noqa: E402
from ms_designer import DesignerTab  # noqa: E402


APP_NAME = "u8g2 Studio"
APP_VERSION = "2.1"

DARK_QSS = """
QWidget { background: #12161f; color: #d8e2f0; font-size: 12px; }
QGroupBox {
    border: 1px solid #24344c; border-radius: 4px;
    margin-top: 10px; padding-top: 8px; font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #6fb6d9; }
QPushButton, QToolButton {
    background: #1b2433; border: 1px solid #2c3d55; border-radius: 3px;
    padding: 4px 8px;
}
QPushButton:hover, QToolButton:hover { background: #243247; }
QPushButton:pressed, QToolButton:pressed { background: #2f4a68; }
QPushButton:disabled { color: #55637a; }
QToolButton:checked { background: #2b6fa0; border-color: #4ba6d8; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QListWidget, QTreeWidget {
    background: #0d1119; border: 1px solid #2c3d55; border-radius: 3px; padding: 2px 4px;
}
QSpinBox:disabled, QLineEdit:disabled { color: #55637a; background: #11151d; }
QScrollArea { border: 1px solid #24344c; }
QTabBar::tab {
    background: #1b2433; padding: 6px 16px; border: 1px solid #2c3d55;
    border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px;
}
QTabBar::tab:selected { background: #2b6fa0; }
QMenuBar, QMenu { background: #12161f; }
QMenu::item:selected { background: #2b6fa0; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #2b6fa0; }
"""


class MainWindow(QMainWindow):

    def __init__(self, initial=None):
        QMainWindow.__init__(self)
        self.resize(1440, 900)
        app = QApplication.instance()
        if app is not None and not app.styleSheet():
            app.setStyle("Fusion")
            app.setStyleSheet(DARK_QSS)

        self.settings = QSettings("u8g2Studio", "u8g2Studio")
        self.project = None

        self.tabs = QTabWidget()
        self.editor = EditorTab()
        self.designer = DesignerTab()
        self.tabs.addTab(self.designer, "  Pantallas  ")
        self.tabs.addTab(self.editor, "  Pixel art  ")
        self.tabs.currentChanged.connect(self._tab_changed)
        self.setCentralWidget(self.tabs)

        self.status = self.statusBar()
        self.lb_dirty = QLabel("")
        self.status.addPermanentWidget(self.lb_dirty)
        self.editor.canvas.statusChanged.connect(self.status.showMessage)
        self.designer.canvas.statusChanged.connect(self.status.showMessage)
        self.designer.projectEdited.connect(self.update_title)
        self.editor.bitmapChanged.connect(self.update_title)

        self._build_menu()
        self._build_shortcuts()
        self.update_title()

        # aviso si alguien edita los archivos por fuera (Arduino IDE, git...)
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._check_external)
        self._watch.start(3000)
        self._warned = set()

        target = initial or self.settings.value("last_folder", "")
        if target and os.path.exists(target):
            self.open_path(target, quiet=True)

    # =========================================================
    def open_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, "Carpeta del sketch (donde estan los .ino/.cpp/.h)",
            self.settings.value("last_folder", ""))
        if d:
            self.open_path(d)

    def open_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Abrir archivo", self.settings.value("last_folder", ""),
            "Codigo C/C++ (*.ino *.cpp *.cc *.c *.h *.hpp);;Todos (*)")
        if p:
            self.open_path(p)

    def open_path(self, path, quiet=False):
        if self.project is not None and not self.confirm_discard():
            return
        try:
            proj = mpj.Project(path)
        except Exception as e:
            if not quiet:
                QMessageBox.critical(self, "Abrir", str(e))
            return
        self.project = proj
        self.designer.set_project(proj)
        self.editor.set_project(proj)
        self._warned = set()
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        self.settings.setValue("last_folder", folder)
        self.update_title()
        n_scr = len(proj.screens)
        n_bmp = len(proj.bitmaps)
        self.status.showMessage(
            "%d archivo(s), pantalla %dx%d, %d pantalla(s), %d bitmap(s)"
            % (len(proj.files), proj.screen_w, proj.screen_h, n_scr, n_bmp))
        if not quiet and n_scr == 0 and n_bmp == 0:
            QMessageBox.information(
                self, "Abrir",
                "No encontre llamadas de dibujo (drawStr, drawBox...) ni "
                "arreglos de bytes ahi.\n\n"
                "Apunta a la carpeta que tiene el .ino o los .cpp que usan u8g2.")

    def add_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Agregar archivo al analisis", "",
            "Codigo C/C++ (*.ino *.cpp *.cc *.c *.h *.hpp);;Todos (*)")
        if p and self.project:
            self.project.add_file(p)
            self.designer.set_project(self.project)
            self.editor.set_project(self.project)

    # =========================================================
    def save(self):
        if not self.project:
            return
        # el pixel art vive en un buffer aparte; volcarlo antes de escribir
        if self.editor._dirty:
            self.editor.commit()
            self.editor._dirty = False
        paths = self.project.dirty_files()
        if not paths:
            self.status.showMessage("No hay cambios que guardar")
            return
        try:
            written = self.project.save(paths)
        except Exception as e:
            QMessageBox.critical(self, "Guardar", str(e))
            return
        self.designer.set_project(self.project)
        self.editor.refresh_bitmap_list()
        self.update_title()
        self.status.showMessage("Guardado: " + ", ".join(
            os.path.basename(p) for p in written))

    def revert(self):
        if not self.project:
            return
        if not self.confirm_discard("Descartar todos los cambios y releer del disco?"):
            return
        self.project.reload_from_disk()
        self.designer.set_project(self.project)
        self.editor.set_project(self.project)
        self.update_title()
        self.status.showMessage("Releido del disco")

    def confirm_discard(self, msg=None):
        if not self.project:
            return True
        if self.editor._dirty:
            self.editor.commit()
            self.editor._dirty = False
        dirty = self.project.dirty_files()
        if not dirty:
            return True
        r = QMessageBox.question(
            self, "Cambios sin guardar",
            (msg or "Hay cambios sin guardar en:\n  %s\n\nSeguir y perderlos?")
            % ", ".join(os.path.basename(p) for p in dirty)
            if msg is None else msg,
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if r == QMessageBox.Save:
            self.save()
            return True
        return r == QMessageBox.Discard

    # =========================================================
    def _tab_changed(self, idx):
        if not self.project:
            return
        if idx == 0 and self.editor._dirty:
            # al volver a Pantallas, que el bitmap ya se vea actualizado
            self.editor.commit()
            self.editor._dirty = False
            self.designer._reload_bitmaps()
            self.designer.canvas.update()
        if idx == 1:
            self.editor.refresh_bitmap_list()
        self.update_title()

    def update_title(self):
        name = "sin proyecto"
        mark = ""
        if self.project:
            name = os.path.basename(self.project.root or "") or self.project.root
            dirty = list(self.project.dirty_files())
            if self.editor._dirty:
                dirty.append("bitmap")
            if dirty:
                mark = " *"
                self.lb_dirty.setText("sin guardar: " + ", ".join(
                    os.path.basename(p) for p in dirty))
            else:
                self.lb_dirty.setText("guardado")
        self.setWindowTitle("%s %s  -  %s%s" % (APP_NAME, APP_VERSION, name, mark))

    def _check_external(self):
        if not self.project:
            return
        for p in self.project.externally_changed():
            if p in self._warned:
                continue
            self._warned.add(p)
            r = QMessageBox.question(
                self, "El archivo cambio afuera",
                "%s cambio en el disco (otro editor, git...).\n\n"
                "Releer del disco? Se pierden los cambios que tengas aqui."
                % os.path.basename(p),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r == QMessageBox.Yes:
                self.project.reload_from_disk()
                self.designer.set_project(self.project)
                self.editor.set_project(self.project)
                self._warned = set()
                self.update_title()
            return

    # =========================================================
    def _build_menu(self):
        m = self.menuBar()
        fm = m.addMenu("&Archivo")
        for label, slot, sc in [
            ("Abrir carpeta del sketch...", self.open_folder, "Ctrl+O"),
            ("Abrir un solo archivo...", self.open_file, None),
            ("Agregar archivo al analisis...", self.add_file, None),
            (None, None, None),
            ("Guardar cambios", self.save, "Ctrl+S"),
            ("Descartar y releer del disco", self.revert, None),
            (None, None, None),
            ("Importar imagen al bitmap...", self.editor.import_image, "Ctrl+I"),
            ("Exportar bitmap a PNG...", self.editor.export_png, None),
            (None, None, None),
            ("Salir", self.close, "Ctrl+Q"),
        ]:
            if label is None:
                fm.addSeparator()
                continue
            a = QAction(label, self)
            a.triggered.connect(slot)
            if sc:
                a.setShortcut(QKeySequence(sc))
            fm.addAction(a)

        em = m.addMenu("&Editar")
        for label, slot, sc in [
            ("Deshacer", self._undo, "Ctrl+Z"),
            ("Rehacer", self._redo, "Ctrl+Y"),
            (None, None, None),
            ("Invertir bitmap", self.editor.op_invert, None),
            ("Limpiar bitmap", self.editor.op_clear, None),
            ("Espejo horizontal", self.editor.op_fliph, None),
            ("Espejo vertical", self.editor.op_flipv, None),
            (None, None, None),
            ("Copiar arreglo C del bitmap", self.editor.copy_array, None),
        ]:
            if label is None:
                em.addSeparator()
                continue
            a = QAction(label, self)
            a.triggered.connect(slot)
            if sc:
                a.setShortcut(QKeySequence(sc))
            em.addAction(a)

        hm = m.addMenu("A&yuda")
        a = QAction("Como funciona", self)
        a.triggered.connect(lambda: QMessageBox.information(self, "Como funciona", HELP))
        hm.addAction(a)
        a = QAction("Acerca de", self)
        a.triggered.connect(lambda: QMessageBox.about(self, "Acerca de", ABOUT))
        hm.addAction(a)

    def _build_shortcuts(self):
        for k, tool in {"P": "pencil", "E": "eraser", "L": "line", "R": "rect",
                        "F": "rectfill", "O": "ellipse", "D": "ellipsefill",
                        "B": "bucket", "T": "text", "S": "select",
                        "I": "picker"}.items():
            sc = QShortcut(QKeySequence(k), self)
            sc.activated.connect(lambda t=tool: self._pick_tool(t))

    def _pick_tool(self, tool):
        if self.tabs.currentIndex() == 1:
            self.editor.set_tool(tool)

    def _undo(self):
        if self.tabs.currentIndex() == 1:
            self.editor.canvas.undo()
        elif self.project and self.project.undo():
            self.designer.canvas.refresh()
            self.designer.refresh_tree()
            self.designer._after_edit()
            self.designer.canvas.update()

    def _redo(self):
        if self.tabs.currentIndex() == 1:
            self.editor.canvas.redo()
        elif self.project and self.project.redo():
            self.designer.canvas.refresh()
            self.designer.refresh_tree()
            self.designer._after_edit()
            self.designer.canvas.update()

    def closeEvent(self, ev):
        if self.confirm_discard():
            ev.accept()
        else:
            ev.ignore()


HELP = """\
EL CODIGO ES EL MODELO
  No hay archivo de proyecto. La app lee tus .ino/.cpp/.h, interpreta las
  funciones que dibujan y te las muestra. Cuando mueves algo, reescribe el
  numero exacto dentro de la llamada. Nada se escribe al disco hasta Ctrl+S;
  el titulo muestra un asterisco mientras haya cambios pendientes.

FUNCIONA CON CUALQUIER SKETCH DE u8g2
  No hay nada especifico de un proyecto. Al abrir una carpeta, la app:
    - detecta el nombre de tu objeto de display (u8g2, oled, display...)
      leyendo como lo usas, no necesitas configurarlo;
    - detecta el tamano real de la pantalla leyendo la clase del
      constructor (p.ej. U8G2_SSD1306_128X32_UNIVISION_F_HW_I2C -> 128x32);
      si no encuentra un constructor, busca un #define de tamano comun
      (SCREEN_W/H, DISPLAY_WIDTH/HEIGHT...) y si tampoco hay, usa 128x64;
    - encuentra sola las funciones que dibujan y los arreglos de bytes.

PESTANA "PANTALLAS"
  El arbol de la izquierda lista cada funcion que produce dibujo.
  Arrastra los elementos; el cuadrito naranja redimensiona; las flechas
  mueven 1 px (Shift = 5).

  Contorno morado punteado = ese elemento vive en OTRA funcion (p.ej. una
  funcion de cabecera que llaman varias pantallas). Moverlo lo mueve en todas.

  Si un elemento se dibuja dentro de un bucle aparece varias veces y el
  panel lo dice ("se dibuja 5 veces"). Moverlo mueve las 5, porque cambia
  la constante de la expresion.

  Si una coordenada sale de una variable (drawStr(6, y, ...)), la app sigue
  la variable hasta su asignacion (int y = 24 + i * 10) y edita ahi. El
  panel lo indica con "(via y)".

  Un argumento que no tiene ningun numero literal aparece como [fijo] y no
  se puede arrastrar: no hay nada que reescribir sin cambiar la logica.

PESTANA "PIXEL ART"
  El combo lista TODOS los arreglos de bytes de la carpeta. Elige uno y
  editalo. Izquierdo pinta, derecho borra. Ctrl+rueda hace zoom.
  Teclas: P lapiz  E borrador  L linea  R rect  F rect lleno  O elipse
          D elipse llena  B relleno  T texto  S seleccion  I cuentagotas

NOTAS
  - No se crean archivos .bak. La red de seguridad es git y el Ctrl+Z de
    la app (que deshace sobre el texto del archivo, no sobre un modelo).
  - Los valores que el firmware calcula en tiempo real (contadores, sensores)
    se muestran con datos de muestra para que la vista se parezca a la real.
  - Las fuentes usan el ancho y alto reales de u8g2; los glifos se dibujan
    con una 5x7 escalada, asi que la posicion es fiel y el trazo aproximado.
"""

ABOUT = """\
<h3>u8g2 Studio %s</h3>
<p>Editor visual de interfaces para displays monocromaticos, para
cualquier proyecto que use u8g2 (o U8x8 / Adafruit_GFX).
Lee y reescribe tu propio codigo: sin formato propio, sin exportar,
sin copiar y pegar.</p>
<p>Licencia MIT. PyQt5 + Pillow.</p>
""" % APP_VERSION


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_QSS)
    initial = sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else None
    w = MainWindow(initial)
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
