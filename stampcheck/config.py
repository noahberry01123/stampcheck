"""Tool name, data model constants, default thresholds, and config-file loading (YAML or JSON)."""
from __future__ import annotations

import json
import secrets
from pathlib import Path

NAME = "stampcheck"  # the command and package name (also rename the package folder and pyproject.toml)
BRAND = "StampCheck"  # the product name wherever it appears in prose
VERSION = "0.1.2"
CONFIG_FILE = f"{NAME}.yaml"
DB_FILE = f"{NAME}.db"
ENV_PATH = f"{NAME.upper()}_PATH"

FIELDS = ("case_id", "recommended", "decision", "reviewer", "opened_at", "decided_at",
          "notified_at", "category", "executed")
RECOMMENDATIONS = ("approve", "reject")
DECISIONS = ("approve", "reject", "escalate", "timeout_approve", "timeout_reject")
DECIDED = ("approve", "reject", "escalate")  # a human actually decided; timeouts are not decisions

THRESHOLDS: dict[str, float] = {
    "min_cases": 30,
    "max_disagreement_upper": 0.05,
    "max_median_seconds": 30,
    "max_gap_seconds": 1800,
    "drift_recent_days": 14,
    "drift_baseline_days": 28,
    "drift_change": 0.5,
    "logging_dominant_share": 0.99,
    "logging_min_second_value": 5,
    "queue_max_per_day": 200,
}
KEYS = {"thresholds", "columns", "values", "timezone", "csv_delimiter", "pseudonymize_salt"}


class ConfigError(Exception):
    """A bad config or mapping file. The message is shown to the user (exit code 2)."""


def load_config(path: str | None = None, auto: bool = True) -> dict:
    """Defaults merged with `path`, or with ./stampcheck.yaml if it exists and `auto` is set."""
    cfg: dict = {"thresholds": dict(THRESHOLDS), "columns": {}, "values": {}, "timezone": "UTC",
                 "csv_delimiter": None, "pseudonymize_salt": NAME, "path": None}
    if path is None:
        if not (auto and Path(CONFIG_FILE).is_file()):
            return cfg
        path = CONFIG_FILE
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"config file not found: {path}")
    data = _parse(p)
    if unknown := set(data) - KEYS:
        raise ConfigError(f"{p}: unknown keys {sorted(unknown)}; allowed: {sorted(KEYS)}")
    for k, v in (data.get("thresholds") or {}).items():
        if k not in THRESHOLDS:
            raise ConfigError(f"{p}: unknown threshold {k!r}; allowed: {sorted(THRESHOLDS)}")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigError(f"{p}: threshold {k} must be a number, got {v!r}")
        cfg["thresholds"][k] = v
    for f, col in (data.get("columns") or {}).items():
        if f not in FIELDS:
            raise ConfigError(f"{p}: unknown field {f!r} under columns; allowed: {', '.join(FIELDS)}")
        cfg["columns"][f] = None if col in (None, {}) else str(col)
    allowed = {"recommended": RECOMMENDATIONS, "decision": DECISIONS}
    for f, mapping in (data.get("values") or {}).items():
        if f not in allowed:
            raise ConfigError(f"{p}: values can be mapped for recommended and decision, not {f!r}")
        cfg["values"][f] = {}
        for raw, canon in (mapping or {}).items():
            if str(canon).strip().lower() not in allowed[f]:
                raise ConfigError(f"{p}: {f} value {raw!r} maps to {canon!r}; must be one of {', '.join(allowed[f])}")
            cfg["values"][f][str(raw).strip().lower()] = str(canon).strip().lower()
    for k in ("timezone", "csv_delimiter", "pseudonymize_salt"):
        if data.get(k) not in (None, {}):
            cfg[k] = str(data[k])
    cfg["path"] = str(p)
    return cfg


