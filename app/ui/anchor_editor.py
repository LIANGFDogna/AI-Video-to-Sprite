from PySide6.QtCore import Signal

from app.ui.video_viewer import VideoViewer


class AnchorEditor(VideoViewer):
    root_selected = Signal(float, float)
    color_selected = Signal(float, float)
    roi_selected = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_clicked.connect(self._clicked)
        self._roi_start = None

    def _clicked(self, x, y):
        if self.interaction == "root":
            self.root_selected.emit(x, y)
        elif self.interaction == "color":
            self.color_selected.emit(x, y)
        elif self.interaction in ("ground_roi", "body_roi"):
            if self._roi_start is None:
                self._roi_start = (x, y)
            else:
                sx, sy = self._roi_start
                self._roi_start = None
                roi = (min(sx, x), min(sy, y), max(sx, x), max(sy, y))
                if roi[2]-roi[0] >= 2 and roi[3]-roi[1] >= 2:
                    self.roi_selected.emit(self.interaction, roi)

    def set_interaction(self, mode):
        super().set_interaction(mode)
        self._roi_start = None
