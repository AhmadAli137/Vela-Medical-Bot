"""Current native controller/CLI and a coherent loopback attachment contract."""
import copy
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from types import SimpleNamespace
from urllib.error import HTTPError

import mujoco
import numpy as np
import pytest

from sim.reference_model import load_reference_model
from sim.reference_runtime import ReferenceSimulation
from sim.reference_viewer_client import ReferenceViewerClient, apply_reference_frame, validate_connection_url
from sim.viewer_live import DEMO_KEYS, SENSOR_CAMERAS, ViewerInput, configure_view, initialize_view, run_viewer, viewer_text


def frame_of(sim):
    with sim.lock:
        return {"state": sim.advance(0), **{name: getattr(sim.data, name).tolist() for name in ("qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat")}}


def test_runtime_loader_injection_preserves_default_physics_and_controls():
    supplied = load_reference_model()
    injected = ReferenceSimulation(loader=lambda: supplied)
    default = ReferenceSimulation()
    assert injected.model is supplied[0] and injected.data is supplied[1]
    assert injected.metadata["model_hash"] == default.metadata["model_hash"]
    for runtime in (injected, default):
        runtime.command("joint_demo")
        runtime.advance(.3)
    np.testing.assert_array_equal(injected.data.qpos, default.data.qpos)
    np.testing.assert_array_equal(injected.data.ctrl, default.data.ctrl)
    assert injected.advance(0)["cameras"].keys() == default.advance(0)["cameras"].keys()


def test_viewer_inputs_queue_reset_and_shared_commands_without_alternate_controllers():
    controls = ViewerInput()
    calls = []
    for key, (command, _) in DEMO_KEYS.items():
        controls.key_callback(ord(key))
        assert not calls
        controls.process(calls.append)
        assert calls == ["reset", command]
        calls.clear()
    assert {command for command, _ in DEMO_KEYS.values()} == {"joint_demo", "reach_demo", "pickup_demo", "lift_demo", "bedside_demo", "greeting_demo", "phone_return_demo", "deliver_phone_demo", "deliver_meal_demo", "blinds_demo"}
    for key in " RF":
        controls.key_callback(ord(key))
    controls.process(calls.append)
    assert calls == ["pause", "reset", "release_phone"]


def test_viewer_surfaces_runtime_rejection_and_never_starts_after_failed_reset():
    controls = ViewerInput()
    calls = []
    def reject(command):
        calls.append(command)
        raise ValueError("Backend is unavailable")
    controls.key_callback(ord("8"))
    controls.process(reject)
    assert calls == ["reset"] and "Backend is unavailable" in controls.message


def test_native_camera_cycle_enclosure_and_collision_display_groups():
    model, _, _ = load_reference_model()
    controls = ViewerInput()
    viewer = SimpleNamespace(cam=mujoco.MjvCamera(), opt=mujoco.MjvOption())
    for expected in (*SENSOR_CAMERAS, None):
        controls.key_callback(ord("C"))
        controls.process(lambda _: pytest.fail("Camera selection must not change physics"))
        configure_view(viewer, model, controls)
        assert bool(viewer.opt.geomgroup[4]) == (expected is not None)
        assert viewer.cam.fixedcamid == (model.camera(expected).id if expected else -1)
    controls.key_callback(ord("V")); controls.process(lambda _: None)
    configure_view(viewer, model, controls)
    assert viewer.opt.geomgroup[3] and not viewer.opt.geomgroup[2]
    assert not viewer.opt.sitegroup.any()


def test_initial_camera_matches_authored_overview_after_native_first_sync():
    model, data, _ = load_reference_model()
    controls = ViewerInput()
    calls = []
    viewer = SimpleNamespace(cam=mujoco.MjvCamera(), opt=mujoco.MjvOption(), lock=lambda: nullcontext())
    def sync():
        if not calls:
            viewer.cam.lookat[:] = [1.4, 1.8, 1.2]
            viewer.cam.distance = .6
        calls.append(True)
    viewer.sync = sync
    initialize_view(viewer, model, data, controls)
    scene = mujoco.MjvScene(model, 1000)
    mujoco.mjv_updateScene(model, data, viewer.opt, None, viewer.cam, mujoco.mjtCatBit.mjCAT_ALL, scene)
    orbit_position = scene.camera[0].pos.copy()
    orbit_direction = scene.camera[0].forward.copy()
    viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    viewer.cam.fixedcamid = model.camera("overview").id
    mujoco.mjv_updateScene(model, data, viewer.opt, None, viewer.cam, mujoco.mjtCatBit.mjCAT_ALL, scene)
    np.testing.assert_allclose(orbit_position, scene.camera[0].pos, atol=1e-6)
    np.testing.assert_allclose(orbit_direction, scene.camera[0].forward, atol=1e-6)
    assert len(calls) == 2
    state = ReferenceSimulation().advance(0)
    assert len(viewer_text(state, controls, True).splitlines()) == 4
    controls.key_callback(ord("H")); controls.process(lambda _: None)
    assert "RESET + RUN" in viewer_text(state, controls, True)
    controls.display_error = "Frame rejected: model hash mismatch"
    assert "DISPLAY FROZEN" in viewer_text(state, controls, True)
    assert controls.display_error in viewer_text(state, controls, True)


