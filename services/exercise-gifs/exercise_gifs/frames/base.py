from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

from ..models import KeyframePlan


@dataclass
class RenderedSheet:
    image: Image.Image
    prompt: str
    source: str
    usage: dict[str, Any] | None = None


class FrameSource(Protocol):
    """Anything that can draw a whole keyframe grid for one exercise on a single sheet."""

    name: str

    def render_sheet(
        self,
        plan: KeyframePlan,
        *,
        cols: int,
        rows: int,
        style: str = "flat",
        athlete: str | None = None,
        attempt: int = 1,
    ) -> RenderedSheet: ...
