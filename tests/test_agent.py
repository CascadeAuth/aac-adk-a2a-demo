"""Both agents on the scripted model, the pairing middleware, and a reply the sidecar accepts."""
import asyncio
import importlib
import json

import httpx
import pytest
import sidecar_rules
from aac_invoke_auth import sign_invoke_request, verify_invoke_request
from conftest import SECRET
from starlette.testclient import TestClient

TASK = "po4143-test"
VERIFIED = {"X-AAC-Task-Ref": TASK, "X-AAC-Presenter-Token-Id": "b" * 64,
            "X-AAC-Presenter-Spiffe-Id": "spiffe://vantis.example/trip-planner",
            "X-AAC-Originator-Tenant-Id": "tnt-11111111-1111-4111-8111-111111111111"}


def a2a_request(module, scenario="reservation"):
    order = {**module.ORDER, "amount": 8000, "scenario": scenario}
    return {"jsonrpc": "2.0", "id": TASK, "method": "SendMessage",
            "params": {"message": {"messageId": "m-1", "role": "ROLE_USER",
                                   "parts": [{"text": "Please reserve PO #4143: Austin to Shanghai, departing 12 May, up to $8,000."},
                                             {"text": json.dumps(order)}]}}}


def signed(body, secret=SECRET):
    headers = {"Content-Type": "application/json", "A2A-Version": "1.0", **VERIFIED}
    headers.update(sign_invoke_request(secret=secret, method="POST", path="/a2a/v1", headers=headers, body=body))
    return headers


def actions(agent_env):
    path = agent_env / "actions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_booking_holds_the_reservation_within_the_sidecars_reply_profile(agent_module, agent_env):
    body = json.dumps(a2a_request(agent_module)).encode()
    with TestClient(agent_module.app) as client:
        response = client.post("/a2a/v1", headers=signed(body), content=body)
    assert response.status_code == 200
    reply = response.json()
    assert sidecar_rules.check_reply(reply, TASK) == "task TASK_STATE_COMPLETED"
    # ADK's history carries the model's tool call and the tool's result; every entry has the context id.
    assert len(reply["result"]["task"]["history"]) == 4
    assert agent_module.reply_text(reply) == ("Reservation synthetic-po4143-test held for PO #4143, Austin to Shanghai "
                                              "on 12 May, $8,000, unpaid.")
    [record] = actions(agent_env)
    assert record["event_type"] == "action_taken" and record["token_id"] == "b" * 64
    assert record["action_payload"]["task_ref"] == TASK and record["action_payload"]["decision"] == "settle"
    assert record["action_payload"]["sender"] == VERIFIED["X-AAC-Presenter-Spiffe-Id"]
    assert json.loads(record["action_payload"]["agent_decision"]["action_summary"])["amount"] == 8000


def test_booking_declines_a_fare_above_the_authority(agent_module, agent_env):
    body = json.dumps(a2a_request(agent_module, "fare-change")).encode()
    with TestClient(agent_module.app) as client:
        reply = client.post("/a2a/v1", headers=signed(body), content=body).json()
    assert sidecar_rules.check_reply(reply, TASK) == "task TASK_STATE_COMPLETED"
    assert agent_module.reply_text(reply) == "No reservation: The fare is now $9,500, above the $8,000 I may spend."
    [record] = actions(agent_env)
    assert record["action_payload"]["decision"] == "refuse" and "synthetic" not in record["action_summary"]


@pytest.mark.parametrize("mode", ["absent", "wrong-pair", "altered"])
def test_unauthenticated_call_never_reaches_the_booking_agent(agent_module, agent_env, mode):
    body = json.dumps(a2a_request(agent_module)).encode()
    headers = {"Content-Type": "application/json", "A2A-Version": "1.0", **VERIFIED}
    if mode != "absent":
        headers = signed(body, SECRET if mode == "altered" else b"wrong")
    if mode == "altered":
        body += b" "
    with TestClient(agent_module.app) as client:
        assert client.post("/a2a/v1", headers=headers, content=body).status_code == 401
    assert actions(agent_env) == []


