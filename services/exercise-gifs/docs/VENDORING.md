# Vendoring exercise-gifs into another repository

The service is a self-contained Python package with no imports outside its own
directory, so it drops into another codebase as-is. Use this when the consuming
application (for example the Chiron coaching bot) lives in a different GitHub
organisation and cannot depend on this repository at build time.

## 1. Copy the package in

`rafazka13/cobuild-site` is public, so no credentials are needed:

```bash
git clone --depth 1 --branch main https://github.com/rafazka13/cobuild-site /tmp/cobuild-site
cp -r /tmp/cobuild-site/services/exercise-gifs/exercise_gifs  <target>/
cp -r /tmp/cobuild-site/services/exercise-gifs/tests          <target>/tests/exercise_gifs
cp -r /tmp/cobuild-site/services/exercise-gifs/docs           <target>/docs/exercise-gifs
cp    /tmp/cobuild-site/services/exercise-gifs/README.md      <target>/docs/exercise-gifs/
cp    /tmp/cobuild-site/services/exercise-gifs/.env.example   <target>/docs/exercise-gifs/
```

Pick `<target>` to match the host project's layout. Record the source commit in
the vendored README header so a future maintainer can diff against upstream.

## 2. Declare the dependencies

```
openai>=2.0,<4
pillow>=10.0
pydantic>=2.0
```

Nothing else is required. The CLI entry point (`exercise-gifs`) is optional; the
library works through `from exercise_gifs import ExerciseGifService`.

## 3. Call it where sessions are delivered

```python
from exercise_gifs import ExerciseGifService

service = ExerciseGifService()          # once per process: thread-safe, holds the render locks

result = service.generate_for_session(session)
for gif in result.gifs:
    send_animation(chat_id, gif.path, caption=gif.caption)
for slug, error in result.errors.items():
    send_text(chat_id, f"{slug}: no demo available")
```

Four rules for a production hook:

1. **Build the service once**, at module or app-state level — never per request.
2. **Never let it break delivery.** Wrap the call so a missing API key or a raised
   exception still leaves the athlete with their text session; log and continue.
3. **Gate it behind a flag** so it can be switched off without a redeploy.
4. **Off the event loop** in async apps: `await asyncio.to_thread(service.generate_for_session, session)`.
   An uncached exercise takes 15–40 s.

`BOT_INTEGRATION.md` has transport-specific examples (Telegram, WhatsApp/Twilio,
Discord, plain HTTP) and the per-athlete appearance options.

## 4. Verify offline

```bash
python -m pytest <target>/tests/exercise_gifs -q        # 113 tests, ~5 s, no network
python <target>/docs/exercise-gifs/examples/bot_hook.py --synthetic
```

Both run without an API key: the synthetic backend draws stick figures through
the same slicing, validation and GIF code as the real one.

## 5. Before it reaches athletes

Set `OPENAI_API_KEY`, point `EXERCISE_GIF_CACHE_DIR` at a persistent volume, and
run `exercise-gifs --warm` once at deploy so live sessions hit the cache instead
of paying for a render. Then render a couple of real exercises and look at them:

```bash
exercise-gifs "Back Squat" "Bench Press" --out ./gifs --verbose
```

Inspect both the GIFs and the raw sprite sheets in `$EXERCISE_GIF_CACHE_DIR/sheets/`.
If panels merge or the figure drifts between frames, try `--quality high`, a
smaller `--grid 2x2`, or a simpler athlete description; individual movements are
plain-text storyboards in `exercise_gifs/library_data/` and are safe to edit.
