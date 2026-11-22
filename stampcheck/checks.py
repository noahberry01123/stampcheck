"""The checks. Each returns a finding: a verdict (GREEN / AMBER / RED / GREY) and one plain sentence."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from statistics import median

from .config import DECIDED, NAME, VERSION

GREEN, AMBER, RED, GREY = "GREEN", "AMBER", "RED", "GREY"
RANK = {GREY: 0, GREEN: 1, AMBER: 2, RED: 3}
Z = 1.96  # 95% interval


def wilson_upper(k: int, n: int, z: float = Z) -> float:
    """Upper end of the Wilson score interval for k events in n trials."""
    if n == 0:
        return 1.0
    p = k / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + margin) / (1 + z * z / n))


def fmt_s(s: float | None) -> str:
    if s is None:
        return "n/a"
    if s < 60:
        return f"{s:.0f} s"
    if s < 3600:
        m, sec = divmod(round(s), 60)
        return f"{m} min {sec} s" if sec else f"{m} min"
    return f"{s / 3600:.1f} h"


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}" if x >= 0.1 or x == 0 else f"{x:.1%}"


def stats(rows: list[dict]) -> dict:
    """Disagreement and time-per-case figures for the cases a human actually decided."""
    decided = [r for r in rows if r["decision"] in DECIDED]
    n = len(decided)
    k = sum(r["decision"] != r["recommended"] for r in decided)
    times = [(r["decided_at"] - r["opened_at"]).total_seconds() for r in decided if r["opened_at"]]
    waits = [(r["decided_at"] - r["notified_at"]).total_seconds() for r in decided
             if r["notified_at"] and not r["opened_at"]]
    return {"n": n, "disagree": k, "rate": k / n if n else None, "upper": wilson_upper(k, n),
            "median_s": median(times) if times else None, "timed": len(times),
            "median_from_notified_s": median(waits) if waits else None}


def signs(s: dict, th: dict) -> tuple[bool, bool] | None:
    """(agrees almost always, decides fast), or None when there is not enough timed data."""
    if s["n"] < th["min_cases"] or s["timed"] < th["min_cases"]:
        return None
    return s["upper"] < th["max_disagreement_upper"], s["median_s"] < th["max_median_seconds"]


def finding(check: str, verdict: str, message: str, **data) -> dict:
    return {"check": check, "verdict": verdict, "message": message, "data": data}


def rubber_stamp(rows: list[dict], th: dict) -> dict:
    s = stats(rows)
    n, k, minc = s["n"], s["disagree"], th["min_cases"]
    agreed = f"agreed with the system on {n - k} of {n} decided cases"
    if n < minc:
        return finding("rubber_stamp", GREY, f"Only {n} decided cases; at least {minc} are needed to judge.", **s)
    if s["timed"] < minc:
        why = "No opened_at recorded" if s["timed"] == 0 else f"Only {s['timed']} of {n} cases have opened_at"
        msg = f"{why}: rubber-stamp check not possible. Use record_review to start logging it."
        if s["upper"] < th["max_disagreement_upper"]:
            msg += f" Worth a look anyway: {agreed}."
        if s["median_from_notified_s"] is not None:
            msg += (f" Time from notification ({fmt_s(s['median_from_notified_s'])}) includes queue wait,"
                    " so it can't tell reading from clicking.")
        return finding("rubber_stamp", GREY, msg, **s)
    agree, fast = signs(s, th)
    med = fmt_s(s["median_s"])
    if agree and fast:
        return finding("rubber_stamp", RED, f"Looks like rubber-stamping: {agreed}, median {med} from opening "
                                            "to decision.", **s)
    if agree:
        return finding("rubber_stamp", AMBER, f"One warning sign: {agreed}, but a median of {med} per case "
                                              "suggests the cases are being read.", **s)
    if fast:
        return finding("rubber_stamp", AMBER, f"One warning sign: fast (median {med} per case), but still "
                                              f"disagrees with the system on {pct(s['rate'])} of cases.", **s)
    return finding("rubber_stamp", GREEN, f"Engaged: disagrees with the system on {pct(s['rate'])} of cases, "
                                          f"median {med} per case.", **s)


def weeks(days: float) -> str:
    return f"{days // 7:g} weeks" if days % 7 == 0 else f"{days:g} days"


def drift(rows: list[dict], th: dict, end: datetime) -> dict:
    """Last drift_recent_days vs the drift_baseline_days before, both ending at `end`."""
    recent_from = end - timedelta(days=th["drift_recent_days"])
    base_from = recent_from - timedelta(days=th["drift_baseline_days"])
    a = stats([r for r in rows if base_from <= r["decided_at"] < recent_from])
    b = stats([r for r in rows if r["decided_at"] >= recent_from])
    span = f"the last {weeks(th['drift_recent_days'])} vs the {weeks(th['drift_baseline_days'])} before"
    minc = th["min_cases"]
    if min(a["n"], b["n"]) < minc:
        return finding("drift", GREY, f"Not enough cases to compare {span} ({b['n']} vs {a['n']}; "
                                      f"need {minc} in each).", baseline=a, recent=b)
    trends = []
    if min(a["timed"], b["timed"]) >= minc and b["median_s"] <= a["median_s"] * (1 - th["drift_change"]):
        trends.append(f"time per case went from {fmt_s(a['median_s'])} to {fmt_s(b['median_s'])}")
    if b["upper"] < a["rate"]:
        trends.append(f"disagreement fell from {pct(a['rate'])} to {pct(b['rate'])}")
    trend = " and ".join(trends)
    zone_a, zone_b = signs(a, th) == (True, True), signs(b, th) == (True, True)
    if zone_b and not zone_a:
        return finding("drift", RED, f"Drifted into the rubber-stamp zone: {trend or 'now agrees and decides fast'}"
                                     f" ({span}).", baseline=a, recent=b)
    if trend and not zone_b:
        return finding("drift", AMBER, f"Trending toward rubber-stamping: {trend} ({span}), not in the "
                                       "rubber-stamp zone yet.", baseline=a, recent=b)
    if zone_a and zone_b:
        return finding("drift", GREEN, "No change: already in the rubber-stamp zone in both periods.",
                       baseline=a, recent=b)
    return finding("drift", GREEN, f"Stable: median {fmt_s(a['median_s'])} then {fmt_s(b['median_s'])} per case, "
                                   f"disagreement {pct(a['rate'])} then {pct(b['rate'])} ({span}).",
                   baseline=a, recent=b)


def timeouts(rows: list[dict], th: dict) -> dict:
    hits = sorted(r["decided_at"] for r in rows if r["decision"] == "timeout_approve")
    total = sum(r["decision"].startswith("timeout") for r in rows)
    if not hits:
        msg = f"No timeouts ended in approval ({total} timed out, all rejected)." if total else "No timeouts."
        return finding("timeouts", GREEN, msg, count=0, total=total)
    when = f"between {hits[0]:%Y-%m-%d %H:%M} and {hits[-1]:%Y-%m-%d %H:%M} UTC" if len(hits) > 1 \
        else f"at {hits[0]:%Y-%m-%d %H:%M} UTC"
    return finding("timeouts", RED, f"{len(hits)} cases nobody reviewed before the deadline were approved "
                                    f"anyway, {when}.", count=len(hits), total=total)


def duplicates(rows: list[dict], th: dict) -> dict:
    if all(r["executed"] is None for r in rows):
        return finding("duplicates", GREY, "No executed column: duplicate-execution check not possible.")
    runs: Counter = Counter()
    approved = set()
    for r in rows:
        runs[r["case_id"]] += r["executed"] or 0
        if r["decision"] in ("approve", "timeout_approve"):
            approved.add(r["case_id"])
    dups = sorted(((c, n) for c, n in runs.items() if c in approved and n > 1), key=lambda x: (-x[1], x[0]))
    if not dups:
        return finding("duplicates", GREEN, "Every approval was executed at most once.", cases={})
    names = ", ".join(f"case {c} ran {n} times" for c, n in dups[:3])
    return finding("duplicates", RED, f"{len(dups)} approval{'s were' if len(dups) > 1 else ' was'} used for more "
                                      f"than one action ({names}); often a retry or idempotency bug.",
                   cases=dict(dups))


def logging_quality(rows: list[dict], th: dict) -> dict:
    if len(rows) < th["min_cases"]:
        return finding("logging", GREY, f"Only {len(rows)} rows; too few to tell whether logging is hard-coded.",
                       suspicious=[])
    issues, suspicious = [], []
    for col in ("recommended", "decision"):
        top = Counter(r[col] for r in rows).most_common(2)
        share, second = top[0][1] / len(rows), top[1][1] if len(top) > 1 else 0
        if share >= th["logging_dominant_share"] or second < th["logging_min_second_value"]:
            suspicious.append(col)
            issues.append(f"{col} is '{top[0][0]}' on {share:.1%} of rows (next value: {second} times)")
    if not issues:
        return finding("logging", GREEN, "The recommended and decision columns both vary.", suspicious=[])
    return finding("logging", AMBER, f"Your logging may be hard-coded: {'; '.join(issues)}. Check it before "
                                     "trusting the numbers built on it.", suspicious=suspicious)


def per_day(rows: list[dict]) -> float | None:
    """Mean decided cases per reviewer per active day."""
    days = Counter((r["reviewer"], r["decided_at"].date()) for r in rows
                   if r["reviewer"] and r["decision"] in DECIDED)
    return sum(days.values()) / len(days) if days else None


def queue_load(rows: list[dict], th: dict) -> dict | None:
    load = per_day(rows)
    if load is None or load <= th["queue_max_per_day"]:
        return None
    return finding("queue", AMBER, f"Queue overload: ~{load:.0f} cases per reviewer per working day (limit "
                                   f"{th['queue_max_per_day']:g}), which leaves little time to read each one.",
                   per_day=load)


def worst(findings: list[dict]) -> str:
    return max((f["verdict"] for f in findings), key=RANK.get, default=GREY)


def weekly(rows: list[dict]) -> list[dict]:
    by_week = group(rows, lambda r: (r["decided_at"].date() - timedelta(days=r["decided_at"].weekday())).isoformat())
    return [{"week": w, **{k: s[k] for k in ("n", "rate", "median_s")}}
            for w, s in ((w, stats(rs)) for w, rs in sorted(by_week.items()))]


def group(rows: list[dict], key: str | Callable) -> dict[str, list[dict]]:
    out: dict = defaultdict(list)
    for r in rows:
        out[key(r) if callable(key) else r[key]].append(r)
    return out


def _cap(findings: list[dict], why: str) -> None:
    """Logging looks hard-coded: report RED rubber-stamp/drift findings as AMBER instead of trusting them."""
    for f in findings:
        if f["check"] in ("rubber_stamp", "drift") and f["verdict"] == RED:
            f["verdict"], f["message"] = AMBER, f"{f['message']} (Not trusted: {why}.)"


def _attach_cause(findings: list[dict], queue: dict | None, who: str) -> None:
    if queue:
        for f in findings:
            if f["check"] in ("rubber_stamp", "drift") and f["verdict"] in (RED, AMBER):
                f["message"] += f" Likely cause: {who} handled ~{queue['data']['per_day']:.0f} cases per day."


def _summary(findings: list[dict], verdict: str) -> str:
    if verdict == GREEN:
        return "No problems found."
    return " ".join(f["message"] for f in findings if f["verdict"] == verdict)


def run_all(rows: list[dict], th: dict, quality: dict | None = None) -> dict:
    """Run every check per approval step and per reviewer. Returns a JSON-ready result."""
    last = max(r["decided_at"] for r in rows)
    end = datetime.combine(last.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
    steps = group(rows, "category")
    step_logging = {s: logging_quality(rs, th) for s, rs in steps.items()}
    untrusted = {s for s, f in step_logging.items() if "recommended" in f["data"]["suspicious"]}

    reviewers = {}
    for name, rs in sorted(group([r for r in rows if r["reviewer"]], "reviewer").items()):
        fs = [rubber_stamp(rs, th), drift(rs, th, end)]
        queue = queue_load(rs, th)
        _attach_cause(fs, queue, "this reviewer")
        fs += [queue] if queue else []
        their_steps = sorted({r["category"] for r in rs})
        if untrusted & set(their_steps):
            _cap(fs, "the system's recommendation barely varies in this step")
        reviewers[name] = {"verdict": worst(fs), "steps": their_steps, "stats": stats(rs), "per_day": per_day(rs),
                           "findings": fs, "weekly": weekly(rs)}

    out_steps = {}
    for step, rs in sorted(steps.items()):
        fs = [rubber_stamp(rs, th), drift(rs, th, end), timeouts(rs, th), duplicates(rs, th), step_logging[step]]
        queue = queue_load(rs, th)
        _attach_cause(fs, queue, "each reviewer")
        fs += [queue] if queue else []
        if step in untrusted:
            _cap(fs, "the system's recommendation barely varies in this step")
        names = sorted({r["reviewer"] for r in rs if r["reviewer"]})
        if len(names) > 1:  # with one reviewer the step-level findings already say it
            fs.insert(0, _rollup([reviewers[n] for n in names]))
        verdict = worst(fs)
        out_steps[step] = {"verdict": verdict, "summary": _summary(fs, verdict), "stats": stats(rs),
                           "reviewers": len(names), "findings": fs, "weekly": weekly(rs)}

    verdicts = [s["verdict"] for s in out_steps.values()] + [r["verdict"] for r in reviewers.values()]
    return {"tool": NAME, "version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "period": {"from": min(r["decided_at"] for r in rows).isoformat(), "to": last.isoformat()},
            "thresholds": th, "quality": quality or {}, "not_possible": not_possible(rows),
            "steps": out_steps, "reviewers": reviewers, "red": RED in verdicts}


def _rollup(revs: list[dict]) -> dict:
    """Step-level line about its reviewers, without naming anyone."""
    def count(check: str, verdict: str) -> int:
        return sum(any(f["check"] == check and f["verdict"] == verdict for f in r["findings"]) for r in revs)

    n, stamp, drifted = len(revs), count("rubber_stamp", RED), count("drift", RED)
    of_n = f"of {n} reviewer{'s' if n != 1 else ''}"
    parts = [f"{stamp} {of_n} match{'es' if stamp == 1 else ''} the rubber-stamp pattern"] if stamp else []
    parts += [f"{drifted} {of_n} drifted into the rubber-stamp zone"] if drifted else []
    if parts:
        return finding("reviewers", RED, " and ".join(parts) + ".", red=stamp + drifted)
    amber = sum(r["verdict"] == AMBER for r in revs)
    if amber:
        return finding("reviewers", AMBER, f"{amber} of {n} reviewers show one warning sign or a downward trend.")
    if all(r["verdict"] == GREY for r in revs):
        return finding("reviewers", GREY, f"Not enough data to judge any of the {n} reviewers yet.")
    return finding("reviewers", GREEN, f"None of the {n} reviewers match the rubber-stamp pattern.")


def not_possible(rows: list[dict]) -> list[str]:
    out = []
    if all(r["opened_at"] is None for r in rows):
        out.append("No opened_at column: rubber-stamp check not possible. Use record_review to start logging it.")
    if all(r["reviewer"] is None for r in rows):
        out.append("No reviewer column: per-reviewer checks and queue load not possible.")
    if all(r["executed"] is None for r in rows):
        out.append("No executed column: duplicate-execution check not possible.")
    if all(r["category"] == "default" for r in rows):
        out.append("No category column: all rows are treated as one approval step.")
    return out
