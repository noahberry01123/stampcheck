"""Timing without opened_at: consecutive-decision gaps, notified_at as an upper bound, and no recommendation."""
from datetime import datetime, timedelta, timezone

from stampcheck.checks import ESTIMATED, run_all
from stampcheck.cli import main
from stampcheck.record import write_rows
from stampcheck.report import html, terminal

T0 = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)


def rows(n=120, gap=5, wait=None, opened=False, agree_every=0, recommended=True, breaks_every=20):
    """One reviewer working a queue: a decision every `gap` seconds, a 2-hour break every `breaks_every` cases.
    wait = seconds from notified_at to decided_at; agree_every = k makes every k-th decision a disagreement."""
    out, t = [], T0
    for i in range(n):
        disagree = agree_every and i % agree_every == 0
        rec = "reject" if i % 7 == 3 else "approve"  # the system recommends a rejection now and then
        dec = {"approve": "reject", "reject": "approve"}[rec] if disagree else rec
        out.append({"case_id": f"C-{i}", "recommended": rec if recommended else None,
                    "decision": dec, "reviewer": "pat", "category": "refunds",
                    "decided_at": t, "opened_at": t - timedelta(seconds=gap - 1) if opened else None,
                    "notified_at": t - timedelta(seconds=wait) if wait is not None else None,
                    "executed": int(dec == "approve")})
        t += timedelta(hours=2) if (i + 1) % breaks_every == 0 else timedelta(seconds=gap)
    return out


def rubber(result):
    return result["reviewers"]["pat"]["findings"][0], result["reviewers"]["pat"]["stats"]


def test_gaps_reveal_a_fast_reviewer_without_opened_at(th):
    f, s = rubber(run_all(rows(gap=5), th))
    assert s["source"] == "gaps" and s["median_s"] == 5
    assert f["verdict"] == "RED" and "at most 5 s per case" in f["message"] and ESTIMATED.strip() in f["message"]


def test_gaps_longer_than_the_break_limit_are_ignored(th):
    data = rows(gap=5, breaks_every=3)  # a 2-hour break after every third case
    _, s = rubber(run_all(data, th))
    assert s["median_s"] == 5
    assert all(r.get("gap_s") is None or r["gap_s"] <= th["max_gap_seconds"] for r in data)
    assert sum(r.get("gap_s") is None for r in data) == 40  # the first case and every case after a break


def test_long_gaps_prove_nothing_so_agreement_alone_is_amber(th):
    f, _ = rubber(run_all(rows(gap=600), th))  # 10 minutes between decisions: maybe reading, maybe not
    assert f["verdict"] == "AMBER" and "Speed can't be confirmed" in f["message"]


def test_fast_notified_to_decided_is_reliable_without_opened_at(th):
    f, s = rubber(run_all(rows(gap=600, wait=8), th))  # queue wait plus reading is under 30 s
    assert s["source"] == "notified_at" and f["verdict"] == "RED"


def test_slow_notified_to_decided_is_not_evidence_of_reading(th):
    f, s = rubber(run_all(rows(gap=600, wait=3600), th))
    assert f["verdict"] == "AMBER" and s["source"] in ("notified_at", "gaps")


def test_opened_at_wins_when_present(th):
    f, s = rubber(run_all(rows(gap=600, wait=8, opened=True), th))
    assert s["source"] == "opened_at" and ESTIMATED.strip() not in f["message"]


def test_engaged_reviewer_with_estimates_is_green(th):
    f, _ = rubber(run_all(rows(gap=600, agree_every=5), th))  # disagrees on 20%
    assert f["verdict"] == "GREEN" and ESTIMATED.strip() in f["message"]


def test_without_recommendation_only_speed_checks_run(th):
    res = run_all(rows(gap=5, recommended=False), th)
    f, s = rubber(res)
    assert s["rate"] is None and f["verdict"] == "AMBER" and "without the system's recommendation" in f["message"]
    assert any("only the speed checks run" in m for m in res["not_possible"])
    logging = [x for x in res["steps"]["refunds"]["findings"] if x["check"] == "logging"][0]
    assert "recommended" not in logging["data"]["suspicious"]  # a missing column isn't "hard-coded"


def test_report_names_the_timing_source(th, tmp_path):
    est = run_all(rows(gap=5), th)
    exact = run_all(rows(gap=600, opened=True), th)
    assert "decision gaps (upper bound)" in html(est) and "opened_at (exact)" in html(exact)
    assert "Timing from gaps between consecutive decisions (an upper bound): pat" in terminal(est, tmp_path, False)
    assert "opened_at (exact, the most precise)" in terminal(exact, tmp_path, False)


def test_csv_without_recommendation_column_loads(tmp_path):
    path = tmp_path / "speed_only.csv"
    lines = ["id,decision,reviewer,decided_at"] + [
        f"{r['case_id']},{r['decision']},{r['reviewer']},{r['decided_at'].isoformat()}" for r in rows(gap=5)]
    path.write_text("\n".join(lines) + "\n")
    assert main(["check", "--source", str(path), "--out", str(tmp_path)]) == 0  # AMBER at most, never RED
