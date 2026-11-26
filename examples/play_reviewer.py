"""Be the reviewer: approve or reject fake refund requests that an "AI agent" recommends.

Every decision is logged with stampcheck.review(), which records when you opened each case and
when you decided. Afterwards, run `stampcheck check --source my_reviews.db` to see what it says
about you. Part of the hands-on tutorial at https://stampcheck.io/tutorial/

Usage:
    python play_reviewer.py careful         # 40 cases: read each one properly
    python play_reviewer.py fast 80         # 80 cases: just hold Enter (go with the AI every time)

Keys: a = approve, r = reject, e = escalate, Enter = go with the AI's recommendation.
"""
import random
import sys

import stampcheck

REASONS_OK = ["parcel lost by the carrier (tracking confirms)", "item arrived damaged, photo attached",
              "wrong size sent, item returned unused", "order cancelled before shipping",
              "duplicate charge on the card statement"]
RED_FLAGS = ["this is the customer's 4th refund this month", "the refund is larger than the order total",
             "the order was never paid", "tracking shows the parcel was delivered and signed for",
             "the account was opened yesterday"]


def make_cases(n: int, rng: random.Random, prefix: str = "P") -> list[dict]:
    cases = []
    for i in range(n):
        amount = round(rng.choice([rng.uniform(5, 49), rng.uniform(50, 500), rng.uniform(501, 1500)]), 2)
        case = {"id": f"{prefix}-{1000 + i}", "amount": amount, "reason": rng.choice(REASONS_OK), "flag": None,
                "recommended": "approve"}
        roll = rng.random()
        if roll < 0.15:    # a problem the AI missed: it recommends approve anyway
            case["flag"] = rng.choice(RED_FLAGS)
        elif roll < 0.35:  # the AI is over-cautious: recommends reject for a fine case
            case["recommended"] = "reject"
        cases.append(case)
    return cases


def main() -> None:
    reviewer = sys.argv[1] if len(sys.argv) > 1 else "me"
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    rng = random.Random()
    run = f"{reviewer}-{rng.randrange(16**4):04x}"  # unique case IDs per run, so rounds never collide
    cases = make_cases(total, rng, prefix=run)
    print(f"\nYou are reviewing as '{reviewer}': {total} refund requests. a = approve, r = reject, "
          "e = escalate, Enter = go with the AI.\n")
    for n, c in enumerate(cases, 1):
        with stampcheck.review(c["id"], c["recommended"], reviewer, category="refund_requests",
                               path="my_reviews.db") as r:
            print(f"--- Case {n}/{total}: {c['id']}  refund of EUR {c['amount']:.2f}")
            print(f"    Customer says: {c['reason']}")
            if c["flag"]:
                print(f"    Account notes: {c['flag']}")
            print(f"    AI agent recommends: {c['recommended'].upper()}")
            answer = input("    Your decision [a/r/e, Enter = go with the AI]: ").strip().lower()
            r.decision = {"a": "approve", "r": "reject", "e": "escalate"}.get(answer[:1], c["recommended"])
            r.executed = 1 if r.decision == "approve" else 0
    print("\nDone. Now run:  stampcheck check --source my_reviews.db\n")


if __name__ == "__main__":
    main()
