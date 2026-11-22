"""Built-in demo: 8 weeks of synthetic refund approvals with known, planted problems.

An AI support agent recommends whether to refund a customer; human reviewers approve or reject.
Three approval steps by refund size, five reviewers (all fictional):
  alex    careful senior reviewer, refunds over EUR 500               -> GREEN
  sam     approves almost everything in ~4 s, refunds under EUR 50    -> RED
  jordan  fast but still disagrees often, refunds under EUR 50        -> AMBER
  taylor  careful for 5 weeks, then drifts to ~6 s clicks, EUR 50-500 -> drift RED
  kim     joined in the last two weeks, only 12 cases                  -> GREY
Plus 25 overnight timeouts that were approved anyway (EUR 50-500) and one small refund that was
paid out three times (a retry bug).
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

SEED = 22
START = datetime(2026, 9, 7, tzinfo=timezone.utc)  # a Monday
DAYS = [START + timedelta(days=7 * w + d) for w in range(8) for d in range(5)]  # 40 working days
SMALL, MID, LARGE = "refund_under_50", "refund_50_to_500", "refund_over_500"


def reviewer_rows(rng: random.Random, reviewer: str, step: str, days: list[datetime], per_day: tuple[int, int],
                  median_s: float, p_disagree: float, p_reject: float = 0.15, sigma: float = 0.45) -> list[dict]:
    """One reviewer working through their queue: open a case, decide, open the next."""
    rows = []
    for day in days:
        t = day + timedelta(hours=7, minutes=rng.randint(0, 90))
        for _ in range(rng.randint(*per_day)):
            t += timedelta(seconds=rng.randint(30, 900))
            dwell = timedelta(seconds=max(1, round(rng.lognormvariate(math.log(median_s), sigma))))
            rec = "reject" if rng.random() < p_reject else "approve"
            dec = rec
            if rng.random() < p_disagree:
                dec = "escalate" if rng.random() < 0.2 else {"approve": "reject", "reject": "approve"}[rec]
            rows.append({"recommended": rec, "decision": dec, "reviewer": reviewer, "opened_at": t,
                         "decided_at": t + dwell, "notified_at": t - timedelta(seconds=rng.randint(60, 10800)),
                         "category": step, "executed": int(dec == "approve")})
            t += dwell
    return rows


def generate(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed)
    # sam: 219 cases, the agent recommended a refund every time, sam approved 218 of them.
    counts = [5] * 40
    for i in rng.sample(range(40), 19):
        counts[i] = 6
    sam = [r for day, c in zip(DAYS, counts)
           for r in reviewer_rows(rng, "sam", SMALL, [day], (c, c), 4, 0, p_reject=0, sigma=0.35)]
    sam[rng.randrange(40)].update(decision="reject", executed=0)  # the one disagreement, in week 1 or 2
    jordan = reviewer_rows(rng, "jordan", SMALL, DAYS, (4, 8), 12, 0.15, p_reject=0.12, sigma=0.4)
    rng.choice([r for r in jordan if r["decision"] == "approve"])["executed"] = 3  # paid out three times
    alex = reviewer_rows(rng, "alex", LARGE, DAYS, (3, 7), 150, 0.10, p_reject=0.2, sigma=0.5)
    taylor = (reviewer_rows(rng, "taylor", MID, DAYS[:25], (4, 6), 110, 0.10, p_reject=0.12)
              + reviewer_rows(rng, "taylor", MID, DAYS[25:30], (7, 9), 60, 0.04, p_reject=0.12)
              + reviewer_rows(rng, "taylor", MID, DAYS[30:], (11, 13), 6, 0.0, p_reject=0.12, sigma=0.4))
    kim = reviewer_rows(rng, "kim", LARGE, DAYS[34:], (2, 2), 5, 0.0, p_reject=0.1)

    system = []
    night = datetime(2026, 10, 13, 20, 40, tzinfo=timezone.utc)  # timeout default flipped to approve overnight
    for _ in range(25):
        queued = night + timedelta(seconds=rng.randint(0, 9000))
        system.append({"recommended": "approve", "decision": "timeout_approve", "reviewer": None,
                       "opened_at": None, "decided_at": queued + timedelta(hours=4), "notified_at": queued,
                       "category": MID, "executed": 1})
    for step in (SMALL, MID, LARGE, MID, SMALL, LARGE):  # ordinary timeouts that correctly fail closed
        queued = rng.choice(DAYS) + timedelta(hours=rng.randint(8, 15), seconds=rng.randint(0, 3599))
        system.append({"recommended": rng.choice(["approve", "reject"]), "decision": "timeout_reject",
                       "reviewer": None, "opened_at": None, "decided_at": queued + timedelta(hours=4),
                       "notified_at": queued, "category": step, "executed": 0})

    rows = sorted(sam + jordan + alex + taylor + kim + system, key=lambda r: (r["notified_at"], r["category"]))
    for i, r in enumerate(rows):
        r["case_id"] = f"R-{10001 + i}"
    return rows
