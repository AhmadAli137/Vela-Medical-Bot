from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from pydantic import ValidationError

from robot.capabilities import UnconfiguredBracketBot, manifest
from robot.mock import MockBracketBot
from services.planner import build_plan
from services.router import triage
from services.safety import evaluate, check_joint_limits, check_velocity_limits, check_object_permission
from services.store import Store, digest
from services.world import desired_diff, seed_room, snapshot, temporal_diff
from shared.models import TaskProposal


@pytest.mark.parametrize("text",[
    "My chest hurts", "I cannot breathe", "I am bleeding", "Bring my phone and my medication",
    "I fell", "Silence the alarm", "Move my IV", "No pain, just bring my phone", "Turn me over",
    "Help me stand", "Adjust the oxygen", "Which dose should I take?", "My catheter is stuck",
    "I feel dizzy", "I am unwell", "Move the feeding tube", "I want to die", "Nurse please",
    "ｐａｉｎ and bring phone", "Bring phone because it hurts", "phone and blood pressure pump",
    "bring my phone because I feel weak", "bring my phone and silence the ventilator", "bring my phone, I cannot see", "Bring my phone and do something else",
])
def test_critical_rules_cannot_be_downgraded(text):
    result = triage(text,model_route="B")
    assert result["route"] == "D"
    assert result["locked"]


@pytest.mark.parametrize("text,route",[("When are visiting hours?","A"),("What's happening next?","A"),("Where is my wheelchair?","A"),("Bring my phone closer","B"),("Prepare the room for physio","B"),("Please clean my room","C"),("I need a towel","C"),("Help","D"),("Do something","D"),("","D")])
def test_routes(text,route):
    assert triage(text)["route"] == route


def test_model_only_escalates():
    assert triage("Bring my phone",model_route="D")["route"] == "D"
    assert triage("something unknown",model_route="B")["route"] == "D"


def task_fixture(room=None):
    room = room or seed_room()
    task = build_plan({"goal":"Bring my phone closer"},room)
    task["approval_hash"] = task["plan_hash"]
    report = {"passed":True,"plan_hash":task["plan_hash"],"room_hash":digest(room)}
    robot = {"estop":False,"watchdog_ok":True,"health":"ok","online":True,"manipulation_paused":False}
    return task,room,robot,report


def test_hardware_manifest_never_asserts_runtime_verification():
    data = manifest()
    assert len(data["arms"]) == 2 and all(a["dof"]["value"] == 7 for a in data["arms"])
    assert data["arms"][0]["stated_payload"]["value"] == 2
    assert not data["hardware_model_verified"] and not data["execution_enabled"]
    assert data["watchdog"]["value"] is None
    def walk(item):
        if isinstance(item,dict):
            if "value" in item:
                assert item["source"] and item["verification"] in ("unknown","reported")
            for value in item.values():
                walk(value)
        elif isinstance(item,list):
            for value in item:
                walk(value)
    walk(data)
    with pytest.raises(RuntimeError):
        UnconfiguredBracketBot().execute_verified_trajectory({"approved":True})
    assert not UnconfiguredBracketBot().stop()["confirmed"]


def test_hardware_denial_even_with_every_mock_gate_passing():
    task,room,robot,report = task_fixture()
    assert evaluate(task,room,robot,report)["allowed"]
    assert not evaluate(task,room,robot,report,target="hardware")["allowed"]


@pytest.mark.parametrize("field,value",[("estop",True),("watchdog_ok",False),("online",False),("health","fault"),("manipulation_paused",True)])
def test_runtime_health_veto(field,value):
    task,room,robot,report = task_fixture()
    robot[field] = value
    assert not evaluate(task,room,robot,report)["allowed"]


@pytest.mark.parametrize("field,value",[("policy","UNKNOWN_PROHIBITED"),("policy","CLINICAL_PROHIBITED"),("attached",True),("confidence",.4),("grasp_confidence",.4),("mass_range_kg",None),("mass_range_kg",[2,3]),("reachable_by_robot",False),("clinical_sensitivity",True)])
def test_object_veto(field,value):
    room = seed_room()
    room["objects"][0][field] = value
    task,room,robot,report = task_fixture(room)
    assert not evaluate(task,room,robot,report)["allowed"]


