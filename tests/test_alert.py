import json
from unittest import mock
from urllib.error import URLError

import pytest

from stampcheck.cli import main
from stampcheck.record import write_rows
from conftest import add_ids

HOOK = "slack:https://hooks.slack.com/services/T000/B000/XXXX"


@pytest.fixture
def urlopen():
    with mock.patch("stampcheck.alert.urlopen") as m:
        yield m


def sent_text(urlopen) -> str:
    return json.loads(urlopen.call_args.args[0].data)["text"]


def test_no_alert_when_all_green(tmp_path, green_rows, urlopen):
    db = write_rows(add_ids(green_rows), tmp_path / "g.db")
    assert main(["check", "--source", str(db), "--out", str(tmp_path), "--alert", HOOK]) == 0
    urlopen.assert_not_called()


def test_alert_on_red_is_step_level_by_default(tmp_path, demo_rows, urlopen):
    db = write_rows(demo_rows, tmp_path / "d.db")
    main(["check", "--source", str(db), "--out", str(tmp_path), "--alert", HOOK])
    urlopen.assert_called_once()
    text = sent_text(urlopen)
    assert "refund_under_50" in text and "refund_50_to_500" in text
    assert "sam" not in text and "taylor" not in text


def test_per_reviewer_names_reviewers(tmp_path, demo_rows, urlopen):
    db = write_rows(demo_rows, tmp_path / "d.db")
    main(["check", "--source", str(db), "--out", str(tmp_path), "--alert", HOOK, "--per-reviewer"])
    assert "sam" in sent_text(urlopen)


def test_new_drift_alerts_once(tmp_path, drifting_rows, urlopen):
    db = write_rows(add_ids(drifting_rows), tmp_path / "drift.db")
    args = ["check", "--source", str(db), "--out", str(tmp_path), "--alert", HOOK]
    assert main(args) == 0  # AMBER drift only, nothing RED
    assert urlopen.call_count == 1 and "Trending toward rubber-stamping" in sent_text(urlopen)
    main(args)  # same drift as last run: not new, no RED, so no second message
    assert urlopen.call_count == 1


def test_failed_alert_does_not_change_exit_code(tmp_path, demo_rows, urlopen, capsys):
    urlopen.side_effect = URLError("offline")
    db = write_rows(demo_rows, tmp_path / "d.db")
    assert main(["check", "--source", str(db), "--out", str(tmp_path), "--alert", HOOK]) == 1
    assert "could not send the Slack alert" in capsys.readouterr().err
