"""Independent PNG/TIFF fixtures verify actual on-disk sample depth and values."""
import json
import struct
import zlib
import numpy as np
import pytest
from PIL import Image

from app.core.frame_sequence import scan_sequence, read_sequence_frame
from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.core.canvas_normalizer import premultiplied_resize
from app.exporters.image_exporter import export_images
from app.models.project import Project
from app.utils.cache import FrameCache, save_rgba
from app.utils.rgba_image import read_rgba_with_format, to_rgba8
from app.utils.paths import frame_path


def write_png(path, pixels):
    h, w, channels = pixels.shape
    bits = pixels.dtype.itemsize * 8
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = pixels.astype('>u2' if bits == 16 else 'u1')
    raw = b''.join(b'\0' + row.tobytes() for row in rows)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, bits, 6 if channels == 4 else 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def write_tiff(path, pixels, associated=False):
    h, w, channels = pixels.shape
    bits = pixels.dtype.itemsize * 8
    tags = {256: (4, 1, w), 257: (4, 1, h), 258: (3, channels, 0), 259: (3, 1, 1),
        262: (3, 1, 2), 273: (4, 1, 0), 277: (3, 1, channels), 278: (4, 1, h),
        279: (4, 1, pixels.nbytes), 284: (3, 1, 1)}
    if channels == 4:
        tags[338] = (3, 1, 1 if associated else 2)
    samples_offset = 8 + 2 + len(tags) * 12 + 4
    tags[258] = (3, channels, samples_offset)
    tags[273] = (4, 1, samples_offset + channels * 2)
    directory = struct.pack('<H', len(tags)) + b''.join(struct.pack('<HHII', key, *value) for key, value in sorted(tags.items())) + b'\0' * 4
    path.write_bytes(b'II*\0' + struct.pack('<I', 8) + directory + struct.pack('<' + 'H' * channels, *([bits] * channels))
        + pixels.astype('<u2' if bits == 16 else 'u1').tobytes())


@pytest.mark.parametrize('bits,channels', [(8, 3), (8, 4), (16, 3), (16, 4)])
@pytest.mark.parametrize('extension', ['png', 'tiff'])
def test_rgb_rgba_sample_depth_alpha_cache_and_export(tmp_path, bits, channels, extension):
    folder = tmp_path / '中文序列'
    folder.mkdir()
    maximum = 2 ** bits - 1
    source = np.random.default_rng(71).integers(0, maximum + 1, (18, 27, channels), dtype=np.uint8 if bits == 8 else np.uint16)
    source[0, 0] = 0
    source[-1, -1] = maximum
    (write_png if extension == 'png' else write_tiff)(folder / ('0000.' + extension), source)
    rgba, info = read_rgba_with_format(folder / ('0000.' + extension))
    assert info.color_mode == ('RGBA' if channels == 4 else 'RGB')
    assert info.channels == channels and info.bits_per_channel == bits
    assert info.bits_per_pixel == channels * bits and info.has_alpha == (channels == 4)
    assert np.array_equal(rgba[..., :channels], source)
    if channels == 3:
        assert np.all(rgba[..., 3] == maximum)
    scan = scan_sequence(folder)
    assert scan.formats == (info,)
    project = Project().import_frame_sequence(folder)
    pipe = Pipeline(project, tmp_path / 'cache')
    output = export_images(pipe, tmp_path / 'export')
    assert np.array_equal(FrameCache().read(frame_path(pipe.raw, 0)), rgba)
    assert frame_path(pipe.raw, 0).read_bytes()[24] == bits
    final = FinalFrameProvider(project, pipe.cache_dir)
    expected = source if channels == 4 else rgba
    if bits == 16:
        expected = np.floor(expected.astype(np.float64) * 255 / 65535 + .5).astype(np.uint8)
    assert np.array_equal(final.get_final_frame(0), expected)
    with Image.open(output / 'frames' / '0000.png') as exported:
        assert np.array_equal(np.array(exported), expected)
    assert np.array_equal(final.get_source_keyed_frame(0), expected)
    project.save(tmp_path / 'project.aivsprite')
    restored = Project.load(tmp_path / 'project.aivsprite')
    restored.sequence_formats = []
    Pipeline(restored, pipe.cache_dir).build()
    assert restored.sequence_formats == [info.to_dict()]


