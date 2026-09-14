from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget
from app.i18n import t


class SliderField(QWidget):
    value_changed = Signal(float)

    def __init__(self, minimum, maximum, step=1, parent=None):
        super().__init__(parent)
        self.step = step
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(round(minimum / step), round(maximum / step))
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(0 if step == 1 else (1 if step == 0.1 else 2))
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setFixedWidth(76)
        self.slider.valueChanged.connect(self._slider_changed)
        self.spin.valueChanged.connect(self._spin_changed)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)

    def _slider_changed(self, value):
        self.spin.setValue(value * self.step)

    def _spin_changed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round(value / self.step))
        self.slider.blockSignals(False)
        self.value_changed.emit(value)

    def set_value(self, value):
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)
        self.slider.blockSignals(True)
        self.slider.setValue(round(value / self.step))
        self.slider.blockSignals(False)


class ParameterPanel(QWidget):
    changed = Signal(str, object)
    action = Signal(str)

    def __init__(self, title, description, parent=None):
        super().__init__(parent)
        self.fields = {}
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 16, 16, 16)
        heading = QLabel(t(title))
        heading.setObjectName("panelTitle")
        self.layout.addWidget(heading)
        self.description = QLabel(t(description))
        self.description.setWordWrap(True)
        self.description.setObjectName("muted")
        self.layout.addWidget(self.description)
        self.form = QFormLayout()
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.form.setVerticalSpacing(9)
        self.layout.addLayout(self.form)

    def slider(self, key, label, minimum, maximum, step=1):
        control = SliderField(minimum, maximum, step)
        control.value_changed.connect(lambda value: self.changed.emit(key, value))
        self.form.addRow(t(label), control)
        control.setToolTip(t("tooltip." + key))
        self.fields[key] = control
        return control

    def combo(self, key, label, choices):
        control = QComboBox()
        for value in choices:
            control.addItem(t(str(value)), str(value))
            if key == "alignment_mode":
                control.setItemData(control.count()-1, t("tooltip.option."+str(value)), Qt.ItemDataRole.ToolTipRole)
        control.currentIndexChanged.connect(lambda _: self.changed.emit(key, control.currentData()))
        self.form.addRow(t(label), control)
        control.setToolTip(t("tooltip." + key))
        self.fields[key] = control
        return control

    def integer(self, key, label, minimum, maximum):
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.valueChanged.connect(lambda value: self.changed.emit(key, value))
        self.form.addRow(t(label), control)
        control.setToolTip(t("tooltip." + key))
        self.fields[key] = control
        return control

    def decimal(self, key, label, minimum, maximum, decimals=3):
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(decimals)
        control.valueChanged.connect(lambda value: self.changed.emit(key, value))
        self.form.addRow(t(label), control)
        control.setToolTip(t("tooltip." + key))
        self.fields[key] = control
        return control

    def text(self, key, label):
        control = QLineEdit()
        control.textEdited.connect(lambda value: self.changed.emit(key, value))
        self.form.addRow(t(label), control)
        control.setToolTip(t("tooltip." + key))
        self.fields[key] = control
        return control

    def check(self, key, label):
        control = QCheckBox(t(label))
        control.setToolTip(t("tooltip." + key))
        control.toggled.connect(lambda value: self.changed.emit(key, value))
        self.form.addRow(control)
        self.fields[key] = control
        return control

    def button(self, action, label, primary=False):
        button = QPushButton(t(label))
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(lambda: self.action.emit(action))
        self.layout.addWidget(button)
        return button

    def note(self, text):
        label = QLabel(t(text))
        label.setWordWrap(True)
        label.setObjectName("muted")
        self.layout.addWidget(label)
        return label

    def finish(self):
        self.layout.addStretch()

    def set_values(self, values):
        for key, control in self.fields.items():
            value = values[key]
            control.blockSignals(True)
            if isinstance(control, SliderField):
                control.set_value(value)
            elif isinstance(control, QComboBox):
                control.setCurrentIndex(control.findData(str(value)))
            elif isinstance(control, QCheckBox):
                control.setChecked(bool(value))
            elif isinstance(control, QLineEdit):
                control.setText(str(value))
            else:
                control.setValue(value)
            control.blockSignals(False)
