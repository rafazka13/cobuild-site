from __future__ import annotations

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from exercise_gifs import ExerciseGifService, Settings
from exercise_gifs.frames.synthetic import SyntheticFrameSource
from exercise_gifs.models import KeyframePlan
from exercise_gifs.planner import LLMKeyframePlan


def synthetic_sheet(cols: int = 3, rows: int = 2, name: str = "Test Move") -> Image.Image:
    plan = KeyframePlan(exercise=name, keyframes=tuple(f"pose {i}" for i in range(cols * rows)))
    return SyntheticFrameSource().render_sheet(plan, cols=cols, rows=rows).image


def png_b64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class FakeImages:
    """Stands in for ``client.images``; records every call and returns a synthetic sheet."""

    def __init__(self, cols: int = 3, rows: int = 2):
        self.cols, self.rows = cols, rows
        self.generate_calls: list[dict] = []
        self.edit_calls: list[dict] = []
        self.error: Exception | None = None
        self.empty = False
        self.bad_data = False

    def _response(self):
        if self.error is not None:
            raise self.error
        if self.empty:
            return SimpleNamespace(data=[], usage=None)
        if self.bad_data:
            return SimpleNamespace(data=[SimpleNamespace(b64_json="not base64 png")], usage=None)
        usage = SimpleNamespace(model_dump=lambda: {"input_tokens": 10, "output_tokens": 1000})
        return SimpleNamespace(data=[SimpleNamespace(b64_json=png_b64(synthetic_sheet(self.cols, self.rows)))], usage=usage)

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return self._response()

    def edit(self, **kwargs):
        self.edit_calls.append(kwargs)
        return self._response()


class FakeResponses:
    """Stands in for ``client.responses``; returns a parsed ``LLMKeyframePlan``."""

    def __init__(self, keyframes: int = 8):
        self.parse_calls: list[dict] = []
        self.error: Exception | None = None
        self.parsed: LLMKeyframePlan | None = LLMKeyframePlan(
            exercise="Zercher Squat",
            camera="side view, camera at hip height, athlete facing left",
            equipment="a barbell held in the crooks of the elbows",
            setting="a plain gym floor",
            loop="pingpong",
            keyframes=[f"llm pose {i}" for i in range(keyframes)],
            cue="Elbows tight, chest up.",
        )

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(output_parsed=self.parsed)


@pytest.fixture
def fake_client():
    return SimpleNamespace(images=FakeImages(), responses=FakeResponses())


@pytest.fixture
def synthetic_settings(tmp_path: Path) -> Settings:
    return Settings.from_env({}, backend="synthetic", cache_dir=tmp_path / "cache", output_dir=tmp_path / "out")


@pytest.fixture
def service(synthetic_settings: Settings) -> ExerciseGifService:
    return ExerciseGifService(synthetic_settings)
