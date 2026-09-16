"""Phase 2E runtime: deterministic transition evaluation for previewing a State Machine."""
from __future__ import annotations
from dataclasses import dataclass

from app.core.final_frame_provider import FinalFrameProvider
from app.core.set_preview import SetPreviewProvider
from app.models.state_machine import coerce_value


@dataclass
class TransitionEvent:
    transition_id: str
    from_state: str
    to_state: str
    priority: int
    reason: str


class MachineRuntime:
    """Holds parameter values and evaluates transitions; no pixel work happens here."""

    def __init__(self, machine):
        self.machine = machine
        self.values = {row.name: coerce_value(row.type, row.default) for row in machine.parameters}
        self.current = machine.entry_state
        self.history: list[TransitionEvent] = []
        self.state_time = 0.0

    @property
    def current_state(self):
        return self.machine.state(self.current)

    def parameter(self, name):
        return self.machine.parameter(name)

    def set_parameter(self, name, value):
        row = self.parameter(name)
        if row is None:
            raise ValueError("State Machine condition uses an unknown parameter")
        self.values[name] = coerce_value(row.type, value)
        return self.values[name]

    def toggle(self, name):
        row = self.parameter(name)
        if row is None:
            raise ValueError("State Machine condition uses an unknown parameter")
        if row.type == "bool":
            return self.set_parameter(name, not self.values[name])
        if row.type == "trigger":
            return self.set_parameter(name, True)
        raise ValueError("Only bool or trigger parameters can be toggled")

    def candidates(self):
        "Satisfied transitions from the current state, best first (priority, then declaration order)."
        if self.current is None:
            return []
        rows = self.machine.transitions_from(self.current)
        satisfied = [(index, row) for index, row in enumerate(rows) if row.satisfied(self.values)]
        satisfied.sort(key=lambda pair: (-pair[1].priority, pair[0]))
        return [row for _, row in satisfied]

    def tick(self, dt=0.0, force=False):
        "Apply at most one transition per tick. Non-interruptible edges need an explicit force."
        self.state_time += max(0.0, float(dt))
        for row in self.candidates():
            if not row.interruptible and not force:
                continue
            if self.state_time < row.exit_time:
                continue
            event = TransitionEvent(row.id, row.from_state, row.to_state, row.priority, row.describe())
            self.current = row.to_state
            self.state_time = 0.0
            self.history.append(event)
            self.consume_triggers()
            return event
        return None

    def consume_triggers(self):
        for row in self.machine.parameters:
            if row.type == "trigger":
                self.values[row.name] = False

    def force_state(self, state_id):
        if state_id is not None and self.machine.state(state_id) is None:
            raise ValueError("Invalid State Machine state")
        self.current = state_id
        self.state_time = 0.0
        self.consume_triggers()
        return self.current


def state_provider(project, project_file, machine, state_id):
    "Resolve one State to a FinalFrameProvider (Animation) or SetPreviewProvider (Animation Set)."
    state = machine.state(state_id)
    if state is None:
        raise ValueError("Invalid State Machine state")
    if state.kind == "set":
        animation_set = project.library.animation_sets.get(state.set_id)
        if animation_set is None:
            raise ValueError("Animation Set does not exist")
        return SetPreviewProvider(project, project_file, animation_set)
    owner = project.library.animation(state.animation_id)
    if owner is None:
        raise ValueError("Resource does not exist")
    from app.utils.paths import cache_directory
    animation = project.select_animation(state.animation_id)
    return FinalFrameProvider(animation, cache_directory(project.project_id, project_file, state.animation_id), live_edit=True)
