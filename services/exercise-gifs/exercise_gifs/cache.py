from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

CACHE_VERSION = 1


def make_key(*parts: Any) -> str:
    payload = json.dumps([CACHE_VERSION, *parts], sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class DiskCache:
    """Two-level on-disk cache.

    Sprite sheets (the expensive image-model call) are cached separately from the GIFs
    built from them, so changing frame timing or size never re-renders a sheet.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.sheets = self.root / "sheets"
        self.gifs = self.root / "gifs"

    def sheet_path(self, key: str) -> Path:
        return self.sheets / f"{key}.png"

    def gif_path(self, key: str) -> Path:
        return self.gifs / f"{key}.gif"

    def get_sheet(self, key: str) -> Image.Image | None:
        path = self.sheet_path(key)
        if not path.is_file():
            return None
        with Image.open(path) as img:
            return img.convert("RGB")

    def put_sheet(self, key: str, image: Image.Image, meta: dict[str, Any]) -> Path:
        path = self.sheet_path(key)
        buffer = _png_bytes(image)
        _atomic_write(path, buffer)
        _atomic_write(path.with_suffix(".json"), _json_bytes(meta))
        return path

    def get_gif(self, key: str) -> Path | None:
        path = self.gif_path(key)
        return path if path.is_file() else None

    def put_gif(self, key: str, data: bytes, meta: dict[str, Any]) -> Path:
        path = self.gif_path(key)
        _atomic_write(path, data)
        _atomic_write(path.with_suffix(".json"), _json_bytes(meta))
        return path

    def read_meta(self, path: Path) -> dict[str, Any] | None:
        meta_path = path.with_suffix(".json")
        if not meta_path.is_file():
            return None
        return json.loads(meta_path.read_text("utf-8"))

    def clear(self) -> int:
        removed = 0
        for folder in (self.sheets, self.gifs):
            if folder.is_dir():
                for child in folder.iterdir():
                    if child.is_file():
                        child.unlink()
                        removed += 1
        return removed


def _png_bytes(image: Image.Image) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _json_bytes(meta: dict[str, Any]) -> bytes:
    return json.dumps(meta, indent=2, sort_keys=True, default=str).encode("utf-8")
