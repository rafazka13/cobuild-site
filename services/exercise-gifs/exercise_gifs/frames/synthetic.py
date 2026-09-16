from __future__ import annotations

import hashlib
import math

from PIL import Image, ImageDraw

from ..models import KeyframePlan
from ..sprites import even_boundaries, sheet_size_for_grid
from .base import RenderedSheet

WHITE = (255, 255, 255)
INK = (52, 58, 64)
ACCENTS = [(0, 150, 136), (233, 30, 99), (63, 81, 181), (255, 152, 0), (76, 175, 80)]


def _stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


class SyntheticFrameSource:
    """Draws a stick-figure squat storyboard with Pillow. No network, fully deterministic.

    Used for tests, dry runs and local development. The separator lines are deliberately
    jittered off the exact grid so the slicer's snapping logic is exercised too.
    """

    name = "synthetic"
    source_id = "synthetic"

    def __init__(self, *, jitter: float = 0.012, line_width: int = 3, line_color=(204, 204, 204)):
        self.jitter = jitter
        self.line_width = line_width
        self.line_color = line_color

    def render_sheet(
        self,
        plan: KeyframePlan,
        *,
        cols: int,
        rows: int,
        style: str = "flat",
        athlete: str | None = None,
        attempt: int = 1,
    ) -> RenderedSheet:
        width, height = sheet_size_for_grid(cols, rows)
        image = Image.new("RGB", (width, height), WHITE)
        draw = ImageDraw.Draw(image)
        seed = _stable_int(plan.slug)
        xs = self._jittered(even_boundaries(width, cols), width, seed)
        ys = self._jittered(even_boundaries(height, rows), height, seed >> 4)
        for x in xs[1:-1]:
            draw.line([(x, 0), (x, height)], fill=self.line_color, width=self.line_width)
        for y in ys[1:-1]:
            draw.line([(0, y), (width, y)], fill=self.line_color, width=self.line_width)

        count = cols * rows
        accent = ACCENTS[seed % len(ACCENTS)]
        for index in range(count):
            r, c = divmod(index, cols)
            box = (xs[c], ys[r], xs[c + 1], ys[r + 1])
            t = _progress(index, count, plan.loop)
            _draw_figure(draw, box, t, accent)
        return RenderedSheet(image=image, prompt=f"synthetic:{plan.slug}:{cols}x{rows}", source=self.source_id)

    def _jittered(self, boundaries: list[int], length: int, seed: int) -> list[int]:
        out = list(boundaries)
        for i in range(1, len(out) - 1):
            wobble = ((seed >> (i * 3)) % 200 - 100) / 100  # -1..1
            out[i] = int(out[i] + wobble * self.jitter * length)
        return out


def _progress(index: int, count: int, loop: str) -> float:
    if count <= 1:
        return 0.0
    if loop == "cycle":
        return (1 - math.cos(2 * math.pi * index / count)) / 2
    return index / (count - 1)


def _draw_figure(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], t: float, accent) -> None:
    """Side-view stick figure going from standing (t=0) to a deep squat (t=1)."""
    x0, y0, x1, y1 = box
    s = min(x1 - x0, y1 - y0)
    cx = (x0 + x1) / 2
    floor = y1 - 0.14 * s
    stroke = max(2, int(s * 0.035))
    shin = thigh = 0.22 * s
    torso = 0.26 * s
    head_r = 0.06 * s

    foot = (cx + 0.05 * s, floor)
    shin_tilt = math.radians(35 * t)
    knee = (foot[0] - shin * math.sin(shin_tilt), floor - shin * math.cos(shin_tilt))
    thigh_tilt = math.radians(85 * t)
    hip = (knee[0] - thigh * math.sin(thigh_tilt), knee[1] - thigh * math.cos(thigh_tilt))
    lean = math.radians(35 * t)
    shoulder = (hip[0] + torso * math.sin(lean), hip[1] - torso * math.cos(lean))
    head = (shoulder[0] + head_r * 1.1 * math.sin(lean), shoulder[1] - head_r * 1.6 * math.cos(lean))
    arm_len = 0.2 * s
    hand = (shoulder[0] + arm_len, shoulder[1] + 0.02 * s)

    draw.line([foot, knee, hip], fill=INK, width=stroke, joint="curve")
    draw.line([(foot[0] - 0.08 * s, floor), (foot[0] + 0.04 * s, floor)], fill=INK, width=stroke)
    draw.line([hip, shoulder], fill=accent, width=int(stroke * 1.6), joint="curve")
    draw.line([shoulder, hand], fill=INK, width=stroke)
    draw.ellipse([head[0] - head_r, head[1] - head_r, head[0] + head_r, head[1] + head_r], fill=INK)
