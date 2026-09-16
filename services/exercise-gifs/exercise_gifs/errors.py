class ExerciseGifError(Exception):
    """Base class for every error raised by exercise_gifs."""


class SettingsError(ExerciseGifError):
    """Invalid configuration (bad env var, unsupported option)."""


class PlanningError(ExerciseGifError):
    """A keyframe plan could not be produced for an exercise."""


class FrameSourceError(ExerciseGifError):
    """The frame source (image model) failed to render a sprite sheet."""


class SheetValidationError(ExerciseGifError):
    """A rendered sprite sheet did not contain usable panels."""
