"""The two ADK agents, and what each one hands to AAC.

Vantis Equity's trip-planner asks Tourfedia's booking agent to reserve a trip. Its one tool sends an
A2A message through its own sidecar, which mints the authority for the task, narrows it to the order,
signs the request and delivers it. Tourfedia's booking agent is served over A2A by ADK itself; its
sidecar verifies the sender's authority before the message reaches it, and its one tool holds the
reservation within that authority and records what it did. Keys, tokens and proofs stay in the sidecars.

Marc Sterling's approval and Tourfedia's inventory are simulated.
"""
import contextvars
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from aac_invoke_auth import sign_invoke_request
from aac_invoke_auth.fastapi import InvokeAuthGuard, InvokeAuthMiddleware
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig, ExecuteInterceptor
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import LlmAgent
from scripted_model import ScriptedModel

ORDER = {"order": "PO #4143", "origin": "Austin", "destination": "Shanghai", "departure": "12 May"}
SIDECAR = "http://127.0.0.1:8080"  # this agent's own sidecar, on the pair's loopback
DISPATCH_PATH = "/v1/agent/a2a/dispatch"


def model(tool: str):
    """The scripted model, unless AAC_DEMO_MODEL names a real one (README, "Run it with your own model")."""
    name = os.environ.get("AAC_DEMO_MODEL", "")
    if not name:
        return ScriptedModel(tool=tool)
    if "/" in name:  # a LiteLLM name such as ollama_chat/llama3.1
        from google.adk.models.lite_llm import LiteLlm
        return LiteLlm(model=name)
    return name  # a Gemini model name; ADK reads GOOGLE_API_KEY


def pairing_secret() -> bytes:
    return Path(os.environ["AAC_INVOKE_AUTH_SECRET_FILE"]).read_bytes().strip()


# ---- Vantis Equity: the trip-planner and its one tool -----------------------------------------------------

