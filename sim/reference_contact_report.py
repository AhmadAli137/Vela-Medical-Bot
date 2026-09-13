"""Reproducible physical pickup, sustained hold, release and lift-travel evidence."""
import argparse
import json
from pathlib import Path

import mujoco

from sim.reference_runtime import ReferenceSimulation


def run_report():
    simulation = ReferenceSimulation()
    simulation.command("pickup_demo")
    pickup_samples = []
    for _ in range(15):
        state = simulation.advance(2.)
        pickup_samples.append({"simulation_time": state["simulation_time"], "phone_pose": state["bodies"]["phone"], "pickup": state["metrics"]["pickup"], "contacts": state["metrics"]["contacts"], "paused": state["paused"]})
        if state["paused"]:
            break
    held = state["metrics"]["pickup"]["success"]
    if held:
        simulation.command("release_phone")
        release = simulation.advance(2.)
    else:
        release = state
    simulation.command("reset")
    simulation.command("lift_demo")
    lift_samples = []
    for _ in range(14):
        state = simulation.advance(2.)
        lift_samples.append({"simulation_time": state["simulation_time"], "lift": state["metrics"]["lift"], "contacts": state["metrics"]["contacts"], "paused": state["paused"]})
        if state["paused"]:
            break
    valid = held and release["metrics"]["pickup"]["released"] and state["metrics"]["lift"]["complete"] and all(not sample["paused"] for sample in pickup_samples+lift_samples)
    return {"passed": valid, "model_hash": simulation.metadata["model_hash"], "mujoco_version": mujoco.__version__, "hardware_model_verified": False, "authorizes_hardware": False, "phone_mass_kg": float(simulation.model.body_mass[simulation.model.body("phone").id]), "attachment_constraints": sum(kind in {mujoco.mjtEq.mjEQ_WELD,mujoco.mjtEq.mjEQ_CONNECT} for kind in simulation.model.eq_type), "mechanical_blinds_linkages": int(simulation.model.neq), "pickup_samples": pickup_samples, "release": {"phone_pose": release["bodies"]["phone"], "metrics": release["metrics"]}, "lift_samples": lift_samples, "limitations": ["Single fixed synthetic fixture with a 35 mm physical phone riser", "Estimated gripper geometry, mass, friction, torque and actuator response", "Free-space approach sampled; loaded grasp checked through actual contact dynamics", "Constrained planar base, synchronized wheel angle commands; no balancing or traction validation", "Measured simulator grasp and workspace do not establish hardware or learned VLA competence"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="sim/outputs/reference_contact_manipulation.json")
    args = parser.parse_args()
    report = run_report()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "model_hash": report["model_hash"], "output": str(destination), "held_height_m": report["pickup_samples"][-1]["pickup"]["height_gain_m"], "released": report["release"]["metrics"]["pickup"]["released"], "lift": report["lift_samples"][-1]["lift"]}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
