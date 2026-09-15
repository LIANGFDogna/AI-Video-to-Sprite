"""One per-animation translation; source canvas fitting remains untouched."""
import copy
import numpy as np
from app.core.alignment import warp_rgba
from app.core.alpha_utils import alpha_bbox
from app.core.canvas_normalizer import canvas_transform, normalize_canvas
from app.utils.rgba_image import to_rgba8

ANIMATION_OVERFLOW = "Animation content exceeds project canvas."


def translate_rgba(image,x,y):
    if not x and not y:return image
    h,w=image.shape[:2]
    if x!=round(x) or y!=round(y):return warp_rgba(image,w,h,1.,(x,y))
    x,y=int(x),int(y)
    out=np.zeros_like(image)
    sx,sy,tx,ty=max(0,-x),max(0,-y),max(0,x),max(0,y)
    cw,ch=min(w-sx,w-tx),min(h-sy,h-ty)
    if cw>0 and ch>0:out[ty:ty+ch,tx:tx+cw]=image[sy:sy+ch,sx:sx+cw]
    return out


def apply_animation_transform(project,image,frame,read_keyed):
    value=project.animation_transform
    if not value.active:return image,frame
    frame=copy.deepcopy(frame)
    sx,sy=project.layout.normalize_scale
    dx,dy=value.offset_x*sx,value.offset_y*sy
    if project.is_passthrough:
        # Translate/crop on the already fitted project canvas, before output resize.
        source=read_keyed(frame.index)
        bbox=alpha_bbox(source,0,0)
        w,h=source.shape[1],source.shape[0]
        x,y=value.offset_x,value.offset_y
        pixels=translate_rgba(source,x,y)
        settings=project.sprite_cell
        transform=canvas_transform(w,h,settings.target_width,settings.target_height,settings.preserve_aspect_ratio) if settings.canvas_mode=='normalize_source' else None
        pixels=normalize_canvas(pixels,transform) if transform else to_rgba8(pixels)
    else:
        # Old automatic alignment remains an explicit, independent operation.
        bbox=frame.cell_bbox;w,h=image.shape[1],image.shape[0];x,y=dx,dy
        pixels=translate_rgba(image,dx,dy)
    if bbox and (bbox[0]+x<0 or bbox[1]+y<0 or bbox[2]+x>w or bbox[3]+y>h):
        frame.warnings=list(dict.fromkeys([*frame.warnings,ANIMATION_OVERFLOW]))
    frame.cell_root=(frame.cell_root[0]+dx,frame.cell_root[1]+dy)
    frame.cell_ground=None if frame.cell_ground is None else frame.cell_ground+dy
    frame.cell_bbox=alpha_bbox(pixels,0,0)
    frame.offset=(frame.offset[0]+dx,frame.offset[1]+dy)
    return pixels,frame
