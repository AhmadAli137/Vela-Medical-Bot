"""CC0 MakeHuman adult, dressed and resting in the reference hospital bed.

Call build_patient(globals()) from the room builder, or run this file in Blender
to render an isolated inspection. No addon, animation, clinical data or runtime
physics changes are involved. Graphical source licenses live in assets/patient.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/patient/makehuman"


def read_obj(path):
    vertices, coordinates, faces = [], [], []
    group = "mesh"
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "v":
            vertices.append(Vector(tuple(map(float, fields[1:4]))))
        elif fields[0] == "vt":
            coordinates.append(tuple(map(float, fields[1:3])))
        elif fields[0] == "g":
            group = fields[1]
        elif fields[0] == "f":
            corners = []
            for field in fields[1:]:
                values = field.split("/")
                corners.append((int(values[0])-1, int(values[1])-1 if len(values)>1 and values[1] else None))
            faces.append((group, corners))
    return vertices, coordinates, faces


def proxy_vertices(path, base):
    """Apply the asset's CC0 barycentric fit data to the exact hm08 base mesh."""
    result, scales, reading = [], Vector((1., 1., 1.)), False
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        values = line.split()
        if not values or values[0].startswith("#"):
            continue
        if values[0] in {"x_scale", "y_scale", "z_scale"}:
            axis = "xyz".index(values[0][0])
            scales[axis] = abs(base[int(values[1])][axis]-base[int(values[2])][axis])/float(values[3])
        elif values[0] == "verts":
            reading = True
        elif reading and len(values) == 9:
            try:
                indices = [int(x) for x in values[:3]]
                weights = [float(x) for x in values[3:6]]
                offsets = Vector(tuple(float(x)*scales[i] for i, x in enumerate(values[6:9])))
            except ValueError:
                break
            result.append(sum((base[i]*w for i,w in zip(indices,weights)), Vector())+offsets)
        elif reading and len(values) == 1 and values[0].isdigit():
            result.append(base[int(values[0])].copy())
        elif reading:
            break
    return result


def _material(name, rgba, roughness=.7, texture=None, alpha=False):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = rgba
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = rgba
    shader.inputs["Roughness"].default_value = roughness
    if texture:
        image = material.node_tree.nodes.new("ShaderNodeTexImage")
        image.image = bpy.data.images.load(str(SOURCE/texture), check_existing=True)
        material.node_tree.links.new(image.outputs["Color"], shader.inputs["Base Color"])
        if alpha:
            material.node_tree.links.new(image.outputs["Alpha"], shader.inputs["Alpha"])
            material.surface_render_method = "DITHERED"
    return material


