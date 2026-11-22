"""Outputs: a short terminal summary, result.json, and a self-contained report.html (inline SVG, no network)."""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import textwrap
from datetime import date
from html import escape
from pathlib import Path

from .checks import RANK, fmt_s, pct
from .config import NAME

ANSI = {"RED": "\033[1;31m", "AMBER": "\033[1;33m", "GREEN": "\033[1;32m", "GREY": "\033[2m"}
TOKEN = {"RED": "critical", "AMBER": "warning", "GREEN": "good", "GREY": "muted"}


def by_severity(items: dict) -> list:
    return sorted(items.items(), key=lambda kv: (-RANK[kv[1]["verdict"]], kv[0]))


def reason(item: dict) -> str:
    """Why an item got its verdict: every RED/AMBER message, or the first GREEN/GREY one."""
    if item.get("summary"):
        return item["summary"]
    msgs = [f["message"] for f in item["findings"] if f["verdict"] == item["verdict"]]
    return " ".join(msgs) if item["verdict"] in ("RED", "AMBER") else msgs[0]


def thresholds_text(th: dict) -> list[str]:
    return [
        f"Rubber-stamping needs at least {th['min_cases']:g} decided cases, a 95% upper bound on the disagreement "
        f"rate below {th['max_disagreement_upper']:.0%}, and a median time from opened to decided below "
        f"{th['max_median_seconds']:g} s.",
        f"Drift compares the last {th['drift_recent_days']:g} days with the {th['drift_baseline_days']:g} days "
        f"before. A trend is time per case falling by {th['drift_change']:.0%} or more, or disagreement falling "
        f"significantly. It is RED once the recent period is in the rubber-stamp zone.",
        f"Logging looks hard-coded when one value covers {th['logging_dominant_share']:.0%} or more of rows, or "
        f"the second value appears fewer than {th['logging_min_second_value']:g} times.",
        f"Queue overload means more than {th['queue_max_per_day']:g} decided cases per reviewer per working day.",
    ]


def mapping_lines(q: dict) -> list[str]:
    cols = ", ".join(f"{f}={c}" for f, c in q.get("columns", {}).items() if c)
    lines = [f"Columns used: {cols}"]
    if q.get("missing_columns"):
        lines.append(f"Columns not found: {', '.join(q['missing_columns'])}")
    vals = [f"{raw}->{canon}" for vs in q.get("values", {}).values() for raw, canon in vs.items() if raw != canon]
    if vals:
        lines.append(f"Values mapped: {', '.join(vals)}")
    for f, counts in q.get("unmapped", {}).items():
        listed = ", ".join(f"{v!r} ({n})" for v, n in counts.items())
        lines.append(f"Unmapped {f} values, rows skipped: {listed}. Map them under values: in your config.")
    return lines


def terminal(result: dict, report_dir: Path, color: bool | None = None) -> str:
    if color is None:
        color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    width = min(shutil.get_terminal_size((100, 20)).columns, 110)
    q = result["quality"]

    def tag(v: str) -> str:
        return f"{ANSI[v]}{v:<6}\033[0m" if color else f"{v:<6}"

    def block(title: str, items: dict) -> list[str]:
        pad = max(len(k) for k in items) + 2
        out = [title]
        for name, item in by_severity(items):
            body = textwrap.wrap(reason(item), max(40, width - pad - 9), break_on_hyphens=False) or [""]
            out.append(f"  {tag(item['verdict'])} {name:<{pad}}{body[0]}")
            out += [" " * (pad + 9) + line for line in body[1:]]
        return out + [""]

    skipped = sum(q.get("skipped", {}).values())
    lines = [f"{NAME}: checked {q.get('source', 'data')}",
             f"{q.get('rows_read', '?')} rows read, {q.get('rows_used', '?')} used, {skipped} skipped. "
             f"Decisions from {result['period']['from'][:10]} to {result['period']['to'][:10]}.", ""]
    lines += mapping_lines(q) + [""] if q else []
    lines += [f"Skipped {n} row{'s' if n != 1 else ''}: {why}" for why, n in q.get("skipped", {}).items()]
    lines += [f"Note: {n} x {why}" for why, n in q.get("notes", {}).items()]
    lines += [f"Not possible: {msg}" for msg in result["not_possible"]]
    lines += [""] if (skipped or q.get("notes") or result["not_possible"]) else []
    lines += block("Approval steps", result["steps"])
    if result["reviewers"]:
        lines += block("Reviewers", result["reviewers"])
    lines += textwrap.wrap("Thresholds: " + " ".join(thresholds_text(result["thresholds"])), width,
                           break_on_hyphens=False) + [""]
    lines.append(f"Report: {report_dir / 'report.html'}   Result: {report_dir / 'result.json'}")
    return "\n".join(lines)


