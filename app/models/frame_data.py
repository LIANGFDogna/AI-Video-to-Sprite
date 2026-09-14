from dataclasses import dataclass, field

BBox = tuple[int, int, int, int]
Point = tuple[float, float]


@dataclass
class FrameData:
    index: int
    bbox: BBox | None = None
    root: Point = (0.0, 0.0)
    tracking_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    features: list[Point] = field(default_factory=list)
    manual: bool = False
    offset: Point = (0.0, 0.0)
    cell_root: Point = (0.0, 0.0)
    cell_bbox: BBox | None = None
    raw_root: Point | None = None
    filtered_root: Point | None = None
    target_root: Point | None = None
    motion_root: Point | None = None
    correction: Point = (0.0, 0.0)
    root_motion: Point = (0.0, 0.0)
    velocity: Point = (0.0, 0.0)
    ground: float | None = None
    cell_ground: float | None = None
    ground_roi: BBox | None = None
    tracking_method: str = "optical_flow"
    tracking_metrics: dict = field(default_factory=dict)
    effective_policy: tuple[str, str] = ("LOCK", "GROUND_LOCK")
    tracked_root: Point | None = None  # Character Space pixels, before correction
    character_correction: Point | None = None

    def __post_init__(self):
        for name in ("root", "offset", "cell_root", "raw_root", "filtered_root", "target_root", "motion_root", "correction", "root_motion", "velocity", "tracked_root", "character_correction"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, tuple(value))


@dataclass
class CellLayout:
    width: int
    height: int
    target_root: Point
    ground_baseline: float
    required_width: int
    required_height: int
    clipped_frames: list[int] = field(default_factory=list)
    canvas_mode: str = "auto_bounds"
    normalize_scale: Point = (1.0, 1.0)
    normalize_offset: Point = (0.0, 0.0)
    source_width: int = 0
    source_height: int = 0
