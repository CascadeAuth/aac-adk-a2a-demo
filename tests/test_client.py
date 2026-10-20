"""The run client treats a successful acknowledgement as the start of the evidence, not its end."""
import copy
import json
import time

import pytest

TASK, ROOT, TOKEN = "po4143-test", "a" * 64, "b" * 64
BOOKING = "spiffe://tourfedia.example/booking"


def evidence(scenario="reservation"):
    held = {"order": "PO #4143", "origin": "Austin", "destination": "Shanghai", "departure": "12 May",
            "reservation_id": "synthetic-" + TASK, "amount": 8000, "currency": "USD", "payment_status": "unpaid"}
    if scenario == "fare-change":
        decision = {"action": "refuse", "reason": "The fare is now $9,500, above the $8,000 I may spend."}
        text = "No reservation: " + decision["reason"]
    else:
        decision = {"action": "settle", "settlement_id": held["reservation_id"], "action_summary": json.dumps(held, sort_keys=True)}
        text = "Reservation synthetic-po4143-test held for PO #4143, Austin to Shanghai on 12 May, $8,000, unpaid."
    acknowledged = {"task_ref": TASK, "status": "dispatched", "dispatch_id": "d-1", "a2a_response": {
        "jsonrpc": "2.0", "id": TASK, "result": {"message": {"messageId": "r", "contextId": "c", "role": "ROLE_AGENT",
                                                             "parts": [{"text": text}]}}}}
    common = {"result": "success", "root_token_id": ROOT, "task_ref": TASK}
    mint = {"event_type": "mint", **common, "token_id": ROOT}
    dispatch = {"event_type": "dispatch", **common, "token_id": TOKEN, "caveat_audience": BOOKING,
                "caveat_predicates": f"action:reserve_travel,amount_max:8000,originator_reference:PO #4143,task_ref:{TASK},valid_until:{int(time.time()) + 1800}"}
    receive = {"event_type": "receive", **common, "token_id": TOKEN, "actor_spiffe_id": BOOKING}
    action = {"token_id": TOKEN, "action_payload": {"task_ref": TASK, "decision": decision["action"], "agent_decision": decision}}
    return [acknowledged, mint, dispatch, receive, action, BOOKING, scenario]


def test_correlated_result(client_module):
    result = client_module.verify_result(*evidence())
    assert result["root_token_id"] == ROOT and result["decision"]["action"] == "settle"
    assert client_module.verify_result(*evidence("fare-change"))["decision"]["action"] == "refuse"


@pytest.mark.parametrize("index,key,value", [
    (0, "status", "retained"),
    (2, "root_token_id", "wrong"),
    (3, "token_id", "wrong"),
    (4, "token_id", "wrong"),
    (2, "caveat_audience", "spiffe://wrong.example/booking"),
    (3, "actor_spiffe_id", "spiffe://wrong.example/booking"),
    (2, "caveat_predicates", f"amount_max:9500,originator_reference:PO #4143,task_ref:{TASK}"),
])
def test_ack_or_mismatched_evidence_is_not_success(client_module, index, key, value):
    args = copy.deepcopy(evidence())
    args[index][key] = value
    with pytest.raises(AssertionError):
        client_module.verify_result(*args)


def test_a_reply_that_does_not_match_the_record_is_not_success(client_module):
    args = evidence()
    args[0]["a2a_response"]["result"]["message"]["parts"][0]["text"] = "Reservation synthetic-other held."
    with pytest.raises(AssertionError):
        client_module.verify_result(*args)


def test_waits_for_the_chain_and_fails_without_it(client_module, monkeypatch, capsys):
    acknowledged = evidence()[0]

    async def acknowledged_only(scenario):
        return acknowledged

    monkeypatch.setattr(client_module, "ask_trip_planner", acknowledged_only)
    monkeypatch.setattr(client_module, "matching", lambda *_: [])
    clock = iter(range(0, 100, 10))
    monkeypatch.setattr(client_module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(client_module.time, "sleep", lambda seconds: None)
    with pytest.raises(RuntimeError, match="No complete chain evidence for task po4143-test"):
        client_module.run("reservation")
    assert '"simulated_approval"' in capsys.readouterr().out


def test_matching_reads_rows_for_the_task_only(client_module, tmp_path):
    (tmp_path / "telemetry.jsonl").write_text(json.dumps({"event_type": "mint", "task_ref": TASK}) + "\n"
                                              + json.dumps({"event_type": "mint", "task_ref": "other"}) + "\n")
    (tmp_path / "actions.jsonl").write_text(json.dumps({"action_payload": {"task_ref": TASK}}) + "\n" + '{"partial')
    assert len(client_module.matching(tmp_path, "telemetry.jsonl", TASK)) == 1
    assert len(client_module.matching(tmp_path, "actions.jsonl", TASK)) == 1
