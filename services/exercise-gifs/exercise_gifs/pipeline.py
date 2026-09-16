from __future__ import annotations

import hashlib
import logging
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable

from PIL import Image

from .cache import DiskCache, make_key
from .errors import ExerciseGifError, SheetValidationError
from .frames.base import FrameSource, RenderedSheet
from .frames.synthetic import SyntheticFrameSource
from .gif import assemble_gif, read_gif_info
from .library import ExerciseLibrary
from .models import ExerciseGif, KeyframePlan, Session, SessionGifs, SessionItem, normalize_session
from .planner import KeyframePlanner
from .settings import Settings
from .sprites import blank_panels, slice_grid

log = logging.getLogger("exercise_gifs")

ProgressCallback = Callable[[dict[str, Any]], None]


def build_caption(items: list[SessionItem], plan: KeyframePlan) -> str:
    first = items[0]
    prescription = first.prescription()
    lines = [f"{first.name} — {prescription}" if prescription else first.name]
    if plan.cue.strip():
        lines.append(plan.cue.strip())
    if first.notes and first.notes.strip() and first.notes.strip() != plan.cue.strip():
        lines.append(first.notes.strip())
    return "\n".join(lines)


class ExerciseGifService:
    """Session in, GIFs out. Construct once and reuse; it is safe to call from threads."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        frame_source: FrameSource | None = None,
        planner: KeyframePlanner | None = None,
        cache: DiskCache | None = None,
        library: ExerciseLibrary | None = None,
        client: Any | None = None,
    ):
        self.settings = settings if settings is not None else Settings.from_env()
        self._key_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self.library = library if library is not None else ExerciseLibrary.default()
        self.cache = cache if cache is not None else DiskCache(self.settings.cache_dir)
        self.frame_source = frame_source if frame_source is not None else self._default_frame_source(client)
        planner_mode = self.settings.planner
        if planner_mode == "auto" and self.settings.backend == "synthetic":
            planner_mode = "library"  # a no-network backend must never wait on the GPT planner
        self.planner = planner if planner is not None else KeyframePlanner(
            mode=planner_mode,
            library=self.library,
            client=client,
            model=self.settings.planner_model,
            keyframe_count=self.settings.keyframe_count,
            api_key=self.settings.api_key,
            timeout=min(self.settings.request_timeout, 120.0),
        )

    def _default_frame_source(self, client: Any | None) -> FrameSource:
        if self.settings.backend == "synthetic":
            return SyntheticFrameSource()
        from .frames.openai_images import OpenAIImageFrameSource

        return OpenAIImageFrameSource(
            client,
            model=self.settings.image_model,
            quality=self.settings.image_quality,
            moderation=self.settings.image_moderation,
            timeout=self.settings.request_timeout,
            api_key=self.settings.api_key,
            reference_image=self.settings.reference_image,
        )

    # -- public API ------------------------------------------------------------

    def plan(self, exercise: str, *, hints: str | None = None) -> KeyframePlan:
        return self.planner.plan(exercise, hints=hints).resampled(self.settings.keyframe_count)

    def generate_for_exercise(
        self,
        exercise: str | SessionItem | KeyframePlan,
        *,
        output_dir: Path | str | None = None,
        force: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> ExerciseGif:
        if isinstance(exercise, KeyframePlan):
            item = SessionItem(name=exercise.exercise, plan=exercise)
        elif isinstance(exercise, SessionItem):
            item = exercise
        else:
            item = SessionItem(name=str(exercise))
        notify = _notifier(on_progress)
        plan = self._plan_for(item, notify)
        return self._render_plan(plan, [item], self._resolve_output_dir(output_dir), force, notify)

    def generate_for_session(
        self,
        session: Any,
        *,
        output_dir: Path | str | None = None,
        force: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> SessionGifs:
        """Generate one GIF per distinct exercise in ``session`` (see ``normalize_session``).

        Failures are collected per exercise in ``SessionGifs.errors`` instead of aborting the
        whole session, so the bot can still send the GIFs that succeeded.
        """
        parsed = normalize_session(session)
        out_dir = self._resolve_output_dir(output_dir)
        notify = _notifier(on_progress)
        errors: dict[str, str] = {}

        # 1. Resolve plans for each distinct name. "Back Squat" and "Heavy back squat 5x5"
        #    both land on the library's Back Squat, so grouping happens on the *plan*.
        raw_groups: dict[str, list[SessionItem]] = {}
        for item in parsed.items:
            raw_groups.setdefault(item.slug, []).append(item)
        plans: dict[str, KeyframePlan] = {}

        def resolve(slug: str, items: list[SessionItem]) -> None:
            try:
                plans[slug] = self._plan_for(items[0], notify)
            except Exception as exc:  # noqa: BLE001 - one bad exercise must not sink the session
                self._record_error(errors, slug, items[0], exc, notify)

        self._run_parallel(resolve, raw_groups)

        # 2. Render one GIF per distinct plan.
        plan_groups: dict[str, tuple[KeyframePlan, list[SessionItem]]] = {}
        for slug, items in raw_groups.items():
            plan = plans.get(slug)
            if plan is None:
                continue
            existing = plan_groups.get(plan.slug)
            if existing is None:
                plan_groups[plan.slug] = (plan, list(items))
            else:
                existing[1].extend(items)
        results: dict[str, ExerciseGif] = {}

        def render(slug: str, group: tuple[KeyframePlan, list[SessionItem]]) -> None:
            plan, items = group
            try:
                results[slug] = self._render_plan(plan, items, out_dir, force, notify)
            except Exception as exc:  # noqa: BLE001
                self._record_error(errors, slug, items[0], exc, notify)

        self._run_parallel(render, plan_groups)
        ordered = [results[slug] for slug in plan_groups if slug in results]
        return SessionGifs(session=parsed, gifs=ordered, errors=errors)

    def _run_parallel(self, fn: Callable[[str, Any], None], groups: dict[str, Any]) -> None:
        if not groups:
            return
        workers = max(1, min(self.settings.max_workers, len(groups)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="exercise-gif") as pool:
            futures = [pool.submit(fn, slug, group) for slug, group in groups.items()]
            for future in futures:
                future.result()

    @staticmethod
    def _record_error(errors: dict[str, str], slug: str, item: SessionItem, exc: Exception, notify: ProgressCallback) -> None:
        log.warning("exercise %r failed: %s", item.name, exc)
        errors[slug] = f"{type(exc).__name__}: {exc}"
        notify({"stage": "error", "exercise": item.name, "error": str(exc)})

    def warm(self, exercises: Iterable[str] | None = None, *, on_progress: ProgressCallback | None = None) -> SessionGifs:
        """Pre-render GIFs (default: the whole bundled library) so live sessions hit the cache."""
        names = list(exercises) if exercises is not None else self.library.names()
        return self.generate_for_session({"name": "warm-up cache", "exercises": names}, on_progress=on_progress)

    # -- internals ---------------------------------------------------------------

    def _resolve_output_dir(self, output_dir: Path | str | None) -> Path:
        path = Path(output_dir) if output_dir is not None else Path(self.settings.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _plan_for(self, item: SessionItem, notify: ProgressCallback) -> KeyframePlan:
        notify({"stage": "plan", "exercise": item.name})
        plan = item.plan if item.plan is not None else self.planner.plan(item.name, hints=item.notes)
        return plan.resampled(self.settings.keyframe_count)

    def _render_plan(
        self,
        plan: KeyframePlan,
        items: list[SessionItem],
        out_dir: Path,
        force: bool,
        notify: ProgressCallback,
    ) -> ExerciseGif:
        s = self.settings
        label = items[0].name
        sheet_key = self._sheet_key(plan)
        # Serialise work on one key so two athletes asking for the same exercise at the same
        # moment cost one image-model call, not two.
        with self._key_lock(sheet_key):
            sheet = None if force else self.cache.get_sheet(sheet_key)
            sheet_cached = sheet is not None
            if sheet is None:
                notify({"stage": "sheet", "exercise": label, "source": self._source_id()})
                rendered = self._render_valid_sheet(plan, label, notify)
                sheet = rendered.image
                self.cache.put_sheet(
                    sheet_key,
                    sheet,
                    {"exercise": plan.exercise, "plan": plan.to_dict(), "prompt": rendered.prompt, "source": rendered.source,
                     "usage": rendered.usage, "style": s.style, "grid": f"{s.grid_cols}x{s.grid_rows}"},
                )
            else:
                notify({"stage": "sheet_cached", "exercise": label})
            sheet_path = self.cache.sheet_path(sheet_key)

            frames = self._usable_frames(sheet, plan.exercise)
            gif_key = make_key("gif", sheet_key, s.frame_size, s.frame_ms, s.effective_hold_ends_ms, plan.loop, s.colors, s.snap_grid)
            cached_gif = None if force else self.cache.get_gif(gif_key)
            gif_cached = cached_gif is not None
            if cached_gif is None:
                notify({"stage": "gif", "exercise": label, "frames": len(frames)})
                data = assemble_gif(
                    frames,
                    size=s.frame_size,
                    frame_ms=s.frame_ms,
                    loop=plan.loop,
                    hold_ends_ms=s.effective_hold_ends_ms,
                    colors=s.colors,
                )
                cached_gif = self.cache.put_gif(gif_key, data, {"exercise": plan.exercise, "sheet": sheet_key, "frames": len(frames)})
            else:
                notify({"stage": "gif_cached", "exercise": label})
                data = cached_gif.read_bytes()

        target = out_dir / f"{plan.slug}.gif"
        if target.resolve() != cached_gif.resolve():
            shutil.copyfile(cached_gif, target)
        info = read_gif_info(data)
        result = ExerciseGif(
            exercise=plan.exercise,
            slug=plan.slug,
            path=target,
            caption=build_caption(items, plan),
            plan=plan,
            frame_count=info.frame_count,
            width=info.width,
            height=info.height,
            duration_ms=info.duration_ms,
            source=self._source_id(),
            from_cache=sheet_cached and gif_cached,
            items=list(items),
            sheet_path=sheet_path if sheet_path.is_file() else None,
        )
        notify({"stage": "done", "exercise": label, "path": str(target), "from_cache": result.from_cache})
        return result

    def _key_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = self._key_locks[key] = threading.Lock()
            return lock

    def _render_valid_sheet(self, plan: KeyframePlan, label: str, notify: ProgressCallback) -> RenderedSheet:
        s = self.settings
        count = s.keyframe_count
        best: tuple[int, RenderedSheet] | None = None
        for attempt in range(1, s.max_attempts + 1):
            rendered = self.frame_source.render_sheet(
                plan, cols=s.grid_cols, rows=s.grid_rows, style=s.style, athlete=s.athlete, attempt=attempt
            )
            blanks = blank_panels(slice_grid(rendered.image, s.grid_cols, s.grid_rows, snap=s.snap_grid))
            if not blanks:
                return rendered
            log.info("%s: attempt %d produced %d blank panel(s) %s", label, attempt, len(blanks), blanks)
            notify({"stage": "retry", "exercise": label, "attempt": attempt, "blank_panels": blanks})
            if best is None or len(blanks) < best[0]:
                best = (len(blanks), rendered)
        assert best is not None
        usable = count - best[0]
        if usable < max(2, count // 2):
            raise SheetValidationError(
                f"{label}: the image model left {best[0]} of {count} panels empty after {s.max_attempts} attempt(s)"
            )
        log.warning("%s: using best sheet with %d blank panel(s) dropped", label, best[0])
        return best[1]

    def _usable_frames(self, sheet: Image.Image, label: str) -> list[Image.Image]:
        s = self.settings
        frames = slice_grid(sheet, s.grid_cols, s.grid_rows, snap=s.snap_grid)
        blanks = set(blank_panels(frames))
        frames = [f for i, f in enumerate(frames) if i not in blanks]
        if len(frames) < 2:
            raise SheetValidationError(f"{label}: fewer than two usable panels on the sheet")
        return frames

    def _source_id(self) -> str:
        return getattr(self.frame_source, "source_id", getattr(self.frame_source, "name", "unknown"))

    def _sheet_key(self, plan: KeyframePlan) -> str:
        s = self.settings
        plan_data = plan.to_dict()
        plan_data.pop("source", None)
        plan_data.pop("cue", None)  # captions do not affect the drawing
        reference = None
        if s.reference_image is not None:
            reference = hashlib.sha256(Path(s.reference_image).read_bytes()).hexdigest()[:16]
        return make_key(
            "sheet", plan_data, s.style, s.athlete, self._source_id(),
            getattr(self.frame_source, "quality", None), s.grid_cols, s.grid_rows, reference,
        )


def _notifier(callback: ProgressCallback | None) -> ProgressCallback:
    if callback is None:
        return lambda event: None

    def safe(event: dict[str, Any]) -> None:
        try:
            callback(event)
        except Exception:  # noqa: BLE001 - a broken progress hook must never break rendering
            log.exception("progress callback raised")

    return safe


def generate_session_gifs(session: Any, *, output_dir: Path | str | None = None, force: bool = False, **overrides: Any) -> SessionGifs:
    """One-call convenience: ``generate_session_gifs(session_dict, backend="synthetic")``."""
    settings = Settings.from_env(**overrides)
    return ExerciseGifService(settings).generate_for_session(session, output_dir=output_dir, force=force)


__all__ = ["ExerciseGifService", "ExerciseGifError", "Session", "SessionGifs", "build_caption", "generate_session_gifs"]
