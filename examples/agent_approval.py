"""A human approval step in an LLM-agent workflow, with review logging.

The agent proposes a tool call (here: a refund). A person approves, rejects, or escalates it.
stampcheck.review() records when the person saw the proposal (opened_at) and when they decided.
Run: python examples/agent_approval.py   (the agent is a stub, so no API key is needed)
"""
import getpass

import stampcheck


def agent_propose(ticket: dict) -> dict:
    """Stand-in for your agent. It returns the tool call it wants to make and its recommendation."""
    return {"tool": "issue_refund", "amount_eur": ticket["amount_eur"], "recommendation": "approve",
            "why": "order arrived damaged, photo attached, first complaint from this customer"}


def issue_refund(ticket: dict, amount: float) -> None:
    print(f"Refunded EUR {amount:.2f} for {ticket['id']}")


def refund_band(amount: float) -> str:
    return "refund_under_50" if amount < 50 else "refund_50_to_500" if amount <= 500 else "refund_over_500"


def handle(ticket: dict) -> None:
    proposal = agent_propose(ticket)
    with stampcheck.review(ticket["id"], proposal["recommendation"], getpass.getuser(),
                          category=refund_band(proposal["amount_eur"])) as r:
        print(f"\nAgent wants to refund EUR {proposal['amount_eur']:.2f}: {proposal['why']}")
        answer = input("approve / reject / escalate? ").strip().lower()
        r.decision = answer if answer in ("approve", "reject", "escalate") else "escalate"
        r.executed = 0
        if r.decision == "approve":
            issue_refund(ticket, proposal["amount_eur"])
            r.executed = 1


if __name__ == "__main__":
    handle({"id": "T-2041", "amount_eur": 64.90})
    print("Logged to stampcheck.db. Once you have a few weeks of reviews: stampcheck check --source stampcheck.db")
