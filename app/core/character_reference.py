"""Reference source cache and resolution-only overlay mapping; no alignment detection."""
from pathlib import Path
from app.core.pipeline import Pipeline
from app.core.canvas_normalizer import canvas_transform, normalize_canvas
from app.utils.paths import frame_path, cache_directory
from app.utils.cache import FrameCache
from app.utils.rgba_image import to_rgba8


def reference_mapping(reference,layout,preserve_aspect=True):
    transform=canvas_transform(*reference.canvas_size,layout.width,layout.height,preserve_aspect)
    return transform.scale_x,transform.scale_y,transform.offset_x,transform.offset_y


def animation_cache(project,current_cache,project_file,animation_id):
    current_cache=Path(current_cache)
    if animation_id==project.animation_id:return current_cache
    if current_cache.name==project.animation_id and current_cache.parent.name=='animations':
        root=current_cache.parent.parent
    elif project.animation_id=='default':root=current_cache
    else:return cache_directory(project.project_id,project_file,animation_id)
    return root if animation_id=='default' else root/'animations'/animation_id


class ReferenceSource:
    """Load the original keyed reference once; offsets and timeline edits are ignored."""
    def __init__(self,project,reference,current_cache,project_file=None):
        self.reference=reference
        self.project=project.select_animation(reference.reference_animation_id)
        self.directory=animation_cache(project,current_cache,project_file,reference.reference_animation_id)
        self.pipe=Pipeline(self.project,self.directory)
        self.identity=(str(self.directory),reference.reference_animation_id,reference.reference_frame_index,self.pipe.key_signature())
        self.cache=FrameCache(48*1024*1024)
        self.pixels=None
        self.resized={}

    def get(self,cancel=None):
        if self.pixels is None:
            self.pipe.cancel=cancel
            self.pipe.ensure_key()
            path=frame_path(self.pipe.keyed,self.reference.reference_frame_index)
            pixels=self.cache.read(path)
            if (pixels.shape[1],pixels.shape[0])!=self.reference.canvas_size:
                raise ValueError("Reference canvas differs from the saved project canvas")
            self.pixels=pixels
        return self.pixels

    def output(self,layout,preserve_aspect=True,cancel=None):
        key=(layout.width,layout.height,preserve_aspect)
        if key not in self.resized:
            rgba=self.get(cancel)
            transform=canvas_transform(*self.reference.canvas_size,layout.width,layout.height,preserve_aspect)
            image=to_rgba8(rgba) if key[:2]==self.reference.canvas_size else normalize_canvas(rgba,transform)
            self.resized={key:image}
        return self.resized[key]
