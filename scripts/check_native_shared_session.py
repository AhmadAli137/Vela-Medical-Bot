"""Check the live local API against native FK, without a second physics clock."""
from __future__ import annotations
import json
from pathlib import Path
import time
import numpy as np

from sim.reference_visual_model import load_reference_visual_model
from sim.reference_viewer_client import ReferenceViewerClient, apply_reference_frame


def main():
    model,data,metadata=load_reference_visual_model()
    client=ReferenceViewerClient("http://127.0.0.1:8000")
    client.command("reset")
    client.command("joint_demo")
    samples=[]
    try:
        for _ in range(20):
            frame=client.frame()
            state=apply_reference_frame(model,data,metadata,frame)
            errors=[]
            for name,pose in state["bodies"].items():
                ident=model.body(name).id
                errors.append(float(np.max(np.abs(data.xpos[ident]-pose["position"]))))
                np.testing.assert_allclose(data.xquat[ident],pose["quaternion"],atol=1e-12,rtol=0)
            for name,pose in state["cameras"].items():
                ident=model.camera(name).id
                np.testing.assert_allclose(data.cam_xpos[ident],pose["position"],atol=1e-12,rtol=0)
                np.testing.assert_allclose(data.cam_xmat[ident],pose["rotation"],atol=1e-12,rtol=0)
            assert max(errors)<1e-12
            assert data.time==state["simulation_time"]
            samples.append({"time":data.time,"max_body_position_error_m":max(errors)})
            time.sleep(.1)
        client.command("pause")
        first=client.frame();time.sleep(.25);second=client.frame()
        assert first==second,"Paused local/native session drifted"
        assert samples[-1]["time"]>samples[0]["time"]+.5
        report={"passed":True,"model_hash":metadata["model_hash"],"visual_hash":metadata["visual_hash"],"bodies":len(state["bodies"]),"cameras":len(state["cameras"]),"samples":samples,"pause_froze_shared_state":True,"native_integration_steps":0}
        Path("artifacts/native-shared-session.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(json.dumps(report))
    finally:
        client.command("reset")


if __name__=="__main__":
    main()
