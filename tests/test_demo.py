import json

import pytest

from stampcheck.cli import main
from conftest import verdicts

REVIEWERS = {"alex": "GREEN", "sam": "RED", "jordan": "AMBER", "taylor": "RED", "kim": "GREY"}
STEPS = {"refund_under_50": "RED", "refund_50_to_500": "RED", "refund_over_500": "GREEN"}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    code = main(["demo", "--out", str(out)])
    return code, out, json.loads((out / "result.json").read_text())


def test_exit_code_and_files(demo):
    code, out, _ = demo
    assert code == 1
    html = (out / "report.html").read_text()
    assert "http" not in html  # self-contained: no network
    assert "evidence to look into, not proof" in html


def test_planted_verdicts(demo):
    _, _, res = demo
    assert {n: r["verdict"] for n, r in res["reviewers"].items()} == REVIEWERS
    assert {n: s["verdict"] for n, s in res["steps"].items()} == STEPS


def test_each_planted_problem_is_caught_by_the_right_check(demo):
    _, _, res = demo
    v = verdicts(res)
    sam = res["reviewers"]["sam"]["findings"][0]
    assert sam["verdict"] == "RED" and "218 of 219" in sam["message"]
    assert v["reviewers", "jordan", "rubber_stamp"] == "AMBER"
    assert v["reviewers", "alex", "rubber_stamp"] == "GREEN"
    assert v["reviewers", "kim", "rubber_stamp"] == "GREY"
    # the drifter looks fine over the whole period; only the drift check catches them
    assert v["reviewers", "taylor", "rubber_stamp"] == "GREEN"
    assert v["reviewers", "taylor", "drift"] == "RED"
    assert "time per case went from" in res["reviewers"]["taylor"]["findings"][1]["message"]
    assert [k for k, val in v.items() if k[2] == "drift" and val == "RED"] == [
        ("steps", "refund_50_to_500", "drift"), ("reviewers", "taylor", "drift")]
    timeouts = {n: s["findings"] for n, s in res["steps"].items()}
    assert [f["data"]["count"] for f in timeouts["refund_50_to_500"] if f["check"] == "timeouts"] == [25]
    assert [k[1] for k, val in v.items() if k[2] == "timeouts" and val == "RED"] == ["refund_50_to_500"]
    dups = [f for f in res["steps"]["refund_under_50"]["findings"] if f["check"] == "duplicates"][0]
    assert dups["verdict"] == "RED" and list(dups["data"]["cases"].values()) == [3]
    assert [k[1] for k, val in v.items() if k[2] == "duplicates" and val == "RED"] == ["refund_under_50"]
    assert all(val == "GREEN" for k, val in v.items() if k[2] == "logging")
    assert not any(k[2] == "queue" for k in v)


def test_terminal_summary(demo, capsys):
    main(["demo", "--out", str(demo[1])])
    out = " ".join(capsys.readouterr().out.split())  # undo line wrapping
    assert "agreed with the system on 218 of 219 decided cases, median 4 s" in out
    assert "Approval steps" in out and "Thresholds:" in out
