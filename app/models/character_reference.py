"""Project-space reference geometry; never a tracked Root or image transform."""
from dataclasses import dataclass, replace
import math


@dataclass(frozen=True)
class CharacterReference:
    reference_animation_id: str
    reference_frame_index: int
    origin_x: float
    ground_y: float
    project_canvas_width: int
    project_canvas_height: int
    locked: bool = True

    def __post_init__(self):
        self.validate()

    def validate(self):
        if not self.reference_animation_id or not isinstance(self.reference_frame_index,int) or self.reference_frame_index < 0:
            raise ValueError("Invalid character reference frame")
        w,h=self.project_canvas_width,self.project_canvas_height
        if not all(isinstance(v,int) and 1<=v<=16384 for v in (w,h)) or w*h>64000000:
            raise ValueError("Invalid character reference canvas")
        if not all(math.isfinite(v) for v in (self.origin_x,self.ground_y)) or not (0<=self.origin_x<w and 0<=self.ground_y<h):
            raise ValueError("Character reference axes must be inside the project canvas")
        if self.locked is not True:
            raise ValueError("Saved character reference must be locked")

    @property
    def origin(self):return self.origin_x,self.ground_y

    @property
    def canvas_size(self):return self.project_canvas_width,self.project_canvas_height

    def moved(self,part,dx,dy):
        if part not in ('ground','y_axis','origin'):raise ValueError("Invalid character reference handle")
        x=self.origin_x+(dx if part!='ground' else 0)
        y=self.ground_y+(dy if part!='y_axis' else 0)
        return replace(self,origin_x=max(0,min(self.project_canvas_width-1,x)),ground_y=max(0,min(self.project_canvas_height-1,y)))

    @classmethod
    def from_dict(cls,data):
        return data if isinstance(data,cls) else cls(**data) if data else None


@dataclass(frozen=True)
class AnimationTransform:
    """One translation shared by the entire animation, in project canvas pixels."""
    offset_x: float = 0.
    offset_y: float = 0.

    def __post_init__(self):
        if not all(math.isfinite(v) and abs(v)<=32768 for v in (self.offset_x,self.offset_y)):
            raise ValueError("Invalid animation offset")

    @property
    def active(self):return bool(self.offset_x or self.offset_y)

    @classmethod
    def from_dict(cls,data):
        return data if isinstance(data,cls) else cls(**(data or {}))
