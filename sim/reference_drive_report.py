"""Independent wheel/contact evidence, measured from MuJoCo state and forces.

Raw trials set wheel velocity controls only. They do not invoke the trajectory
controller or write base/object poses. Counterfactuals change only an isolated
model's tire/floor friction or wheel torque limits, never source model files.
Force API: https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-contactforce
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np

from sim.reference_model import load_reference_model

WHEELS = ("left", "right")
BASE_JOINTS = ("base_x", "base_y", "base_yaw")


def stats(values):
    values = np.asarray(values, dtype=float)
    return {"median": float(np.median(values)), "p95": float(np.quantile(values, .95)), "maximum": float(np.max(values))}


def drive_geometry(model, data):
    base = model.body("robot_base").id
    rotation = data.xmat[base].reshape(3, 3)
    positions = [rotation.T @ (data.xpos[model.body(f"{side}_wheel").id] - data.xpos[base]) for side in WHEELS]
    radii = [float(model.geom_size[model.geom(f"{side}_wheel_geom").id][0]) for side in WHEELS]
    axes = [rotation.T @ data.xaxis[model.joint(f"{side}_wheel_joint").id] for side in WHEELS]
    if not all(np.allclose(axis, [0, 1, 0], atol=1e-8) for axis in axes):
        raise ValueError("Wheel-sign derivation requires both measured hinge axes to point along body +Y")
    track = float(positions[0][1] - positions[1][1])
    if track <= 0 or not np.allclose(radii, radii[0]):
        raise ValueError("Expected equal-radius wheels with the left wheel on body +Y")
    return {"radius_m": radii[0], "track_m": track, "axis_body": [axis.tolist() for axis in axes],
            "sign_derivation": "+Y hinge spin gives -X contact-surface velocity at the bottom; forward rolling requires base +X velocity. Left wheel lies at +Y.",
            "rolling_relation": "v = r*(w_left+w_right)/2; yaw_rate = r*(w_right-w_left)/track"}


def drive_observation(model, data, geometry):
    base = model.body("robot_base").id
    rotation = data.xmat[base].reshape(3, 3)
    linear, angular = np.zeros((3, model.nv)), np.zeros((3, model.nv))
    mujoco.mj_jacBody(model, data, linear, angular, base)
    velocity = rotation.T @ linear @ data.qvel
    angular_velocity = rotation.T @ angular @ data.qvel
    speeds = [float(data.qvel[model.jnt_dofadr[model.joint(f"{side}_wheel_joint").id]]) for side in WHEELS]
    wheel_geoms = {model.geom(f"{side}_wheel_geom").id: side for side in WHEELS}
    floor = model.geom("floor").id
    contact_forces = {side: {"normal_n": 0., "tangential_n": 0., "forward_n": 0., "maximum_penetration_m": 0., "friction_coefficient": 0.} for side in WHEELS}
    for index, contact in enumerate(data.contact[:data.ncon]):
        pair = (int(contact.geom1), int(contact.geom2))
        wheel = next((geom for geom in pair if geom in wheel_geoms), None)
        if wheel is None or floor not in pair:
            continue
        force = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, force)
        world_force = contact.frame.reshape(3, 3).T @ force[:3]
        if pair[0] == wheel:
            world_force *= -1
        record = contact_forces[wheel_geoms[wheel]]
        record["normal_n"] += float(force[0])
        record["tangential_n"] += float(np.linalg.norm(force[1:3]))
        record["forward_n"] += float((rotation.T @ world_force)[0])
        record["maximum_penetration_m"] = max(record["maximum_penetration_m"], -float(contact.dist))
        record["friction_coefficient"] = max(record["friction_coefficient"], float(contact.friction[0]))
    base_dofs = [model.jnt_dofadr[model.joint(name).id] for name in BASE_JOINTS]
    return {"time_s": float(data.time), "position_world": data.xpos[base].tolist(),
            "yaw_rad": float(data.qpos[model.jnt_qposadr[model.joint("base_yaw").id]]),
            "forward_m_s": float(velocity[0]), "lateral_m_s": float(velocity[1]), "yaw_rate_rad_s": float(angular_velocity[2]),
            "wheel_rad_s": speeds, "rolling_forward_m_s": geometry["radius_m"] * sum(speeds) / 2,
            "rolling_yaw_rate_rad_s": geometry["radius_m"] * (speeds[1] - speeds[0]) / geometry["track_m"],
            "base_actuator_force_max": float(np.max(np.abs(data.qfrc_actuator[base_dofs]))),
            "base_applied_force_max": float(np.max(np.abs(data.qfrc_applied[base_dofs]))),
            "external_body_wrench_max": float(np.max(np.abs(data.xfrc_applied))),
            "wheel_torque_nm": [float(data.actuator_force[model.actuator(f"ctrl_{side}_wheel_joint").id]) for side in WHEELS],
            "contacts": contact_forces}


def summarize(samples, geometry):
    intervals = [b["time_s"] - a["time_s"] for a, b in zip(samples, samples[1:])]
    start, end = samples[0], samples[-1]
    steady = [sample for sample in samples if sample["time_s"] >= start["time_s"] + .5]
    return {"samples": len(samples), "duration_s": end["time_s"] - start["time_s"],
            "world_displacement_m": np.subtract(end["position_world"], start["position_world"]).tolist(),
            "yaw_change_rad": end["yaw_rad"] - start["yaw_rad"],
            "body_lateral_absolute_travel_m": sum(abs(sample["lateral_m_s"]) * dt for sample, dt in zip(samples, intervals)),
            "lateral_speed_abs_m_s": stats([abs(sample["lateral_m_s"]) for sample in samples]),
            "steady_forward_error_m_s": stats([abs(sample["forward_m_s"] - sample["rolling_forward_m_s"]) for sample in steady]),
            "steady_yaw_error_rad_s": stats([abs(sample["yaw_rate_rad_s"] - sample["rolling_yaw_rate_rad_s"]) for sample in steady]),
            "steady_forward_speed_m_s": stats([sample["forward_m_s"] for sample in steady]),
            "wheel_speed_abs_rad_s": [stats([abs(sample["wheel_rad_s"][i]) for sample in steady]) for i in range(2)],
            "ground_contact_fraction": {side: sum(sample["contacts"][side]["normal_n"] > .1 for sample in samples) / len(samples) for side in WHEELS},
            "normal_force_n": {side: stats([sample["contacts"][side]["normal_n"] for sample in samples]) for side in WHEELS},
            "forward_contact_impulse_n_s": sum(sum(sample["contacts"][side]["forward_n"] for side in WHEELS) * dt for sample, dt in zip(samples, intervals)),
            "maximum_tire_penetration_m": max(sample["contacts"][side]["maximum_penetration_m"] for sample in samples for side in WHEELS),
            "maximum_base_actuator_force": max(sample["base_actuator_force_max"] for sample in samples),
            "maximum_base_applied_force": max(sample["base_applied_force_max"] for sample in samples),
            "maximum_external_body_wrench": max(sample["external_body_wrench_max"] for sample in samples),
            "maximum_wheel_torque_nm": max(abs(torque) for sample in samples for torque in sample["wheel_torque_nm"]),
            "geometry": geometry}


def raw_drive_trial(left, right, *, duration_s=2., frictionless=False, disabled_motors=False):
    model, data, metadata = load_reference_model()
    wheel_ids = [model.actuator(f"ctrl_{side}_wheel_joint").id for side in WHEELS]
    forbidden = {model.joint(name).id for name in BASE_JOINTS}
    if any(int(joint) in forbidden for joint in model.actuator_trnid[:, 0]):
        raise ValueError("Direct X/Y/yaw base actuator remains; this is not wheel-only propulsion")
    if frictionless:
        for name in ("floor", "left_wheel_geom", "right_wheel_geom"):
            model.geom_friction[model.geom(name).id] = 0.
    if disabled_motors:
        model.actuator_forcerange[wheel_ids] = 0.
        model.actuator_forcelimited[wheel_ids] = 1
    data.ctrl[wheel_ids] = 0.
    for _ in range(round(1. / model.opt.timestep)):
        mujoco.mj_step(model, data)
    mujoco.mj_forward(model, data)
    geometry = drive_geometry(model, data)
    data.ctrl[wheel_ids] = [left, right]
    samples = [drive_observation(model, data, geometry)]
    for index in range(round(duration_s / model.opt.timestep)):
        mujoco.mj_step(model, data)
        if (index + 1) % 10 == 0:
            mujoco.mj_forward(model, data)
            samples.append(drive_observation(model, data, geometry))
    return {"model_hash": metadata["model_hash"], "wheel_command_rad_s": [left, right],
            "counterfactual": "zero tire/floor friction" if frictionless else "zero wheel torque limit" if disabled_motors else None,
            "summary": summarize(samples, geometry), "samples": samples}


def evaluate_raw_drive():
    trials = {
        "forward": raw_drive_trial(1.5, 1.5),
        "turn": raw_drive_trial(-1.5, 1.5),
        "arc": raw_drive_trial(.8, 1.6),
        "no_traction": raw_drive_trial(1.5, 1.5, frictionless=True),
        "motors_off": raw_drive_trial(1.5, 1.5, disabled_motors=True),
    }
    physical = [trials[name]["summary"] for name in ("forward", "turn", "arc")]
    forward, turn = trials["forward"]["summary"], trials["turn"]["summary"]
    checks = {
        "forward_travel_observed": forward["world_displacement_m"][0] > .20,
        "opposite_wheels_turn_observed": turn["yaw_change_rad"] > 1.,
        "small_body_lateral_slip": all(summary["lateral_speed_abs_m_s"]["maximum"] < .005 for summary in physical),
        "rolling_forward_agreement": all(summary["steady_forward_error_m_s"]["p95"] < .015 for summary in physical),
        "rolling_yaw_agreement": all(summary["steady_yaw_error_rad_s"]["p95"] < .04 for summary in physical),
        "both_tires_loaded": all(min(summary["ground_contact_fraction"].values()) > .98 for summary in physical),
        "contact_provides_forward_impulse": forward["forward_contact_impulse_n_s"] > .5,
        "no_direct_base_drive_force": all(summary["maximum_base_actuator_force"] == 0. and summary["maximum_base_applied_force"] == 0. and summary["maximum_external_body_wrench"] == 0. for summary in physical),
        "frictionless_wheels_spin_without_base_propulsion": max(abs(v) for v in trials["no_traction"]["summary"]["world_displacement_m"][:2]) < .005 and min(value["median"] for value in trials["no_traction"]["summary"]["wheel_speed_abs_rad_s"]) > 1.,
        "zero_motor_torque_prevents_propulsion": max(abs(v) for v in trials["motors_off"]["summary"]["world_displacement_m"][:2]) < .005,
    }
    return {"passed": all(checks.values()), "model_hash": trials["forward"]["model_hash"], "mujoco_version": mujoco.__version__,
            "checks": checks, "trials": trials, "hardware_model_verified": False, "authorizes_hardware": False,
            "limitations": ["Roll and pitch remain ideal constrained coordinates; this does not demonstrate two-wheel balancing.",
                            "Estimated tire friction, mass and motor gains are not calibrated vendor hardware parameters.",
                            "Raw wheel experiments validate propulsion; route completion and obstacle clearances require separate runtime trials."],
            "measurement_sources": ["https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-contactforce",
                                    "https://mujoco.readthedocs.io/en/stable/computation/index.html#contact"]}


def allowed_route_contacts(command):
    """Explicit physical fixture pairs, never copied from runtime exclusions."""
    allowed = {frozenset(("floor", f"{side}_wheel_geom")) for side in WHEELS}
    if command in {"phone_return_demo", "deliver_phone_demo", "deliver_meal_demo"}:
        object_geom = "meal_box_geom" if command == "deliver_meal_demo" else "phone_geom"
        allowed.update(frozenset((object_geom, f"left_finger_{finger}_geom")) for finger in (-1, 1))
    if command == "blinds_demo":
        allowed.update(frozenset(("blinds_handle_geom", geom)) for geom in ("left_hand_geom", "left_finger_-1_geom", "left_finger_1_geom"))
    for object_geom, support in (("phone_geom", "phone_riser"), ("meal_box_geom", "meal_riser")):
        allowed.update((frozenset((object_geom, support)), frozenset((object_geom, "bedside_tray"))))
    if command == "deliver_phone_demo":
        allowed.add(frozenset(("phone_geom", "phone_delivery_riser")))
    elif command == "deliver_meal_demo":
        allowed.add(frozenset(("meal_box_geom", "meal_delivery_riser")))
    return allowed


def route_contacts(model, data, command):
    """Classify actual contacts independently of runtime allowance state."""
    base = model.body("robot_base").id
    robot_bodies = {base}
    for body in range(base + 1, model.nbody):
        if int(model.body_parentid[body]) in robot_bodies:
            robot_bodies.add(body)
    objects = {"phone_geom", "meal_box_geom"}
    allowed = allowed_route_contacts(command)
    unexpected = []
    for index, contact in enumerate(data.contact[:data.ncon]):
        geoms = (int(contact.geom1), int(contact.geom2))
        names = [model.geom(geom).name for geom in geoms]
        relevant = any(int(model.geom_bodyid[geom]) in robot_bodies for geom in geoms) or bool(objects.intersection(names))
        if not relevant or frozenset(names) in allowed:
            continue
        force = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, force)
        if contact.dist < -.0001 or force[0] > .1:
            unexpected.append({"geoms": names, "penetration_m": max(0., -float(contact.dist)), "normal_force_n": float(force[0])})
    return unexpected


def route_trial(command, *, interval_s=.02):
    """Measure complete controller runs without altering any state or model."""
    from sim.reference_runtime import ReferenceSimulation

    simulation = ReferenceSimulation()
    model, data = simulation.model, simulation.data
    geometry = drive_geometry(model, data)
    collision_flags = (model.geom_contype.copy(), model.geom_conaffinity.copy())
    state = simulation.command(command)
    budget = state["metrics"]["demo"]["duration_s"] + 4.
    samples, unexpected = [], []
    masks_unchanged = True
    for _ in range(int(budget / interval_s) + 1):
        state = simulation.advance(interval_s)
        sample = drive_observation(model, data, geometry)
        sample["stage"] = state["metrics"]["demo"]["stage"]
        samples.append(sample)
        for contact in route_contacts(model, data, command):
            unexpected.append({"time_s": float(data.time), "stage": sample["stage"], **contact})
        masks_unchanged &= np.array_equal(collision_flags[0], model.geom_contype) and np.array_equal(collision_flags[1], model.geom_conaffinity)
        if state["paused"] or state["metrics"]["demo"]["complete"]:
            break
    summary = summarize(samples, geometry)
    measured = state["metrics"]["demo"]
    checks = {
        "measured_demo_completed": measured["complete"] and all(measured["checks"].values()) and not state["paused"],
        "no_unexpected_contacts": not unexpected,
        "collision_masks_unchanged": bool(masks_unchanged),
        "no_direct_base_drive_force": summary["maximum_base_actuator_force"] == 0. and summary["maximum_base_applied_force"] == 0. and summary["maximum_external_body_wrench"] == 0.,
        "small_lateral_speed": summary["lateral_speed_abs_m_s"]["maximum"] < .01,
        "small_cumulative_lateral_slip": summary["body_lateral_absolute_travel_m"] < .02,
        "rolling_forward_agreement": summary["steady_forward_error_m_s"]["p95"] < .015,
        "rolling_yaw_agreement": summary["steady_yaw_error_rad_s"]["p95"] < .04,
        "both_tires_loaded": min(summary["ground_contact_fraction"].values()) > .98,
    }
    return {"passed": all(checks.values()), "command": command, "model_hash": simulation.metadata["model_hash"],
            "checks": checks, "summary": summary, "final_demo": measured, "stop_reason": state["metrics"]["stop_reason"],
            "unexpected_contacts": unexpected, "samples": samples}


def evaluate_routes(commands=None):
    from sim.reference_demos import DEMO_COMMANDS
    trials = {}
    for command in sorted(DEMO_COMMANDS if commands is None else commands):
        trials[command] = route_trial(command)
        print(json.dumps({"command": command, "passed": trials[command]["passed"], "checks": trials[command]["checks"]}), flush=True)
    return {"passed": all(trial["passed"] for trial in trials.values()), "trials": trials,
            "model_hash": next(iter(trials.values()))["model_hash"], "mujoco_version": mujoco.__version__,
            "sample_interval_s": .02, "hardware_model_verified": False, "authorizes_hardware": False,
            "limitations": ["Contacts are checked against collision proxies, not every rendered mesh triangle.",
                            "Independent measurements sample every 20 ms; the runtime also checks contact stops each physics step.",
                            "Roll/pitch are ideally constrained; wheel propulsion does not validate balancing.",
                            "Scripted fixture routes do not establish autonomous navigation or hardware performance."]}


def write_report(report, destination, *, compress_trace=False):
    """Keep summaries reviewable and preserve every measured sample separately."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if compress_trace:
        raw = gzip.compress(json.dumps(report, separators=(",", ":"), allow_nan=False).encode(), mtime=0)
        archive = destination.with_suffix(".trace.json.gz")
        archive.write_bytes(raw)
        report = {**report, "trials": {name: {key: value for key, value in trial.items() if key != "samples"}
                                      for name, trial in report["trials"].items()},
                  "raw_trace": {"file": archive.name, "sha256": hashlib.sha256(raw).hexdigest(),
                                "contains": "Every independently measured 20 ms sample; JSON compressed with gzip"}}
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/differential-drive-physics.json"))
    parser.add_argument("--routes", action="store_true", help="Audit all six complete shared controller routes instead of raw wheel trials")
    parser.add_argument("--command", action="append", help="Limit --routes to specified command(s)")
    args = parser.parse_args()
    report = evaluate_routes(args.command) if args.routes else evaluate_raw_drive()
    write_report(report, args.output, compress_trace=args.routes)
    print(json.dumps({"passed": report["passed"], "checks": report.get("checks"), "trials": {name: trial["summary"] for name, trial in report["trials"].items()}}))
    raise SystemExit(0 if report["passed"] else 1)
