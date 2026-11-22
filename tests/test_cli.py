from stampcheck.cli import main
from stampcheck.config import load_config
from stampcheck.record import write_rows
from conftest import add_ids


def test_exit_0_when_nothing_is_red(tmp_path, green_rows):
    db = write_rows(add_ids(green_rows), tmp_path / "green.db")
    assert main(["check", "--source", str(db), "--out", str(tmp_path)]) == 0


def test_exit_1_when_something_is_red(tmp_path, demo_rows):
    db = write_rows(demo_rows, tmp_path / "demo.db")
    assert main(["check", "--source", str(db), "--out", str(tmp_path)]) == 1


def test_exit_2_on_input_errors(tmp_path, capsys):
    assert main(["check", "--source", str(tmp_path / "nope.csv")]) == 2
    no_decision = tmp_path / "no_decision.csv"
    no_decision.write_text("id,recommendation,decided_at\n1,approve,2026-11-02T10:00:00Z\n")
    assert main(["check", "--source", str(no_decision), "--out", str(tmp_path)]) == 2
    assert "no column found for decision" in capsys.readouterr().err
    bad_map = tmp_path / "bad.yaml"
    bad_map.write_text("thresholds:\n  min_case: 30\n")
    assert main(["check", "--source", str(no_decision), "--mapping", str(bad_map)]) == 2
    assert main(["check", "--source", "postgresql://u:secret@localhost/db"]) == 2
    assert "secret" not in capsys.readouterr().err
    assert main(["check", "--source", str(no_decision), "--alert", "email:me"]) == 2


def test_init_writes_a_loadable_config(tmp_path):
    path = tmp_path / "stampcheck.yaml"
    assert main(["init", "--path", str(path)]) == 0
    assert load_config(str(path))["thresholds"]["min_cases"] == 30
    assert main(["init", "--path", str(path)]) == 2  # never overwrites without --force
    assert main(["init", "--path", str(path), "--force"]) == 0
