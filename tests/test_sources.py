import csv
import json
from datetime import datetime, timedelta, timezone

import pytest

import stampcheck
from conftest import ROOT, verdicts
from make_messy import build
from stampcheck.checks import ESTIMATED, run_all
from stampcheck.config import ConfigError, init_text, load_config, mini_yaml
from stampcheck.record import write_rows
from stampcheck.sources import InputError, load

MESSY, MAPPING = ROOT / "examples" / "messy.csv", ROOT / "examples" / "mapping.yaml"


def test_messy_csv_matches_clean_input(demo_rows, th):
    rows, q = load(str(MESSY), load_config(str(MAPPING)))
    assert verdicts(run_all(rows, th)) == verdicts(run_all(demo_rows, th))
    assert q["rows_used"] == len(demo_rows)
    assert q["skipped"] == {"case_id missing": 1, "recommended missing": 2, "decided_at unreadable": 1,
                            "unmapped decision value": 1}
    assert q["unmapped"] == {"decision": {"maybe": 1}}
    assert q["columns"]["decision"] == "Outcome"  # auto-detected next to the explicit mapping


def test_committed_messy_csv_is_current():
    assert MESSY.read_text(encoding="utf-8") == build()


def test_unmapped_values_are_listed_not_guessed(tmp_path):
    columns_only = tmp_path / "columns_only.yaml"
    columns_only.write_text(MAPPING.read_text().split("values:")[0])
    with pytest.raises(InputError, match="'REFUND'"):  # every row is skipped, and the message names the value
        load(str(MESSY), load_config(str(columns_only)))


def test_missing_opened_at_uses_estimates_and_never_a_false_green(demo_rows, th):
    for r in demo_rows:
        r["opened_at"] = None
    res = run_all(demo_rows, th)
    sam = res["reviewers"]["sam"]["findings"][0]
    # sam agrees with nearly everything; the estimated timing (an upper bound) can't prove speed here
    assert sam["verdict"] == "AMBER" and "Speed can't be confirmed" in sam["message"]
    assert ESTIMATED.strip() in sam["message"]
    assert res["reviewers"]["sam"]["stats"]["source"] in ("gaps", "notified_at")
    assert any(ESTIMATED.strip() in m for m in res["not_possible"])
    assert not any(r["findings"][0]["verdict"] == "RED" for r in res["reviewers"].values())


def test_csv_without_opened_at_column(tmp_path, demo_rows, th):
    path = tmp_path / "no_opened.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "recommendation", "decision", "reviewer", "reviewed_at"])
        for r in demo_rows:
            w.writerow([r["case_id"], r["recommended"], r["decision"], r["reviewer"] or "",
                        r["decided_at"].isoformat()])
    rows, q = load(str(path), load_config(auto=False))
    assert "opened_at" in q["missing_columns"]
    sam = run_all(rows, th)["reviewers"]["sam"]
    assert sam["stats"]["source"] == "gaps" and sam["verdict"] == "AMBER"


def test_record_review_round_trip(tmp_path, caplog):
    t = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    for name in ("r.db", "r.jsonl"):
        path = tmp_path / name
        stampcheck.record_review("A-1", "approve", "approve", "sam", t, t + timedelta(seconds=4),
                                notified_at=t - timedelta(hours=1), category="refund_under_50", executed=1, path=path)
        with stampcheck.review("A-2", "reject", "sam", category="refund_under_50", path=path) as r:
            r.decision, r.executed = "reject", 0
        rows, q = load(str(path), load_config(auto=False))
        assert [x["case_id"] for x in rows] == ["A-1", "A-2"]
        assert rows[0]["decided_at"] - rows[0]["opened_at"] == timedelta(seconds=4)
        assert rows[1]["opened_at"] <= rows[1]["decided_at"]
        assert q["missing_columns"] == []
    # never raises into the approval flow: bad values and failed writes become warnings
    stampcheck.record_review("A-3", "approve", "yes", "sam", t, t, path=tmp_path / "x.db")
    stampcheck.record_review("A-4", "approve", "approve", "sam", t, t, path=tmp_path / "missing" / "x.db")
    assert "decision should be one of" in caplog.text and "could not record review" in caplog.text


def test_naive_timestamps_use_config_timezone(tmp_path):
    path = tmp_path / "naive.jsonl"
    path.write_text(json.dumps({"case_id": "1", "recommended": "approve", "decision": "approve",
                                "decided_at": "2026-11-02 10:00:00"}) + "\n")
    rows, q = load(str(path), {**load_config(auto=False), "timezone": "Europe/Berlin"})
    assert rows[0]["decided_at"] == datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    assert any("without a timezone" in k for k in q["notes"])


def _drop_empty(d):
    return {k: _drop_empty(v) if isinstance(v, dict) else v for k, v in d.items() if v not in ({}, None)}


def test_mini_yaml_matches_pyyaml():
    yaml = pytest.importorskip("yaml")
    for text in (MAPPING.read_text(), init_text()):
        assert _drop_empty(mini_yaml(text)) == _drop_empty(yaml.safe_load(text))


def test_bad_config_is_an_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("colums:\n  case_id: id\n")
    with pytest.raises(ConfigError, match="unknown keys"):
        load_config(str(bad))
    bad.write_text("values:\n  decision:\n    AUTO: approved_later\n")
    with pytest.raises(ConfigError, match="must be one of"):
        load_config(str(bad))
