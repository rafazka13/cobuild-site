from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image

from exercise_gifs import ExerciseGifService, KeyframePlan, SessionItem, Settings
from exercise_gifs.errors import PlanningError, SheetValidationError
from exercise_gifs.frames.base import RenderedSheet
from exercise_gifs.frames.synthetic import SyntheticFrameSource
from exercise_gifs.gif import read_gif_info
from exercise_gifs.pipeline import build_caption, generate_session_gifs
from exercise_gifs.planner import KeyframePlanner

SESSION = {
    "name": "Lower A",
    "blocks": [
        {"name": "A", "exercises": [{"exercise": "Back Squat", "sets": 4, "reps": 6, "rpe": 8}]},
        {"name": "B", "exercises": [{"exercise": "heavy back squat 5x5", "sets": 5, "reps": 5}, "Push-up", {"exercise": "Zercher Squat", "notes": "Elbows tight."}]},
    ],
}


def test_session_end_to_end(service, tmp_path):
    result = service.generate_for_session(SESSION)
    assert result.ok and [g.exercise for g in result.gifs] == ["Back Squat", "Push-up", "Zercher Squat"]
    squat = result.gifs[0]
    assert squat.path == tmp_path / "out" / "back-squat.gif" and squat.path.is_file()
    assert [i.name for i in squat.items] == ["Back Squat", "heavy back squat 5x5"]
    assert squat.caption == "Back Squat — 4×6 @ RPE 8\nBrace, sit between your heels, drive the floor away."
    assert squat.frame_count == 10 and squat.width == squat.height == 480 and squat.duration_ms == 1680
    assert squat.plan.source == "library" and squat.source == "synthetic" and squat.from_cache is False
    assert squat.sheet_path is not None and squat.sheet_path.is_file()
    assert read_gif_info(squat.read_bytes()).frame_count == 10

    zercher = result.gifs[2]
    assert zercher.plan.source == "generic" and zercher.caption == "Zercher Squat\nElbows tight."
    assert result.to_dict()["session"] == "Lower A" and len(result.to_dict()["gifs"]) == 3


def test_cache_hits_and_force(service):
    first = service.generate_for_exercise("Back Squat")
    second = service.generate_for_exercise("Back Squat")
    forced = service.generate_for_exercise("Back Squat", force=True)
    assert first.from_cache is False and second.from_cache is True and forced.from_cache is False


def test_gif_cache_is_independent_of_sheet_cache(synthetic_settings, tmp_path):
    ExerciseGifService(synthetic_settings).generate_for_exercise("Back Squat")
    faster = ExerciseGifService(synthetic_settings.with_(frame_ms=60))
    events = []
    gif = faster.generate_for_exercise("Back Squat", on_progress=events.append)
    stages = [e["stage"] for e in events]
    assert "sheet_cached" in stages and "gif" in stages and "sheet" not in stages
    assert gif.duration_ms == 120 * 2 + 60 * 8


def test_failures_are_isolated(synthetic_settings):
    class FlakyPlanner(KeyframePlanner):
        def plan(self, name, *, hints=None):
            if "bad" in name.lower():
                raise PlanningError("no storyboard for you")
            return super().plan(name, hints=hints)

    service = ExerciseGifService(synthetic_settings, planner=FlakyPlanner(mode="library"))
    result = service.generate_for_session(["Back Squat", "Bad Move"])
    assert [g.exercise for g in result.gifs] == ["Back Squat"]
    assert result.errors == {"bad-move": "PlanningError: no storyboard for you"} and not result.ok


def test_progress_events_and_broken_callback(service):
    events = []
    service.generate_for_exercise("Plank", on_progress=events.append)
    stages = [e["stage"] for e in events]
    assert stages == ["plan", "sheet", "gif", "done"]
    assert events[-1]["exercise"] == "Plank" and events[-1]["path"].endswith("plank.gif")

    def boom(event):
        raise RuntimeError("callback bug")

    assert service.generate_for_exercise("Plank", on_progress=boom).exercise == "Plank"


class BlankThenGood:
    name = source_id = "blank-then-good"

    def __init__(self, blank_rounds: int):
        self.blank_rounds = blank_rounds
        self.attempts: list[int] = []
        self.inner = SyntheticFrameSource()

    def render_sheet(self, plan, *, cols, rows, style="flat", athlete=None, attempt=1):
        self.attempts.append(attempt)
        if len(self.attempts) <= self.blank_rounds:
            return RenderedSheet(image=Image.new("RGB", (1536, 1024), (255, 255, 255)), prompt="blank", source=self.name)
        return self.inner.render_sheet(plan, cols=cols, rows=rows, style=style, athlete=athlete, attempt=attempt)