def request_reservation(order: str, origin: str, destination: str, departure: str, amount: int,
                        scenario: str = "reservation") -> dict:
    """Ask Tourfedia's booking agent to reserve the trip, with authority to spend up to the amount.

    The request goes to this agent's own sidecar, which mints root authority for the task under the
    class reserve_travel, narrows it to this order and amount, signs the A2A message and delivers it to
    Tourfedia's sidecar. The acknowledgement carries Tourfedia's reply as its sidecar returned it.
    """
    task_ref = "po4143-" + uuid.uuid4().hex[:12]
    request = {"order": order, "origin": origin, "destination": destination, "departure": departure,
               "amount": amount, "scenario": scenario}
    envelope = {
        "schema_version": "aac.a2a.egress.v1",
        "dispatch_id": str(uuid.uuid4()),
        "destination_profile": "tourfedia",
        "task_ref": task_ref,
        "authority": {
            "mode": "originate",
            "class_of_action": "reserve_travel",
            # A real agent takes these from the signed-in user's session; Marc's approval is simulated.
            "human_originator": {"iss": "https://login.vantis.example", "sub": "marc-sterling",
                                 "auth_time_unix_seconds": int(time.time())},
        },
        # The limits Tourfedia's sidecar will see on the authority: this order, this amount, this task.
        "additional_predicates": {"amount_max": amount, "originator_reference": order, "task_ref": task_ref},
        "a2a_request": {
            "jsonrpc": "2.0", "id": task_ref, "method": "SendMessage",
            "params": {"message": {
                "messageId": str(uuid.uuid4()), "role": "ROLE_USER",
                "parts": [{"text": f"Please reserve {order}: {origin} to {destination}, departing {departure}, "
                                   f"up to ${amount:,}."},
                          {"text": json.dumps(request)}],
            }},
        },
    }
    body = json.dumps(envelope, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json", "X-AAC-Envelope-Schema": "aac.a2a.egress.v1"}
    headers.update(sign_invoke_request(secret=pairing_secret(), method="POST", path=DISPATCH_PATH,
                                       headers=headers, body=body))
    # trust_env=False: a proxy setting in the container's environment must not divert this loopback call.
    response = httpx.post(SIDECAR + DISPATCH_PATH, headers=headers, content=body, timeout=65, trust_env=False)
    answer = response.json()
    if response.status_code != 200:
        error = answer.get("error", {})  # the sidecar's error envelope: {"error": {"code", "message", ...}}
        return {"task_ref": task_ref, "status": "refused", "sidecar_error": answer,
                "summary": f"My sidecar refused to send the request: {error.get('code')}, {error.get('message')}."}
    return {"task_ref": task_ref, "status": answer["status"], "dispatch_id": answer["dispatch_id"],
            "a2a_response": answer["a2a_response"],
            "summary": "Tourfedia answered: " + reply_text(answer["a2a_response"])}


def reply_text(a2a_response: dict) -> str:
    """The sentences in the peer's JSON-RPC reply: its message, or its task's answer and artifacts."""
    if "error" in a2a_response:
        return f"error {a2a_response['error'].get('code')}: {a2a_response['error'].get('message')}"
    result = a2a_response["result"]
    messages = [result["message"]] if "message" in result else []
    if "task" in result:
        messages += [result["task"]["status"].get("message", {})] + result["task"].get("artifacts", [])
    return " ".join(part["text"] for item in messages for part in item.get("parts", []) if "text" in part)


trip_planner = LlmAgent(
    name="trip_planner", model=model("request_reservation"),
    instruction="You plan business travel for Vantis Equity. When given an order, ask Tourfedia to reserve "
                "it with the request_reservation tool, then tell the user what Tourfedia answered.",
    tools=[request_reservation])


# ---- Tourfedia: the booking agent and its one tool -------------------------------------------------------

# What the sidecar verified about the message being handled: the task, the presenting workload and the
# originating tenant from the X-AAC-* headers it signed (set per request by VerifiedContext below), and
# the order exactly as the delivered message carries it (set by remember_the_order below).
verified = contextvars.ContextVar("verified")


def hold_reservation(order: str, origin: str, destination: str, departure: str, amount: int,
                     scenario: str = "reservation") -> dict:
    """Hold an unpaid reservation for the trip if the fare is within the amount the sender may spend.

    The arguments are what the model read from the message. The limit, the fare and the record come from
    the order as the sidecar delivered it, so a model that asks for more than the sender allowed cannot
    raise what Tourfedia holds.
    """
    context = verified.get()
    delivered = context["order"]
    allowed = int(delivered["amount"])
    fare = 9500 if delivered.get("scenario") == "fare-change" else allowed  # the fare-change run simulates a price rise
    if fare > allowed:
        decision = {"action": "refuse", "reason": f"The fare is now ${fare:,}, above the ${allowed:,} I may spend."}
        summary = f"No reservation: {decision['reason']}"
    else:
        reservation = "synthetic-" + context["task_ref"]
        result = {"order": delivered["order"], "origin": delivered["origin"], "destination": delivered["destination"],
                  "departure": delivered["departure"], "reservation_id": reservation, "amount": fare,
                  "currency": "USD", "payment_status": "unpaid"}
        decision = {"action": "settle", "settlement_id": reservation, "action_summary": json.dumps(result, sort_keys=True)}
        summary = (f"Reservation {reservation} held for {result['order']}, {result['origin']} to {result['destination']} "
                   f"on {result['departure']}, ${fare:,}, unpaid.")
    # The public eight-field action record; the token comes from the verified context, never the message.
    record = {"timestamp_unix_seconds": time.time(), "event_type": "action_taken",
              "tenant_id": os.environ["AAC_TENANT_ID"], "tenant_short": "Tourfedia",
              "token_id": context["presenter_token_id"], "actor_spiffe_id": os.environ["AAC_WORKLOAD_SPIFFE_ID"],
              "action_summary": decision.get("action_summary") or decision["reason"],
              "action_payload": {"task_ref": context["task_ref"], "decision": decision["action"],
                                 "agent_decision": decision, "sender": context["presenter_spiffe_id"],
                                 "originator_tenant_id": context["originator_tenant_id"],
                                 "payload": {"order": delivered["order"], "amount": allowed, "scenario": delivered.get("scenario")},
                                 "model_asked_for": {"order": order, "amount": amount, "scenario": scenario}}}
    with Path(os.environ["AAC_DEMO_ACTIONS"]).open("a", encoding="utf-8") as output:
        output.write(json.dumps(record) + "\n")
    return {**decision, "summary": summary}


booking = LlmAgent(
    name="booking", model=model("hold_reservation"),
    instruction="You take reservations for Tourfedia. When a request arrives, hold it with the "
                "hold_reservation tool, then answer with what the tool reported.",
    tools=[hold_reservation])


class VerifiedContext:
    """Keeps the verified X-AAC-* headers of the message being handled where the tool can read them."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/a2a/v1":
            headers = {name.decode().lower(): value.decode() for name, value in scope["headers"]}
            verified.set({"task_ref": headers.get("x-aac-task-ref", ""),
                          "presenter_token_id": headers.get("x-aac-presenter-token-id", ""),
                          "presenter_spiffe_id": headers.get("x-aac-presenter-spiffe-id", ""),
                          "originator_tenant_id": headers.get("x-aac-originator-tenant-id", "")})
        await self.app(scope, receive, send)


async def remember_the_order(context):
    """Keep the order as the verified message carries it, next to the headers, before the model runs."""
    for part in context.message.parts:
        if part.HasField("text") and part.text.lstrip().startswith("{"):
            verified.get()["order"] = json.loads(part.text)
    return context


def a2a_app(agent: LlmAgent):
    """ADK's A2A server for the agent, reachable only through the sidecar: the pairing signature is checked first."""
    app = to_a2a(agent, rpc_path="a2a/v1", agent_executor_factory=lambda runner: A2aAgentExecutor(
        runner=runner, config=A2aAgentExecutorConfig(execute_interceptors=[
            ExecuteInterceptor(before_agent=remember_the_order)])))
    app.add_middleware(VerifiedContext)
    app.add_middleware(InvokeAuthMiddleware, guard=InvokeAuthGuard.from_env(), protected_paths=("/a2a/v1",))
    return app


# Each pair's container serves its own agent over A2A; only Tourfedia's is ever called in this example.
app = a2a_app({"trip-planner": trip_planner, "booking": booking}[os.environ["AAC_DEMO_ROLE"]])
