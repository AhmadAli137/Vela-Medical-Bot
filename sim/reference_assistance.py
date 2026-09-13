"""Contact-driven assistance fixtures; no robot/object pose attachment.

These model an accessible tray and a passive mechanical blinds linkage.
They do not model patient handoffs, feeding, perception, or balancing.
"""
from __future__ import annotations

import math
import mujoco
import numpy as np

from sim.reference_model import DELIVERY_TARGETS, MEAL_POSITION, PHONE_POSITION
from sim.reference_pickup import GRASP_ROTATION, solve_pose

ASSISTANCE_COMMANDS = {"deliver_phone_demo", "deliver_meal_demo", "blinds_demo"}
PATIENT_HAND_REFERENCE = [1.13, 1.58, 1.12]


def build_assistance_commands(model, initial):
    def pose(source=None, **changes):
        q = initial.copy() if source is None else source.copy()
        for name, value in changes.items():
            q[model.joint(name).qposadr[0]] = value
        return q

    def wheels(q):
        return q

    def stage(name, q, seconds, gate=None):
        result = {"name": name, "target_qpos": q.tolist(), "duration_s": seconds}
        if gate:
            result["gate_after"] = gate
        return result

    common = {"rest_qpos_tolerance": .05, "robot_speed_tolerance": .05, "settle_dwell_s": .5}
    commands = {}
    for command, body, source in (("deliver_phone_demo", "phone", PHONE_POSITION), ("deliver_meal_demo", "meal_box", MEAL_POSITION)):
        target = DELIVERY_TARGETS[body]
        pickup_y = source[1]+.72
        destination_y = target[1]+.72
        park = pose(right_joint_1=0.,right_joint_2=-.8,right_lift=.20)
        for finger in (-1, 1):
            park[model.joint(f"left_gripper_{finger}").qposadr[0]] = finger*.60
        drive = wheels(pose(park, base_x=.78, base_y=pickup_y))
        errors = {}
        hover, errors["hover"] = solve_pose(model, drive, [source[0], source[1], .96], base_y=pickup_y)
        grasp, errors["grasp"] = solve_pose(model, hover, [source[0], source[1], source[2]-.0005], base_y=pickup_y)
        closed = grasp.copy()
        for finger in (-1, 1):
            closed[model.joint(f"left_gripper_{finger}").qposadr[0]] = -finger*.25
        carry, errors["carry"] = solve_pose(model, closed, [source[0], source[1], 1.18], base_y=pickup_y, lift=.15)
        clear_table = wheels(pose(carry, base_y=1.10))
        bedside = wheels(pose(carry, base_x=1., base_y=destination_y))
        corridor = pose(carry,base_x=.78,base_y=destination_y)
        at_tray, errors["tray_hover"] = solve_pose(model, bedside, [target[0],target[1],1.18], base_x=1., base_y=destination_y, lift=.15)
        placement_goal=list(target)
        if body == "phone":
            # The thin phone can sit slightly high between compliant pads
            # after turning. A small physical press loads its support before
            # fingers open; the force/outcome gates remain unchanged.
            placement_goal[2]-=.0015
        place, errors["place"] = solve_pose(model, at_tray, placement_goal, base_x=1., base_y=destination_y, lift=.15)
        opened = place.copy()
        for finger in (-1, 1):
            opened[model.joint(f"left_gripper_{finger}").qposadr[0]] = finger*.60
        retreat = at_tray.copy()
        for finger in (-1, 1):
            retreat[model.joint(f"left_gripper_{finger}").qposadr[0]] = finger*.60
        release_clear, errors["release_clear"] = solve_pose(model,opened,[target[0],target[1],target[2]+.06],base_x=1.,base_y=destination_y,lift=.15)
        withdrawn = wheels(pose(retreat, base_x=.78, base_y=1.10))
        return_lane = wheels(pose(park, base_x=.78, base_y=1.10))
        back_from_tray=pose(retreat,base_x=.78,base_y=destination_y)
        stages = [stage("park",park,2),stage("approach_source",drive,4),stage("object_hover",hover,3),stage("object_descend",grasp,3),stage("grip_object",closed,1.5,"assist_bilateral"),stage("raise_object",carry,4),stage("confirm_grasp",carry,2,"assist_grasped"),stage("clear_work_table",clear_table,5),stage("navigate_bedside",corridor,5),stage("navigate_bedside",bedside,3),stage("tray_hover",at_tray,2),stage("lower_to_tray",place,4,"assist_supported"),stage("release_on_tray",opened,2),stage("clear_open_fingers",release_clear,1.5,"assist_released"),stage("retract_from_tray",retreat,2.5),stage("leave_bedside",back_from_tray,3),stage("leave_bedside",withdrawn,5),stage("fold_empty_arm",return_lane,3),stage("return_start",park,5),stage("rest_arms",initial,2),stage("settle",initial,2)]
        commands[command] = {"name": "Deliver phone to bedside" if body=="phone" else "Deliver meal container", "description": "Carry a real free body to the accessible bedside tray, confirm support, release, and return.", "object_name":body, "source_position":source, "support_geom":"phone_delivery_riser" if body=="phone" else "meal_delivery_riser", "intentional_contacts":[[f"{body}_geom",f"left_finger_{finger}_geom"]for finger in (-1,1)], "stages":stages, "ik_errors":errors, "outcomes":{**common,"object_target":target,"object_xy_tolerance_m":.025,"object_z_tolerance_m":.008,"object_speed_tolerance_m_s":.04,"object_angular_speed_tolerance_rad_s":.4,"support_force_minimum_n":.05,"minimum_grasp_height_m":.15,"minimum_bilateral_hold_s":2.,"hand_clearance_m":.12,"patient_hand_reference":PATIENT_HAND_REFERENCE,"maximum_patient_reach_m":.55}}

    # A downward press operates the passive slide; equality constraints model
    # the handle-to-slat transmission, never an attachment to the robot.
    folded = pose(left_joint_1=.25,right_joint_1=-.25,left_joint_2=-.8,right_joint_2=-.8,left_joint_4=-.5,right_joint_4=-.5)
    west = wheels(pose(folded,base_x=-2.07,base_y=0.))
    facing = wheels(pose(west,base_yaw=math.pi))
    for index, value in enumerate([0.,-.30,0.,-1.50,0.,-.15,0.],1):
        facing[model.joint(f"left_joint_{index}").qposadr[0]]=value
    rotation = np.diag([-1.,-1.,1.]) @ GRASP_ROTATION
    above, above_error = solve_pose(model,facing,[-3.14,-.70,1.275],rotation=rotation,base_x=-2.07,base_y=0.,lift=.20)
    over_handle = pose(above,base_y=.30)
    pressed, press_error = solve_pose(model,over_handle,[-3.14,-.40,1.052],rotation=rotation,base_x=-2.07,base_y=.30,lift=.20)
    stages = [stage("clear_arms",folded,2),stage("navigate_window",west,7),stage("face_blinds",facing,4),stage("raise_beside_control",above,4),stage("align_above_control",over_handle,3),stage("press_blinds_control",pressed,6,"blinds_open"),stage("withdraw_control",over_handle,3),stage("clear_return_control",above,3),stage("fold_at_window",facing,3),stage("turn_from_window",west,4),stage("return_from_window",folded,7),stage("rest_arms",initial,2),stage("settle",initial,2)]
    commands["blinds_demo"] = {"name":"Open window blinds", "description":"Press a passive sliding control through hand contact; its modeled mechanical linkage rotates the slats.","intentional_contacts":[["blinds_handle_geom",f"left_finger_{finger}_geom"]for finger in (-1,1)]+[["blinds_handle_geom","left_hand_geom"]],"stages":stages,"ik_errors":{"above":above_error,"press":press_error},"outcomes":{**common,"minimum_handle_travel_m":.15,"minimum_slat_angle_rad":1.10,"minimum_control_contact_force_n":.05}}
    for definition in commands.values():
        definition["duration_s"] = sum(stage["duration_s"] for stage in definition["stages"])
    return commands


