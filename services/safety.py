"""Deterministic veto independent of language models and learned policies.

Thresholds below apply exclusively to synthetic software fixtures. They are
not vendor limits or hospital-approved clearances. No hardware is enabled.
"""
import math
from datetime import datetime, timezone
from services.store import digest
from services.world import get_object, in_zone, overlaps_zone

POLICY_VERSION = "mock-room-policy/1.0.0"
PROHIBITED_CLASSES = {"bed", "iv_pump", "medication", "sharps", "patient", "oxygen", "catheter", "clinical_device", "feeding_tube"}
MOCK_LIMITS = {"person_clearance_m": 1.0, "payload_kg": 1.0, "identity_confidence": .95, "grasp_confidence": .9, "freshness_seconds": 120, "command_horizon_ms": 100}


def check_clinical_prohibition(obj):
    return obj.get("semantic_class") not in PROHIBITED_CLASSES and not obj.get("clinical_sensitivity") and obj.get("policy") != "CLINICAL_PROHIBITED"


def check_object_permission(obj, approved=False, teleop=False):
    if not check_clinical_prohibition(obj):
        return False
    policy = obj.get("policy", "UNKNOWN_PROHIBITED")
    return policy == "SAFE_GENERAL" or (policy in ("SAFE_WITH_POLICY", "STAFF_APPROVAL") and approved) or (policy == "TELEOP_ONLY" and teleop and approved)


def check_target_identity(obj):
    return obj.get("confidence", 0) >= MOCK_LIMITS["identity_confidence"]


def check_attached_object(obj):
    return obj.get("attached") is False and not any(r.get("type") in ("attached", "connected", "attached-to") for r in obj.get("relationships", []) if isinstance(r, dict))


def check_payload(obj):
    mass = obj.get("mass_range_kg")
    return isinstance(mass, list) and len(mass) == 2 and all(isinstance(v, (int,float)) and math.isfinite(v) for v in mass) and 0 <= mass[0] <= mass[1] <= MOCK_LIMITS["payload_kg"]


def check_grasp_confidence(obj):
    return obj.get("grasp_confidence", 0) >= MOCK_LIMITS["grasp_confidence"]


def check_patient_distance(start, end, persons):
    a = [start[k] for k in ("x","y","z")]
    b = [end[k] for k in ("x","y","z")]
    for person in persons:
        p = [person["pose"][k] for k in ("x","y","z")]
        delta = [b[i]-a[i] for i in range(3)]
        length2 = sum(v*v for v in delta)
        t = max(0,min(1,sum((p[i]-a[i])*delta[i] for i in range(3))/length2)) if length2 else 0
        distance = math.sqrt(sum((p[i]-(a[i]+t*delta[i]))**2 for i in range(3)))
        if distance < MOCK_LIMITS["person_clearance_m"] + person.get("radius", .3):
            return False
    return True


def check_workspace(point, geometry):
    return 0 <= point["x"] <= geometry["width"] and 0 <= point["y"] <= geometry["depth"] and 0 <= point["z"] <= geometry["height"]


def check_keepout_zone(obj, target, zones):
    # Conservative swept AABB. Over-approximates every straight-line fixture move.
    swept = {"pose": {a:(obj["pose"][a]+target[a])/2 for a in ("x","y","z")}, "dimensions": {a:abs(obj["pose"][a]-target[a])+obj["dimensions"][a] for a in ("x","y","z")}}
    return not any(overlaps_zone(swept,z) for z in zones if z["type"] in ("keepout", "privacy"))


def check_joint_limits(values, bounds):
    return bool(bounds) and len(values) == len(bounds) and all(math.isfinite(v) and low <= v <= high for v,(low,high) in zip(values,bounds))


def check_velocity_limits(values, limits):
    return bool(limits) and len(values) == len(limits) and all(math.isfinite(v) and math.isfinite(limit) and limit > 0 and abs(v) <= limit for v,limit in zip(values,limits))


def check_watchdog(state):
    return state.get("watchdog_ok") is True


def check_estop(state):
    return state.get("estop") is False


