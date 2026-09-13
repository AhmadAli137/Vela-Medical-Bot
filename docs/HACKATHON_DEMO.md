# Runnable demonstration

Use a laptop/browser; no robot is required. Start with `scripts/run.ps1`. All room content is synthetic. The automated counterpart is `python -m scripts.run_demo` and writes `artifacts/demo-report.json`.

1. Open the patient view and request **Bring my phone closer**. The route is B and a reviewable task appears. Switch to staff role, inspect the proposal, validate, approve, then run it in the mock room. The phone changes logical position and verification checks the accessible zone. No physical grasp occurred.
2. Prepare **physio_ready** from room operations. The plan moves the lightweight chair proxy, small bag and remote into semantic zones, clears egress, and verifies the full template. It never moves the bed or clinical equipment.
3. Use operator demo controls or `POST /api/demo/scenario` with `uncertain_phone`. Create a new phone task. Validation/approval cannot override low object/grasp confidence: execution returns blocked.
4. As operator, accept software takeover and consent to synthetic recording. Record the synthetic correction, then stop and label it. The episode has 12 state/action frames and placeholder media references; it remains quarantined. This demonstrates the lifecycle, not a connected Quest session.
5. Run `python -m ml demo --output artifacts/learning`. Five synthetic episodes train an actual tiny ridge behavior-cloning baseline with an episode-level holdout. Inspect computed evaluation and abstention results. The policy remains unpromoted pending explicit research signoff. No VLA competence is implied.
6. Request **My chest hurts**. Deterministic Route D takes priority. The UI explicitly says it cannot contact staff and refers to the existing hospital call pathway. The synthetic FHIR-style task is not a delivered nurse-call message.

Use `POST /api/demo/scenario` with `reset` and a new `seed` to vary the phone location. A changed room invalidates old tasks; replan against the refreshed snapshot. Other fixtures cover person entry, attached phone, blocked path and unknown object policy.

