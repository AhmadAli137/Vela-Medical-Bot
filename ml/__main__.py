import argparse
import json

from ml.pipeline import run_learning_demo

parser = argparse.ArgumentParser(description="Run synthetic teleop recording and tiny feature behavior cloning")
parser.add_argument("command", choices=["demo"])
parser.add_argument("--output", default="data/runtime/learning-demo")
parser.add_argument("--seed", type=int, default=17)
args = parser.parse_args()
print(json.dumps(run_learning_demo(args.output, args.seed), indent=2))
