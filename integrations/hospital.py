"""Synthetic hospital service contracts. No EHR/call-bell connectivity."""
from typing import Protocol
from uuid import uuid4
from services.store import now


class HospitalAdapter(Protocol):
    def information(self, query: str, room_id: str) -> dict: ...
    def route_request(self, route: str, room_id: str, request_id: str) -> dict: ...
    def locate_asset(self, asset: str) -> dict: ...


class MockHospitalAdapter:
    def information(self, query, room_id):
        query = query.lower()
        answer = "That information is unavailable. Please check with staff."
        if "visiting" in query:
            answer = "Demo visiting hours are 10 am–8 pm. These are synthetic hours for this mock room."
        elif "next" in query or "transport" in query or "when" in query:
            answer = "The demo transport request is awaiting confirmation. No appointment time is available."
        elif "wi" in query:
            answer = "The demo guest network is Vela-Guest. No real hospital network is connected."
        return {"answer":answer, "source":"Synthetic hospital operations fixture", "updated_at":now(), "live":False}

    def route_request(self, route, room_id, request_id):
        task = {"resourceType":"Task", "id":str(uuid4()), "status":"requested", "intent":"order", "priority":"stat" if route == "D" else "routine", "code":{"text":"Synthetic clinical escalation" if route == "D" else "Synthetic non-clinical service request"}, "for":{"reference":"Location/"+room_id}, "authoredOn":now(), "identifier":[{"system":"urn:vela:demo:request", "value":request_id}], "meta":{"tag":[{"system":"urn:vela:environment", "code":"synthetic"}]}}
        return {"status":"queued_in_mock_adapter", "delivered_to_staff":False, "queue":"clinical staff" if route == "D" else "room services", "fhir_task":task, "live":False}

    def locate_asset(self, asset):
        return {"asset":asset, "location":None, "source":"Mock RTLS adapter", "live":False, "reason":"No authoritative asset observation available"}