def test_blank_sheet_triggers_retry(synthetic_settings):
    source = BlankThenGood(blank_rounds=1)
    events = []
    gif = ExerciseGifService(synthetic_settings, frame_source=source).generate_for_exercise("Back Squat", on_progress=events.append)
    assert source.attempts == [1, 2] and gif.frame_count == 10
    retries = [e for e in events if e["stage"] == "retry"]
    assert len(retries) == 1 and retries[0]["attempt"] == 1 and retries[0]["blank_panels"] == [0, 1, 2, 3, 4, 5]


def test_persistently_blank_sheet_fails(synthetic_settings):
    source = BlankThenGood(blank_rounds=10)
    service = ExerciseGifService(synthetic_settings.with_(max_attempts=3), frame_source=source)
    with pytest.raises(SheetValidationError, match="6 of 6 panels empty"):
        service.generate_for_exercise("Back Squat")
    assert source.attempts == [1, 2, 3]
    result = service.generate_for_session(["Back Squat"])
    assert "back-squat" in result.errors and result.gifs == []


def test_generate_for_exercise_inputs(service):
    plan = KeyframePlan(exercise="Custom Carry", keyframes=("a", "b", "c", "d"), loop="cycle")
    assert service.generate_for_exercise("Back Squat").slug == "back-squat"
    item = SessionItem(name="Plank", sets=3, reps="45 s")
    assert service.generate_for_exercise(item).caption.startswith("Plank — 3×45 s")
    custom = service.generate_for_exercise(plan)
    assert custom.slug == "custom-carry" and custom.frame_count == 6 and custom.plan.loop == "cycle"


def test_warm_renders_named_or_all(synthetic_settings, tmp_path):
    service = ExerciseGifService(synthetic_settings)
    result = service.warm(["Back Squat", "Plank"])
    assert result.ok and {g.slug for g in result.gifs} == {"back-squat", "plank"}
    assert (tmp_path / "out" / "plank.gif").is_file()


def test_concurrent_requests_render_once(synthetic_settings):
    class Counting(SyntheticFrameSource):
        calls = 0

        def render_sheet(self, *args, **kwargs):
            type(self).calls += 1
            return super().render_sheet(*args, **kwargs)

    service = ExerciseGifService(synthetic_settings, frame_source=Counting())
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.generate_for_exercise("Back Squat"), range(4)))
    assert Counting.calls == 1 and all(r.slug == "back-squat" for r in results)


def test_synthetic_backend_never_needs_gpt_planner(tmp_path):
    settings = Settings.from_env({}, backend="synthetic", planner="auto", cache_dir=tmp_path / "c", output_dir=tmp_path / "o")
    result = ExerciseGifService(settings).generate_for_session(["Made Up Movement"])
    assert result.ok and result.gifs[0].plan.source == "generic"


def test_openai_backend_end_to_end_with_fake_client(fake_client, tmp_path):
    settings = Settings.from_env({}, backend="openai", api_key="sk-test", cache_dir=tmp_path / "c", output_dir=tmp_path / "o")
    service = ExerciseGifService(settings, client=fake_client)
    result = service.generate_for_session(["Back Squat", "Zercher Squat"])
    assert result.ok and [g.source for g in result.gifs] == ["openai:gpt-image-2", "openai:gpt-image-2"]
    assert len(fake_client.images.generate_calls) == 2 and len(fake_client.responses.parse_calls) == 1
    assert result.gifs[1].plan.source == "llm:gpt-5.4-mini"
    meta = service.cache.read_meta(result.gifs[0].sheet_path)
    assert meta["source"] == "openai:gpt-image-2" and meta["usage"]["output_tokens"] == 1000 and "Back Squat" in meta["prompt"]


def test_sheet_key_ignores_cue_but_not_style(service, monkeypatch):
    plan = KeyframePlan(exercise="X", keyframes=("a", "b"), cue="one")
    same_drawing = KeyframePlan(exercise="X", keyframes=("a", "b"), cue="two")
    assert service._sheet_key(plan) == service._sheet_key(same_drawing)
    other = ExerciseGifService(service.settings.with_(style="clay"), frame_source=service.frame_source, cache=service.cache)
    assert other._sheet_key(plan) != service._sheet_key(plan)
    before = service._sheet_key(plan)
    monkeypatch.setattr("exercise_gifs.pipeline.PROMPT_VERSION", 999)
    assert service._sheet_key(plan) != before


def test_build_caption():
    plan = KeyframePlan(exercise="Row", keyframes=("a", "b"), cue="Pull to the belly.")
    items = [SessionItem(name="Row", sets=3, reps="10", notes="Pull to the belly."), SessionItem(name="row", sets=4, reps="8")]
    assert build_caption(items, plan) == "Row — 3×10\nPull to the belly."
    assert build_caption([SessionItem(name="Row", notes="Slow eccentric")], plan) == "Row\nPull to the belly.\nSlow eccentric"


def test_generate_session_gifs_convenience(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = generate_session_gifs(["Plank"], output_dir=tmp_path / "o", backend="synthetic", cache_dir=tmp_path / "c")
    assert result.ok and result.gifs[0].path == Path(tmp_path / "o" / "plank.gif")
