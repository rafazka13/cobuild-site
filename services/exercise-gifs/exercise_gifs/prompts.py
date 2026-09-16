from __future__ import annotations

from .models import KeyframePlan

# Bump when the prompt wording changes so cached sheets drawn with the old prompt are not reused.
PROMPT_VERSION = 1

STYLE_PRESETS: dict[str, str] = {
    "flat": (
        "clean flat vector illustration in the style of a modern fitness app: simple bold shapes, "
        "minimal detail, a charcoal-grey athlete with a single teal accent colour on the shirt, flat "
        "colours only, no gradients, no outlines, no shadows, no background scenery"
    ),
    "clay": (
        "soft matte 3D clay-render style, smooth simplified anatomy, neutral studio lighting, "
        "no background scenery"
    ),
    "photo": (
        "photorealistic studio photograph of a real athlete against a seamless white backdrop with "
        "soft, even lighting and no background scenery"
    ),
}

DEFAULT_ATHLETE = (
    "an adult athlete with an average, athletic build and short dark hair, wearing a fitted "
    "dark-grey t-shirt, black shorts and white training shoes"
)


def sprite_sheet_prompt(
    plan: KeyframePlan,
    *,
    cols: int,
    rows: int,
    style: str = "flat",
    athlete: str | None = None,
) -> str:
    """Build the single prompt that makes the image model draw all keyframes on one sheet.

    Drawing every phase on one sheet is what keeps the athlete, camera and scale identical
    across frames; separately generated images drift and do not animate cleanly.
    """
    if style not in STYLE_PRESETS:
        raise ValueError(f"unknown style {style!r}; expected one of {', '.join(STYLE_PRESETS)}")
    count = cols * rows
    if len(plan.keyframes) != count:
        plan = plan.resampled(count)

    panel_lines = "\n".join(f"Panel {i + 1}: {text}" for i, text in enumerate(plan.keyframes))
    if plan.loop == "pingpong":
        motion = (
            f"The panels show one continuous direction of the movement, from the start position in "
            f"panel 1 to the end position in panel {count}."
        )
    else:
        motion = "The panels show one complete repetition from start to finish, ending where it began."
    notes = f" {plan.notes.strip()}" if plan.notes.strip() else ""
    layout = f"{rows} row{'s' if rows != 1 else ''} of {cols} panel{'s' if cols != 1 else ''}"

    return (
        f"A storyboard sprite sheet for an exercise animation: a grid of exactly {count} panels, "
        f"{layout}, filling the entire image edge to edge. Every panel is exactly the same size, "
        f"separated by thin light-grey lines. Pure white background inside every panel. Absolutely no "
        f"text, numbers, letters, arrows, labels, logos or watermarks anywhere.\n\n"
        f"The subject in every panel is the SAME athlete: {athlete or DEFAULT_ATHLETE}. Same clothing, "
        f"same body, same hairstyle in all panels. Fixed camera: {plan.camera}. Same distance and scale "
        f"in every panel, full body always fully visible, feet on the same floor line, figure centred in "
        f"its panel, so that flipping through the panels in order plays as a smooth animation.\n\n"
        f"Visual style: {STYLE_PRESETS[style]}.\n\n"
        f"Equipment: {plan.equipment}. Setting: {plan.setting}.\n\n"
        f"Exercise: {plan.exercise}. {motion} Read the panels left to right, top to bottom:\n"
        f"{panel_lines}\n\n"
        f"Make the pose change between consecutive panels small and evenly spaced so the motion looks "
        f"continuous. Keep the equipment identical in every panel.{notes}"
    )
