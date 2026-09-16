"""Central Character page: identity, counts and Character Reference entry points."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QListWidget, QListWidgetItem, QPlainTextEdit)
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
        sets_group=QGroupBox(t('Animation Sets'))
        sets_layout=QVBoxLayout(sets_group)
        self.sets_list=QListWidget();self.sets_list.setMaximumHeight(132)
        self.sets_list.currentItemChanged.connect(lambda item,previous:self.show_set(item.data(0x0100) if item else None))
        sets_layout.addWidget(self.sets_list)
        self.set_slots=QPlainTextEdit();self.set_slots.setReadOnly(True);self.set_slots.setMaximumHeight(120)
        sets_layout.addWidget(self.set_slots)
        first=QHBoxLayout()
        for label,callback in (('New Animation Set',lambda:self.controller and self.controller.new_animation_set()),
                               ('Sets From Template',lambda:self.controller and self.controller.template_animation_sets()),
                               ('Auto Match',lambda:self.controller and self.controller.auto_match_animation_set(self.selected_set()))):
            first.addWidget(self._set_button(label,callback))
        sets_layout.addLayout(first)
        second=QHBoxLayout()
        for label,callback in (('Bind Animation',lambda:self.controller and self.controller.bind_slot_dialog(self.selected_set())),
                               ('Clear Binding',lambda:self.controller and self.controller.clear_slot_dialog(self.selected_set())),
                               ('Preview Set',lambda:self.controller and self.controller.preview_animation_set(self.selected_set())),
                               ('Export Set',lambda:self.controller and self.controller.export_animation_set(self.selected_set())),
                               ('Remove Set',lambda:self.controller and self.controller.remove_animation_set(self.selected_set()))):
            second.addWidget(self._set_button(label,callback))
        sets_layout.addLayout(second)
        layout.addWidget(sets_group)
        layout.addStretch()

    def _set_button(self,label,callback):
        button=QPushButton(t(label));button.setAutoDefault(False);button.clicked.connect(callback)
        return button

    def selected_set(self):
        item=self.sets_list.currentItem()
        return item.data(0x0100) if item else None

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
        self.refresh_sets(character)

    def refresh_sets(self,character=None):
        self.sets_list.blockSignals(True);self.sets_list.clear()
        if character is None:
            self.set_slots.setPlainText('')
        else:
            library=self.host.project.library
            for row in library.animation_sets_for(character.id):
                bound,total=row.completion
                mark='✓' if row.status=='READY' else '⚠' if row.status=='INCOMPLETE' else '○'
                item=QListWidgetItem(f'{row.name}   {bound}/{total}  {mark}')
                item.setData(0x0100,row.id)
                if row.missing_required:
                    item.setToolTip(t('Missing: {slots}',slots=', '.join(slot.display_name for slot in row.missing_required)))
                self.sets_list.addItem(item)
        self.sets_list.blockSignals(False)
        if self.sets_list.count():
            self.sets_list.setCurrentRow(0);self.show_set(self.sets_list.item(0).data(0x0100))
        else:
            self.set_slots.setPlainText(t('No Animation Sets yet. Create one or use the template.'))

    def show_set(self,set_id):
        row=self.host.project.library.animation_sets.get(set_id) if set_id else None
        if row is None:
            self.set_slots.setPlainText('')
            return
        library=self.host.project.library
        lines=[f"{row.name}  ({row.semantic_type or 'custom'})  {row.status}  {row.completion[0]}/{row.completion[1]}"]
        for slot in row.slots:
            animation=library.animation(slot.animation_id) if slot.animation_id else None
            mark='✓' if animation else ('⚠' if slot.required else '○')
            suffix=f" x{slot.repeat_count}" if slot.repeat_count>1 else ''
            lines.append(f"  {mark} {slot.display_name}{suffix}  {animation.name if animation else t('Not bound')}")
        if row.pre_animation or row.post_animation:
            pre=library.animation(row.pre_animation).name if row.pre_animation else '-'
            post=library.animation(row.post_animation).name if row.post_animation else '-'
            lines.append(t('Preview context: {pre} -> ... -> {post}',pre=pre,post=post))
        if row.missing_required:
            lines.append(t('Missing: {slots}',slots=', '.join(slot.display_name for slot in row.missing_required)))
        self.set_slots.setPlainText('\n'.join(lines))
