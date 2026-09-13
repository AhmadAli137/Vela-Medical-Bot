"""Optional provider clients accept explicitly classified synthetic input only.

No provider is given robot tools. Refusal, missing parsing, or invalid schemas
raise errors and cannot grant execution authority.
"""
import json
import os
from shared.models import Critique, SceneInterpretation, TaskProposal


def ensure_cloud_allowed(data_class):
    if os.getenv("VELA_ENABLE_CLOUD_MODELS") != "1":
        raise RuntimeError("Cloud models disabled; configure explicit opt-in and credentials")
    if data_class != "synthetic":
        raise ValueError("Prototype cloud adapters accept synthetic data only")


class AstraAdapter:
    model = "gpt-6-astra"

    def structured(self, prompt, payload, schema, *, data_class):
        ensure_cloud_allowed(data_class)
        from openai import OpenAI
        client = OpenAI(timeout=30, max_retries=0)
        result = client.responses.parse(model=self.model, store=False, instructions=prompt, input=json.dumps(payload), text_format=schema)
        if result.status != "completed" or result.output_parsed is None:
            raise RuntimeError("Astra response refused, incomplete or unparseable")
        return result.output_parsed

    def plan(self, goal, room, *, data_class):
        return self.structured("Propose a non-clinical semantic plan using only the supplied object IDs and zones. No patient contact, clinical objects or actuator commands. Uncertain requests must abstain. These are synthetic fixtures; all steps must use mock-semantic-place-v1, DETERMINISTIC, place_in_zone. Never claim hardware validation. Require human approval.", {"goal":goal,"room":room}, TaskProposal,data_class=data_class)

    def interpret_scene(self, image_descriptions, *, data_class):
        return self.structured("Interpret supplied synthetic scene observations into semantic hypotheses. Single views cannot establish metric geometry. Include uncertainties.", image_descriptions, SceneInterpretation,data_class=data_class)


class FableAdapter:
    model = "claude-fable-5"

    def critique(self, proposal, room, *, data_class):
        ensure_cloud_allowed(data_class)
        from anthropic import Anthropic
        client = Anthropic(timeout=30, max_retries=0)
        result = client.messages.parse(model=self.model, max_tokens=2048, system="Independently critique this synthetic hospital non-clinical candidate. Reject clinical interaction, invented geometry, unsafe proximity, unsupported permission, and plans that do not solve intent. No motor commands. Acceptance is a candidate assessment only.", messages=[{"role":"user","content":json.dumps({"proposal":proposal,"room":room})}], output_format=Critique)
        if result.stop_reason != "end_turn" or result.parsed_output is None:
            raise RuntimeError("Fable response refused, incomplete or unparseable")
        return result.parsed_output
