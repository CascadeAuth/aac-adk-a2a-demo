"""Opt-in: the documented steps on real tenants. AAC_DEMO_LIVE=1 and both pairs already up."""
import json
import os
import subprocess

import pytest
from conftest import REPO

pytestmark = pytest.mark.skipif(os.environ.get("AAC_DEMO_LIVE") != "1", reason="set AAC_DEMO_LIVE=1 to run against live tenants")


@pytest.mark.parametrize("scenario,decision", [("reservation", "settle"), ("fare-change", "refuse")])
def test_run_ends_with_correlated_evidence(scenario, decision):
    output = subprocess.run([str(REPO / "demo"), "run", scenario], cwd=REPO, check=True, capture_output=True, text=True).stdout
    evidence = next(json.loads(line)["evidence"] for line in output.splitlines() if line.startswith('{"evidence"'))
    assert evidence["decision"]["action"] == decision
    assert evidence["mint"]["root_token_id"] == evidence["dispatch"]["root_token_id"] == evidence["receive"]["root_token_id"]
    assert "aeg render --root-token-id " + evidence["root_token_id"] in output
