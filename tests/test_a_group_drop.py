"""Phase 2F Part A: Group drop zones, arbitrary order, nesting and safe deletion."""
import json

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage, QPainter
from PySide6.QtWidgets import QAbstractItemView

from PySide6.QtWidgets import QApplication

from app.ui.dialogs import MessageBox
from app.ui.project_library import MIME, ROLE
from test_group_workspace_ui import cached_clip, window
from test_workspace_ui import close_window, events, qt


ZONES = {'above': QAbstractItemView.DropIndicatorPosition.AboveItem,
         'on': QAbstractItemView.DropIndicatorPosition.OnItem,
         'below': QAbstractItemView.DropIndicatorPosition.BelowItem}


def tree_item(w, kind, ident):
    return w.library_panel.items[(kind, ident)]


def live_item(w, kind, ident):
    "Rows are rebuilt on every refresh, so re-read and verify the hit test each time."
    tree = w.library_panel.tree
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
        item = w.library_panel.items.get((kind, ident))
        assert item is not None, f'row {kind}/{ident} is missing from the tree'
        tree.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
        app.processEvents()
        rect = tree.visualItemRect(item)
        if rect.height() > 0 and tree.itemAt(rect.center()) is item:
            return item, rect
    raise AssertionError(f'row {kind}/{ident} cannot be hit-tested')


def drop_position(w, kind, ident, zone):
    item, rect = live_item(w, kind, ident)
    if zone == 'above':
        return QPointF(rect.left() + 5, rect.top() + 1)
    if zone == 'below':
        return QPointF(rect.left() + 5, max(rect.top() + 1, rect.bottom() - 1))
    return QPointF(rect.center())


