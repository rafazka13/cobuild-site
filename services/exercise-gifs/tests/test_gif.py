from io import BytesIO

import pytest
from PIL import Image, ImageSequence

from exercise_gifs.gif import assemble_gif, fit_square, frame_durations, loop_sequence, read_gif_info
from exercise_gifs.sprites import slice_grid
from tests.conftest import synthetic_sheet


def _frames(count=6):
    cols, rows = (3, 2) if count == 6 else (2, 2)
    return slice_grid(synthetic_sheet(cols, rows), cols, rows)


def _durations(data: bytes) -> list[int]:
    with Image.open(BytesIO(data)) as img:
        return [int(frame.info.get("duration", 0)) for frame in ImageSequence.Iterator(img)]


def test_pingpong_gif_layout():
    data = assemble_gif(_frames(6), size=240, frame_ms=140)
    info = read_gif_info(data)
    assert info.frame_count == 10 and info.width == 240 and info.height == 240 and info.loop == 0
    durations = _durations(data)
    assert durations[0] == 280 and durations[5] == 280
    assert all(d == 140 for i, d in enumerate(durations) if i not in (0, 5))
    assert info.duration_ms == sum(durations) == 280 * 2 + 140 * 8


def test_cycle_gif_layout():
    data = assemble_gif(_frames(6), size=200, frame_ms=100, loop="cycle", hold_ends_ms=500)
    assert read_gif_info(data).frame_count == 6
    assert _durations(data) == [100] * 6


def test_custom_hold_and_two_frame_pingpong():
    data = assemble_gif(_frames(4)[:2], size=120, frame_ms=100, hold_ends_ms=300)
    assert read_gif_info(data).frame_count == 2
    assert _durations(data) == [300, 300]


def test_needs_two_frames():
    with pytest.raises(ValueError):
        assemble_gif(_frames(4)[:1], size=120)


def _gif_color_tables(data: bytes) -> tuple[bytes, list[bytes | None]]:
    """Return (global colour table, per-frame local colour table or None) from raw GIF bytes."""
    pos = 6
    packed = data[pos + 4]
    pos += 7
    global_table = b""
    if packed & 0x80:
        size = 3 * (2 << (packed & 7))
        global_table, pos = data[pos : pos + size], pos + size
    frames: list[bytes | None] = []
    while data[pos] != 0x3B:
        block = data[pos]
        if block == 0x21:  # extension: label + sub-blocks
            pos += 2
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
        elif block == 0x2C:  # image descriptor
            packed = data[pos + 9]
            pos += 10
            local = None
            if packed & 0x80:
                size = 3 * (2 << (packed & 7))
                local, pos = data[pos : pos + size], pos + size
            pos += 1  # LZW minimum code size
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
            frames.append(local)
        else:
            raise AssertionError(f"unexpected GIF block {block:#x}")
    return global_table, frames


def test_frames_share_one_palette():
    data = assemble_gif(_frames(6), size=160, colors=64)
    global_table, locals_ = _gif_color_tables(data)
    assert len(global_table) == 64 * 3 and len(locals_) == 10
    assert all(table is None or table == global_table for table in locals_)


def test_loop_sequence_and_durations_helpers():
    frames = list("abcdef")
    assert loop_sequence(frames, "pingpong") == list("abcdefedcb")
    assert loop_sequence(frames, "cycle") == frames
    assert loop_sequence(list("ab"), "pingpong") == list("ab")
    assert frame_durations(6, 10, 100, 250, "pingpong") == [250, 100, 100, 100, 100, 250, 100, 100, 100, 100]
    assert frame_durations(6, 6, 100, 250, "cycle") == [100] * 6


def test_fit_square_pads_with_white():
    wide = Image.new("RGB", (200, 100), (0, 0, 0))
    square = fit_square(wide, 400)
    assert square.size == (400, 400)
    assert square.getpixel((200, 10)) == (255, 255, 255)
    assert square.getpixel((200, 200)) == (0, 0, 0)
