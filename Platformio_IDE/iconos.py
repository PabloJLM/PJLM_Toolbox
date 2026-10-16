"""Iconos vectoriales dibujados con QPainter (sin archivos de imagen)."""
from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _linea(p, *pts):
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))


def _verificar(p, c):
    p.setPen(QPen(c, 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    _linea(p, (5.5, 12.5), (10, 17), (18.5, 7.5))


def _subir(p, c):
    _linea(p, (5, 12), (18, 12))
    _linea(p, (12.5, 6.5), (18, 12), (12.5, 17.5))


def _detener(p, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(7, 7, 10, 10), 1.5, 1.5)


def _monitor(p, c):
    p.drawEllipse(QPointF(10.5, 10.5), 5.5, 5.5)
    _linea(p, (14.6, 14.6), (19.5, 19.5))


def _refrescar(p, c):
    p.drawArc(QRectF(5, 5, 14, 14), 70 * 16, 300 * 16)
    _linea(p, (11.2, 2.8), (14.4, 5.4), (11.6, 8.4))


def _carpeta(p, c):
    ruta = QPainterPath()
    ruta.moveTo(3.5, 7)
    ruta.lineTo(3.5, 18.5)
    ruta.lineTo(20.5, 18.5)
    ruta.lineTo(20.5, 9)
    ruta.lineTo(11.5, 9)
    ruta.lineTo(9.5, 6.5)
    ruta.lineTo(4.5, 6.5)
    ruta.closeSubpath()
    p.drawPath(ruta)


def _app(p, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(1, 1, 22, 22), 5, 5)
    p.setPen(QPen(QColor("#FFFFFF"), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    _linea(p, (7, 12), (16.5, 12))
    _linea(p, (12.5, 7.5), (17, 12), (12.5, 16.5))


_DIBUJOS = {
    "verificar": _verificar, "subir": _subir, "detener": _detener,
    "monitor": _monitor, "refrescar": _refrescar, "carpeta": _carpeta, "app": _app,
}


def icono(nombre: str, color: str, tam: int = 24) -> QIcon:
    escala = 2  # nitido en pantallas HiDPI
    pm = QPixmap(tam * escala, tam * escala)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(tam * escala / 24.0, tam * escala / 24.0)
    c = QColor(color)
    p.setPen(QPen(c, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    dibujo = _DIBUJOS.get(nombre)
    if dibujo:
        dibujo(p, c)
    p.end()
    pm.setDevicePixelRatio(escala)
    return QIcon(pm)
