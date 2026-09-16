"""Phase 2E: Character State Machines. Conditions are structured data only, never expressions."""
from __future__ import annotations
from dataclasses import dataclass, field
import math

from app.models.ids import new_id, now_stamp, valid_id

STATE_KINDS = ("animation", "set")
PARAMETER_TYPES = ("bool", "float", "int", "trigger")
OPERATORS = ("==", "!=", ">", ">=", "<", "<=")


def coerce_value(kind, value):
    "Convert a user/JSON value to the declared parameter type."
    if kind == "bool":
        return bool(value)
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    return bool(value)  # trigger


@dataclass
class StateParameter:
    name: str
    type: str = "float"
    default: object = 0

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Invalid State Machine parameter")
        if self.type not in PARAMETER_TYPES:
            raise ValueError("Invalid State Machine parameter")
        self.default = coerce_value(self.type, self.default)
        return self


@dataclass
class Condition:
    parameter: str
    operator: str = "=="
    value: object = 0

    def validate(self, parameter_types):
        if self.parameter not in parameter_types:
            raise ValueError("State Machine condition uses an unknown parameter")
        if self.operator not in OPERATORS:
            raise ValueError("State Machine condition uses an unsupported operator")
        return self

    def matches(self, values):
        if self.parameter not in values:
            return False
        left, right = values[self.parameter], self.value
        try:
            if self.operator == "==":
                return left == right or (isinstance(left, float) and isinstance(right, (int, float)) and math.isclose(left, right))
            if self.operator == "!=":
                return not self.matches_comparison(left, right)
            if self.operator == ">":
                return left > right
            if self.operator == ">=":
                return left >= right
            if self.operator == "<":
                return left < right
            if self.operator == "<=":
                return left <= right
        except TypeError:
            return False
        return False

    def matches_comparison(self, left, right):
        if isinstance(left, float) and isinstance(right, (int, float)):
            return math.isclose(left, right)
        return left == right


@dataclass
class Transition:
    from_state: str
    to_state: str
    id: str = field(default_factory=new_id)
    conditions: list[Condition] = field(default_factory=list)
    priority: int = 0
    exit_time: float = 0.0
    interruptible: bool = True

    def validate(self, state_ids, parameter_types):
        if not valid_id(self.id) or self.from_state not in state_ids or self.to_state not in state_ids:
            raise ValueError("Invalid State Machine transition")
        if not isinstance(self.priority, int):
            raise ValueError("Invalid State Machine transition")
        if not isinstance(self.exit_time, (int, float)) or self.exit_time < 0 or self.exit_time > 60:
            raise ValueError("Invalid State Machine transition")
        for condition in self.conditions:
            condition.validate(parameter_types)
        return self

    def satisfied(self, values):
        return all(condition.matches(values) for condition in self.conditions)

    def describe(self):
        if not self.conditions:
            return "always"
        return " and ".join(f"{c.parameter} {c.operator} {c.value}" for c in self.conditions)


@dataclass
class State:
    name: str
    id: str = field(default_factory=new_id)
    kind: str = "animation"
    animation_id: str | None = None
    set_id: str | None = None
    position: tuple[float, float] = (0.0, 0.0)
    loop: bool = True

    @property
    def binding_id(self):
        return self.animation_id if self.kind == "animation" else self.set_id

    def validate(self):
        if not valid_id(self.id) or not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Invalid State Machine state")
        if self.kind not in STATE_KINDS:
            raise ValueError("Invalid State Machine state")
        if self.kind == "animation" and not self.animation_id:
            raise ValueError("Invalid State Machine state")
        if self.kind == "set" and not self.set_id:
            raise ValueError("Invalid State Machine state")
        if not (isinstance(self.position, (list, tuple)) and len(self.position) == 2):
            raise ValueError("Invalid State Machine state")
        self.position = (float(self.position[0]), float(self.position[1]))
        return self


