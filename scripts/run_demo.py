"""Run the three signature software workflows against an isolated real API app."""
import json
from pathlib import Path
from uuid import uuid4
from fastapi.testclient import TestClient
from services.app import create_app


def run(output="artifacts/demo-report.json"):
    directory = Path(".cache") / ("demo-"+uuid4().hex[:8])
    directory.mkdir(parents=True,exist_ok=True)
    app = create_app(directory/"demo.sqlite3")
    results = {"mode":"synthetic", "physical_robot_actions":0, "live_hospital_messages":0, "workflows":[]}
    with TestClient(app) as client:
        def post(path,payload=None):
            response = client.post("/api"+path,json=payload or {})
            response.raise_for_status()
            return response.json()
        def role(name):
            post("/session",{"role":name})
        role("patient")
        request = post("/requests",{"text":"Can you bring my phone closer?"})
        role("staff")
        identifier = request["task_id"]
        post(f"/tasks/{identifier}/approve")
        post(f"/tasks/{identifier}/validate")
        task = post(f"/tasks/{identifier}/execute")
        assert task["status"] == "completed"
        results["workflows"].append({"name":"phone_retrieval", "task":task})
        task = post("/tasks/plan",{"goal":"Prepare the room for physio","template":"physio_ready"})
        identifier = task["id"]
        post(f"/tasks/{identifier}/approve")
        post(f"/tasks/{identifier}/validate")
        task = post(f"/tasks/{identifier}/execute")
        assert task["status"] == "completed"
        results["workflows"].append({"name":"physio_preparation","task":task})
        role("operator")
        post("/demo/scenario",{"scenario":"reset","seed":31})
        post("/demo/scenario",{"scenario":"uncertain_phone"})
        role("staff")
        task = post("/tasks/plan",{"goal":"Bring my phone closer"})
        identifier = task["id"]
        post(f"/tasks/{identifier}/approve")
        post(f"/tasks/{identifier}/validate")
        blocked = post(f"/tasks/{identifier}/execute")
        assert blocked["status"] == "blocked"
        role("operator")
        session = post("/teleop/sessions",{"task_id":identifier,"reason":"Synthetic low-confidence target","consent":True,"environment":"mock"})
        sid = session["id"]
        post(f"/teleop/sessions/{sid}/demo-correction")
        session = post(f"/teleop/sessions/{sid}/complete",{"success":True,"notes":"Synthetic point-action corrective fixture, no robot or camera capture"})
        assert session["frame_count"] == 12 and session["privacy_status"] == "quarantined"
        results["workflows"].append({"name":"stop_takeover_record","blocked_task":blocked,"episode":session})
        urgent = post("/requests",{"text":"My chest hurts"})
        assert urgent["route"] == "D" and not urgent["routing"]["delivered_to_staff"]
        results["clinical_escalation"] = urgent
        results["audit_chain_valid"] = client.get("/api/audit").json()["chain_valid"]
    path = Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(results,indent=2),encoding="utf-8")
    return {"report":str(path),"workflows_passed":3,"clinical_route":"D","audit_chain_valid":results["audit_chain_valid"],"real_robot_actions":0}


if __name__ == "__main__":
    print(json.dumps(run(),indent=2))

