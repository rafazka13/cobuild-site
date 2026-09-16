"""exercise_gifs: looping exercise-demo GIFs for strength sessions, drawn by GPT image models.

Typical use inside a coaching bot::

    from exercise_gifs import ExerciseGifService

    service = ExerciseGifService()                 # reads OPENAI_API_KEY / EXERCISE_GIF_* env
    result = service.generate_for_session(session)  # session = whatever your planner produced
    for gif in result.gifs:
        send_animation(chat_id, gif.path, caption=gif.caption)
    for slug, error in result.errors.items():
        log.warning("no GIF for %s: %s", slug, error)
"""

from .errors import ExerciseGifError, FrameSourceError, PlanningError, SettingsError, SheetValidationError
from .library import ExerciseLibrary
from .models import ExerciseGif, KeyframePlan, Session, SessionGifs, SessionItem, normalize_session
from .pipeline import ExerciseGifService, build_caption, generate_session_gifs
from .planner import KeyframePlanner
from .settings import Settings

__version__ = "0.1.0"

__all__ = [
    "ExerciseGif",
    "ExerciseGifError",
    "ExerciseGifService",
    "ExerciseLibrary",
    "FrameSourceError",
    "KeyframePlan",
    "KeyframePlanner",
    "PlanningError",
    "Session",
    "SessionGifs",
    "SessionItem",
    "Settings",
    "SettingsError",
    "SheetValidationError",
    "__version__",
    "build_caption",
    "generate_session_gifs",
    "normalize_session",
]