def _parse(p: Path) -> dict:
    text = p.read_text(encoding="utf-8")
    try:
        if p.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            try:
                import yaml
            except ImportError:
                data = mini_yaml(text)
            else:
                data = yaml.safe_load(text)
    except ConfigError:
        raise
    except Exception as e:  # any parser error becomes a readable input error
        raise ConfigError(f"could not read {p}: {e}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{p}: expected key: value pairs at the top level")
    return data


def mini_yaml(text: str) -> dict:
    """The YAML subset our config uses (nested mappings of scalars), so PyYAML stays optional."""
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for n, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, rest = _split_key(line.strip(), n)
        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if rest.strip():
            parent[key] = _scalar(rest)
        else:
            parent[key] = {}
            stack.append((indent, parent[key]))
    return root


def _strip_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i].rstrip()
    return line.rstrip()


def _split_key(s: str, n: int) -> tuple[str, str]:
    if s[0] in "'\"" and (end := s.find(s[0], 1)) > 0 and s[end + 1:end + 2] == ":":
        return s[1:end], s[end + 2:]
    if ": " in s:
        key, rest = s.split(": ", 1)
        return key.strip(), rest
    if s.endswith(":"):
        return s[:-1].strip(), ""
    raise ConfigError(f"line {n}: expected 'key: value', got {s!r}")


def _scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    if s.lower() in ("null", "~"):
        return None
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


INIT_TEMPLATE = """\
# {name} config, written by `{name} init`. Every key is optional.
# `{name} check` reads ./{config} automatically, or pass --config FILE (alias: --mapping).

# Thresholds. All of them are printed in every report.
thresholds:
  min_cases: 30                 # decided cases needed before a reviewer or step is judged
  max_disagreement_upper: 0.05  # sign 1: 95% upper bound on the disagreement rate is below this
  max_median_seconds: 30        # sign 2: median time per case is below this
  max_gap_seconds: 1800         # without opened_at: gaps between a reviewer's decisions longer than this are breaks
  drift_recent_days: 14         # drift compares the most recent N days...
  drift_baseline_days: 28       # ...with the N days before that
  drift_change: 0.5             # time per case falling by 50% or more counts as a trend
  logging_dominant_share: 0.99  # one value on 99%+ of rows looks hard-coded
  logging_min_second_value: 5   # so does a second value seen fewer than 5 times
  queue_max_per_day: 200        # decided cases per reviewer per working day

# Which column in your data holds each field. Columns with common names are found automatically, and
# the check prints the mapping it used. Set a field to null if your data does not have it.
# The minimum is who decided (reviewer), what they decided (decision), when (decided_at), and what the
# system recommended (recommended). Without the recommendation, only the speed checks run.
# opened_at is optional, but it makes the timings exact.
columns:
  # case_id: ticket_id
  # recommended: ai_suggestion     # what the system proposed
  # decision: final_status         # what the human did
  # reviewer: handled_by
  # opened_at: first_opened_at     # when the reviewer opened the case: makes timings exact
  # decided_at: closed_at
  # notified_at: queued_at
  # category: refund_band          # approval step or category; each one gets its own verdict
  # executed: times_executed       # how many times the approved action actually ran

# Your values -> canonical values. Recognised without mapping: approve, approved, accept, accepted,
# reject, rejected, deny, denied, decline, declined, escalate, escalated, timeout_approve, timeout_reject.
# Any other value is listed in the output and its rows are skipped until you map it here.
values:
  recommended:
    # "REFUND": approve
    # "NO_REFUND": reject
  decision:
    # "AUTO_APPROVED_SLA": timeout_approve   # nobody reviewed it before the deadline, approved anyway
    # "AUTO_REJECTED_SLA": timeout_reject

timezone: UTC                  # applied to timestamps that have no offset
csv_delimiter: null            # detected automatically; set ";" or "tab" to force it
pseudonymize_salt: "{salt}"    # used by --pseudonymize; keep it stable so hashes match across runs
"""


def init_text() -> str:
    return INIT_TEMPLATE.format(name=NAME, config=CONFIG_FILE, salt=secrets.token_hex(8))
