from types import SimpleNamespace

import pytest

from exercise_gifs.errors import PlanningError, SettingsError
from exercise_gifs.library import ExerciseLibrary
from exercise_gifs.planner import KeyframePlanner, LLMKeyframePlan, generic_plan
from tests.conftest import FakeResponses


class ExplodingClient:
    """Any attribute access means the planner touched the network client when it should not."""

    def __getattr__(self, name):
        raise AssertionError(f"client.{name} accessed")


def test_generic_plan_shape():
    plan = generic_plan("Zercher Squat", 6)
    assert plan.source == "generic" and len(plan.keyframes) == 6
    assert plan.keyframes[0].startswith("the start position") and plan.keyframes[-1].startswith("the end position")
    assert "50%" in plan.keyframes[3] or "60%" in plan.keyframes[3]


def test_library_mode_never_calls_client():
    planner = KeyframePlanner(mode="library", client=ExplodingClient(), keyframe_count=4)
    assert planner.plan("Back Squat").source == "library"
    generic = planner.plan("Zercher Squat")
    assert generic.source == "generic" and len(generic.keyframes) == 4


def test_auto_mode_uses_library_first():
    client = SimpleNamespace(responses=FakeResponses())
    planner = KeyframePlanner(mode="auto", client=client)
    assert planner.plan("heavy back squat 5x5").exercise == "Back Squat"
    assert client.responses.parse_calls == []


def test_auto_mode_falls_back_to_llm():
    client = SimpleNamespace(responses=FakeResponses(keyframes=8))
    planner = KeyframePlanner(mode="auto", client=client, model="gpt-5.4-mini", keyframe_count=6)
    plan = planner.plan("Zercher Squat", hints="keep the elbows high")
    call = client.responses.parse_calls[0]
    assert call["model"] == "gpt-5.4-mini" and call["text_format"] is LLMKeyframePlan
    assert "Zercher Squat" in call["input"] and "keep the elbows high" in call["input"] and "6" in call["input"]
    assert "storyboards" in call["instructions"]
    assert plan.source == "llm:gpt-5.4-mini" and plan.exercise == "Zercher Squat" and len(plan.keyframes) == 6
    assert plan.keyframes[0] == "llm pose 0" and plan.keyframes[-1] == "llm pose 7"
    assert plan.cue == "Elbows tight, chest up." and plan.loop == "pingpong"


def test_llm_mode_bypasses_library():
    client = SimpleNamespace(responses=FakeResponses())
    planner = KeyframePlanner(mode="llm", client=client)
    plan = planner.plan("Back Squat")
    assert client.responses.parse_calls and plan.source.startswith("llm:")


def test_llm_failures_become_planning_errors():
    responses = FakeResponses()
    responses.error = RuntimeError("boom")
    with pytest.raises(PlanningError, match="boom"):
        KeyframePlanner(mode="llm", client=SimpleNamespace(responses=responses)).plan("X")

    responses = FakeResponses()
    responses.parsed = None
    with pytest.raises(PlanningError, match="no structured output"):
        KeyframePlanner(mode="llm", client=SimpleNamespace(responses=responses)).plan("X")

    responses = FakeResponses()
    responses.parsed = LLMKeyframePlan(exercise="X", camera="c", equipment="e", setting="s", loop="cycle", keyframes=["one", ""], cue="")
    with pytest.raises(PlanningError, match="fewer than two"):
        KeyframePlanner(mode="llm", client=SimpleNamespace(responses=responses)).plan("X")


def test_empty_name_and_bad_mode():
    with pytest.raises(PlanningError):
        KeyframePlanner(mode="library").plan("   ")
    with pytest.raises(SettingsError):
        KeyframePlanner(mode="psychic")


def test_missing_api_key_is_a_settings_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    planner = KeyframePlanner(mode="llm", library=ExerciseLibrary([]))
    with pytest.raises(SettingsError, match="OPENAI_API_KEY"):
        planner.plan("Anything")
