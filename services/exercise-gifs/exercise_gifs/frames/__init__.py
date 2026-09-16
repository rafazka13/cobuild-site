from .base import FrameSource, RenderedSheet
from .synthetic import SyntheticFrameSource

__all__ = ["FrameSource", "RenderedSheet", "SyntheticFrameSource", "OpenAIImageFrameSource"]


def __getattr__(name: str):
    # openai is imported lazily so the synthetic backend and tests never need the SDK.
    if name == "OpenAIImageFrameSource":
        from .openai_images import OpenAIImageFrameSource

        return OpenAIImageFrameSource
    raise AttributeError(name)
