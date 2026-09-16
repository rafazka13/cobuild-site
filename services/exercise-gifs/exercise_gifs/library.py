from __future__ import annotations

import importlib
import re
import threading
from typing import Any, Iterable

from . import library_data
from .models import KeyframePlan, normalize_name

_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_PRESCRIPTION = re.compile(r"\b\d+\s*[x×]\s*\d+\b|\b\d+\s*(reps?|sets?|kg|lbs?|%|rpe)\b|\brpe\s*\d+\b", re.IGNORECASE)


def _clean_query(name: str) -> str:
    text = _PAREN.sub(" ", name)
    text = _PRESCRIPTION.sub(" ", text)
    text = text.replace("&", " and ").replace("/", " ")
    return normalize_name(text)


class ExerciseLibrary:
    """Registry of curated ``KeyframePlan``s with alias and fuzzy lookup."""

    _default: "ExerciseLibrary | None" = None
    _default_lock = threading.Lock()

    def __init__(self, entries: Iterable[dict[str, Any]] | None = None):
        self._plans: dict[str, KeyframePlan] = {}
        self._aliases: dict[str, str] = {}
        self._categories: dict[str, str] = {}
        for entry in entries or ():
            self.register(entry)

    @classmethod
    def default(cls) -> "ExerciseLibrary":
        """The bundled library, loaded once per process."""
        with cls._default_lock:
            if cls._default is None:
                library = cls()
                for module_name in library_data.MODULES:
                    try:
                        module = importlib.import_module(f"{library_data.__name__}.{module_name}")
                    except ImportError:
                        continue
                    for entry in getattr(module, "EXERCISES", ()):
                        library.register(entry)
                cls._default = library
            return cls._default

    def register(self, entry: dict[str, Any]) -> KeyframePlan:
        name = str(entry.get("name", "")).strip()
        if not name:
            raise ValueError("library entry needs a name")
        key = normalize_name(name)
        if key in self._plans:
            raise ValueError(f"duplicate library exercise: {name!r}")
        if key in self._aliases:
            raise ValueError(f"{name!r} collides with an alias of {self._plans[self._aliases[key]].exercise!r}")
        keyframes = entry.get("keyframes") or ()
        if not isinstance(keyframes, (list, tuple)) or len(keyframes) < 2:
            raise ValueError(f"{name!r}: keyframes must be a list of at least two descriptions")
        plan = KeyframePlan(
            exercise=name,
            keyframes=tuple(str(k) for k in keyframes),
            camera=str(entry.get("camera") or KeyframePlan.camera),
            equipment=str(entry.get("equipment") or KeyframePlan.equipment),
            setting=str(entry.get("setting") or KeyframePlan.setting),
            notes=str(entry.get("notes") or ""),
            cue=str(entry.get("cue") or ""),
            loop=entry.get("loop") or "pingpong",
            source="library",
        )
        self._plans[key] = plan
        self._categories[key] = str(entry.get("category") or "")
        for alias in entry.get("aliases") or ():
            alias_key = normalize_name(str(alias))
            if not alias_key or alias_key == key:
                continue
            owner = self._aliases.get(alias_key)
            if owner is not None and owner != key:
                raise ValueError(f"alias {alias!r} is claimed by both {self._plans[owner].exercise!r} and {name!r}")
            if alias_key in self._plans and alias_key != key:
                raise ValueError(f"alias {alias!r} of {name!r} collides with exercise {self._plans[alias_key].exercise!r}")
            self._aliases[alias_key] = key
        return plan

    def find(self, name: str) -> KeyframePlan | None:
        query = _clean_query(name)
        if not query:
            return None
        key = self._resolve_exact(query)
        if key is None:
            key = self._resolve_token_set(query)
        if key is None:
            key = self._resolve_substring(query)
        return self._plans[key] if key else None

    def category(self, name: str) -> str | None:
        plan = self.find(name)
        return self._categories.get(normalize_name(plan.exercise)) if plan else None

    def names(self) -> list[str]:
        return [plan.exercise for plan in self._plans.values()]

    def plans(self) -> list[KeyframePlan]:
        return list(self._plans.values())

    def categories(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for key, plan in self._plans.items():
            grouped.setdefault(self._categories.get(key, ""), []).append(plan.exercise)
        return grouped

    def __len__(self) -> int:
        return len(self._plans)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.find(name) is not None

    # -- lookup strategies -------------------------------------------------

    def _resolve_exact(self, query: str) -> str | None:
        if query in self._plans:
            return query
        return self._aliases.get(query)

    def _resolve_token_set(self, query: str) -> str | None:
        tokens = frozenset(query.split())
        for key in self._all_keys():
            if frozenset(key.split()) == tokens:
                return self._canonical(key)
        return None

    def _resolve_substring(self, query: str) -> str | None:
        """Longest library name/alias appearing as whole words inside the query.

        Single-word keys only match single-word queries so that e.g. "squat jump" is not
        mistaken for a back squat.
        """
        query_tokens = query.split()
        best_key: str | None = None
        best_len = 0
        for key in self._all_keys():
            key_tokens = key.split()
            if len(key_tokens) == 1 and len(query_tokens) != 1:
                continue
            if len(key_tokens) <= best_len:
                continue
            if _contains_phrase(query_tokens, key_tokens):
                best_key, best_len = key, len(key_tokens)
        return self._canonical(best_key) if best_key else None

    def _all_keys(self) -> Iterable[str]:
        yield from self._plans.keys()
        yield from self._aliases.keys()

    def _canonical(self, key: str) -> str:
        return self._aliases.get(key, key)


def _contains_phrase(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))
