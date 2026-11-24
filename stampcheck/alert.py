"""Slack alert: posts only when something is RED or a drift finding is new since the last run."""
from __future__ import annotations

import json
from urllib.request import Request, urlopen

from .checks import AMBER, RED
from .config import BRAND


def parse_target(spec: str) -> str:
    """'slack:https://hooks.slack.com/...' -> the webhook URL. Raises ValueError otherwise."""
    kind, _, url = spec.partition(":")
    if kind != "slack" or not url.startswith("https://"):
        raise ValueError(f"--alert must look like slack:https://hooks.slack.com/services/..., got {spec!r}")
    return url


def _drifting(result: dict | None) -> set[tuple[str, str]]:
    if not result:
        return set()
    return {(kind, name) for kind in ("steps", "reviewers") for name, item in result.get(kind, {}).items()
            for f in item["findings"] if f["check"] == "drift" and f["verdict"] in (RED, AMBER)}


def should_alert(result: dict, previous: dict | None) -> bool:
    return result["red"] or bool(_drifting(result) - _drifting(previous))


def message(result: dict, previous: dict | None, per_reviewer: bool, report: str) -> str:
    new = _drifting(result) - _drifting(previous)
    lines = [f"*{BRAND}*: an approval review check needs a look (data up to {result['period']['to'][:10]})"]
    for kind in ("steps", "reviewers") if per_reviewer else ("steps",):
        for name, item in sorted(result[kind].items()):
            hits = [f["message"] for f in item["findings"]
                    if f["verdict"] == RED or (f["check"] == "drift" and (kind, name) in new and f["verdict"] == AMBER)]
            if hits:
                lines.append(f"- {item['verdict']} {name}: {' '.join(hits)}")
    lines.append(f"Report: {report}")
    return "\n".join(lines)


def send(url: str, text: str) -> None:
    req = Request(url, data=json.dumps({"text": text}).encode(), headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as resp:
        resp.read()
