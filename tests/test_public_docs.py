"""The README is the public teaching surface; keep its adopted presentation."""
import re
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]


def test_story_and_boundary():
    readme = (ROOT / "README.md").read_text()
    assert readme.splitlines()[0] == "# AAC: two ADK agents, one reservation over A2A"
    normalized = " ".join(readme.split())
    assert normalized.count("supplier integration and payment are omitted for clarity") == 1
    assert "https://docs.cascadeauth.com/" in readme
    assert "https://github.com/CascadeAuth/aac-compose-demo" in readme


def test_every_named_requirement_is_linked_and_explains_where_it_runs():
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## Requirements\n", 1)[1].split("## Quickstart", 1)[0]
    rows = [line.split("|")[1:3] for line in section.splitlines() if line.startswith("| ")][1:]
    assert len(rows) == 8
    for component, supplied in rows:
        links = re.findall(r"\[[^\]]+\]\(https://[^)]+\)", component)
        assert links
        assert re.sub(r"\[[^\]]+\]\(https://[^)]+\)", "", component).strip(" / ") == ""
        assert supplied.strip()
    assert "host Python" in section and "inside the agent image" in section
    assert "released-components.json" in section


def test_prescribed_journey_has_no_inline_python_and_uses_every_scalar():
    text = (ROOT / "README.md").read_text()
    assert not re.search(r"\bpython(?:3)?\s+(?:-[A-Za-z]*c\b|(?:-\s*)?<<|-(?:\s|$))", text)
    for agent in ("trip-planner", "booking"):
        for field in ("tenant-id", "hosted-trust-domain", "workload-spiffe-id"):
            assert f"aac agent status --agent {agent} --field {field}" in text
    rendered = MarkdownIt("commonmark").render(text)
    assert "python -c" not in rendered
    assert "./demo prepare" in text and "components.json" in text


def test_the_quickstart_follow_up_block_activates_the_tools_first():
    quickstart = (ROOT / "README.md").read_text().split("## Quickstart\n", 1)[1].split("\n## How the pieces", 1)[0]
    block = next(b for b in re.findall(r"```sh\n(.*?)```", quickstart, re.S) if "./demo run fare-change" in b)
    assert block.splitlines()[:2] == [". .aac-tools/bin/activate", 'export AAC_CLI_HOME="$PWD/.local/aac"']


def test_own_model_section_names_the_one_variable_and_both_routes():
    section = (ROOT / "README.md").read_text().split("## 5. Run it with your own model\n", 1)[1].split("\n## 6. ", 1)[0]
    assert "AAC_DEMO_MODEL" in section and "GOOGLE_API_KEY" in section
    assert "ollama_chat/" in section and "OLLAMA_API_BASE" in section
    assert "scripted_model.py" in section
