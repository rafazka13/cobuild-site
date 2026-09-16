#!/usr/bin/env python
"""Minimal coaching-bot hook: session in, "messages" out.

This is the exact shape of the code a bot runs right after it has generated a
strength session. It loads ``examples/session.json``, asks the service for one
GIF per exercise, and prints what the bot would send (GIF path + caption). Exercises
that failed get a text-only fallback message so the athlete never misses a lift.

Run without any API key or network access::

    python examples/bot_hook.py --synthetic

With ``OPENAI_API_KEY`` set, drop ``--synthetic`` to draw real GIFs::

    python examples/bot_hook.py --out ./gifs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from exercise_gifs import ExerciseGifService, SessionGifs, Settings

HERE = Path(__file__).resolve().parent


def send_animation(chat_id: str, path: Path, caption: str) -> None:
    """Stand-in for bot.send_animation / Twilio media / an HTTP upload."""
    print(f"[{chat_id}] ANIMATION {path}")
    for line in caption.splitlines():
        print(f"[{chat_id}]     {line}")


def send_text(chat_id: str, text: str) -> None:
    print(f"[{chat_id}] TEXT {text}")


def deliver(chat_id: str, result: SessionGifs) -> None:
    """Send every GIF with its caption, then a text fallback for anything that failed."""
    for gif in result.gifs:
        send_animation(chat_id, gif.path, gif.caption)

    if result.errors:
        by_slug = {item.slug: item for item in result.session.items}
        for slug, error in result.errors.items():
            item = by_slug.get(slug)
            if item is not None:
                prescription = item.prescription()
                label = f"{item.name} — {prescription}" if prescription else item.name
            else:
                label = slug.replace("-", " ").title()
            send_text(chat_id, f"{label} (no demo available)")
            print(f"    reason: {error}", file=sys.stderr)


def progress(event: dict) -> None:
    stage = event.get("stage")
    if stage in ("sheet", "retry", "error"):
        print(f"  ... {event.get('exercise')}: {stage} {event.get('error', '')}".rstrip(), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", default=str(HERE / "session.json"), help="session JSON file")
    parser.add_argument("--synthetic", action="store_true", help="stick-figure backend, no API key or network")
    parser.add_argument("--out", help="where to write the GIFs (default: EXERCISE_GIF_OUTPUT_DIR or ./exercise-gifs-out)")
    parser.add_argument("--cache-dir", help="sheet/GIF cache (default: EXERCISE_GIF_CACHE_DIR or ~/.cache/exercise-gifs)")
    parser.add_argument("--chat-id", default="athlete-42", help="pretend chat id used in the printed messages")
    args = parser.parse_args(argv)

    session = json.loads(Path(args.session).read_text("utf-8"))

    # Settings.from_env() reads EXERCISE_GIF_* and OPENAI_API_KEY; keyword overrides win.
    settings = Settings.from_env(
        backend="synthetic" if args.synthetic else None,
        output_dir=Path(args.out) if args.out else None,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
    )
    service = ExerciseGifService(settings)  # build once per process, reuse for every athlete

    print(f"Session: {session.get('name')}  (backend={settings.backend}, cache={settings.cache_dir})", file=sys.stderr)
    result = service.generate_for_session(session, on_progress=progress)
    deliver(args.chat_id, result)

    cached = sum(1 for g in result.gifs if g.from_cache)
    print(f"\n{len(result.gifs)} GIF(s) sent ({cached} from cache), {len(result.errors)} fallback message(s)", file=sys.stderr)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
