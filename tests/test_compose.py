"""Resolve the actual Compose input against the public CLI-generated paths."""
import json
import os
import shutil
import subprocess

import pytest
import yaml
import components
from conftest import REPO

pytestmark = pytest.mark.skipif(not shutil.which("docker"), reason="Docker Compose unavailable")


@pytest.mark.parametrize("agent", ["trip-planner", "booking"])
def test_independent_mounts_a2a_and_runtime(synthetic_home, agent):
    env = {**os.environ, **components.compose_values(components.selected(REPO)),
           "AAC_DEMO_ROLE": agent, "AAC_DEMO_UID": "4242", "AAC_DEMO_GID": "4243",
           "AAC_DEMO_VANTIS_STATE": str(synthetic_home / "agents/trip-planner/state"),
           "AAC_DEMO_TOURFEDIA_STATE": str(synthetic_home / "agents/booking/state"),
           "AAC_DEMO_BOOKING_ID": "spiffe://tourfedia.example/booking"}
    env.pop("AAC_DEMO_MODEL", None)
    folder = synthetic_home / "agents" / agent
    result = subprocess.run(["docker", "compose", "--env-file", str(folder / "compose.env"),
        "--profile", "exercise", "config", "--format", "json"], cwd=REPO, env=env,
        capture_output=True, text=True, check=True)
    rendered = json.loads(result.stdout)
    services = rendered["services"]
    assert rendered["name"] == "aac-adk-a2a-demo-" + agent
    assert services["sidecar"]["image"] == env["AAC_DEMO_SIDECAR_IMAGE"]
    assert services["sidecar"]["network_mode"] == "service:agent"
    assert services["client"]["network_mode"] == "service:agent"
    assert services["agent"]["environment"]["AAC_DEMO_ROLE"] == agent
    assert services["client"]["environment"]["AAC_DEMO_ROLE"] == agent
    assert services["agent"]["environment"]["AAC_DEMO_MODEL"] == ""  # the scripted model, unless you set one
    assert services["agent"]["networks"]["peers"]["aliases"] == [agent]
    for service in services.values():
        assert service["user"] == "4242:4243"
        assert "ports" not in service
    for name in ("agent", "client"):
        mounts = {m["target"]: m["source"] for m in services[name]["volumes"]}
        assert mounts["/run/secrets"] == str(folder / "agent")
        assert not any("/sidecar" in source for source in mounts.values())
    client = {m["target"]: m for m in services["client"]["volumes"]}
    assert client["/evidence/vantis"]["source"] == env["AAC_DEMO_VANTIS_STATE"] and client["/evidence/vantis"]["read_only"]
    assert client["/evidence/tourfedia"]["source"] == env["AAC_DEMO_TOURFEDIA_STATE"] and client["/evidence/tourfedia"]["read_only"]
    assert services["client"]["environment"]["AAC_DEMO_BOOKING_ID"] == env["AAC_DEMO_BOOKING_ID"]
    assert services["agent"]["extra_hosts"] == ["host.docker.internal=host-gateway"]
    # The client shares the agent's network namespace and so its hosts file;
    # Docker refuses extra_hosts together with network_mode: service (the
    # first live run failed on exactly that).
    assert "extra_hosts" not in services["client"]
    sidecar = {m["target"]: m for m in services["sidecar"]["volumes"]}
    assert sidecar["/etc/aac/pki"]["source"] == str(folder / "sidecar")
    assert sidecar["/etc/aac/pki"]["read_only"]
    cfg = yaml.safe_load((folder / "sidecar-config.yaml").read_text())
    assert cfg["sidecar"]["dev_mode"] is False
    assert cfg["sidecar"]["external_bind_address"] == "0.0.0.0"
    assert cfg["replay_protection"]["deployment_profile"] == "basic"
    # The CLI wrote the whole a2a block from the two addresses in config/*.yaml.
    assert cfg["a2a"]["public_base_url"] == f"https://{agent}:9443"
    assert cfg["a2a"]["local_handler_url"] == "http://127.0.0.1:8000/a2a/v1"
    assert cfg["a2a"]["egress_idempotency"]["state_file"] == "/var/lib/aac/a2a-egress.db"  # the mounted state directory
    assert cfg["destinations"] == {}
    assert agent in (folder / "compose.env").read_text()
    if agent == "trip-planner":
        coa = cfg["classes_of_action"]["reserve_travel"]
        assert coa["valid_for"] == "+2h" and coa["predicates"] == {"action": "reserve_travel"}
    else:
        assert cfg["classes_of_action"] == {}
