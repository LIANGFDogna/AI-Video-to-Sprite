from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QWidget
from app.models.timeline_edit import curve_value
from app.i18n import t


class CurveEditor(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curve = 'linear'
        self.controls = (.25, .1, .75, .9)
        self.drag = None
        self.setMinimumHeight(135)
        self.setToolTip(t('Bezier: drag the two control points'))

    def plot(self):
        return QRectF(18, 10, max(10, self.width()-32), max(10, self.height()-30))

    def point(self, x, y):
        r = self.plot()
        return QPointF(r.left()+x*r.width(), r.bottom()-y*r.height())

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#202b3a'))
        p.setPen(QPen(QColor('#43556b'), 1))
        for i in range(5):
            p.drawLine(self.point(i/4, 0), self.point(i/4, 1))
            p.drawLine(self.point(0, i/4), self.point(1, i/4))
        path = QPainterPath(self.point(0, 0))
        for i in range(1, 101): path.lineTo(self.point(i/100, curve_value(i/100, self.curve, self.controls)))
        p.setPen(QPen(QColor('#75ddc4'), 2))
        p.drawPath(path)
        if self.curve == 'bezier':
            a, b = self.point(*self.controls[:2]), self.point(*self.controls[2:])
            p.setPen(QPen(QColor('#e8ba6f'), 1))
            p.drawLine(self.point(0, 0), a); p.drawLine(b, self.point(1, 1))
            p.setBrush(QColor('#e8ba6f'))
            p.drawEllipse(a, 6, 6); p.drawEllipse(b, 6, 6)
        p.end()

    def mousePressEvent(self, event):
        if self.curve != 'bezier': return
        for index in (0, 2):
            if (event.position()-self.point(*self.controls[index:index+2])).manhattanLength() < 22:
                self.drag = index

    def mouseMoveEvent(self, event):
        if self.drag is None: return
        r = self.plot()
        x = min(1., max(0., (event.position().x()-r.left())/r.width()))
        y = min(1., max(0., (r.bottom()-event.position().y())/r.height()))
        v = list(self.controls)
        if self.drag == 0: x, y = min(x, v[2]), min(y, v[3])
        else: x, y = max(x, v[0]), max(y, v[1])
        v[self.drag:self.drag+2] = (x, y)
        self.controls = tuple(v)
        self.changed.emit(self.controls)
        self.update()

    def mouseReleaseEvent(self, event):
        self.drag = None