def test_attached_frame_has_one_authoritative_clock_and_actual_camera_poses(monkeypatch):
    source = ReferenceSimulation()
    source.command("joint_demo"); source.advance(.4)
    model, data, metadata = load_reference_model()
    frame = frame_of(source)
    monkeypatch.setattr(mujoco, "mj_step", lambda *_: pytest.fail("Attached viewer must never integrate physics"))
    for _ in range(3):
        state = apply_reference_frame(model, data, metadata, frame)
        assert data.time == frame["state"]["simulation_time"]
        np.testing.assert_array_equal(data.qpos, source.data.qpos)
        np.testing.assert_array_equal(data.ctrl, source.data.ctrl)
        np.testing.assert_allclose(data.cam_xpos, source.data.cam_xpos, atol=1e-12)
        for spec in metadata["body_specs"]:
            body = model.body(spec["name"]).id
            source_body = source.model.body(spec["name"]).id
            np.testing.assert_allclose(data.xpos[body], source.data.xpos[source_body], atol=1e-12)
            np.testing.assert_allclose(data.xquat[body], source.data.xquat[source_body], atol=1e-12)
        assert state == frame["state"]
    state["mode"] = "changed"
    assert frame["state"]["mode"] == "joint_demo"


@pytest.mark.parametrize("corruption", ["hash", "qpos_length", "nonfinite_velocity", "ctrl_length", "mocap_shape", "quaternion", "clock"])
def test_malformed_frames_are_rejected_before_any_state_mutation(corruption):
    source = ReferenceSimulation(); frame = frame_of(source)
    model, data, metadata = load_reference_model()
    original = {name: getattr(data, name).copy() for name in ("qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat")}
    if corruption == "hash": frame["state"]["model_hash"] = "old model"
    elif corruption == "qpos_length": frame["qpos"].pop()
    elif corruption == "nonfinite_velocity": frame["qvel"][0] = float("nan")
    elif corruption == "ctrl_length": frame["ctrl"].append(0.)
    elif corruption == "mocap_shape": frame["mocap_pos"] = [0, 0, 0]
    elif corruption == "quaternion": frame["mocap_quat"] = [[0, 0, 0, 0]]
    else: frame["state"]["simulation_time"] = float("inf")
    with pytest.raises(ValueError): apply_reference_frame(model, data, metadata, frame)
    assert data.time == 0
    for name, value in original.items(): np.testing.assert_array_equal(getattr(data, name), value)


def test_viewer_connection_rejects_nonloopback_credentials_redirects_and_paths():
    for valid in ("http://127.0.0.1:8000", "http://[::1]:8123/"):
        assert validate_connection_url(valid) == valid.rstrip("/")
    for invalid in ("https://127.0.0.1", "http://example.com", "http://192.168.1.8", "http://127.0.0.1@evil.test", "http://user:password@127.0.0.1", "file:///tmp/model", "http://127.0.0.1/api", "http://127.0.0.1?url=evil", "http://127.0.0.1#part", "http://127.0.0.1:99999"):
        with pytest.raises(ValueError): validate_connection_url(invalid)


def test_loopback_client_cookie_auth_controls_and_redirect_refusal():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        redirect = False
        def log_message(self, *_): pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, payload, self.headers.get("Cookie")))
            if self.path == "/api/session" and self.redirect:
                self.send_response(302); self.send_header("Location", "/must-not-follow"); self.end_headers(); return
            self.send_response(200); self.send_header("Content-Type", "application/json")
            if self.path == "/api/session": self.send_header("Set-Cookie", "viewer_session=test; HttpOnly; Path=/")
            self.end_headers(); self.wfile.write(b'{"mode":"idle"}')
        def do_GET(self):
            calls.append((self.path, None, self.headers.get("Cookie")))
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"state":{"mode":"idle"}}')
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        client = ReferenceViewerClient(url)
        assert client.frame()["state"]["mode"] == "idle"
        client.command("pause_for_tracking")
        assert calls[0][:2] == ("/api/session", {"role": "staff"})
        assert calls[1][2] == calls[2][2] == "viewer_session=test"
        assert calls[2][1] == {"command": "pause_for_tracking"}
        Handler.redirect = True
        with pytest.raises(HTTPError, match="do not follow redirects"): ReferenceViewerClient(url)
        assert all(path != "/must-not-follow" for path, _, _ in calls)
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


