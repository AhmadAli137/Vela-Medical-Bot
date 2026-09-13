"""Current reference viewer/render/export; the original benchmark is explicit."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Current reference MuJoCo scene; no hardware authority")
    parser.add_argument("command", choices=["generate", "benchmark", "render", "viewer"])
    parser.add_argument("--output", default="data/runtime/sim")
    parser.add_argument("--episodes", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7, help="Seed for the original benchmark/legacy scene only")
    parser.add_argument("--camera", default="overview")
    parser.add_argument("--ready-file", default=None)
    parser.add_argument("--connect", help="Attach viewer to a browser/API session at an HTTP loopback IP origin")
    parser.add_argument("--legacy", action="store_true", help="Use the original seeded surrogate for render/generate")
    args = parser.parse_args(argv)
    if args.connect and args.command != "viewer":
        parser.error("--connect is only available with viewer")
    if args.legacy and args.command not in {"render", "generate"}:
        parser.error("--legacy applies to render/generate; benchmark already uses the original seeded model")
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if args.command == "viewer":
        from sim.viewer_live import run_viewer
        result = run_viewer(args.seed, args.ready_file, connect=args.connect)
    elif args.command == "benchmark":
        from sim.engine import run_benchmark
        result = run_benchmark(args.episodes, args.seed)
        # Preserve the numerical benchmark and its historical output schema.
        (out / "evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    elif args.legacy:
        if args.command == "generate":
            from sim.model import write_scene
            result = write_scene(out, args.seed)
        else:
            from sim.engine import render_scene
            result = render_scene(out / f"{args.camera}.png", args.seed, args.camera)
    else:
        from sim.reference_cli import generate_reference_scene, render_reference_scene
        result = generate_reference_scene(out) if args.command == "generate" else render_reference_scene(out / f"{args.camera}.png", args.camera)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
