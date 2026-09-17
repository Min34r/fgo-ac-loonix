"""
Chamfered UI components: ChamferWidget and ChamferButton.
Draws geometric panels with top-left and bottom-right 45-degree chamfered cuts.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QPushButton, QWidget


class ChamferWidget(QWidget):
    """Container widget with top-left and bottom-right chamfered corners."""

    def __init__(
        self,
        cut: float = 8.0,
        stroke_color: str = "#7CC4E4",
        stroke_width: float = 1.0,
        fill_color: str = "#1A1D22",
        parent=None,
    ):
        super().__init__(parent)
        self.cut = cut
        self.stroke_color = QColor(stroke_color) if stroke_color else None
        self.stroke_width = stroke_width
        self.fill_color = QColor(fill_color) if fill_color else None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def setColors(self, fill: str, stroke: str):
        self.fill_color = QColor(fill) if fill else None
        self.stroke_color = QColor(stroke) if stroke else None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return

        inset = self.stroke_width / 2.0 if self.stroke_color else 0.0
        c = max(0.0, min(self.cut, min(w, h) / 2.0))

        # Top-left and bottom-right corners cut away
        poly = QPolygonF([
            QPointF(c + inset, inset),
            QPointF(w - inset, inset),
            QPointF(w - inset, h - c - inset),
            QPointF(w - c - inset, h - inset),
            QPointF(inset, h - inset),
            QPointF(inset, c + inset),
        ])

        if self.fill_color:
            painter.setBrush(QBrush(self.fill_color))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.stroke_color and self.stroke_width > 0:
            painter.setPen(QPen(self.stroke_color, self.stroke_width))
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        painter.drawPolygon(poly)


class ChamferButton(QPushButton):
    """Push button with chamfered top-left and bottom-right corners."""

    def __init__(
        self,
        text: str = "",
        cut: float = 8.0,
        stroke_color: str = "#7CC4E4",
        hover_stroke: str = "#B3E0F5",
        fill_color: str = "#1A1D22",
        hover_fill: str = "#23272E",
        text_color: str = "#E8EAED",
        font_size: int = 14,
        parent=None,
    ):
        super().__init__(text, parent)
        self.cut = cut
        self.normal_stroke = QColor(stroke_color)
        self.hover_stroke = QColor(hover_stroke)
        self.normal_fill = QColor(fill_color)
        self.hover_fill = QColor(hover_fill)
        self.text_color = QColor(text_color)
        self.font_size = font_size
        self._is_hovered = False

        font = self.font()
        font.setPointSize(self.font_size)
        font.setBold(True)
        self.setFont(font)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return

        c = max(0.0, min(self.cut, min(w, h) / 2.0))
        inset = 1.0

        poly = QPolygonF([
            QPointF(c + inset, inset),
            QPointF(w - inset, inset),
            QPointF(w - inset, h - c - inset),
            QPointF(w - c - inset, h - inset),
            QPointF(inset, h - inset),
            QPointF(inset, c + inset),
        ])

        fill = self.hover_fill if self._is_hovered else self.normal_fill
        stroke = self.hover_stroke if self._is_hovered else self.normal_stroke

        if not self.isEnabled():
            fill = QColor("#121417")
            stroke = QColor("#2B3038")

        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(stroke, 1.5 if self._is_hovered else 1.0))
        painter.drawPolygon(poly)

        # Draw centered text
        painter.setFont(self.font())
        txt_col = self.text_color if self.isEnabled() else QColor("#6F7681")
        if self._is_hovered and self.isEnabled():
            txt_col = QColor("#FFFFFF")
        painter.setPen(txt_col)
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.text())
