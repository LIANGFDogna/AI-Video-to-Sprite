"""Catalog coverage and placeholder checks. Run after editing any interface text."""
import ast
from pathlib import Path


EXTRA = [
    "1024×1536", "Project Standard Canvas",
    "Native Resolution", "1536×1536", "1024×1024", "768×768", "512×512",
    "Standard 512×512", "1536→512 AI Character", "Default Output Resolution", "Source Canvas", "Import Idle Video", "Character reference: not established",
    "source_canvas", "RGBA", "RGB", "Mixed RGB / RGBA", "Frame sequence passthrough", "Frame sequence · Root / Motion / Align",
    "Y Axis", "X Axis", "Ground Origin", "Canonical Root", "right", "left", "Outside Character Reference Box",
    "1  Import", "2  Key", "3  Anchor", "4  Motion", "5  Align", "6  Sprite", "7  Export",
    "Original", "Transparent", "Alpha Matte", "Checkerboard", "Sheet grid", "Frame number", "Root point",
    "Ground line", "Alpha bounds", "Tracked features", "Root path", "Canvas bounds", "Raw Root Path", "Filtered Root Path", "Target Root Path",
    "Tolerance", "Softness", "Edge Feather (px)", "Despill Strength", "Minimum Alpha", "Noise Removal (pixels)", "Open / Close Radius",
    "Takeoff Frame", "Apex Frame", "Landing Frame", "Root X Curve", "Root Y Curve",
    "Frame", "Root position", "Confidence", "Alpha bounding box", "Warnings",
    "Root Point", "Ground Reference", "Alpha Bounds", "Cell Bounds", "Frame Number", "Root Path",
    "Black", "White", "Custom Color", "Fit", "100%", "200%", "400%", "Source", "Custom",
    "First Frame", "Previous Frame", "Save", "Don't Save", "Cancel", "Yes", "No", "OK",
    "Look in", "File name", "File type", "Open",
    "ROOT XY LOCK", "GROUND LOCK", "ROOT X + GROUND Y",
    "tooltip.option.ROOT XY LOCK", "tooltip.option.GROUND LOCK", "tooltip.option.ROOT X + GROUND Y",
    "Root X and Y stay fixed. Foot height can vary with the pose.",
    "Only the lowest effective alpha pixel stays on the ground. Source X motion is preserved.",
    "Root X stays fixed; the lowest effective alpha pixel stays on the ground. Anatomical root Y may vary.",
    "idle", "walk", "run", "jump", "fall", "dash", "ground_attack", "air_attack", "cinematic", "custom",
    "Clipping", "Ground Detection Failed", "Root Spike", "Low Confidence", "Alpha Bounds Change", "Size Jump", "Root Jump",
    "Loop Discontinuity", "Alpha Empty", "Root Outside Subject", "Tracking Lost", "Green Spill", "Motion Prediction",
]


def required_keys():
    keys = set(EXTRA)
    def add(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value:
            keys.add(node.value)
    for path in Path("app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
            args = node.args
            if name == "t" and args:
                add(args[0])
            if name == "ParameterPanel":
                for arg in args[:2]: add(arg)
            if name == "_button" and args: add(args[0])
            if name == "button" and args:
                add(args[1] if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "p" else args[0])
            if name == "note" and args: add(args[0])
            if name in ("combo", "slider", "integer", "decimal", "check", "text") and path.name == "main_window.py" and len(args) >= 2:
                add(args[1])
                if isinstance(args[0], ast.Constant): keys.add("tooltip."+args[0].value)
                if name == "combo" and isinstance(args[2], (ast.List, ast.Tuple)):
                    for value in args[2].elts: add(value)
            if name in ("question", "warning", "information", "critical", "getOpenFileName", "getSaveFileName", "getExistingDirectory"):
                for arg in args[1:]:
                    add(arg)
            if name == "progress" and args: add(args[-1])
            if name in ("ValueError", "RuntimeError") and args: add(args[0])
    for key in ("tolerance", "softness", "edge_feather", "despill_strength", "minimum_alpha", "noise_removal", "morphology"):
        keys.add("tooltip.chroma_key_settings."+key)
    for key in ("takeoff_frame", "apex_frame", "landing_frame"):
        keys.add("tooltip.motion_settings."+key)
    return keys


if __name__ == "__main__":
    from app.i18n import manager
    manager().validate()
    missing = required_keys()-manager().catalogs["en_US"].keys()
    if missing:
        print("\n".join(sorted(missing)))
        raise SystemExit(1)
    print(f"Catalogs valid: {len(manager().catalogs['en_US'])} keys; source coverage complete")
