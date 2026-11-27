"""Build the agent setup page from AGENTS.md, the single source for the agent instructions.

    python scripts/build_agent_page.py          # writes docs/agent/index.html and docs/agent.txt
    python scripts/build_agent_page.py --check  # exits 1 if either file is out of date (tests run this)

Needs the dev extra (pip install -e ".[dev]") for the pinned markdown package.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "AGENTS.md"
HTML = ROOT / "docs/agent/index.html"   # served at stampcheck.io/agent/
TEXT = ROOT / "docs/agent.txt"          # served at stampcheck.io/agent.txt, an exact copy of AGENTS.md

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>StampCheck agent setup</title>
<meta name="description" content="Step-by-step instructions for an AI coding agent setting up StampCheck in a project. Plain text: https://stampcheck.io/agent.txt">
<link rel="alternate" type="text/plain" href="/agent.txt">
<script>try { if (localStorage.getItem("stampcheck-theme") === "dark") document.documentElement.setAttribute("data-theme", "dark"); } catch (e) {}</script>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink2: #52514e; --muted: #6b6a66;
  --border: #e1e0d9; --code: #f0efec; --accent: #d03b3b; --link: #1c5cab;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink2: #c3c2b7; --muted: #898781;
  --border: #2c2c2a; --code: #232321; --accent: #e66767; --link: #6da7ec;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 17px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 760px; margin: 0 auto; padding: 40px 16px 64px; overflow-wrap: break-word; }
.top { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.theme {
  font: 600 14px/1 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); cursor: pointer;
  background: var(--surface); border: 1px solid var(--border); border-radius: 999px; padding: 8px 14px;
}
.theme:hover { border-color: var(--muted); }
.theme:focus-visible { outline: 2px solid var(--link); outline-offset: 2px; }
.brand { font: 800 18px/1 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); letter-spacing: -0.01em; text-decoration: none; }
.intro { margin: 20px 0 0; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); font-size: 15px; color: var(--ink2); }
h1 { font-size: clamp(28px, 5vw, 38px); line-height: 1.15; letter-spacing: -0.02em; margin: 28px 0 16px; }
h2 { font-size: 24px; margin: 44px 0 12px; }
h3 { font-size: 19px; margin: 32px 0 8px; }
p, li { color: var(--ink2); }
p { margin: 0 0 14px; }
li { margin: 4px 0; }
strong { color: var(--ink); }
a { color: var(--link); }
code { font: 0.9em ui-monospace, "SF Mono", Menlo, monospace; background: var(--code); border-radius: 4px; padding: 1px 4px; color: var(--ink); }
pre {
  background: var(--code); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px;
  overflow-x: auto; font: 14px/1.6 ui-monospace, "SF Mono", Menlo, monospace; color: var(--ink); margin: 0 0 16px;
}
pre code { background: none; padding: 0; font-size: inherit; }
.scroll { overflow-x: auto; margin: 0 0 16px; }
table { border-collapse: collapse; width: 100%; font-size: 15px; }
th, td { text-align: left; vertical-align: top; padding: 8px 10px; border-bottom: 1px solid var(--border); }
th { color: var(--ink); }
td { color: var(--ink2); }
footer { margin-top: 56px; padding-top: 16px; border-top: 1px solid var(--border); font-size: 14px; color: var(--muted); }
footer a { margin-right: 16px; }
</style>
</head>
<body>
<main>
  <div class="top">
    <a class="brand" href="/">StampCheck</a>
    <button class="theme" id="theme" type="button" aria-pressed="false">Dark mode</button>
  </div>
  <p class="intro">This page is written for AI coding agents. To use it, paste this into your coding agent:
    <em>"Set up StampCheck for this project. Follow the instructions at https://stampcheck.io/agent. Ask me before changing any code."</em>
    Plain-text version: <a href="/agent.txt">stampcheck.io/agent.txt</a>. Same text in the repo: <a href="https://github.com/noahberry01123/stampcheck/blob/main/AGENTS.md">AGENTS.md</a>.</p>
<!-- AGENTS.md -->
  <footer>
    <a href="/">&larr; What is StampCheck?</a>
    <a href="https://github.com/noahberry01123/stampcheck">GitHub repo</a>
    <a href="https://github.com/noahberry01123/stampcheck/discussions">Questions and ideas: GitHub Discussions</a>
  </footer>
</main>
<script>
(function () {
  var root = document.documentElement, btn = document.getElementById("theme");
  function apply(theme) {
    var dark = theme === "dark";
    root.setAttribute("data-theme", dark ? "dark" : "light");
    btn.textContent = dark ? "Light mode" : "Dark mode";
    btn.setAttribute("aria-pressed", dark ? "true" : "false");
  }
  apply(root.getAttribute("data-theme"));
  btn.addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    apply(next);
    try { localStorage.setItem("stampcheck-theme", next); } catch (e) {}
  });
})();
</script>
</body>
</html>
"""


def build() -> dict[Path, str]:
    import markdown

    md = SOURCE.read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["fenced_code", "tables"])
    body = body.replace("<table>", '<div class="scroll"><table>').replace("</table>", "</table></div>")
    return {HTML: PAGE.replace("<!-- AGENTS.md -->", body), TEXT: md}


def main(argv: list[str]) -> int:
    try:
        files = build()
    except ImportError:
        print('Needs the markdown package: pip install -e ".[dev]"', file=sys.stderr)
        return 2
    if "--check" in argv:
        stale = [p for p, text in files.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
        for p in stale:
            print(f"{p.relative_to(ROOT)} is out of date with AGENTS.md. Run: python scripts/build_agent_page.py",
                  file=sys.stderr)
        return 1 if stale else 0
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
