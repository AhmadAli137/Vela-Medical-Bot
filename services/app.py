from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from integrations.hospital import MockHospitalAdapter
from robot.capabilities import manifest
from robot.mock import MockBracketBot
from services.planner import build_plan
from services.router import triage
from services.safety import POLICY_VERSION, evaluate
from services.store import Store, digest, now
from services.world import TEMPLATES, desired_diff, get_object, seed_room, snapshot, temporal_diff
from shared.models import PlanInput, RequestInput, StrictModel

ROOT = Path(__file__).resolve().parents[1]


class SessionInput(StrictModel):
    role: str
    token: str | None = None


class BenchmarkInput(StrictModel):
    episodes: int = Field(default=12,ge=1,le=100)
    seed: int = Field(default=7,ge=0)


class PrivacyInput(StrictModel):
    camera_enabled: bool = False
    microphone_enabled: bool = False


class StopInput(StrictModel):
    engaged: bool


class ExecuteInput(StrictModel):
    target: str = "mock"


class TeleopInput(StrictModel):
    task_id: str
    reason: str = Field(min_length=1,max_length=500)
    consent: bool = False
    environment: str = "mock"


class CompleteInput(StrictModel):
    success: bool
    notes: str = Field(default="",max_length=1000)
    failure_category: str | None = None


class ScenarioInput(StrictModel):
    scenario: str
    seed: int = Field(default=7,ge=0)


class ObjectPolicyInput(StrictModel):
    policy: str


class ReferenceControlInput(StrictModel):
    command: Literal["joint_demo", "reach_demo", "pickup_demo", "release_phone", "lift_demo", "bedside_demo", "greeting_demo", "phone_return_demo", "deliver_phone_demo", "deliver_meal_demo", "blinds_demo", "pause", "pause_for_tracking", "reset"]


