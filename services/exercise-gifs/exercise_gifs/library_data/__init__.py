"""Curated keyframe storyboards for common strength exercises.

Each module exposes ``EXERCISES: list[dict]``. Entry schema::

    {
        "name": "Back Squat",                  # canonical display name (unique)
        "aliases": ["barbell back squat"],      # optional lookup aliases (unique across library)
        "category": "lower_body",              # free-form grouping
        "camera": "side view, camera at hip height",
        "equipment": "a loaded barbell across the upper back",
        "setting": "inside a squat rack on a gym floor",
        "loop": "pingpong",                     # keyframes cover ONE direction; GIF plays there and back
        "keyframes": [ ... 4-8 drawable pose descriptions, start -> end ... ],
        "cue": "Drive the floor away, bar over midfoot.",   # optional caption line for the athlete
        "notes": "",                            # optional extra prompt guidance for the image model
    }

Keep every keyframe concrete and *drawable* (joint angles, where the load is, where the
hands are), 10-35 words, no coaching advice. For ``loop: "cycle"`` the keyframes cover the whole
repetition and should end close to where they began.
"""

MODULES = ("lower_body", "upper_push", "upper_pull", "core_and_carries")
