import math
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont

from app.ui.video_viewer import VideoViewer


class SpritePreview(VideoViewer):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None

    def drawForeground(self, painter, rect):
        p = self.project
        if not p or not p.layout or not self.image_size[0]:
            return
        s, layout = self.display_scale, p.layout
        cw, ch = layout.width * s, layout.height * s
        cols = p.export_settings.columns
        rows = math.ceil(p.output_count / cols)
        if self.overlays["canvas"]:
            painter.setPen(self.pen("#a0aec2"))
            painter.drawRect(self.sceneRect())
        if self.overlays["grid"]:
            painter.setPen(self.pen("#66758e"))
            for x in range(cols + 1):
                painter.drawLine(QPointF(x*cw, 0), QPointF(x*cw, rows*ch))
            for y in range(rows + 1):
                painter.drawLine(QPointF(0, y*ch), QPointF(cols*cw, y*ch))
        screen_scale = max(self.transform().m11(), 0.001)
        font = QFont()
        font.setPixelSize(max(1, round(11 / screen_scale)))
        painter.setFont(font)
        for f in p.output_frames:
            x, y = (f.index % cols) * cw, (f.index // cols) * ch
            if not QRectF(x, y, cw, ch).intersects(rect):
                continue
            if self.overlays["ground"] and not p.is_passthrough:
                painter.setPen(self.pen("#a78547"))
                gy = y + layout.ground_baseline * s
                painter.drawLine(QPointF(x, gy), QPointF(x+cw, gy))
            if self.overlays["bounds"] and f.cell_bbox:
                l, t, r, b = f.cell_bbox
                painter.setPen(self.pen("#5ad6c5"))
                painter.drawRect(QRectF(x+l*s, y+t*s, (r-l)*s, (b-t)*s))
            if self.overlays["root"] and not p.is_passthrough:
                self.draw_root(painter, x+f.cell_root[0]*s, y+f.cell_root[1]*s, "#ffcb6b")
            if self.overlays["numbers"] and cw * screen_scale >= 22:
                painter.setPen(QColor("#ecf2fc"))
                painter.drawText(QPointF(x+5/screen_scale, y+15/screen_scale), str(f.index))
