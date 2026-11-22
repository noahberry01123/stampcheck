"""Read review data (SQLite, JSONL, CSV/TSV, Postgres) and map it onto the canonical fields."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import DECISIONS, FIELDS, NAME, RECOMMENDATIONS

REQUIRED = ("case_id", "recommended", "decision", "decided_at")
TIMES = ("opened_at", "decided_at", "notified_at")
ALLOWED = {"recommended": RECOMMENDATIONS, "decision": DECISIONS}
BAD = "\0unreadable"
# Column names recognised automatically, compared after norm(); earlier aliases win.
ALIASES = {
    "case_id": ["case_id", "case", "id", "ticket_id", "request_id", "approval_id", "decision_id"],
    "recommended": ["recommended", "recommendation", "ai_recommendation", "system_recommendation",
                    "suggested", "suggestion", "ai_decision", "model_decision", "proposed"],
    "decision": ["decision", "human_decision", "verdict", "outcome", "final_decision", "review_decision"],
    "reviewer": ["reviewer", "reviewer_id", "reviewed_by", "approver", "approver_id", "decided_by"],
    "opened_at": ["opened_at", "opened", "first_opened_at", "first_viewed_at", "viewed_at",
                  "review_started_at", "started_at", "claimed_at"],
    "decided_at": ["decided_at", "decided", "decision_at", "reviewed_at", "resolved_at",
                   "completed_at", "closed_at"],
    "notified_at": ["notified_at", "queued_at", "assigned_at", "requested_at", "created_at"],
    "category": ["category", "step", "approval_step", "queue", "tier", "type"],
    "executed": ["executed", "executions", "execution_count", "times_executed"],
}
SYNONYMS = {v: c for c, vs in {
    "approve": ["approve", "approved", "accept", "accepted"],
    "reject": ["reject", "rejected", "deny", "denied", "decline", "declined"],
    "escalate": ["escalate", "escalated"],
    "timeout_approve": ["timeout_approve"], "timeout_reject": ["timeout_reject"],
}.items() for v in vs}


class InputError(Exception):
    """A problem with the input data that stops the run (exit code 2)."""


def norm(name: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def load(source: str, cfg: dict, query: str | None = None) -> tuple[list[dict], dict]:
    """Return (rows, quality). Rows have the canonical FIELDS; quality says what was read and skipped."""
    header, raw = read_raw(source, cfg, query)
    columns = resolve_columns(header, cfg["columns"])
    try:
        tz = ZoneInfo(cfg["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise InputError(f"unknown timezone {cfg['timezone']!r} in config") from None
    rows, skipped, notes = [], Counter(), Counter()
    unmapped: dict = defaultdict(Counter)
    used: dict = defaultdict(dict)
    for r in raw:
        rec, why = convert(r, columns, cfg["values"], tz, unmapped, used, notes)
        if why:
            skipped[why] += 1
        else:
            rows.append(rec)
    quality = {"source": re.sub(r"//[^@/]*@", "//***@", source), "rows_read": len(raw),
               "rows_used": len(rows), "skipped": dict(skipped), "columns": columns,
               "values": {f: dict(v) for f, v in used.items()},
               "unmapped": {f: dict(c.most_common()) for f, c in unmapped.items()},
               "missing_columns": [f for f in FIELDS if not columns.get(f)], "notes": dict(notes)}
    if not rows:
        detail = "; ".join(f"{n} {why}" for why, n in skipped.items()) or "the source is empty"
        hint = f" Unmapped values: {quality['unmapped']}. Map them under values: in a config file." \
            if unmapped else ""
        raise InputError(f"no usable rows in {quality['source']} ({detail}).{hint}")
    return rows, quality


def read_raw(source: str, cfg: dict, query: str | None) -> tuple[list, list[dict]]:
    if re.match(r"postgres(ql)?://", source):
        if not query:
            raise InputError("Postgres sources need --query, e.g. --query 'SELECT * FROM reviews'")
        return _postgres(source, query)
    p = Path(source)
    if not p.is_file():
        raise InputError(f"source not found: {source}")
    suffix = p.suffix.lower()
    if suffix in (".db", ".sqlite", ".sqlite3"):
        return _sqlite(p, query or "SELECT * FROM reviews")
    try:
        text = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise InputError(f"{source} is not UTF-8 text; re-export it as UTF-8") from None
    if suffix in (".jsonl", ".ndjson"):
        return _jsonl(text)
    return _csv(text, cfg.get("csv_delimiter"), suffix == ".tsv", source)


def _sqlite(p: Path, query: str) -> tuple[list, list[dict]]:
    con = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)  # read-only
    try:
        cur = con.execute(query)
        header = [d[0] for d in cur.description]
        return header, [dict(zip(header, r)) for r in cur.fetchall()]
    except sqlite3.Error as e:
        raise InputError(f"{p}: {e}") from None
    finally:
        con.close()


def _postgres(url: str, query: str) -> tuple[list, list[dict]]:
    try:
        import psycopg
    except ImportError:
        raise InputError(f"Postgres needs the optional extra: pip install '{NAME}[postgres]'") from None
    try:
        with psycopg.connect(url) as con, con.cursor() as cur:
            cur.execute(query)
            header = [d.name for d in cur.description]
            return header, [dict(zip(header, r)) for r in cur.fetchall()]
    except psycopg.Error as e:
        raise InputError(f"Postgres: {e}") from None


def _jsonl(text: str) -> tuple[list, list[dict]]:
    rows = []
    for line in text.splitlines():
        if line.strip():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                obj = None
            rows.append(obj if isinstance(obj, dict) else {BAD: True})
    return list(dict.fromkeys(k for r in rows for k in r if k != BAD)), rows


def _csv(text: str, delimiter: str | None, tab: bool, source: str) -> tuple[list, list[dict]]:
    if delimiter in ("tab", "\\t"):
        delimiter = "\t"
    if not delimiter:
        first = text.split("\n", 1)[0]
        delimiter = "\t" if tab else max(",;\t|", key=first.count)
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
        header = [h for h in reader.fieldnames or [] if h is not None]
        rows = list(reader)
    except csv.Error as e:
        raise InputError(f"{source}: {e}") from None
    if not header:
        raise InputError(f"{source} is empty")
    return header, rows


def resolve_columns(header: list, explicit: dict) -> dict:
    by_norm: dict[str, str] = {}
    for h in header:
        by_norm.setdefault(norm(h), h)
    found = ", ".join(map(str, header))
    cols: dict = {}
    for f, name in explicit.items():
        if name is None:
            cols[f] = None
            continue
        match = name if name in header else by_norm.get(norm(name))
        if match is None:
            raise InputError(f"the mapping says {f} is column {name!r}, but there is no such column. "
                             f"Columns found: {found}")
        cols[f] = match
    taken = set(cols.values())
    for f in FIELDS:
        if f not in cols:
            cols[f] = next((by_norm[a] for a in ALIASES[f] if a in by_norm and by_norm[a] not in taken), None)
            taken.add(cols[f])
    if missing := [f for f in REQUIRED if not cols[f]]:
        raise InputError(f"no column found for {', '.join(missing)}. Columns found: {found}. "
                         f"Run `{NAME} init` and map them under columns:, then pass --mapping {NAME}.yaml")
    return cols


def convert(r: dict, cols: dict, values: dict, tz, unmapped, used, notes) -> tuple[dict | None, str | None]:
    """One raw row -> (canonical row, None) or (None, reason it was skipped)."""
    if BAD in r:
        return None, "unreadable line"

    def text(f: str) -> str | None:
        v = r.get(cols[f]) if cols[f] else None
        return None if v is None or str(v).strip() == "" else str(v).strip()

    rec: dict = {"case_id": text("case_id")}
    if not rec["case_id"]:
        return None, "case_id missing"
    for f in ("recommended", "decision"):
        raw = text(f)
        if raw is None:
            return None, f"{f} missing"
        canon = values.get(f, {}).get(raw.lower()) or SYNONYMS.get(raw.lower())
        if canon not in ALLOWED[f]:
            unmapped[f][raw] += 1
            return None, f"unmapped {f} value"
        used[f][raw] = rec[f] = canon
    for f in TIMES:
        try:
            rec[f], naive = parse_ts(r.get(cols[f]) if cols[f] else None, tz)
        except (ValueError, OverflowError, OSError):
            if f == "decided_at":
                return None, "decided_at unreadable"
            rec[f], naive = None, False
            notes[f"{f} unreadable, treated as missing"] += 1
        if naive:
            notes[f"timestamps without a timezone, read as {tz.key}"] += 1
    if rec["decided_at"] is None:
        return None, "decided_at missing"
    if rec["opened_at"] and rec["opened_at"] > rec["decided_at"]:
        rec["opened_at"] = None
        notes["opened_at later than decided_at, treated as missing"] += 1
    rec["reviewer"] = text("reviewer")
    rec["category"] = text("category") or "default"
    ex = text("executed")
    if ex is not None and ex.lower() in ("true", "yes", "false", "no"):
        ex = "1" if ex.lower() in ("true", "yes") else "0"
    try:
        rec["executed"] = None if ex is None else int(float(ex))
    except ValueError:
        return None, "executed is not a number"
    return rec, None


_FRACTION = re.compile(r"\.(\d+)")
_OFFSET = re.compile(r"([+-]\d{2})(\d{2})$")


def parse_ts(v: object, tz) -> tuple[datetime | None, bool]:
    """(UTC datetime or None, whether it had no timezone). Raises ValueError if unreadable."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, False
    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, (int, float)) or re.fullmatch(r"\d{9,13}(\.\d+)?", str(v).strip()):
        x = float(v)  # epoch seconds, or milliseconds if it is that large
        return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, timezone.utc), False
    else:
        s = str(v).strip()
        s = s[:-1] + "+00:00" if s[-1] in "zZ" else s
        s = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], s)  # Python 3.10 wants 6 digits
        s = _OFFSET.sub(r"\1:\2", s) if len(s) > 10 else s
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz).astimezone(timezone.utc), True
    return dt.astimezone(timezone.utc), False


def pseudonymize(rows: list[dict], salt: str) -> None:
    """Replace reviewer IDs with a salted hash, stable across runs that use the same salt."""
    for r in rows:
        if r["reviewer"]:
            r["reviewer"] = "r-" + hashlib.sha256(f"{salt}:{r['reviewer']}".encode()).hexdigest()[:8]
