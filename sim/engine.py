"""Measured MuJoCo surrogate rollout and conservative scene-plan diagnostics.

Neither a successful rollout nor a semantic plan check authorizes hardware.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import mujoco
import numpy as np

from sim.model import build_scene


def load_scene(seed=7, **kwargs):
    xml, metadata = build_scene(seed, **kwargs)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    # Starting bend avoids the fully straight-arm Jacobian singularity.
    for side in ("left", "right"):
        data.qpos[model.joint(f"{side}_joint_2").qposadr[0]] = -.3
        data.qpos[model.joint(f"{side}_joint_4").qposadr[0]] = .6
    for idx in range(model.nu):
        joint = model.actuator_trnid[idx, 0]
        data.ctrl[idx] = data.qpos[model.jnt_qposadr[joint]]
    mujoco.mj_forward(model, data)
    return model, data, metadata


def robot_contacts(model, data) -> list[dict]:
    """Return all robot contacts, including self contacts, without counting furniture settling."""
    result = []
    for contact in data.contact[:data.ncon]:
        names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(i)) or "" for i in (contact.geom1, contact.geom2)]
        is_robot = lambda name: name.startswith(("left_", "right_", "base_", "shoulder", "mast", "head"))
        if any(map(is_robot, names)):
            result.append({"geoms": names, "distance_m": float(contact.dist), "self_collision": all(map(is_robot, names))})
    return result


def inverse_kinematics(model, data, side: str, target, iterations=120) -> dict:
    """Damped position-only IK for the seven synthetic joints; no hardware semantics."""
    if side not in {"left", "right"}:
        raise ValueError("Unknown arm")
    target = np.asarray(target, dtype=float)
    if target.shape != (3,) or not np.isfinite(target).all():
        raise ValueError("IK target must be three finite coordinates")
    site = model.site(f"{side}_ee").id
    joints = [model.joint(f"{side}_joint_{i}").id for i in range(1, 8)]
    qindices = np.array([model.jnt_qposadr[j] for j in joints])
    dofs = np.array([model.jnt_dofadr[j] for j in joints])
    candidate = mujoco.MjData(model)
    candidate.qpos[:] = data.qpos
    for _ in range(iterations):
        mujoco.mj_forward(model, candidate)
        error = target-candidate.site_xpos[site]
        if np.linalg.norm(error) < .008:
            break
        jac = np.zeros((3, model.nv))
        mujoco.mj_jacSite(model, candidate, jac, None, site)
        jac = jac[:, dofs]
        delta = jac.T @ np.linalg.solve(jac @ jac.T + .015*np.eye(3), error)
        candidate.qpos[qindices] = np.clip(candidate.qpos[qindices]+np.clip(delta, -.1, .1), model.jnt_range[joints, 0], model.jnt_range[joints, 1])
    mujoco.mj_forward(model, candidate)
    residual = float(np.linalg.norm(target-candidate.site_xpos[site]))
    return {"reachable": residual < .015, "residual_m": residual, "joint_positions": candidate.qpos[qindices].tolist(), "contacts": robot_contacts(model, candidate), "hardware_model_verified": False}


def _xyz(value: Any) -> np.ndarray:
    if isinstance(value, dict):
        value = [value.get(k, 0) for k in ("x", "y", "z")]
    vector = np.asarray(value, dtype=float)
    if vector.shape != (3,) or not np.isfinite(vector).all():
        raise ValueError("Pose must contain three finite coordinates")
    return vector


def _inside(point, bounds, margin=0.0):
    lo, hi = _xyz(bounds["min"])-margin, _xyz(bounds["max"])+margin
    return bool(np.all(point >= lo) and np.all(point <= hi))


def validate_plan(plan: dict, room: dict) -> dict:
    """Check semantic swept-object/person zones and load/settle a surrogate scene.

    Not a grasp or robot trajectory validation. Root safety must gate authority
    independently. Missing metric targets fail closed for manipulation steps.
    """
    reasons, checks = [], []
    objects = room.get("objects", [])
    objects = objects if isinstance(objects, dict) else {o["id"]: o for o in objects}
    minimum_person_clearance = None
    steps = plan.get("candidate_steps", plan.get("steps", []))
    if not steps:
        reasons.append("No executable candidate steps")
    for step in steps:
        if step.get("action") in {"observe", "scan", "verify", "speak"}:
            checks.append({"step": step.get("id"), "status": "no_physics_required"})
            continue
        obj = objects.get(step.get("object_id", step.get("target_object_id")))
        if not obj:
            reasons.append("Target object absent from current room")
            continue
        try:
            source, target = _xyz(obj["pose"]), _xyz(step["target_pose"])
            dims = _xyz(obj.get("dimensions", {"x": .1, "y": .1, "z": .1}))
        except (ValueError, KeyError, TypeError):
            reasons.append("Missing or invalid metric source/target geometry")
            continue
        radius = float(np.linalg.norm(dims[:2])/2)
        if np.any(dims <= 0):
            reasons.append("Object dimensions must be positive")
        geometry = room.get("geometry", {})
        if geometry and (target[0] < 0 or target[1] < 0 or target[2] < 0 or target[0] > geometry.get("width", math.inf) or target[1] > geometry.get("depth", math.inf) or target[2] > geometry.get("height", math.inf)):
            reasons.append("Target lies outside room geometry")
        path = np.linspace(source, target, 40)
        for person in room.get("persons", room.get("people", [])):
            person_pose = _xyz(person["pose"])
            clearance = min(float(np.linalg.norm(p[:2]-person_pose[:2])-float(person.get("radius", .3))-radius) for p in path)
            minimum_person_clearance = clearance if minimum_person_clearance is None else min(minimum_person_clearance, clearance)
            if clearance < .75:
                reasons.append("Swept object path enters synthetic 0.75 m person clearance")
        for zone in room.get("zones", []):
            if zone.get("type", "").lower() in {"keep_out", "keepout", "patient", "privacy", "egress", "keep_clear"} and "bounds" in zone:
                if any(_inside(p, zone["bounds"], radius) for p in path):
                    reasons.append(f"Swept object path intersects protected zone {zone['id']}")
        checks.append({"step": step.get("id"), "object_id": obj["id"], "swept_samples": len(path), "distance_m": float(np.linalg.norm(target-source))})
    try:
        model, data, metadata = load_scene(seed=7, clutter=0)
        for _ in range(50):
            mujoco.mj_step(model, data)
        finite = bool(np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all())
        if not finite:
            reasons.append("Surrogate dynamics became nonfinite")
        metrics = {"physics_steps": 50, "physics_duration_s": float(data.time), "finite_dynamics": finite, "minimum_person_clearance_m": minimum_person_clearance, "trajectory_validated": False, "grasp_validated": False}
    except Exception as exc:
        reasons.append(f"MuJoCo scene load/step failed: {type(exc).__name__}: {exc}")
        metadata, metrics = {}, {"physics_steps": 0, "trajectory_validated": False, "grasp_validated": False}
    return {"passed": not reasons, "status": "surrogate_checks_passed" if not reasons else "rejected", "scope": "semantic_object_path_and_surrogate_engine_smoke", "hardware_model_verified": False, "authorizes_hardware": False, "model_hash": metadata.get("model_hash"), "plan_hash": hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(), "room_version": room.get("version"), "reasons": sorted(set(reasons)), "checks": checks, "metrics": metrics, "limitations": ["No robot trajectory or grasp has been validated", "Swept object check is not a full swept robot volume", "All robot dimensions are synthetic"]}


ABSTENTION_CASES = [
    {"name": "permitted_phone", "object_class": "phone", "confidence": .98, "mass_kg": .2, "person_clearance_m": 1.2, "attached": False, "in_distribution": True},
    {"name": "prohibited_object", "object_class": "iv_pump", "confidence": .99, "mass_kg": .2, "person_clearance_m": 1.2, "attached": False, "in_distribution": True},
    {"name": "uncertain_identity", "object_class": "phone", "confidence": .3, "mass_kg": .2, "person_clearance_m": 1.2, "attached": False, "in_distribution": True},
    {"name": "excessive_load", "object_class": "phone", "confidence": .98, "mass_kg": 3, "person_clearance_m": 1.2, "attached": False, "in_distribution": True},
    {"name": "person_enters", "object_class": "phone", "confidence": .98, "mass_kg": .2, "person_clearance_m": .1, "attached": False, "in_distribution": True},
    {"name": "attached_object", "object_class": "phone", "confidence": .98, "mass_kg": .2, "person_clearance_m": 1.2, "attached": True, "in_distribution": True},
    {"name": "policy_ood", "object_class": "phone", "confidence": .98, "mass_kg": .2, "person_clearance_m": 1.2, "attached": False, "in_distribution": False},
    {"name": "poor_grasp", "object_class": "phone", "confidence": .98, "grasp_confidence": .2, "mass_kg": .2, "person_clearance_m": 1.2, "attached": False, "in_distribution": True},
    {"name": "blocked_path", "object_class": "phone", "confidence": .98, "mass_kg": .2, "person_clearance_m": 1.2, "attached": False, "in_distribution": True, "blocked_path": True},
]


def abstention_gate(observation: dict) -> dict:
    """Synthetic evaluation envelope, independent of any learned policy."""
    reasons = []
    if observation.get("object_class") not in {"phone", "remote", "glasses_case", "book", "small_bag"}:
        reasons.append("object_class_not_allowlisted")
    for field, minimum in (("confidence", .9), ("grasp_confidence", .8), ("person_clearance_m", .75)):
        default = 1 if field == "grasp_confidence" else -1
        value = observation.get(field, default)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
            reasons.append(f"insufficient_{field}")
    mass = observation.get("mass_kg")
    if not isinstance(mass, (int, float)) or not math.isfinite(mass) or not 0 < mass <= .5:
        reasons.append("outside_synthetic_payload_envelope")
    if observation.get("attached") is not False:
        reasons.append("attachment_not_cleared")
    if observation.get("in_distribution") is not True:
        reasons.append("outside_validated_distribution")
    if observation.get("blocked_path"):
        reasons.append("blocked_path")
    return {"abstain": bool(reasons), "reasons": reasons, "authorizes_hardware": False}


def run_benchmark(episodes: int = 12, seed: int = 7) -> dict:
    if not 1 <= episodes <= 200:
        raise ValueError("episodes must be between 1 and 200")
    results = []
    for idx in range(episodes):
        model, data, metadata = load_scene(seed+idx, clutter=idx % 6, table_height=.68+(idx % 4)*.035)
        start = data.qpos.copy()
        # Actuate both arms and lift: actual forward dynamics, not an edited pose.
        for side, sign in (("left", 1), ("right", -1)):
            data.ctrl[model.actuator(f"ctrl_{side}_joint_1").id] = sign*.12
        data.ctrl[model.actuator("ctrl_lift").id] = .08
        collision_steps, self_collision_steps, max_speed = 0, 0, 0.0
        for _ in range(300):
            mujoco.mj_step(model, data)
            contacts = robot_contacts(model, data)
            collision_steps += bool(contacts)
            self_collision_steps += any(c["self_collision"] for c in contacts)
            max_speed = max(max_speed, float(np.max(np.abs(data.qvel))))
        finite = bool(np.isfinite(data.qpos).all())
        left_site = data.site_xpos[model.site("left_ee").id].copy()
        target = left_site+np.array([-.04, .03, .025])
        ik = inverse_kinematics(model, data, "left", target)
        abstention = abstention_gate(ABSTENTION_CASES[idx % len(ABSTENTION_CASES)])
        results.append({"episode": idx, "seed": seed+idx, "scenario": ABSTENTION_CASES[idx % len(ABSTENTION_CASES)]["name"], "clutter": idx % 6, "model_hash": metadata["model_hash"], "physics_steps": 300, "simulated_seconds": float(data.time), "finite_dynamics": finite, "robot_contact_steps": collision_steps, "self_collision_steps": self_collision_steps, "max_generalized_speed": max_speed, "lift_displacement_m": float(data.qpos[model.joint("lift").qposadr[0]]-start[model.joint("lift").qposadr[0]]), "left_ik_reachable": ik["reachable"], "left_ik_residual_m": ik["residual_m"], "abstention": abstention, "grasp_success": None, "bimanual_manipulation_success": None})
    return {"benchmark": "surrogate_dynamics_ik_and_deterministic_abstention", "seed": seed, "episodes": episodes, "mujoco_version": mujoco.__version__, "hardware_model_verified": False, "authorizes_hardware": False, "results": results, "summary": {"finite_dynamics_rate": sum(r["finite_dynamics"] for r in results)/episodes, "ik_reachable_rate": sum(r["left_ik_reachable"] for r in results)/episodes, "episodes_with_robot_contacts": sum(r["robot_contact_steps"] > 0 for r in results), "abstention_rate": sum(r["abstention"]["abstain"] for r in results)/episodes, "physics_steps": 300*episodes, "task_success_rate": None, "sim_to_real_gap": None}, "limitations": ["This suite measures arm/lift dynamics, endpoint IK, contacts and a deterministic abstention filter", "No physical grasp, bimanual bag manipulation, cloth skill or trained VLA is scored", "Robot and hospital props have synthetic parameters", "Numerical contact metrics are reported, not suppressed"]}


def render_scene(path, seed=7, camera="overview", depth=False):
    from PIL import Image
    model, data, metadata = load_scene(seed)
    for _ in range(30):
        mujoco.mj_step(model, data)
    with mujoco.Renderer(model, height=640, width=960) as renderer:
        if depth:
            renderer.enable_depth_rendering()
        renderer.update_scene(data, camera=camera)
        pixels = renderer.render()
        if depth:
            np.save(path, pixels)
        else:
            Image.fromarray(pixels).save(path)
    return {"path": str(path), "camera": camera, "depth": depth, "model_hash": metadata["model_hash"], "synthetic": True}


def replay_trajectory(frames: list[dict], seed=7, robot_revision="surrogate_v1") -> dict:
    """Replay bounded joint targets through MuJoCo position servos, with contact stop.

    Real robot recordings cannot be interpreted until vendor joint mapping exists.
    This checks synthetic arm/lift target playback; it does not replay video.
    """
    if robot_revision != "surrogate_v1":
        raise ValueError("Vendor action/joint mapping is unverified; only surrogate_v1 may replay")
    if not 1 <= len(frames) <= 1000:
        raise ValueError("Replay requires 1-1000 frames")
    model, data, metadata = load_scene(seed, clutter=0)
    reports, previous_time = [], None
    for frame in frames:
        timestamp = float(frame["timestamp_s"])
        if not math.isfinite(timestamp) or timestamp < 0 or (previous_time is not None and not 0 < timestamp-previous_time <= .1):
            raise ValueError("Replay must be monotonic with at most 100 ms gaps")
        for side in ("left", "right"):
            values = frame.get(f"{side}_arm_q")
            if values is None or len(values) != 7 or not all(math.isfinite(v) and abs(v) <= 2.6 for v in values):
                raise ValueError("Invalid synthetic joint targets")
            for index, value in enumerate(values, 1):
                data.ctrl[model.actuator(f"ctrl_{side}_joint_{index}").id] = value
        lift = frame.get("vertical_stage_state", [0.0])[0]
        if not math.isfinite(lift) or not 0 <= lift <= .5:
            raise ValueError("Invalid synthetic lift target")
        data.ctrl[model.actuator("ctrl_lift").id] = lift
        duration = .05 if previous_time is None else timestamp-previous_time
        contacts = []
        for _ in range(max(1, int(duration/model.opt.timestep))):
            mujoco.mj_step(model, data)
            contacts = robot_contacts(model, data)
            if contacts or not np.isfinite(data.qpos).all():
                break
        reports.append({"timestamp_s": timestamp, "simulated_seconds": float(data.time), "robot_contacts": contacts, "finite_dynamics": bool(np.isfinite(data.qpos).all())})
        if contacts or not reports[-1]["finite_dynamics"]:
            break
        previous_time = timestamp
    return {"model_hash": metadata["model_hash"], "frames_requested": len(frames), "frames_replayed": len(reports), "frames": reports, "stopped": bool(reports[-1]["robot_contacts"] or not reports[-1]["finite_dynamics"]), "hardware_model_verified": False, "authorizes_hardware": False}
