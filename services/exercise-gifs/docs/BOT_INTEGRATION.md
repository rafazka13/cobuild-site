# Wiring exercise-gifs into the coaching bot

The contract is deliberately small: **session in, list of (GIF path, caption) out**, with
per-exercise failures reported instead of raised. This page shows where to call it, how to
send the result on the usual channels, and what to set up in production.

## 1. The hook

Call the service right after the bot has generated a strength session and before it replies.
Build one `ExerciseGifService` per process and reuse it — it is thread-safe and holds the
per-exercise locks that stop duplicate renders.

```python
# bot/exercise_media.py
from exercise_gifs import ExerciseGifService, SessionGifs

service = ExerciseGifService()          # OPENAI_API_KEY + EXERCISE_GIF_* from the environment


def media_for_session(session: dict) -> SessionGifs:
    """session = whatever the routine planner produced (see README, 'Session shapes')."""
    return service.generate_for_session(session)
```

Then, in the handler that delivers the session:

```python
result = media_for_session(session)

for gif in result.gifs:                       # one per distinct exercise, in session order
    await send_animation(chat_id, gif.path, caption=gif.caption)

for slug, error in result.errors.items():     # never let one bad exercise sink the message
    item = next(i for i in result.session.items if i.slug == slug)
    await send_text(chat_id, f"{item.name} — {item.prescription()} (no demo available)")
    log.warning("no GIF for %s: %s", slug, error)
```

`gif.caption` is `"<name> — <prescription>\n<cue>\n<notes>"`, e.g.

```
Back Squat — 4×6 @ RPE 8 rest 3 min
Brace, sit between your heels, drive the floor away.
```

If two session items map to the same exercise (`"Back Squat"` in block A and
`"heavy back squat 5x5"` in block C) you get **one** GIF whose `items` list holds both; the
caption uses the first. Build per-item captions from `gif.items` if you want one per block.

### Async bots

Rendering blocks on network calls (15–40 s per uncached exercise). From an `asyncio` bot,
push it to a thread:

```python
import asyncio

result = await asyncio.to_thread(service.generate_for_session, session)
```

Send a "Putting your session together…" message first if the cache is cold; with a warmed
cache the call returns in milliseconds.

### Progress events

`on_progress` receives dicts with a `stage` (`plan`, `sheet`, `sheet_cached`, `retry`, `gif`,
`gif_cached`, `done`, `error`) and the `exercise` name — handy for typing indicators or logs.
A callback that raises is logged and ignored.

## 2. Sending on each channel

### Telegram (python-telegram-bot)

```python
with gif.path.open("rb") as handle:
    await context.bot.send_animation(chat_id=chat_id, animation=handle, caption=gif.caption)
```

Telegram transcodes GIFs to MP4 and shows them inline; 480 px square at ~1 MB is ideal.

### WhatsApp (Twilio)

Twilio needs a public `media_url`, so upload the GIF to your object store or CDN first:

```python
url = storage.upload(gif.path, content_type="image/gif")   # S3/GCS/R2, public or signed URL
client.messages.create(from_="whatsapp:+1...", to=f"whatsapp:{phone}", body=gif.caption, media_url=[url])
```

WhatsApp's media limit is 16 MB; the defaults produce ~0.5–1.5 MB.

### Discord (discord.py)

```python
await channel.send(content=gif.caption, file=discord.File(gif.path, filename=f"{gif.slug}.gif"))
```

### Anything else

```python
requests.post(endpoint, data={"caption": gif.caption}, files={"file": (f"{gif.slug}.gif", gif.read_bytes(), "image/gif")})
```

## 3. Production setup

**Warm the cache on deploy.** Every library exercise is one paid call, once:

```bash
exercise-gifs --warm                     # whole library
exercise-gifs --warm "Back Squat" "Bench Press" "Plank"   # or just the staples
```

Run it from your release pipeline (or a nightly cron after library changes). Because the
cache key includes style, athlete, model, quality and grid, re-run it after changing any of
those.

**Keep the cache persistent.** Point `EXERCISE_GIF_CACHE_DIR` at a volume that survives
restarts. Sheets are PNGs (~1–2 MB each), GIFs ~1 MB; the whole library is well under 300 MB.
`EXERCISE_GIF_OUTPUT_DIR` only receives copies for sending — safe to clean at any time.

**Recommended environment**

```bash
OPENAI_API_KEY=...
EXERCISE_GIF_BACKEND=openai
EXERCISE_GIF_IMAGE_MODEL=gpt-image-2
EXERCISE_GIF_IMAGE_QUALITY=medium
EXERCISE_GIF_STYLE=flat
EXERCISE_GIF_GRID=3x2
EXERCISE_GIF_CACHE_DIR=/var/lib/exercise-gifs
EXERCISE_GIF_MAX_WORKERS=4
EXERCISE_GIF_REQUEST_TIMEOUT=180
```

**Concurrency.** `MAX_WORKERS` bounds parallel image calls per session; the service's
per-exercise locks mean N athletes asking for the same uncached lift at once still cost one
call. Multiple processes share the disk cache but not the locks — warm the cache so this
rarely matters.

**Timeouts and retries.** The OpenAI client retries transient errors twice on its own;
`MAX_ATTEMPTS` (default 2) governs re-draws when the model returns blank panels. Failures
end up in `SessionGifs.errors` as `"<ExceptionType>: <message>"`.

**Costs.** One image call per *new* exercise, then free forever from cache; the planner call
for unknown exercises is a fraction of a cent. Set `EXERCISE_GIF_PLANNER=library` if you
want the bot to never spend on planning — unknown exercises then get a generic storyboard
that still draws reasonably because the image model knows the movement.

## 4. Per-athlete looks

Everything is keyed on `Settings`, so a per-athlete look is a per-athlete service:

```python
from functools import lru_cache
from exercise_gifs import ExerciseGifService, Settings

@lru_cache(maxsize=256)
def service_for(athlete_id: str) -> ExerciseGifService:
    profile = athletes.get(athlete_id)
    return ExerciseGifService(Settings.from_env(
        athlete=profile.appearance,                 # "a tall athlete with a long ponytail …"
        reference_image=profile.avatar_path,        # or a brand mascot PNG for everyone
    ))
```

Sheets drawn for different athlete descriptions or reference images never collide in the
cache.

## 5. Custom and new exercises

* **One-off**: put `keyframes` (and optionally `camera`, `equipment`, `setting`, `loop`) on
  the session item and the planner is bypassed.
* **Permanent**: add an entry to `exercise_gifs/library_data/<group>.py` following the schema
  in `library_data/__init__.py` (six drawable poses, camera, equipment, cue, aliases). The
  library test enforces the rules; `exercise-gifs --list` shows what is bundled.

## 6. QA before going live

```bash
exercise-gifs "Back Squat" "Push-up" "Farmer's Carry" --out ./qa --verbose
```

Open the GIFs and the sheets (`~/.cache/exercise-gifs/sheets/*.png`). If a movement reads
wrong, tune the library keyframes or the prompt in `prompts.py`, then `--force` to re-render.
