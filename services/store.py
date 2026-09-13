"""SQLite transactional records and append-only, hash-chained audit events.

The chain detects tampering; it is not an external immutable audit service.
"""
import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Store:
    def __init__(self, path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, body TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
            CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append only'); END;
        """)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            else:
                self.db.execute("COMMIT")

    def put(self, kind, identifier, value):
        with self.lock:
            self.db.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body", (kind, identifier, canonical(value)))
        return value

    def get(self, kind, identifier):
        with self.lock:
            row = self.db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, identifier)).fetchone()
        if not row:
            raise KeyError(identifier)
        return json.loads(row[0])

    def list(self, kind):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute("SELECT body FROM records WHERE kind=? ORDER BY rowid DESC", (kind,))]

    def event(self, action, actor, details):
        with self.lock:
            row = self.db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            previous = row[0] if row else "0" * 64
            body = {"timestamp": now(), "action": action, "actor": actor, "details": details}
            hash_value = digest({"previous": previous, "body": body})
            self.db.execute("INSERT INTO events(body,previous_hash,hash) VALUES (?,?,?)", (canonical(body), previous, hash_value))
        return body

    def events(self, limit=100):
        with self.lock:
            return [{"seq": r[0], **json.loads(r[1]), "previous_hash": r[2], "hash": r[3]} for r in self.db.execute("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,))]

    def verify_audit(self):
        previous = "0" * 64
        for item in reversed(self.events(1_000_000)):
            body = {key: item[key] for key in ("timestamp", "action", "actor", "details")}
            if item["previous_hash"] != previous or item["hash"] != digest({"previous": previous, "body": body}):
                return False
            previous = item["hash"]
        return True

