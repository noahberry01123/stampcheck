"""A FastAPI approval endpoint for refunds proposed by an AI support agent, logging every review.

The line that matters is in open_case(): it records when the reviewer actually opened the case.
Run: pip install fastapi uvicorn && uvicorn examples.fastapi_endpoint:app --reload
"""
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import stampcheck

app = FastAPI()
# Refund proposals from the AI agent. In your app these live in your database.
CASES = {"R-1001": {"customer": "C-77", "amount_eur": 38.0, "recommended": "approve",
                    "reason": "parcel marked lost by carrier", "created_at": datetime.now(timezone.utc)}}
OPENED: dict[tuple[str, str], datetime] = {}  # (case_id, reviewer) -> opened_at; store it in your DB


def refund_band(amount: float) -> str:
    return "refund_under_50" if amount < 50 else "refund_50_to_500" if amount <= 500 else "refund_over_500"


def issue_refund(case: dict) -> None:
    ...  # your payment provider call


class Decision(BaseModel):
    reviewer: str
    decision: str  # "approve" | "reject" | "escalate"


@app.get("/refunds/{case_id}")
def open_case(case_id: str, reviewer: str) -> dict:
    if case_id not in CASES:
        raise HTTPException(404)
    OPENED.setdefault((case_id, reviewer), datetime.now(timezone.utc))  # the reviewer is looking at it now
    return CASES[case_id]


@app.post("/refunds/{case_id}/decision")
def decide(case_id: str, body: Decision) -> dict:
    case = CASES[case_id]
    executed = 0
    if body.decision == "approve":
        issue_refund(case)
        executed = 1
    stampcheck.record_review(case_id, case["recommended"], body.decision, body.reviewer,
                            opened_at=OPENED.get((case_id, body.reviewer)),
                            decided_at=datetime.now(timezone.utc), notified_at=case["created_at"],
                            category=refund_band(case["amount_eur"]), executed=executed)
    return {"case_id": case_id, "decision": body.decision}
