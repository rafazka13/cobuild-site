# exercise-gifs

Looping exercise-demo GIFs for strength sessions, drawn by OpenAI GPT image models.

Give it the session your coaching bot just produced and it hands back one animated GIF per
exercise — a consistent athlete performing one repetition, ready to send to the athlete with a
caption such as `Back Squat — 4×6 @ RPE 8` and the coaching cue.

```
session ─▶ keyframe storyboard ─▶ one GPT-image sprite sheet ─▶ slice ─▶ looping GIF ─▶ cache
```

## Why one sprite sheet per exercise

Image models do not keep a character, camera angle or scale stable across separate calls, so
frames generated one by one never animate cleanly. Instead every keyframe of an exercise is
drawn on a **single sheet** (a 3×2 grid by default: "Panel 1: standing tall … Panel 6: bottom
of the squat"). One image, one athlete, one camera. The sheet is then sliced into frames and
played forward and back (ping-pong), which turns six poses into a smooth repetition.

## Install

```bash
cd services/exercise-gifs
pip install -e ".[dev]"          # openai, pillow, pydantic (+ pytest)
export OPENAI_API_KEY=sk-...
```

Python 3.10+. Verified against `openai` 3.14 (`gpt-image-2`, `gpt-5.4-mini`).

## Quickstart

### CLI

```bash
exercise-gifs "Back Squat" "Romanian Deadlift" --out ./gifs      # one GIF per exercise
exercise-gifs --session session.json --out ./gifs --json         # JSON manifest for a bot
exercise-gifs --list                                              # bundled exercise library
exercise-gifs --warm                                              # pre-render the whole library
exercise-gifs "Push-up" --synthetic                               # offline stick figures, no key
exercise-gifs "Bench Press" --style clay --grid 3x3 --frame-ms 120 --force
```

Exit codes: `0` all GIFs produced, `1` at least one exercise failed (details on stderr as
`failed: <slug>: …`), `2` bad input or configuration.

### Python

```python
from exercise_gifs import ExerciseGifService

service = ExerciseGifService()          # reads OPENAI_API_KEY and EXERCISE_GIF_* once
result = service.generate_for_session(session)   # any of the shapes below

for gif in result.gifs:                  # one per distinct exercise, in session order
    send_animation(chat_id, gif.path, caption=gif.caption)
for slug, error in result.errors.items():        # failures never abort the session
    send_text(chat_id, f"{slug}: no demo available")
```

`ExerciseGif` fields: `exercise`, `slug`, `path`, `caption`, `plan` (the storyboard used),
`frame_count`, `width`, `height`, `duration_ms`, `source` (`openai:gpt-image-2`, `synthetic`),
`from_cache`, `items` (every session item that mapped to this exercise) and `sheet_path`
(the raw sprite sheet, useful for QA). `read_bytes()` returns the GIF data;
`to_dict()` gives a JSON-safe manifest (`SessionGifs.to_dict()` for the whole session).

Other entry points: `service.generate_for_exercise("Plank")` (accepts a name, a
`SessionItem` or a `KeyframePlan`), `service.warm()` to pre-render the library, and
`exercise_gifs.generate_session_gifs(session, backend="synthetic")` for one-off calls.

### Session shapes

`normalize_session` accepts whatever your planner emits:

```python
"Back Squat"
["Back Squat", "Push-up"]
[{"exercise": "Back Squat", "sets": 4, "reps": 6, "rpe": 8, "rest": "3 min"}]
{"name": "Lower A",
 "warmup": ["Goblet Squat"],
 "blocks": [{"name": "A", "exercises": [{"exercise": "Back Squat", "sets": 5, "reps": 5}]},
            {"name": "B", "exercises": ["Romanian Deadlift", {"exercise": "Plank", "reps": "45 s"}]}]}
```

Item keys: `exercise`/`name`/`movement`/`title`, `sets`, `reps`, `load`/`weight`/`intensity`,
`rpe`, `percent`, `tempo`, `rest`, `notes`/`cues`. Lists under `warmup`, `exercises`, `blocks`,
`items`, `movements`, `workout`, `main`, `sections`, `accessories`, `cooldown` are flattened in
order; a dict that contains such a list is a section, never an exercise. An item may carry its
own `keyframes` (plus `camera`, `equipment`, `setting`, `loop`) to bypass the planner.

Names are matched loosely: `"heavy back squat 5x5"`, `"Back Squat (paused) @ RPE 8"`,
`"RDL 3x8"` and `"back squat"` all resolve to the library's **Back Squat** and share one GIF.

## Configuration

Everything is an environment variable (or a keyword to `Settings.from_env(**overrides)`).

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | – | Required for the `openai` backend (`EXERCISE_GIF_OPENAI_API_KEY` also accepted). |
| `EXERCISE_GIF_BACKEND` | `openai` | `openai` or `synthetic` (offline stick figures). |
| `EXERCISE_GIF_IMAGE_MODEL` | `gpt-image-2` | GPT image model that draws the sheets (`gpt-image-1.5`, `gpt-image-2.5-*` also work). |
| `EXERCISE_GIF_IMAGE_QUALITY` | `medium` | `low`, `medium`, `high`, `xhigh`, `max`, `auto`. Part of the cache key. |
| `EXERCISE_GIF_IMAGE_MODERATION` | `auto` | `auto` or `low` (passed to `images.generate`). |
| `EXERCISE_GIF_PLANNER` | `auto` | `auto` = library first, GPT planner for unknown exercises; `library` = never call GPT (generic storyboard for unknowns); `llm` = always GPT. |
| `EXERCISE_GIF_PLANNER_MODEL` | `gpt-5.4-mini` | Text model for the structured-output keyframe planner. |
| `EXERCISE_GIF_STYLE` | `flat` | `flat` (fitness-app vector), `clay` (matte 3D), `photo` (photoreal studio). |
| `EXERCISE_GIF_ATHLETE` | neutral adult athlete | Free-text description of the athlete to draw. |
| `EXERCISE_GIF_REFERENCE_IMAGE` | – | Path to a mascot/athlete image; sheets are drawn with `images.edit` from it. |
| `EXERCISE_GIF_GRID` | `3x2` | Keyframe grid, columns × rows (each 1–4, product 2–12). |
| `EXERCISE_GIF_FRAME_SIZE` | `480` | Output GIF is square, this many pixels per side (64–1024). |
| `EXERCISE_GIF_FRAME_MS` | `140` | Milliseconds per frame (20–2000). |
| `EXERCISE_GIF_HOLD_ENDS_MS` | `2 × FRAME_MS` | Extra dwell on the two turnaround poses of a ping-pong loop. |
| `EXERCISE_GIF_COLORS` | `128` | Colours in the shared GIF palette (2–256). |
| `EXERCISE_GIF_SNAP_GRID` | `true` | Snap panel boundaries onto the separator lines the model drew. |
| `EXERCISE_GIF_CACHE_DIR` | `~/.cache/exercise-gifs` | Two-level cache (`sheets/`, `gifs/`). |
| `EXERCISE_GIF_OUTPUT_DIR` | `./exercise-gifs-out` | Where `<slug>.gif` files are written. |
| `EXERCISE_GIF_MAX_WORKERS` | `4` | Parallel exercises per session (each is one image call). |
| `EXERCISE_GIF_MAX_ATTEMPTS` | `2` | Sheet re-draws allowed when panels come back blank. |
| `EXERCISE_GIF_REQUEST_TIMEOUT` | `180` | Seconds per image call (the planner uses `min(this, 120)`). |

`.env.example` lists the same values with comments.

## How it works

1. **Plan** – the exercise name is resolved against the bundled library (84 lifts across
   lower body, upper push, upper pull, core and carries; aliases such as `RDL`, `BSS`,
   `push ups`). Unknown movements go to the GPT planner, which returns a strict-schema
   storyboard (`exercise`, `camera`, `equipment`, `setting`, `loop`, `keyframes`, `cue`).
2. **Sheet** – one `images.generate` call (or `images.edit` with `input_fidelity="high"` when a
   reference image is set) draws all keyframes as a grid on a 1536×1024 / 1024×1024 /
   1024×1536 canvas, whichever keeps the panels square for the chosen grid.
3. **Slice** – the grid is cut into panels. Boundaries snap onto the thin separator lines the
   model actually drew (±3 % search), and a 3 % margin is trimmed so no line leaks into a frame.
4. **Validate** – panels with (almost) no content mean the model skipped or merged frames; the
   sheet is re-drawn up to `MAX_ATTEMPTS` times, then the best attempt is used if at least
   half the panels are usable, otherwise the exercise fails with `SheetValidationError`.
5. **GIF** – frames are fitted to a square, quantised with one shared palette (no flicker) and
   written with `loop=0`. `pingpong` plans play forward then backward with a longer dwell on
   the two turnaround poses; `cycle` plans (walking lunge, burpee, carries, get-ups) loop
   straight through.

## Caching and warm-up

Sheets (the paid call) and GIFs are cached separately under `EXERCISE_GIF_CACHE_DIR`, keyed
by everything that changes the drawing: storyboard, style, athlete, model, quality, grid and
reference image for sheets; plus frame size/timing/colours for GIFs. Changing `FRAME_MS`
re-encodes GIFs without touching the image model; changing `STYLE` re-draws. Concurrent
requests for the same key inside one process are serialised so a popular exercise is only
ever drawn once.

Run `exercise-gifs --warm` at deploy time to draw the whole library up front; live sessions
then complete in milliseconds. Keep the cache directory on a persistent volume.

## Look and consistency

* `flat` is the recommended style for messaging: bold shapes, small files, readable at phone
  size. `clay` and `photo` look richer but are harder for the model to keep consistent across
  six panels.
* `EXERCISE_GIF_ATHLETE` changes who is drawn ("a tall athlete with a long ponytail wearing a
  navy tank top…"). Use it per athlete if you want a look-alike.
* `EXERCISE_GIF_REFERENCE_IMAGE` turns every sheet into an edit of that image, so a brand
  mascot or a specific athlete appears in every exercise.

## Cost and latency

One image-model call per exercise, ever — after that the GIF is served from cache. At medium
quality a sheet is a few cents and takes roughly 15–40 s; a six-exercise session with an empty
cache finishes in about the time of the slowest call because exercises render in parallel
(`MAX_WORKERS`). The planner call for unknown exercises is a fraction of a cent. `warm` the
library once and most sessions cost nothing.

## Offline mode and tests

`EXERCISE_GIF_BACKEND=synthetic` (or `--synthetic`) draws deterministic stick figures with
Pillow — no key, no network — through exactly the same slicing, validation and GIF code, and
never calls the GPT planner (unknown exercises get a generic storyboard). The test suite runs
entirely offline:

```bash
python -m pytest -q
python examples/bot_hook.py --synthetic     # what a bot would send for examples/session.json
```

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `SettingsError: OPENAI_API_KEY is not set` | Export the key, or use `--synthetic` / `EXERCISE_GIF_PLANNER=library` for offline runs. |
| `SheetValidationError: … panels empty` | The model merged or skipped panels twice. Try `EXERCISE_GIF_GRID=2x2`, `--quality high`, or a simpler `EXERCISE_GIF_ATHLETE`. The sheet is kept in the cache `sheets/` folder for inspection. |
| Motion looks jumpy | Increase the grid (`3x3` = 9 keyframes) or `FRAME_MS`; `--force` to re-render after changes. |
| Figure is cropped in some frames | Lower `snap` false positives with `EXERCISE_GIF_SNAP_GRID=false`, or re-render; check `sheet_path`. |
| Unknown exercise produces an odd storyboard | Add it to `exercise_gifs/library_data/` (see the schema in `library_data/__init__.py`) or pass `keyframes` on the session item. |
| `FrameSourceError: … moderation` | The prompt tripped image moderation; `EXERCISE_GIF_IMAGE_MODERATION=low` or rephrase the athlete description. |

## Layout

```
exercise_gifs/
  models.py        KeyframePlan, SessionItem, normalize_session, ExerciseGif
  library.py       ExerciseLibrary (alias + fuzzy lookup) over library_data/*.py
  planner.py       library → GPT structured-output planner → generic fallback
  prompts.py       the sprite-sheet prompt and style presets
  frames/          FrameSource protocol, OpenAIImageFrameSource, SyntheticFrameSource
  sprites.py       canvas selection, grid slicing, line snapping, blank detection
  gif.py           fit, shared palette, ping-pong ordering, GIF encoding
  cache.py         two-level disk cache
  pipeline.py      ExerciseGifService (threads, retries, captions, progress events)
  cli.py           `exercise-gifs`
docs/BOT_INTEGRATION.md   wiring it into a coaching bot
examples/                 session.json, bot_hook.py
```
