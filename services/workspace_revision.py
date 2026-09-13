"""Fingerprint local backend inputs so launchers detect a stale running server."""
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def backend_revision():
    digest = sha256()
    sources = [p for directory in ("services", "sim", "robot", "integrations", "ml", "shared") for p in (ROOT/directory).rglob("*.py")]
    sources += [ROOT/"sim"/"reference_demo_trajectories.json"]
    for path in sorted(sources):
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()

if __name__ == "__main__":
    print(backend_revision())
