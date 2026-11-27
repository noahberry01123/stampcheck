from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_published_agent_instructions_match_agents_md():
    # docs/agent.txt is served at stampcheck.io/agent.txt and must stay an exact copy of AGENTS.md
    assert (ROOT / "docs/agent.txt").read_text(encoding="utf-8") == (ROOT / "AGENTS.md").read_text(encoding="utf-8")