def build_patient(namespace=None):
    ns = namespace or {}
    objects = ns.get("room_objects", [])
    if "assembly" in ns:
        patient = ns["assembly"]("patient")
    else:
        patient = bpy.data.objects.new("patient", None)
        bpy.context.collection.objects.link(patient)
        objects.append(patient)
    patient["fictional_adult"] = True
    patient["source"] = "MakeHuman CC0 hm08 artist-authored base; no real patient identity"
    patient["pose"] = "supine with head supported by pillow and arms resting beside torso"
    for name in ("Sage patient blanket", "Turned blanket hem"):
        old = bpy.data.objects.get(name)
        if old:
            if old in objects:
                objects.remove(old)
            bpy.data.objects.remove(old, do_unlink=True)

    skin = _material("Patient skin · CC0 adult texture", (.55,.32,.22,1), .53, "middleage_lightskinned_male_diffuse.png")
    skin.node_tree.nodes.get("Principled BSDF").inputs["Subsurface Weight"].default_value = .075
    skin.node_tree.nodes.get("Principled BSDF").inputs["Subsurface Radius"].default_value = (1.,.45,.22)
    hair = _material("Patient short hair · CC0 alpha texture", (.06,.04,.025,1), .85, "short01_diffuse.png", True)
    # The source texture uses a transparent atlas island for the outer cornea.
    # Ignoring alpha renders that shell opaque blue-white over iris and pupil.
    eyes = _material("Patient eyes · CC0 brown texture", (.55,.50,.40,1), .2, "brown_eye.png", True)
    gown = _material("Patient gown · pale blue woven cotton", (.49,.67,.73,1), .94)
    seam = _material("Patient gown · seam thread", (.26,.47,.55,1), .98)
    blanket = ns.get("M", {}).get("blanket") or _material("Patient blanket · sage cotton", (.34,.48,.42,1), .98)

    base, uv, faces = read_obj(SOURCE/"base.obj")
    skeleton = json.loads((SOURCE/"default.mhskel").read_text())
    weight_data = json.loads((SOURCE/"default_weights.mhw").read_text())["weights"]
    arm_weights = {"L": {}, "R": {}}
    for name, weights in weight_data.items():
        if name.startswith(("upperarm", "lowerarm", "wrist", "finger", "metacarpal")):
            side = name[-1]
            if side in arm_weights:
                for index, weight in weights:
                    arm_weights[side][index] = arm_weights[side].get(index, 0.)+weight
    posed = [v.copy() for v in base]
    hand_indices=set()
    for side in ("L", "R"):
        weights={}
        for name,pairs in weight_data.items():
            if name.endswith("."+side) and name.startswith(("wrist","finger","metacarpal")):
                for index,weight in pairs:
                    weights[index]=weights.get(index,0.)+weight
        indices=skeleton["joints"][skeleton["bones"][f"wrist.{side}"]["head"]]
        wrist=sum((base[i]for i in indices),Vector())/len(indices)
        rotation=Matrix.Rotation(math.radians(40),3,"X")
        for index,weight in weights.items():
            posed[index]+=min(1.,weight)*(rotation@(posed[index]-wrist)+wrist-posed[index])
    for side in ("L", "R"):
        forearm_weights={}
        for name, weights in weight_data.items():
            if name.endswith("."+side) and name.startswith(("lowerarm", "wrist", "finger", "metacarpal")):
                for index,weight in weights:
                    forearm_weights[index]=forearm_weights.get(index,0.)+weight
                    if name.startswith(("wrist","finger","metacarpal")) and weight>.05:
                        hand_indices.add(index)
        descriptor=skeleton["bones"][f"lowerarm01.{side}"]
        indices=skeleton["joints"][descriptor["head"]]
        elbow=sum((base[i]for i in indices),Vector())/len(indices)
        rotation=Matrix.Rotation(math.radians(25),3,"X")
        for index,weight in forearm_weights.items():
            posed[index]+=min(1.,weight)*(rotation@(posed[index]-elbow)+elbow-posed[index])
    for side, sign in (("L", 1), ("R", -1)):
        descriptor = skeleton["bones"][f"upperarm01.{side}"]
        indices = skeleton["joints"][descriptor["head"]]
        shoulder = sum((base[i] for i in indices), Vector())/len(indices)
        raise_arm=Matrix.Rotation(math.radians(-10),3,"X")
        rotation = Matrix.Rotation(math.radians(-35*sign), 3, "Z")
        for index, weight in arm_weights[side].items():
            weight = min(1., weight)
            posed[index]+=weight*(raise_arm@(posed[index]-shoulder)+shoulder-posed[index])
            posed[index] += weight*(rotation@(posed[index]-shoulder)+shoulder-posed[index])

    def to_world(vertex):
        # Native MakeHuman uses decimetres and +Y stature, +Z face-forward.
        # Raising the head/neck smoothly rests the occiput on the pillow.
        x,y,z = vertex
        ratio = max(0., min(1., (y-4.1)/2.6))
        support = .15*ratio*ratio*(3.-2.*ratio)
        return Vector((1.4+.1*x, 1.35+.1*y, .98+.1*z+support))

    world = [to_world(v) for v in posed]

    def finish(obj):
        obj.parent = patient
        obj["assembly"] = "patient"
        objects.append(obj)
        return obj

    def mesh(name, positions, coords, source_faces, mat, subdivision=0):
        used = sorted({index for _, face in source_faces for index,_ in face})
        mapping = {old:new for new,old in enumerate(used)}
        data = bpy.data.meshes.new(name)
        data.from_pydata([positions[i] for i in used], [], [[mapping[i] for i,_ in face] for _,face in source_faces])
        data.update()
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        data.materials.append(mat)
        layer = data.uv_layers.new(name="SourceUV")
        data.polygons.foreach_set("use_smooth",[True]*len(data.polygons))
        uv_values=[]
        for _,face in source_faces:
            for _,coordinate in face:
                uv_values.extend(coords[coordinate] if coordinate is not None and coords else (0.,0.))
        layer.data.foreach_set("uv",uv_values)
        finish(obj)
        if subdivision:
            bpy.context.view_layer.objects.active = obj
            modifier = obj.modifiers.new("Smooth anatomical topology", "SUBSURF")
            modifier.levels = subdivision
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        return obj

    skin_faces = [face for face in faces if face[0] == "body"]
    print("Patient: creating anatomical skin", flush=True)
    body = mesh("patient_anatomical_skin", world, uv, skin_faces, skin, 1)
    for name, obj_file, mapping_file, mat in (("patient_short_hair", "short01.obj", "short01.mhclo", hair), ("patient_eyes", "high-poly.obj", "high-poly.mhclo", eyes)):
        _, asset_uv, asset_faces = read_obj(SOURCE/obj_file)
        fitted = proxy_vertices(SOURCE/mapping_file, base)
        mesh(name, [to_world(v) for v in fitted], asset_uv, asset_faces, mat, 0)

    # Loose gown surface derives from the actual torso and upper arm topology.
    # It is intentionally independent cloth geometry, with no anatomical skin
    # showing beneath the garment and no nude lower body visible above bedding.
    covered = []
    for group, face in skin_faces:
        center = sum((base[index] for index,_ in face), Vector())/len(face)
        # Keep the visible gown plus an overlap beneath the waist blanket;
        # omit hidden lower cloth sheets to avoid coincident surface shards.
        if 1.30 < center.y < 5.60 and (abs(center.x)<1.75 or center.y>3.8 and abs(center.x)<2.7):
            covered.append((group,face))
    gown_world = []
    for original, position in zip(base, world):
        p = position.copy()
        if original.y < 5.50:
            p.x = 1.4+(p.x-1.4)*1.10
        p.z += .018 if original.z>0 else -.007
        p.z += .0018*math.sin(original.y*9+original.x*7)
        gown_world.append(p)
    garment = mesh("patient_hospital_gown", gown_world, uv, covered, gown, 0)
    bpy.context.view_layer.objects.active = garment
    modifier = garment.modifiers.new("Relax cotton folds", "SMOOTH")
    modifier.factor = .8
    modifier.iterations = 6
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    modifier = garment.modifiers.new("Cloth thickness", "SOLIDIFY")
    modifier.thickness = .002
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    modifier = garment.modifiers.new("Soft gown folds", "SUBSURF")
    modifier.levels = 1
    bpy.ops.object.modifier_apply(modifier=modifier.name)

    def line(name, points, radius, material):
        curve = bpy.data.curves.new(name,"CURVE")
        curve.dimensions="3D"
        curve.bevel_depth=radius
        curve.bevel_resolution=2
        spline=curve.splines.new("BEZIER")
        spline.bezier_points.add(len(points)-1)
        for p,co in zip(spline.bezier_points,points):
            p.co=co
            p.handle_left_type="AUTO"
            p.handle_right_type="AUTO"
        obj=bpy.data.objects.new(name,curve)
        bpy.context.collection.objects.link(obj)
        obj.data.materials.append(material)
        finish(obj)
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active=obj
        bpy.ops.object.convert(target="MESH")
        return obj

    # Drape lower bedding over the actual upper envelope of the posed legs,
    # hips and lower torso. A coarse spatial grid keeps the build bounded.
    bins = {}
    body_indices={index for _,face in skin_faces for index,_ in face}
    arm_indices={index for weights in arm_weights.values() for index,weight in weights.items() if weight>.05}
    for index in body_indices-arm_indices:
        position=world[index]
        if .35 < position.y < 1.72 and .85<position.x<1.95:
            key=(round(position.x/.025),round(position.y/.025))
            bins[key]=max(bins.get(key,.89),position.z)
    bpy.context.view_layer.update()
    gown_support=BVHTree.FromObject(garment,bpy.context.evaluated_depsgraph_get())
    body_support_faces=[[index for index,_ in face]for _,face in skin_faces if not any(index in arm_indices for index,_ in face)]
    body_support=BVHTree.FromPolygons(world,body_support_faces,all_triangles=False)
    def surface_height(x,y):
        heights=[.887]
        for support in (gown_support,body_support):
            hit=support.ray_cast(Vector((x,y,2.)),Vector((0,0,-1)),2.)
            if hit[0] is not None:
                heights.append(hit[0].z)
        return max(heights)
    nx,ny=96,128
    vertices,blanket_uv,blanket_faces=[],[],[]
    for j in range(ny+1):
        y=.40+j/ny*1.14
        for i in range(nx+1):
            x=.83+i/nx*1.14
            heights=[]
            for dx in range(-3,4):
                for dy in range(-3,4):
                    key=(round(x/.025)+dx,round(y/.025)+dy)
                    if key in bins:
                        distance=math.hypot(dx*.025,dy*.025)
                        heights.append(bins[key]+.005-distance*.35)
            z=max([surface_height(x,y)+.005,*heights])
            edge=max(0.,(abs(x-1.4)-.47)/.10)
            z-=.17*edge**1.5
            z+=.001*math.sin(x*64+y*17)+.001*math.sin(y*55-x*7)
            vertices.append((x,y,z))
            blanket_uv.append((i/nx*2,j/ny*3))
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i
            blanket_faces.append(("blanket",[(index,index)for index in (a,a+1,a+nx+2,a+nx+1)]))
    blanket_obj=mesh("patient_contoured_blanket",vertices,blanket_uv,blanket_faces,blanket,0)
    bpy.context.view_layer.objects.active=blanket_obj
    smooth=blanket_obj.modifiers.new("Broad natural bedding folds","SMOOTH")
    smooth.factor=.85;smooth.iterations=5
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    # Smoothing must not push bedding through the dressed body. Project only
    # upward onto the actual supporting surfaces, preserving relaxed valleys.
    for vertex in blanket_obj.data.vertices:
        if .905<vertex.co.x<1.895:
            vertex.co.z=max(vertex.co.z,surface_height(vertex.co.x,vertex.co.y)+.005)
    thick=blanket_obj.modifiers.new("Blanket hem thickness","SOLIDIFY")
    thick.thickness=.003
    bpy.ops.object.modifier_apply(modifier=thick.name)

    def bone_position(name):
        indices=skeleton["joints"][skeleton["bones"][name]["head"]]
        return sum((world[index] for index in indices),Vector())/len(indices)
    anatomical_markers={
        "patient_head":to_world(Vector((0.,7.55,.3))),
        "patient_torso":to_world(Vector((0.,3.8,.7))),
        "patient_left_arm":bone_position("lowerarm01.L"),
        "patient_right_arm":bone_position("lowerarm01.R"),
        "patient_left_leg":Vector((1.50,.92,1.0)),
        "patient_right_leg":Vector((1.30,.92,1.0)),
    }
    for name,position in anatomical_markers.items():
        marker=bpy.data.objects.new(name,None)
        bpy.context.collection.objects.link(marker)
        marker.location=position
        marker.empty_display_size=.03
        finish(marker)
    bbox=[body.matrix_world@Vector(corner)for corner in body.bound_box]
    manifest={"source":"MakeHuman hm08 CC0 mesh and official core textures/hair/eyes", "fictional_adult":True,"clinical_data":False,"anatomical_base_faces":len(skin_faces),"skin_faces_after_subdivision":len(body.data.polygons),"pose":"supine, supported head and tucked arms","head_center":list(anatomical_markers["patient_head"]),"face_direction":[0,0,1],"body_bounds":{"min":[min(p[i]for p in bbox)for i in range(3)],"max":[max(p[i]for p in bbox)for i in range(3)]},"named_anatomy":{name:list(value)for name,value in anatomical_markers.items()},"blanket_bounds":{"x":[.83,1.97],"y":[.40,1.54]},"mesh_objects":[obj.name for obj in patient.children if obj.type=="MESH"],"limitations":["Static visual patient only; no human dynamics, physiology or clinical simulation","Generic artist-authored adult anatomy, not a scan of an identified patient","Bed fit and cloth drape are visual approximations"]}
    destination=ROOT/"assets/patient/patient-build-manifest.json"
    destination.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    patient["manifest"]=str(destination.relative_to(ROOT))
    return patient


if __name__=="__main__":
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    build_patient()
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.samples=24
    scene.render.resolution_x=1280
    scene.render.resolution_y=960
    scene.render.resolution_percentage=100
    scene.world.color=(.25,.25,.25)
    bpy.ops.object.light_add(type="AREA",location=(.6,1.2,3.))
    bpy.context.object.data.energy=180
    bpy.context.object.data.shape="DISK"
    bpy.context.object.data.size=3.
    closeup="--face" in sys.argv
    bpy.ops.object.camera_add(location=(1.4,1.82,1.70) if closeup else (3.1,.60,3.1))
    camera=bpy.context.object
    camera.rotation_euler=(Vector((1.4,2.105,1.18) if closeup else (1.4,1.5,1.05))-camera.location).to_track_quat("-Z","Y").to_euler()
    camera.data.lens=65 if closeup else 52
    scene.camera=camera
    scene.render.image_settings.file_format="PNG"
    scene.render.filepath=str(ROOT/"assets/patient"/("patient-eye-inspection.png" if closeup else "patient-inspection.png"))
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/"assets/patient/patient-inspection.blend"))
    bpy.ops.render.render(write_still=True)
