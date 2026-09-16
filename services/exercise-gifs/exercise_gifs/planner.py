from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel

from .errors import PlanningError, SettingsError
from .library import ExerciseLibrary
from .models import KeyframePlan
from .settings import DEFAULT_PLANNER_MODEL

PLANNER_INSTRUCTIONS = """You write storyboards for short, looping exercise-demonstration animations used by a strength coaching app.

Given an exercise name (and optional notes from the coach), describe the poses an illustrator must draw so that the panels, shown one after another, animate one repetition.

Rules:
- Produce exactly the requested number of keyframes, in order.
- If the movement is symmetric (the way back mirrors the way there, e.g. squat, press, row, curl), set loop to "pingpong" and describe ONE direction only, from the start position to the end position. The animation will play the frames forward and then backward.
- If the movement is not symmetric (e.g. burpee, clean, box jump, turkish get-up), set loop to "cycle" and describe the whole repetition, with the last keyframe close to the first.
- Every keyframe must be a concrete, drawable description of the whole body: joint angles, where the load is, where the hands and feet are, torso angle. 10-35 words each. No coaching advice, no counting, no text overlays.
- Keep the camera fixed and describe it once (e.g. "side view, camera at hip height, athlete facing left"). Choose the angle that shows the movement best.
- equipment: what the athlete holds or uses, with how it is loaded, or "no equipment".
- setting: a short description of the immediate surroundings (e.g. "a flat bench on a plain gym floor").
- exercise: the clean, canonical name of the movement.
- cue: one short coaching cue (max 12 words) suitable for a caption.
"""


class LLMKeyframePlan(BaseModel):
    exercise: str
    camera: str
    equipment: str
    setting: str
    loop: Literal["pingpong", "cycle"]
    keyframes: list[str]
    cue: str


def generic_plan(name: str, count: int) -> KeyframePlan:
    """A plan that leans entirely on the image model's own knowledge of the movement."""
    steps = []
    for i in range(count):
        pct = round(100 * i / (count - 1))
        if i == 0:
            steps.append(f"the start position of the {name}, ready to begin the repetition")
        elif i == count - 1:
            steps.append(f"the end position of the {name}, the furthest point of the repetition")
        else:
            steps.append(f"{pct}% of the way from the start position to the end position of the {name}")
    return KeyframePlan(exercise=name.strip(), keyframes=tuple(steps), equipment=f"whatever the {name} normally requires", source="generic")


class KeyframePlanner:
    """Resolve an exercise name to a ``KeyframePlan``.

    ``mode``: ``library`` (bundled plans, generic fallback, never calls the network),
    ``auto`` (library first, then the GPT planner) or ``llm`` (always the GPT planner).
    """

    def __init__(
        self,
        *,
        mode: str = "auto",
        library: ExerciseLibrary | None = None,
        client: Any | None = None,
        model: str = DEFAULT_PLANNER_MODEL,
        keyframe_count: int = 6,
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        if mode not in ("auto", "library", "llm"):
            raise SettingsError(f"unknown planner mode {mode!r}")
        self.mode = mode
        self.library = library if library is not None else ExerciseLibrary.default()
        self._client = client
        self.model = model
        self.keyframe_count = keyframe_count
        self.api_key = api_key
        self.timeout = timeout

    @property
    def client(self) -> Any:
        if self._client is None:
            key = self.api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise SettingsError("OPENAI_API_KEY is not set; the GPT keyframe planner needs it (or use planner=library)")
            from openai import OpenAI

            self._client = OpenAI(api_key=key, timeout=self.timeout)
        return self._client

    def plan(self, name: str, *, hints: str | None = None) -> KeyframePlan:
        name = name.strip()
        if not name:
            raise PlanningError("exercise name is empty")
        if self.mode != "llm":
            found = self.library.find(name)
            if found is not None:
                return found
            if self.mode == "library":
                return generic_plan(name, self.keyframe_count)
        return self.plan_with_llm(name, hints=hints)

    def plan_with_llm(self, name: str, *, hints: str | None = None) -> KeyframePlan:
        request = f"Exercise: {name}\nNumber of keyframes: {self.keyframe_count}"
        if hints:
            request += f"\nCoach notes: {hints}"
        client = self.client  # configuration errors surface as SettingsError, not as a failed call
        try:
            response = client.responses.parse(
                model=self.model,
                instructions=PLANNER_INSTRUCTIONS,
                input=request,
                text_format=LLMKeyframePlan,
            )
        except Exception as exc:
            raise PlanningError(f"{name}: keyframe planner call failed: {exc}") from exc
        parsed: LLMKeyframePlan | None = getattr(response, "output_parsed", None)
        if parsed is None:
            raise PlanningError(f"{name}: keyframe planner returned no structured output")
        keyframes = [k.strip() for k in parsed.keyframes if k and k.strip()]
        if len(keyframes) < 2:
            raise PlanningError(f"{name}: keyframe planner returned fewer than two keyframes")
        plan = KeyframePlan(
            exercise=parsed.exercise.strip() or name,
            keyframes=tuple(keyframes),
            camera=parsed.camera.strip() or KeyframePlan.camera,
            equipment=parsed.equipment.strip() or KeyframePlan.equipment,
            setting=parsed.setting.strip() or KeyframePlan.setting,
            cue=parsed.cue.strip(),
            loop=parsed.loop,
            source=f"llm:{self.model}",
        )
        return plan.resampled(self.keyframe_count)
