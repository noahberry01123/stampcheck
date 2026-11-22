import random
import sys
from pathlib import Path

import pytest

from stampcheck.config import THRESHOLDS
from stampcheck.demo import DAYS, LARGE, generate, reviewer_rows

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))  # for make_messy


def verdicts(result: dict) -> dict:
    """Every verdict in a result, keyed by (kind, name, check)."""
    return {(kind, name, f["check"]): f["verdict"] for kind in ("steps", "reviewers")
            for name, item in result[kind].items() for f in item["findings"]}


@pytest.fixture
def th():
    return dict(THRESHOLDS)


@pytest.fixture
def demo_rows():
    return generate()


@pytest.fixture
def green_rows():
    """One engaged reviewer, no timeouts or duplicates: nothing to report."""
    return reviewer_rows(random.Random(3), "alex", LARGE, DAYS, (3, 7), 150, 0.10, p_reject=0.2, sigma=0.5)


@pytest.fixture
def drifting_rows():
    """Time per case halves (120 s -> 45 s) but stays out of the rubber-stamp zone: AMBER drift, no RED."""
    rng = random.Random(4)
    return (reviewer_rows(rng, "pat", LARGE, DAYS[:30], (5, 7), 120, 0.12, p_reject=0.2)
            + reviewer_rows(rng, "pat", LARGE, DAYS[30:], (5, 7), 45, 0.12, p_reject=0.2))


def add_ids(rows: list[dict]) -> list[dict]:
    for i, r in enumerate(rows):
        r["case_id"] = f"C-{i}"
    return rows
