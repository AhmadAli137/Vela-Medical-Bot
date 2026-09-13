import json
from pathlib import Path
from robot.capabilities import manifest
from shared.models import TaskProposal, Critique, SceneInterpretation
from ml.pipeline import TeleopFrame
from services.app import app

if __name__ == "__main__":
    target = Path("shared/schemas")
    target.mkdir(parents=True,exist_ok=True)
    for model in (TaskProposal,Critique,SceneInterpretation,TeleopFrame):
        (target/(model.__name__+".json")).write_text(json.dumps(model.model_json_schema(),indent=2),encoding="utf-8")
    Path("robot/capability-manifest.json").write_text(json.dumps(manifest(),indent=2),encoding="utf-8")
    Path("docs/openapi.json").write_text(json.dumps(app.openapi(),indent=2),encoding="utf-8")
    print("Exported schemas, reported capability manifest and generated OpenAPI")

