"""Phase 2E UI: node graph, transition inspector and parameter simulator for a Character State Machine."""
from __future__ import annotations
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QGraphicsItem, QGraphicsScene,
    QGraphicsView, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QCheckBox, QSpinBox, QSplitter, QVBoxLayout, QWidget)

from app.core.state_machine import MachineRuntime
from app.i18n import t
from app.models.state_machine import Condition, OPERATORS, PARAMETER_TYPES, StateParameter
from app.ui.animation_preview import AnimationPreview


class StateNodeItem(QGraphicsItem):
    """One State in the graph; drag moves the node and stores its position on release."""

    def __init__(self, state, panel, width=190., height=64.):
        super().__init__()
        self.state = state
        self.panel = panel
        self.width, self.height = width, height
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(QPointF(*state.position))
        self.setZValue(1)

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        active = self.panel.runtime is not None and self.panel.runtime.current == self.state.id
        label = self.panel.binding_label(self.state)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QColor("#2f4f6f") if active else QColor("#26313f")
        border = QColor("#7fd8ff") if active else QColor("#5a6b7d")
        painter.setBrush(QBrush(body))
        painter.setPen(QPen(border, 3 if active else 1))
        painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), 8, 8)
        painter.setPen(QPen(QColor("#f2f8ff")))
        font = QFont(); font.setBold(True); font.setPixelSize(13); painter.setFont(font)
        painter.drawText(QRectF(10, 8, self.width - 20, 20), Qt.AlignmentFlag.AlignLeft, self.state.name)
        font.setBold(False); font.setPixelSize(11); painter.setFont(font)
        painter.setPen(QPen(QColor("#bcd2e8")))
        painter.drawText(QRectF(10, 30, self.width - 20, 26), Qt.AlignmentFlag.AlignLeft,
            t("{kind}: {binding}", kind=t("Animation Set") if self.state.kind == "set" else t("Animation"), binding=label))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.state.position = (float(self.pos().x()), float(self.pos().y()))
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.panel.view is not None:
            self.panel.view.viewport().update()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.panel.positions_changed()


class StateMachineGraph(QGraphicsView):
    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setBackgroundBrush(QBrush(QColor("#1a2129")))
        self.setMinimumSize(420, 320)

    def rebuild(self, machine):
        self.scene().clear()
        self.panel.nodes = {}
        if machine is None:
            return
        for state in machine.states:
            item = StateNodeItem(state, self.panel)
            self.scene().addItem(item)
            self.panel.nodes[state.id] = item
        for transition in machine.transitions:
            source, target = self.panel.nodes.get(transition.from_state), self.panel.nodes.get(transition.to_state)
            if not source or not target:
                continue
            start = source.pos() + QPointF(source.width / 2, source.height)
            end = target.pos() + QPointF(target.width / 2, 0)
            item = self.scene().addLine(start.x(), start.y(), end.x(), end.y(),
                QPen(QColor("#ffca74") if transition.priority > 0 else QColor("#6f8296"), 2))
            item.setZValue(0)
        rect = self.scene().itemsBoundingRect().adjusted(-120, -120, 120, 120)
        self.scene().setSceneRect(rect)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.scale(1.1 if event.angleDelta().y() > 0 else 1 / 1.1)
            event.accept()
        else:
            super().wheelEvent(event)


