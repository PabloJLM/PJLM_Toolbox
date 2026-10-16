"""Carga de temas desde temas.json y generacion de la hoja de estilo (QSS)."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtGui import QColor

BASE = Path(__file__).resolve().parent
RUTA_TEMAS = BASE / "temas.json"
DIR_BG = BASE / "imgs" / "bg"
PREDETERMINADO = "Reze"

# valores de respaldo por si a un tema del json le falta alguna clave
_RESPALDO = {
    "fondo_app": "#141826", "fondo_panel": "#1C2233", "texto": "#D6DEEB",
    "borde": "#2E3A5C", "acento": "#7AA2F7", "texto_acento": "#0F111A",
    "fondo_editor": "#0F111A", "texto_editor": "#D6DEEB",
    "fondo_consola": "#0B0D14", "texto_consola": "#C3CCE3",
    "linea_actual": "#161A28", "num_linea": "#3B4261", "seleccion": "#2E3A5C",
    "hl": {
        "palabras_clave": "#BB9AF7", "tipos": "#7AA2F7", "funciones": "#7DCFFF",
        "numeros": "#FF9E64", "cadenas": "#9ECE6A", "preprocesador": "#F7768E",
        "comentarios": "#565F89",
    },
    "consola": {"ok": "#9ECE6A", "error": "#F7768E", "aviso": "#E0AF68", "info": "#7AA2F7"},
    "bg": None,
}


def cargar_temas() -> dict:
    try:
        with RUTA_TEMAS.open(encoding="utf-8") as f:
            datos = json.load(f)
        if isinstance(datos, dict) and datos:
            return datos
    except (OSError, ValueError):
        pass
    return {PREDETERMINADO: _RESPALDO}


def tema(temas: dict, nombre: str) -> dict:
    """Devuelve el tema completo (rellenando claves faltantes)."""
    base = temas.get(nombre) or temas.get(PREDETERMINADO) or next(iter(temas.values()))
    t = dict(_RESPALDO)
    t.update(base)
    t["hl"] = {**_RESPALDO["hl"], **base.get("hl", {})}
    t["consola"] = {**_RESPALDO["consola"], **base.get("consola", {})}
    return t


def ruta_bg(t: dict) -> str | None:
    archivo = t.get("bg")
    if not archivo:
        return None
    ruta = DIR_BG / archivo
    return str(ruta) if ruta.exists() else None


def _mas_claro(color: str, factor: int = 115) -> str:
    c = QColor(color)
    return (c.darker(factor) if c.lightness() > 160 else c.lighter(factor)).name()


def hoja_estilo(t: dict) -> str:
    app, panel, texto = t["fondo_app"], t["fondo_panel"], t["texto"]
    borde, acento, tacento = t["borde"], t["acento"], t["texto_acento"]
    fed, ted = t["fondo_editor"], t["texto_editor"]
    fcon, tcon = t["fondo_consola"], t["texto_consola"]
    sel = t["seleccion"]
    hover = _mas_claro(acento)
    return f"""
