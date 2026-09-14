from dataclasses import asdict
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image
from app.core.frame_sequence import scan_sequence, sequence_paths
from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.exporters.image_exporter import export_images
from app.models.project import Project, ALIGNMENT_MODES
from app.models.character_profile import CharacterProfile
from app.utils.paths import frame_path


def rgba_frame(size=(512, 512), index=0):
    w, h = size
    image = np.zeros((h, w, 4), np.uint8)
    image[..., :3] = (10, 230, 80)  # Hidden RGB is part of the original pixels, too.
    image[30:90, 15+index:65+index] = (240, 15, 60, 255)
    image[31, 15+index] = (50, 120, 200, 17)
    image[0, 0] = (25, 40, 80, 91)  # Corner data must survive; no alpha crop/centering.
    return image


@pytest.fixture
def idle(tmp_path):
    folder = tmp_path / "idle"
    folder.mkdir()
    for i in range(22):
        Image.fromarray(rgba_frame(index=i)).save(folder / f"{i:04d}.png")
    for name in (".DS_Store", "Thumbs.db", "settings.json", "notes.txt"):
        (folder / name).write_text("ignored")
    return folder


def sequence_project(folder, **kwargs):
    return Project().import_frame_sequence(folder, **kwargs)


def test_scan_22_png_dimensions_alpha_and_animation_name(idle):
    scan = scan_sequence(idle)
    assert len(scan.names) == 22 and scan.canvas_size == (512, 512)
    assert scan.alpha == "RGBA" and not scan.mixed_sizes
    p = sequence_project(idle)
    assert p.export_settings.animation_name == "idle"
    assert p.sequence_fps == 24 and p.is_passthrough and p.alignment_mode == "passthrough"


def test_natural_order_1_2_10(tmp_path):
    for name in ("frame_10.png", "frame_2.png", "frame_1.png"):
        Image.fromarray(rgba_frame((80, 100))).save(tmp_path / name)
    assert [p.name for p in sequence_paths(tmp_path)] == ["frame_1.png", "frame_2.png", "frame_10.png"]


def test_passthrough_never_calls_root_motion_align_or_chroma_and_preserves_rgba(idle, tmp_path, monkeypatch):
    p = sequence_project(idle)
    p.character_profile = CharacterProfile()
    p.root_keyframes[0] = (450, 400)
    p.scale = 3
    p.motion_settings.enabled = True
    p.motion_settings.x_policy = p.motion_settings.y_policy = "LOCK"
    pipe = Pipeline(p, tmp_path / "cache")
    def forbidden(*args, **kwargs):
        raise AssertionError("Passthrough must not call alignment or key/tracking")
    for method in ("ensure_key", "ensure_roots", "ensure_motion", "ensure_source_aligned"):
        monkeypatch.setattr(pipe, method, forbidden)
    for name in ("warp_rgba", "chroma_key", "apply_character_motion", "calculate_layout", "motion_auto_layout"):
        monkeypatch.setattr("app.core.pipeline."+name, forbidden)
    pipe.build()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    assert (p.layout.width, p.layout.height) == (512, 512)
    assert p.layout.normalize_scale == (1, 1)
    for i in range(22):
        assert np.array_equal(provider.get_final_frame(i), rgba_frame(index=i))
    assert all(f.offset == f.correction == (0, 0) for f in p.tracking_results)
    assert all(f.tracking_method == "passthrough" and not f.warnings for f in p.tracking_results)


def test_sheet_and_export_match_provider_exactly(idle, tmp_path):
    p = sequence_project(idle)
    p.character_profile = CharacterProfile()
    p.export_settings.columns = 10
    pipe = Pipeline(p, tmp_path / "cache")
    output = export_images(pipe, tmp_path / "export", godot=True)
    provider = FinalFrameProvider(p, pipe.cache_dir)
    with Image.open(output / "sprite_sheet.png") as sheet:
        assert sheet.size == (5120, 1536)
        assert sheet.getpixel((5119, 1535)) == (0, 0, 0, 0)
        assert np.array_equal(np.array(sheet.crop((512, 1024, 1024, 1536))), rgba_frame(index=21))
    for i in range(22):
        with Image.open(output / "frames" / f"{i:04d}.png") as image:
            assert np.array_equal(np.array(image), provider.get_final_frame(i))
    metadata = json.loads((output / "animation.json").read_text())
    assert metadata["alignment_mode"] == "passthrough" and not metadata["character_profile_applied"]
    assert all(f["root"] is None and f["tracking_confidence"] is None for f in metadata["frames"])
    assert metadata["frames"][-1]["source_filename"] == "0021.png"
    motion = json.loads((output / "root_motion.json").read_text())
    assert motion["available"] is False and not motion["frames"]


def test_1536_original_default_then_explicit_canvas_normalization(tmp_path):
    folder = tmp_path / "large"
    folder.mkdir()
    image = np.zeros((1536, 1536, 4), np.uint8)
    image[..., :3] = (0, 255, 0)
    image[601:901, 301:601] = (240, 30, 70, 255)
    Image.fromarray(image).save(folder / "0.png")
    p = sequence_project(folder)
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.build()
    assert (p.layout.width, p.layout.height) == (1536, 1536)
    assert np.array_equal(FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0), image)
    raw_path = frame_path(pipe.raw, 0)
    before = raw_path.stat().st_mtime_ns
    p.sprite_cell.canvas_mode = "normalize_source"
    p.sprite_cell.target_width = p.sprite_cell.target_height = 512
    pipe.build()
    final = FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0)
    assert final.shape == (512, 512, 4) and p.layout.normalize_scale == (1/3, 1/3)
    assert p.tracking_results[0].cell_bbox == (100, 200, 201, 301)
    assert np.all(final[final[..., 3] > 0, :3] == (240, 30, 70))
    assert raw_path.stat().st_mtime_ns == before