class StateMachineDialog(QDialog):
    """Graph + inspector + simulator for the Character State Machines of the active Character."""

    def __init__(self, host, controller):
        super().__init__(host)
        self.host = host
        self.controller = controller
        self.runtime = None
        self.nodes = {}
        from app.ui.state_machine_panel import StateMachineGraph
        self.setWindowTitle(t("State Machine"))
        self.resize(1280, 820)
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        bar = QHBoxLayout()
        self.machine_box = QComboBox()
        self.machine_box.currentIndexChanged.connect(lambda index: self.select_machine(self.machine_box.itemData(index)))
        bar.addWidget(self.machine_box, 1)
        for label, callback in (("New State Machine", self.new_machine), ("From Template", self.from_template),
                                ("Remove", self.remove_machine), ("Export", self.export_machine)):
            button = QPushButton(t(label)); button.setAutoDefault(False); button.clicked.connect(callback)
            bar.addWidget(button)
        left.addLayout(bar)
        self.view = StateMachineGraph(self)
        left.addWidget(self.view, 3)
        state_row = QHBoxLayout()
        self.state_list = QListWidget(); self.state_list.setMaximumHeight(150)
        self.state_list.currentItemChanged.connect(lambda item, previous: self.select_state(item.data(0x0100) if item else None))
        state_row.addWidget(self.state_list, 1)
        state_buttons = QVBoxLayout()
        for label, callback in (("Add State", self.add_state), ("Remove State", self.remove_state),
                                ("Set Entry", self.set_entry), ("Play State", self.play_state)):
            button = QPushButton(t(label)); button.setAutoDefault(False); button.clicked.connect(callback)
            state_buttons.addWidget(button)
        state_buttons.addStretch()
        state_row.addLayout(state_buttons)
        left.addLayout(state_row, 1)
        root.addLayout(left, 3)
        right = QVBoxLayout()
        self.transition_group = QGroupBox(t("Transition Inspector"))
        inspector = QVBoxLayout(self.transition_group)
        pick = QHBoxLayout()
        self.from_box = QComboBox(); self.to_box = QComboBox()
        pick.addWidget(QLabel(t("From"))); pick.addWidget(self.from_box, 1)
        pick.addWidget(QLabel(t("To"))); pick.addWidget(self.to_box, 1)
        inspector.addLayout(pick)
        self.transition_list = QListWidget(); self.transition_list.setMaximumHeight(120)
        self.transition_list.currentItemChanged.connect(lambda item, previous: self.load_transition(item.data(0x0100) if item else None))
        inspector.addWidget(self.transition_list)
        self.condition_list = QListWidget(); self.condition_list.setMaximumHeight(110)
        inspector.addWidget(self.condition_list)
        condition_row = QHBoxLayout()
        self.condition_parameter = QComboBox()
        self.condition_operator = QComboBox()
        for operator in OPERATORS:
            self.condition_operator.addItem(operator, operator)
        self.condition_value = QLineEdit()
        for widget in (self.condition_parameter, self.condition_operator, self.condition_value):
            condition_row.addWidget(widget, 1)
        for label, callback in (("Add Condition", self.add_condition), ("Remove Condition", self.remove_condition)):
            button = QPushButton(t(label)); button.setAutoDefault(False); button.clicked.connect(callback)
            condition_row.addWidget(button)
        inspector.addLayout(condition_row)
        options = QHBoxLayout()
        self.priority = QSpinBox(); self.priority.setRange(-100, 100)
        self.exit_time = QDoubleSpinBox(); self.exit_time.setRange(0, 60); self.exit_time.setDecimals(2)
        self.interruptible = QCheckBox(t("Interruptible")); self.interruptible.setChecked(True)
        options.addWidget(QLabel(t("Priority"))); options.addWidget(self.priority)
        options.addWidget(QLabel(t("Exit Time"))); options.addWidget(self.exit_time)
        options.addWidget(self.interruptible)
        inspector.addLayout(options)
        transition_buttons = QHBoxLayout()
        for label, callback in (("Add Transition", self.add_transition), ("Remove Transition", self.remove_transition)):
            button = QPushButton(t(label)); button.setAutoDefault(False); button.clicked.connect(callback)
            transition_buttons.addWidget(button)
        inspector.addLayout(transition_buttons)
        right.addWidget(self.transition_group)
        self.simulator_group = QGroupBox(t("Preview Simulator"))
        simulator = QVBoxLayout(self.simulator_group)
        self.parameter_box = QComboBox()
        self.parameter_value = QLineEdit()
        parameter_row = QHBoxLayout()
        parameter_row.addWidget(self.parameter_box, 1); parameter_row.addWidget(self.parameter_value, 1)
        for label, callback in (("Set", self.set_parameter), ("Toggle", self.toggle_parameter),
                                ("Tick", self.tick), ("Force", self.force_tick)):
            button = QPushButton(t(label)); button.setAutoDefault(False); button.clicked.connect(callback)
            parameter_row.addWidget(button)
        simulator.addLayout(parameter_row)
        self.current_state = QLabel(); self.current_state.setObjectName("panelTitle")
        simulator.addWidget(self.current_state)
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True); self.log_view.setMaximumHeight(150)
        simulator.addWidget(self.log_view)
        simulator.addWidget(self.hint())
        right.addWidget(self.simulator_group, 1)
        root.addLayout(right, 2)
        self.refresh_machines()

    def hint(self):
        label = QLabel(t("Parameters drive the transitions; conditions are data only, never scripts."))
        label.setObjectName("muted"); label.setWordWrap(True)
        return label

    @property
    def machine(self):
        return self.host.project.library.state_machine(self.machine_box.currentData())

    def refresh_machines(self, select=None):
        character = self.host.project.active_character()
        current = select or self.machine_box.currentData()
        self.machine_box.blockSignals(True); self.machine_box.clear()
        if character is not None:
            for machine in self.host.project.library.state_machines_for(character.id):
                self.machine_box.addItem(machine.name, machine.id)
        index = self.machine_box.findData(current)
        self.machine_box.setCurrentIndex(index if index >= 0 else (0 if self.machine_box.count() else -1))
        self.machine_box.blockSignals(False)
        self.select_machine(self.machine_box.currentData())

    def select_machine(self, machine_id):
        machine = self.host.project.library.state_machine(machine_id)
        self.runtime = MachineRuntime(machine) if machine is not None else None
        self.view.rebuild(machine)
        self.refresh_states()
        self.refresh_transitions()
        self.refresh_parameters()
        self.refresh_runtime()

    def binding_label(self, state):
        library = self.host.project.library
        if state.kind == "set":
            row = library.animation_sets.get(state.set_id)
            return row.name if row else t("Not bound")
        row = library.animation(state.animation_id)
        return row.name if row else t("Not bound")

    def positions_changed(self):
        self.controller.save_state_positions(self.machine.id if self.machine else None)
        self.view.rebuild(self.machine)
        self.refresh_states()

    def refresh_states(self):
        machine = self.machine
        self.state_list.blockSignals(True); self.state_list.clear()
        if machine is not None:
            for state in machine.states:
                marker = "★ " if state.id == machine.entry_state else ""
                item = QListWidgetItem(f"{marker}{state.name}   ({self.binding_label(state)})")
                item.setData(0x0100, state.id)
                self.state_list.addItem(item)
        self.state_list.blockSignals(False)
        if self.state_list.count():
            self.state_list.setCurrentRow(0)

    def select_state(self, state_id):
        machine = self.machine
        if machine is None or state_id is None:
            return
        for box in (self.from_box, self.to_box):
            box.blockSignals(True)
            box.clear()
            for state in machine.states:
                box.addItem(state.name, state.id)
            box.blockSignals(False)
        index = self.from_box.findData(state_id)
        if index >= 0:
            self.from_box.setCurrentIndex(index)

    def refresh_transitions(self, select=None):
        machine = self.machine
        self.transition_list.blockSignals(True); self.transition_list.clear()
        if machine is not None:
            for row in machine.transitions:
                source = machine.state(row.from_state); target = machine.state(row.to_state)
                item = QListWidgetItem(f"{source.name if source else '?'} → {target.name if target else '?'}   [{row.describe()}]")
                item.setData(0x0100, row.id)
                self.transition_list.addItem(item)
        self.transition_list.blockSignals(False)
        if self.transition_list.count():
            self.transition_list.setCurrentRow(0)
        elif machine is not None:
            self.load_transition(None)

    def load_transition(self, transition_id):
        machine = self.machine
        self.condition_list.clear()
        if machine is None or transition_id is None:
            self.condition_parameter.clear()
            return
        row = machine.transition(transition_id)
        if row is None:
            return
        self.condition_parameter.blockSignals(True); self.condition_parameter.clear()
        for parameter in machine.parameters:
            self.condition_parameter.addItem(f"{parameter.name} ({parameter.type})", parameter.name)
        self.condition_parameter.blockSignals(False)
        for condition in row.conditions:
            self.condition_list.addItem(f"{condition.parameter} {condition.operator} {condition.value}")
        self.priority.blockSignals(True); self.priority.setValue(row.priority); self.priority.blockSignals(False)
        self.exit_time.blockSignals(True); self.exit_time.setValue(row.exit_time); self.exit_time.blockSignals(False)
        self.interruptible.blockSignals(True); self.interruptible.setChecked(row.interruptible); self.interruptible.blockSignals(False)
        index = self.from_box.findData(row.from_state)
        if index >= 0:
            self.from_box.setCurrentIndex(index)
        index = self.to_box.findData(row.to_state)
        if index >= 0:
            self.to_box.setCurrentIndex(index)

    def refresh_parameters(self):
        machine = self.machine
        self.parameter_box.clear()
        if machine is not None:
            for parameter in machine.parameters:
                self.parameter_box.addItem(f"{parameter.name} ({parameter.type})", parameter.name)

    def refresh_runtime(self):
        machine = self.machine
        if machine is None or self.runtime is None:
            self.current_state.setText(t("No State Machine selected."))
            return
        state = self.runtime.current_state
        self.current_state.setText(t("Current State: {name}", name=state.name if state else "-"))
        self.log_view.setPlainText("\n".join(
            t("{source} → {target}  ({reason})", source=machine.state(row.from_state).name if machine.state(row.from_state) else '?',
              target=machine.state(row.to_state).name if machine.state(row.to_state) else '?', reason=row.reason)
            for row in self.runtime.history[-40:]))
        self.view.viewport().update()

    def new_machine(self):
        machine = self.controller.new_state_machine()
        if machine is not None:
            self.refresh_machines(machine.id)

    def from_template(self):
        created = self.controller.template_state_machines()
        if created:
            self.refresh_machines(created[0][0].id)

    def remove_machine(self):
        machine = self.machine
        if machine is None:
            return
        self.controller.remove_state_machine(machine.id)
        self.refresh_machines()

    def export_machine(self):
        machine = self.machine
        if machine is not None:
            self.controller.export_state_machine(machine.id)

    def add_state(self):
        machine = self.machine
        if machine is None:
            return
        name, ok = QInputDialog.getText(self, t("Add State"), t("State name"), QLineEdit.EchoMode.Normal, t("New State"))
        if not ok:
            return
        kind, ok = QInputDialog.getItem(self, t("Add State"), t("State content"), [t("Animation"), t("Animation Set")], 0, False)
        if not ok:
            return
        content = self.controller.state_content_choices(kind == t("Animation Set"))
        if not content:
            return
        label, ok = QInputDialog.getItem(self, t("Add State"), t("State content"), [row[0] for row in content], 0, False)
        if not ok:
            return
        self.controller.add_state(machine.id, name, "set" if kind == t("Animation Set") else "animation", dict(content)[label])
        self.view.rebuild(self.machine)
        self.refresh_states()
        self.refresh_transitions()

    def remove_state(self):
        machine = self.machine
        item = self.state_list.currentItem()
        if machine is None or item is None:
            return
        self.controller.remove_state(machine.id, item.data(0x0100))
        self.view.rebuild(self.machine)
        self.refresh_states()
        self.refresh_transitions()

    def set_entry(self):
        machine = self.machine
        item = self.state_list.currentItem()
        if machine is None or item is None:
            return
        self.controller.set_entry_state(machine.id, item.data(0x0100))
        self.refresh_states()

    def play_state(self):
        machine = self.machine
        item = self.state_list.currentItem()
        if machine is None or item is None or self.host is None:
            return
        self.host.preview_state(self.machine.id, item.data(0x0100))

    def add_transition(self):
        machine = self.machine
        if machine is None:
            return
        self.controller.add_transition(machine.id, self.from_box.currentData(), self.to_box.currentData())
        self.refresh_transitions()

    def remove_transition(self):
        machine = self.machine
        item = self.transition_list.currentItem()
        if machine is None or item is None:
            return
        self.controller.remove_transition(machine.id, item.data(0x0100))
        self.refresh_transitions()

    def add_condition(self):
        machine = self.machine
        row = self.transition_list.currentItem()
        if machine is None or row is None or self.condition_parameter.currentData() is None:
            return
        self.controller.add_condition(machine.id, row.data(0x0100), self.condition_parameter.currentData(),
            self.condition_operator.currentData(), self.condition_value.text())
        self.load_transition(row.data(0x0100))

    def remove_condition(self):
        machine = self.machine
        row = self.transition_list.currentItem()
        item = self.condition_list.currentRow()
        if machine is None or row is None or item < 0:
            return
        self.controller.remove_condition(machine.id, row.data(0x0100), item)
        self.load_transition(row.data(0x0100))

    def set_parameter(self):
        name = self.parameter_box.currentData()
        if self.runtime is None or name is None:
            return
        self.runtime.set_parameter(name, self.parameter_value.text())
        self.refresh_runtime()

    def toggle_parameter(self):
        name = self.parameter_box.currentData()
        if self.runtime is None or name is None:
            return
        self.runtime.toggle(name)
        self.refresh_runtime()

    def tick(self):
        if self.runtime is None:
            return
        self.runtime.tick(0.0)
        self.refresh_runtime()

    def force_tick(self):
        "Fire a non-interruptible transition on purpose (preview only)."
        if self.runtime is None:
            return
        self.runtime.tick(0.0, force=True)
        self.refresh_runtime()
