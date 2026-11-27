import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_agent_page_matches_agents_md():
    # docs/agent/index.html and docs/agent.txt (stampcheck.io/agent) are generated from AGENTS.md
    r = subprocess.run([sys.executable, str(ROOT / "scripts/build_agent_page.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
