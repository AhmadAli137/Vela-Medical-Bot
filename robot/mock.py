from copy import deepcopy
from services.world import get_object, in_zone, snapshot


class MockBracketBot:
    """Logical scene adapter. It cannot and does not dispatch actuator commands."""
    def observe(self, room):
        return deepcopy(room)

    def execute(self, task, room, decision):
        if decision.get("allowed") is not True or decision.get("target") != "mock":
            raise ValueError("Mock execution requires a passing deterministic gate")
        observed = snapshot(room)
        for step in task["proposal"]["candidate_steps"]:
            obj = get_object(observed,step["object_id"])
            obj["pose"] = deepcopy(step["target_pose"])
            obj["relationships"] = [{"type":"belongs-in-zone","target":step["target_zone"]}]
            obj["reachable_by_patient"] = step["target_zone"] == "accessible_zone"
            obj["state"] = "placed_in_mock_world"
        return observed

    def verify(self, task, observed):
        predicates = []
        for step in task["proposal"]["candidate_steps"]:
            obj = get_object(observed,step["object_id"])
            zone = next(z for z in observed["zones"] if z["id"] == step["target_zone"])
            predicates.append({"object_id":step["object_id"],"target_zone":step["target_zone"],"passed":bool(obj and in_zone(obj["pose"],zone))})
        return {"passed":all(p["passed"] for p in predicates),"predicates":predicates,"source":"re-observed synthetic world state", "physical_grasp_verified":False}

