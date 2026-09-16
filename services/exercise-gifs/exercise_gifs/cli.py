from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .errors import ExerciseGifError
from .library import ExerciseLibrary
from .pipeline import ExerciseGifService
from .settings import BACKENDS, IMAGE_QUALITIES, PLANNER_MODES, STYLES, Settings, parse_grid


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exercise-gifs",
        description="Generate looping exercise-demo GIFs for a strength session.",
        epilog=(
            "Examples:\n"
            '  exercise-gifs "Back Squat" "Romanian Deadlift" --out ./gifs\n'
            "  exercise-gifs --session session.json --out ./gifs --json\n"
            "  exercise-gifs --list\n"
            "  exercise-gifs --warm            # pre-render the whole library into the cache\n"
            "  exercise-gifs \"Push-up\" --synthetic   # no API key needed, stick-figure output"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("exercises", nargs="*", help="exercise names (or use --session)")
    parser.add_argument("--session", metavar="FILE", help="JSON session file ('-' for stdin)")
    parser.add_argument("--out", metavar="DIR", help="output directory for the GIFs")
    parser.add_argument("--list", action="store_true", help="list the bundled exercise library and exit")
    parser.add_argument("--warm", action="store_true", help="render every library exercise (or the given ones) into the cache")
    parser.add_argument("--force", action="store_true", help="ignore the cache and re-render")
    parser.add_argument("--json", action="store_true", help="print a JSON manifest of the results to stdout")
    parser.add_argument("-v", "--verbose", action="store_true", help="log progress to stderr")

    backend = parser.add_argument_group("backend")
    backend.add_argument("--backend", choices=BACKENDS)
    backend.add_argument("--synthetic", action="store_true", help="shorthand for --backend synthetic")
    backend.add_argument("--image-model", metavar="MODEL", help="OpenAI image model (default gpt-image-2)")
    backend.add_argument("--quality", choices=IMAGE_QUALITIES)
    backend.add_argument("--planner", choices=PLANNER_MODES)
    backend.add_argument("--planner-model", metavar="MODEL")
    backend.add_argument("--reference-image", metavar="PATH", help="draw the same athlete/mascot from this image")
    backend.add_argument("--cache-dir", metavar="DIR")
    backend.add_argument("--workers", type=int, metavar="N")

    look = parser.add_argument_group("look")
    look.add_argument("--style", choices=STYLES)
    look.add_argument("--athlete", metavar="TEXT", help="describe the athlete to draw")
    look.add_argument("--grid", metavar="CxR", help="keyframe grid, e.g. 3x2")
    look.add_argument("--frame-size", type=int, metavar="PX")
    look.add_argument("--frame-ms", type=int, metavar="MS")
    look.add_argument("--hold-ms", type=int, metavar="MS", help="extra dwell on the two turnaround poses")
    look.add_argument("--colors", type=int, metavar="N")
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    overrides: dict[str, Any] = {
        "backend": "synthetic" if args.synthetic else args.backend,
        "image_model": args.image_model,
        "image_quality": args.quality,
        "planner": args.planner,
        "planner_model": args.planner_model,
        "reference_image": Path(args.reference_image) if args.reference_image else None,
        "cache_dir": Path(args.cache_dir) if args.cache_dir else None,
        "max_workers": args.workers,
        "style": args.style,
        "athlete": args.athlete,
        "frame_size": args.frame_size,
        "frame_ms": args.frame_ms,
        "hold_ends_ms": args.hold_ms,
        "colors": args.colors,
        "output_dir": Path(args.out) if args.out else None,
    }
    if args.grid:
        overrides["grid_cols"], overrides["grid_rows"] = parse_grid(args.grid)
    return Settings.from_env(**overrides)


def load_session(args: argparse.Namespace) -> Any:
    if args.session:
        text = sys.stdin.read() if args.session == "-" else Path(args.session).read_text("utf-8")
        session = json.loads(text)
        if args.exercises:
            raise SystemExit("give either exercise names or --session, not both")
        return session
    if args.exercises:
        return list(args.exercises)
    return None


def _progress_printer(event: dict[str, Any]) -> None:
    stage = event.get("stage")
    name = event.get("exercise", "")
    if stage == "sheet":
        print(f"  {name}: rendering keyframes with {event.get('source')}", file=sys.stderr)
    elif stage == "retry":
        print(f"  {name}: blank panels {event.get('blank_panels')} on attempt {event.get('attempt')}, retrying", file=sys.stderr)
    elif stage == "done":
        cached = " (cached)" if event.get("from_cache") else ""
        print(f"  {name}: {event.get('path')}{cached}", file=sys.stderr)
    elif stage == "error":
        print(f"  {name}: FAILED - {event.get('error')}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    if args.list:
        library = ExerciseLibrary.default()
        for category, names in sorted(library.categories().items()):
            print(f"[{category or 'uncategorised'}]")
            for name in names:
                print(f"  {name}")
        print(f"{len(library)} exercises", file=sys.stderr)
        return 0

    try:
        settings = settings_from_args(args)
        session = load_session(args)
        if session is None and not args.warm:
            parser.print_usage(sys.stderr)
            print("error: give at least one exercise name, --session FILE, --warm or --list", file=sys.stderr)
            return 2
        service = ExerciseGifService(settings)
        progress = _progress_printer if (args.verbose or not args.json) else None
        if args.warm:
            names = list(args.exercises) if args.exercises else None
            result = service.warm(names, on_progress=progress)
        else:
            result = service.generate_for_session(session, force=args.force, on_progress=progress)
    except (ExerciseGifError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        for gif in result.gifs:
            print(gif.path)
    if result.errors:
        for slug, message in result.errors.items():
            print(f"failed: {slug}: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
