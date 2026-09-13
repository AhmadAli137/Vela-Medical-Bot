import os
from uuid import uuid4
from services.models import AstraAdapter, FableAdapter
from services.router import triage
from services.safety import POLICY_VERSION, check_clinical_prohibition
from services.store import digest, now
from services.world import TEMPLATES, desired_diff, get_object, zone_target
from shared.models import Critique, Step, TaskProposal


def local_critique(proposal, room):
    reasons = []
    for step in proposal.candidate_steps:
        obj = get_object(room, step.object_id)
        if obj is None or not check_clinical_prohibition(obj):
            reasons.append("Unknown or clinically prohibited target: " + step.object_id)
        if step.execution_type != "DETERMINISTIC" or step.skill_id != "mock-semantic-place-v1":
            reasons.append("No learned policy or physical controller is validated in this prototype")
    return Critique(verdict="reject" if reasons else "accept_candidate", reasons=reasons or ["Candidate uses known mock objects and semantic destinations"], hidden_assumptions=["Synthetic scene geometry; no real perception or grasp validation"], clinical_boundary_violation=bool(reasons), human_first_alternative="Ask staff to move permitted belongings", solves_original_intent=not reasons)


def build_plan(payload, room):
    goal = payload["goal"]
    route = triage(goal)
    if route["route"] == "D":
        raise ValueError("Clinical or ambiguous requests require staff routing; planning prohibited")
    template = payload.get("template")
    if template is None:
        template = next((t for t in TEMPLATES if t.replace("_ready", "") in goal.lower()), None)
    object_id = payload.get("object_id")
    if object_id is None and template is None:
        object_id = next((o["id"] for o in room["objects"] if o["id"] in goal.lower()), None)
    if template:
        changes = desired_diff(room, template)["changes"]
        assignments = [(change["object_id"], change["target_zone"]) for change in changes]
    elif object_id and get_object(room,object_id):
        assignments = [(object_id, "accessible_zone")]
    else:
        raise ValueError("No permitted semantic goal could be resolved; request staff assistance")
    steps = [Step(id=str(i+1), action="place_in_zone", object_id=identifier, target_zone=zone, target_pose=zone_target(room,zone,i), skill_id="mock-semantic-place-v1", execution_type="DETERMINISTIC") for i,(identifier,zone) in enumerate(assignments)]
    proposal = TaskProposal(intent=goal,target_outcome=template or "Item on an accessible side surface",patient_context_allowed=False,current_room_state_id=f'{room["id"]}/v{room["version"]}',desired_room_state=template or "personal_item_accessible",candidate_steps=steps,affected_objects=[s.object_id for s in steps],assumptions=["Synthetic empty mock room; no patient contact", "Object motion is a logical fixture transition, not a physical grasp"],uncertainties=["Real SDK, kinematics, calibration and VLA competence are unverified"],required_skills=["mock-semantic-place-v1"] if steps else [],prohibited_interactions=["patients", "clinical devices", "attached objects", "unknown objects"],human_approval_required=True,success_criteria=[f"{identifier} within {zone}" for identifier,zone in assignments])
    source = "deterministic mock planner and separate rule critic"
    critique = local_critique(proposal,room)
    if os.getenv("VELA_ENABLE_CLOUD_MODELS") == "1":
        # Never send operational free text or identifiers to cloud providers.
        # This API only has server-generated synthetic rooms; reject any other source.
        canonical_goal = [{"object_class":identifier,"destination":zone} for identifier,zone in assignments]
        cloud_room = {"id":"room-417","version":room["version"],"source":"synthetic", "geometry":room["geometry"],"zones":room["zones"],"objects":[{key:obj[key] for key in ("id","semantic_class","pose","dimensions","policy","confidence","attached")} for obj in room["objects"]]}
        try:
            if room.get("source") != "synthetic":
                raise ValueError("Cloud planning is restricted to generated synthetic scenes")
            candidate = AstraAdapter().plan(canonical_goal,cloud_room,data_class="synthetic")
            expected = {(s.object_id,s.target_zone) for s in proposal.candidate_steps}
            actual = {(s.object_id,s.target_zone) for s in candidate.candidate_steps}
            if expected != actual or len(candidate.candidate_steps) != len(steps) or candidate.current_room_state_id != proposal.current_room_state_id:
                raise ValueError("Model candidate differs from deterministic intent envelope")
            candidate.human_approval_required = True
            local = local_critique(candidate,room)
            independent = FableAdapter().critique(candidate.model_dump(mode="json"),cloud_room,data_class="synthetic")
            proposal = candidate
            critique = local if local.verdict == "reject" else independent
            source = "gpt-6-astra candidate + claude-fable-5 critique + deterministic constraints"
        except Exception as exc:
            # A failed optional consultation cannot lose the request or grant authority.
            # Retain the original deterministic candidate and its existing staff gate.
            source = "deterministic fallback; optional cloud consultation unavailable ("+type(exc).__name__+")"
            proposal.uncertainties.append("Cloud consultation unavailable; staff must review deterministic candidate")
    serialized = proposal.model_dump(mode="json")
    task = {"id":str(uuid4()),"room_id":room["id"],"room_version":room["version"],"room_hash":digest(room),"goal":goal,"status":"planned","created_at":now(),"updated_at":now(),"policy_version":POLICY_VERSION,"proposal":serialized,"critique":critique.model_dump(),"planner_source":source,"execution_mode":"DETERMINISTIC","skill_id":"mock-semantic-place-v1","simulation":None,"approval_hash":None,"safety":None,"verification":None,"mode":"mock","template":template}
    task["plan_hash"] = digest({"proposal":serialized,"room_hash":task["room_hash"],"policy":POLICY_VERSION})
    return task
