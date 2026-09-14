from app.core.canvas_fit import CanvasFit
from app.i18n import t


def canvas_fit_summary(source, target):
    text = t("Project Standard Canvas: {width} × {height}", width=target[0], height=target[1])
    text += "\n" + t("Canvas fit: center crop / pad")
    if source and min(source) > 0:
        fit = CanvasFit(tuple(source), tuple(target))
        text = t("Original size: {width} × {height}", width=source[0], height=source[1]) + "\n" + text
        text += "\n" + t("Padding L / T / R / B: {left} / {top} / {right} / {bottom}", **dict(zip(("left", "top", "right", "bottom"), fit.padding)))
        text += "\n" + t("Crop L / T / R / B: {left} / {top} / {right} / {bottom}", **dict(zip(("left", "top", "right", "bottom"), fit.crop)))
    return text
