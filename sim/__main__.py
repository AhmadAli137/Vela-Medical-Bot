import argparse
import json
from pathlib import Path

from sim.engine import render_scene, run_benchmark
from sim.model import write_scene

parser = argparse.ArgumentParser(description="Synthetic MuJoCo research; no hardware authority")
parser.add_argument("command", choices=["generate", "benchmark", "render", "viewer"])
parser.add_argument("--output", default="data/runtime/sim")
parser.add_argument("--episodes", type=int, default=12)
parser.add_argument("--seed", type=int, default=7)
parser.add_argument("--camera", default="overview")
parser.add_argument("--ready-file", default=None)
args = parser.parse_args()
out = Path(args.output)
out.mkdir(parents=True, exist_ok=True)
if args.command == "viewer":
    from sim.viewer_live import run_viewer
    run_viewer(args.seed,args.ready_file)
    result = {"status":"closed","mode":"native_mujoco","hardware_model_verified":False}
elif args.command == "generate":
    result = write_scene(out, args.seed)
elif args.command == "benchmark":
    result = run_benchmark(args.episodes, args.seed)
    (out / "evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
else:
    result = render_scene(out / f"{args.camera}.png", args.seed, args.camera)
print(json.dumps(result, indent=2))
