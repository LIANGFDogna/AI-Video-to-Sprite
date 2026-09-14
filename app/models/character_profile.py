"""Project-level character geometry; independent of any animation's alpha bounds."""
from dataclasses import dataclass, field, replace
import math


@dataclass(frozen=True)
class CharacterProfile:
    canvas_size: tuple[int, int] = (512, 512)
    character_scale: float = 1/3  # source pixels → character/cell pixels
    ground_origin: tuple[float, float] = (256., 480.)
    canonical_root: tuple[float, float] = (256., 256.)
    reference_box_half_width: float = 128.
    facing: str = "right"
    canonical_root_offset: tuple[float, float] = field(init=False)

    def __post_init__(self):
        for name in ("canvas_size", "ground_origin", "canonical_root"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        self.validate()
        object.__setattr__(self, "canonical_root_offset", tuple(self.canonical_root[i]-self.ground_origin[i] for i in (0, 1)))

    def validate(self):
        if len(self.canvas_size) != 2 or any(not isinstance(v, int) or not 1 <= v <= 16384 for v in self.canvas_size) or math.prod(self.canvas_size) > 64_000_000:
            raise ValueError("Invalid character canvas size")
        if not math.isfinite(self.character_scale) or not .01 <= self.character_scale <= 8:
            raise ValueError("Invalid character scale")
        if math.prod(math.ceil(v/self.character_scale) for v in self.canvas_size) > 64_000_000:
            raise ValueError("Invalid character canvas size")
        for point in (self.ground_origin, self.canonical_root):
            if len(point) != 2 or not all(math.isfinite(v) for v in point):
                raise ValueError("Invalid character reference point")
        if self.canonical_root[0] != self.ground_origin[0]:
            raise ValueError("Canonical Root X must equal the character Y Axis")
        if not 0 <= self.ground_origin[0] < self.canvas_size[0] or not 0 < self.ground_origin[1] < self.canvas_size[1]:
            raise ValueError("Ground Origin must be inside the character canvas")
        if not 0 <= self.canonical_root[1] <= self.ground_origin[1]:
            raise ValueError("Canonical Root must be above Ground Origin")
        if not math.isfinite(self.reference_box_half_width) or not .5 <= self.reference_box_half_width <= 32768:
            raise ValueError("Invalid character reference box width")
        if self.facing not in ("left", "right"):
            raise ValueError("Invalid character facing")

    @property
    def reference_box(self):
        x, y = self.ground_origin
        return x-self.reference_box_half_width, 0., x+self.reference_box_half_width, y

    def with_edge(self, x):
        """Either handle edits only one half-width; the opposite edge is derived."""
        return replace(self, reference_box_half_width=max(.5, min(32768., abs(float(x)-self.ground_origin[0]))))

    def with_canonical_root(self, x, y):
        # X is unconditionally snapped, regardless of the clicked pixel's X.
        return replace(self, canonical_root=(self.ground_origin[0], min(self.ground_origin[1], max(0., float(y)))))

    def transform_key(self):
        # Reference width/facing annotate results; neither can change image pixels.
        return self.canvas_size, self.character_scale, self.ground_origin, self.canonical_root

    @classmethod
    def from_dict(cls, data):
        values = dict(data)
        offset = values.pop("canonical_root_offset", None)
        result = cls(**values)
        if offset is not None and tuple(offset) != result.canonical_root_offset:
            raise ValueError("Canonical Root offset does not match Ground Origin")
        return result
