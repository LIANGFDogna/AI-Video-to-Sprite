from dataclasses import asdict
import copy
import pytest

from app.models.timeline_edit import TimelineEdit, FrameOverride, EditHistory, curve_value


def animation(count=39):
    edit = TimelineEdit()
    edit.initialize(count, 24)
    return edit


def ids(edit):
    return [f.id for f in edit.frames('main')]


def test_39_to_20_ease_keeps_endpoints_and_marked_keyframes():
    edit = animation()
    original = ids(edit)
    edit.mark_keyframes([original[12], original[13]])
    created = edit.retime_count(original, 20, 24, 'ease_in_out')
    frames = edit.frames('main')
    assert len(frames) == len(created) == 20
    assert frames[0].source_index == 0 and frames[-1].source_index == 38
    assert {12, 13} <= {f.source_index for f in frames}
    assert len({f.source_index for f in frames}) == 20
    assert edit.duration == pytest.approx(20/24)
    assert edit.source_frames == list(range(39))
    edit.validate(39)


def test_protected_frames_cannot_be_silently_discarded():
    edit = animation(4)
    edit.mark_keyframes(ids(edit))
    before = asdict(edit)
    with pytest.raises(ValueError, match='protected'):
        edit.retime_count(ids(edit), 2, 24)
    assert asdict(edit) == before


def test_delete_single_and_multiple_only_changes_timeline():
    edit = animation(8)
    original = ids(edit)
    edit.delete([original[1]])
    edit.delete([original[3], original[5]])
    assert [f.source_index for f in edit.frames()] == [0, 2, 4, 6, 7]
    assert [f.start for f in edit.frames()] == pytest.approx([i/24 for i in range(5)])
    assert edit.source_frames == list(range(8)) and len(edit.deleted_frames) == 3


def test_copy_paste_single_multiple_and_overrides_are_independent():
    edit = animation(6)
    original = ids(edit)
    edit.offset([original[1]], -6, 14)
    pasted = edit.paste(edit.copy([original[1]]), edit.duration)
    edit.offset(pasted, 1, 2)
    assert edit.frame_overrides[original[1]].offset_x == -6
    assert edit.frame_overrides[pasted[0]].offset_x == -5
    edit.paste(edit.copy(original[2:5]), 0)
    assert len(edit.timeline_clips) == 10 and len({f.id for f in edit.timeline_clips}) == 10
    assert [f.source_index for f in edit.frames()[:3]] == [2, 3, 4]
    edit.validate(6)


def test_reverse_selected_range_and_move_to_another_track():
    edit = animation(8)
    original = ids(edit)
    edit.reverse(original[3:7])
    assert [f.source_index for f in edit.frames()] == [0, 1, 2, 6, 5, 4, 3, 7]
    edit.move(original[1:3], 0, 'effects')
    assert [f.source_index for f in edit.frames('effects')] == [1, 2]
    assert len(edit.frames('main')) == 6
    edit.validate(8)


def test_selected_duration_and_speed_curve_leave_unselected_frames_intact():
    edit = animation()
    original = ids(edit)
    edit.retime_duration(original[10:26], .4, 'ease_in_out')
    frames = edit.frames('main')
    assert [f.source_index for f in frames] == list(range(39))
    assert frames[9].start == 9/24
    assert frames[25].end == pytest.approx(10/24+.4)
    assert frames[26].start == pytest.approx(10/24+.4)
    assert frames[10].duration > frames[17].duration
    edit.retime_duration(ids(edit), .8, 'bezier', (.1, .1, .9, .9))
    assert edit.duration == pytest.approx(.8)
    assert all(f.duration > 0 for f in edit.timeline_clips)


def test_position_scale_opacity_interpolation_and_locked_tracks():
    edit = animation(5)
    ordered = ids(edit)
    edit.frame_overrides[ordered[-1]] = FrameOverride(40, -20, 2, .2)
    edit.interpolate(ordered, 'linear')
    middle = edit.frame_overrides[ordered[2]]
    assert (middle.offset_x, middle.offset_y, middle.scale, middle.opacity) == pytest.approx((20, -10, 1.5, .6))
    edit.track_layout[0].locked = True
    for action in (lambda: edit.delete(ordered), lambda: edit.offset(ordered, 10, 2), lambda: edit.reverse(ordered)):
        with pytest.raises(ValueError, match='locked'):
            action()


def test_history_roundtrip_includes_root_and_all_edit_data():
    edit = animation(5)
    history = EditHistory()
    before = dict(editor=asdict(edit), roots={0: (1., 2.)})
    edit.reverse(ids(edit))
    after = dict(editor=asdict(edit), roots={0: (3., 4.)})
    history.record(before, after, 'Reverse and Root')
    assert history.undo() == before
    assert history.redo() == after
    assert asdict(TimelineEdit.from_dict(after['editor'])) == after['editor']
    assert history.undo() == before
    replacement = copy.deepcopy(before)
    replacement['roots'] = {0: (5., 6.)}
    history.record(before, replacement, 'Root')
    assert history.redo() is None and history.undo() == before


def test_curve_monotonicity_and_invalid_bezier():
    for curve in ('linear', 'ease_in', 'ease_out', 'ease_in_out', 'bezier'):
        values = [curve_value(i/100, curve) for i in range(101)]
        assert values == sorted(values)
        assert values[0] == pytest.approx(0, abs=1e-8)
        assert values[-1] == pytest.approx(1, abs=1e-8)
    with pytest.raises(ValueError, match='monotonic'):
        curve_value(.5, 'bezier', (.8, .1, .2, .9))


def test_interpolation_preserves_marked_middle_keyframe():
    edit=animation(5)
    ordered=ids(edit)
    edit.mark_keyframes([ordered[2]])
    edit.frame_overrides[ordered[2]]=FrameOverride(40,-20,2,.4)
    edit.interpolate(ordered)
    assert edit.frame_overrides[ordered[2]]==FrameOverride(40,-20,2,.4)
    assert edit.frame_overrides[ordered[1]]==FrameOverride(20,-10,1.5,.7)
    assert edit.frame_overrides[ordered[3]]==FrameOverride(20,-10,1.5,.7)
