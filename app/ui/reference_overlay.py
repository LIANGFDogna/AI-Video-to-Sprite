"""Cosmetic reference guides. These are painter overlays, never PNG pixels."""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor
from app.i18n import t


def draw_reference(painter,view,reference,mapping=(1.,1.,0.,0.),ground=True,axes=True,origin=True):
    if not reference:return
    sx,sy,ox,oy=mapping
    x,y=reference.origin_x*sx+ox,reference.ground_y*sy+oy
    w,h=view.image_size
    painter.save()
    if ground:
        painter.setPen(view.pen('#e6b879',1.6));painter.drawLine(QPointF(0,y),QPointF(w,y))
    if axes:
        painter.setPen(view.pen('#86b7df',1.));painter.drawLine(QPointF(x,0),QPointF(x,h))
    if origin:
        zoom=max(view.transform().m11(),.001);radius=5/zoom
        painter.setPen(view.pen('#ffe8bb',1.5));painter.setBrush(QColor('#253547'))
        painter.drawEllipse(QPointF(x,y),radius,radius)
        painter.drawLine(QPointF(x-radius*1.6,y),QPointF(x+radius*1.6,y))
        painter.drawLine(QPointF(x,y-radius*1.6),QPointF(x,y+radius*1.6))
        font=painter.font();font.setPixelSize(max(1,round(12/zoom)));painter.setFont(font)
        painter.drawText(QPointF(max(3,x+9/zoom),max(14/zoom,y-9/zoom)),t('Origin ({x:.0f}, {y:.0f})',x=reference.origin_x,y=reference.ground_y))
    painter.restore()
