"""A test-only copy of the sidecar's A2A reply rules.

The sidecar checks every reply the booking agent returns before it sends it on to the peer
(aac-sidecar-go `internal/a2a/response.go`: ValidateResponse, validateResponseMessage,
validateTerminalTask; `profile.go`: validatePart). These functions mirror those checks so the tests
can tell whether ADK's reply would be accepted. Compare them with the sidecar release named in
tests/fixtures/components.json whenever that release changes.

Not mirrored here, because they concern the transport rather than the JSON: the sidecar also requires
HTTP 200, exactly one Content-Type of application/json, no Content-Encoding, a body within the configured
size, nesting and node limits, and no duplicate object members (`service.go`). Also not mirrored: the
sidecar's detection of a raw AAC credential inside a string, which needs its wire decoder; the reply never
carries one, and this copy claims nothing about that case.
"""
import base64
import json
import re

TERMINAL = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}
BEARER = re.compile(r"(?i)^bearer [A-Za-z0-9\-._~+/]{16,}=*$")
BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def smuggles_a_credential(value):
    """A credential-shaped key or string anywhere in the reply (profile.go securitySmuggling); the sidecar
    refuses the whole reply. ADK copies a tool's return value into the reply verbatim, so this matters."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = "".join(c.lower() for c in key if c.isalnum())
            if normalized == "aacmacaroon" or normalized.startswith("xaac") or smuggles_a_credential(child):
                return True
    if isinstance(value, list):
        return any(smuggles_a_credential(child) for child in value)
    if isinstance(value, str):
        return value.lower().startswith("aac-macaroon ") or bool(BEARER.match(value)) or is_dpop_jws(value)
    return False


def is_dpop_jws(value):
    segments = value.split(".")
    if len(segments) != 3 or not all(segment and BASE64URL.match(segment) for segment in segments):
        return False
    try:
        header = json.loads(base64.urlsafe_b64decode(segments[0] + "=" * (-len(segments[0]) % 4)))
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(header, dict) and header.get("typ") in ("dpop+jwt", "aac-dpop+jwt")


def check_part(part):
    assert isinstance(part, dict), "part must be an object"
    assert "raw" not in part and "url" not in part, "file and URL parts are disabled"
    assert ("text" in part) != ("data" in part), "part must contain exactly one text or data value"
    if "text" in part:
        assert isinstance(part["text"], str), "text part must be a string"
    if "data" in part and "mediaType" in part:
        assert part["mediaType"] == "application/json", "data part mediaType must be application/json"
    if "metadata" in part:
        assert isinstance(part["metadata"], dict), "metadata must be an object"


def check_message(message, roles):
    assert isinstance(message, dict), "response message must be an object"
    assert isinstance(message.get("messageId"), str) and message["messageId"], "response messageId is required"
    if "contextId" in message:
        assert isinstance(message["contextId"], str) and message["contextId"], "response contextId must be a nonempty string"
    assert message.get("role") in roles, "response message role is invalid"
    assert "referenceTaskIds" not in message, "task references are outside the unary pilot"
    parts = message.get("parts")
    assert isinstance(parts, list) and parts, "response message needs parts"
    for part in parts:
        check_part(part)
    if "metadata" in message:
        assert isinstance(message["metadata"], dict), "response metadata must be an object"


def check_task(task):
    assert isinstance(task, dict), "response task must be an object"
    for field in ("id", "contextId"):
        assert isinstance(task.get(field), str) and task[field], f"response task {field} is required"
    status = task.get("status")
    assert isinstance(status, dict), "response task status is required"
    assert status.get("state") in TERMINAL, "non-terminal or unknown tasks are outside the unary pilot"
    if "message" in status:
        check_message(status["message"], {"ROLE_AGENT"})
    if "metadata" in task:
        assert isinstance(task["metadata"], dict), "task metadata must be an object"
    assert isinstance(task.get("artifacts", []), list), "task artifacts must be a list"
    for artifact in task.get("artifacts", []):
        assert isinstance(artifact, dict), "artifact must be an object"
        assert isinstance(artifact.get("artifactId"), str) and artifact["artifactId"], "artifactId is required"
        if "metadata" in artifact:
            assert isinstance(artifact["metadata"], dict), "artifact metadata must be an object"
        assert isinstance(artifact.get("parts"), list) and artifact["parts"], "artifact needs parts"
        for part in artifact["parts"]:
            check_part(part)
    assert isinstance(task.get("history", []), list), "task history must be a list"
    for message in task.get("history", []):
        check_message(message, {"ROLE_USER", "ROLE_AGENT"})
    return "task " + status["state"]


def check_reply(value, request_id):
    """Raise AssertionError with the sidecar's reason, or return what the reply holds."""
    assert value.get("jsonrpc") == "2.0", "response jsonrpc must be 2.0"
    assert value.get("id") == request_id, "response ID type and value must be preserved"
    assert not smuggles_a_credential(value), "credential-shaped values are forbidden in the A2A response"
    assert ("result" in value) != ("error" in value), "response must contain exactly one result or error"
    if "error" in value:
        error = value["error"]
        code = error.get("code") if isinstance(error, dict) else None
        assert isinstance(code, int) and not isinstance(code, bool), "error code must be an integer"
        assert isinstance(error.get("message"), str) and error["message"], "error message is required"
        if "data" in error:
            assert isinstance(error["data"], list) and all(
                isinstance(item, dict) and isinstance(item.get("@type"), str) and item["@type"] for item in error["data"]), \
                "A2A error data must be a typed-object list"
        return "error"
    result = value["result"]
    assert isinstance(result, dict), "result must be an object"
    assert ("message" in result) != ("task" in result), "SendMessage result needs exactly one message or task"
    if "message" in result:
        check_message(result["message"], {"ROLE_AGENT"})
        return "message"
    return check_task(result["task"])