def test_adks_reply_passes_the_sidecar_rules_as_it_is(agent_module, agent_env):
    body = json.dumps(a2a_request(agent_module)).encode()
    with TestClient(agent_module.app) as client:
        reply = client.post("/a2a/v1", headers=signed(body), content=body).json()
    task = reply["result"]["task"]
    agent_messages = [m for m in task["history"] if m["role"] == "ROLE_AGENT"]
    if "message" in task["status"]:
        agent_messages.append(task["status"]["message"])
    assert agent_messages and all("contextId" not in m for m in agent_messages)  # ADK's own shape, untouched
    sidecar_rules.check_reply(reply, TASK)


def fake_sidecar(posted, status=200, reply_text="Reservation synthetic-x held for PO #4143."):
    def post(url, headers, content, timeout, trust_env=True):
        posted.update(url=url, headers=headers, body=content, envelope=json.loads(content), timeout=timeout, trust_env=trust_env)
        if status != 200:
            return httpx.Response(status, json={"error": {"code": "ERR_DESTINATION_NOT_FOUND", "message": "no such destination",
                                                          "detail": None, "request_id": "r-1"}})
        envelope = posted["envelope"]
        reply = {"jsonrpc": "2.0", "id": envelope["a2a_request"]["id"], "result": {"message": {
            "messageId": "r-1", "contextId": envelope["task_ref"], "role": "ROLE_AGENT", "parts": [{"text": reply_text}]}}}
        return httpx.Response(200, json={"a2a_response": reply, "dispatch_id": envelope["dispatch_id"], "status": "dispatched"})
    return post


def test_trip_planner_asks_its_sidecar_with_the_orders_limits(agent_module, agent_env, monkeypatch):
    posted = {}
    monkeypatch.setattr(agent_module.httpx, "post", fake_sidecar(posted))
    client = importlib.import_module("client")
    result, requested = asyncio.run(client.ask_trip_planner("reservation"))
    assert posted["url"] == "http://127.0.0.1:8080/v1/agent/a2a/dispatch" and posted["trust_env"] is False
    assert posted["headers"]["X-AAC-Envelope-Schema"] == "aac.a2a.egress.v1"
    # The signature the sidecar will check: over these headers and exactly these bytes.
    assert verify_invoke_request(secret=SECRET, method="POST", path="/v1/agent/a2a/dispatch",
                                 headers=posted["headers"], body=posted["body"]) is None
    assert requested["amount"] == 8000
    envelope = posted["envelope"]
    assert envelope["schema_version"] == "aac.a2a.egress.v1" and envelope["destination_profile"] == "tourfedia"
    assert envelope["authority"]["mode"] == "originate" and envelope["authority"]["class_of_action"] == "reserve_travel"
    assert envelope["authority"]["human_originator"]["sub"] == "marc-sterling"
    assert envelope["additional_predicates"] == {"amount_max": 8000, "originator_reference": "PO #4143",
                                                 "task_ref": envelope["task_ref"]}
    request = envelope["a2a_request"]
    assert request["method"] == "SendMessage" and request["id"] == envelope["task_ref"]
    text, order = request["params"]["message"]["parts"]
    assert text["text"].startswith("Please reserve PO #4143: Austin to Shanghai, departing 12 May, up to $8,000.")
    assert json.loads(order["text"]) == {**agent_module.ORDER, "amount": 8000, "scenario": "reservation"}
    assert result["status"] == "dispatched" and result["task_ref"] == envelope["task_ref"]
    assert result["summary"] == "Tourfedia answered: Reservation synthetic-x held for PO #4143."


def test_trip_planner_reports_a_refused_dispatch(agent_module, agent_env, monkeypatch):
    monkeypatch.setattr(agent_module.httpx, "post", fake_sidecar({}, status=404))
    client = importlib.import_module("client")
    result, _ = asyncio.run(client.ask_trip_planner("reservation"))
    assert result["status"] == "refused" and result["sidecar_error"]["error"]["code"] == "ERR_DESTINATION_NOT_FOUND"
    assert result["summary"] == "My sidecar refused to send the request: ERR_DESTINATION_NOT_FOUND, no such destination."


