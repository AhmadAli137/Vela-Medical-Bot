"""Run with Blender --background --factory-startup --python this-file.

Creates editable, detailed visual assets from the supplied Bracket Bot imagery.
Dimensions are estimates. No vendor CAD or exact reconstruction is claimed.
"""
import bpy
import json
import math
import random
import sys
from pathlib import Path
from mathutils import Vector, Quaternion

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"assets"/"simulation"
OUT.mkdir(parents=True,exist_ok=True)
random.seed(21)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
room_objects=[]
robot_objects=[]
current_objects=room_objects


def color(hex_value):
    rgb=[int(hex_value[i:i+2],16)/255 for i in (0,2,4)]
    return tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb)+(1,)


def material(name,hex_value,roughness=.45,metallic=0,transmission=0):
    mat=bpy.data.materials.new(name)
    mat.use_nodes=True
    mat.diffuse_color=color(hex_value)
    shader=mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value=color(hex_value)
    shader.inputs["Roughness"].default_value=roughness
    shader.inputs["Metallic"].default_value=metallic
    if transmission:
        shader.inputs["Transmission Weight"].default_value=transmission
        shader.inputs["IOR"].default_value=1.45
    return mat


M={
    "shell":material("Robot · warm satin polymer","E7E8E2",.27),
    "metal":material("Machined aluminium","9CA6A7",.25,.8),
    "darkmetal":material("Anodized actuator housings","454B4D",.31,.65),
    "rubber":material("Tire rubber","191C1E",.83),
    "black":material("Carbon black detail","111819",.39),
    "glass":material("Stereo optical cover","091522",.10,.12),
    "lens":material("Coated lens glass","253E69",.12,.6),
    "green":material("Gripper green status inset","60CF9B",.25),
    "wall":material("Warm mineral wall finish","EEECE3",.91),
    "white":material("Porcelain white","F4F2EB",.36),
    "linen":material("White cotton linen","F4F0E6",.96),
    "blanket":material("Sage knitted blanket","8BABA0",.98),
    "wood":material("Light natural oak","B9A07D",.57),
    "wooddark":material("Oak endgrain trim","947B5E",.5),
    "floor":material("Warm resilient vinyl","ACA79A",.48),
    "seam":material("Floor board seams","938E83",.7),
    "upholstery":material("Visitor chair woven teal","527B78",.94),
    "steel":material("Hospital frame steel","A8B3B5",.3,.85),
    "bedframe":material("Medical furniture polymer","E1E6E1",.42),
    "panel":material("Headwall pale sage","CDDAD1",.63),
    "curtain":material("Sheer window curtain","DFE5DC",.97),
    "window":material("Low iron window glass","C0D9E3",.09,0,.82),
    "sky":material("Daylight exterior","CBDFE5",1),
    "leaf":material("Foliage","476C3C",.9),
    "leaf2":material("Foliage highlight","729257",.9),
    "soil":material("Potting soil","382E20",1),
}


def add_texture(mat,stem):
    # Only externally acquired files with provenance are used when present.
    folder=ROOT/"assets"/"textures"
    candidates=list(folder.rglob("*.jpg"))+list(folder.rglob("*.png")) if folder.exists() else []
    path=next((p for p in candidates if stem in p.name.lower() and any(t in p.name.lower() for t in ("diff","color","albedo"))),None)
    if not path:
        return
    nodes=mat.node_tree.nodes
    tex=nodes.new("ShaderNodeTexImage")
    tex.image=bpy.data.images.load(str(path))
    mat.node_tree.links.new(tex.outputs["Color"],nodes.get("Principled BSDF").inputs["Base Color"])
    for key in ("rough","normal","nor_gl"):
        other=next((p for p in candidates if stem in p.name.lower() and key in p.name.lower()),None)
        if not other:continue
        image=nodes.new("ShaderNodeTexImage")
        image.image=bpy.data.images.load(str(other));image.image.colorspace_settings.name="Non-Color"
        if key=="rough":mat.node_tree.links.new(image.outputs["Color"],nodes.get("Principled BSDF").inputs["Roughness"])
        elif key=="nor_gl":
            normal=nodes.new("ShaderNodeNormalMap");normal.inputs["Strength"].default_value=.35
            mat.node_tree.links.new(image.outputs["Color"],normal.inputs["Color"])
            mat.node_tree.links.new(normal.outputs["Normal"],nodes.get("Principled BSDF").inputs["Normal"])