def test_full_16_bit_range_maps_color_and_alpha_with_rounding():
    values = np.arange(65536, dtype=np.uint16)
    rgba = np.repeat(values[:, None, None], 4, axis=2)
    expected = np.floor(values.astype(np.float64) / 257 + .5).astype(np.uint8)
    result = to_rgba8(rgba)
    for channel in range(4):
        assert np.array_equal(result[:, 0, channel], expected)
    assert list(result[[0, 128, 129, 257, 32768, 65535], 0, 3]) == [0, 0, 1, 1, 128, 255]


def test_16_bit_resize_keeps_precision_until_final_quantization(tmp_path):
    # Quantizing Alpha first erases the first contributor (128 -> 0).
    # Its color still belongs in the rounded alpha=1 footprint after averaging.
    pixels = np.array([[[50000, 12000, 20000, 128], [50000, 12000, 20000, 130]]], np.uint16)
    result = premultiplied_resize(pixels, 1, 1)
    assert result[0, 0].tolist() == [195, 47, 78, 1]
    first_quantized = premultiplied_resize(to_rgba8(pixels), 1, 1)
    assert first_quantized[0, 0, 3] == 1
    # A color difference establishes that the early quantization path is detectably wrong.
    pixels[0, 1, :3] = (6000, 42000, 65000)
    assert not np.array_equal(premultiplied_resize(pixels, 1, 1), premultiplied_resize(to_rgba8(pixels), 1, 1))
    large = np.zeros((1536, 1536, 4), np.uint16)
    large[..., :3] = (0, 65535, 0)
    large[301:601, 601:901] = (50000, 12000, 20000, 65535)
    folder = tmp_path / 'large'
    folder.mkdir()
    write_png(folder / '0.png', large)
    project = Project().import_frame_sequence(folder)
    project.sprite_cell.canvas_mode = 'normalize_source'
    pipe = Pipeline(project, tmp_path / 'cache')
    pipe.build()
    final = FinalFrameProvider(project, pipe.cache_dir).get_final_frame(0)
    assert final.shape == (512, 512, 4)
    assert np.all(final[final[..., 3] > 0, :3] == (195, 47, 78))
    assert FrameCache().read(frame_path(pipe.raw, 0)).dtype == np.uint16


def test_16_bit_padding_and_processed_sequence_keep_native_source(tmp_path):
    folder = tmp_path / 'processed'
    folder.mkdir()
    texture = np.random.default_rng(6).integers(10000, 60000, (40, 30, 3), dtype=np.uint16)
    for i in range(3):
        pixels = np.zeros((100, 100, 4), np.uint16)
        pixels[20:60, 25+i:55+i, :3] = texture
        pixels[20:60, 25+i:55+i, 3] = 45000
        write_png(folder / f'{i}.png', pixels)
    padded = read_sequence_frame(folder / '0.png', (110, 120))
    assert padded.dtype == np.uint16 and np.count_nonzero(padded[100:]) == 0
    project = Project().import_frame_sequence(folder, passthrough=False)
    project.root_keyframes[0] = (40, 40)
    project.sprite_cell.canvas_mode = 'normalize_source'
    project.sprite_cell.target_width = project.sprite_cell.target_height = 50
    pipe = Pipeline(project, tmp_path / 'cache')
    pipe.build()
    assert FrameCache().read(frame_path(pipe.source_aligned, 0)).dtype == np.uint16
    assert all(f.tracking_confidence > .35 for f in project.tracking_results)
    assert FinalFrameProvider(project, pipe.cache_dir).get_final_frame(0).dtype == np.uint8


def test_associated_alpha_tiff_is_unpremultiplied_without_losing_alpha(tmp_path):
    pixels = np.array([[[10000, 5000, 2500, 32768], [0, 0, 0, 0]]], np.uint16)
    write_tiff(tmp_path / 'associated.tiff', pixels, associated=True)
    rgba, info = read_rgba_with_format(tmp_path / 'associated.tiff')
    assert info.has_alpha and rgba[0, 0].tolist() == [20000, 10000, 5000, 32768]
    assert rgba[0, 1].tolist() == [0, 0, 0, 0]