QWidget {{ background:{app}; color:{texto}; }}
QMainWindow::separator {{ background:{borde}; width:1px; height:1px; }}
QMenuBar {{ background:{panel}; border-bottom:1px solid {borde}; }}
QMenuBar::item {{ padding:4px 10px; background:transparent; }}
QMenuBar::item:selected, QMenu::item:selected {{ background:{acento}; color:{tacento}; }}
QMenu {{ background:{panel}; border:1px solid {borde}; padding:4px 0; }}
QMenu::item {{ padding:5px 28px 5px 22px; }}
QMenu::separator {{ height:1px; background:{borde}; margin:4px 8px; }}
QMenu::item:disabled {{ color:{t['num_linea']}; }}
QToolBar {{ background:{panel}; border:none; border-bottom:1px solid {borde}; padding:6px 8px; spacing:6px; }}
QToolButton {{ background:transparent; border:none; border-radius:4px; padding:4px; }}
QToolButton:hover {{ background:{borde}; }}
QToolButton:checked {{ background:{borde}; }}
QToolButton#redondo {{ background:{acento}; border-radius:16px; padding:0; }}
QToolButton#redondo:hover {{ background:{hover}; }}
QToolButton#redondo:disabled {{ background:{borde}; }}
QPushButton {{ background:{panel}; border:1px solid {borde}; border-radius:4px; padding:4px 12px; }}
QPushButton:hover {{ border-color:{acento}; }}
QPushButton:checked, QPushButton:default {{ background:{acento}; color:{tacento}; border-color:{acento}; }}
QPushButton:disabled {{ color:{t['num_linea']}; }}
QComboBox, QLineEdit, QSpinBox {{
    background:{fed}; color:{ted}; border:1px solid {borde}; border-radius:4px; padding:3px 6px;
    selection-background-color:{sel}; selection-color:{ted};
}}
QComboBox:hover, QLineEdit:focus, QSpinBox:focus {{ border-color:{acento}; }}
QComboBox::drop-down {{ border:none; width:18px; }}
QComboBox QAbstractItemView {{ background:{panel}; color:{texto}; border:1px solid {borde};
    selection-background-color:{acento}; selection-color:{tacento}; outline:0; }}
QTabWidget::pane {{ border:none; }}
QTabBar {{ background:{panel}; }}
QTabBar::tab {{ background:{panel}; color:{texto}; padding:6px 14px; border:none;
    border-right:1px solid {borde}; border-top:2px solid transparent; }}
QTabBar::tab:selected {{ background:{fed}; color:{ted}; border-top:2px solid {acento}; }}
QTabBar::tab:hover:!selected {{ background:{borde}; }}
QTreeView, QTreeWidget, QListWidget {{ background:{panel}; border:none; outline:0; }}
QTreeView::item, QTreeWidget::item {{ padding:3px 2px; }}
QTreeView::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{ background:{sel}; color:{texto}; }}
QTreeView::item:hover, QTreeWidget::item:hover {{ background:{borde}; }}
QHeaderView::section {{ background:{panel}; color:{texto}; border:none; border-bottom:1px solid {borde}; padding:4px; }}
QPlainTextEdit {{ border:none; selection-background-color:{sel}; }}
QPlainTextEdit#editor {{ background:{fed}; color:{ted}; }}
QPlainTextEdit#salida, QPlainTextEdit#monitor {{ background:{fcon}; color:{tcon}; }}
QStatusBar {{ background:{panel}; border-top:1px solid {borde}; }}
QStatusBar QLabel {{ background:transparent; padding:0 8px; }}
QStatusBar::item {{ border:none; }}
QSplitter::handle {{ background:{borde}; }}
QSplitter::handle:horizontal {{ width:1px; }}
QSplitter::handle:vertical {{ height:1px; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:0; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:0; }}
QScrollBar::handle {{ background:{borde}; border-radius:4px; min-height:24px; min-width:24px; }}
QScrollBar::handle:hover {{ background:{t['num_linea']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QGroupBox {{ border:1px solid {borde}; border-radius:6px; margin-top:12px; padding:10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; color:{acento}; }}
QCheckBox {{ background:transparent; spacing:6px; }}
QCheckBox::indicator {{ width:13px; height:13px; border:1px solid {t['num_linea']}; border-radius:3px; background:{fed}; }}
QCheckBox::indicator:checked {{ background:{acento}; border-color:{acento}; }}
QCheckBox::indicator:disabled {{ background:{borde}; border-color:{borde}; }}
QLabel {{ background:transparent; }}
QLabel#titulo {{ font-size:22pt; font-weight:bold; color:{acento}; }}
QLabel#tenue {{ color:{t['num_linea']}; }}
QSlider::groove:horizontal {{ height:4px; background:{borde}; border-radius:2px; }}
QSlider::handle:horizontal {{ background:{acento}; width:14px; margin:-5px 0; border-radius:7px; }}
QToolTip {{ background:{panel}; color:{texto}; border:1px solid {borde}; padding:4px; }}
QWidget#barra_buscar, QWidget#barra_panel {{ background:{panel}; border-top:1px solid {borde}; }}
"""