def test_clinical_permission_cannot_be_relabelled_safe():
    room = seed_room()
    obj = next(o for o in room["objects"] if o["id"] == "iv_pump")
    obj["policy"] = "SAFE_GENERAL"
    obj["clinical_sensitivity"] = False
    assert not check_object_permission(obj,approved=True,teleop=True)


def test_stale_snapshot_and_expired_observation_reject():
    task,room,robot,report = task_fixture()
    assert not evaluate(task,snapshot(room),robot,report)["allowed"]
    room["timestamp"] = (datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
    task,room,robot,report = task_fixture(room)
    assert not evaluate(task,room,robot,report)["allowed"]


def test_person_and_attached_relationship_reject():
    room = seed_room()
    room["persons"] = [{"pose":room["objects"][0]["pose"],"radius":.3}]
    assert not evaluate(*task_fixture(room))["allowed"]
    room = seed_room()
    room["objects"][0]["relationships"] = [{"type":"attached","target":"patient"}]
    assert not evaluate(*task_fixture(room))["allowed"]


def test_forged_report_and_approval_rejected():
    task,room,robot,report = task_fixture()
    task["approval_hash"] = "another-plan"
    assert not evaluate(task,room,robot,report)["allowed"]
    task["approval_hash"] = task["plan_hash"]
    report["room_hash"] = "different-room"
    assert not evaluate(task,room,robot,report)["allowed"]


def test_policy_candidate_cannot_escape_semantic_goal():
    task,room,robot,report = task_fixture()
    task["proposal"]["candidate_steps"][0]["target_pose"] = {"x":1,"y":1,"z":1}
    assert not evaluate(task,room,robot,report)["allowed"]


def test_strict_schema_rejects_actuator_fields_and_nonfinite_geometry():
    task,room,robot,report = task_fixture()
    data = deepcopy(task["proposal"])
    data["motor_pwm"] = 100
    with pytest.raises(ValidationError):
        TaskProposal.model_validate(data)
    data.pop("motor_pwm")
    data["candidate_steps"][0]["target_pose"]["x"] = float("nan")
    with pytest.raises(ValidationError):
        TaskProposal.model_validate(data)


def test_joint_velocity_missing_or_invalid_limits_reject():
    assert not check_joint_limits([1],[])
    assert not check_joint_limits([float("nan")],[(-2,2)])
    assert not check_velocity_limits([3],[1])
    assert not check_velocity_limits([0],[])


def test_room_temporal_diff_and_verification():
    task,room,robot,report = task_fixture()
    adapter = MockBracketBot()
    after = adapter.execute(task,room,evaluate(task,room,robot,report))
    assert adapter.verify(task,after)["passed"]
    assert not adapter.verify(task,room)["passed"]
    assert any(c["kind"] == "pose" for c in temporal_diff(room,after)["changes"])
    assert room["version"]+1 == after["version"]


def test_room_ready_requires_egress_clear():
    room = seed_room()
    assert not desired_diff(room,"physio_ready")["ready"]
    assert desired_diff(room,"physio_ready")["blockers"]
    task = build_plan({"goal":"Prepare room for physio","template":"physio_ready"},room)
    task["approval_hash"] = task["plan_hash"]
    report = {"passed":True,"plan_hash":task["plan_hash"],"room_hash":digest(room)}
    robot = task_fixture()[2]
    after = MockBracketBot().execute(task,room,evaluate(task,room,robot,report))
    assert desired_diff(after,"physio_ready")["ready"]


def test_store_transaction_rollback_and_audit_append_only():
    store = Store(":memory:")
    store.event("one","test",{})
    assert store.verify_audit()
    with pytest.raises(ValueError), store.transaction():
        store.put("test","id",{"value":1})
        raise ValueError("rollback")
    with pytest.raises(KeyError):
        store.get("test","id")
    with pytest.raises(Exception):
        store.db.execute("DELETE FROM events")
    assert store.verify_audit()
