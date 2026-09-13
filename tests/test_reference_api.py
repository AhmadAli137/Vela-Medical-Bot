"""Transport, authority, and state integrity for the separate reference simulator."""
from importlib import import_module

from fastapi.testclient import TestClient


def client_for(tmp_path, role="researcher", demo=True):
    app_module = import_module("services.app")
    client = TestClient(app_module.create_app(tmp_path/"api.sqlite3",demo=demo))
    if role:
        client.post("/api/session",json={"role":role})
    return client


def test_reference_requires_session_and_excludes_patient(tmp_path):
    client = client_for(tmp_path,role=None)
    assert client.get("/api/sim/reference/state").status_code == 401
    client.post("/api/session",json={"role":"patient"})
    assert client.get("/api/sim/reference/state").status_code == 403
    assert client.get("/api/sim/assets/robot.glb").status_code == 403
    assert client.post("/api/sim/reference/control",json={"command":"reset"}).status_code == 403


def test_reference_state_and_pause_use_actual_mujoco(tmp_path):
    client = client_for(tmp_path)
    initial = client.get("/api/sim/reference/state").json()
    assert initial["hardware_model_verified"] is False
    assert "robot_base" in initial["bodies"]
    assert len(initial["bodies"]) >= 20
    assert "phone" in initial["bodies"]
    assert "phone_free" not in initial["joints"]
    paused = client.post("/api/sim/reference/control",json={"command":"pause"}).json()
    assert paused["paused"] is True
    later = client.get("/api/sim/reference/state").json()
    assert later["simulation_time"] == paused["simulation_time"]
    reset = client.post("/api/sim/reference/control",json={"command":"reset"}).json()
    assert reset["mode"] == "idle"
    assert reset["authorizes_hardware"] is False


def test_reference_control_rejects_arbitrary_commands_and_fields(tmp_path):
    client = client_for(tmp_path)
    assert client.post("/api/sim/reference/control",json={"command":"drive_hardware"}).status_code == 422
    assert client.post("/api/sim/reference/control",json={"command":"reset","target":"hardware"}).status_code == 422


def test_reference_assets_are_exact_allowlist_with_binary_response(tmp_path,monkeypatch):
    app_module = import_module("services.app")
    client = client_for(tmp_path)
    monkeypatch.setattr(app_module,"ROOT",tmp_path)
    directory = tmp_path/"assets"/"simulation"
    directory.mkdir(parents=True)
    sentinel = b"endpoint transport test, not a model"
    for asset in ("room.glb", "phone.glb"):
        (directory/asset).write_bytes(sentinel)
        result = client.get(f"/api/sim/assets/{asset}?v=current-scene")
        assert result.status_code == 200
        assert result.headers["content-type"] == "model/gltf-binary"
        assert result.content == sentinel
    assert client.get("/api/sim/assets/secrets.json").status_code == 404
    assert client.get("/api/sim/assets/robot.glb").status_code == 404
    assert "connect-src 'self' blob:" in result.headers["content-security-policy"]
    assert "'unsafe-eval'" not in result.headers["content-security-policy"]


def test_reference_fixture_commands_report_actual_plan_and_reject_early_release(tmp_path):
    client = client_for(tmp_path)
    premature = client.post("/api/sim/reference/control", json={"command": "release_phone"})
    assert premature.status_code == 409
    for command in ("lift_demo", "pickup_demo"):
        client.post("/api/sim/reference/control", json={"command": "reset"})
        result = client.post("/api/sim/reference/control", json={"command": command})
        assert result.status_code == 200, result.text
        state = result.json()
        assert state["mode"] == command
        assert state["metrics"]["object_attached"] is False
        assert state["authorizes_hardware"] is False
    assert state["metrics"]["pickup"]["sampled_collision_gate_passed"] is True
    assert state["metrics"]["grasp_success"] is False


def test_reference_local_demo_boundary_applies_with_valid_production_role(tmp_path,monkeypatch):
    monkeypatch.setenv("VELA_RESEARCHER_TOKEN","test-token")
    app_module = import_module("services.app")
    client = TestClient(app_module.create_app(tmp_path/"locked.sqlite3",demo=False),base_url="https://testserver")
    assert client.post("/api/session",json={"role":"researcher","token":"test-token"}).status_code == 200
    assert client.get("/api/sim/reference/state").status_code == 403
    assert client.get("/api/sim/assets/robot.glb").status_code == 403
    assert client.post("/api/sim/reference/control",json={"command":"joint_demo"}).status_code == 403
