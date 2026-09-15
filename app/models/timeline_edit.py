"""Non-destructive timeline data. Times are seconds; frame IDs identify instances."""
from dataclasses import asdict, dataclass, field
import copy
import math
import uuid


def identifier():
    return uuid.uuid4().hex


def curve_value(x, curve="linear", bezier=(.25, .1, .75, .9)):
    x = min(1., max(0., x))
    if curve == "linear":
        return x
    if curve == "ease_in":
        return x*x
    if curve == "ease_out":
        return 1-(1-x)**2
    if curve == "ease_in_out":
        return x*x*(3-2*x)
    if curve != "bezier":
        raise ValueError("Invalid timing curve")
    x1, y1, x2, y2 = bezier
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in bezier) or x1 > x2 or y1 > y2:
        raise ValueError("Bezier controls must be monotonic and within 0..1")
    def cubic(t, a, b):
        return 3*(1-t)**2*t*a + 3*(1-t)*t*t*b + t**3
    lo, hi = 0., 1.
    for _ in range(36):
        mid = (lo+hi)/2
        if cubic(mid, x1, x2) < x:
            lo = mid
        else:
            hi = mid
    return cubic((lo+hi)/2, y1, y2)


def inverse_curve(y, curve, bezier):
    if y <= 0: return 0.
    if y >= 1: return 1.
    lo, hi = 0., 1.
    for _ in range(36):
        mid = (lo+hi)/2
        if curve_value(mid, curve, bezier) < y:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


def resample_indices(count, target, curve="linear", bezier=(.25, .1, .75, .9), protected=()):
    if count < 1 or not 1 <= target <= 100000:
        raise ValueError("Target frame count must be between 1 and 100000")
    protected = set(protected)
    if len(protected) > target:
        raise ValueError("Target count is smaller than the protected keyframe count")
    desired = [round(curve_value(i/max(1, target-1), curve, bezier)*(count-1)) for i in range(target)]
    if target >= count:
        chosen = list(range(count))
        chosen.extend(desired[i % len(desired)] for i in range(target-count))
        return sorted(chosen)
    chosen = set(protected)
    for index in desired:
        if len(chosen) == target:
            break
        available = (i for i in range(count) if i not in chosen)
        chosen.add(min(available, key=lambda i: (abs(i-index), i)))
    return sorted(chosen)


@dataclass
class FrameOverride:
    offset_x: float = 0.
    offset_y: float = 0.
    scale: float = 1.
    opacity: float = 1.


@dataclass
class TimelineFrame:
    source_index: int = 0
    start: float = 0.
    duration: float = 1/24
    track_id: str = "main"
    id: str = field(default_factory=identifier)
    keyframe: bool = False
    reversed: bool = False
    speed: float = 1.
    curve: str = "linear"

    @property
    def end(self):
        return self.start+self.duration


@dataclass
class TimelineTrack:
    id: str = "main"
    name: str = "Main Animation"
    visible: bool = True
    locked: bool = False


def default_tracks():
    return [TimelineTrack(i, n) for i, n in (("main", "Main Animation"), ("overlay", "Overlay"),
                                           ("effects", "Effects"), ("reference", "Reference"))]