def check_robot_health(state):
    return state.get("online") is True and state.get("health") == "ok"


def check_policy_distribution(step):
    return step.get("execution_type") == "DETERMINISTIC" and step.get("skill_id") == "mock-semantic-place-v1"


def check_collision_prediction(report):
    return bool(report and report.get("passed") is True and report.get("plan_hash") and report.get("room_hash"))


def check_human_in_workspace(room):
    return all(p.get("pose") is not None and p.get("radius", 0) >= 0 for p in room.get("persons", []))


def evaluate(task, room, robot, simulation=None, target="mock", require_sim=True):
    checks = []
    def check(name, passed, reason):
        checks.append({"name":name, "passed":bool(passed), "reason":reason})
    check("execution_target", target == "mock", "Only synthetic state transitions are implemented; vendor hardware unverified")
    check("plan_snapshot", task["room_version"] == room["version"] and task["room_hash"] == digest(room), "Plan must match the exact current room snapshot")
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(room["timestamp"])).total_seconds()
    check("observation_freshness", 0 <= age <= MOCK_LIMITS["freshness_seconds"], "Mock observation must be recent; scan and replan")
    check("policy_version", task["policy_version"] == POLICY_VERSION, "Policy changes invalidate prior approval")
    check("estop", check_estop(robot), "E-stop must be released")
    check("watchdog", check_watchdog(robot), "Watchdog health required")
    check("robot_health", check_robot_health(robot), "Robot must be online and healthy")
    check("manipulation_enabled", not robot.get("manipulation_paused", True), "Manipulation pause has veto authority")
    check("person_observation", check_human_in_workspace(room), "Person safety geometry must be available")
    approved = task.get("approval_hash") == task["plan_hash"]
    check("human_approval", not task["proposal"]["human_approval_required"] or approved, "Approval binds to plan and room snapshot")
    critique = task["critique"]
    check("independent_critique", critique["verdict"] == "accept_candidate" and not critique["clinical_boundary_violation"] and critique["solves_original_intent"], "Critic may veto a candidate; it cannot authorize hardware")
    for step in task["proposal"]["candidate_steps"]:
        obj = get_object(room, step["object_id"])
        prefix = step["object_id"] + ":"
        check(prefix+"target_exists", obj is not None, "Exact object instance required")
        if obj is None:
            continue
        zone = next((z for z in room["zones"] if z["id"] == step.get("target_zone")),None)
        check(prefix+"semantic_destination", zone is not None and in_zone(step["target_pose"],zone), "Candidate must satisfy its intended semantic destination")
        check(prefix+"action_type", step.get("action") == "place_in_zone", "Only the mock semantic placement transition exists")
        for name, passed in (("clinical_prohibition", check_clinical_prohibition(obj)), ("object_permission", check_object_permission(obj,approved)), ("target_identity",check_target_identity(obj)), ("attached_object",check_attached_object(obj)), ("payload",check_payload(obj)), ("grasp_confidence",check_grasp_confidence(obj)), ("reachable",obj.get("reachable_by_robot") is True), ("workspace",check_workspace(step["target_pose"],room["geometry"])), ("keepout",check_keepout_zone(obj,step["target_pose"],room["zones"])), ("patient_distance",check_patient_distance(obj["pose"],step["target_pose"],room["persons"])), ("policy_distribution",check_policy_distribution(step))):
            check(prefix+name, passed, "Synthetic envelope check: " + name)
    if require_sim:
        check("simulation", check_collision_prediction(simulation), "Passing surrogate geometry/dynamics validation required for demo transition")
        check("simulation_binding", bool(simulation and simulation.get("plan_hash") == task["plan_hash"] and simulation.get("room_hash") == digest(room)), "Simulation must match this plan and room")
    reasons = [c["name"] + ": " + c["reason"] for c in checks if not c["passed"]]
    return {"allowed": not reasons, "target":target, "authorizes_hardware":False, "policy_version":POLICY_VERSION, "checks":checks, "reasons":reasons, "limits_provenance":"synthetic research fixture only"}
