"""record_review: one line to log a human review, including when the reviewer opened the case."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from .config import DB_FILE, DECISIONS, ENV_PATH, FIELDS, NAME, RECOMMENDATIONS

log = logging.getLogger(NAME)
CREATE = f"CREATE TABLE IF NOT EXISTS reviews ({', '.join(FIELDS)})"
INSERT = f"INSERT INTO reviews VALUES ({', '.join('?' * len(FIELDS))})"
Time = datetime | str | float | None


def record_review(case_id: str, recommended: str, decision: str, reviewer: str | None,
                  opened_at: Time, decided_at: Time, notified_at: Time = None,
                  category: str | None = None, executed: int | None = None,
                  *, path: str | Path | None = None) -> None:
    """Log one human review of an automated recommendation.

    The point of this helper is `opened_at`: the moment the reviewer actually opened the case.
    Most systems only log when the decision was made. Without the opening time you cannot tell a
    reviewer who read the case for two minutes from one who clicked approve two seconds after it
    appeared, and the rubber-stamp check cannot run.

    recommended: what the system proposed, "approve" or "reject".
    decision:    what the human did: "approve", "reject" or "escalate". If nobody acted before the
                 deadline, log "timeout_approve" or "timeout_reject" (whatever happened by default).
    opened_at, decided_at, notified_at: datetimes (naive ones are read as local time), ISO-8601
                 strings, or epoch seconds. notified_at is when the case entered the queue.
    category:    the approval step or category, e.g. "refund_under_50". Each gets its own verdict.
    executed:    how many times the approved action ran (normally 1, or 0 if rejected). None if unknown.
    path:        SQLite file, default ./stampcheck.db or $STAMPCHECK_PATH. A path ending in .jsonl
                 appends JSON lines instead.

    It never raises, so it cannot break your approval flow: problems (an unknown value, a full disk)
    are logged as warnings on the "stampcheck" logger. Unknown values are still written, and
    `stampcheck check` lists them.
    """
    if recommended not in RECOMMENDATIONS:
        log.warning("recommended should be one of %s, got %r", RECOMMENDATIONS, recommended)
    if decision not in DECISIONS:
        log.warning("decision should be one of %s, got %r", DECISIONS, decision)
    try:
        write_rows([{"case_id": str(case_id), "recommended": recommended, "decision": decision,
                     "reviewer": None if reviewer is None else str(reviewer), "opened_at": opened_at,
                     "decided_at": decided_at, "notified_at": notified_at, "category": category,
                     "executed": None if executed is None else int(executed)}], path)
    except Exception:  # noqa: BLE001 (logging must never break the caller)
        log.warning("could not record review of case %r", case_id, exc_info=True)


@contextmanager
def review(case_id: str, recommended: str, reviewer: str | None, *, notified_at: Time = None,
           category: str | None = None, path: str | Path | None = None) -> Iterator[SimpleNamespace]:
    """Record opened_at on enter and decided_at on exit. Set r.decision (and r.executed) inside:

        with stampcheck.review(case.id, case.ai_recommendation, user.id) as r:
            r.decision = ask_human(case)       # "approve" / "reject" / "escalate"
            r.executed = 1 if r.decision == "approve" else 0

    Nothing is written if the block raises or never sets r.decision.
    """
    r = SimpleNamespace(decision=None, executed=None, opened_at=datetime.now(timezone.utc))
    yield r
    if r.decision is None:
        log.warning("case %r: set r.decision inside the `with stampcheck.review(...)` block", case_id)
        return
    record_review(case_id, recommended, r.decision, reviewer, r.opened_at, datetime.now(timezone.utc),
                  notified_at, category, r.executed, path=path)


def write_rows(rows: list[dict], path: str | Path | None = None) -> Path:
    """Append rows (dicts with the FIELDS keys) to a SQLite or JSONL file."""
    path = Path(path or os.environ.get(ENV_PATH) or DB_FILE)
    out = [{k: _iso(r.get(k)) if k.endswith("_at") else r.get(k) for k in FIELDS} for r in rows]
    if path.suffix.lower() == ".jsonl":
        with path.open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(r) + "\n" for r in out)
        return path
    with closing(sqlite3.connect(path)) as con, con:
        con.execute(CREATE)
        con.executemany(INSERT, [tuple(r[k] for k in FIELDS) for r in out])
    return path


def _iso(v: Time) -> str | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        v = datetime.fromtimestamp(v, timezone.utc)
    elif isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    elif v.tzinfo is None:
        v = v.astimezone()  # naive datetime: local time, like datetime.now()
    return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
