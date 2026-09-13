from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from services.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path/"api.sqlite3")
    with TestClient(app) as c:
        c.post("/api/session",json={"role":"staff"})
        yield c


def plan(client,goal="Bring my phone closer"):
    result = client.post("/api/tasks/plan",json={"goal":goal,"room_id":"room-417"})
    assert result.status_code == 200, result.text
    return result.json()


def validate_and_approve(client,identifier):
    assert client.post(f"/api/tasks/{identifier}/approve",json={}).status_code == 200
    result = client.post(f"/api/tasks/{identifier}/validate",json={})
    assert result.status_code == 200, result.text
    assert result.json()["simulation"]["passed"],result.text


def test_request_to_verified_mock_completion(client):
    request = client.post("/api/requests",json={"text":"Bring my phone closer"}).json()
    assert request["route"] == "B"
    identifier = request["task_id"]
    validate_and_approve(client,identifier)
    result = client.post(f"/api/tasks/{identifier}/execute",json={}).json()
    assert result["status"] == "completed"
    assert result["verification"]["passed"]
    assert result["verification"]["physical_grasp_verified"] is False
    assert client.post(f"/api/tasks/{identifier}/execute",json={}).status_code == 409


def test_room_preparation_end_to_end(client):
    task = plan(client,"Prepare the room for physio")
    validate_and_approve(client,task["id"])
    result = client.post(f"/api/tasks/{task['id']}/execute",json={}).json()
    assert result["status"] == "completed",result
    assert client.get("/api/rooms/room-417/diff?template=physio_ready").json()["ready"]


def test_no_approval_no_execution_and_hardware_never_enabled(client):
    task = plan(client)
    result = client.post(f"/api/tasks/{task['id']}/execute",json={}).json()
    assert result["status"] == "blocked"
    validate_and_approve(client,task["id"])
    result = client.post(f"/api/tasks/{task['id']}/execute",json={"target":"hardware"}).json()
    assert result["status"] == "blocked" and not result["safety"]["authorizes_hardware"]


def test_clinical_request_uses_mock_escalation_and_cannot_plan(client):
    response = client.post("/api/requests",json={"text":"I cannot breathe and need my phone"}).json()
    assert response["route"] == "D"
    assert response["routing"]["delivered_to_staff"] is False
    assert "cannot contact" in response["message"]
    assert response["routing"]["fhir_task"]["priority"] == "stat"
    assert client.post("/api/tasks/plan",json={"goal":"Move my IV pump"}).status_code == 409


def test_information_has_synthetic_authority_and_no_wait_estimate(client):
    result = client.post("/api/requests",json={"text":"What's happening next?"}).json()
    assert result["route"] == "A"
    assert "Synthetic" in result["source"]
    assert result["information"]["live"] is False


def test_room_scan_invalidates_approval_and_simulation(client):
    task = plan(client)
    validate_and_approve(client,task["id"])
    client.post("/api/rooms/room-417/scan",json={})
    assert client.post(f"/api/tasks/{task['id']}/approve",json={}).status_code == 409
    result = client.post(f"/api/tasks/{task['id']}/execute",json={}).json()
    assert result["status"] == "blocked"


def test_estop_release_requires_new_approval(client):
    task = plan(client)
    validate_and_approve(client,task["id"])
    client.post("/api/robots/mock-bracketbot/estop",json={"engaged":True})
    assert client.post(f"/api/tasks/{task['id']}/execute",json={}).json()["status"] == "blocked"
    client.post("/api/robots/mock-bracketbot/estop",json={"engaged":False})
    assert client.post(f"/api/tasks/{task['id']}/execute",json={}).json()["status"] == "blocked"


def test_patient_cannot_cross_role_or_session_boundary(client):
    staff_task = plan(client)
    client.post("/api/session",json={"role":"patient"})
    assert client.post("/api/tasks/plan",json={"goal":"Bring phone"}).status_code == 403
    assert client.post(f"/api/tasks/{staff_task['id']}/cancel",json={}).status_code == 403
    assert client.get("/api/audit").status_code == 403
    assert client.get("/api/research").status_code == 403
    own = client.post("/api/requests",json={"text":"Bring my phone"}).json()
    assert client.post(f"/api/tasks/{own['task_id']}/cancel",json={}).json()["status"] == "cancelled"
    assert client.get("/api/bootstrap").json()["tasks"][0]["id"] == own["task_id"]


