import pytest

from stampcheck.checks import GREY, fmt_s, rubber_stamp, wilson_upper


def test_wilson_known_values():
    assert wilson_upper(1, 219) == pytest.approx(0.0254, abs=5e-4)
    assert wilson_upper(0, 90) == pytest.approx(0.041, abs=5e-4)


def test_wilson_edges():
    assert wilson_upper(0, 0) == 1.0
    assert wilson_upper(10, 10) == 1.0
    assert wilson_upper(5, 100) > 0.05  # 5% observed is not "below 5%" once uncertainty is counted


def test_fmt_seconds():
    assert fmt_s(6) == "6 s"
    assert fmt_s(120) == "2 min"
    assert fmt_s(92) == "1 min 32 s"
    assert fmt_s(None) == "n/a"


def test_too_few_cases_is_grey_not_green(demo_rows, th):
    kim = [r for r in demo_rows if r["reviewer"] == "kim"]
    assert rubber_stamp(kim, th)["verdict"] == GREY