def test_attached_viewer_loop_never_calls_local_runtime_advance(monkeypatch, tmp_path):
    import sim.viewer_live as module
    source = ReferenceSimulation(); source.command("joint_demo"); source.advance(.2)
    frame = frame_of(source)
    captured = {}
    class Client:
        def __init__(self, url): assert url == "http://127.0.0.1:8000"
        def frame(self): return copy.deepcopy(frame)
        def command(self, command): captured.setdefault("commands", []).append(command)
    class Viewer:
        def __init__(self, model, data, **options):
            self.cam = mujoco.MjvCamera(); self.opt = mujoco.MjvOption(); self.frames = 0
            self.callback = options["key_callback"]; captured["data"] = data
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def lock(self): return nullcontext()
        def is_running(self):
            self.frames += 1
            if self.frames == 1: self.callback(ord("8"))
            return self.frames <= 2
        def set_texts(self, value): captured["hud"] = value[2]
        def sync(self): pass
    monkeypatch.setattr(module, "ReferenceViewerClient", Client)
    monkeypatch.setattr(module.mujoco.viewer, "launch_passive", Viewer)
    monkeypatch.setattr(module.time, "sleep", lambda *_: None)
    monkeypatch.setattr(ReferenceSimulation, "advance", lambda *_: pytest.fail("Attached mode cannot run a local clock"))
    ready = tmp_path / "ready.json"
    result = run_viewer(ready_path=ready, connect="http://127.0.0.1:8000", loader=load_reference_model)
    assert result["session"] == "attached"
    assert json.loads(ready.read_text())["session"] == "attached"
    assert captured["commands"] == ["reset", "deliver_phone_demo"]
    assert captured["data"].time == source.data.time
    assert "SHARED browser session" in captured["hud"]


def test_current_export_contains_loadable_model_and_explicit_initial_state(tmp_path):
    from sim.reference_cli import generate_reference_scene
    result = generate_reference_scene(tmp_path, loader=load_reference_model)
    restored = mujoco.MjModel.from_binary_path(result["model_binary"])
    assert restored.nu == 22 and restored.nq == 57
    assert len(result["initial_qpos"]) == restored.nq
    assert result["model_family"] == "current_reference" and result["seeded"] is False


def test_cli_defaults_current_reference_and_keeps_legacy_benchmark_explicit(monkeypatch, tmp_path):
    from sim.__main__ import main
    import sim.reference_cli as current
    import sim.engine as legacy
    import sim.model as legacy_model
    import sim.viewer_live as viewer
    calls = []
    monkeypatch.setattr(current, "generate_reference_scene", lambda path: calls.append(("current_generate", path)) or {"current": True})
    monkeypatch.setattr(current, "render_reference_scene", lambda path, camera: calls.append(("current_render", camera)) or {"current": True})
    monkeypatch.setattr(legacy_model, "write_scene", lambda path, seed: calls.append(("legacy_generate", seed)) or {"legacy": True})
    monkeypatch.setattr(legacy, "render_scene", lambda path, seed, camera: calls.append(("legacy_render", seed, camera)) or {"legacy": True})
    monkeypatch.setattr(legacy, "run_benchmark", lambda episodes, seed: calls.append(("benchmark", episodes, seed)) or {"unchanged": True})
    monkeypatch.setattr(viewer, "run_viewer", lambda seed, ready, connect: calls.append(("viewer", connect)) or {"current": True})
    def run(*args): return main([*args, "--output", str(tmp_path)])
    assert run("generate")["current"]
    assert run("render", "--camera", "head_rgb")["current"]
    assert run("generate", "--legacy", "--seed", "19")["legacy"]
    assert run("render", "--legacy", "--seed", "19")["legacy"]
    assert run("benchmark", "--episodes", "2", "--seed", "19") == {"unchanged": True}
    assert json.loads((tmp_path / "evaluation.json").read_text()) == {"unchanged": True}
    assert run("viewer", "--connect", "http://127.0.0.1:8000")["current"]
    assert [call[0] for call in calls] == ["current_generate", "current_render", "legacy_generate", "legacy_render", "benchmark", "viewer"]
    assert calls[4] == ("benchmark", 2, 19)
