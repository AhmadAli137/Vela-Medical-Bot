"""Detailed native MuJoCo visuals from the exact shipped browser GLBs.

Only rendering assets are added. Original inertias, collision shapes, joints,
actuators and reference cameras remain authoritative. MuJoCo's native Phong
renderer approximates glTF PBR materials; it is not the browser renderer.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from PIL import Image

from sim.reference_glb_check import _read_glb, check_glb
from sim.reference_model import build_reference_model, load_reference_model

ROOT = Path(__file__).resolve().parents[1]
VISUAL_GROUP = 2
COLLISION_GROUP = 3
ENCLOSURE_GROUP = 4
ASSET_FILES = ("room.glb", "robot.glb", "phone.glb", "meal_box.glb")


def _vec(values):
    return " ".join(format(float(value), ".17g") for value in values)


def _accessor(document, binary, index):
    accessor = document["accessors"][index]
    if "sparse" in accessor:
        raise ValueError("Sparse GLB accessors are not supported")
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    dtype = np.dtype({5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}[accessor["componentType"]])
    view = document["bufferViews"][accessor["bufferView"]]
    count = int(accessor["count"])
    offset = int(view.get("byteOffset", 0))+int(accessor.get("byteOffset", 0))
    stride = int(view.get("byteStride", width*dtype.itemsize))
    length = int(view["byteLength"])
    relative = int(accessor.get("byteOffset", 0))
    if view.get("buffer", 0) != 0 or count < 1 or stride < width*dtype.itemsize or relative+(count-1)*stride+width*dtype.itemsize > length or offset+(count-1)*stride+width*dtype.itemsize > len(binary):
        raise ValueError("GLB accessor exceeds its embedded buffer")
    array = np.ndarray((count, width), dtype=dtype, buffer=binary, offset=offset, strides=(stride, dtype.itemsize)).copy()
    if accessor.get("normalized") and dtype.kind in "iu":
        array = array.astype(float)/np.iinfo(dtype).max
        if dtype.kind == "i":
            array = np.maximum(array, -1)
    if not np.isfinite(array).all():
        raise ValueError("GLB contains nonfinite geometry")
    return array


def _matrix(node):
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=float).reshape(4, 4, order="F")
    matrix = np.eye(4)
    xyzw = np.asarray(node.get("rotation", [0., 0., 0., 1.]))
    rotation = np.zeros(9)
    mujoco.mju_quat2Mat(rotation, xyzw[[3, 0, 1, 2]])
    matrix[:3, :3] = rotation.reshape(3, 3) @ np.diag(node.get("scale", [1., 1., 1.]))
    matrix[:3, 3] = node.get("translation", [0., 0., 0.])
    if not np.isfinite(matrix).all():
        raise ValueError("GLB contains a nonfinite transform")
    return matrix


def _msh(vertices, normals, uv, faces):
    """MuJoCo's documented binary MSH format preserves normals and UVs."""
    vertices = np.asarray(vertices, dtype="<f4")
    normals = np.asarray(normals, dtype="<f4") if normals is not None else np.empty((0, 3), dtype="<f4")
    uv = np.asarray(uv, dtype="<f4") if uv is not None else np.empty((0, 2), dtype="<f4")
    faces = np.asarray(faces, dtype="<i4")
    return struct.pack("<4i", len(vertices), len(normals), len(uv), len(faces))+vertices.tobytes()+normals.tobytes()+uv.tobytes()+faces.tobytes()