def test_auth_and_csrf_boundaries(client):
    response = client.post("/api/privacy",json={},headers={"Origin":"https://evil.example"})
    assert response.status_code == 403
    client.delete("/api/session")
    assert client.get("/api/bootstrap").status_code == 401
    assert client.get("/api/health").status_code == 200


def test_non_demo_missing_credentials_fail_closed(tmp_path):
    app = create_app(tmp_path/"secure.sqlite3",demo=False)
    with TestClient(app) as c:
        assert c.post("/api/session",json={"role":"admin","token":"anything"}).status_code == 401


def test_clinical_object_permission_cannot_be_relaxed(client):
    assert client.post("/api/rooms/room-417/objects/iv_pump/policy",json={"policy":"SAFE_GENERAL"}).status_code == 403
    assert client.post("/api/rooms/room-417/objects/iv_pump/policy",json={"policy":"TELEOP_ONLY"}).status_code == 403


def test_takeover_stops_autonomy_and_records_quarantined_correction(client):
    task = plan(client)
    client.post("/api/session",json={"role":"operator"})
    response = client.post("/api/teleop/sessions",json={"task_id":task["id"],"reason":"Low confidence","consent":True,"environment":"mock"})
    assert response.status_code == 200,response.text
    session = response.json()
    assert session["hardware_connected"] is False
    assert client.post(f"/api/tasks/{task['id']}/execute",json={}).status_code == 409
    recorded = client.post(f"/api/teleop/sessions/{session['id']}/demo-correction",json={})
    assert recorded.status_code == 200,recorded.text
    assert recorded.json()["frame_count"] == 12
    completed = client.post(f"/api/teleop/sessions/{session['id']}/complete",json={"success":True,"notes":"Synthetic correction label"}).json()
    assert completed["privacy_status"] == "quarantined"
    client.post("/api/session",json={"role":"researcher"})
    assert client.post(f"/api/teleop/sessions/{session['id']}/review",json={"approved":True}).status_code == 409
    reviewed = client.post(f"/api/teleop/sessions/{session['id']}/review",json={"approved":True,"privacy_cleared":True,"safety_cleared":True})
    assert reviewed.status_code == 200,reviewed.text


@pytest.mark.parametrize("scenario",["person_enters","uncertain_phone","attached_phone","blocked_path","unknown_object"])
def test_synthetic_adverse_scenarios_cannot_execute(client,scenario):
    client.post("/api/session",json={"role":"operator"})
    assert client.post("/api/demo/scenario",json={"scenario":scenario}).status_code == 200
    client.post("/api/session",json={"role":"staff"})
    task = plan(client)
    client.post(f"/api/tasks/{task['id']}/approve",json={})
    client.post(f"/api/tasks/{task['id']}/validate",json={})
    result = client.post(f"/api/tasks/{task['id']}/execute",json={}).json()
    assert result["status"] == "blocked"


