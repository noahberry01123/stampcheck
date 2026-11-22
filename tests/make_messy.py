"""Regenerate examples/messy.csv: the demo data exported the way real systems often do it.

Semicolons, renamed and extra columns, local times with two offset styles, the team's own enum
values, blanks instead of zeros, shuffled rows, and a few garbage rows. Run: python tests/make_messy.py
"""
from __future__ import annotations

import csv
import io
import random
from pathlib import Path
from zoneinfo import ZoneInfo

from stampcheck.demo import generate

OUT = Path(__file__).resolve().parent.parent / "examples" / "messy.csv"
BERLIN = ZoneInfo("Europe/Berlin")
HEADER = ["Ref", "Refund Band", "Amount EUR", "AI Suggestion", "Outcome", "Handled By", "Sent To Queue",
          "First Opened", "Closed At", "Times Executed", "Customer Country", "Channel"]
REC = {"approve": "REFUND", "reject": "NO_REFUND"}
DEC = {"approve": "Approved", "reject": "Rejected", "escalate": "ESCALATED",
       "timeout_approve": "AUTO_APPROVED_SLA", "timeout_reject": "AUTO_REJECTED_SLA"}
AMOUNT = {"refund_under_50": (5, 49), "refund_50_to_500": (50, 500), "refund_over_500": (501, 4000)}
GARBAGE = [
    [""] * len(HEADER),                                                          # empty row
    ["TOTAL", "", "", "", "", "", "", "", "", "948", "", ""],                    # summary row
    ["R-99001", "refund_under_50", "12,00", "REFUND", "Approved", "sam", "", "", "not a date", "1", "DE", "chat"],
    ["R-99002", "refund_over_500", "780,00", "REFUND", "maybe", "alex", "", "", "2026-10-01 10:00:00+02:00",
     "", "AT", "email"],
    ["R-99003", "refund_50_to_500"],                                             # truncated line
]


def stamp(dt, i: int) -> str:
    if dt is None:
        return ""
    local = dt.astimezone(BERLIN)
    return local.isoformat(sep=" ") if i % 2 else local.strftime("%Y-%m-%dT%H:%M:%S%z")


def build() -> str:
    rng = random.Random(5)
    lines = []
    for i, r in enumerate(generate()):
        lo, hi = AMOUNT[r["category"]]
        lines.append([r["case_id"], r["category"], f"{rng.uniform(lo, hi):.2f}".replace(".", ","),
                      REC[r["recommended"]], DEC[r["decision"]], r["reviewer"] or "", stamp(r["notified_at"], i),
                      stamp(r["opened_at"], i), stamp(r["decided_at"], i), str(r["executed"] or ""),
                      rng.choice(["DE", "FR", "NL", "AT", "ES"]), rng.choice(["chat", "email", "phone"])])
    lines += GARBAGE
    rng.shuffle(lines)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(HEADER)
    w.writerows(lines)
    return buf.getvalue()


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT}")
