from pathlib import Path

import pytest

from exercise_gifs.errors import SettingsError
from exercise_gifs.settings import Settings, parse_grid


def test_defaults():
    s = Settings.from_env({})
    assert s.backend == "openai" and s.image_model == "gpt-image-2" and s.planner_model == "gpt-5.4-mini"
    assert s.grid == (3, 2) and s.keyframe_count == 6
    assert s.effective_hold_ends_ms == 280 and s.api_key is None


def test_env_coercion():
    env = {
        "EXERCISE_GIF_BACKEND": "synthetic",
        "EXERCISE_GIF_FRAME_SIZE": "320",
        "EXERCISE_GIF_REQUEST_TIMEOUT": "30.5",
        "EXERCISE_GIF_SNAP_GRID": "false",
        "EXERCISE_GIF_CACHE_DIR": "/tmp/eg-cache",
        "EXERCISE_GIF_GRID": "2x3",
        "EXERCISE_GIF_HOLD_ENDS_MS": "0",
        "EXERCISE_GIF_ATHLETE": "a tall athlete",
        "OPENAI_API_KEY": "sk-env",
    }
    s = Settings.from_env(env)
    assert s.backend == "synthetic" and s.frame_size == 320 and s.request_timeout == 30.5
    assert s.snap_grid is False and s.cache_dir == Path("/tmp/eg-cache")
    assert s.grid == (2, 3) and s.keyframe_count == 6
    assert s.hold_ends_ms == 0 and s.effective_hold_ends_ms == 0
    assert s.athlete == "a tall athlete" and s.api_key == "sk-env"


def test_dedicated_api_key_wins():
    assert Settings.from_env({"OPENAI_API_KEY": "a", "EXERCISE_GIF_OPENAI_API_KEY": "b"}).api_key == "b"
    assert Settings.from_env({"OPENAI_API_KEY": "a", "EXERCISE_GIF_API_KEY": "c"}).api_key == "c"


def test_overrides_win_and_none_is_ignored():
    s = Settings.from_env({"EXERCISE_GIF_STYLE": "clay"}, style="photo", frame_ms=None)
    assert s.style == "photo" and s.frame_ms == 140


@pytest.mark.parametrize(
    "env",
    [
        {"EXERCISE_GIF_STYLE": "neon"},
        {"EXERCISE_GIF_FRAME_MS": "abc"},
        {"EXERCISE_GIF_SNAP_GRID": "maybe"},
        {"EXERCISE_GIF_GRID": "5x5"},
        {"EXERCISE_GIF_GRID": "3"},
        {"EXERCISE_GIF_GRID": "1x1"},
        {"EXERCISE_GIF_FRAME_SIZE": "10"},
        {"EXERCISE_GIF_COLORS": "1"},
        {"EXERCISE_GIF_MAX_WORKERS": "0"},
        {"EXERCISE_GIF_IMAGE_QUALITY": "ultra"},
        {"EXERCISE_GIF_PLANNER": "magic"},
        {"EXERCISE_GIF_REFERENCE_IMAGE": "/definitely/missing.png"},
    ],
)
def test_invalid_env_raises(env):
    with pytest.raises(SettingsError):
        Settings.from_env(env)


def test_parse_grid():
    assert parse_grid("3x2") == (3, 2)
    assert parse_grid("2×3") == (2, 3)
    with pytest.raises(SettingsError):
        parse_grid("3by2")


def test_with_validates():
    s = Settings.from_env({})
    assert s.with_(frame_ms=200).frame_ms == 200
    with pytest.raises(SettingsError):
        s.with_(backend="carrier-pigeon")
