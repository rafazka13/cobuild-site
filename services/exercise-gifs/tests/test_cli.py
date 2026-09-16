import json

import pytest

from exercise_gifs.cli import main


def _run(capsys, *args):
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_list(capsys):
    code, out, err = _run(capsys, "--list")
    assert code == 0 and "Back Squat" in out and "[lower_body]" in out and "exercises" in err


def test_names_to_json_manifest(capsys, tmp_path):
    code, out, _ = _run(capsys, "Back Squat", "Plank", "--synthetic", "--out", str(tmp_path / "o"), "--cache-dir", str(tmp_path / "c"), "--json")
    assert code == 0
    manifest = json.loads(out)
    assert [g["slug"] for g in manifest["gifs"]] == ["back-squat", "plank"] and manifest["errors"] == {}
    assert (tmp_path / "o" / "plank.gif").is_file()


def test_plain_output_prints_paths(capsys, tmp_path):
    code, out, _ = _run(capsys, "Plank", "--synthetic", "--out", str(tmp_path / "o"), "--cache-dir", str(tmp_path / "c"))
    assert code == 0 and out.strip().endswith("plank.gif")


def test_session_file(capsys, tmp_path):
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"name": "S", "exercises": [{"exercise": "Bench Press", "sets": 3, "reps": 5}]}))
    code, out, _ = _run(capsys, "--session", str(session), "--synthetic", "--out", str(tmp_path / "o"), "--cache-dir", str(tmp_path / "c"), "--json")
    assert code == 0
    manifest = json.loads(out)
    assert manifest["session"] == "S" and manifest["gifs"][0]["caption"].startswith("Bench Press — 3×5")


def test_names_and_session_conflict(tmp_path):
    session = tmp_path / "session.json"
    session.write_text("[\"Plank\"]")
    with pytest.raises(SystemExit):
        main(["Plank", "--session", str(session), "--synthetic"])


def test_no_input_is_usage_error(capsys):
    code, _, err = _run(capsys)
    assert code == 2 and "at least one exercise" in err


def test_bad_option_is_error(capsys, tmp_path):
    code, _, err = _run(capsys, "Plank", "--synthetic", "--grid", "9x9", "--cache-dir", str(tmp_path))
    assert code == 2 and "error:" in err


def test_grid_changes_frame_count(capsys, tmp_path):
    code, out, _ = _run(capsys, "Plank", "--synthetic", "--grid", "2x2", "--frame-size", "120", "--out", str(tmp_path / "o"), "--cache-dir", str(tmp_path / "c"), "--json")
    gif = json.loads(out)["gifs"][0]
    assert code == 0 and gif["frame_count"] == 6 and gif["width"] == 120


def test_failing_exercise_exit_code(capsys, tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    code, out, err = _run(capsys, "Plank", "--synthetic", "--planner", "llm", "--out", str(tmp_path / "o"), "--cache-dir", str(tmp_path / "c"), "--json")
    assert code == 1 and "failed: plank" in err
    assert json.loads(out)["gifs"] == []


def test_warm_named(capsys, tmp_path):
    code, out, _ = _run(capsys, "--warm", "Plank", "--synthetic", "--out", str(tmp_path / "o"), "--cache-dir", str(tmp_path / "c"))
    assert code == 0 and out.strip().endswith("plank.gif")
