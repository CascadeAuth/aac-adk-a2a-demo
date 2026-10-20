"""The quickstart runs README steps 1 to 4 exactly as written."""
import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import subprocess

from aac_cli._aeg.cli import parser
from conftest import REPO

# Lines of steps 1 to 4 the quickstart leaves out on purpose: the clone happens
# before it runs, the reader supplies the contact addresses, and it runs the
# reservation scenario only.
LEFT_OUT = {
    "git clone https://github.com/CascadeAuth/aac-adk-a2a-demo.git",
    "cd aac-adk-a2a-demo",
    "export VANTIS_CONTACT='you+vantis@example.com'",
    "export TOURFEDIA_CONTACT='you+tourfedia@example.com'",
    "./demo run fare-change",
}
# The one command the quickstart adds to the README's steps: it acts on a rerun
# only, renewing the development certificates that expired since the first run.
RERUN_ONLY = {"./demo renew"}


def readme_step_lines():
    """Every line of the shell blocks in steps 1 to 3, and of the first block of step 4."""
    readme = (REPO / "README.md").read_text()
    steps_1_to_3 = readme.split("\n## 1. ", 1)[1].split("\n## 4. ", 1)[0]
    step_4 = readme.split("\n## 4. ", 1)[1]
    blocks = re.findall(r"```sh\n(.*?)```", steps_1_to_3, re.S) + re.findall(r"```sh\n(.*?)```", step_4, re.S)[:1]
    return [line for block in blocks for line in block.splitlines() if line.strip() and line not in LEFT_OUT]


def quickstart_step_lines():
    """The script's command lines from step 1 up to the graph, without headings, comments and trace switches."""
    script = (REPO / "quickstart").read_text()
    steps = script.split(': "== 1.', 1)[1].split(': "== View', 1)[0].splitlines()[1:]
    return [line for line in steps if line.strip() and not line.startswith((": ", "set ", "#")) and line not in RERUN_ONLY]


def test_quickstart_runs_exactly_the_readme_steps():
    assert quickstart_step_lines() == readme_step_lines()


def test_quickstart_renews_expired_certificates_after_the_cli_home_is_set_and_before_step_2():
    script = (REPO / "quickstart").read_text().splitlines()
    assert script.count("./demo renew") == 1
    renew = script.index("./demo renew")
    assert any(line.startswith("export AAC_CLI_HOME=") for line in script[:renew])
    assert all(not line.startswith(': "== 2.') for line in script[:renew])
    assert any(line.startswith(': "== 2.') for line in script[renew:])


def quickstart_render_args(evidence):
    """The quickstart's render command, parsed, with its shell variables filled in."""
    script = (REPO / "quickstart").read_text()
    render = script.split("\naeg render ", 1)[1].split("\n\n", 1)[0].replace("\\\n", "")
    lines = script.splitlines()
    assignments = "; ".join(next(line for line in lines if line.startswith(name + "=")) for name in ("ROOT", "RUN", "GRAPH"))
    values = subprocess.run(["bash", "-c", f'EVIDENCE={shlex.quote(str(evidence))}; {assignments}; printf "%s\\n%s\\n%s" "$ROOT" "$RUN" "$GRAPH"'],
                            check=True, capture_output=True, text=True).stdout.split("\n")
    render = render.replace('"$ROOT"', values[0]).replace('"$RUN.', values[1] + ".").replace('"$GRAPH"', values[2] + '"')
    render = render.replace('"', "")
    return parser().parse_args(["render", *shlex.split(render)])


def test_quickstart_renders_the_same_graph_as_demo_run(synthetic_home, tmp_path, monkeypatch, capsys):
    # Produce the render command ./demo run prints, as in test_demo.py.
    monkeypatch.setenv("AAC_CLI_HOME", str(synthetic_home))
    loader = importlib.machinery.SourceFileLoader("demo_for_quickstart", str(REPO / "demo"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec); loader.exec_module(module)
    monkeypatch.setattr(module, "REPO", tmp_path)
    monkeypatch.setattr(module, "renew_expired", lambda agent: False)  # nothing expired in the synthetic home
    from test_demo import chain_evidence
    evidence = chain_evidence("attempt-1")
    monkeypatch.setattr(module, "compose", lambda *a, **k: json.dumps({"evidence": evidence}) + "\n")
    monkeypatch.setattr(module.sys, "argv", ["demo", "run", "reservation"])
    module.main()
    printed = capsys.readouterr().out.split("Render this attempt locally:\n", 1)[1].splitlines()[0]
    demo = parser().parse_args(shlex.split(printed)[1:])

    quickstart = quickstart_render_args(tmp_path / ".runs/attempt-1.json")
    for field in ("root_token_id", "events", "actions", "output"):
        assert getattr(quickstart, field) == getattr(demo, field), field


def test_the_printed_follow_up_activates_the_tools_before_any_demo_command():
    """The quickstart's tools and CLI home end with the script; the commands it suggests need them back."""
    script = (REPO / "quickstart").read_text()
    follow_up = script.split("Quickstart demo completed successfully.", 1)[1]
    commands = [line.split("'")[1].strip() for line in follow_up.splitlines() if line.startswith("echo '  ")]
    assert commands[:2] == [". .aac-tools/bin/activate", 'export AAC_CLI_HOME="$PWD/.local/aac"']
    assert all(command.startswith("./demo ") for command in commands[2:]) and len(commands) > 2


def test_quickstart_is_an_executable_shell_script():
    path = REPO / "quickstart"
    assert os.access(path, os.X_OK)
    subprocess.run(["bash", "-n", str(path)], check=True)
