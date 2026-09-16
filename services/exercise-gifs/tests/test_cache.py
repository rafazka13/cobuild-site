import json

from PIL import Image

from exercise_gifs.cache import DiskCache, make_key


def test_make_key_is_stable_and_order_insensitive():
    assert make_key("a", {"x": 1, "y": 2}) == make_key("a", {"y": 2, "x": 1})
    assert make_key("a", {"x": 1}) != make_key("a", {"x": 2})
    assert make_key("a") != make_key("b")
    assert len(make_key("a")) == 24


def test_sheet_round_trip(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    assert cache.get_sheet("missing") is None
    image = Image.new("RGB", (30, 20), (10, 20, 30))
    path = cache.put_sheet("k1", image, {"exercise": "X"})
    assert path == cache.sheet_path("k1") and path.is_file()
    back = cache.get_sheet("k1")
    assert back.size == (30, 20) and back.getpixel((0, 0)) == (10, 20, 30)
    assert json.loads(path.with_suffix(".json").read_text())["exercise"] == "X"
    assert cache.read_meta(path) == {"exercise": "X"}


def test_gif_round_trip_and_clear(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    assert cache.get_gif("nope") is None
    path = cache.put_gif("g1", b"GIF89a-bytes", {"frames": 3})
    assert cache.get_gif("g1") == path and path.read_bytes() == b"GIF89a-bytes"
    cache.put_sheet("s1", Image.new("RGB", (4, 4)), {})
    assert cache.clear() == 4
    assert cache.get_gif("g1") is None and cache.get_sheet("s1") is None
    assert cache.read_meta(path) is None
