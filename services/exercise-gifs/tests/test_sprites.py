import pytest
from PIL import Image, ImageDraw

from exercise_gifs.frames.synthetic import SyntheticFrameSource
from exercise_gifs.models import KeyframePlan
from exercise_gifs.sprites import blank_panels, content_fraction, even_boundaries, sheet_size_for_grid, slice_grid, snap_boundaries

LINE = (204, 204, 204)


@pytest.mark.parametrize(("grid", "size"), [((3, 2), (1536, 1024)), ((2, 2), (1024, 1024)), ((2, 3), (1024, 1536)), ((3, 3), (1024, 1024)), ((4, 2), (1536, 1024)), ((1, 2), (1024, 1536))])
def test_sheet_size_for_grid(grid, size):
    assert sheet_size_for_grid(*grid) == size


def test_even_boundaries():
    assert even_boundaries(1536, 3) == [0, 512, 1024, 1536]
    assert even_boundaries(1024, 3) == [0, 341, 683, 1024]


def _white_sheet(width=1536, height=1024):
    return Image.new("RGB", (width, height), (255, 255, 255))


def test_snap_moves_boundaries_onto_drawn_lines():
    sheet = _white_sheet()
    draw = ImageDraw.Draw(sheet)
    for x in (532, 1009):
        draw.line([(x, 0), (x, 1024)], fill=LINE, width=3)
    draw.line([(0, 524), (1536, 524)], fill=LINE, width=3)
    xs = snap_boundaries(sheet, even_boundaries(1536, 3), axis=0)
    ys = snap_boundaries(sheet, even_boundaries(1024, 2), axis=1)
    assert xs[0] == 0 and xs[-1] == 1536 and abs(xs[1] - 532) <= 2 and abs(xs[2] - 1009) <= 2
    assert ys[0] == 0 and ys[-1] == 1024 and abs(ys[1] - 524) <= 2


def test_snap_prefers_the_line_nearest_the_expected_boundary():
    sheet = _white_sheet()
    draw = ImageDraw.Draw(sheet)
    draw.line([(0, 520), (1536, 520)], fill=LINE, width=3)  # the real separator, slightly off
    draw.line([(0, 488), (1536, 488)], fill=(60, 60, 60), width=4)  # a floor line across the top row
    ys = snap_boundaries(sheet, even_boundaries(1024, 2), axis=1)
    assert abs(ys[1] - 520) <= 2


def test_snap_ignores_wide_dark_regions_and_short_lines():
    sheet = _white_sheet()
    draw = ImageDraw.Draw(sheet)
    draw.rectangle([490, 0, 550, 1024], fill=(40, 40, 40))  # a figure, not a separator
    draw.line([(1030, 200), (1030, 800)], fill=LINE, width=3)  # too short to be a separator
    xs = snap_boundaries(sheet, even_boundaries(1536, 3), axis=0)
    assert xs == [0, 512, 1024, 1536]


def test_slice_grid_shapes_and_no_separator_leakage():
    plan = KeyframePlan(exercise="Back Squat", keyframes=tuple(f"p{i}" for i in range(6)))
    sheet = SyntheticFrameSource().render_sheet(plan, cols=3, rows=2).image
    frames = slice_grid(sheet, 3, 2)
    assert len(frames) == 6
    for frame in frames:
        assert 440 <= frame.width <= 520 and 440 <= frame.height <= 520
        assert LINE not in {color for _, color in frame.getcolors(maxcolors=1 << 24)}
    with pytest.raises(ValueError):
        slice_grid(sheet, 0, 2)


def test_slice_grid_without_snap_is_geometric():
    frames = slice_grid(_white_sheet(), 2, 2, snap=False, margin=0.0)
    assert [f.size for f in frames] == [(768, 512)] * 4


def test_content_fraction_and_blank_panels():
    blank = _white_sheet(400, 400)
    drawn = _white_sheet(400, 400)
    ImageDraw.Draw(drawn).ellipse([150, 150, 250, 250], fill=(30, 30, 30))
    assert content_fraction(blank) == 0
    assert content_fraction(drawn) > 0.004
    assert blank_panels([drawn, blank, drawn, blank]) == [1, 3]
    assert blank_panels([]) == []
