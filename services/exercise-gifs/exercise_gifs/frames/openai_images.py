from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from ..errors import FrameSourceError, SettingsError
from ..models import KeyframePlan
from ..prompts import sprite_sheet_prompt
from ..sprites import sheet_size_for_grid, size_string
from .base import RenderedSheet


class OpenAIImageFrameSource:
    """Draw the keyframe grid with an OpenAI GPT image model (``client.images.generate``).

    With ``reference_image`` set, ``client.images.edit`` is used instead with
    ``input_fidelity="high"`` so every exercise features the same athlete/mascot.
    """

    name = "openai"

    def __init__(
        self,
        client: Any | None = None,
        *,
        model: str = "gpt-image-2",
        quality: str = "medium",
        moderation: str = "auto",
        timeout: float = 180.0,
        max_retries: int = 2,
        api_key: str | None = None,
        reference_image: Path | str | None = None,
    ):
        self._client = client
        self.model = model
        self.quality = quality
        self.moderation = moderation
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = api_key
        self.reference_image = Path(reference_image) if reference_image else None

    @property
    def source_id(self) -> str:
        return f"openai:{self.model}"

    @property
    def client(self) -> Any:
        if self._client is None:
            key = self.api_key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise SettingsError(
                    "OPENAI_API_KEY is not set. Export it, pass api_key=..., or run with the synthetic backend."
                )
            from openai import OpenAI

            self._client = OpenAI(api_key=key, timeout=self.timeout, max_retries=self.max_retries)
        return self._client

    def render_sheet(
        self,
        plan: KeyframePlan,
        *,
        cols: int,
        rows: int,
        style: str = "flat",
        athlete: str | None = None,
        attempt: int = 1,
    ) -> RenderedSheet:
        prompt = sprite_sheet_prompt(plan, cols=cols, rows=rows, style=style, athlete=athlete)
        if attempt > 1:
            prompt += (
                f"\n\nThis is attempt {attempt}: the previous sheet had missing or merged panels. "
                f"Draw all {cols * rows} panels, each with the athlete fully visible."
            )
        size = size_string(sheet_size_for_grid(cols, rows))
        params: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "quality": self.quality,
            "n": 1,
            "output_format": "png",
            "background": "opaque",
        }
        client = self.client  # configuration errors surface as SettingsError, not as a failed call
        try:
            if self.reference_image is not None:
                with self.reference_image.open("rb") as handle:
                    response = client.images.edit(image=handle, input_fidelity="high", **params)
            else:
                response = client.images.generate(moderation=self.moderation, **params)
        except Exception as exc:  # openai.OpenAIError and transport errors alike
            raise FrameSourceError(f"{plan.exercise}: image generation failed: {exc}") from exc

        data = getattr(response, "data", None) or []
        b64 = getattr(data[0], "b64_json", None) if data else None
        if not b64:
            raise FrameSourceError(f"{plan.exercise}: image model returned no image data")
        try:
            image = Image.open(BytesIO(base64.b64decode(b64)))
            image.load()
        except Exception as exc:
            raise FrameSourceError(f"{plan.exercise}: could not decode image data: {exc}") from exc

        usage = getattr(response, "usage", None)
        usage_dict = None
        if usage is not None:
            usage_dict = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
        return RenderedSheet(image=image.convert("RGB"), prompt=prompt, source=self.source_id, usage=usage_dict)
