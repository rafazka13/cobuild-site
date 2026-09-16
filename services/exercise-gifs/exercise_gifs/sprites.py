from __future__ import annotations

from PIL import Image

LANDSCAPE = (1536, 1024)
PORTRAIT = (1024, 1536)
SQUARE = (1024, 1024)


def sheet_size_for_grid(cols: int, rows: int) -> tuple[int, int]:
    """Pick the GPT-image canvas whose aspect best matches the grid so panels stay ~square."""
    aspect = cols / rows
    if aspect >= 1.25:
        return LANDSCAPE
    if aspect <= 0.8:
        return PORTRAIT
    return SQUARE


def size_string(size: tuple[int, int]) -> str:
    return f"{size[0]}x{size[1]}"


def even_boundaries(length: int, parts: int) -> list[int]:
    return [round(i * length / parts) for i in range(parts + 1)]


def _coverage_profile(band: Image.Image, white_threshold: int) -> list[float]:
    """Fraction of non-white pixels in each column of ``band`` (0..1)."""
    mask = band.convert("L").point(lambda v: 255 if v < white_threshold else 0)
    profile = mask.resize((mask.width, 1), Image.Resampling.BOX)
    return [v / 255 for v in profile.getdata()]


def snap_boundaries(
    sheet: Image.Image,
    boundaries: list[int],
    axis: int,
    *,
    search: float = 0.03,
    min_coverage: float = 0.9,
    max_line_fraction: float = 0.015,
    white_threshold: int = 238,
) -> list[int]:
    """Move interior boundaries onto the grid lines the model actually drew.

    Image models rarely place panel borders at mathematically exact positions. For each
    interior boundary we look ±``search`` of the sheet size for a thin column (axis 0) or row
    (axis 1) that is almost entirely non-white, which is what a drawn separator looks like,
    and snap to it. Boundaries with no convincing line nearby are left untouched.
    """
    width, height = sheet.size
    length = width if axis == 0 else height
    window = max(2, int(length * search))
    max_run = max(3, int(length * max_line_fraction))
    snapped = list(boundaries)
    for i in range(1, len(boundaries) - 1):
        expected = boundaries[i]
        lo, hi = max(0, expected - window), min(length, expected + window + 1)
        if axis == 0:
            band = sheet.crop((lo, 0, hi, height))
        else:
            band = sheet.crop((0, lo, width, hi)).transpose(Image.Transpose.TRANSPOSE)
        profile = _coverage_profile(band, white_threshold)
        if not profile:
            continue
        best = max(range(len(profile)), key=profile.__getitem__)
        if profile[best] < min_coverage:
            continue
        run = sum(1 for v in profile if v >= min_coverage)
        if run > max_run:
            continue  # a wide dark region is content, not a separator
        snapped[i] = lo + best
    return snapped


def slice_grid(
    sheet: Image.Image,
    cols: int,
    rows: int,
    *,
    margin: float = 0.03,
    snap: bool = True,
) -> list[Image.Image]:
    """Cut a sprite sheet into ``cols*rows`` panels, reading left-to-right, top-to-bottom.

    ``margin`` trims a fraction of each panel edge so separator lines never leak into frames.
    """
    if cols < 1 or rows < 1:
        raise ValueError("cols and rows must be >= 1")
    sheet = sheet.convert("RGB")
    width, height = sheet.size
    xs = even_boundaries(width, cols)
    ys = even_boundaries(height, rows)
    if snap:
        xs = snap_boundaries(sheet, xs, axis=0)
        ys = snap_boundaries(sheet, ys, axis=1)
    frames: list[Image.Image] = []
    for r in range(rows):
        for c in range(cols):
            x0, x1, y0, y1 = xs[c], xs[c + 1], ys[r], ys[r + 1]
            mx = int((x1 - x0) * margin)
            my = int((y1 - y0) * margin)
            frames.append(sheet.crop((x0 + mx, y0 + my, x1 - mx, y1 - my)))
    return frames


def content_fraction(frame: Image.Image, *, white_threshold: int = 235, inset: float = 0.1) -> float:
    """Fraction of non-white pixels in the central region of a frame."""
    width, height = frame.size
    box = (int(width * inset), int(height * inset), int(width * (1 - inset)), int(height * (1 - inset)))
    inner = frame.crop(box).convert("L").point(lambda v: 255 if v < white_threshold else 0)
    if inner.width == 0 or inner.height == 0:
        return 0.0
    return inner.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0)) / 255


def blank_panels(frames: list[Image.Image], *, min_content: float = 0.004) -> list[int]:
    """Indices of panels that contain (almost) nothing; the model skipped or merged them."""
    return [i for i, frame in enumerate(frames) if content_fraction(frame) < min_content]