def test_the_rules_copy_refuses_credential_shaped_values_like_the_sidecar():
    reply = {"jsonrpc": "2.0", "id": TASK, "result": {"message": {"messageId": "r", "contextId": "c", "role": "ROLE_AGENT",
                                                                  "parts": [{"text": "ok"}]}}}
    assert sidecar_rules.check_reply(reply, TASK) == "message"
    for smuggled in ({"metadata": {"X-AAC-Task-Ref": "t"}}, {"metadata": {"note": "Bearer abcdefghijklmnopqrstuvwxyz"}},
                     {"metadata": {"note": "AAC-Macaroon abc"}}):
        with pytest.raises(AssertionError, match="credential-shaped"):
            sidecar_rules.check_reply({**reply, **smuggled}, TASK)
    # Ordinary long base64url text is not a credential; the sidecar decodes a real one, which this copy does not claim.
    assert sidecar_rules.check_reply({**reply, "metadata": {"note": "A" * 400}}, TASK) == "message"


@pytest.mark.parametrize("error,reason", [
    ({"code": True, "message": "x"}, "integer"),
    ({"code": -32601, "message": "x", "data": [{"@type": 123}]}, "typed-object list"),
    ({"code": -32601, "message": "x", "data": [{"@type": ""}]}, "typed-object list"),
])
def test_the_rules_copy_refuses_the_error_shapes_the_sidecar_refuses(error, reason):
    with pytest.raises(AssertionError, match=reason):
        sidecar_rules.check_reply({"jsonrpc": "2.0", "id": TASK, "error": error}, TASK)
    good = {"jsonrpc": "2.0", "id": TASK, "error": {"code": -32601, "message": "x", "data": [{"@type": "example.Detail"}]}}
    assert sidecar_rules.check_reply(good, TASK) == "error"


def test_booking_holds_to_the_delivered_amount_whatever_its_model_asks_for(agent_module, agent_env):
    from google.adk.agents import LlmAgent
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    class Inflating(agent_module.ScriptedModel):
        """A model that asks the tool for more than the sender allowed."""
        async def generate_content_async(self, llm_request, stream=False):
            last = llm_request.contents[-1]
            if any(part.function_response for part in last.parts):
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="Held at $9,500.")]))
            else:
                args = {**agent_module.ORDER, "amount": 9500, "scenario": "reservation"}
                yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name="hold_reservation", args=args))]))

    agent = LlmAgent(name="booking", model=Inflating(tool="hold_reservation"), tools=[agent_module.hold_reservation])
    body = json.dumps(a2a_request(agent_module)).encode()  # the delivered order allows $8,000
    with TestClient(agent_module.a2a_app(agent)) as client:
        reply = client.post("/a2a/v1", headers=signed(body), content=body).json()
    assert sidecar_rules.check_reply(reply, TASK) == "task TASK_STATE_COMPLETED"
    [record] = actions(agent_env)
    held = json.loads(record["action_payload"]["agent_decision"]["action_summary"])
    assert record["action_payload"]["decision"] == "settle" and held["amount"] == 8000
    assert record["action_payload"]["payload"]["amount"] == 8000 and record["action_payload"]["model_asked_for"]["amount"] == 9500


def test_reply_text_reads_messages_tasks_and_errors(agent_module):
    task = {"result": {"task": {"status": {"message": {"parts": [{"text": "Done."}]}},
                                "artifacts": [{"parts": [{"text": "Held."}, {"data": {}}]}]}}}
    assert agent_module.reply_text(task) == "Done. Held."
    assert agent_module.reply_text({"error": {"code": -32601, "message": "unknown method"}}) == "error -32601: unknown method"


def test_model_selection_follows_the_environment(agent_module, monkeypatch):
    assert type(agent_module.model("x")).__name__ == "ScriptedModel"
    monkeypatch.setenv("AAC_DEMO_MODEL", "gemini-2.5-flash")
    assert agent_module.model("x") == "gemini-2.5-flash"
