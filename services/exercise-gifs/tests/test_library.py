import pytest

from exercise_gifs.library import ExerciseLibrary
from exercise_gifs.models import normalize_name

SQUAT = {
    "name": "Back Squat",
    "aliases": ["barbell back squat", "squat"],
    "category": "lower_body",
    "camera": "side view, athlete facing left",
    "equipment": "a barbell on the upper back",
    "setting": "a squat rack",
    "keyframes": ["standing tall", "quarter squat", "parallel", "deep squat"],
    "cue": "Drive up.",
}
BOX_JUMP = {
    "name": "Box Jump",
    "aliases": ["box jumps"],
    "category": "lower_body",
    "camera": "side view, athlete facing left",
    "equipment": "a plyo box",
    "setting": "a gym floor",
    "loop": "cycle",
    "keyframes": ["standing", "dip", "jump", "land", "stand"],
}


@pytest.fixture
def library():
    return ExerciseLibrary([SQUAT, BOX_JUMP])


def test_register_validation():
    with pytest.raises(ValueError):
        ExerciseLibrary([{"name": "", "keyframes": ["a", "b"]}])
    with pytest.raises(ValueError):
        ExerciseLibrary([{"name": "One", "keyframes": ["only"]}])
    with pytest.raises(ValueError):
        ExerciseLibrary([SQUAT, dict(SQUAT)])
    with pytest.raises(ValueError):
        ExerciseLibrary([SQUAT, {"name": "Other", "aliases": ["squat"], "keyframes": ["a", "b"]}])
    with pytest.raises(ValueError):
        ExerciseLibrary([SQUAT, {"name": "Other", "aliases": ["back squat"], "keyframes": ["a", "b"]}])


def test_registered_plan_fields(library):
    plan = library.find("Back Squat")
    assert plan.source == "library" and plan.cue == "Drive up." and plan.loop == "pingpong"
    assert library.find("Box Jump").loop == "cycle"
    assert library.category("box jumps") == "lower_body"
    assert len(library) == 2 and "squat" in library and "yoga" not in library
    assert library.categories() == {"lower_body": ["Back Squat", "Box Jump"]}


@pytest.mark.parametrize(
    "query",
    ["Back Squat", "back squat", "BARBELL BACK SQUAT", "squat", "squat back", "Heavy back squat 5x5", "Back Squat (paused) 3x5 @ RPE 8", "back-squat", "Back squat, 4 x 6"],
)
def test_find_resolves_variants(library, query):
    assert library.find(query).exercise == "Back Squat"


def test_single_word_key_needs_single_word_query(library):
    assert library.find("squat jump") is None
    assert library.find("squat") is not None


def test_find_unknown_and_empty(library):
    assert library.find("Yoga Flow") is None
    assert library.find("") is None
    assert library.find("3x5") is None


def test_default_library_quality():
    lib = ExerciseLibrary.default()
    assert len(lib) >= 60
    assert set(lib.categories()) == {"lower_body", "upper_push", "upper_pull", "core_and_carries"}
    seen = set()
    for plan in lib.plans():
        assert 4 <= len(plan.keyframes) <= 8, plan.exercise
        for keyframe in plan.keyframes:
            assert 8 <= len(keyframe.split()) <= 45, (plan.exercise, keyframe)
        assert plan.camera.strip() and plan.equipment.strip() and plan.setting.strip(), plan.exercise
        assert plan.loop in ("pingpong", "cycle")
        assert plan.source == "library"
        assert lib.find(plan.exercise) is plan, plan.exercise
        key = normalize_name(plan.exercise)
        assert key not in seen
        seen.add(key)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("heavy back squat 5x5", "Back Squat"),
        ("RDL 3x8", "Romanian Deadlift"),
        ("Bulgarian split squat (dumbbells) 3x10", "Bulgarian Split Squat"),
        ("Push-ups", "Push-up"),
        ("bench press 4x6 @ 80%", "Bench Press"),
        ("Pull ups", "Pull-up"),
        ("farmers carry", "Farmer's Carry"),
        ("plank 3x45s", "Plank"),
    ],
)
def test_default_library_coach_queries(query, expected):
    assert ExerciseLibrary.default().find(query).exercise == expected
