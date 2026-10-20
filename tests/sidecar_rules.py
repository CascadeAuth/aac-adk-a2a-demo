"""A test-only copy of the sidecar's A2A reply rules.

The sidecar checks every reply the booking agent returns before it sends it on to the peer
(aac-sidecar-go `internal/a2a/response.go`: ValidateResponse, validateResponseMessage,
validateTerminalTask; `profile.go`: validatePart). These functions mirror those checks so the tests
can tell whether ADK's reply would be accepted. Compare them with the sidecar release named in
tests/fixtures/components.json whenever that release changes.
"""
TERMINAL = {"TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED"}


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
    for field in ("messageId", "contextId"):
        assert isinstance(message.get(field), str) and message[field], f"response {field} is required"
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
    for artifact in task.get("artifacts", []):
        assert isinstance(artifact.get("artifactId"), str) and artifact["artifactId"], "artifactId is required"
        assert isinstance(artifact.get("parts"), list) and artifact["parts"], "artifact needs parts"
        for part in artifact["parts"]:
            check_part(part)
    for message in task.get("history", []):
        check_message(message, {"ROLE_USER", "ROLE_AGENT"})
    return "task " + status["state"]


def check_reply(value, request_id):
    """Raise AssertionError with the sidecar's reason, or return what the reply holds."""
    assert value.get("jsonrpc") == "2.0", "response jsonrpc must be 2.0"
    assert value.get("id") == request_id, "response ID type and value must be preserved"
    assert ("result" in value) != ("error" in value), "response must contain exactly one result or error"
    if "error" in value:
        error = value["error"]
        assert isinstance(error, dict) and isinstance(error.get("code"), int), "error code must be an integer"
        assert isinstance(error.get("message"), str) and error["message"], "error message is required"
        return "error"
    result = value["result"]
    assert isinstance(result, dict), "result must be an object"
    assert ("message" in result) != ("task" in result), "SendMessage result needs exactly one message or task"
    if "message" in result:
        check_message(result["message"], {"ROLE_AGENT"})
        return "message"
    return check_task(result["task"])