def create_app(db_path=None, demo=None):
    demo = os.getenv("VELA_DEMO_MODE", "1") == "1" if demo is None else demo
    app = FastAPI(title="Vela Room Agent",version="0.1.0",description="Synthetic non-clinical room operations research prototype; no hardware or hospital connectivity")
    store = Store(db_path or os.getenv("VELA_DB", str(ROOT/"runtime"/"vela.sqlite3")))
    app.state.store = store
    app.state.execution_lock = threading.RLock()
    app.state.sessions = {}
    hospital = MockHospitalAdapter()
    mock = MockBracketBot()
    if not store.list("room"):
        room = seed_room()
        store.put("room",room["id"],room)
        store.put("snapshot",f'{room["id"]}/1',room)
        store.put("robot","mock-bracketbot",{"id":"mock-bracketbot","name":"Bracket Bot · software twin","online":True,"health":"ok","battery":None,"localization":"synthetic fixture","hardware_revision":"unknown","mode":"mock","estop":False,"watchdog_ok":True,"manipulation_paused":False,"arms":{"left":"synthetic idle","right":"synthetic idle"},"teleop_available":"software workflow only; Quest bridge unconfigured","policy_version":POLICY_VERSION})
        store.event("demo_initialized","system",{"source":"synthetic fixtures"})

    def learning():
        from ml.pipeline import LearningPipeline
        if not hasattr(app.state,"learning"):
            directory = ROOT/"runtime"/"learning" if db_path is None else Path(str(db_path)).parent/"learning"
            app.state.learning = LearningPipeline(directory)
        return app.state.learning

    def research():
        from services.evidence import get_research
        return get_research()

    @app.middleware("http")
    async def boundary(request, call_next):
        # Local role switching is expressly limited to loopback synthetic mode.
        host = request.client.host if request.client else "unknown"
        if demo and host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            return JSONResponse({"detail":"Demo mode is loopback only"},status_code=403)
        origin = request.headers.get("origin")
        allowed = {"http://localhost:5173","http://127.0.0.1:5173","http://localhost:8000","http://127.0.0.1:8000"} if demo else {os.getenv("VELA_PUBLIC_ORIGIN", "https://invalid.local")}
        if request.method not in ("GET","HEAD","OPTIONS") and origin and origin not in allowed:
            return JSONResponse({"detail":"Untrusted request origin"},status_code=403)
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 2_000_000:
            return JSONResponse({"detail":"Request body too large"},status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self)"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' blob:; frame-ancestors 'none'; base-uri 'self'"
        if request.url.path in ("/docs","/redoc"):
            # Only the documentation renderer loads its standard CDN assets.
            # The operational application retains a self-only content policy.
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        if not demo:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path.startswith("/api") and request.url.path != "/api/health":
            access_identity = app.state.sessions.get(request.cookies.get("vela_session", ""),{})
            store.event("api_access",access_identity.get("id","anonymous"),{"method":request.method,"path":request.url.path,"status":response.status_code,"role":access_identity.get("role")})
        return response

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({"detail":"Record not found"},status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, error):
        return JSONResponse({"detail":str(error)},status_code=409)

    def auth(request: Request):
        token = request.cookies.get("vela_session", "")
        session = app.state.sessions.get(token)
        if not session or session["expires"] < time.time():
            raise HTTPException(401,"Sign in to the local demo")
        return session

    def role(*roles):
        def check(user=Depends(auth)):
            if user["role"] not in roles:
                raise HTTPException(403,"Role is not permitted to perform this action")
            return user
        return check

    def own_task(identifier,user):
        task = store.get("task",identifier)
        if user["role"] == "researcher":
            raise HTTPException(403,"Research role cannot access operational tasks")
        if user["role"] == "patient" and task.get("owner") != user["id"]:
            raise HTTPException(403,"Task is outside this bedside session")
        return task

    def own_episode(identifier,user):
        episode = learning().get_session(identifier)
        if user["role"] != "admin" and episode.get("operator_id") != user["id"]:
            raise HTTPException(403,"Recording belongs to another operator session")
        return episode

    def release_takeover(task,reason):
        identifier = task.get("active_session_id")
        if not identifier:
            return
        episode = learning().get_session(identifier)
        if episode["status"] == "recording":
            learning().stop_session(identifier)
        robot = store.get("robot","mock-bracketbot")
        if robot.get("active_session_id") == identifier:
            robot["active_session_id"] = None
            store.put("robot",robot["id"],robot)
        task["active_session_id"] = None
        store.event("software_takeover_released","system",{"session_id":identifier,"reason":reason})

    def persist_room(room,actor):
        store.put("room",room["id"],room)
        store.put("snapshot",f'{room["id"]}/{room["version"]}',room)
        store.event("room_snapshot",actor,{"room_id":room["id"],"version":room["version"],"hash":digest(room)})

    def new_plan(payload,user):
        room = store.get("room",payload["room_id"])
        task = build_plan(payload,room)
        task["owner"] = user["id"]
        store.put("task",task["id"],task)
        store.event("task_planned",user["role"],{"task_id":task["id"],"plan_hash":task["plan_hash"]})
        return task

    api = APIRouter(prefix="/api")

    @api.get("/health")
    def health():
        return {"status":"ok","mode":"mock","hardware_execution":False,"cloud_models_enabled":os.getenv("VELA_ENABLE_CLOUD_MODELS") == "1"}

    @api.post("/session")
    def session(payload: SessionInput,response: Response):
        if payload.role not in ("patient","staff","operator","researcher","admin"):
            raise HTTPException(400,"Unknown role")
        if not demo:
            expected = os.getenv("VELA_" + payload.role.upper() + "_TOKEN")
            if not expected or not payload.token or not hmac.compare_digest(expected,payload.token):
                raise HTTPException(401,"Invalid credentials")
        token = secrets.token_urlsafe(32)
        identity = {"id":str(uuid4()),"role":payload.role,"room_id":"room-417","expires":time.time()+3600}
        app.state.sessions[token] = identity
        response.set_cookie("vela_session",token,httponly=True,secure=not demo,samesite="strict",max_age=3600)
        store.event("session_created",payload.role,{"demo":demo})
        return {"role":payload.role,"mode":"mock","demo_role_switching":demo}

    @api.delete("/session")
    def logout(request:Request,response:Response):
        app.state.sessions.pop(request.cookies.get("vela_session", ""),None)
        response.delete_cookie("vela_session")
        return {"signed_out":True}

    @api.get("/bootstrap")
    def bootstrap(user=Depends(auth)):
        tasks = store.list("task")
        requests = store.list("request")
        room = store.get("room","room-417")
        if user["role"] == "patient":
            tasks = [t for t in tasks if t.get("owner") == user["id"]]
            requests = [r for r in requests if r.get("owner") == user["id"]]
        if user["role"] == "researcher":
            tasks, requests = [], []
        completed = [t for t in tasks if t["status"] == "completed"]
        data = {"mode":"mock","role":user["role"],"room":room,"tasks":tasks,"requests":requests,"robots":store.list("robot"),"metrics":{"task_count":len(tasks),"completed":len(completed),"blocked":sum(t["status"] == "blocked" for t in tasks),"escalations":sum(r["route"] == "D" for r in requests),"completion_rate":len(completed)/len(tasks) if tasks else None,"staff_minutes_saved":None,"patient_autonomy_gain":None,"physical_grasp_success":None,"source":"observed software workflow events only"},"templates":list(TEMPLATES),"privacy":room["privacy"],"policy_version":POLICY_VERSION}
        if user["role"] != "patient":
            data.update({"capabilities":manifest(),"skills":learning().list_skills(),"sessions":learning().list_sessions(),"policies":learning().list_policies(),"events":[] if user["role"] == "researcher" else store.events(40),"integrations":{"hospital":"mock","bracketbot":"unconfigured","quest":"unconfigured","models":"cloud opt-in" if os.getenv("VELA_ENABLE_CLOUD_MODELS") == "1" else "deterministic fixture"}})
            evidence = research()
            data.update({"opportunities":evidence.get("opportunities",[]),"images":evidence.get("images",[]),"dataset_summary":evidence.get("dataset_summary",{})})
        return data

    @api.post("/requests/triage")
    @api.post("/patient/requests/triage")
    def triage_request(payload:RequestInput,user=Depends(auth)):
        return triage(payload.text)

    @api.post("/requests")
    def patient_request(payload:RequestInput,user=Depends(auth)):
        store.get("room",payload.room_id)
        if user["role"] == "patient" and user["room_id"] != payload.room_id:
            raise HTTPException(403,"Room outside bedside session")
        result = {"id":str(uuid4()),**triage(payload.text),"text":payload.text,"room_id":payload.room_id,"owner":user["id"],"created_at":now(),"mode":"mock"}
        if result["route"] == "A":
            answer = hospital.information(payload.text,payload.room_id)
            result.update({"message":answer["answer"],"source":answer["source"],"information":answer,"status":"answered_from_fixture"})
        elif result["route"] == "B":
            try:
                task = new_plan({"room_id":payload.room_id,"goal":payload.text},user)
                result.update({"task_id":task["id"],"message":"Your request is ready for review in this demo. No physical item has moved.","status":"awaiting_approval"})
            except ValueError:
                result.update({"route":"C","reason":"physical_target_unresolved","routing":hospital.route_request("C",payload.room_id,result["id"]),"message":"This request needs staff assistance. It is queued in the demo only; no staff were contacted.","status":"queued_in_mock_adapter"})
        else:
            routing = hospital.route_request(result["route"],payload.room_id,result["id"])
            result.update({"routing":routing,"status":routing["status"],"message":"This demo cannot contact staff. Use your hospital call button or speak to staff directly." if result["route"] == "D" else "Your request is in the demo room-services queue. No real staff were contacted."})
        store.put("request",result["id"],result)
        store.event("request_routed",user["role"],{"request_id":result["id"],"route":result["route"],"clinical_locked":result.get("locked",False),"live_delivery":False})
        return result

    @api.get("/rooms/{room_id}/state")
    def room_state(room_id,user=Depends(auth)):
        if user["role"] == "patient" and room_id != user["room_id"]:
            raise HTTPException(403,"Room outside session")
        return store.get("room",room_id)

    @api.post("/rooms/{room_id}/scan")
    @api.post("/rooms/{room_id}/snapshot")
    def scan(room_id,user=Depends(role("staff","operator","admin"))):
        with app.state.execution_lock, store.transaction():
            room = snapshot(store.get("room",room_id))
            persist_room(room,user["role"])
            return room

    @api.get("/rooms/{room_id}/diff")
    def diff(room_id,template="physio_ready",from_version:int|None=None,to_version:int|None=None,user=Depends(role("staff","operator","researcher","admin"))):
        room = store.get("room",room_id)
        if from_version is not None:
            return temporal_diff(store.get("snapshot",f"{room_id}/{from_version}"),store.get("snapshot",f"{room_id}/{to_version or room['version']}"))
        return desired_diff(room,template)

    @api.get("/rooms/{room_id}/history")
    def history(room_id,user=Depends(role("staff","operator","researcher","admin"))):
        return [s for s in store.list("snapshot") if s["id"] == room_id]

    @api.post("/rooms/{room_id}/objects/{object_id}/policy")
    def object_policy(room_id,object_id,payload:ObjectPolicyInput,user=Depends(role("staff","admin"))):
        # The UI may narrow authority only. Vendor/clinical policies cannot be relaxed here.
        if payload.policy not in ("UNKNOWN_PROHIBITED","CLINICAL_PROHIBITED","TELEOP_ONLY"):
            raise HTTPException(403,"This interface may only restrict object permission")
        with app.state.execution_lock, store.transaction():
            room = snapshot(store.get("room",room_id))
            obj = get_object(room,object_id)
            if obj is None:
                raise KeyError(object_id)
            if obj["policy"] in ("CLINICAL_PROHIBITED","UNKNOWN_PROHIBITED"):
                raise HTTPException(403,"Prohibited object policy cannot be changed through this interface")
            obj["policy"] = payload.policy
            persist_room(room,user["role"])
            return room

    @api.post("/tasks/plan")
    def plan(payload:PlanInput,user=Depends(role("staff","operator","admin"))):
        return new_plan(payload.model_dump(),user)

    @api.get("/tasks/{task_id}")
    def get_task(task_id,user=Depends(auth)):
        return own_task(task_id,user)

    @api.post("/tasks/{task_id}/approve")
    def approve(task_id,user=Depends(role("staff","admin"))):
        with app.state.execution_lock, store.transaction():
            task = store.get("task",task_id)
            if task["status"] not in ("planned","validated","approved","blocked"):
                raise ValueError("Task cannot be approved in its current state")
            room = store.get("room",task["room_id"])
            if task["room_hash"] != digest(room):
                raise ValueError("Room changed; scan and create a new plan")
            if task["critique"]["verdict"] != "accept_candidate":
                raise ValueError("Critic veto cannot be overridden")
            task.update(approval_hash=task["plan_hash"],approved_by=user["id"],status="approved",updated_at=now())
            store.put("task",task_id,task)
            store.event("task_approved",user["role"],{"task_id":task_id,"plan_hash":task["plan_hash"]})
            return task

    @api.post("/tasks/{task_id}/validate")
    def validate(task_id,user=Depends(role("staff","operator","admin"))):
        from sim.engine import validate_plan
        task = store.get("task",task_id)
        if task["status"] not in ("planned","approved","validated","blocked"):
            raise ValueError("Task cannot be validated in its current state")
        room = store.get("room",task["room_id"])
        if task["room_hash"] != digest(room):
            raise ValueError("Room changed; replan before validation")
        report = validate_plan(task["proposal"],room)
        report.update(plan_hash=task["plan_hash"],room_hash=digest(room),authorizes_hardware=False)
        with app.state.execution_lock, store.transaction():
            current = store.get("task",task_id)
            if current["status"] not in ("planned","approved","validated","blocked"):
                raise ValueError("Task state changed during validation")
            current.update(simulation=report,status="validated" if report["passed"] else "blocked",updated_at=now())
            current["safety"] = evaluate(current,store.get("room",task["room_id"]),store.get("robot","mock-bracketbot"),report)
            store.put("task",task_id,current)
            store.event("simulation_validated",user["role"],{"task_id":task_id,"passed":report["passed"],"hardware":False})
            return current

    @api.post("/tasks/{task_id}/execute")
    def execute(task_id,payload:ExecuteInput=ExecuteInput(),user=Depends(role("staff","operator","admin"))):
        with app.state.execution_lock, store.transaction():
            task = store.get("task",task_id)
            robot = store.get("robot","mock-bracketbot")
            if robot.get("active_session_id"):
                raise ValueError("Autonomy is paused while an operator owns the software robot")
            if task["status"] in ("completed","cancelled","teleoperation","verification_failed"):
                raise ValueError("Task cannot execute in current state")
            room = store.get("room",task["room_id"])
            task["safety"] = evaluate(task,room,robot,task["simulation"],payload.target)
            if not task["safety"]["allowed"]:
                task.update(status="blocked",updated_at=now())
                store.put("task",task_id,task)
                store.event("safety_veto",user["role"],{"task_id":task_id,"reasons":task["safety"]["reasons"]})
                return task
            observed = mock.observe(mock.execute(task,room,task["safety"]))
            task["verification"] = mock.verify(task,observed)
            if task.get("template"):
                task["verification"]["desired_state"] = desired_diff(observed,task["template"])
                task["verification"]["passed"] &= task["verification"]["desired_state"]["ready"]
            persist_room(observed,user["role"])
            task.update(status="completed" if task["verification"]["passed"] else "verification_failed",updated_at=now(),completed_at=now())
            store.put("task",task_id,task)
            for req in store.list("request"):
                if req.get("task_id") == task_id:
                    req["status"] = task["status"]
                    req["message"] = "The item reached the requested place in the demo. No physical object was moved." if task["status"] == "completed" else "The demo could not verify the requested result. Staff assistance is needed."
                    store.put("request",req["id"],req)
            store.event("mock_task_finished",user["role"],{"task_id":task_id,"verified":task["verification"]["passed"],"physical_action":False})
            return task

    @api.post("/tasks/{task_id}/cancel")
    def cancel(task_id,user=Depends(role("patient","staff","operator","admin"))):
        with app.state.execution_lock, store.transaction():
            task = own_task(task_id,user)
            if task["status"] == "completed":
                raise ValueError("Completed task cannot be cancelled")
            release_takeover(task,"task_cancelled")
            task.update(status="cancelled",updated_at=now(),approval_hash=None)
            store.put("task",task_id,task)
            store.event("task_cancelled",user["role"],{"task_id":task_id,"physical_stop_confirmed":False})
            return task

    @api.post("/privacy")
    def privacy(payload:PrivacyInput,user=Depends(auth)):
        with app.state.execution_lock,store.transaction():
            room = snapshot(store.get("room",user["room_id"]))
            room["privacy"].update(payload.model_dump())
            persist_room(room,user["role"])
            return room["privacy"]

    @api.get("/robots/{robot_id}/capabilities")
    def capabilities(robot_id,user=Depends(role("staff","operator","researcher","admin"))):
        store.get("robot",robot_id)
        return manifest()

    @api.post("/robots/{robot_id}/estop")
    def estop(robot_id,payload:StopInput,user=Depends(role("patient","staff","operator","admin"))):
        if user["role"] == "patient" and not payload.engaged:
            raise HTTPException(403,"Staff must release the software stop")
        with app.state.execution_lock,store.transaction():
            robot = store.get("robot",robot_id)
            robot["estop"] = payload.engaged
            store.put("robot",robot_id,robot)
            for task in store.list("task"):
                if task["status"] not in ("completed","cancelled"):
                    release_takeover(task,"estop_changed")
                    task["approval_hash"] = None
                    task["status"] = "blocked"
                    store.put("task",task["id"],task)
            store.event("mock_estop_changed",user["role"],{"engaged":payload.engaged,"physical_stop_confirmed":False})
            return robot

    @api.post("/teleop/sessions")
    def takeover(payload:TeleopInput,user=Depends(role("operator","admin"))):
        with app.state.execution_lock:
            task = store.get("task",payload.task_id)
            robot = store.get("robot","mock-bracketbot")
            if robot.get("active_session_id"):
                raise ValueError("Another operator already owns the software robot")
            if task["status"] in ("completed","cancelled","teleoperation"):
                raise ValueError("Takeover requires an incomplete stopped task")
            if payload.environment != "mock" or not payload.consent:
                raise ValueError("Recording requires consent in a synthetic mock environment")
            # Stop autonomy before granting software operator ownership.
            task.update(status="blocked",approval_hash=None,updated_at=now())
            store.put("task",task["id"],task)
            instruction = "Synthetic semantic task: " + "; ".join(s["object_id"]+" to "+s["target_zone"] for s in task["proposal"]["candidate_steps"])
            session = learning().create_session({**payload.model_dump(),"environment":"synthetic_mock_room","instruction":instruction[:500],"takeover_reason":payload.reason,"operator_id":user["id"],"robot_revision":"synthetic-surrogate-v1","policy_version":"none","recording_consent":True,"synthetic":True})
            session = learning().start_session(session["id"])
            task["status"] = "teleoperation"
            task["active_session_id"] = session["id"]
            robot["active_session_id"] = session["id"]
            store.put("robot",robot["id"],robot)
            store.put("task",task["id"],task)
            store.event("software_takeover_accepted",user["role"],{"task_id":task["id"],"session_id":session["id"],"quest_connected":False})
            return session

    @api.post("/teleop/sessions/{session_id}/complete")
    def complete_session(session_id,payload:CompleteInput,user=Depends(role("operator","admin"))):
        if not payload.success and not payload.failure_category:
            raise ValueError("An unsuccessful episode needs a failure category")
        with app.state.execution_lock,store.transaction():
            episode = own_episode(session_id,user)
            if episode["status"] == "recording":
                learning().stop_session(session_id)
            session = learning().label_session(session_id,{"success":payload.success,"failure_category":payload.failure_category,"correction_notes":payload.notes})
            task_id = session.get("task_id")
            if task_id:
                task = store.get("task",task_id)
                if task.get("active_session_id") == session_id:
                    release_takeover(task,"recording_completed")
                    if task["status"] == "teleoperation":
                        task.update(status="blocked",updated_at=now(),approval_hash=None)
                    store.put("task",task_id,task)
            store.event("correction_label_saved",user["role"],{"session_id":session_id,"real_trajectory":False})
            return session

    @api.post("/teleop/sessions/{session_id}/demo-correction")
    def demo_correction(session_id,user=Depends(role("operator","admin"))):
        from ml.pipeline import synthetic_frame
        with app.state.execution_lock:
            session = own_episode(session_id,user)
            if session["environment"] != "synthetic_mock_room" or session["frame_count"]:
                raise ValueError("Synthetic fixture recording requires a new empty synthetic episode")
            if store.get("robot","mock-bracketbot").get("active_session_id") != session_id:
                raise ValueError("Session does not own the software robot")
            for i in range(12):
                offset = [.06-i*.004, -.03+i*.002, .02]
                learning().record_frame(session_id,synthetic_frame(i*.05,offset,intervention=True))
            store.event("synthetic_correction_frames",user["role"],{"session_id":session_id,"frames":12,"contains_camera_pixels":False})
            return learning().get_session(session_id)

    @api.post("/teleop/sessions/{session_id}/frames")
    def record_frame(session_id,payload:dict,user=Depends(role("operator","admin"))):
        with app.state.execution_lock:
            own_episode(session_id,user)
            if store.get("robot","mock-bracketbot").get("active_session_id") != session_id:
                raise ValueError("Session does not own the software robot")
            return learning().record_frame(session_id,payload)

    @api.post("/teleop/sessions/{session_id}/review")
    def review_session(session_id,payload:dict,user=Depends(role("researcher","admin"))):
        return learning().review_session(session_id,{**payload,"reviewer_id":user["id"]})

    @api.get("/teleop/sessions/{session_id}")
    def session_details(session_id,user=Depends(role("operator","researcher","admin"))):
        return learning().get_session(session_id)

    @api.get("/policies")
    def policies(user=Depends(role("staff","operator","researcher","admin"))):
        return learning().list_policies()

    @api.post("/policies/register")
    def register(payload:dict,user=Depends(role("researcher","admin"))):
        return learning().register_policy(payload)

    @api.post("/policies/train")
    def train_policy(payload:dict,user=Depends(role("researcher","admin"))):
        return learning().train_policy(payload)

    @api.post("/datasets/export")
    def export_dataset(payload:dict,user=Depends(role("researcher","admin"))):
        result = learning().export_dataset(payload.get("session_ids",[]),user["id"],payload.get("export_approved") is True)
        store.event("training_export",user["role"],{"dataset_id":result["id"],"episodes":result["episode_count"]})
        return result

    @api.post("/policies/{policy_id}/evaluate")
    def policy_evaluate(policy_id,payload:dict,user=Depends(role("researcher","admin"))):
        return learning().evaluate_policy(policy_id,payload)

    @api.post("/policies/{policy_id}/promote")
    def policy_promote(policy_id,payload:dict,user=Depends(role("researcher","admin"))):
        result = learning().promote_policy(policy_id,{**payload,"reviewer_id":user["id"]})
        store.event("policy_promotion",user["role"],{"policy_id":policy_id,"hardware_authorized":False})
        return result

    @api.post("/policies/{policy_id}/retire")
    def retire(policy_id,user=Depends(role("researcher","admin"))):
        return learning().retire_policy(policy_id)

    @api.post("/policies/{policy_id}/rollback")
    def rollback(policy_id,user=Depends(role("researcher","admin"))):
        return learning().rollback_policy(policy_id)

    @api.post("/skills/route")
    def skill_route(payload:dict,user=Depends(role("operator","researcher","admin"))):
        return learning().route_skill(payload)

    @api.post("/sim/benchmarks")
    def benchmark(payload:BenchmarkInput,user=Depends(role("operator","researcher","admin"))):
        from sim.engine import run_benchmark
        result = run_benchmark(payload.episodes,payload.seed)
        identifier = str(uuid4())
        result["id"] = identifier
        store.put("benchmark",identifier,result)
        store.event("surrogate_benchmark",user["role"],{"id":identifier,"episodes":payload.episodes})
        return result

    @api.get("/sim/reports/{report_id}")
    def report(report_id,user=Depends(role("operator","researcher","admin"))):
        return store.get("benchmark",report_id)

    @api.get("/sim/scene.png")
    def scene_image(user=Depends(role("staff","operator","researcher","admin"))):
        from sim.engine import render_scene
        path = ROOT/"artifacts"/"surrogate-room.png"
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            render_scene(path)
        return FileResponse(path,media_type="image/png")

    def reference_simulation():
        if not demo:
            raise HTTPException(403,"Reference simulation is available in local demo mode only")
        with app.state.execution_lock:
            if not hasattr(app.state,"reference_simulation"):
                from sim.reference_runtime import ReferenceSimulation
                app.state.reference_simulation = ReferenceSimulation()
            return app.state.reference_simulation

    @api.get("/sim/assets/{filename}")
    def reference_asset(filename: str,user=Depends(role("staff","operator","researcher","admin"))):
        if not demo:
            raise HTTPException(403,"Reference assets are available in local demo mode only")
        if filename not in {"room.glb","robot.glb","phone.glb","meal_box.glb"}:
            raise HTTPException(404,"Unknown simulation asset")
        directory = (ROOT/"assets"/"simulation").resolve()
        path = (directory/filename).resolve()
        if path.parent != directory or not path.is_file():
            raise HTTPException(404,"Detailed simulation asset is not available yet")
        return FileResponse(path,media_type="model/gltf-binary")

    @api.get("/sim/reference/state")
    def reference_state(user=Depends(role("staff","operator","researcher","admin"))):
        return reference_simulation().state()

    @api.post("/sim/reference/control")
    def reference_control(payload:ReferenceControlInput,user=Depends(role("staff","operator","researcher","admin"))):
        result = reference_simulation().command(payload.command)
        store.event("reference_simulation_control",user["id"],{"command":payload.command,"hardware_verified":False})
        return result

    @api.post("/sim/viewer")
    def open_viewer(user=Depends(role("staff","operator","researcher","admin"))):
        if not demo:
            raise HTTPException(403,"Native desktop viewer is available in local demo mode only")
        with app.state.execution_lock:
            process = getattr(app.state,"viewer_process",None)
            if process is not None and process.poll() is None:
                return {"status":"already_running","mode":"native_mujoco","hardware_model_verified":False}
            ready = ROOT/"artifacts"/("viewer-ready-"+uuid4().hex+".json")
            # Fixed local command; no model or user-supplied shell/path parameters.
            log = (ROOT/"artifacts"/"viewer.log").open("a",encoding="utf-8")
            try:
                process = subprocess.Popen([sys.executable,"-m","sim","viewer","--ready-file",str(ready)],cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            finally:
                log.close()
            app.state.viewer_process = process
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            if ready.exists():
                store.event("native_mujoco_viewer_opened",user["id"],{"hardware_verified":False})
                return {"status":"opened","mode":"native_mujoco","hardware_model_verified":False,"controls":"Mouse orbit; wheel zoom; Space pause; M motion; R reset; C cameras"}
            if process.poll() is not None:
                raise HTTPException(503,"Native viewer could not start; inspect artifacts/viewer.log")
            time.sleep(.1)
        return {"status":"starting","mode":"native_mujoco","hardware_model_verified":False,"message":"Waiting for the native OpenGL window"}

    @api.post("/demo/scenario")
    def scenario(payload:ScenarioInput,user=Depends(role("operator","admin"))):
        if payload.scenario not in ("reset","person_enters","uncertain_phone","attached_phone","blocked_path","unknown_object"):
            raise ValueError("Unknown synthetic scenario")
        with app.state.execution_lock,store.transaction():
            if store.get("robot","mock-bracketbot").get("active_session_id"):
                raise ValueError("Finish or cancel operator takeover before changing scenarios")
            previous = store.get("room","room-417")
            room = seed_room(payload.seed) if payload.scenario == "reset" else snapshot(previous)
            room["version"] = previous["version"]+1
            phone = get_object(room,"phone")
            if payload.scenario == "person_enters":
                room["persons"] = [{"id":"synthetic-person","pose":{"x":2,"y":2,"z":.8},"radius":.35}]
            elif payload.scenario == "uncertain_phone":
                phone["confidence"] = .4
                phone["grasp_confidence"] = .3
            elif payload.scenario == "attached_phone":
                phone["attached"] = True
            elif payload.scenario == "unknown_object":
                phone["policy"] = "UNKNOWN_PROHIBITED"
            elif payload.scenario == "blocked_path":
                room["zones"].append({"id":"temporary-obstacle","type":"keepout","bounds":{"min":{"x":1.7,"y":1.8,"z":0},"max":{"x":2.2,"y":2.7,"z":2}}})
            persist_room(room,user["role"])
            store.event("synthetic_scenario_selected",user["role"],{"scenario":payload.scenario,"seed":payload.seed})
            return room

    @api.get("/research")
    def get_research(user=Depends(role("staff","operator","researcher","admin"))):
        return {**research(),"benchmarks":store.list("benchmark")}

    @api.get("/audit")
    def audit(user=Depends(role("operator","admin"))):
        return {"chain_valid":store.verify_audit(),"events":store.events(200)}

    app.include_router(api)
    dist = ROOT/"apps"/"web"/"dist"
    if dist.exists():
        app.mount("/assets",StaticFiles(directory=dist/"assets"),name="assets")
        @app.get("/")
        def index():
            return FileResponse(dist/"index.html")
    return app


app = create_app()
