"""Write reproducible measured forward-dynamics evidence for the reference model."""
import argparse
import json
from pathlib import Path

import mujoco
import numpy as np

from sim.reference_runtime import ReferenceSimulation


def run_report():
    simulation = ReferenceSimulation()
    original = simulation.initial_q.copy()
    simulation.command("joint_demo")
    samples = [simulation.advance(2.) for _ in range(8)]
    actual_delta = np.abs(simulation.data.qpos[simulation.actuated_q]-original[simulation.actuated_q])
    joint_result = {"duration_s": samples[-1]["simulation_time"], "physics_steps": samples[-1]["metrics"]["physics_steps"], "joint_displacements": dict(zip(samples[-1]["joints"], actual_delta.tolist())), "all_dofs_actuated": bool(np.all(actual_delta > .0001)), "contacts": samples[-1]["metrics"]["contacts"], "stopped": samples[-1]["paused"], "finite_dynamics": samples[-1]["metrics"]["finite_dynamics"]}
    simulation.command("reset")
    planned = simulation.command("reach_demo")
    for _ in range(3):
        final = simulation.advance(2.)
    return {"model_hash": simulation.metadata["model_hash"], "mujoco_version": mujoco.__version__, "reference_source": simulation.metadata["reference_files"], "hardware_model_verified": False, "authorizes_hardware": False, "joint_demonstration": joint_result, "reach_demonstration": {"planned": planned["metrics"]["reach"], "actual": final["metrics"]["reach"], "physics_steps": final["metrics"]["physics_steps"], "contacts": final["metrics"]["contacts"], "finite_dynamics": final["metrics"]["finite_dynamics"], "object_attached": False, "grasp_success": None}, "limitations": ["Visually inferred dimensions and joint axes; not vendor verified", "Constrained planar base and separately actuated wheel hinges; not balancing or odometry simulation", "Position-only IK and sampled static collision configurations, followed by runtime contact checks", "Endpoint reaching is not grasping or manipulating a physical object"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="sim/outputs/reference_actuation.json")
    args = parser.parse_args()
    report = run_report()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
