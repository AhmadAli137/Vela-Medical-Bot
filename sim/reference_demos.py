"""Shared, bounded control trajectories for additional reference-model demos.

These are actuator setpoints, never recorded body poses. Native and browser
engines check the model hash and measure actual forward-dynamics outcomes.
"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

from sim.reference_model import load_reference_model
from sim.reference_pickup import pickup_stages

LIBRARY_PATH = Path(__file__).with_name("reference_demo_trajectories.json")
DEMO_COMMANDS = {"bedside_demo", "greeting_demo", "phone_return_demo"}


def build_trajectories():
    model, data, metadata = load_reference_model()
    initial = data.qpos.copy()
    def pose(source=None, **changes):
        q = initial.copy() if source is None else source.copy()
        for name,value in changes.items():
            q[model.joint(name).qposadr[0]] = value
        return q
    def stage(name, q, duration, gate=None):
        result={"name":name,"target_qpos":q.tolist(),"duration_s":duration}
        if gate:
            result["gate_after"]=gate
        return result
    def wheels(q):
        travel=q[model.joint("base_x").qposadr[0]]
        yaw=q[model.joint("base_yaw").qposadr[0]]
        q[model.joint("left_wheel_joint").qposadr[0]]=(travel-.20*yaw)/.13
        q[model.joint("right_wheel_joint").qposadr[0]]=(travel+.20*yaw)/.13
        return q
    common={"rest_qpos_tolerance":.05,"robot_speed_tolerance":.05,"settle_dwell_s":.5}
    tucked=pose(left_joint_1=.20,right_joint_1=-.20,left_joint_2=-.70,right_joint_2=-.70,left_joint_4=-1.65,right_joint_4=-1.65)
    beside=wheels(pose(tucked,base_x=.74,base_y=.28,base_yaw=.25))
    bedside=[stage("clear_arms",tucked,2.),stage("approach_bedside",beside,4.),stage("pause_beside_bed",beside,2.),stage("return_base",tucked,4.),stage("rest_arms",initial,2.),stage("settle",initial,1.)]

    clear=pose(left_joint_1=.35,left_joint_2=-.8,left_joint_4=-.5)
    raised=pose(clear,left_lift=.12,left_joint_2=-2.1,left_joint_4=-.3)
    for finger in (-1,1):
        raised[model.joint(f"left_gripper_{finger}").qposadr[0]]=finger*.35
    greeting=[stage("clear_greeting",clear,2.),stage("raise_greeting",raised,3.)]
    for index,(bend,roll) in enumerate(((-.55,-.45),(.20,.45),(-.55,-.45),(.20,.45)),1):
        greeting.append(stage(f"wave_{index}",pose(raised,left_joint_6=bend,left_joint_7=roll),1.))
    greeting.extend([stage("center_wrist",raised,1.),stage("lower_greeting",clear,3.),stage("rest_arms",initial,2.),stage("settle",initial,1.)])

    pickup,errors=pickup_stages(model,initial)
    returned=[stage(p["name"],p["target_qpos"],p["duration_s"],"bilateral_contact" if p["name"]=="close" else "grasp_confirmed" if p["name"]=="hold" else None)for p in pickup]
    closed=pickup[4]["target_qpos"].copy()
    opened=closed.copy()
    for finger in (-1,1):
        opened[model.joint(f"left_gripper_{finger}").qposadr[0]]=finger*.60
    returned.extend([stage("lower_phone",closed,4.,"phone_supported"),stage("open_fingers",opened,1.5,"phone_settled"),stage("retreat_hand",pickup[2]["target_qpos"],3.),stage("clear_return",pickup[1]["target_qpos"],2.),stage("return_base",pickup[0]["target_qpos"],4.),stage("rest_arms",initial,2.),stage("settle",initial,2.)])
    commands={
        "bedside_demo":{"name":"Bedside approach","description":"Move through the clear lane near the foot of the bed, pause, then return to the starting pose.","stages":bedside,"outcomes":{**common,"base_goal_qpos":[.74,.28,.25],"base_goal_tolerance_m":.025,"yaw_tolerance_rad":.03,"minimum_base_excursion_m":.70}},
        "greeting_demo":{"name":"Arm greeting","description":"Raise the left arm, wave the wrist twice, then return to rest.","stages":greeting,"outcomes":{**common,"minimum_hand_height_m":1.50,"minimum_wave_range_rad":.50}},
        "phone_return_demo":{"name":"Pick up and put back","description":"Grip and lift the phone, lower it onto its original riser, open the fingers, then retreat and confirm the phone is settled.","stages":returned,"ik_errors":errors,"outcomes":{**common,"phone_target":[.63,-.72,.8135],"phone_xy_tolerance_m":.02,"phone_z_tolerance_m":.006,"phone_speed_tolerance_m_s":.03,"phone_angular_speed_tolerance_rad_s":.4,"hand_clearance_m":.10,"support_force_minimum_n":.05,"minimum_grasp_height_m":.15,"minimum_bilateral_hold_s":2.}},
    }
    for command in commands.values():
        command["duration_s"]=sum(item["duration_s"]for item in command["stages"])
    return {"schema_version":1,"model_hash":metadata["model_hash"],"nq":model.nq,"nu":model.nu,"actuated_q_indices":model.jnt_qposadr[model.actuator_trnid[:,0]].tolist(),"commands":commands,"hardware_model_verified":False,"authorizes_hardware":False,"notes":["Targets are position-actuator controls, not body pose playback","The base uses existing constrained planar sliders; wheel targets follow forward/yaw travel, without traction or balance validation","Free-space paths receive sampled collision checks; loaded finger targets are checked through actual contact dynamics","Completion requires measured outcomes and is revoked on fault"]}


def load_trajectories(model_hash):
    library=json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    if library["model_hash"]!=model_hash:
        raise ValueError("Demo trajectory model hash mismatch; regenerate trajectories")
    return library


def verify_demos(output="sim/outputs/reference_more_demos.json"):
    """Execute each demo and save actual outcomes; never replay pose samples."""
    from sim.reference_runtime import ReferenceSimulation
    results={}
    for command in sorted(DEMO_COMMANDS):
        simulation=ReferenceSimulation()
        initial=simulation.command(command)
        samples=[]
        for _ in range(int((initial["metrics"]["demo"]["duration_s"]+4.)/.5)):
            state=simulation.advance(.5)
            samples.append({"time":state["simulation_time"],"demo":state["metrics"]["demo"],"pickup":state["metrics"].get("pickup"),"contacts":state["metrics"]["contacts"]})
            if state["paused"] or state["metrics"]["demo"]["complete"]:
                break
        results[command]={"completed":state["metrics"]["demo"]["complete"],"paused":state["paused"],"stop_reason":state["metrics"]["stop_reason"],"physics_steps":state["metrics"]["physics_steps"],"final":state["metrics"]["demo"],"samples":samples}
    report={"passed":all(item["completed"] and not item["paused"] for item in results.values()),"model_hash":simulation.metadata["model_hash"],"results":results,"authorizes_hardware":False,"hardware_model_verified":False}
    destination=Path(output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    library=build_trajectories()
    LIBRARY_PATH.write_text(json.dumps(library,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"file":str(LIBRARY_PATH),"model_hash":library["model_hash"],"commands":{name:value["duration_s"]for name,value in library["commands"].items()}}))
    if args.verify:
        report=verify_demos()
        print(json.dumps({"passed":report["passed"],"outcomes":{name:item["final"] for name,item in report["results"].items()}},indent=2))
        raise SystemExit(0 if report["passed"] else 1)
