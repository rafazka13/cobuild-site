from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

LoopMode = Literal["pingpong", "cycle"]

_ITEM_LIST_KEYS = (
    "warmup", "exercises", "blocks", "items", "movements", "workout", "main", "sections", "accessories", "cooldown",
)
_ITEM_NAME_KEYS = ("exercise", "name", "movement", "title")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "exercise"


def normalize_name(name: str) -> str:
    """Loose key used for library lookups: lower-case, ascii, single spaces, no punctuation."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).strip()


@dataclass(frozen=True)
class KeyframePlan:
    """Ordered storyboard for one exercise.

    ``keyframes`` describe consecutive poses. With ``loop="pingpong"`` they cover ONE
    direction of the movement (e.g. standing -> bottom of the squat) and the GIF plays
    them forward then backward. With ``loop="cycle"`` they cover the whole repetition
    and the GIF simply loops.
    """

    exercise: str
    keyframes: tuple[str, ...]
    camera: str = "side view, camera at hip height"
    equipment: str = "no equipment"
    setting: str = "a plain gym floor"
    notes: str = ""
    cue: str = ""
    loop: LoopMode = "pingpong"
    source: str = "custom"

    def __post_init__(self) -> None:
        if not self.exercise.strip():
            raise ValueError("KeyframePlan.exercise must not be empty")
        cleaned = tuple(k.strip() for k in self.keyframes if k and k.strip())
        if len(cleaned) < 2:
            raise ValueError(f"{self.exercise!r}: a plan needs at least two keyframes")
        if self.loop not in ("pingpong", "cycle"):
            raise ValueError(f"{self.exercise!r}: loop must be 'pingpong' or 'cycle'")
        object.__setattr__(self, "keyframes", cleaned)

    @property
    def slug(self) -> str:
        return slugify(self.exercise)

    def resampled(self, count: int) -> "KeyframePlan":
        """Return a plan with exactly ``count`` keyframes, keeping first and last."""
        if count < 2:
            raise ValueError("count must be >= 2")
        total = len(self.keyframes)
        if count == total:
            return self
        picked = [self.keyframes[round(i * (total - 1) / (count - 1))] for i in range(count)]
        return replace(self, keyframes=tuple(picked))

    def to_dict(self) -> dict[str, Any]:
        return {
            "exercise": self.exercise,
            "keyframes": list(self.keyframes),
            "camera": self.camera,
            "equipment": self.equipment,
            "setting": self.setting,
            "notes": self.notes,
            "cue": self.cue,
            "loop": self.loop,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeyframePlan":
        return cls(
            exercise=str(data.get("exercise") or data.get("name") or ""),
            keyframes=tuple(str(k) for k in data.get("keyframes", ())),
            camera=str(data.get("camera") or cls.camera),
            equipment=str(data.get("equipment") or cls.equipment),
            setting=str(data.get("setting") or cls.setting),
            notes=str(data.get("notes") or ""),
            cue=str(data.get("cue") or ""),
            loop=data.get("loop") or "pingpong",
            source=str(data.get("source") or "custom"),
        )


@dataclass(frozen=True)
class SessionItem:
    """One prescribed exercise inside a strength session, as the bot describes it."""

    name: str
    sets: int | None = None
    reps: str | None = None
    load: str | None = None
    tempo: str | None = None
    rest: str | None = None
    notes: str | None = None
    plan: KeyframePlan | None = None
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def slug(self) -> str:
        return slugify(self.name)

    def prescription(self) -> str:
        parts: list[str] = []
        if self.sets and self.reps:
            parts.append(f"{self.sets}×{self.reps}")
        elif self.sets:
            parts.append(f"{self.sets} sets")
        elif self.reps:
            parts.append(f"{self.reps} reps")
        if self.load:
            parts.append(f"@ {self.load}")
        if self.tempo:
            parts.append(f"tempo {self.tempo}")
        if self.rest:
            parts.append(f"rest {self.rest}")
        return " ".join(parts)


@dataclass(frozen=True)
class Session:
    name: str | None
    items: tuple[SessionItem, ...]

    def unique_items(self) -> list[SessionItem]:
        seen: set[str] = set()
        unique: list[SessionItem] = []
        for item in self.items:
            if item.slug not in seen:
                seen.add(item.slug)
                unique.append(item)
        return unique


@dataclass
class ExerciseGif:
    """A finished GIF ready to be sent to the athlete."""

    exercise: str
    slug: str
    path: Path
    caption: str
    plan: KeyframePlan
    frame_count: int
    width: int
    height: int
    duration_ms: int
    source: str
    from_cache: bool
    items: list[SessionItem] = field(default_factory=list)
    sheet_path: Path | None = None

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()

    def to_dict(self) -> dict[str, Any]:
        return {
            "exercise": self.exercise,
            "slug": self.slug,
            "path": str(self.path),
            "caption": self.caption,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "duration_ms": self.duration_ms,
            "source": self.source,
            "from_cache": self.from_cache,
            "sheet_path": str(self.sheet_path) if self.sheet_path else None,
            "plan": self.plan.to_dict(),
        }


@dataclass
class SessionGifs:
    session: Session
    gifs: list[ExerciseGif]
    errors: dict[str, str]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.name,
            "gifs": [g.to_dict() for g in self.gifs],
            "errors": dict(self.errors),
        }


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def _item_from_dict(data: dict[str, Any]) -> SessionItem | None:
    name = next((data[k] for k in _ITEM_NAME_KEYS if data.get(k)), None)
    if not name:
        return None
    load = data.get("load") or data.get("weight") or data.get("intensity")
    if load is None and data.get("rpe") is not None:
        load = f"RPE {data['rpe']}"
    if load is None and data.get("percent") is not None:
        load = f"{data['percent']}%"
    plan = None
    if isinstance(data.get("keyframes"), (list, tuple)) and len(data["keyframes"]) >= 2:
        plan_data = {k: v for k, v in data.items() if k in ("keyframes", "camera", "equipment", "setting", "notes", "cue", "loop")}
        plan_data["exercise"] = str(name)
        plan_data["source"] = "session"
        plan = KeyframePlan.from_dict(plan_data)
    return SessionItem(
        name=str(name).strip(),
        sets=_as_int(data.get("sets")),
        reps=_as_text(data.get("reps")),
        load=_as_text(load),
        tempo=_as_text(data.get("tempo")),
        rest=_as_text(data.get("rest")),
        notes=_as_text(data.get("notes") or data.get("cues") or data.get("cue")),
        plan=plan,
        raw=dict(data),
    )


def _collect_items(node: Any, out: list[SessionItem]) -> None:
    if node is None:
        return
    if isinstance(node, str):
        if node.strip():
            out.append(SessionItem(name=node.strip()))
        return
    if isinstance(node, (list, tuple)):
        for child in node:
            _collect_items(child, out)
        return
    if isinstance(node, dict):
        # A dict that holds a list of exercises is a section/superset, never an exercise itself.
        nested = [v for k, v in node.items() if k in _ITEM_LIST_KEYS and isinstance(v, (list, tuple, dict))]
        if nested:
            for child in nested:
                _collect_items(child, out)
            return
        item = _item_from_dict(node)
        if item is not None:
            out.append(item)
        return
    if hasattr(node, "__dict__"):
        _collect_items(vars(node), out)


def normalize_session(session: Any) -> Session:
    """Accept the many shapes a bot might use for a session and return a ``Session``.

    Supported inputs: a single exercise name, a list of names, a list of dicts with
    ``exercise``/``name`` plus optional ``sets``/``reps``/``load``/``rpe``/``tempo``/``rest``/``notes``,
    or a dict with ``name`` and an ``exercises``/``blocks``/``items`` list (nested blocks are flattened).
    An item may carry its own ``keyframes`` list to bypass the planner.
    """
    if isinstance(session, Session):
        return session
    name: str | None = None
    if isinstance(session, dict):
        name = _as_text(session.get("name") or session.get("title") or session.get("session"))
    items: list[SessionItem] = []
    _collect_items(session, items)
    if not items:
        raise ValueError("session contains no exercises")
    return Session(name=name, items=tuple(items))
