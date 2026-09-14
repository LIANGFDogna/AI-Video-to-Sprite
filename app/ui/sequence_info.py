"""Shared, explicit source sample information for import and project panels."""
from app.i18n import t


def format_summary(formats):
    lines = []
    for info in formats:
        line = t("{mode} · {channels} channels · {bits}-bit/channel · Alpha {alpha}",
            mode=info["color_mode"], channels=info["channels"], bits=info["bits_per_channel"], alpha="✓" if info["has_alpha"] else "—")
        line += "\n" + t("Total bits per pixel: {bits}", bits=info["bits_per_pixel"])
        if line not in lines:
            lines.append(line)
    if any(info["bits_per_channel"] == 16 for info in formats):
        lines.append(t("Source/cache: 16-bit/channel. Resize: float32.\nPreview/output: RGBA 8-bit/channel.\nRGB and Alpha: full-range rounded conversion 0..65535 → 0..255."))
    return "\n".join(lines)


def alpha_warning(formats):
    missing = sum(not info["has_alpha"] for info in formats)
    if not missing:
        return ""
    if missing == len(formats):
        return t("These sequence frames have no Alpha channel and will be treated as fully opaque images.")
    return t("Some sequence frames have no Alpha channel; those frames will be treated as fully opaque images.")
