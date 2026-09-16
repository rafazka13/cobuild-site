from types import SimpleNamespace

import pytest
from PIL import Image

from exercise_gifs.errors import FrameSourceError, SettingsError
from exercise_gifs.frames import OpenAIImageFrameSource
from exercise_gifs.models import KeyframePlan
from tests.conftest import FakeImages

PLAN = KeyframePlan(exercise="Back Squat", keyframes=tuple(f"pose {i}" for i in range(6)), cue="Drive.")


def _source(images: FakeImages, **kwargs) -> OpenAIImageFrameSource:
    return OpenAIImageFrameSource(SimpleNamespace(images=images), model="gpt-image-2", quality="high", **kwargs)


def test_generate_request_and_response():
    images = FakeImages()
    source = _source(images)
    sheet = source.render_sheet(PLAN, cols=3, rows=2, style="flat")
    call = images.generate_calls[0]
    assert call["model"] == "gpt-image-2" and call["size"] == "1536x1024" and call["quality"] == "high"
    assert call["n"] == 1 and call["output_format"] == "png" and call["background"] == "opaque" and call["moderation"] == "auto"
    assert "Back Squat" in call["prompt"] and "Panel 6: pose 5" in call["prompt"] and "attempt" not in call["prompt"]
    assert sheet.image.mode == "RGB" and sheet.image.size == (1536, 1024)
    assert sheet.source == "openai:gpt-image-2" == source.source_id
    assert sheet.usage == {"input_tokens": 10, "output_tokens": 1000}
    assert images.edit_calls == []


def test_grid_aspect_picks_canvas():
    images = FakeImages(cols=2, rows=3)
    _source(images).render_sheet(PLAN, cols=2, rows=3)
    assert images.generate_calls[0]["size"] == "1024x1536"


def test_retry_attempt_is_mentioned_in_prompt():
    images = FakeImages()
    _source(images).render_sheet(PLAN, cols=3, rows=2, attempt=2)
    assert "attempt 2" in images.generate_calls[0]["prompt"]


def test_reference_image_uses_edit_endpoint(tmp_path):
    reference = tmp_path / "mascot.png"
    Image.new("RGB", (64, 64), (200, 30, 30)).save(reference)
    images = FakeImages()
    _source(images, reference_image=reference).render_sheet(PLAN, cols=3, rows=2)
    assert images.generate_calls == []
    call = images.edit_calls[0]
    assert call["input_fidelity"] == "high" and "moderation" not in call
    assert call["model"] == "gpt-image-2" and call["size"] == "1536x1024"
    assert hasattr(call["image"], "read")


def test_failures_become_frame_source_errors():
    images = FakeImages()
    images.error = RuntimeError("rate limited")
    with pytest.raises(FrameSourceError, match="rate limited"):
        _source(images).render_sheet(PLAN, cols=3, rows=2)

    images = FakeImages()
    images.empty = True
    with pytest.raises(FrameSourceError, match="no image data"):
        _source(images).render_sheet(PLAN, cols=3, rows=2)

    images = FakeImages()
    images.bad_data = True
    with pytest.raises(FrameSourceError, match="decode"):
        _source(images).render_sheet(PLAN, cols=3, rows=2)


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SettingsError, match="OPENAI_API_KEY"):
        OpenAIImageFrameSource().client
