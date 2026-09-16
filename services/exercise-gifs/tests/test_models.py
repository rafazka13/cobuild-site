import pytest

from exercise_gifs.models import KeyframePlan, Session, SessionItem, normalize_name, normalize_session, slugify


def test_slugify_and_normalize_name():
    assert slugify("Bulgarian Split Squat (DB)") == "bulgarian-split-squat-db"
    assert slugify("  ") == "exercise"
    assert slugify("Café Row") == "cafe-row"
    assert normalize_name("Push-Up!") == "push up"
    assert normalize_name("  Back   Squat ") == "back squat"


def test_keyframe_plan_validation():
    with pytest.raises(ValueError):
        KeyframePlan(exercise="", keyframes=("a", "b"))
    with pytest.raises(ValueError):
        KeyframePlan(exercise="X", keyframes=("only one",))
    with pytest.raises(ValueError):
        KeyframePlan(exercise="X", keyframes=("a", "b"), loop="bounce")
    plan = KeyframePlan(exercise="X", keyframes=(" a ", "", "b", "   "))
    assert plan.keyframes == ("a", "b")
    assert plan.slug == "x"


def test_resampled_keeps_ends():
    plan = KeyframePlan(exercise="X", keyframes=tuple("abcdef"))
    assert plan.resampled(6) is plan
    assert plan.resampled(4).keyframes == ("a", "c", "d", "f")
    assert plan.resampled(2).keyframes == ("a", "f")
    up = plan.resampled(9).keyframes
    assert len(up) == 9 and up[0] == "a" and up[-1] == "f"
    with pytest.raises(ValueError):
        plan.resampled(1)


def test_plan_dict_round_trip():
    plan = KeyframePlan(exercise="X", keyframes=("a", "b"), camera="front", equipment="bar", setting="rack", notes="n", cue="c", loop="cycle", source="library")
    assert KeyframePlan.from_dict(plan.to_dict()) == plan
    assert KeyframePlan.from_dict({"name": "Y", "keyframes": ["a", "b"]}).exercise == "Y"


def test_normalize_session_shapes():
    assert [i.name for i in normalize_session("Back Squat").items] == ["Back Squat"]
    assert [i.name for i in normalize_session(["A", " B "]).items] == ["A", "B"]

    items = normalize_session([
        {"exercise": "Back Squat", "sets": 4, "reps": 6, "rpe": 8, "rest": "3 min"},
        {"name": "Bench", "sets": "3", "reps": [8, 8, 6], "percent": 80, "tempo": "3-1-1", "notes": "pause"},
        {"movement": "Row", "weight": "60 kg"},
    ]).items
    assert items[0].sets == 4 and items[0].reps == "6" and items[0].load == "RPE 8" and items[0].rest == "3 min"
    assert items[1].sets == 3 and items[1].reps == "8, 8, 6" and items[1].load == "80%" and items[1].tempo == "3-1-1" and items[1].notes == "pause"
    assert items[2].name == "Row" and items[2].load == "60 kg"


def test_normalize_session_nested_blocks_and_ordering():
    session = normalize_session({
        "name": "Lower A",
        "warmup": ["Goblet Squat"],
        "blocks": [
            {"name": "A", "exercises": [{"exercise": "Back Squat", "sets": 5, "reps": 5}]},
            {"name": "B", "exercises": ["Romanian Deadlift", {"exercise": "Plank", "reps": "45 s"}]},
        ],
        "accessories": [{"exercise": "Leg Curl"}],
    })
    assert session.name == "Lower A"
    assert [i.name for i in session.items] == ["Goblet Squat", "Back Squat", "Romanian Deadlift", "Plank", "Leg Curl"]


def test_superset_with_children_is_not_an_exercise():
    session = normalize_session({"exercise": "Superset", "sets": 3, "exercises": ["Push-up", "Row"]})
    assert [i.name for i in session.items] == ["Push-up", "Row"]


def test_item_with_own_keyframes_becomes_plan():
    session = normalize_session([{"exercise": "Custom Move", "keyframes": ["start", "middle", "end"], "camera": "front view", "loop": "cycle"}])
    plan = session.items[0].plan
    assert plan is not None and plan.source == "session" and plan.loop == "cycle" and plan.camera == "front view"
    assert plan.keyframes == ("start", "middle", "end")


def test_empty_session_raises():
    with pytest.raises(ValueError):
        normalize_session([])
    with pytest.raises(ValueError):
        normalize_session({"exercises": []})
    with pytest.raises(ValueError):
        normalize_session({"name": "Lower A", "blocks": [{"name": "A", "exercises": []}]})
    # A dict with just a name is a single exercise, not an empty session.
    assert normalize_session({"name": "Back Squat"}).items[0].name == "Back Squat"


def test_prescription_formatting():
    assert SessionItem(name="X", sets=4, reps="6").prescription() == "4×6"
    assert SessionItem(name="X", sets=4).prescription() == "4 sets"
    assert SessionItem(name="X", reps="8").prescription() == "8 reps"
    assert SessionItem(name="X", sets=3, reps="10", load="80 kg", tempo="3-0-1", rest="90 s").prescription() == "3×10 @ 80 kg tempo 3-0-1 rest 90 s"
    assert SessionItem(name="X").prescription() == ""


def test_unique_items_dedups_by_slug():
    session = Session(name=None, items=(SessionItem(name="Back Squat"), SessionItem(name="back squat"), SessionItem(name="Row")))
    assert [i.name for i in session.unique_items()] == ["Back Squat", "Row"]