def drop_group(w, dragged_id, target, zone, allowed=True):
    "Send real Qt drag/drop events so the drop zone logic itself is what runs."
    tree = w.library_panel.tree
    kind, ident = target.data(0, ROLE)
    position = drop_position(w, kind, ident, zone)
    data = QMimeData()
    data.setData(MIME, json.dumps(['GROUP', dragged_id]).encode())
    tree.dragEnterEvent(QDragEnterEvent(position.toPoint(), Qt.DropAction.MoveAction, data,
                                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    move = QDragMoveEvent(position.toPoint(), Qt.DropAction.MoveAction, data,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dragMoveEvent(move)
    if allowed:
        assert tree.drop_zone == (kind, ident, zone), tree.drop_zone
    else:
        assert tree.drop_zone is None, tree.drop_zone
    drop = QDropEvent(position, Qt.DropAction.MoveAction, data,
                      Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(drop)
    return drop.isAccepted()


def siblings(w, parent_id, character_id=None):
    "Top-level rows are scoped per Character; pass the owner explicitly."
    return [row.name for row in w.project.library.ordered_children(parent_id, character_id)]


def nested_window(qt, tmp_path):
    "Player -> Movement / Jump / Combat, matching the acceptance tree."
    w = window(qt, tmp_path)
    c = w.library_controller
    character = c.new_character(template_id='blank', name='Player')
    movement = c.new_group(name='Movement', character_id=character.id)
    jump = c.new_group(name='Jump', character_id=character.id)
    combat = c.new_group(name='Combat', character_id=character.id)
    return w, c, character, {'movement': movement, 'jump': jump, 'combat': combat}


def render_tree(w):
    tree = w.library_panel.tree
    tree.expandAll()
    tree.verticalScrollBar().setValue(0)
    tree.horizontalScrollBar().setValue(0)
    image = QImage(tree.viewport().size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    tree.viewport().render(painter, QPoint(0, 0))
    painter.end()
    rows = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, :image.width()].copy()


def test_group_reorder_up(qt, tmp_path):
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        assert siblings(w, None, character.id) == ['Movement', 'Jump', 'Combat']
        assert drop_group(w, groups['combat'].id, tree_item(w, 'GROUP', groups['movement'].id), 'above')
        assert siblings(w, None, character.id) == ['Combat', 'Movement', 'Jump']
    finally:
        close_window(qt, w)


def test_group_reorder_down(qt, tmp_path):
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        assert drop_group(w, groups['movement'].id, tree_item(w, 'GROUP', groups['combat'].id), 'below')
        assert siblings(w, None, character.id) == ['Jump', 'Combat', 'Movement']
    finally:
        close_window(qt, w)


def test_group_nest(qt, tmp_path):
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        assert drop_group(w, groups['combat'].id, tree_item(w, 'GROUP', groups['movement'].id), 'on')
        library = w.project.library
        assert library.groups[groups['combat'].id].parent_id == groups['movement'].id
        assert [g.name for g in library.children(groups['movement'].id)] == ['Combat']
        assert siblings(w, None, character.id) == ['Movement', 'Jump']
        assert drop_group(w, groups['jump'].id, tree_item(w, 'GROUP', groups['combat'].id), 'on')
        assert [g.name for g in library.children(groups['combat'].id)] == ['Jump']
        assert [g.name for g in library.children(groups['movement'].id)] == ['Combat']
        assert all(library.groups[g.id].character_id == character.id for g in (groups['movement'], groups['jump']))
    finally:
        close_window(qt, w)


def test_group_unnest(qt, tmp_path):
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        library = w.project.library
        assert drop_group(w, groups['combat'].id, tree_item(w, 'GROUP', groups['movement'].id), 'on')
        library.move_group(groups['jump'].id, groups['movement'].id)
        c.select_group(None)
        library = w.project.library
        assert drop_group(w, groups['jump'].id, tree_item(w, 'CHARACTER', character.id), 'on')
        library = w.project.library
        assert library.groups[groups['jump'].id].parent_id is None
        assert library.groups[groups['jump'].id].character_id == character.id
        assert [row.name for row in library.ordered_children(None, character.id)] == ['Movement', 'Jump']
        assert [row.name for row in library.children(groups['movement'].id)] == ['Combat']
    finally:
        close_window(qt, w)


def test_group_drop_to_character_root(qt, tmp_path):
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        library = w.project.library
        enemy = c.new_character(template_id='blank', name='Enemy')
        c.move('GROUP', groups['combat'].id, groups['movement'].id)
        assert library.groups[groups['combat'].id].parent_id == groups['movement'].id
        assert drop_group(w, groups['combat'].id, tree_item(w, 'CHARACTER', enemy.id), 'on')
        row = library.groups[groups['combat'].id]
        assert row.character_id == enemy.id and row.parent_id is None
        assert library.character_roots(enemy.id)[0].id == groups['combat'].id
        assert library.groups[groups['movement'].id].character_id == character.id
        assert row.alignment_review_required
    finally:
        close_window(qt, w)


def test_group_drop_to_loose(qt, tmp_path):
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        library = w.project.library
        assert drop_group(w, groups['jump'].id, tree_item(w, 'LOOSE', None), 'on')
        row = library.groups[groups['jump'].id]
        assert row.character_id is None and row.parent_id is None
        assert [g.name for g in library.loose_roots()] == ['Jump']
        assert library.groups[groups['movement'].id].character_id == character.id
    finally:
        close_window(qt, w)


def test_group_cycle_rejected(qt, tmp_path):
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        library = w.project.library
        assert drop_group(w, groups['jump'].id, tree_item(w, 'GROUP', groups['movement'].id), 'on')
        before = {ident: (row.parent_id, row.order) for ident, row in library.groups.items()}
        assert not drop_group(w, groups['movement'].id, tree_item(w, 'GROUP', groups['jump'].id), 'on', allowed=False)
        assert {ident: (row.parent_id, row.order) for ident, row in library.groups.items()} == before
        with pytest.raises(ValueError):
            library.move_group(groups['movement'].id, groups['jump'].id)
        library.groups[groups['movement'].id].parent_id = groups['jump'].id
        with pytest.raises(ValueError):
            library.validate()
    finally:
        close_window(qt, w)


def test_delete_leaf_child_only(qt, tmp_path):
    "Jump -> JumpUp / FallLoop / Land: removing FallLoop keeps Jump, JumpUp and Land."
    w = window(qt, tmp_path)
    c = w.library_controller
    try:
        jump = c.new_group(name='Jump')
        jump_up = c.new_group(name='JumpUp')
        fall = c.new_group(name='FallLoop')
        land = c.new_group(name='Land')
        library = w.project.library
        for child in (jump_up, fall, land):
            library.move_group(child.id, jump.id)
        c.refresh()
        c.remove_group(fall.id, confirmed=True)
        library = w.project.library
        assert jump.id in library.groups and fall.id not in library.groups
        assert [row.name for row in library.children(jump.id)] == ['JumpUp', 'Land']
        assert library.groups[jump_up.id].parent_id == jump.id and library.groups[land.id].parent_id == jump.id
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_delete_child_keeps_parent(qt, tmp_path):
    w = window(qt, tmp_path)
    c = w.library_controller
    try:
        parent = c.new_group(name='Movement')
        child = c.new_group(name='Walk')
        w.project.library.move_group(child.id, parent.id)
        c.select_group(parent.id)
        c.remove_group(child.id, confirmed=True)
        assert parent.id in w.project.library.groups
        assert not w.project.library.children(parent.id)
        assert w.project.current_group_id == parent.id
    finally:
        close_window(qt, w)


def test_delete_child_keeps_siblings(qt, tmp_path):
    w = window(qt, tmp_path)
    c = w.library_controller
    try:
        layout = c.new_group(name='Movement')
        walk = c.new_group(name='Walk')
        run = c.new_group(name='Run')
        sprint = c.new_group(name='Sprint')
        for child in (walk, run, sprint):
            w.project.library.move_group(child.id, layout.id)
        c.refresh()
        c.remove_group(run.id, confirmed=True)
        names = [row.name for row in w.project.library.children(layout.id)]
        assert names == ['Walk', 'Sprint']
        assert all(row.id in w.project.library.groups for row in (layout, walk, sprint))
    finally:
        close_window(qt, w)


def test_delete_parent_promote_children(qt, tmp_path):
    "The default answer promotes child Groups and keeps every resource inside."
    w = window(qt, tmp_path)
    c = w.library_controller
    try:
        root = c.new_group(name='Root')
        movement = c.new_group(name='Movement')
        w.project.library.move_group(movement.id, root.id)
        animation_id = cached_clip(w, movement.id, 'Walk', count=3)
        walk = c.new_group(name='Walk')
        run = c.new_group(name='Run')
        sprint = c.new_group(name='Sprint')
        for child in (walk, run, sprint):
            w.project.library.move_group(child.id, movement.id)
        c.refresh()
        assert c.remove_group(movement.id, mode='promote') is not None
        library = w.project.library
        assert movement.id not in library.groups
        assert [row.name for row in library.children(root.id)] == ['Walk', 'Run', 'Sprint']
        assert all(library.groups[row.id].parent_id == root.id for row in (walk, run, sprint))
        assert library.animation(animation_id).group_id == root.id
    finally:
        close_window(qt, w)


def test_delete_parent_recursive_requires_explicit_confirmation(qt, tmp_path, monkeypatch):
    w = window(qt, tmp_path)
    c = w.library_controller
    try:
        root = c.new_group(name='Movement')
        walk = c.new_group(name='Walk')
        w.project.library.move_group(walk.id, root.id)
        animation_id = cached_clip(w, walk.id, 'Walk', count=3)
        c.refresh()
        asked = []
        monkeypatch.setattr(MessageBox, 'choice', staticmethod(
            lambda *args, **kwargs: asked.append(args) or 2))
        assert c.remove_group(root.id) is None
        assert asked and root.id in w.project.library.groups
        assert w.project.library.animation(animation_id) is not None
        monkeypatch.setattr(MessageBox, 'question', staticmethod(lambda *args, **kwargs: MessageBox.StandardButton.Yes))
        monkeypatch.setattr(MessageBox, 'choice', staticmethod(lambda *args, **kwargs: 0))
        assert c.remove_group(root.id) is not None
        library = w.project.library
        assert root.id not in library.groups and walk.id not in library.groups
        assert library.animation(animation_id) is None
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_delete_group_undo(qt, tmp_path):
    w = window(qt, tmp_path)
    c = w.library_controller
    try:
        root = c.new_group(name='Player')
        jump = c.new_group(name='Jump')
        jump_up = c.new_group(name='JumpUp')
        land = c.new_group(name='Land')
        w.project.library.move_group(jump.id, root.id)
        for child in (jump_up, land):
            w.project.library.move_group(child.id, jump.id)
        animation_id = cached_clip(w, jump.id, 'Jump', count=3)
        c.remove_group(jump.id, mode='promote')
        assert jump.id not in w.project.library.groups
        w.undo_edit()
        library = w.project.library
        assert jump.id in library.groups
        assert [row.name for row in library.children(jump.id)] == ['JumpUp', 'Land']
        assert library.animation(animation_id) is not None
        assert library.animation(animation_id).group_id == jump.id
    finally:
        close_window(qt, w)


def test_tree_drag_100_visual_no_trail(qt, tmp_path):
    "100 reorder / nest / unnest operations must leave no visual residue in the tree."
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        library = w.project.library
        for step in range(100):
            library.move_group(groups['combat'].id, groups['movement'].id if step % 2 else None)
            library.move_group(groups['jump'].id, groups['combat'].id if step % 4 == 0 else None)
        library.move_group(groups['combat'].id, groups['movement'].id)
        c.selection = ('PROJECT', None)
        c.refresh()
        first = render_tree(w)
        fresh = tmp_path / 'fresh-tree'
        fresh.mkdir()
        w2 = window(qt, fresh)
        try:
            w2.project = w.project
            w2.project_file = w.project_file
            w2.library_controller.selection = ('PROJECT', None)
            w2.library_controller.refresh()
            events(qt, lambda: True)
            second = render_tree(w2)
        finally:
            close_window(qt, w2)
        difference = int(np.abs(first.astype(int) - second.astype(int)).max())
        assert np.array_equal(first, second), difference
    finally:
        close_window(qt, w)


def test_tree_drag_uses_no_widget_snapshot(qt, tmp_path, monkeypatch):
    "Group drags may only use the drop indicator; Qt must never grab a widget pixmap."
    w, c, character, groups = nested_window(qt, tmp_path)
    try:
        from PySide6.QtGui import QDrag
        from PySide6.QtWidgets import QWidget
        tree = w.library_panel.tree
        calls = []
        monkeypatch.setattr(QWidget, 'grab', lambda self, *args, **kwargs: calls.append(self) or None)
        # exec() would block on a real drop target; only the pixmap rule is under test.
        monkeypatch.setattr(QDrag, 'exec', lambda self, *args, **kwargs: Qt.DropAction.IgnoreAction)
        tree.startDrag(Qt.DropAction.MoveAction)
        assert not calls
    finally:
        close_window(qt, w)
