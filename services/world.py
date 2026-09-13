"""Persistent semantic room snapshots use synthetic metric fixtures only."""
from copy import deepcopy
import random
from services.store import now

TEMPLATES = {
    "admission_ready": {"phone": "accessible_zone", "chair": "visitor_zone", "bag": "storage_zone"},
    "rounds_ready": {"chair": "visitor_zone", "bag": "storage_zone"},
    "physio_ready": {"chair": "visitor_zone", "bag": "storage_zone", "remote": "accessible_zone"},
    "meal_ready": {"phone": "accessible_zone", "bag": "storage_zone"},
    "visitor_ready": {"chair": "visitor_zone", "bag": "storage_zone"},
    "rest": {"phone": "accessible_zone", "remote": "accessible_zone"},
    "discharge_ready": {"phone": "storage_zone", "bag": "storage_zone", "remote": "accessible_zone"},
    "turnover_nonclinical_ready": {"chair": "visitor_zone", "bag": "storage_zone", "remote": "accessible_zone"},
}


def pose(x, y, z):
    return dict(x=x, y=y, z=z)


def seed_room(seed=7):
    rng = random.Random(seed)
    def obj(identifier, label, x, y, z, dimensions, policy="SAFE_GENERAL", mass=0.2):
        return {"id": identifier, "label": label, "semantic_class": identifier, "pose": pose(x, y, z), "dimensions": pose(*dimensions), "policy": policy, "confidence": .99, "mobility": "movable" if policy != "CLINICAL_PROHIBITED" else "fixed", "mass_range_kg": [mass*.8, mass], "clinical_sensitivity": policy == "CLINICAL_PROHIBITED", "attached": False, "reachable_by_robot": True, "reachable_by_patient": False, "grasp_confidence": .98, "grasp_hypotheses": ["synthetic_top_grasp"], "state": "observed", "relationships": [], "last_observed": now(), "provenance": "synthetic mock-room fixture; not measured hardware"}
    return {
        "id": "room-417", "name": "Room 417", "unit": "Mock care unit", "hospital": "Vela demonstration hospital (synthetic)", "version": 1, "timestamp": now(), "source": "synthetic", "geometry": {"width": 6, "depth": 5, "height": 3},
        "objects": [obj("phone", "Personal phone", rng.uniform(1, 1.5), 1.2, .8, (.08, .16, .015)), obj("chair", "Lightweight chair proxy", 2.9, 2.4, .4, (.4, .4, .8), "STAFF_APPROVAL", .7), obj("bag", "Small empty bag", 3.1, 1.9, .2, (.25, .2, .3), "SAFE_WITH_POLICY", .3), obj("remote", "TV remote", 1.3, 1.6, .8, (.06,.18,.03)), obj("bed", "Hospital bed (keep out)", 4.5, 3.3, .5, (1.1, 2, 1), "CLINICAL_PROHIBITED", 100), obj("iv_pump", "Clinical equipment (keep out)", 4.6, 1.7, .8, (.4,.4,1.5), "CLINICAL_PROHIBITED", 5)],
        "zones": [
            {"id": "accessible_zone", "type": "approved_surface", "label": "Accessible side surface", "bounds": {"min": pose(2, 3.6, .7), "max": pose(2.7, 4.3, 1)}},
            {"id": "visitor_zone", "type": "staff_zone", "label": "Visitor space", "bounds": {"min": pose(.5, 3.3, 0), "max": pose(1.5, 4.4, 1)}},
            {"id": "storage_zone", "type": "robot_operating_zone", "label": "Belongings", "bounds": {"min": pose(.5,.3,0), "max": pose(1.5,.9,1)}},
            {"id": "egress", "type": "clear_path", "label": "Keep clear", "bounds": {"min": pose(2.8,0,0), "max": pose(3.6,3.5,2)}},
            {"id": "patient_zone", "type": "keepout", "label": "Patient space", "bounds": {"min": pose(3.8,2.2,0), "max": pose(5.4,4.5,2.5)}}],
        "persons": [], "doorways": [{"id": "entry", "pose": pose(3.2,0,0)}], "privacy": {"camera_enabled": False, "microphone_enabled": False, "recording": False, "raw_retention_seconds": 0}, "robot_pose": pose(1.8,2.5,0),
    }


def get_object(room, identifier):
    return next((obj for obj in room["objects"] if obj["id"] == identifier), None)


def in_zone(point, zone, margin=0):
    return all(zone["bounds"]["min"][axis] + margin <= point[axis] <= zone["bounds"]["max"][axis] - margin for axis in ("x", "y", "z"))


def overlaps_zone(obj, zone):
    return all(obj["pose"][a] + obj["dimensions"][a]/2 > zone["bounds"]["min"][a] and obj["pose"][a] - obj["dimensions"][a]/2 < zone["bounds"]["max"][a] for a in ("x", "y", "z"))


def zone_target(room, zone_id, index=0):
    zone = next(z for z in room["zones"] if z["id"] == zone_id)
    result = {a: (zone["bounds"]["min"][a]+zone["bounds"]["max"][a])/2 for a in ("x", "y", "z")}
    # Separate small personal-item slots on a synthetic surface.
    if zone_id == "accessible_zone":
        result["y"] += (index % 3 - 1) * .20
    return result


def desired_diff(room, template):
    if template not in TEMPLATES:
        raise ValueError("Unknown desired-state template")
    changes = []
    for identifier, target in TEMPLATES[template].items():
        obj = get_object(room, identifier)
        zone = next(z for z in room["zones"] if z["id"] == target)
        if obj is None or not in_zone(obj["pose"], zone):
            changes.append({"object_id": identifier, "label": obj["label"] if obj else identifier, "predicate": "within", "target_zone": target, "current": obj["pose"] if obj else None, "reason": "outside desired zone" if obj else "missing object", "permitted": bool(obj and obj["policy"] not in ("CLINICAL_PROHIBITED", "UNKNOWN_PROHIBITED", "TELEOP_ONLY"))})
    blockers = [{"object_id": obj["id"], "zone_id": z["id"], "reason": "blocking clear path"} for z in room["zones"] if z["type"] == "clear_path" for obj in room["objects"] if overlaps_zone(obj,z)]
    return {"template": template, "room_version": room["version"], "ready": not changes and not blockers, "changes": changes, "blockers": blockers, "constraints": ["objects in semantic zones", "egress clear", "no clinical interaction"], "source": "synthetic semantic check"}


def temporal_diff(before, after):
    old = {obj["id"]: obj for obj in before["objects"]}
    new = {obj["id"]: obj for obj in after["objects"]}
    changes = []
    for identifier in sorted(old.keys() | new.keys()):
        if identifier not in old or identifier not in new:
            changes.append({"object_id": identifier, "kind": "appeared" if identifier in new else "disappeared"})
        else:
            for field in ("pose", "state", "policy", "confidence", "relationships", "reachable_by_patient", "attached"):
                if old[identifier].get(field) != new[identifier].get(field):
                    changes.append({"object_id": identifier, "kind": field, "before": old[identifier].get(field), "after": new[identifier].get(field)})
    return {"from_version": before["version"], "to_version": after["version"], "changes": changes}


def snapshot(room):
    result = deepcopy(room)
    result["version"] += 1
    result["timestamp"] = now()
    for obj in result["objects"]:
        obj["last_observed"] = result["timestamp"]
    return result

