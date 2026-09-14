from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen
from app.i18n import t


def draw_character_space(painter, profile, display_scale=1., zoom=1., handles=False):
    """Draw project reference geometry separately from per-frame Alpha Bounds."""
    painter.save()
    s = display_scale
    ox, oy = profile.ground_origin
    width, height = profile.canvas_size
    def pen(color, style=Qt.PenStyle.SolidLine, width=1.5):
        p = QPen(QColor(color), width, style)
        p.setCosmetic(True)
        return p
    painter.setPen(pen("#779ac3", Qt.PenStyle.DashDotLine))
    painter.drawLine(QPointF(0, oy*s), QPointF(width*s, oy*s))
    painter.drawLine(QPointF(ox*s, 0), QPointF(ox*s, height*s))
    painter.setPen(pen("#79aef7", Qt.PenStyle.DashLine, 2))
    l, top, r, b = profile.reference_box
    painter.drawRect(QRectF(l*s, top*s, (r-l)*s, (b-top)*s))
    radius = 6/max(zoom, .001)
    if handles:
        painter.setBrush(QColor("#79aef7"))
        for x in (l, r):
            painter.drawRect(QRectF(x*s-radius, (top+b)*s/2-radius, 2*radius, 2*radius))
        painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(pen("#f3df9c", width=2))
    painter.drawEllipse(QPointF(ox*s, oy*s), radius, radius)
    painter.setPen(pen("#f59bd6", width=2.5))
    rx, ry = profile.canonical_root
    painter.drawLine(QPointF(rx*s-radius, ry*s), QPointF(rx*s+radius, ry*s))
    painter.drawLine(QPointF(rx*s, ry*s-radius), QPointF(rx*s, ry*s+radius))
    # Labels use viewport pixels so zoom never makes the text unreadable.
    transform = painter.transform()
    painter.resetTransform()
    painter.setPen(QColor("#bacbe0"))
    for point, label in (((ox*s, 16*s), "Y Axis"), ((width*s-35, oy*s-7), "X Axis"),
                         ((ox*s+8, oy*s+18), "Ground Origin"), ((rx*s+9, ry*s-10), "Canonical Root")):
        painter.drawText(transform.map(QPointF(*point)), t(label))
    painter.restore()