@dataclass
class TimelineEdit:
    enabled: bool = False
    source_frames: list[int] = field(default_factory=list)
    timeline_clips: list[TimelineFrame] = field(default_factory=list)
    frame_overrides: dict[str, FrameOverride] = field(default_factory=dict)
    retime_segments: list[dict] = field(default_factory=list)
    deleted_frames: list[dict] = field(default_factory=list)
    copied_segments: list[dict] = field(default_factory=list)
    track_layout: list[TimelineTrack] = field(default_factory=default_tracks)

    @classmethod
    def from_dict(cls, data):
        data = copy.deepcopy(data or {})
        data['timeline_clips'] = [TimelineFrame(**f) for f in data.get('timeline_clips', [])]
        data['frame_overrides'] = {k: FrameOverride(**v) for k, v in data.get('frame_overrides', {}).items()}
        if 'track_layout' in data:
            data['track_layout'] = [TimelineTrack(**v) for v in data['track_layout']]
        return cls(**data)

    def initialize(self, count, fps):
        if not self.source_frames:
            self.source_frames = list(range(count))
            self.timeline_clips = [TimelineFrame(i, i/fps, 1/fps) for i in range(count)]
        self.enabled = True

    @property
    def duration(self):
        return max((f.end for f in self.timeline_clips), default=0.)

    def frames(self, track=None):
        order = {t.id: i for i, t in enumerate(self.track_layout)}
        return sorted((f for f in self.timeline_clips if track is None or f.track_id == track),
                      key=lambda f: (f.start, order[f.track_id], f.id))

    def selected(self, ids, editable=True):
        ids = set(ids)
        result = [f for f in self.frames() if f.id in ids]
        locked = {t.id for t in self.track_layout if t.locked}
        if editable and any(f.track_id in locked for f in result):
            raise ValueError("A selected track is locked")
        return result

    def validate(self, source_count):
        tracks = {t.id for t in self.track_layout}
        if not 1 <= len(tracks) <= 4 or len(tracks) != len(self.track_layout):
            raise ValueError("Timeline requires one to four unique tracks")
        ids = set()
        for f in self.timeline_clips:
            if f.id in ids or f.track_id not in tracks or not 0 <= f.source_index < source_count:
                raise ValueError("Invalid timeline source frame or track")
            ids.add(f.id)
            if not all(math.isfinite(v) for v in (f.start, f.duration, f.speed)) or f.start < 0 or f.duration <= 0 or f.end > 86400 or f.speed <= 0:
                raise ValueError("Invalid timeline timing")
        for override in self.frame_overrides.values():
            if not all(math.isfinite(v) for v in asdict(override).values()) or not .01 <= override.scale <= 8 or not 0 <= override.opacity <= 1:
                raise ValueError("Invalid frame transform")

    def delete(self, ids, ripple=True):
        selected = self.selected(ids)
        selected_ids = {f.id for f in selected}
        if ripple:
            for frame in self.timeline_clips:
                if frame.id not in selected_ids:
                    frame.start = max(0., frame.start-sum(f.duration for f in selected if f.track_id == frame.track_id and f.end <= frame.start+1e-8))
        self.deleted_frames.extend(asdict(f) for f in selected)
        self.timeline_clips = [f for f in self.timeline_clips if f.id not in selected_ids]

    def copy(self, ids):
        selected = self.selected(ids, editable=False)
        if not selected: return []
        origin = min(f.start for f in selected)
        return [dict(frame={**asdict(f), "start": f.start-origin}, override=asdict(self.frame_overrides.get(f.id, FrameOverride()))) for f in selected]

    def paste(self, clipboard, at, track_id="main", ripple=True):
        if not clipboard: return []
        track = next(t for t in self.track_layout if t.id == track_id)
        if track.locked: raise ValueError("A selected track is locked")
        at = max(0., at)
        duration = max(item['frame']['start']+item['frame']['duration'] for item in clipboard)
        if ripple:
            for frame in self.timeline_clips:
                if frame.track_id == track_id and frame.start >= at-1e-8:
                    frame.start += duration
        created = []
        for item in clipboard:
            frame = TimelineFrame(**{**item['frame'], "id": identifier(), "track_id": track_id, "start": at+item['frame']['start']})
            self.timeline_clips.append(frame)
            self.frame_overrides[frame.id] = FrameOverride(**item['override'])
            created.append(frame.id)
        self.copied_segments.append(dict(ids=created, start=at, track_id=track_id))
        return created

    def move(self, ids, at, track_id, ripple=True):
        selected = self.selected(ids)
        if not selected: return
        if next(t for t in self.track_layout if t.id == track_id).locked:
            raise ValueError("A selected track is locked")
        origin = min(f.start for f in selected)
        span = max(f.end for f in selected)-origin
        shifts = {f.id: f.start-origin for f in selected}
        if ripple:
            self.delete(ids, ripple=True)
            for frame in self.timeline_clips:
                if frame.track_id == track_id and frame.start >= at-1e-8:
                    frame.start += span
            self.timeline_clips.extend(selected)
        for frame in selected:
            frame.track_id = track_id
            frame.start = max(0., at)+shifts[frame.id]

    def reverse(self, ids):
        selected = self.selected(ids)
        for track in self.track_layout:
            group = [f for f in selected if f.track_id == track.id]
            slots = [(f.start, f.duration) for f in group]
            for frame, (start, duration) in zip(reversed(group), slots):
                frame.start, frame.duration = start, duration
                frame.reversed = not frame.reversed

    def offset(self, ids, x, y, relative=True):
        for frame in self.selected(ids):
            value = self.frame_overrides.setdefault(frame.id, FrameOverride())
            value.offset_x = value.offset_x+x if relative else x
            value.offset_y = value.offset_y+y if relative else y

    def mark_keyframes(self, ids, value=True):
        for frame in self.selected(ids):
            frame.keyframe = value

    def _range(self, ids):
        selected = self.selected(ids)
        if not selected or len({f.track_id for f in selected}) != 1:
            raise ValueError("Select a range on one track")
        selected_ids = {f.id for f in selected}
        start, end = selected[0].start, selected[-1].end
        if any(f.id not in selected_ids and start < f.start < end-1e-8 for f in self.frames(selected[0].track_id)):
            raise ValueError("Select a continuous range for retiming")
        return selected

    def retime_count(self, ids, target, fps, curve="linear", bezier=(.25, .1, .75, .9), keep_first=True, keep_last=True, keep_keys=True):
        selected = self._range(ids)
        protected = {i for i, f in enumerate(selected) if keep_keys and f.keyframe}
        if keep_first: protected.add(0)
        if keep_last: protected.add(len(selected)-1)
        indices = resample_indices(len(selected), target, curve, bezier, protected)
        at, track = selected[0].start, selected[0].track_id
        old_duration = sum(f.duration for f in selected)
        copied = self.copy([f.id for f in selected])
        self.delete(ids)
        clipboard = []
        for i, index in enumerate(indices):
            item = copy.deepcopy(copied[index])
            item['frame'].update(start=i/fps, duration=1/fps, curve=curve, speed=old_duration/(target/fps))
            clipboard.append(item)
        created = self.paste(clipboard, at, track)
        self.retime_segments.append(dict(ids=created, mode="count", target=target, curve=curve, bezier=list(bezier)))
        return created

    def retime_duration(self, ids, duration, curve="linear", bezier=(.25, .1, .75, .9)):
        selected = self._range(ids)
        if not math.isfinite(duration) or duration <= .0001:
            raise ValueError("Target duration must be positive")
        start, old_end = selected[0].start, selected[-1].end
        old_duration = sum(f.duration for f in selected)
        fractions = [0.]
        for frame in selected: fractions.append(fractions[-1]+frame.duration/old_duration)
        edges = [inverse_curve(value, curve, bezier)*duration for value in fractions]
        for i, frame in enumerate(selected):
            frame.start, frame.duration = start+edges[i], edges[i+1]-edges[i]
            frame.speed, frame.curve = old_duration/duration, curve
        chosen = {f.id for f in selected}
        delta = start+duration-old_end
        for frame in self.frames(selected[0].track_id):
            if frame.id not in chosen and frame.start >= old_end-1e-8:
                frame.start += delta
        self.retime_segments.append(dict(ids=list(chosen), mode="duration", target=duration, curve=curve, bezier=list(bezier)))

    def interpolate(self, ids, curve="linear", bezier=(.25, .1, .75, .9)):
        selected = self._range(ids)
        if len(selected) < 2: return
        anchors = sorted({0, len(selected)-1, *(i for i,f in enumerate(selected) if f.keyframe)})
        values = {i:asdict(self.frame_overrides.get(selected[i].id, FrameOverride())) for i in anchors}
        for left, right in zip(anchors, anchors[1:]):
            first, last = values[left], values[right]
            for i in range(left,right+1):
                amount = curve_value((i-left)/(right-left),curve,bezier)
                self.frame_overrides[selected[i].id] = FrameOverride(**{key:first[key]+(last[key]-first[key])*amount for key in first})



class EditHistory:
    """Snapshot history can include timeline, Root and alignment settings together."""
    def __init__(self, limit=80):
        self.entries, self.index, self.limit = [], 0, limit
        self.last_changed_fields=set()

    def record(self, before, after, label):
        if before == after: return
        del self.entries[self.index:]
        self.entries.append((copy.deepcopy(before), copy.deepcopy(after), label))
        self.entries = self.entries[-self.limit:]
        self.index = len(self.entries)

    def undo(self):
        if self.index == 0: return None
        self.index -= 1
        before,after,_=self.entries[self.index]
        self.last_changed_fields={k for k in before if before[k]!=after.get(k)}
        return copy.deepcopy(before)

    def redo(self):
        if self.index == len(self.entries): return None
        before,after,_=self.entries[self.index]
        self.last_changed_fields={k for k in before if before[k]!=after.get(k)}
        state = copy.deepcopy(after)
        self.index += 1
        return state