def test_concurrent_execution_cannot_apply_twice(client):
    task = plan(client)
    validate_and_approve(client,task["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post(f"/api/tasks/{task['id']}/execute",json={}),range(2)))
    assert sorted(r.status_code for r in results) == [200,409]
    assert client.get("/api/rooms/room-417/state").json()["version"] == 2


def start_takeover(client,task):
    client.post("/api/session",json={"role":"operator"})
    response = client.post("/api/teleop/sessions",json={"task_id":task["id"],"reason":"Synthetic correction","consent":True,"environment":"mock"})
    assert response.status_code == 200,response.text
    return response.json()


def test_late_recording_completion_does_not_reopen_cancelled_task(client):
    task = plan(client)
    session = start_takeover(client,task)
    client.post(f"/api/tasks/{task['id']}/cancel",json={})
    finished = client.post(f"/api/teleop/sessions/{session['id']}/complete",json={"success":True})
    assert finished.status_code == 200,finished.text
    assert client.get(f"/api/tasks/{task['id']}").json()["status"] == "cancelled"
    client.post("/api/session",json={"role":"staff"})
    assert client.post(f"/api/tasks/{task['id']}/approve",json={}).status_code == 409


def test_takeover_is_exclusive_across_tasks(client):
    first = plan(client)
    second = plan(client)
    validate_and_approve(client,second["id"])
    session = start_takeover(client,first)
    assert client.post(f"/api/tasks/{second['id']}/execute",json={}).status_code == 409
    assert client.post("/api/teleop/sessions",json={"task_id":second["id"],"reason":"Second operator","consent":True,"environment":"mock"}).status_code == 409
    client.post(f"/api/teleop/sessions/{session['id']}/complete",json={"success":True})
    assert client.post(f"/api/tasks/{second['id']}/execute",json={}).json()["status"] == "completed"


def test_other_operator_cannot_write_or_close_recording(client):
    task = plan(client)
    session = start_takeover(client,task)
    client.post("/api/session",json={"role":"operator"})
    assert client.post(f"/api/teleop/sessions/{session['id']}/demo-correction",json={}).status_code == 403
    assert client.post(f"/api/teleop/sessions/{session['id']}/complete",json={"success":True}).status_code == 403
    assert client.get(f"/api/teleop/sessions/{session['id']}").json()["status"] == "recording"


def test_estop_stops_recording_and_invalidates_ownership(client):
    task = plan(client)
    session = start_takeover(client,task)
    client.post("/api/robots/mock-bracketbot/estop",json={"engaged":True})
    assert client.get(f"/api/teleop/sessions/{session['id']}").json()["status"] == "stopped"
    assert client.post(f"/api/teleop/sessions/{session['id']}/demo-correction",json={}).status_code == 409
    assert client.post(f"/api/tasks/{task['id']}/execute",json={}).json()["status"] == "blocked"


def test_patient_may_engage_but_never_release_stop(client):
    client.post("/api/session",json={"role":"patient"})
    assert client.post("/api/robots/mock-bracketbot/estop",json={"engaged":True}).status_code == 200
    assert client.post("/api/robots/mock-bracketbot/estop",json={"engaged":False}).status_code == 403


def test_researcher_cannot_see_requests_or_cancel_operational_tasks(client):
    task = plan(client)
    client.post("/api/requests",json={"text":"Bring my phone"})
    client.post("/api/session",json={"role":"researcher"})
    bootstrap = client.get("/api/bootstrap").json()
    assert bootstrap["requests"] == [] and bootstrap["tasks"] == []
    assert client.get(f"/api/tasks/{task['id']}").status_code == 403
    assert client.post(f"/api/tasks/{task['id']}/cancel",json={}).status_code == 403


def test_unknown_object_policy_cannot_be_changed_to_teleop(client):
    path = "/api/rooms/room-417/objects/phone/policy"
    assert client.post(path,json={"policy":"UNKNOWN_PROHIBITED"}).status_code == 200
    assert client.post(path,json={"policy":"TELEOP_ONLY"}).status_code == 403


def test_cloud_failure_preserves_request_and_only_sends_canonical_input(client,monkeypatch):
    sent = []
    class OfflineAstra:
        def plan(self,goal,room,*,data_class):
            sent.append((goal,room,data_class))
            raise RuntimeError("Synthetic network failure")
    monkeypatch.setenv("VELA_ENABLE_CLOUD_MODELS","1")
    monkeypatch.setattr("services.planner.AstraAdapter",OfflineAstra)
    result = client.post("/api/requests",json={"text":"Could you please bring my personal phone closer?"})
    assert result.status_code == 200,result.text
    assert result.json()["route"] == "B"
    assert sent[0][0] == [{"object_class":"phone","destination":"accessible_zone"}]
    assert sent[0][2] == "synthetic"
    assert "owner" not in str(sent[0])
    assert client.get("/api/bootstrap").json()["requests"]