def write_json(result: dict, path: Path) -> None:
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


# ------------------------------------------------------------------ HTML

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--line:#2a78d6;--border:rgba(11,11,11,.10);
--good:#0ca30c;--warning:#fab219;--critical:#d03b3b;--zone:rgba(208,59,59,.10)}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;
--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--line:#3987e5;--border:rgba(255,255,255,.10);--zone:rgba(208,59,59,.18)}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px}
h2{font-size:17px;margin:32px 0 8px}p.sub{color:var(--ink2);margin:0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 16px;overflow-x:auto}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);
vertical-align:top}th{color:var(--ink2);font-weight:600;font-size:13px}td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;min-width:64px;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;
text-align:center;color:#fff}.pill.good{background:var(--good)}.pill.critical{background:var(--critical)}
.pill.warning{background:var(--warning);color:#0b0b0b}.pill.muted{background:var(--muted)}
.icon{margin-right:4px}svg{display:block;max-width:100%;height:auto}svg text{fill:var(--ink2);font-size:11px}
.trend{display:grid;grid-template-columns:110px 1fr 1fr;gap:4px 16px;align-items:center}
.trend .name{font-weight:600}.note{color:var(--ink2);font-size:13px}ul{margin:4px 0;padding-left:20px}
footer{margin-top:40px;color:var(--ink2);font-size:13px;border-top:1px solid var(--grid);padding-top:12px}
@media (max-width:640px){.trend{grid-template-columns:1fr}}
"""
ICON = {"RED": "&#x2716;", "AMBER": "&#x25B2;", "GREEN": "&#x2714;", "GREY": "&#x25CB;"}


def pill(v: str) -> str:
    return f'<span class="pill {TOKEN[v]}"><span class="icon" aria-hidden="true">{ICON[v]}</span>{v}</span>'


def _log_x(s: float, x0: float, w: float, lo: float = 1, hi: float = 3600) -> float:
    s = min(max(s, lo), hi)
    return x0 + w * (math.log10(s) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))


def scatter(points: list[tuple[str, dict, str]], th: dict) -> str:
    """Time per case (log) vs disagreement %, one dot per reviewer, danger zone shaded."""
    W, H, L, R, T, B = 640, 340, 52, 20, 14, 42
    pw, ph = W - L - R, H - T - B
    ymax = max(20, math.ceil(max((s["rate"] or 0) for _, s, _ in points) * 100 / 5) * 5 + 5)
    y = lambda p: T + ph * (1 - p * 100 / ymax)  # noqa: E731
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Time per case against disagreement rate">']
    zx, zy = _log_x(th["max_median_seconds"], L, pw), y(th["max_disagreement_upper"])
    out.append(f'<rect x="{L}" y="{zy:.1f}" width="{zx - L:.1f}" height="{T + ph - zy:.1f}" fill="var(--zone)"/>')
    out.append(f'<text x="{L + 6}" y="{zy - 6:.1f}">rubber-stamp zone</text>')
    for p in range(0, ymax + 1, 5 if ymax <= 30 else 10):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(p / 100):.1f}" y2="{y(p / 100):.1f}" stroke="var(--grid)"/>'
                   f'<text x="{L - 6}" y="{y(p / 100) + 4:.1f}" text-anchor="end">{p}%</text>')
    for s, label in ((1, "1 s"), (5, "5 s"), (30, "30 s"), (120, "2 min"), (600, "10 min"), (3600, "1 h")):
        x = _log_x(s, L, pw)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{T}" y2="{T + ph}" stroke="var(--grid)"/>'
                   f'<text x="{x:.1f}" y="{T + ph + 16}" text-anchor="middle">{label}</text>')
    out.append(f'<line x1="{L}" x2="{W - R}" y1="{T + ph}" y2="{T + ph}" stroke="var(--axis)"/>'
               f'<text x="{L + pw / 2}" y="{H - 6}" text-anchor="middle">median time from opened to decided '
               f'(log scale)</text><text x="12" y="{T + ph / 2}" transform="rotate(-90 12 {T + ph / 2})" '
               f'text-anchor="middle">disagrees with the system</text>')
    placed: list[tuple[float, float]] = []
    for name, s, verdict in sorted(points, key=lambda p: (p[1]["rate"] or 0)):
        cx, cy = _log_x(s["median_s"], L, pw), y(s["rate"] or 0)
        ly = cy + 4
        while any(abs(cx - px) < 70 and abs(ly - py) < 13 for px, py in placed):
            ly -= 13
        placed.append((cx, ly))
        tip = f"{name}: {s['n']} cases, disagrees {pct(s['rate'])}, median {fmt_s(s['median_s'])} ({verdict})"
        out.append(f'<g><title>{escape(tip)}</title><circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" fill="transparent"/>'
                   f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6" fill="var(--{TOKEN[verdict]})" stroke="var(--surface)" '
                   f'stroke-width="2"/><text x="{cx + 10:.1f}" y="{ly:.1f}" style="fill:var(--ink)">'
                   f'{escape(name)}</text></g>')
    return "".join(out) + "</svg>"


def sparkline(weeks: list[dict], key: str, th_value: float, log: bool) -> str:
    """One small chart: a weekly series with a dashed threshold line. Log scale for time."""
    W, H, L, R, T, B = 320, 84, 40, 74, 8, 18
    pw, ph = W - L - R, H - T - B
    pts = [(i, w[key]) for i, w in enumerate(weeks) if w[key] is not None]
    top = 0.2 if not log else 3600
    if not log:
        top = max([0.2] + [v * 1.15 for _, v in pts])
    yv = (lambda v: T + ph * (1 - (math.log10(max(v, 1))) / math.log10(top))) if log \
        else (lambda v: T + ph * (1 - v / top))
    xv = lambda i: L + pw * (i / max(1, len(weeks) - 1))  # noqa: E731
    fmt = fmt_s if log else pct
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Weekly {"time per case" if log else "disagreement"}">',
           f'<line x1="{L}" x2="{W - R}" y1="{T + ph}" y2="{T + ph}" stroke="var(--axis)"/>',
           f'<line x1="{L}" x2="{W - R}" y1="{yv(th_value):.1f}" y2="{yv(th_value):.1f}" stroke="var(--muted)" '
           f'stroke-dasharray="3 3"/><text x="{L - 4}" y="{yv(th_value) + 4:.1f}" text-anchor="end">'
           f'{fmt(th_value)}</text><text x="{L - 4}" y="{T + ph + 4}" text-anchor="end">{"1 s" if log else "0%"}'
           '</text>']
    if pts:
        path = " ".join(f"{xv(i):.1f},{yv(v):.1f}" for i, v in pts)
        out.append(f'<polyline points="{path}" fill="none" stroke="var(--line)" stroke-width="2" '
                   'stroke-linejoin="round" stroke-linecap="round"/>')
        for i, v in pts:
            tip = f"week of {weeks[i]['week']}: {fmt(v)} ({weeks[i]['n']} cases)"
            out.append(f'<g><title>{escape(tip)}</title><circle cx="{xv(i):.1f}" cy="{yv(v):.1f}" r="8" '
                       f'fill="transparent"/><circle cx="{xv(i):.1f}" cy="{yv(v):.1f}" r="2.5" fill="var(--line)"/></g>')
        i, v = pts[-1]
        out.append(f'<text x="{xv(i) + 6:.1f}" y="{yv(v) + 4:.1f}" style="fill:var(--ink)">{fmt(v)}</text>')
    if weeks:
        day = lambda w: f"{date.fromisoformat(w['week']):%b} {date.fromisoformat(w['week']).day}"  # noqa: E731
        out.append(f'<text x="{L}" y="{H - 4}">week of {day(weeks[0])}</text>'
                   f'<text x="{W - R}" y="{H - 4}" text-anchor="end">{day(weeks[-1])}</text>')
    return "".join(out) + "</svg>"


def html(result: dict) -> str:
    th, q = result["thresholds"], result["quality"]
    e = escape
    rows = "".join(f"<tr><td>{pill(s['verdict'])}</td><td><b>{e(name)}</b></td><td>{e(s['summary'])}</td></tr>"
                   for name, s in by_severity(result["steps"]))
    parts = [f"<h1>Approval review check</h1><p class='sub'>{e(q.get('source', ''))}: decisions from "
             f"{result['period']['from'][:10]} to {result['period']['to'][:10]}. Generated by {NAME} "
             f"{result['version']} on {result['generated_at'][:10]}.</p>",
             f"<h2>Approval steps</h2><div class='card'><table>{rows}</table></div>"]

    subjects = result["reviewers"] or result["steps"]
    kind = "reviewer" if result["reviewers"] else "approval step"
    if result["reviewers"]:
        trs = "".join(
            f"<tr><td>{pill(r['verdict'])}</td><td><b>{e(n)}</b></td><td class='num'>{r['stats']['n']}</td>"
            f"<td class='num'>{pct(r['stats']['rate'])}</td><td class='num'>{pct(r['stats']['upper'])}</td>"
            f"<td class='num'>{fmt_s(r['stats']['median_s'])}</td><td class='num'>"
            f"{'n/a' if r['per_day'] is None else round(r['per_day'])}</td><td>"
            f"{e(reason(r))}</td></tr>"
            for n, r in by_severity(result["reviewers"]))
        parts.append("<h2>Reviewers</h2><div class='card'><table><tr><th>Verdict</th><th>Reviewer</th><th>Cases</th>"
                     "<th>Disagrees</th><th>Upper bound</th><th>Median time</th><th>Cases/day</th><th>Why</th>"
                     f"</tr>{trs}</table></div>")
    points = [(n, s["stats"], s["verdict"]) for n, s in subjects.items() if s["stats"]["median_s"] is not None]
    left_out = [n for n, s in subjects.items() if s["stats"]["median_s"] is None]
    parts.append(f"<h2>Time per case vs disagreement</h2><div class='card'>"
                 f"{scatter(points, th) if points else '<p>No opened_at data, so there is nothing to plot.</p>'}"
                 f"<p class='note'>One dot per {kind}. The shaded corner is where the rubber-stamp zone starts: "
                 f"under {th['max_median_seconds']:g} s per case and almost never disagreeing (the exact test uses "
                 f"the upper bound, so it depends on the number of cases)."
                 + (f" Not shown (no opened_at): {e(', '.join(left_out))}." if left_out else "") + "</p></div>")
    trend = "".join(f"<div class='name'>{e(n)}</div><div>{sparkline(s['weekly'], 'median_s', th['max_median_seconds'], True)}"
                    f"</div><div>{sparkline(s['weekly'], 'rate', th['max_disagreement_upper'], False)}</div>"
                    for n, s in sorted(subjects.items()))
    parts.append(f"<h2>Weekly trend</h2><div class='card'><div class='trend'><div></div><div class='note'>Median time "
                 "per case (log scale)</div><div class='note'>Disagrees with the system</div>"
                 f"{trend}</div><p class='note'>Dashed lines are the thresholds. Hover a point for the week and "
                 "number of cases.</p></div>")

    explain = [
        "Disagreement rate: the share of decided cases where the human did something other than what the system "
        "recommended (escalating counts as disagreeing). Timeouts are left out because nobody decided.",
        "Upper bound: the Wilson 95% interval's upper end for that rate. With few cases a 0% rate is weak evidence; "
        "the upper bound says how high the true rate could plausibly be.",
        "Median time per case: half of the decisions took less than this, measured from opened_at to decided_at. "
        "Time from notified_at is never used, because it includes time spent waiting in the queue.",
        "Drift: the same figures for the most recent period against the period before, so a slow slide shows up.",
        "Cases per day: decided cases per reviewer on the days they worked.",
    ]
    parts.append("<h2>How these verdicts are decided</h2><div class='card'><ul>"
                 + "".join(f"<li>{e(t)}</li>" for t in thresholds_text(th) + explain)
                 + "</ul><p class='note'>GREY means not enough data to judge, never a pass. Thresholds: "
                 + e(", ".join(f"{k}={v:g}" for k, v in th.items())) + "</p></div>")

    dq = [f"Rows read: {q.get('rows_read', '?')}. Rows used: {q.get('rows_used', '?')}."]
    dq += [f"Skipped {n} row{'s' if n != 1 else ''}: {why}." for why, n in q.get("skipped", {}).items()]
    dq += [f"{n} x {why}." for why, n in q.get("notes", {}).items()]
    dq += mapping_lines(q) if q else []
    dq += [f"Check not possible. {m}" for m in result["not_possible"]]
    grey = [f"{n}: {f['message']}" for n, s in {**result["steps"], **result["reviewers"]}.items()
            for f in s["findings"] if f["verdict"] == "GREY"]
    parts.append("<h2>Data quality</h2><div class='card'><ul>" + "".join(f"<li>{e(t)}</li>" for t in dq) + "</ul>"
                 + ("<p class='note'>Checks that could not run:</p><ul>" + "".join(f"<li>{e(g)}</li>" for g in grey)
                    + "</ul>" if grey else "") + "</div>")
    parts.append("<footer>Patterns in review data are evidence to look into, not proof that anyone did anything "
                 "wrong.</footer>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Approval review check</title>"
            f"<style>{CSS}</style></head><body><main>{''.join(parts)}</main></body></html>")


def write_html(result: dict, path: Path) -> None:
    path.write_text(html(result), encoding="utf-8")
