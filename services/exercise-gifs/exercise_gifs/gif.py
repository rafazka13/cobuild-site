from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageSequence

from .models import LoopMode

WHITE = (255, 255, 255)


@dataclass(frozen=True)
class GifInfo:
    frame_count: int
    width: int
    height: int
    duration_ms: int
    loop: int | None


def fit_square(frame: Image.Image, size: int, background: tuple[int, int, int] = WHITE) -> Image.Image:
    """Scale a frame to fit inside ``size``x``size`` and centre it on a solid background."""
    frame = frame.convert("RGB")
    scale = min(size / frame.width, size / frame.height)
    new_size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
    resized = frame.resize(new_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), background)
    canvas.paste(resized, ((size - new_size[0]) // 2, (size - new_size[1]) // 2))
    return canvas


def loop_sequence(frames: list[Image.Image], loop: LoopMode) -> list[Image.Image]:
    """Order frames for playback: ping-pong plays forward then back (ends not repeated)."""
    if loop == "pingpong" and len(frames) > 2:
        return list(frames) + frames[-2:0:-1]
    return list(frames)


def frame_durations(frame_count: int, sequence_len: int, frame_ms: int, hold_ends_ms: int, loop: LoopMode) -> list[int]:
    """Per-frame durations; the two turnaround poses of a ping-pong loop linger a little longer."""
    durations = [frame_ms] * sequence_len
    if loop == "pingpong" and sequence_len:
        durations[0] = hold_ends_ms
        durations[min(frame_count - 1, sequence_len - 1)] = hold_ends_ms
    return durations


def shared_palette(frames: list[Image.Image], colors: int) -> Image.Image:
    """Quantise a montage of all frames once so every frame shares one palette (no flicker)."""
    thumb = 128
    strip = Image.new("RGB", (thumb * len(frames), thumb), WHITE)
    for i, frame in enumerate(frames):
        strip.paste(frame.resize((thumb, thumb), Image.Resampling.BILINEAR), (i * thumb, 0))
    return strip.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


def assemble_gif(
    frames: list[Image.Image],
    *,
    size: int = 480,
    frame_ms: int = 140,
    loop: LoopMode = "pingpong",
    hold_ends_ms: int | None = None,
    colors: int = 128,
    dither: bool = True,
) -> bytes:
    """Turn keyframes into a looping GIF and return its bytes."""
    if len(frames) < 2:
        raise ValueError("need at least two frames to animate")
    if hold_ends_ms is None:
        hold_ends_ms = frame_ms * 2
    square = [fit_square(f, size) for f in frames]
    palette = shared_palette(square, colors)
    dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    quantised = [f.quantize(palette=palette, dither=dither_mode) for f in square]
    sequence = loop_sequence(quantised, loop)
    durations = frame_durations(len(frames), len(sequence), frame_ms, hold_ends_ms, loop)
    buffer = BytesIO()
    sequence[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=sequence[1:],
        duration=durations,
        loop=0,
        disposal=1,
        optimize=False,
    )
    return buffer.getvalue()


def read_gif_info(data: bytes) -> GifInfo:
    with Image.open(BytesIO(data)) as img:
        total = 0
        count = 0
        for frame in ImageSequence.Iterator(img):
            count += 1
            total += int(frame.info.get("duration", 0))
        return GifInfo(frame_count=count, width=img.width, height=img.height, duration_ms=total, loop=img.info.get("loop"))
