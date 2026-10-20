"""Vantis's run: the trip-planner agent decides, its sidecar sends, and the evidence is read back.

Every line printed is what a component returned or recorded: the agent's tool call, the sidecar's
acknowledgement with Tourfedia's reply inside it, and the chain events and action record the two
sidecars and the booking agent wrote. Nothing here is a summary of this program's own making.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx
from google.adk.runners import InMemoryRunner
from google.genai import types

import agent

APPROVAL = "Marc Sterling: PO #4143, Austin to Shanghai, departing 12 May, up to $8,000"


async def ask_trip_planner(scenario: str) -> dict:
    """Run the trip-planner once and return its tool's result: the sidecar's acknowledgement."""
    runner = InMemoryRunner(agent=agent.trip_planner, app_name="vantis")
    session = await runner.session_service.create_session(app_name="vantis", user_id="marc-sterling")
    order = {**agent.ORDER, "amount": 8000, "scenario": scenario}
    message = types.Content(role="user", parts=[
        types.Part(text="Marc Sterling, a director at Vantis Equity, approved this trip. Reserve it with Tourfedia."),
        types.Part(text=json.dumps(order))])
    result = None
    async for event in runner.run_async(user_id="marc-sterling", session_id=session.id, new_message=message):
        for part in event.content.parts if event.content else []:
            if part.function_call:
                print(json.dumps({"trip_planner_calls": part.function_call.name, "arguments": part.function_call.args}), flush=True)
            elif part.function_response:
                result = part.function_response.response
                print(json.dumps({"sidecar_acknowledged": result}), flush=True)
            elif part.text and event.is_final_response():
                print(json.dumps({"trip_planner_says": part.text}), flush=True)
    return result


def records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    result = []
    for index, line in enumerate(lines):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
            # The last line may still be in flight; the next poll reads it again.
    return result


def matching(directory: Path, filename: str, task: str) -> list[dict]:
    """The rows one agent recorded for this task."""
    if filename == "actions.jsonl":
        return [row for row in records(directory / filename) if row.get("action_payload", {}).get("task_ref") == task]
    return [row for row in records(directory / filename) if row.get("task_ref") == task]


def verify_result(acknowledged: dict, mint: dict, dispatch: dict, receive: dict, action: dict,
                  booking_id: str, scenario: str) -> dict:
    """Require one chain through both sidecars to the booking agent's record, then read the decision."""
    task = acknowledged["task_ref"]
    assert acknowledged["status"] == "dispatched", acknowledged
    assert "error" not in acknowledged["a2a_response"], acknowledged
    root = mint["root_token_id"]
    for row in (mint, dispatch, receive):
        assert row["result"] == "success" and row["root_token_id"] == root and row["task_ref"] == task, row
    assert receive["token_id"] == dispatch["token_id"] == action["token_id"], (dispatch, receive, action)
    assert dispatch["caveat_audience"] == booking_id and receive["actor_spiffe_id"] == booking_id
    limits = dict(part.split(":", 1) for part in dispatch["caveat_predicates"].split(","))
    assert int(limits["amount_max"]) == 8000 and limits["originator_reference"] == "PO #4143"
    assert limits["task_ref"] == task
    decision = action["action_payload"]["agent_decision"]
    reply = agent.reply_text(acknowledged["a2a_response"])
    if scenario == "fare-change":
        assert decision["action"] == "refuse" and "No reservation" in reply, (decision, reply)
    else:
        assert decision["action"] == "settle" and decision["settlement_id"] in reply, (decision, reply)
        held = json.loads(decision["action_summary"])
        assert held["amount"] == 8000 and held["payment_status"] == "unpaid" and held["order"] == "PO #4143"
    return {"task_ref": task, "root_token_id": root, "token_id": dispatch["token_id"], "decision": decision,
            "tourfedia_reply": reply, "mint": mint, "dispatch": dispatch, "receive": receive, "action": action}


def run(scenario: str = "reservation") -> dict:
    print(json.dumps({"simulated_approval": APPROVAL}), flush=True)
    acknowledged = asyncio.run(ask_trip_planner(scenario))
    assert acknowledged and acknowledged["status"] == "dispatched", acknowledged
    task = acknowledged["task_ref"]
    sender, receiver = Path("/evidence/vantis"), Path("/evidence/tourfedia")
    deadline = time.monotonic() + 30
    while True:
        sent = matching(sender, "telemetry.jsonl", task)
        got = matching(receiver, "telemetry.jsonl", task)
        actions = matching(receiver, "actions.jsonl", task)
        mint = next((e for e in sent if e["event_type"] == "mint"), None)
        dispatch = next((e for e in sent if e["event_type"] == "dispatch"), None)
        receive = next((e for e in got if e["event_type"] == "receive"), None)
        if mint and dispatch and receive and actions:
            evidence = verify_result(acknowledged, mint, dispatch, receive, actions[0],
                                     os.environ["AAC_DEMO_BOOKING_ID"], scenario)
            print(json.dumps({"evidence": evidence}), flush=True)
            return evidence
        if time.monotonic() >= deadline:
            found = {"mint": bool(mint), "dispatch": bool(dispatch), "receive": bool(receive), "action": bool(actions)}
            raise RuntimeError(f"No complete chain evidence for task {task} after 30 seconds; found {found}")
        time.sleep(0.25)


def wait_until_ready() -> None:
    for _ in range(90):
        try:
            if httpx.get(agent.SIDECAR + "/readyz").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError("Sidecar not ready after 90 seconds; inspect ./demo compose <agent> logs sidecar")


if __name__ == "__main__":
    if sys.argv[1] == "wait":
        wait_until_ready()
    else:
        run(sys.argv[1])