def finish(obj,name,mat,parent=None,smooth=False):
    obj.name=name
    if mat:obj.data.materials.append(mat)
    if parent:obj.parent=parent
    if smooth and obj.type=="MESH":
        for p in obj.data.polygons:p.use_smooth=True
    current_objects.append(obj)
    return obj


def box(name,loc,size,mat,bevel=.01,parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    obj=bpy.context.object
    obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=obj.modifiers.new("Soft manufactured edges","BEVEL");mod.width=bevel;mod.segments=3
        bpy.ops.object.modifier_apply(modifier=mod.name)
        normal=obj.modifiers.new("Weighted face normals","WEIGHTED_NORMAL")
        bpy.ops.object.modifier_apply(modifier=normal.name)
    return finish(obj,name,mat,parent)


def cylinder(name,loc,radius,depth,mat,axis=(0,0,1),parent=None,vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=loc)
    obj=bpy.context.object
    obj.rotation_mode="QUATERNION";obj.rotation_quaternion=Vector(axis).to_track_quat("Z","Y")
    mod=obj.modifiers.new("Rounded machined edge","BEVEL");mod.width=min(radius*.09,.008);mod.segments=3
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return finish(obj,name,mat,parent,True)


def sphere(name,loc,scale,mat,parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,radius=1,location=loc)
    obj=bpy.context.object;obj.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(obj,name,mat,parent,True)


def tube(name,points,radius,mat,parent=None):
    curve=bpy.data.curves.new(name,"CURVE");curve.dimensions="3D";curve.bevel_depth=radius;curve.bevel_resolution=3
    spline=curve.splines.new("BEZIER");spline.bezier_points.add(len(points)-1)
    for p,co in zip(spline.bezier_points,points):p.co=co;p.handle_left_type="AUTO";p.handle_right_type="AUTO"
    obj=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    bpy.ops.object.convert(target="MESH");obj=bpy.context.object
    return finish(obj,name,mat,parent,True)


def label(name,text,loc,size,mat,rotation=(math.pi/2,0,0),parent=None):
    curve=bpy.data.curves.new(name,"FONT");curve.body=text;curve.size=size;curve.extrude=.0003;curve.align_x="CENTER"
    obj=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(obj);obj.location=loc;obj.rotation_euler=rotation
    bpy.ops.object.select_all(action="DESELECT");obj.select_set(True);bpy.context.view_layer.objects.active=obj;bpy.ops.object.convert(target="MESH")
    return finish(bpy.context.object,name,mat,parent)


def cloth(name,xrange,yrange,z,mat,drop=.14):
    vertices=[];faces=[];nx,ny=48,72
    for j in range(ny+1):
        v=j/ny;y=yrange[0]+v*(yrange[1]-yrange[0])
        for i in range(nx+1):
            u=i/nx;x=xrange[0]+u*(xrange[1]-xrange[0])
            edge=max(0,(abs(u-.5)-.40)/.1)
            sag=drop*edge**1.5
            wrinkles=.005*math.sin(u*83+v*17)+.004*math.cos(v*67+u*15)+.008*math.sin(v*23)*edge
            vertices.append((x,y,z-sag+wrinkles))
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i;faces.append((a,a+1,a+nx+2,a+nx+1))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    solid=obj.modifiers.new("Fabric thickness","SOLIDIFY");solid.thickness=.006
    return finish(obj,name,mat,smooth=True)


def room():
    box("Floor slab",(0,0,-.08),(7,6,.16),M["floor"],.008)
    # Individual seams, offset rows and subtly varying plank colour.
    for row in range(20):
        y=-2.85+row*.30
        for col in range(6):
            x=-3.5+col*1.35+(row%3)*.45
            low=max(-3.5,x);high=min(3.5,x+1.345)
            if high<=low:continue
            box(f"Vinyl plank {row} {col}",((low+high)/2,y,.001),(high-low,.297,.008),M["floor"],.001)
    box("Back wall",(0,3.04,1.5),(7,.10,3),M["wall"],.006)
    box("Left sill wall",(-3.55,0,.40),(.10,6,.8),M["wall"],.006)
    box("Left window header",(-3.55,0,2.85),(.10,6,.3),M["wall"],.006)
    for y in (-2.25,2.35):box("Left window pier",(-3.55,y,1.7),(.12,1.5,1.8),M["wall"],.006)
    box("Right return wall",(3.55,1.9,1.5),(.10,2.2,3),M["wall"],.006)
    for loc,size in (((0,2.97,.08),(7,.025,.16)),((-3.48,0,.08),(.025,6,.16)),((3.48,1.9,.08),(.025,2.2,.16))):box("Rounded baseboard",loc,size,M["white"],.008)
    # Tall glazed opening is a visual layout prior, not a photo-derived metric model.
    for y in (-1.45,1.55):box("Window vertical frame",(-3.47,y,1.75),(.09,.05,1.85),M["white"],.01)
    for z in (.84,2.67):box("Window crossframe",(-3.47,.05,z),(.10,3.05,.05),M["white"],.008)
    box("Window center mullion",(-3.46,.05,1.75),(.09,.04,1.85),M["white"],.006)
    box("Window glazing",(-3.51,.05,1.75),(.015,3.0,1.8),M["window"],.002)
    box("Deep window sill",(-3.38,.05,.83),(.32,3.15,.055),M["white"],.008)
    box("Soft daylight exterior",(-5.5,0,2.0),(.02,9,7),M["sky"],0)
    # External planting creates parallax, rather than a flat room-photo backdrop.
    for i in range(7):
        y=-3+i*1.0;x=-4.2-random.random()*.4
        cylinder("Exterior slender trunk",(x,y,.85),.025,1.7,M["wooddark"])
        for j in range(9):
            sphere("Exterior foliage",(x+random.uniform(-.18,.18),y+random.uniform(-.28,.28),1.4+random.random()*.9),(.15,.20,.3),M["leaf"] if j%2 else M["leaf2"])
    # Curtain panels with real drape geometry.
    for yc in (-1.38,1.43):
        verts=[];faces=[]
        for j in range(31):
            z=.88+j/30*1.75
            for i in range(61):
                y=yc+(i/60-.5)*.42;x=-3.23+.045*math.sin(i*.7)+.014*math.sin(z*4+i*.1)
                verts.append((x,y,z))
        for j in range(30):
            for i in range(60):a=j*61+i;faces.append((a,a+1,a+62,a+61))
        mesh=bpy.data.meshes.new("Draped sheer curtain");mesh.from_pydata(verts,[],faces)
        obj=bpy.data.objects.new("Draped sheer curtain",mesh);bpy.context.collection.objects.link(obj);finish(obj,obj.name,M["curtain"],smooth=True)
    cylinder("Curtain track",(-3.20,.05,2.7),.012,3.1,M["steel"],axis=(0,1,0))
    # Built-in cabinetry and layered headwall.
    box("Oak clinical headwall",(1.40,2.91,1.40),(2.25,.15,2.55),M["wood"],.018)
    for x in (.35,1.15,1.95,2.5):box("Headwall vertical join",(x,2.82,1.40),(.005,.003,2.45),M["wooddark"],0)
    box("Headwall service panel",(1.40,2.80,1.18),(2.0,.05,.36),M["panel"],.025)
    for x in (.7,1.05,1.75,2.1):
        box("Service outlet face",(x,2.764,1.19),(.14,.02,.19),M["white"],.008)
        for z in (1.15,1.22):
            box("Outlet slot",(x-.024,2.75,z),(.009,.005,.022),M["darkmetal"],.002)
            box("Outlet slot",(x+.024,2.75,z),(.009,.005,.022),M["darkmetal"],.002)
    box("Wall task light",(1.4,2.78,2.18),(1.6,.10,.055),M["white"],.018)
    label("Room plaque","417",(-2.7,2.90,2.35),.19,M["darkmetal"])
    for x in (-2.75,-2.12):
        box("Wardrobe carcass",(x,2.6,1.12),(.60,.72,2.24),M["wood"],.012)
        box("Wardrobe door",(x,2.223,1.12),(.57,.035,2.20),M["wood"],.008)
        cylinder("Brushed handle",(x+.18,2.18,1.17),.009,.30,M["steel"])
    # Bed base and actual furniture details.
    for x in (.98,1.82):
        box("Bed lower longitudinal beam",(x,1.43,.26),(.085,1.8,.085),M["bedframe"],.018)
        for y in (.60,2.25):
            cylinder("Caster fork",(x,y,.18),.036,.18,M["steel"])
            cylinder("Bed caster tire",(x,y,.105),.085,.06,M["rubber"],axis=(1,0,0))
            cylinder("Bed caster hub",(x+.031,y,.105),.041,.008,M["steel"],axis=(1,0,0))
    for y in (.85,2.02):box("Bed lift support",(1.4,y,.48),(.36,.28,.40),M["bedframe"],.035)
    box("Bed support deck",(1.4,1.43,.67),(1.05,2.16,.15),M["bedframe"],.065)
    box("Mattress core",(1.4,1.43,.81),(.99,2.08,.15),M["white"],.070)
    cloth("Fitted cotton sheet",(.88,1.92),(.38,2.48),.89,M["linen"],.09)
    pillow=box("Pillow loft",(1.4,2.12,.99),(.71,.43,.16),M["linen"],.077)
    pillow.rotation_euler[2]=-.04
    cloth("Sage patient blanket",(.85,1.95),(.42,1.90),.909,M["blanket"],.17)
    cloth("Turned blanket hem",(.85,1.95),(1.75,1.93),.923,M["blanket"],.12)
    for y in (.32,2.54):
        box("Bed end board",(1.4,y,.85),(1.04,.09,.48),M["bedframe"],.07)
        box("Bed end board recessed panel",(1.4,y-.051,.86),(.8,.018,.27),M["panel"],.035)
    for x in (.82,1.98):
        for y in (.75,2.0):
            tube("Safety rail",[(x,y-.25,.81),(x,y-.25,1.08),(x,y+.25,1.08),(x,y+.25,.81)],.022,M["bedframe"])
            for dy in (-.16,0,.16):cylinder("Rail crossbar",(x,y+dy,.955),.012,.22,M["bedframe"])
    box("Rail interface",(2.003,1.98,.985),(.035,.19,.11),M["white"],.015)
    for y in (1.935,1.98,2.025):sphere("Rail soft button",(2.025,y,.985),(.004,.011,.011),M["panel"])
    # Bedside work table, cupboard and visitor chair.
    box("Bedside tabletop",(.75,-.70,.75),(.80,.80,.045),M["wood"],.025)
    for x in (.43,1.07):
        for y in (-1.02,-.38):cylinder("Table aluminium leg",(x,y,.36),.022,.71,M["steel"])
    box("Phone",(.63,-.72,.785),(.082,.158,.012),M["black"],.007)
    box("Phone display",(.63,-.72,.792),(.073,.142,.002),M["glass"],.004)
    sphere("Phone camera",(.65,-.781,.794),(.003,.003,.001),M["lens"])
    box("Soft glasses case",(.91,-.53,.79),(.16,.067,.04),M["upholstery"],.02)
    box("Bedside storage",(2.62,2.30,.39),(.52,.52,.75),M["wood"],.018)
    box("Bedside storage top",(2.62,2.30,.79),(.58,.58,.05),M["white"],.02)
    for z in (.3,.57):
        box("Drawer face",(2.62,2.025,z),(.46,.028,.21),M["wood"],.012)
        cylinder("Drawer pull",(2.62,2.001,z+.04),.008,.16,M["steel"],axis=(1,0,0))
    for x in (-1.93,-1.27):
        for y in (1.00,1.60):cylinder("Visitor chair leg",(x,y,.22),.022,.44,M["wooddark"])
    box("Visitor chair seat",(-1.60,1.30,.49),(.77,.73,.18),M["upholstery"],.08)
    back=box("Visitor chair upholstered back",(-1.60,1.64,.84),(.77,.18,.66),M["upholstery"],.075);back.rotation_euler[0]=-.10
    for x in (-2.0,-1.2):box("Visitor chair padded arm",(x,1.30,.71),(.13,.70,.16),M["upholstery"],.055)
    # A small table, plant and personal props add scale and lived-in detail.
    cylinder("Round visitor table top",(-2.55,1.55,.62),.28,.035,M["wood"])
    cylinder("Visitor table stem",(-2.55,1.55,.32),.03,.60,M["steel"])
    cylinder("Visitor table foot",(-2.55,1.55,.025),.20,.025,M["steel"])
    cylinder("Water cup",(-2.55,1.55,.72),.038,.16,M["white"])
    cylinder("Plant pot",(-2.88,-1.18,.28),.14,.32,M["white"])
    cylinder("Plant soil",(-2.88,-1.18,.445),.126,.008,M["soil"])
    for i in range(12):
        angle=i*2.4;tip=(-2.88+math.cos(angle)*.22,-1.18+math.sin(angle)*.22,.65+random.random()*.23)
        tube("Plant stem",[(-2.88,-1.18,.43),(-2.88,-1.18,.58),tip],.0025,M["leaf"])
        leaf=sphere("Long plant leaf",tip,(.038,.12,.016),M["leaf"] if i%2 else M["leaf2"]);leaf.rotation_euler=(.6,angle,angle)
    # Framed artwork and room controls: generic artwork, no patient information.
    box("Artwork oak frame",(-.75,2.94,1.94),(.85,.06,.62),M["wooddark"],.008)
    box("Artwork canvas",(-.75,2.901,1.94),(.78,.012,.55),M["white"],.001)
    for i,(x,z,r) in enumerate(((-.92,1.96,.12),(-.70,1.90,.14),(-.58,2.04,.07))):
        sphere("Abstract botanical artwork",(x,2.889,z),(r,.003,r*.7),M["panel"] if i%2 else M["upholstery"])


def robot(descriptors):
    global current_objects
    current_objects=robot_objects
    parents={}
    bodies=descriptors["initial_world_poses"]
    if isinstance(bodies,dict):bodies=[{"name":k,**v} for k,v in bodies.items()]
    for desc in bodies:
        name=desc.get("name",desc.get("id"))
        empty=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(empty);parents[name]=empty;robot_objects.append(empty)
        position=desc.get("world_position",desc.get("position",(0,0,0)))
        quat=desc.get("world_quaternion",desc.get("quaternion",(1,0,0,0)))
        empty.location=position;empty.rotation_mode="QUATERNION";empty.rotation_quaternion=Quaternion(quat)
    def parent(name):return parents.get(name)
    base=parent("robot_base")
    cylinder("White transverse base housing",(0,0,0),.104,.33,M["shell"],axis=(0,1,0),parent=base)
    box("Jetson compute enclosure",(-.075,0,.12),(.09,.16,.14),M["darkmetal"],.015,base)
    for y in [i*.011-.07 for i in range(14)]:box("Compute cooling fin",(-.123,y,.12),(.009,.003,.105),M["black"],.001,base)
    cylinder("Mast base collar",(-.025,0,.13),.072,.15,M["shell"],parent=base)
    for side in ("left","right"):
        p=parent(side+"_wheel")
        if not p:continue
        cylinder("Textured rubber tire",(0,0,0),.13,.057,M["rubber"],axis=(0,1,0),parent=p,vertices=80)
        sign=1 if side=="left" else -1
        cylinder("Recessed wheel hub",(0,sign*.032,0),.096,.008,M["black"],axis=(0,1,0),parent=p)
        cylinder("Hub motor rim",(0,sign*.038,0),.079,.004,M["darkmetal"],axis=(0,1,0),parent=p)
        for i in range(72):
            a=i*2*math.pi/72
            tread=box("Tire tread",(math.sin(a)*.128,0,math.cos(a)*.128),(.012,.056,.007),M["rubber"],.001,p)
            tread.rotation_euler[1]=a
        for i in range(6):
            a=i*math.pi/3;cylinder("Wheel hub screw",(math.sin(a)*.059,sign*.042,math.cos(a)*.059),.003,.002,M["metal"],axis=(0,1,0),parent=p,vertices=12)
    p=parent("mast")
    if p:
        # Geometry centered on the mast body descriptor origin.
        box("Long rounded mast shell",(0,0,0),(.083,.085,1.36),M["shell"],.035,p)
        box("Rear mast spine",(-.045,0,0),(.022,.055,1.31),M["metal"],.008,p)
        box("Exposed linear rack",(.044,-.044,0),(.023,.012,1.29),M["black"],.003,p)
        for i in range(108):box("Lift rack tooth",(.053,-.044,-.638+i*.012),(.012,.017,.004),M["darkmetal"],.0008,p)
    p=parent("head")
    if p:
        box("Stereo rounded optical housing",(0,0,0),(.095,.185,.094),M["shell"],.041,p)
        box("Black stereo visor",(.051,0,.005),(.012,.158,.065),M["glass"],.027,p)
        for y in (-.050,.050):
            cylinder("Stereo lens bezel",(.060,y,.008),.014,.005,M["black"],axis=(1,0,0),parent=p)
            cylinder("Stereo lens",(.064,y,.008),.009,.003,M["lens"],axis=(1,0,0),parent=p)
        cylinder("Head swivel mount",(0,0,-.08),.025,.07,M["metal"],parent=p)
        box("AEC speaker grille",(-.054,0,-.012),(.013,.12,.040),M["darkmetal"],.005,p)
        for i in range(12):box("Speaker perforation",(-.062,-.052+i*.009,-.012),(.002,.002,.025),M["black"],.0005,p)
    lengths=[.085,.19,.080,.18,.065,.065,.035]
    radii=[.041,.041,.032,.036,.030,.026,.023]
    for side in ("left","right"):
        p=parent(side+"_shoulder")
        if p:
            box("Shoulder sliding carriage",(0,0,0),(.09,.08,.23),M["shell"],.03,p)
            box("Shoulder carriage backing",(-.052,0,0),(.025,.075,.21),M["metal"],.01,p)
        for i,(length,r) in enumerate(zip(lengths,radii),1):
            p=parent(f"{side}_link_{i}")
            if not p:continue
            cylinder("Satin white actuator shell",(0,0,-length*.50),r,length*.80,M["shell"],parent=p)
            cylinder("Actuator lower seal",(0,0,-length*.91),r*.89,.009,M["darkmetal"],parent=p)
            if i%2==0:
                cylinder("Pitch joint housing",(0,0,-.01),r*.95,r*2.15,M["metal"],axis=(0,1,0),parent=p)
                for sign in (-1,1):
                    cylinder("Pitch joint side cap",(0,sign*r*1.1,-.01),r*.72,.006,M["shell"],axis=(0,1,0),parent=p)
                    for a in (0,math.pi/2,math.pi,math.pi*1.5):
                        cylinder("Pitch cap screw",(math.cos(a)*r*.45,sign*r*1.14,-.01+math.sin(a)*r*.45),.0025,.002,M["darkmetal"],axis=(0,1,0),parent=p,vertices=12)
            else:
                for sign in (-1,1):box("Open articulation bracket",(0,sign*(r+.006),-.015),(.039,.008,.050),M["metal"],.009,p)
            if length>.10:
                tube("Visible flex cable",[(-r*.7,0,-.01),(-r*1.15,0,-length*.4),(-r*.8,0,-length*.9)],.0032,M["black"],p)
        p=parent(side+"_hand")
        if p:
            box("Compact rotary gripper palm",(0,0,0),(.079,.102,.047),M["darkmetal"],.018,p)
            box("Gripper white top plate",(.002,0,.029),(.078,.095,.012),M["shell"],.007,p)
            box("Green fingertip status accent",(.043,0,-.009),(.010,.070,.018),M["green"],.005,p)
            box("Wrist camera mount",(-.028,0,.044),(.028,.04,.045),M["shell"],.009,p)
            cylinder("Wrist camera optic",(-.013,0,.047),.010,.005,M["lens"],axis=(1,0,0),parent=p)
        for sign in (-1,1):
            p=parent(f"{side}_finger_{sign}")
            if p:
                box("Pincher finger body",(0,0,-.030),(.026,.019,.067),M["darkmetal"],.008,p)
                box("Pincher rubber contact pad",(0,-sign*.011,-.046),(.022,.006,.039),M["rubber"],.003,p)


def export_selected(objects,name):
    # Batch geometry by material within each physics body. Preserve named body
    # transforms while avoiding hundreds of draw calls for screws and tread.
    groups={}
    empties=[o for o in objects if o.type!="MESH"]
    for obj in objects:
        if obj.type!="MESH":continue
        groups.setdefault((obj.parent.name if obj.parent else "world",obj.active_material.name if obj.active_material else "none"),[]).append(obj)
    merged=[]
    for (body,mat),members in groups.items():
        bpy.ops.object.select_all(action="DESELECT")
        for obj in members:
            obj.select_set(True)
            bpy.context.view_layer.objects.active=obj
            for modifier in list(obj.modifiers):bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.context.view_layer.objects.active=members[0]
        if len(members)>1:bpy.ops.object.join()
        obj=bpy.context.object;obj.name=body+" visual "+mat;merged.append(obj)
    objects[:]=empties+merged
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:obj.select_set(True)
    bpy.context.view_layer.objects.active=next((o for o in objects if o.type=="MESH"),objects[0])
    bpy.ops.export_scene.gltf(filepath=str(OUT/name),export_format="GLB",use_selection=True,export_yup=False,export_apply=True,export_cameras=False,export_lights=False)


def setup_render():
    scene=bpy.context.scene
    scene.render.engine="CYCLES"
    scene.cycles.samples=48
    scene.cycles.use_denoising=True
    try:
        preferences=bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type="CUDA";preferences.get_devices()
        for device in preferences.devices:device.use=device.type=="CUDA"
        scene.cycles.device="GPU"
    except Exception:pass
    scene.world.color=(.3,.3,.3)
    scene.world.use_nodes=True
    scene.world.node_tree.nodes.get("Background").inputs["Color"].default_value=(.72,.82,.92,1)
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value=.35
    def light(name,loc,power,size,target):
        data=bpy.data.lights.new(name,"AREA");data.energy=power;data.shape="DISK";data.size=size
        obj=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(obj);obj.location=loc;obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()
    light("Window daylight",(-3.2,.05,2.3),700,2.6,(.5,.5,.5))
    light("Ceiling bounce",(0,.5,3.4),380,4.0,(0,0,0))
    light("Camera soft fill",(2,-3,2.6),160,3.0,(0,0,1))
    camera=bpy.data.cameras.new("Interior camera");obj=bpy.data.objects.new("Interior camera",camera);bpy.context.collection.objects.link(obj)
    obj.location=(4.1,-4.1,2.25);target=Vector((.15,.55,.85));obj.rotation_euler=(target-obj.location).to_track_quat("-Z","Y").to_euler();camera.lens=32
    scene.camera=obj;scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.view_settings.view_transform="AgX"
    scene.render.image_settings.file_format="PNG";scene.render.filepath=str(OUT/"reference-room-preview.png")


room()
add_texture(M["wood"],"oak_veneer_01")
add_texture(M["floor"],"linoleum_brown")
add_texture(M["blanket"],"rough_linen")
add_texture(M["curtain"],"rough_linen")
export_selected(room_objects,"room.glb")
descriptor_path=ROOT/"sim"/"reference_body_descriptors.json"
if descriptor_path.exists():
    robot(json.loads(descriptor_path.read_text(encoding="utf-8")))
    export_selected(robot_objects,"robot.glb")
setup_render()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"reference-scene.blend"))
if "--render" in sys.argv:
    bpy.ops.render.render(write_still=True)
print(json.dumps({"room_objects":len(room_objects),"robot_objects":len(robot_objects),"assets":str(OUT),"geometry_verification":"estimated from visual references; not vendor CAD"}))
