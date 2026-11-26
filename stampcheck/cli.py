"""Command line: `stampcheck demo`, `stampcheck check`, `stampcheck init`. Exit 0 = no RED, 1 = RED, 2 = input error."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import webbrowser
from pathlib import Path

from . import alert, demo, report
from .checks import run_all
from .config import CONFIG_FILE, NAME, VERSION, ConfigError, init_text, load_config
from .record import write_rows
from .sources import InputError, load, pseudonymize


def check(source: str, out: str = ".", config: str | None = None, query: str | None = None,
          alert_to: str | None = None, per_reviewer: bool = False, pseudonym: bool = False,
          auto_config: bool = True, open_browser: bool = False) -> int:
    try:
        url = alert.parse_target(alert_to) if alert_to else None
        cfg = load_config(config, auto=auto_config)
        rows, quality = load(source, cfg, query)
    except (ConfigError, InputError, ValueError) as e:
        print(f"{NAME}: input error: {e}", file=sys.stderr)
        return 2
    if pseudonym:
        pseudonymize(rows, cfg["pseudonymize_salt"])
    quality["config"] = cfg["path"]
    result = run_all(rows, cfg["thresholds"], quality)

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    previous = None
    if (out_dir / "result.json").is_file():
        try:
            previous = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = None
    report.write_json(result, out_dir / "result.json")
    report.write_html(result, out_dir / "report.html")
    print(report.terminal(result, out_dir) + "\n")
    html_path, opened = out_dir / "report.html", False
    if open_browser:
        try:
            opened = webbrowser.open(html_path.resolve().as_uri())
        except Exception:  # noqa: BLE001 (no browser here is fine; the path is printed below)
            opened = False
    print(f"Report saved to: {html_path.resolve()}")
    print(f"To open it{' again' if opened else ''}: {open_command(html_path)}")
    print(f"Result data: {(out_dir / 'result.json').resolve()}")

    if url and alert.should_alert(result, previous):
        try:
            alert.send(url, alert.message(result, previous, per_reviewer, str(out_dir / "report.html")))
            print("Slack alert sent.")
        except OSError as e:  # urllib errors are OSErrors; a failed alert never changes the verdict
            print(f"{NAME}: could not send the Slack alert: {e}", file=sys.stderr)
    return 1 if result["red"] else 0


def open_command(path: Path, platform: str = sys.platform) -> str:
    """The command that opens a file on this operating system, with the path relative to here."""
    rel = os.path.relpath(path)
    if platform.startswith("win"):
        return f'start "" "{rel}"' if " " in rel else f"start {rel}"
    return f"{'open' if platform == 'darwin' else 'xdg-open'} {shlex.quote(rel)}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog=NAME, description="Check whether your human approval step still does anything.")
    p.add_argument("--version", action="version", version=f"{NAME} {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="run the check on a built-in example dataset")
    d.add_argument("--out", default=".", help="folder for demo.db, report.html and result.json (default: .)")
    d.add_argument("--no-open", action="store_true", help="don't open the report in a browser (for CI and servers)")

    c = sub.add_parser("check", help="check your own review data")
    c.add_argument("--source", required=True, help="CSV/TSV, .jsonl, SQLite .db, or postgresql://... URL")
    c.add_argument("--query", help="SQL to run (required for Postgres; default for SQLite: SELECT * FROM reviews)")
    c.add_argument("--mapping", "--config", dest="config",
                   help=f"YAML or JSON file with thresholds and column/value mapping (default: ./{CONFIG_FILE})")
    c.add_argument("--out", default=".", help="folder for report.html and result.json (default: .)")
    c.add_argument("--alert", help="slack:<webhook-url>; posts only when something is RED or newly drifting")
    c.add_argument("--per-reviewer", action="store_true", help="name individual reviewers in alerts")
    c.add_argument("--pseudonymize", action="store_true", help="replace reviewer IDs with salted hashes")

    i = sub.add_parser("init", help=f"write a commented example config ({CONFIG_FILE})")
    i.add_argument("--path", default=CONFIG_FILE)
    i.add_argument("--force", action="store_true", help="overwrite an existing file")

    args = p.parse_args(argv)
    if args.cmd == "demo":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        db = out / "demo.db"
        db.unlink(missing_ok=True)  # always rebuild the demo data from the fixed seed
        write_rows(demo.generate(), db)
        print(f"Demo: 8 weeks of synthetic data. An AI support agent recommends refunds and five fictional "
              f"reviewers approve or reject them. Written to {db}\n")
        return check(str(db), str(out), auto_config=False, open_browser=not args.no_open)
    if args.cmd == "check":
        return check(args.source, args.out, args.config, args.query, args.alert, args.per_reviewer, args.pseudonymize)
    target = Path(args.path)
    if target.exists() and not args.force:
        print(f"{NAME}: {target} already exists; use --force to overwrite", file=sys.stderr)
        return 2
    target.write_text(init_text(), encoding="utf-8")
    print(f"Wrote {target}. Edit it, then run: {NAME} check --source <your data>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
