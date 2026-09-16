"""Character creation dialog: name plus a template preview driven by the registry."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPlainTextEdit, QPushButton)
from app.i18n import t
from app.models.character_templates import BLANK


class CharacterDialog(QDialog):
    def __init__(self, host, registry, initial=BLANK, name=""):
        super().__init__(host)
        self.registry = registry
        self.setWindowTitle(t("New Character"))
        self.resize(520, 430)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("Character name")))
        self.name = QLineEdit(name)
        self.name.setPlaceholderText(t("Character name"))
        layout.addWidget(self.name)
        layout.addWidget(QLabel(t("Character template")))
        self.template = QComboBox()
        for entry in registry.templates():
            self.template.addItem(t(entry.label), entry.id)
        index = self.template.findData(initial)
        self.template.setCurrentIndex(max(0, index))
        layout.addWidget(self.template)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)
        row = QHBoxLayout()
        self.cancel = QPushButton(t("Cancel"))
        self.cancel.clicked.connect(self.reject)
        self.create = QPushButton(t("Create Character"))
        self.create.setObjectName("primary")
        self.create.clicked.connect(self.accept)
        for button in (self.cancel, self.create):
            button.setAutoDefault(False)
            row.addWidget(button)
        layout.addLayout(row)
        self.template.currentIndexChanged.connect(self._refresh)
        self.name.textChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self, *args):
        template = self.registry.get(self.template.currentData())
        if template.id == BLANK:
            self.preview.setPlainText(t("This Character starts empty. Create Groups yourself."))
        else:
            self.preview.setPlainText(t("Will create:") + "\n\n" + "\n".join(template.top_level))
        self.create.setEnabled(bool(self.name.text().strip()))

    def character_name(self):
        return self.name.text().strip()

    def template_id(self):
        return self.template.currentData()
