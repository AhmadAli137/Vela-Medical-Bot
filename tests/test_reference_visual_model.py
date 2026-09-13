"""Regression checks for physics isolation and formerly incorrect GLB materials."""
import io
import json
import struct
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image
import pytest

from sim.reference_model import load_reference_model
from sim.reference_visual_model import _assert_physics_parity, _convert_glb, load_reference_visual_model
from sim.reference_visual_check import check_static


@pytest.fixture(scope="module")
def detailed():
    return load_reference_visual_model()


def test_shipped_visuals_preserve_physics_and_initial_camera_body_poses(detailed):
    model, data, metadata = detailed
    result = check_static(model, data, metadata)
    assert result["passed"], result
    assert model.nmesh > 100
    assert metadata["visual_model"] is True
    assert metadata["visual_hash"] != metadata["model_hash"]


def test_actual_actuator_motion_is_unchanged_by_visual_geometry(detailed):
    original, original_data, _ = load_reference_model()
    visual, initial_data, _ = detailed
    data = mujoco.MjData(visual)
    for field in ("qpos", "qvel", "ctrl", "mocap_pos", "mocap_quat"):
        getattr(data, field)[:] = getattr(initial_data, field)
    initial = original_data.qpos.copy()
    for model, state in ((original, original_data), (visual, data)):
        index = model.actuator("ctrl_left_joint_2").id
        state.ctrl[index] += .08
        mujoco.mj_forward(model, state)
    for _ in range(250):
        mujoco.mj_step(original, original_data)
        mujoco.mj_step(visual, data)
    assert np.max(np.abs(original_data.qpos-initial)) > .01
    np.testing.assert_allclose(data.qpos, original_data.qpos, atol=1e-12, rtol=0)
    np.testing.assert_allclose(data.qvel, original_data.qvel, atol=1e-12, rtol=0)


@pytest.mark.parametrize("field", ["body_mass", "geom_friction", "cam_fovy"])
def test_parity_guard_rejects_changed_inertia_contact_or_camera(detailed, field):
    original, _, _ = load_reference_model()
    model = detailed[0]
    array = getattr(model, field)
    saved = array.copy()
    try:
        array[1] *= 1.1
        with pytest.raises(RuntimeError, match="changed"):
            _assert_physics_parity(original, model)
    finally:
        array[:] = saved


def test_dynamics_checker_requires_measured_demo_completion(tmp_path, monkeypatch):
    from sim import reference_visual_check

    # Actual physics with a deliberately truncated greeting must fail the
    # outcome check even when numerical parity is exact throughout the run.
    monkeypatch.setattr(reference_visual_check, "DYNAMICS", {"greeting_demo": .5})
    report = reference_visual_check.check_dynamics(tmp_path)
    result = report["comparisons"]["greeting_demo"]
    assert result["physics_steps"] == 250
    assert result["max_qpos_error"] <= 1e-12
    assert result["max_qvel_error"] <= 1e-12
    assert not result["reference_complete"]
    assert not result["detailed_complete"]
    assert not report["passed"]
    assert json.loads((tmp_path/"native-detailed-dynamics-parity.json").read_text())["passed"] is False


@pytest.fixture
def textured_fixture(tmp_path):
    """Four differently colored image corners reveal a vertical UV inversion."""
    vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype="<f4")
    uv = np.array([[.10, .15], [.75, .20], [.20, .80], [.85, .90]], dtype="<f4")
    faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]], dtype="<u2")
    pixels = np.array([[[250, 30, 50, 255], [10, 240, 40, 255]], [[20, 40, 230, 255], [210, 220, 30, 255]]], dtype=np.uint8)
    stream = io.BytesIO()
    Image.fromarray(pixels).save(stream, format="PNG")
    parts = [vertices.tobytes(), uv.tobytes(), faces.tobytes(), stream.getvalue()]
    binary = bytearray()
    views = []
    for part in parts:
        binary.extend(b"\0"*((-len(binary)) % 4))
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(part)})
        binary.extend(part)
    binary.extend(b"\0"*((-len(binary)) % 4))
    document = {
        "asset": {"version": "2.0"}, "buffers": [{"byteLength": len(binary)}], "bufferViews": views,
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
                      {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC2"},
                      {"bufferView": 2, "componentType": 5123, "count": 12, "type": "SCALAR"}],
        "images": [{"bufferView": 3, "mimeType": "image/png"}], "textures": [{"source": 0}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [.2, .4, .6, 1.], "baseColorTexture": {"index": 0}}}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
        "nodes": [{"name": "test_body", "translation": [4, 5, 6], "children": [1]}, {"name": "surface", "mesh": 0}],
        "scenes": [{"nodes": [0]}], "scene": 0,
    }
    payload = json.dumps(document).encode()
    payload += b" "*((-len(payload)) % 4)
    glb = struct.pack("<III", 0x46546C67, 2, 12+8+len(payload)+8+len(binary))
    glb += struct.pack("<II", len(payload), 0x4E4F534A)+payload+struct.pack("<II", len(binary), 0x004E4942)+binary
    path = tmp_path/"fixture.glb"
    path.write_bytes(glb)
    root = ET.fromstring('<mujoco><compiler/><asset/><worldbody><body name="test_body" pos=".3 .2 .1"/></worldbody></mujoco>')
    body = root.find("worldbody/body")
    _convert_glb(path, root, tmp_path, {"test_body": body})
    xml = tmp_path/"fixture.xml"
    xml.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    return tmp_path, root, mujoco.MjModel.from_xml_path(str(xml)), uv, vertices, pixels


def test_compiled_material_factor_is_not_overridden_by_white_geom_rgba(textured_fixture):
    _, root, model, _, _, _ = textured_fixture
    geom = root.find("worldbody/body/geom")
    assert geom.get("rgba") is None
    np.testing.assert_allclose(model.geom_rgba[0], [.5, .5, .5, 1.])
    np.testing.assert_allclose(model.mat_rgba[model.geom_matid[0]], [.2, .4, .6, 1.])
    assert model.geom_contype[0] == model.geom_conaffinity[0] == 0


def test_authored_uv_image_rows_and_body_local_vertices_survive_conversion(textured_fixture):
    directory, root, model, uv, vertices, pixels = textured_fixture
    msh = directory/root.find("asset/mesh").get("file")
    content = msh.read_bytes()
    nv, nn, nt, nf = struct.unpack("<4i", content[:16])
    assert (nv, nt, nf) == (4, 4, 4)
    exported_vertices = np.frombuffer(content, dtype="<f4", count=nv*3, offset=16).reshape(-1, 3)
    exported_uv = np.frombuffer(content, dtype="<f4", count=nt*2, offset=16+(nv+nn)*12).reshape(-1, 2)
    np.testing.assert_array_equal(exported_vertices, vertices)
    np.testing.assert_array_equal(exported_uv, uv)
    np.testing.assert_array_equal(model.mesh_texcoord[:4], uv)
    texture = directory/root.find("asset/texture").get("file")
    np.testing.assert_array_equal(np.asarray(Image.open(texture)), pixels)