@dataclass
class StateMachine:
    name: str
    character_id: str
    id: str = field(default_factory=new_id)
    states: list[State] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    parameters: list[StateParameter] = field(default_factory=list)
    entry_state: str | None = None
    created_at: str = field(default_factory=now_stamp)
    modified_at: str = field(default_factory=now_stamp)

    def state(self, ident):
        return next((row for row in self.states if row.id == ident), None)

    def state_by_name(self, name):
        return next((row for row in self.states if row.name == name), None)

    def parameter(self, name):
        return next((row for row in self.parameters if row.name == name), None)

    def transition(self, ident):
        return next((row for row in self.transitions if row.id == ident), None)

    def transitions_from(self, state_id):
        return [row for row in self.transitions if row.from_state == state_id]

    def bound_animation_ids(self):
        return {row.animation_id for row in self.states if row.kind == "animation" and row.animation_id}

    def bound_set_ids(self):
        return {row.set_id for row in self.states if row.kind == "set" and row.set_id}

    def clear_animation(self, animation_id):
        "Animation referenced directly; the state is removed because a state must play something."
        removed = [row for row in self.states if row.kind == "animation" and row.animation_id == animation_id]
        for row in removed:
            self.remove_state(row.id)
        return removed

    def clear_set(self, set_id):
        removed = [row for row in self.states if row.kind == "set" and row.set_id == set_id]
        for row in removed:
            self.remove_state(row.id)
        return removed

    def remove_state(self, state_id):
        self.states = [row for row in self.states if row.id != state_id]
        self.transitions = [row for row in self.transitions if state_id not in (row.from_state, row.to_state)]
        if self.entry_state == state_id:
            self.entry_state = self.states[0].id if self.states else None
        self.modified_at = now_stamp()

    def add_state(self, name, kind="animation", animation_id=None, set_id=None, position=(0.0, 0.0), loop=True, unique=True):
        if unique:
            name = unique_state_name(name, [row.name for row in self.states])
        row = State(name, kind=kind, animation_id=animation_id, set_id=set_id, position=tuple(position), loop=loop)
        self.states.append(row)
        if self.entry_state is None:
            self.entry_state = row.id
        self.modified_at = now_stamp()
        return row

    def add_transition(self, from_state, to_state, conditions=(), priority=0, exit_time=0.0, interruptible=True):
        row = Transition(from_state, to_state, conditions=[c if isinstance(c, Condition) else Condition(**c) for c in conditions],
            priority=priority, exit_time=exit_time, interruptible=interruptible)
        self.transitions.append(row)
        self.modified_at = now_stamp()
        return row

    def remove_transition(self, ident):
        row = self.transition(ident)
        if row is None:
            raise ValueError("State Machine transition does not exist")
        self.transitions.remove(row)
        self.modified_at = now_stamp()
        return row

    def validate(self):
        if not valid_id(self.id) or not isinstance(self.name, str) or not self.name.strip() or not valid_id(self.character_id):
            raise ValueError("Invalid State Machine")
        identifiers = [row.id for row in self.states]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("State Machine states must be unique")
        names = [row.name.casefold() for row in self.states]
        if len(names) != len(set(names)):
            raise ValueError("State Machine state names must be unique")
        for row in self.states:
            row.validate()
        parameter_names = [row.name for row in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError("State Machine parameters must be unique")
        for row in self.parameters:
            row.validate()
        parameter_types = {row.name: row for row in self.parameters}
        transitions = [row.id for row in self.transitions]
        if len(transitions) != len(set(transitions)):
            raise ValueError("State Machine transitions must be unique")
        for row in self.transitions:
            row.validate(set(identifiers), parameter_types)
        if self.entry_state is not None and self.entry_state not in set(identifiers):
            raise ValueError("State Machine entry state does not exist")
        return self


def unique_state_name(name, existing):
    taken = {value.casefold() for value in existing}
    if name.strip().casefold() not in taken:
        return name.strip()
    number = 2
    while f"{name} {number}".casefold() in taken:
        number += 1
    return f"{name} {number}"
