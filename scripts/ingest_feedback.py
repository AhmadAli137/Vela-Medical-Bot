"""Import an authorized, human-reviewed CSV into a separate research artifact."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.evidence import import_feedback, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--source", type=Path, required=True, help="JSON rights/provenance record")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--privacy-attestation", required=True, choices=["human_reviewed_deidentified"])
    parser.add_argument("--intended-use", choices=["research", "commercial"], default="research")
    args = parser.parse_args()
    try:
        source = json.loads(args.source.read_text(encoding="utf-8"))
        records = import_feedback(args.csv, source, privacy_attestation=args.privacy_attestation,
                                  intended_use=args.intended_use)
        write_json(args.output, records)
        print(json.dumps({"imported": len(records), "output": str(args.output), "automatically_published": False}))
    except (ValueError, OSError) as error:
        parser.exit(2, f"Import refused: {error}\n")


if __name__ == "__main__":
    main()
