"""Where the report is saved and how to open it: printed by demo and check; only demo opens a browser."""
from pathlib import Path
from unittest import mock

from stampcheck.cli import main, open_command
from stampcheck.record import write_rows


def test_demo_opens_the_report_and_prints_where_it_is(tmp_path, capsys):
    with mock.patch("stampcheck.cli.webbrowser.open", return_value=True) as browser:
        main(["demo", "--out", str(tmp_path)])
    browser.assert_called_once_with((tmp_path / "report.html").resolve().as_uri())
    out = capsys.readouterr().out
    assert f"Report saved to: {(tmp_path / 'report.html').resolve()}" in out
    assert "To open it again: " in out


def test_no_open_skips_the_browser_but_still_prints_how_to_open(tmp_path, capsys):
    with mock.patch("stampcheck.cli.webbrowser.open") as browser:
        main(["demo", "--out", str(tmp_path), "--no-open"])
    browser.assert_not_called()
    out = capsys.readouterr().out
    assert "Report saved to: " in out and "To open it: " in out and "again" not in out.split("Report saved to")[1]


def test_no_browser_available_is_fine(tmp_path, capsys):
    with mock.patch("stampcheck.cli.webbrowser.open", side_effect=RuntimeError("no display")):
        assert main(["demo", "--out", str(tmp_path)]) == 1
    assert "To open it: " in capsys.readouterr().out


def test_check_never_opens_a_browser_but_prints_the_lines(tmp_path, demo_rows, capsys):
    db = write_rows(demo_rows, tmp_path / "d.db")
    with mock.patch("stampcheck.cli.webbrowser.open") as browser:
        main(["check", "--source", str(db), "--out", str(tmp_path / "out")])
    browser.assert_not_called()
    out = capsys.readouterr().out
    assert f"Report saved to: {(tmp_path / 'out' / 'report.html').resolve()}" in out and "To open it: " in out


def test_open_command_per_operating_system(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert open_command(Path("report.html"), "darwin") == "open report.html"
    assert open_command(Path("report.html"), "linux") == "xdg-open report.html"
    assert open_command(Path("report.html"), "win32") == "start report.html"
    assert open_command(Path("my results/report.html"), "darwin") == "open 'my results/report.html'"
    assert open_command(Path("my results/report.html"), "win32") == 'start "" "my results/report.html"'
