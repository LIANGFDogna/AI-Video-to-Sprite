"""Resource removal lifecycle inside the Project Library (records only, never source files)."""
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from app.i18n import t
from app.models.character_reference import CharacterReference
from app.models.character_templates import BLANK, REGISTRY
from app.ui.dialogs import MessageBox
from test_group_workspace_ui import cached_clip, window
from test_workspace_ui import close_window, events, qt


def clip_with_source(w, group_id, name="Idle"):
    animation_id = cached_clip(w, group_id, name)
    animation = w.project.library.animation(animation_id)
    source = w.project.library.resources[animation.source_id]
    return animation_id, animation, source


def generated_sheet(library, animation_id):
    return next((row for row in library.resources.values()
        if row.kind == "GENERATED_SPRITE_SHEET" and row.animation_id == animation_id), None)


def menu_labels(panel, kind, ident):
    menu = panel.build_context_menu(kind, ident)
    labels = []
    for action in menu.actions():
        labels.append(action.text())
        if action.menu():
            labels.extend(sub.text() for sub in action.menu().actions())
    return labels


def test_resource_context_menu_has_remove(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        sheet = generated_sheet(w.project.library, animation_id)
        remove_label = t("Remove from Project")
        for kind, ident in (("RESOURCE", source.id), ("RESOURCE", animation.id), ("RESOURCE", sheet.id)):
            labels = menu_labels(w.library_panel, kind, ident)
            assert remove_label in labels
            assert t("Rename") in labels and t("Move to Group") in labels
            assert t("Show in Explorer") in labels
        assert t("Export") in menu_labels(w.library_panel, "RESOURCE", animation.id)
        assert t("Export") in menu_labels(w.library_panel, "RESOURCE", sheet.id)
    finally:
        close_window(qt, w)


def test_remove_source_does_not_delete_source_file(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        folder = Path(source.path)
        before = sorted(p.name for p in folder.iterdir())
        assert before
        c.remove_resource(source.id, confirmed=True)
        assert source.id not in w.project.library.resources
        assert folder.is_dir() and sorted(p.name for p in folder.iterdir()) == before
        assert animation_id in [row.animation_id for row in w.project.library.resources.values() if row.kind == "ANIMATION"]
        assert w.project.library.animation(animation_id).source_id is None
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_remove_source_keep_generated_animation(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        cache = w.cache_dir / "sprite_sheet.png"
        assert cache.is_file()
        c.remove_resource(source.id, confirmed=True)
        kept = w.project.library.animation(animation_id)
        assert kept is not None and kept.ready
        assert generated_sheet(w.project.library, animation_id) is not None
        assert w.project.library.groups[group.id].status == "READY"
        assert cache.is_file()
        w.project.library.validate()
    finally:
        close_window(qt, w)


def test_remove_source_with_related_results_prompt(qt, tmp_path, monkeypatch):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        seen = []
        monkeypatch.setattr(MessageBox, "choice", staticmethod(lambda *args, **kwargs: (seen.append(args[-2]), 2)[1]))
        assert c.remove_resource(source.id) is None
        assert seen and seen[0][0] == "Remove source only, keep generated results"
        assert seen[0][1] == "Remove related Animations and Sprite Sheets"
        assert source.id in w.project.library.resources
        monkeypatch.setattr(MessageBox, "choice", staticmethod(lambda *args, **kwargs: 0))
        c.remove_resource(source.id)
        assert source.id not in w.project.library.resources
        assert w.project.library.animation(animation_id) is not None
        w.project.library.validate()
    finally:
        close_window(qt, w)


def test_remove_source_cascade_removes_related_results(qt, tmp_path, monkeypatch):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        monkeypatch.setattr(MessageBox, "choice", staticmethod(lambda *args, **kwargs: 1))
        c.remove_resource(source.id)
        assert source.id not in w.project.library.resources
        assert w.project.library.animation(animation_id) is None
        assert generated_sheet(w.project.library, animation_id) is None
        assert not any(row.animation_id == animation_id for row in w.project.library.resources.values())
        w.project.library.validate()
    finally:
        close_window(qt, w)


def test_remove_animation(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        c.remove_resource(animation.id, confirmed=True)
        assert animation.id not in w.project.library.resources
        assert generated_sheet(w.project.library, animation_id) is None
        assert source.id not in w.project.library.resources
        assert Path(source.path).is_dir()
        assert w.project.library.groups[group.id].ui_state.animation_id is None
        assert not w.project.library.groups[group.id].animation_states
        w.project.library.validate()
    finally:
        close_window(qt, w)


def test_remove_sprite_sheet(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        image = tmp_path / "imported.png"
        Image.new("RGBA", (32, 32), (90, 120, 200, 160)).save(image)
        row = c.import_sheet(image)
        c.remove_resource(row.id, confirmed=True)
        assert row.id not in w.project.library.resources
        assert image.is_file()
        animation_id, animation, source = clip_with_source(w, group.id, "Idle2")
        sheet = generated_sheet(w.project.library, animation_id)
        cached = Path(sheet.path) if sheet.path else w.cache_dir / "sprite_sheet.png"
        c.remove_resource(sheet.id, confirmed=True)
        assert sheet.id not in w.project.library.resources
        assert (w.cache_dir / "sprite_sheet.png").is_file()
        assert w.project.library.animation(animation_id) is not None
        w.project.library.validate()
    finally:
        close_window(qt, w)


def test_remove_current_resource_clears_workspace(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        first = cached_clip(w, group.id, "First")
        second = cached_clip(w, group.id, "Second")
        c.select_animation(first)
        assert w.project.animation_id == first
        row = w.project.library.animation(first)
        c.remove_resource(row.id, confirmed=True)
        assert w.project.animation_id == second
        assert w.project.library.animation(first) is None
        assert w.last_error is None and not w.worker
        assert w.project.library.groups[group.id].status == "READY"
    finally:
        close_window(qt, w)


def test_remove_last_resource_makes_group_empty(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        c.remove_resource(animation.id, confirmed=True)
        assert w.project.library.groups[group.id].status == "EMPTY"
        assert w.project.library.animation(w.project.animation_id) is None
        assert not w.project.source_path and not w.built
        assert w.project.current_group_id == group.id
        assert w.views.currentWidget() is w.start_page
        assert w.library_panel.items[("GROUP", group.id)].text(1) == "0"
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_remove_reference_animation_requires_confirmation(qt, tmp_path, monkeypatch):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        hero = c.new_character(name="Hero", template_id=BLANK)
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        w.project.library.characters[hero.id].character_reference = CharacterReference(animation_id, 0, 12, 12, 24, 24)
        w.project.sync_character_reference()
        monkeypatch.setattr(MessageBox, "question", staticmethod(lambda *args, **kwargs: MessageBox.StandardButton.Cancel))
        assert c.remove_resource(animation.id) is None
        assert animation.id in w.project.library.resources
        assert w.project.library.characters[hero.id].character_reference is not None
    finally:
        close_window(qt, w)


def test_remove_reference_animation_clears_reference(qt, tmp_path, monkeypatch):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        hero = c.new_character(name="Hero", template_id=BLANK)
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        w.project.library.characters[hero.id].character_reference = CharacterReference(animation_id, 0, 12, 12, 24, 24)
        w.project.sync_character_reference()
        monkeypatch.setattr(MessageBox, "question", staticmethod(lambda *args, **kwargs: MessageBox.StandardButton.Yes))
        c.remove_resource(animation.id)
        assert w.project.library.characters[hero.id].character_reference is None
        assert animation.id not in w.project.library.resources
        w.project.library.validate()
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_remove_resource_save_reopen(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        folder = Path(source.path)
        c.remove_resource(source.id, confirmed=True)
        w.save_project();events(qt, lambda: not w.worker)
        path = w.project_file
        w.open_project(path)
        assert source.id not in w.project.library.resources
        assert w.project.library.animation(animation_id) is not None
        assert w.project.library.animation(animation_id).source_id is None
        assert folder.is_dir()
        assert w.library_panel.items.get(("RESOURCE", source.id)) is None
    finally:
        close_window(qt, w)


def test_remove_resource_does_not_affect_other_group(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        first = c.new_group(name="Idle")
        second = c.new_group(name="Run")
        first_animation = cached_clip(w, first.id, "Idle")
        second_animation = cached_clip(w, second.id, "Run")
        c.select_animation(second_animation)
        w.set_animation_offset(-12, 4)
        character_before = w.project.library.groups[second.id].character_id
        source = w.project.library.resources[w.project.library.animation(first_animation).source_id]
        c.remove_resource(source.id, confirmed=True)
        assert w.project.library.animation(second_animation) is not None
        assert w.project.select_animation(second_animation).animation_transform == type(w.project.animation_transform)(-12, 4)
        assert w.project.library.groups[second.id].character_id == character_before
        assert w.project.library.animation(second_animation) is not None
        assert w.project.library.animation(first_animation) is not None
        w.project.library.validate()
    finally:
        close_window(qt, w)


def test_remove_resource_undo_restores_records(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        group = c.new_group(name="Idle")
        animation_id, animation, source = clip_with_source(w, group.id)
        sheet = generated_sheet(w.project.library, animation_id)
        c.remove_resource(animation.id, confirmed=True)
        assert animation.id not in w.project.library.resources
        print('DEBUG entries', [(entry[0], entry[-1], entry[1].get('resources', {}).keys() == entry[2].get('resources', {}).keys()) for entry in c.entries], 'index', c.index)
        w.undo_edit();events(qt, lambda: not w.worker)
        print('DEBUG status', w.status.text())
        restored = w.project.library.animation(animation_id)
        assert animation.id in w.project.library.resources
        assert restored is not None and restored.source_id == source.id
        assert generated_sheet(w.project.library, animation_id) is not None
        assert w.project.library.groups[group.id].ui_state.animation_id == animation_id
        w.project.library.validate()
        assert w.last_error is None
    finally:
        close_window(qt, w)