def test_mixed_sizes_require_explicit_padding_and_preserve_top_left(tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    for i, size in enumerate(((512, 512), (600, 512))):
        Image.fromarray(rgba_frame(size)).save(folder / f"{i}.png")
    scan = scan_sequence(folder)
    assert scan.mixed_sizes and scan.canvas_size == (600, 512)
    p = sequence_project(folder)
    pipe = Pipeline(p, tmp_path / "cache")
    with pytest.raises(ValueError, match="dimensions differ"):
        pipe.build()
    assert not (pipe.cache_dir / "align.json").exists()
    p.sequence_size_policy = "pad"
    pipe.build()
    final = FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0)
    assert final.shape == (512, 600, 4)
    assert np.array_equal(final[:, :512], rgba_frame())
    assert np.count_nonzero(final[:, 512:]) == 0


def test_sequence_save_reload_and_fps_changes_keep_raw_cache(idle, tmp_path):
    p = sequence_project(idle)
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.build()
    times = [frame_path(folder, 0).stat().st_mtime_ns for folder in (pipe.raw, pipe.aligned)]
    p.sequence_fps = 12.5
    p.save(tmp_path / "project.aivsprite")
    restored = Project.load(tmp_path / "project.aivsprite")
    assert restored.sequence_folder == str(idle)
    assert restored.sequence_files == p.sequence_files
    Pipeline(restored, pipe.cache_dir).build()
    assert restored.video.fps == 12.5 and restored.video.duration == 22/12.5
    assert times == [frame_path(folder, 0).stat().st_mtime_ns for folder in (pipe.raw, pipe.aligned)]
    saved = json.loads((tmp_path / "project.aivsprite").read_text())
    assert saved["input_mode"] == "frame_sequence" and saved["sequence_folder"] == "idle"
    assert saved["fps"] == saved["video"]["fps"] == 12.5


def test_sequence_processing_option_preserves_alpha_and_uses_existing_tracking(tmp_path, monkeypatch):
    folder = tmp_path / "needs_alignment"
    folder.mkdir()
    for i in range(3):
        Image.fromarray(rgba_frame(index=i)).save(folder / f"{i}.png")
    p = sequence_project(folder, passthrough=False)
    p.root_keyframes = {i: (40+i, 60) for i in range(3)}
    p.motion_settings.x_policy = p.motion_settings.y_policy = "EXTRACT"
    p.sprite_cell.canvas_mode = "normalize_source"
    monkeypatch.setattr("app.core.pipeline.chroma_key", lambda *a: pytest.fail("Sequence must never be keyed again"))
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.build()
    assert all(f.cell_root == (40, 60) for f in p.tracking_results)
    assert np.array_equal(FinalFrameProvider(p, pipe.cache_dir).get_source_keyed_frame(0), rgba_frame())


@pytest.mark.parametrize("extension,mode", [("png", "RGBA"), ("webp", "RGBA"), ("tiff", "RGBA"), ("bmp", "RGB"), ("jpg", "RGB"), ("jpeg", "RGB")])
def test_supported_image_formats(tmp_path, extension, mode):
    path = tmp_path / ("frame."+extension)
    source = Image.fromarray(rgba_frame()).convert(mode)
    source.save(path, lossless=True)
    scan = scan_sequence(tmp_path)
    assert len(scan.names) == 1
    p = sequence_project(tmp_path)
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.build()
    with Image.open(path) as original:
        assert np.array_equal(FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0), np.array(original.convert("RGBA")))


@pytest.mark.parametrize("example", ["demo.aivsprite", "normalized_512.aivsprite", "character_profile.aivsprite"])
def test_legacy_video_projects_compatible(example):
    p = Project.load(Path("examples") / example)
    assert p.input_mode == "video" and not p.is_passthrough and p.alignment_mode in ALIGNMENT_MODES


def test_sequence_and_video_animation_snapshots_share_profile(idle, tmp_path):
    p = Project(source_video=str(tmp_path / "run.mp4"), character_profile=CharacterProfile())
    seq = p.import_frame_sequence(idle)
    assert seq.character_profile is p.character_profile and seq.is_passthrough
    seq.save(tmp_path / "clips.aivsprite")
    loaded = Project.load(tmp_path / "clips.aivsprite")
    video = loaded.select_animation("default")
    assert video.input_mode == "video" and not video.is_passthrough
    again = video.select_animation(seq.animation_id)
    assert again.sequence_folder == str(idle) and again.character_profile == p.character_profile


def test_sequence_file_changes_invalidate_final_frames(tmp_path):
    folder = tmp_path / "idle"
    folder.mkdir()
    Image.fromarray(rgba_frame()).save(folder / "1.png")
    p = sequence_project(folder)
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.build()
    old = FinalFrameProvider(p, pipe.cache_dir)
    Image.fromarray(rgba_frame(index=10)).save(folder / "1.png")
    Image.fromarray(rgba_frame(index=20)).save(folder / "2.png")
    pipe.build()
    assert p.video.frame_count == 2
    with pytest.raises(RuntimeError, match="changed"):
        old.get_final_frame(0)
    assert np.array_equal(FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0), rgba_frame(index=10))
