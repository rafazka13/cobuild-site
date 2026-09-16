from __future__ import annotations

import os
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Mapping

from .errors import SettingsError

ENV_PREFIX = "EXERCISE_GIF_"

BACKENDS = ("openai", "synthetic")
STYLES = ("flat", "clay", "photo")
PLANNER_MODES = ("auto", "library", "llm")
IMAGE_QUALITIES = ("low", "medium", "high", "xhigh", "max", "auto")
IMAGE_MODERATIONS = ("auto", "low")

# Verified against openai-python 3.14 (Sept 2026): ImageModel literal includes
# gpt-image-1, gpt-image-1.5, gpt-image-2 and the gpt-image-2.5-* previews.
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_PLANNER_MODEL = "gpt-5.4-mini"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    """All knobs for the service. Every field can be set with ``EXERCISE_GIF_<FIELD>``.

    ``grid`` is set as ``EXERCISE_GIF_GRID=3x2`` (columns x rows); the product is the
    number of keyframes drawn per exercise.
    """

    backend: str = "openai"
    image_model: str = DEFAULT_IMAGE_MODEL
    image_quality: str = "medium"
    image_moderation: str = "auto"
    planner: str = "auto"
    planner_model: str = DEFAULT_PLANNER_MODEL
    style: str = "flat"
    athlete: str | None = None
    reference_image: Path | None = None
    grid_cols: int = 3
    grid_rows: int = 2
    frame_size: int = 480
    frame_ms: int = 140
    hold_ends_ms: int | None = None
    colors: int = 128
    cache_dir: Path = Path.home() / ".cache" / "exercise-gifs"
    output_dir: Path = Path("exercise-gifs-out")
    max_workers: int = 4
    max_attempts: int = 2
    request_timeout: float = 180.0
    snap_grid: bool = True
    api_key: str | None = None

    @property
    def grid(self) -> tuple[int, int]:
        return (self.grid_cols, self.grid_rows)

    @property
    def keyframe_count(self) -> int:
        return self.grid_cols * self.grid_rows

    @property
    def effective_hold_ends_ms(self) -> int:
        return self.hold_ends_ms if self.hold_ends_ms is not None else self.frame_ms * 2

    def with_(self, **changes: Any) -> "Settings":
        return replace(self, **changes).validate()

    def validate(self) -> "Settings":
        def check(name: str, value: Any, allowed: tuple[str, ...]) -> None:
            if value not in allowed:
                raise SettingsError(f"{name}={value!r} is not one of {', '.join(allowed)}")

        check("backend", self.backend, BACKENDS)
        check("style", self.style, STYLES)
        check("planner", self.planner, PLANNER_MODES)
        check("image_quality", self.image_quality, IMAGE_QUALITIES)
        check("image_moderation", self.image_moderation, IMAGE_MODERATIONS)
        if not (1 <= self.grid_cols <= 4 and 1 <= self.grid_rows <= 4):
            raise SettingsError("grid columns and rows must each be between 1 and 4")
        if not (2 <= self.keyframe_count <= 12):
            raise SettingsError("grid must yield between 2 and 12 keyframes")
        if not (64 <= self.frame_size <= 1024):
            raise SettingsError("frame_size must be between 64 and 1024 pixels")
        if not (20 <= self.frame_ms <= 2000):
            raise SettingsError("frame_ms must be between 20 and 2000")
        if self.hold_ends_ms is not None and not (0 <= self.hold_ends_ms <= 5000):
            raise SettingsError("hold_ends_ms must be between 0 and 5000")
        if not (2 <= self.colors <= 256):
            raise SettingsError("colors must be between 2 and 256")
        if self.max_workers < 1 or self.max_attempts < 1:
            raise SettingsError("max_workers and max_attempts must be >= 1")
        if self.request_timeout <= 0:
            raise SettingsError("request_timeout must be positive")
        if self.reference_image is not None and not Path(self.reference_image).is_file():
            raise SettingsError(f"reference_image {self.reference_image} does not exist")
        return self

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None, **overrides: Any) -> "Settings":
        env = os.environ if env is None else env
        values: dict[str, Any] = {}
        for f in fields(cls):
            raw = env.get(ENV_PREFIX + f.name.upper())
            if raw is None or raw == "":
                continue
            values[f.name] = _coerce(f.name, f.type, raw)
        grid = env.get(ENV_PREFIX + "GRID")
        if grid:
            values["grid_cols"], values["grid_rows"] = parse_grid(grid)
        if "api_key" not in values:
            key = env.get(ENV_PREFIX + "OPENAI_API_KEY") or env.get("OPENAI_API_KEY")
            if key:
                values["api_key"] = key
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values).validate()


def parse_grid(text: str) -> tuple[int, int]:
    parts = text.lower().replace("×", "x").split("x")
    if len(parts) != 2:
        raise SettingsError(f"grid must look like '3x2', got {text!r}")
    try:
        cols, rows = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise SettingsError(f"grid must look like '3x2', got {text!r}") from exc
    return cols, rows


def _coerce(name: str, annotation: Any, raw: str) -> Any:
    text = str(annotation)
    try:
        if "bool" in text:
            low = raw.strip().lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
            raise ValueError(raw)
        if "Path" in text:
            return Path(raw).expanduser()
        if "float" in text:
            return float(raw)
        if "int" in text:
            return int(raw)
    except ValueError as exc:
        raise SettingsError(f"{ENV_PREFIX}{name.upper()}={raw!r} is not a valid {annotation}") from exc
    return raw
