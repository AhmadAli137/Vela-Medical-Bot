"""Actual-export and corruption regressions for the independent sync audit."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from sim.sync_check import GLBS, ROOT, audit_native_cache, audit_sync, native_cache_signature
from sim.reference_model import build_reference_model


@pytest.fixture
def exports(tmp_path):
    for path in ["pyproject.toml", "apps/web/package.json", "sim/reference_body_descriptors.xml", "sim/reference_body_descriptors.json", "sim/reference_demo_trajectories.json",
                 "apps/web/public/simulation/reference.xml", "apps/web/public/simulation/reference-descriptors.json"]:
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    # Contract-only tests explicitly skip GLB parsing; the real-assets test
    # below separately exercises the full default kinematic/UV audit.
    for filename in GLBS:
        target = tmp_path / "assets/simulation" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"contract-test file; visual validation explicitly skipped")
    return tmp_path


def test_current_exports_and_actual_glbs_match_fresh_python_contracts():
    report = audit_sync()
    assert report["passed"], report["checks"]
    assert report["visual_kinematics_checked"]
    assert report["visual_source_regeneration_verified"] is False
    assert any(item["name"] == "shared_trajectories" and item["passed"] for item in report["checks"])


def test_consistent_hand_edited_exports_cannot_hide_a_stale_python_model(exports):
    # All cached copies and claimed hashes agree with one another. Only an
    # independent regeneration reveals the deliberately changed gravity.
    xml = (exports / "sim/reference_body_descriptors.xml").read_text().replace('gravity="0 0 -9.81"', 'gravity="0 0 -10"')
    for path in ["sim/reference_body_descriptors.xml", "apps/web/public/simulation/reference.xml"]:
        (exports / path).write_text(xml, encoding="utf-8")
    digest = hashlib.sha256(xml.encode()).hexdigest()
    for path in ["sim/reference_body_descriptors.json", "apps/web/public/simulation/reference-descriptors.json", "sim/reference_demo_trajectories.json"]:
        data = json.loads((exports / path).read_text())
        data["model_hash"] = digest
        (exports / path).write_text(json.dumps(data))
    report = audit_sync(exports, check_visuals=False)
    assert not report["passed"]
    assert any(item["name"].endswith(".xml") and not item["passed"] for item in report["checks"])


def test_pose_edit_is_detected_even_if_model_hash_was_not_changed(exports):
    path = exports / "apps/web/public/simulation/reference-descriptors.json"
    data = json.loads(path.read_text())
    data["initial_world_poses"]["head"]["position"][2] += .04
    path.write_text(json.dumps(data))
    report = audit_sync(exports, check_visuals=False)
    assert not report["passed"]
    assert any("initial_world_poses.head.position" in item.get("error", "") for item in report["checks"])


def test_changed_trajectory_target_is_detected_despite_matching_model_hash(exports):
    path = exports / "sim/reference_demo_trajectories.json"
    data = json.loads(path.read_text())
    data["commands"]["bedside_demo"]["stages"][1]["target_qpos"][0] += .10
    path.write_text(json.dumps(data))
    report = audit_sync(exports, check_visuals=False)
    check = next(item for item in report["checks"] if item["name"] == "shared_trajectories")
    assert not check["passed"]
    assert "target_qpos" in check["error"]


def test_missing_asset_is_a_structured_failure(exports):
    (exports / "assets/simulation/meal_box.glb").unlink()
    report = audit_sync(exports, check_visuals=False)
    assert not report["passed"]
    assert any(item["name"] == "asset:meal_box.glb" and not item["passed"] for item in report["checks"])


def test_invalid_json_is_a_structured_failure(exports):
    (exports / "sim/reference_body_descriptors.json").write_text("{broken")
    report = audit_sync(exports, check_visuals=False)
    assert not report["passed"]
    assert any(item["name"] == "sim/reference_body_descriptors.json" and not item["passed"] for item in report["checks"])


def test_browser_engine_upgrade_without_native_upgrade_is_rejected(exports):
    path = exports / "apps/web/package.json"
    package = json.loads(path.read_text())
    package["dependencies"]["@mujoco/mujoco"] = "99.0.0"
    path.write_text(json.dumps(package))
    report = audit_sync(exports, check_visuals=False)
    assert any(item["name"] == "engine_versions" and not item["passed"] for item in report["checks"])


@pytest.mark.parametrize("mutation", ["signature", "model.mjb", "model.xml", "mesh.msh"])
def test_stale_native_conversion_is_rejected_before_loading_or_regenerating(tmp_path, mutation):
    _, metadata = build_reference_model()
    signature = native_cache_signature(ROOT, metadata["model_hash"])
    key = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    cache = tmp_path / key
    cache.mkdir()
    contents = {"model.mjb": b"unchanged binary fixture", "model.xml": b"unchanged XML fixture", "mesh.msh": b"unchanged mesh fixture"}
    for filename, data in contents.items():
        (cache / filename).write_bytes(data)
    digest = lambda name: hashlib.sha256(contents[name]).hexdigest()
    receipt = {"signature": signature, "model_binary_sha256": digest("model.mjb"), "model_xml_sha256": digest("model.xml"),
               "generated_assets": {"mesh.msh": digest("mesh.msh")}}
    if mutation == "signature":
        receipt["signature"]["source_glbs"]["robot.glb"] = "0" * 64
    else:
        (cache / mutation).write_bytes(b"stale replacement")
    (cache / "conversion.json").write_text(json.dumps(receipt))
    before = {path.name: path.read_bytes() for path in cache.iterdir()}
    with pytest.raises(ValueError, match="does not match|hash mismatch"):
        audit_native_cache(ROOT, tmp_path)
    assert before == {path.name: path.read_bytes() for path in cache.iterdir()}, "Audit must not repair or regenerate a stale cache"