def _texture_image(document, binary, texture_index):
    texture = document["textures"][texture_index]
    image = document["images"][texture["source"]]
    if "bufferView" not in image:
        raise ValueError("Detailed visuals require embedded GLB textures")
    view = document["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    payload = binary[start:start+view["byteLength"]]
    with Image.open(io.BytesIO(payload)) as source:
        rgba = source.convert("RGBA")
        output = io.BytesIO()
        rgba.save(output, format="PNG")
    return output.getvalue()


def _material(asset, document, binary, index, prefix, cache, material_cache):
    key = (prefix, index)
    if key in material_cache:
        return material_cache[key]
    source = document.get("materials", [])[index] if index is not None else {}
    pbr = source.get("pbrMetallicRoughness", {})
    rgba = list(pbr.get("baseColorFactor", [1., 1., 1., 1.]))
    roughness = float(pbr.get("roughnessFactor", .7))
    metallic = float(pbr.get("metallicFactor", 0.))
    transmission = float(source.get("extensions", {}).get("KHR_materials_transmission", {}).get("transmissionFactor", 0.))
    if transmission:
        rgba[3] *= max(.12, 1.-.82*transmission)
    if source.get("alphaMode") == "BLEND":
        # MuJoCo selects its transparent render pass from material alpha.
        # A fully opaque factor would otherwise hide RGBA texture cutouts.
        rgba[3] = min(rgba[3], .999)
    name = f"visual_material_{prefix}_{index}"
    attributes = {"name": name, "rgba": _vec(rgba), "specular": str(.15+.45*metallic), "shininess": str(max(.02, (1.-roughness)*.7)), "reflectance": "0"}
    texture_info = pbr.get("baseColorTexture")
    if texture_info:
        texture_name = f"visual_texture_{prefix}_{texture_info['index']}"
        texture_file = f"{texture_name}.png"
        if not (cache/texture_file).exists():
            (cache/texture_file).write_bytes(_texture_image(document, binary, texture_info["index"]))
        if asset.find(f"texture[@name='{texture_name}']") is None:
            ET.SubElement(asset, "texture", name=texture_name, type="2d", file=texture_file, nchannel="4")
        attributes.update(texture=texture_name, texrepeat="1 1", texuniform="false")
    ET.SubElement(asset, "material", attributes)
    material_cache[key] = (name, texture_info)
    return name, texture_info


def _convert_glb(path, root, cache, body_nodes, *, room=False):
    document, binary, _ = _read_glb(path)
    if document.get("skins"):
        raise ValueError("GLB skin must be baked before native visual conversion")
    asset = root.find("asset")
    world = root.find("worldbody")
    materials = {}
    counters = {"geoms": 0, "vertices": 0, "triangles": 0, "enclosure_triangles": 0, "alpha_culled_triangles": 0}
    prefix = path.stem
    nodes = document["nodes"]
    roots = document["scenes"][document.get("scene", 0)]["nodes"]

    def visit(index, transform, body_name=None):
        node = nodes[index]
        name = node.get("name", f"node_{index}")
        if not room and name in body_nodes:
            # GLB body roots carry flattened initial world poses. Binding their
            # children directly to the existing MuJoCo body avoids double pose.
            transform = np.eye(4)
            body_name = name
        else:
            transform = transform @ _matrix(node)
        if "mesh" in node:
            if not room and body_name is None:
                raise ValueError(f"Unbound robot/object visual node: {name}")
            parent = world if room else body_nodes[body_name]
            for number, primitive in enumerate(document["meshes"][node["mesh"]]["primitives"]):
                if primitive.get("mode", 4) != 4 or primitive.get("targets"):
                    raise ValueError("Only baked GLB triangle primitives are supported")
                attributes = primitive["attributes"]
                positions = _accessor(document, binary, attributes["POSITION"]).astype(float)
                vertices = positions @ transform[:3, :3].T+transform[:3, 3]
                normals = None
                if "NORMAL" in attributes:
                    normals = _accessor(document, binary, attributes["NORMAL"]) @ np.linalg.inv(transform[:3, :3])
                    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
                faces = _accessor(document, binary, primitive["indices"]).reshape(-1, 3).astype(np.int32) if "indices" in primitive else np.arange(len(vertices), dtype=np.int32).reshape(-1, 3)
                if faces.min() < 0 or faces.max() >= len(vertices):
                    raise ValueError("GLB triangle references a missing vertex")
                if np.linalg.det(transform[:3, :3]) < 0:
                    faces = faces[:, [0, 2, 1]]
                material, texture_info = _material(asset, document, binary, primitive.get("material"), prefix, cache, materials)
                uv = None
                if texture_info:
                    texture_transform = texture_info.get("extensions", {}).get("KHR_texture_transform", {})
                    coordinate = texture_transform.get("texCoord", texture_info.get("texCoord", 0))
                    semantic = f"TEXCOORD_{coordinate}"
                    if semantic not in attributes:
                        raise ValueError(f"Textured GLB node {name} lacks {semantic}")
                    uv = _accessor(document, binary, attributes[semantic]).astype(float)
                    if texture_transform:
                        angle = float(texture_transform.get("rotation", 0.))
                        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
                        uv = (uv*np.asarray(texture_transform.get("scale", [1., 1.]))) @ rotation.T+texture_transform.get("offset", [0., 0.])
                    # MuJoCo's PNG loader uses the same image-row convention
                    # as this GLB exporter; preserve its authored UV values.
                    source_material=document["materials"][primitive["material"]]
                    if source_material.get("alphaMode") in {"BLEND","MASK"}:
                        # Native fixed-function texturing does not reproduce
                        # glTF per-pixel alpha. Discard only triangles whose
                        # three corners AND centroid lie in transparent texels;
                        # this removes the invisible MakeHuman corneal shell.
                        pixels=np.asarray(Image.open(io.BytesIO(_texture_image(document,binary,texture_info["index"]))))
                        samples=np.concatenate([uv[faces],uv[faces].mean(axis=1)[:,None,:]],axis=1)%1.
                        rows=np.minimum((samples[:,:,1]*pixels.shape[0]).astype(int),pixels.shape[0]-1)
                        columns=np.minimum((samples[:,:,0]*pixels.shape[1]).astype(int),pixels.shape[1]-1)
                        keep=pixels[rows,columns,3].max(axis=1)>=128
                        counters["alpha_culled_triangles"]+=int(np.count_nonzero(~keep))
                        faces=faces[keep]
                triangle_positions = vertices[faces]
                area = np.linalg.norm(np.cross(triangle_positions[:, 1]-triangle_positions[:, 0], triangle_positions[:, 2]-triangle_positions[:, 0]), axis=1)
                faces = faces[area > 2e-14]
                if not len(faces):
                    continue
                groups = [(VISUAL_GROUP, faces)]
                if room:
                    triangles = vertices[faces]
                    # Material batching merges the walls with other furniture.
                    # Split enclosure triangles spatially, preserving geometry.
                    enclosure = np.all(triangles[:, :, 0] > 3.48, axis=1) | np.all(triangles[:, :, 1] < -2.98, axis=1) | np.all(triangles[:, :, 2] > 2.99, axis=1)
                    groups = [(VISUAL_GROUP, faces[~enclosure]), (ENCLOSURE_GROUP, faces[enclosure])]
                for group, selected_faces in groups:
                    if not len(selected_faces):
                        continue
                    used, remapped = np.unique(selected_faces.reshape(-1), return_inverse=True)
                    if len(used) < 4:
                        raise ValueError(f"Visual primitive {name} has fewer than four usable vertices")
                    mesh_name = f"visual_mesh_{prefix}_{index}_{number}_{group}"
                    mesh_file = f"{mesh_name}.msh"
                    (cache/mesh_file).write_bytes(_msh(vertices[used], normals[used] if normals is not None else None, uv[used] if uv is not None else None, remapped.reshape(-1, 3)))
                    ET.SubElement(asset, "mesh", name=mesh_name, file=mesh_file, inertia="shell", maxhullvert="4")
                    ET.SubElement(parent, "geom", name=mesh_name, type="mesh", mesh=mesh_name, material=material, group=str(group), contype="0", conaffinity="0", mass="0", density="0")
                    counters["geoms"] += 1
                    counters["vertices"] += len(used)
                    counters["triangles"] += len(selected_faces)
                    counters["enclosure_triangles"] += len(selected_faces) if group == ENCLOSURE_GROUP else 0
        for child in node.get("children", []):
            visit(child, transform, body_name)

    for index in roots:
        visit(index, np.eye(4))
    return counters


def _assert_physics_parity(reference, model):
    scalar_fields = ("nbody", "njnt", "nq", "nv", "nu", "nsite", "ncam", "neq", "nmocap")
    for field in scalar_fields:
        if getattr(reference, field) != getattr(model, field):
            raise RuntimeError(f"Visual conversion changed physics topology: {field}")
    arrays = ("body_parentid", "body_pos", "body_quat", "body_mass", "body_inertia", "body_ipos", "body_iquat", "body_gravcomp", "jnt_type", "jnt_bodyid", "jnt_pos", "jnt_axis", "jnt_range", "jnt_stiffness", "dof_armature", "dof_damping", "dof_frictionloss", "actuator_trnid", "actuator_ctrlrange", "actuator_forcerange", "actuator_gainprm", "actuator_biasprm", "eq_type", "eq_obj1id", "eq_obj2id", "eq_data", "eq_solref", "eq_solimp", "cam_bodyid", "cam_pos", "cam_quat", "cam_fovy", "site_bodyid", "site_pos", "site_quat")
    for field in arrays:
        if not np.allclose(getattr(reference, field), getattr(model, field), atol=1e-12, rtol=1e-12):
            raise RuntimeError(f"Visual conversion changed physics field: {field}")
    geom_fields = ("type", "bodyid", "contype", "conaffinity", "condim", "size", "pos", "quat", "friction", "solref", "solimp", "margin", "gap")
    for index in range(reference.ngeom):
        name = reference.geom(index).name
        target = model.geom(name).id
        for field in geom_fields:
            if not np.allclose(getattr(reference, "geom_"+field)[index], getattr(model, "geom_"+field)[target], atol=1e-12, rtol=1e-12):
                raise RuntimeError(f"Visual conversion changed collision geom {name}: {field}")
    visuals = (model.geom_group == VISUAL_GROUP) | (model.geom_group == ENCLOSURE_GROUP)
    if np.any(model.geom_contype[visuals]) or np.any(model.geom_conaffinity[visuals]):
        raise RuntimeError("Detailed visual geometry unexpectedly participates in collisions")


def load_reference_visual_model(asset_dir=None, cache_dir=None):
    """Load detailed native visuals, failing clearly for unavailable/stale GLBs.

    The cache is bound to the exact GLB bytes, authoritative physics XML and
    converter source. It does not establish Blender source regeneration.
    """
    asset_dir = Path(asset_dir) if asset_dir is not None else ROOT/"assets"/"simulation"
    cache_root = Path(cache_dir) if cache_dir is not None else ROOT/".cache"/"reference-visual"
    reference, reference_data, metadata = load_reference_model()
    sources = {}
    for filename in ASSET_FILES:
        path = asset_dir/filename
        if not path.is_file():
            raise RuntimeError(f"Detailed native scene requires {path}. Restore/build the current scene assets; no proxy fallback was loaded.")
        sources[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = check_glb(asset_dir/"robot.glb", room_path=asset_dir/"room.glb")
    if not report["matched"] or report["model_hash"] != metadata["model_hash"]:
        raise RuntimeError("Detailed scene assets do not match current physics: "+"; ".join(report["failures"]))
    signature = {"physics_model_hash": metadata["model_hash"], "source_glbs": sources, "converter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "mujoco_version": mujoco.__version__}
    visual_hash = hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()
    cache = cache_root/visual_hash
    cache.mkdir(parents=True, exist_ok=True)
    xml_path, binary_path, receipt_path = cache/"model.xml", cache/"model.mjb", cache/"conversion.json"
    if binary_path.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("signature") != signature:
            raise RuntimeError("Native visual cache receipt is stale or corrupt; remove that cache entry and rebuild")
        for path,key in ((binary_path,"model_binary_sha256"),(xml_path,"model_xml_sha256")):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt.get(key):
                raise RuntimeError(f"Native visual cache content failed verification: {path}")
        for filename,digest in receipt.get("generated_assets",{}).items():
            path=cache/filename
            if Path(filename).name!=filename or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise RuntimeError(f"Native visual cache asset failed verification: {filename}")
        model = mujoco.MjModel.from_binary_path(str(binary_path))
    else:
        xml, _ = build_reference_model()
        root = ET.fromstring(xml)
        root.find("compiler").set("inertiafromgeom", "false")
        root.find("compiler").set("meshdir", str(cache))
        root.find("compiler").set("texturedir", str(cache))
        for geom in root.findall(".//geom"):
            if geom.get("name"):
                geom.set("group", str(COLLISION_GROUP))
        body_nodes = {body.get("name"): body for body in root.findall(".//body")}
        for name, body in body_nodes.items():
            index = reference.body(name).id
            ET.SubElement(body, "inertial", pos=_vec(reference.body_ipos[index]), quat=_vec(reference.body_iquat[index]), mass=str(reference.body_mass[index]), diaginertia=_vec(reference.body_inertia[index]))
        ET.SubElement(root, "statistic", meanmass=str(reference.stat.meanmass), meaninertia=str(reference.stat.meaninertia), meansize=str(reference.stat.meansize), extent=str(reference.stat.extent), center=_vec(reference.stat.center))
        ET.SubElement(root, "asset")
        world = root.find("worldbody")
        ET.SubElement(world, "light", name="visual_interior_fill", pos="0 -.5 2.8", diffuse=".55 .55 .55", ambient=".25 .25 .25", castshadow="false")
        counts = {filename: _convert_glb(asset_dir/filename, root, cache, body_nodes, room=filename=="room.glb") for filename in ASSET_FILES}
        # The shipped cutaway GLB omits these camera-facing room boundaries.
        # Render copies of the existing enclosure colliders in their own group;
        # this closes onboard views while retaining the exterior cutaway view.
        for name in ("wall_right", "wall_front", "ceiling"):
            original = world.find(f"geom[@name='{name}']")
            attributes = {key: original.get(key) for key in ("type", "pos", "size")}
            ET.SubElement(world, "geom", **attributes, name=f"visual_enclosure_{name}", group=str(ENCLOSURE_GROUP), contype="0", conaffinity="0", mass="0", density="0", rgba=".75 .79 .76 1")
        xml_path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
        try:
            model = mujoco.MjModel.from_xml_path(str(xml_path))
        except Exception as error:
            raise RuntimeError(f"Detailed native visual conversion failed: {error}") from error
        _assert_physics_parity(reference, model)
        mujoco.mj_saveModel(model, str(binary_path))
        receipt = {"signature": signature, "counts": counts, "physics_parity_verified": True, "visual_source_regeneration_verified": False,
                   "model_binary_sha256":hashlib.sha256(binary_path.read_bytes()).hexdigest(),
                   "model_xml_sha256":hashlib.sha256(xml_path.read_bytes()).hexdigest(),
                   "generated_assets":{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(cache.iterdir()) if path.suffix in {".msh",".png"}}}
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    _assert_physics_parity(reference, model)
    data = mujoco.MjData(model)
    data.qpos[:] = reference_data.qpos
    data.ctrl[:] = reference_data.ctrl
    data.mocap_pos[:] = reference_data.mocap_pos
    data.mocap_quat[:] = reference_data.mocap_quat
    mujoco.mj_forward(model, data)
    metadata.update(visual_model=True, visual_hash=visual_hash, visual_geom_groups={"detailed": VISUAL_GROUP, "collision": COLLISION_GROUP, "enclosure": ENCLOSURE_GROUP}, visual_assets={"source_glbs": sources, "cache_directory": str(cache), "model_xml": str(xml_path), "model_binary": str(binary_path), "receipt": str(receipt_path), **receipt}, visual_limitations=["Native MuJoCo Phong shading approximates glTF PBR materials; normal/roughness maps and transmission are not identical to Three.js", "RGBA alpha uses a triangle-level transparent-surface cutout approximation; fully transparent corneal triangles are omitted", "The exact shipped GLB geometry/textures and current body bindings are verified; Blender source regeneration is not established"])
    return model, data, metadata


if __name__ == "__main__":
    model, data, metadata = load_reference_visual_model()
    print(json.dumps({"model_hash": metadata["model_hash"], "visual_hash": metadata["visual_hash"], "ngeom": model.ngeom, "nmesh": model.nmesh, "visual_assets": metadata["visual_assets"]}, indent=2))
