"""Read-only synchronization audit; regenerates expected contracts in memory.

Run ``python -m sim.sync_check --output artifacts/scene-sync.json``.
The checked-out Python model is authoritative. No XML, trajectories, GLBs or
native visual caches are regenerated on disk by this checker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tomllib

import mujoco
import numpy as np

from sim.reference_model import build_reference_model, load_reference_model
from sim.reference_demos import build_trajectories
from sim.reference_glb_check import check_glb

ROOT = Path(__file__).resolve().parents[1]
GLBS = ("room.glb", "robot.glb", "phone.glb", "meal_box.glb")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def differences(actual, expected, path="", limit=12) -> list[str]:
    """Report semantic drift, allowing only negligible floating-point noise."""
    result = []
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and not isinstance(actual, bool) and not isinstance(expected, bool):
        return [] if math.isfinite(actual) and math.isfinite(expected) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9) else [path]
    if type(actual) is not type(expected):
        return [path]
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            result.append((path or "root") + ".keys")
        for key in sorted(expected.keys() & actual.keys()):
            result.extend(differences(actual[key], expected[key], f"{path}.{key}" if path else key, limit))
            if len(result) >= limit:
                break
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            result.append((path or "root") + ".length")
        for index, (a, b) in enumerate(zip(actual, expected)):
            result.extend(differences(a, b, f"{path}[{index}]", limit))
            if len(result) >= limit:
                break
    elif actual != expected:
        result.append(path)
    return result[:limit]


def expected_contracts():
    xml, _ = build_reference_model()
    model, data, metadata = load_reference_model()
    metadata["initial_world_poses"] = {
        spec["name"]: {
            "position": data.xpos[model.body(spec["name"]).id].tolist(),
            "quaternion": data.xquat[model.body(spec["name"]).id].tolist(),
        } for spec in metadata["body_specs"]
    }
    return xml.encode("utf-8"), json.loads(json.dumps(metadata)), build_trajectories()


def native_cache_signature(root, model_hash):
    root = Path(root)
    return {"physics_model_hash": model_hash,
            "source_glbs": {name: sha256(root / "assets/simulation" / name) for name in GLBS},
            "converter_sha256": sha256(root / "sim/reference_visual_model.py"),
            "mujoco_version": mujoco.__version__}


def audit_native_cache(root, cache_root=None):
    """Validate an existing conversion; never silently repair a stale cache."""
    root = Path(root).resolve()
    reference, initial, metadata = load_reference_model()
    signature = native_cache_signature(root, metadata["model_hash"])
    visual_hash = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    base = Path(cache_root) if cache_root is not None else root / ".cache/reference-visual"
    if not base.is_absolute():
        base = root / base
    cache = base / visual_hash
    receipt = json.loads((cache / "conversion.json").read_text(encoding="utf-8"))
    if receipt.get("signature") != signature:
        raise ValueError("Native conversion receipt does not match current GLBs, converter, physics and MuJoCo")
    for filename, field in [("model.mjb", "model_binary_sha256"), ("model.xml", "model_xml_sha256")]:
        if receipt.get(field) != sha256(cache / filename):
            raise ValueError(f"Native cache output hash mismatch: {filename}")
    generated = receipt.get("generated_assets")
    if not isinstance(generated, dict) or not generated:
        raise ValueError("Native conversion receipt has no generated asset hashes")
    for filename, expected_hash in generated.items():
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError("Native conversion receipt contains an invalid asset path")
        if sha256(cache / filename) != expected_hash:
            raise ValueError(f"Native generated asset hash mismatch: {filename}")
    model = mujoco.MjModel.from_binary_path(str(cache / "model.mjb"))
    for field in ("nq", "nv", "nu", "nbody", "njnt", "ncam", "nsite", "neq", "nmocap"):
        if getattr(model, field) != getattr(reference, field):
            raise ValueError(f"Native visual model changed physics topology: {field}")
    for field in ("body_parentid", "body_mass", "body_inertia", "body_ipos", "body_iquat", "body_gravcomp",
                  "jnt_type", "jnt_axis", "jnt_range", "actuator_trnid", "actuator_ctrlrange", "actuator_forcerange",
                  "actuator_gainprm", "actuator_biasprm", "eq_type", "eq_data", "cam_bodyid", "cam_pos", "cam_quat", "cam_fovy"):
        if not np.allclose(getattr(model, field), getattr(reference, field), atol=1e-12, rtol=1e-12):
            raise ValueError(f"Native visual model changed physics/camera field: {field}")
    for index in range(reference.ngeom):
        name = reference.geom(index).name
        converted = model.geom(name).id
        for field in ("bodyid", "type", "size", "pos", "quat", "contype", "conaffinity", "condim", "friction", "solref", "solimp"):
            if not np.allclose(getattr(model, "geom_" + field)[converted], getattr(reference, "geom_" + field)[index], atol=1e-12, rtol=1e-12):
                raise ValueError(f"Native visual model changed collision proxy {name}.{field}")
    visual_geoms = (model.geom_group == 2) | (model.geom_group == 4)
    if model.nmesh < 1 or not visual_geoms.any() or np.any(model.geom_contype[visual_geoms]) or np.any(model.geom_conaffinity[visual_geoms]):
        raise ValueError("Native detailed geometry is absent or has unintended collision flags")
    data = mujoco.MjData(model)
    data.qpos[:] = initial.qpos
    data.ctrl[:] = initial.ctrl
    data.mocap_pos[:] = initial.mocap_pos
    data.mocap_quat[:] = initial.mocap_quat
    mujoco.mj_forward(model, data)
    for spec in metadata["body_specs"]:
        a, b = reference.body(spec["name"]).id, model.body(spec["name"]).id
        if not np.allclose(initial.xpos[a], data.xpos[b], atol=1e-12, rtol=0) or not np.allclose(initial.xquat[a], data.xquat[b], atol=1e-12, rtol=0):
            raise ValueError(f"Native detailed initial body pose differs: {spec['name']}")
    return {"visual_hash": visual_hash, "physics_model_hash": metadata["model_hash"], "cache_directory": str(cache),
            "source_glbs": signature["source_glbs"], "initial_body_pose_count": len(metadata["body_specs"]),
            "visual_meshes": model.nmesh, "visual_source_regeneration_verified": False}


def audit_sync(root=ROOT, *, check_visuals=True, build_mode=None, native_cache=None):
    root = Path(root).resolve()
    checks, inputs = [], {}
    try:
        xml, descriptors, trajectories = expected_contracts()
    except Exception as error:
        return {"schema_version": 1, "passed": False, "checks": [{"name": "source_regeneration", "passed": False, "error": str(error)}],
                "visual_source_regeneration_verified": False, "visual_kinematics_checked": False}

    def check(name, operation):
        try:
            detail = operation()
            checks.append({"name": name, "passed": True, **(detail or {})})
        except (OSError, ValueError, KeyError, TypeError, AssertionError, RuntimeError, subprocess.SubprocessError) as error:
            checks.append({"name": name, "passed": False, "error": str(error)})

    def read(path):
        data = (root / path).read_bytes()
        inputs[path] = hashlib.sha256(data).hexdigest()
        return data

    def match_xml(path):
        actual = read(path)
        if actual != xml:
            raise ValueError(f"{path} differs from freshly generated Python model XML")
        return {"sha256": hashlib.sha256(actual).hexdigest()}

    def match_json(path, expected):
        actual = json.loads(read(path))
        changed = differences(actual, expected)
        if changed:
            raise ValueError(f"{path} differs from regenerated contract at: {', '.join(changed)}")
        return {"sha256": inputs[path]}

    def engine_versions():
        package = json.loads(read("apps/web/package.json"))
        browser = package["dependencies"]["@mujoco/mujoco"]
        project = tomllib.loads(read("pyproject.toml").decode("utf-8"))
        if browser != mujoco.__version__:
            raise ValueError(f"Native MuJoCo {mujoco.__version__} differs from exact browser dependency {browser}")
        if f"mujoco=={browser}" not in project["project"]["dependencies"]:
            raise ValueError("Python MuJoCo dependency must be pinned to the exact browser engine version")
        return {"native_installed": mujoco.__version__, "browser_pinned": browser}

    check("engine_versions", engine_versions)

    for path in ("sim/reference_body_descriptors.xml", "apps/web/public/simulation/reference.xml"):
        check(path, lambda path=path: match_xml(path))
    for path in ("sim/reference_body_descriptors.json", "apps/web/public/simulation/reference-descriptors.json"):
        check(path, lambda path=path: match_json(path, descriptors))
    check("shared_trajectories", lambda: match_json("sim/reference_demo_trajectories.json", trajectories))

    def visual_contract():
        report = check_glb(root / "assets/simulation/robot.glb")
        if not report["matched"]:
            raise ValueError("; ".join(report["failures"]))
        if report["model_hash"] != descriptors["model_hash"]:
            raise ValueError("GLB audit used a different physics model")
        return {"body_count": report["body_count"], "expected_body_count": report["expected_body_count"],
                "textured_room_primitives": report["room"]["textured_primitive_count"]}

    for filename in GLBS:
        check(f"asset:{filename}", lambda filename=filename: {"sha256": hashlib.sha256(read(f"assets/simulation/{filename}")).hexdigest()})
    if check_visuals:
        check("visual_body_poses_and_room_uv", visual_contract)

    native_visuals = None
    if native_cache is not None:
        def verify_native_cache():
            nonlocal native_visuals
            native_visuals = audit_native_cache(root, native_cache)
            return native_visuals
        check("native_visual_cache", verify_native_cache)

    # Hash sources for reproducibility, but do not invent an absent Blender
    # build receipt linking these scripts to previously generated geometry.
    source_paths = ["sim/reference_model.py", "sim/reference_demos.py", "sim/reference_assistance.py", "sim/reference_pickup.py",
                    "sim/reference_drive.py", "sim/reference_runtime.py",
                    "scripts/build_reference_visuals.py", "scripts/build_patient_visual.py", "scripts/audit_room_visuals.py",
                    "assets/simulation/room-geometry-manifest.json", "assets/patient/patient-build-manifest.json"]
    for path in source_paths:
        if (root / path).exists():
            inputs[path] = sha256(root / path)

    web_build = None
    if build_mode is not None:
        def verify_web():
            nonlocal web_build
            process = subprocess.run(["node", str(root / "apps/web/scripts/check-scene-sync.mjs"), "--check-build", build_mode],
                                     cwd=root, text=True, capture_output=True, timeout=30, check=False)
            try:
                web_build = json.loads(process.stdout)
            except json.JSONDecodeError as error:
                raise ValueError("Node build guard returned no machine-readable report") from error
            if process.returncode or not web_build.get("passed"):
                failures = [item.get("error", item["name"]) for item in web_build.get("checks", []) if not item["passed"]]
                raise ValueError("; ".join(failures) or web_build.get("error", "Frontend build guard failed"))
            return {"mode": build_mode, "scene_revision": web_build["scene_revision"]}
        check("frontend_build", verify_web)

    return {
        "schema_version": 1, "passed": all(item["passed"] for item in checks),
        "model_hash": descriptors["model_hash"], "authoritative_python_root": str(ROOT),
        "checked_export_root": str(root), "checks": checks, "input_hashes": inputs,
        "visual_source_regeneration_verified": False, "visual_kinematics_checked": check_visuals,
        "frontend_build": web_build, "native_visual_cache": native_visuals,
        "limitations": [
            "Existing GLBs have no source-script build receipt; current script hashes do not prove those scripts generated the shipped geometry.",
            "Visual body bindings and finite UVs do not prove furniture-source regeneration, collision fidelity, grasp success or hardware correctness.",
            "This audit compares artifacts and contracts, not shared live state across independent browser/native processes.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-visuals", action="store_true", help="Skip full GLB pose and textured UV validation")
    parser.add_argument("--build-mode", choices=["local", "public"], help="Also verify the built frontend receipt and mode")
    parser.add_argument("--native-cache", nargs="?", const=".cache/reference-visual", help="Validate an already-generated native visual cache without regenerating it")
    args = parser.parse_args()
    report = audit_sync(check_visuals=not args.no_visuals, build_mode=args.build_mode, native_cache=args.native_cache)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, allow_nan=False))
    raise SystemExit(0 if report["passed"] else 1)
