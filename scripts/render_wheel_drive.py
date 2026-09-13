"""Short native-rendered evidence of wheel-contact propulsion; no pose playback."""
import json
from pathlib import Path
import mujoco
import numpy as np
from PIL import Image
from sim.reference_visual_model import load_reference_visual_model
from sim.reference_drive import observe_drive


def main():
    model,data,metadata=load_reference_visual_model()
    frames=[]
    records=[]
    option=mujoco.MjvOption()
    option.geomgroup[2]=1;option.geomgroup[3]=0;option.geomgroup[4]=0
    option.sitegroup[:]=0
    robot_ids={model.body(spec['name']).id for spec in metadata['body_specs'] if spec.get('robot_body')}
    def step_checked():
        mujoco.mj_step(model,data)
        for contact in data.contact[:data.ncon]:
            a,b=int(contact.geom1),int(contact.geom2)
            names={model.geom(a).name,model.geom(b).name}
            if names in ({'floor','left_wheel_geom'},{'floor','right_wheel_geom'}):continue
            if (model.geom_bodyid[a] in robot_ids or model.geom_bodyid[b] in robot_ids) and contact.dist<-.0001:
                raise RuntimeError(f'Unexpected robot contact: {names}')
    # Settle under gravity, then drive a short unobstructed forward segment.
    for _ in range(250):step_checked()
    start=data.xpos[model.body('robot_base').id].copy()
    with mujoco.Renderer(model,height=480,width=768) as renderer:
        for frame in range(40):
            speed=min(2.,frame*.2) if frame<30 else max(0.,2.-(frame-29)*.2)
            for side in ('left','right'):
                data.ctrl[model.actuator(f'ctrl_{side}_wheel_joint').id]=speed
            for _ in range(25):step_checked()
            renderer.update_scene(data,camera='overview',scene_option=option)
            frames.append(Image.fromarray(renderer.render()).convert('RGB'))
            records.append(observe_drive(model,data))
    delta=data.xpos[model.body('robot_base').id]-start
    assert delta[0]>.25 and abs(delta[1])<.002
    out=Path('artifacts/wheel-driven-forward.gif')
    frames[0].save(out,save_all=True,append_images=frames[1:],duration=100,loop=0)
    Path('artifacts/wheel-driven-forward.json').write_text(json.dumps({
        'model_hash':metadata['model_hash'],'visual_hash':metadata['visual_hash'],
        'renderer':'native MuJoCo','physics_steps':1250,'simulation_seconds':2.5,
        'playback':'half speed, 10 fps','displacement_m':delta.tolist(),'samples':records,
        'actuator_controls':'two wheel velocity motors only after initial arm holds',
        'pose_teleports':0,'unintended_robot_contacts':0,'upright_constraint':True,'balance_validated':False
    },indent=2),encoding='utf-8')
    print(json.dumps({'image':str(out),'displacement_m':delta.tolist()}))


if __name__=='__main__':main()
