"""Conservative lexical rules run before any optional classifier.

This is a routing prototype, not a clinically validated triage system.
"""
import re
import unicodedata

CRITICAL = re.compile(
    r"\b(pain\w*|hurt\w*|breath\w*|bleed\w*|blood|chest|dizz\w*|faint\w*|"
    r"fell|fall\w*|seizure\w*|stroke|chok\w*|numb\w*|vomit\w*|nause\w*|"
    r"sick|unwell|fever|swell\w*|allerg\w*|medicin\w*|medicat\w*|pills?|"
    r"drugs?|insulin|dose|dosage|iv|intravenous|catheter\w*|oxygen|tubes?|"
    r"tubing|lines?|pump\w*|alarms?|medical|clinical|diagnos\w*|treat\w*|"
    r"emergency|urgent|nurse|doctor|suicid\w*|dying|die|wound\w*|weak\w*|"
    r"confus\w*|ventilator\w*|infusion\w*|blind|vision|numb\w*|unconscious|"
    r"resuscitat\w*|cpr|tightness)\b|"
    r"\b(help me (up|stand|walk)|lift me|turn me|reposition me|feed me|can't move|cannot move|"
    r"(can't|cannot|can not) (see|hear|feel|swallow)|not enough air|feel strange)\b"
)
INFORMATION = re.compile(r"\b(visiting hours|wi-?fi|what('s| is) (happening )?next|when (is|are)|has transport|where is|where are|request status)\b")
HUMAN = re.compile(r"\b(clean\w*|food|meal|linen\w*|towel\w*|maintenance|broken|laundry|supplies)\b")
PHYSICAL = re.compile(r"\b(bring|move|retrieve|fetch|prepare|arrange|reset|close|open|closer)\b")
KNOWN = re.compile(r"\b(phone|glasses|remote|bag|tray|chair|blinds|room|physio|visitor|rounds)\b")
PHYSICAL_WORDS = set("can could would will you please bring move retrieve fetch prepare arrange reset close open closer my the a an this that our to me for room phone glasses remote bag tray chair blinds physio visitor rounds rest admission discharge meal turnover ready nonclinical non clinical surface bedside table inside on toward within find locate approved personal item items small lightweight case empty now back put set up help with".split())


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).lower().replace("’", "'").split())


def triage(text: str, model_route: str | None = None) -> dict:
    value = normalize(text)
    critical = CRITICAL.search(value)
    if critical:
        return {"route": "D", "reason": "deterministic_clinical_trigger", "trigger": critical.group(), "locked": True}
    # Risk can only rise; unknown model labels cannot create permission.
    if model_route == "D":
        return {"route": "D", "reason": "model_escalated", "locked": True}
    if INFORMATION.search(value):
        return {"route": "A", "reason": "authoritative_information_required", "locked": False}
    if HUMAN.search(value):
        return {"route": "C", "reason": "human_nonclinical_service", "locked": False}
    if PHYSICAL.search(value) and KNOWN.search(value):
        # Do not let one recognized physical phrase absorb an unknown second intent.
        words = set(re.findall(r"[\w']+",value))
        if words - PHYSICAL_WORDS:
            return {"route":"D","reason":"mixed_or_unsupported_physical_request","locked":True}
        return {"route": "B", "reason": "candidate_physical_assistance", "locked": False}
    return {"route": "D", "reason": "ambiguous_request", "locked": True}