def contact_forces(sim, object_name):
    forces = {f"left_finger_{finger}":0. for finger in (-1,1)}
    if object_name=="blinds_handle":
        forces["left_hand"]=0.
    support = 0.
    for index, contact in enumerate(sim.data.contact[:sim.data.ncon]):
        names = {sim.model.geom(int(contact.geom1)).name,sim.model.geom(int(contact.geom2)).name}
        if f"{object_name}_geom" not in names:
            continue
        wrench = np.zeros(6)
        mujoco.mj_contactForce(sim.model,sim.data,index,wrench)
        force = max(0.,float(wrench[0]))
        for finger in forces:
            if f"{finger}_geom" in names:
                forces[finger] += force
        if sim.demo_definition.get("support_geom") in names:
            support += force
    return forces, support


def observe_assistance(sim):
    definition = sim.demo_definition
    measured = sim.demo["measurements"]
    thresholds = definition["outcomes"]
    if sim.mode == "blinds_demo":
        travel = float(sim.data.qpos[sim.model.joint("blinds_slide").qposadr[0]])
        angles = [float(sim.data.qpos[sim.model.joint(f"blinds_tilt_{i:02}").qposadr[0]])for i in range(16)]
        forces,_ = contact_forces(sim,"blinds_handle")
        measured.update(handle_travel_m=travel,minimum_slat_angle_rad=min(angles),maximum_slat_angle_rad=max(angles),control_contact_force_n=sum(forces.values()))
        measured["maximum_control_contact_force_n"] = max(measured.get("maximum_control_contact_force_n",0.),sum(forces.values()))
        return {"handle_moved":travel>=thresholds["minimum_handle_travel_m"],"slats_open":min(angles)>=thresholds["minimum_slat_angle_rad"],"physical_control_contact":measured["maximum_control_contact_force_n"]>=thresholds["minimum_control_contact_force_n"]}
    body = definition["object_name"]
    position = sim.data.xpos[sim.model.body(body).id]
    address = sim.model.joint(f"{body}_free").dofadr[0]
    forces,support = contact_forces(sim,body)
    bilateral = all(force>.01 for force in forces.values())
    target = np.asarray(thresholds["object_target"])
    height_gain = float(position[2]-definition["source_position"][2])
    measured.update(object_name=body,object_position=position.tolist(),object_height_gain_m=height_gain,object_xy_error_m=float(np.linalg.norm(position[:2]-target[:2])),object_z_error_m=abs(float(position[2]-target[2])),object_speed_m_s=float(np.linalg.norm(sim.data.qvel[address:address+3])),object_angular_speed_rad_s=float(np.linalg.norm(sim.data.qvel[address+3:address+6])),support_force_n=support,bilateral_contact=bilateral,fingers_clear=not any(force>.01 for force in forces.values()),hand_clearance_m=float(np.linalg.norm(sim.data.site_xpos[sim.model.site("left_grasp_center").id]-position)),patient_hand_distance_m=float(np.linalg.norm(position-np.asarray(thresholds["patient_hand_reference"]))))
    if bilateral and height_gain>=thresholds["minimum_grasp_height_m"]:
        measured["grasp_hold_s"] = measured.get("grasp_hold_s",0.)+sim.model.opt.timestep
    else:
        measured["grasp_hold_s"] = 0.
    measured["ever_grasped"] = bool(measured.get("ever_grasped",False) or measured["grasp_hold_s"]>=thresholds["minimum_bilateral_hold_s"])
    supported = measured["object_xy_error_m"]<=thresholds["object_xy_tolerance_m"] and measured["object_z_error_m"]<=thresholds["object_z_tolerance_m"] and measured["object_speed_m_s"]<=thresholds["object_speed_tolerance_m_s"] and measured["object_angular_speed_rad_s"]<=thresholds["object_angular_speed_tolerance_rad_s"] and support>thresholds["support_force_minimum_n"]
    measured["supported_on_tray"] = supported
    stage = sim.stages[sim.stage_index].get("action_phase",sim.demo["stage"])
    if stage in {"raise_object","confirm_grasp","clear_work_table","navigate_bedside","tray_hover","lower_to_tray"} and height_gain>.02 and not bilateral:
        sim._stop_demo("Assistance stopped: bilateral object contact lost during transport")
    return {"verified_grasp":measured["ever_grasped"],"placed_on_tray":supported,"fingers_clear":measured["fingers_clear"],"hand_retracted":measured["hand_clearance_m"]>=thresholds["hand_clearance_m"],"within_modeled_patient_reach":measured["patient_hand_distance_m"]<=thresholds["maximum_patient_reach_m"]}


def assistance_gate(sim, gate):
    measured = sim.demo["measurements"]
    if gate=="assist_bilateral":
        return measured.get("bilateral_contact",False)
    if gate=="assist_grasped":
        return measured.get("ever_grasped",False) and measured.get("bilateral_contact",False)
    if gate=="assist_supported":
        return measured.get("supported_on_tray",False) and measured.get("bilateral_contact",False)
    if gate=="assist_released":
        return measured.get("supported_on_tray",False) and measured.get("fingers_clear",False)
    if gate=="blinds_open":
        return all(sim.demo["checks"].get(key,False) for key in ("handle_moved","slats_open","physical_control_contact"))
    raise ValueError(f"Unknown assistance gate: {gate}")
