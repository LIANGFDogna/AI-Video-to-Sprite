"""Central Character page: identity, counts and Character Reference entry points."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from app.i18n import t
from app.models.character_templates import REGISTRY


def character_label(character):
    if character is None:
        return ""
    if character.name == "Default Character":
        return t("Default Character")
    return character.name


class CharacterPanel(QWidget):
    def __init__(self, host, controller=None):
        super().__init__()
        self.host = host
        self.controller = controller
        self.character_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.addStretch()
        self.title = QLabel()
        self.title.setObjectName("panelTitle")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.meta = QLabel()
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)
        self.reference = QLabel()
        self.reference.setWordWrap(True)
        layout.addWidget(self.reference)
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        buttons = QHBoxLayout()
        self.set_reference = QPushButton(t("Set Character Reference"))
        self.edit_reference = QPushButton(t("Edit Character Reference"))
        for button in (self.set_reference, self.edit_reference):
            button.setAutoDefault(False)
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.set_reference.clicked.connect(self._open_reference)
        self.edit_reference.clicked.connect(self._open_reference)
        layout.addStretch()

    def _open_reference(self):
        if self.controller:
            self.controller.open_character_reference()

    def refresh(self, character=None):
        self.character_id = character.id if character else None
        if character is None:
            self.title.setText(t("Create a Character to group animations."))
            self.meta.clear()
            self.reference.clear()
            self.hint.setText(t("Character Reference, Groups and templates belong to a Character."))
            self.set_reference.setEnabled(False)
            self.edit_reference.setEnabled(False)
            return
        library = self.host.project.library
        template = REGISTRY.get(character.template_id) if character.template_id in REGISTRY.ids() else None
        self.title.setText(character_label(character))
        self.meta.setText(t("Template: {template}", template=t(template.label) if template else character.template_id)
            + "\n" + t("Groups: {groups}", groups=len(library.character_members(character.id)))
            + "\n" + t("Animations: {animations}", animations=library.character_animation_count(character.id)))
        reference = character.character_reference
        if reference is None:
            self.reference.setText(t("Character Reference: not established"))
        else:
            row = library.animation(reference.reference_animation_id)
            self.reference.setText(t("Character Reference: {animation} / Frame {frame}",
                animation=row.name if row else reference.reference_animation_id, frame=reference.reference_frame_index))
        self.hint.setText(t("This Character is a workspace container. Media still imports into a Group."))
        self.set_reference.setEnabled(not self.host.interaction_busy)
        self.edit_reference.setEnabled(bool(reference) and not self.host.interaction_busy)
        self.set_reference.setVisible(reference is None)
        self.edit_reference.setVisible(reference is not None)
