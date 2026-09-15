"""Compile non-destructive frame edits; render the same cells for all consumers."""
import copy
from dataclasses import asdict
import numpy as np

from app.core.alignment import warp_rgba
from app.core.alpha_utils import alpha_bbox
from app.models.frame_data import FrameData
from app.models.timeline_edit import FrameOverride, TimelineFrame
from app.core.animation_transform import apply_animation_transform


def compile_timeline(edit):
    visible = [t.id for t in edit.track_layout if t.visible and t.id != "reference"]
    events = {0.: []}
    for order, frame in enumerate(edit.timeline_clips):
        if frame.track_id not in visible:
            continue
        events.setdefault(round(frame.start, 10), []).append((True, frame, order))
        events.setdefault(round(frame.end, 10), []).append((False, frame, order))
    edges = sorted(events)
    if len(edges) > 100001:
        raise ValueError("Timeline output exceeds 100000 frames")
    active = {track: {} for track in visible}
    result = []
    for start, end in zip(edges, edges[1:]):
        for entering, frame, order in events[start]:
            if entering:
                active[frame.track_id][frame.id] = (frame, order)
            else:
                active[frame.track_id].pop(frame.id, None)
        layers = [max(active[track].values(), key=lambda pair: (pair[0].start, pair[1]))[0]
                  for track in visible if active[track]]
        result.append(dict(start=start, duration=end-start, layers=[f.id for f in layers],
                           source_index=layers[0].source_index if layers else -1))
    return result


def compile_final_timing(project):
    if project.timeline_edit.enabled:return compile_timeline(project.timeline_edit)
    fps=project.video.fps or 24
    return [dict(start=i/fps,duration=1/fps,layers=[f'source:{i}'],source_index=i) for i in range(project.video.frame_count)]


def composite_rgba(layers, shape):
    if len(layers) == 1:
        return layers[0].copy()
    out = np.zeros(shape, np.float32)
    for image in layers:
        src = image.astype(np.float32)/255.
        alpha = src[..., 3:4]
        out[..., :3] = src[..., :3]*alpha + out[..., :3]*(1-alpha)
        out[..., 3:4] = alpha + out[..., 3:4]*(1-alpha)
    np.divide(out[..., :3], np.maximum(out[..., 3:4], 1e-8), out=out[..., :3])
    return np.clip(out*255+.5, 0, 255).astype(np.uint8)


def transform_layer(image, override):
    if override == FrameOverride():
        return image  # Identity must preserve hidden RGB and alpha byte-for-byte.
    h, w = image.shape[:2]
    dx = override.offset_x + (1-override.scale)*w/2
    dy = override.offset_y + (1-override.scale)*h/2
    if override.scale == 1 and dx == round(dx) and dy == round(dy):
        out = np.zeros_like(image)
        x, y = int(dx), int(dy)
        sx, sy, tx, ty = max(0, -x), max(0, -y), max(0, x), max(0, y)
        width, height = min(w-sx, w-tx), min(h-sy, h-ty)
        if width > 0 and height > 0:
            out[ty:ty+height, tx:tx+width] = image[sy:sy+height, sx:sx+width]
    else:
        out = warp_rgba(image, w, h, override.scale, (dx, dy))
    if override.opacity != 1:
        out = out.copy()
        out[..., 3] = np.clip(out[..., 3].astype(np.float32)*override.opacity+.5, 0, 255).astype(np.uint8)
    return out


def render_timeline_frame(project, timing, read_base, index=0, read_keyed=None):
    clips = {f.id: f for f in project.timeline_edit.timeline_clips} if project.timeline_edit.enabled else {f'source:{timing["source_index"]}':TimelineFrame(timing['source_index'],timing['start'],timing['duration'])}
    layers, warnings = [], []
    layout = project.layout
    primary = None
    for ident in timing['layers']:
        clip = clips[ident]
        value = project.timeline_edit.frame_overrides.get(ident, FrameOverride())
        image = read_base(clip.source_index)
        base = project.tracking_results[clip.source_index]
        image,base=apply_animation_transform(project,image,base,read_keyed)
        warnings.extend(base.warnings)
        bbox = base.cell_bbox
        dx = value.offset_x+(1-value.scale)*layout.width/2
        dy = value.offset_y+(1-value.scale)*layout.height/2
        if bbox and (bbox[0]*value.scale+dx < 0 or bbox[1]*value.scale+dy < 0 or
                     bbox[2]*value.scale+dx > layout.width or bbox[3]*value.scale+dy > layout.height):
            warnings.append('Clipping')
        layers.append(transform_layer(image, value))
        if primary is None:
            primary = copy.deepcopy(base)
            primary.cell_root = tuple(base.cell_root[a]*value.scale+(dx, dy)[a] for a in (0, 1))
            primary.cell_ground = None if base.cell_ground is None else base.cell_ground*value.scale+dy
            primary.offset = (base.offset[0]+value.offset_x, base.offset[1]+value.offset_y)
    pixels = composite_rgba(layers, (layout.height, layout.width, 4))
    frame = primary or FrameData(index, tracking_method='empty')
    frame.index = index
    frame.cell_bbox = alpha_bbox(pixels, 0, 0)
    frame.warnings = list(dict.fromkeys([*frame.warnings, *warnings]))
    return pixels, frame
