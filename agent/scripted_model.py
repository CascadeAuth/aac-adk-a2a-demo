"""A stand-in for a language model that plays a fixed script, so the example runs without a model key.

Each agent in this example has one tool, and a model drives it in two moves: call the tool with the
order it was given, then answer in a sentence from what the tool returned. A live model makes those
moves from the words of the message; this script makes them from the JSON order inside the message.
Every run therefore gives the same result, and the tests can check it. Set AAC_DEMO_MODEL to replace
the script with a real model (README, "Run it with your own model").
"""
import json

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def order_in(content: types.Content) -> dict:
    """The JSON order carried as one of the message's text parts."""
    for part in content.parts:
        if part.text and part.text.lstrip().startswith("{"):
            return json.loads(part.text)
    raise ValueError("the message carries no JSON order for the script to act on")


class ScriptedModel(BaseLlm):
    model: str = "scripted"
    tool: str = ""  # the one tool this agent has

    async def generate_content_async(self, llm_request, stream=False):
        last = llm_request.contents[-1]
        results = [part.function_response.response for part in last.parts if part.function_response]
        if results:
            # Second move: the tool has run; say what it did, in the tool's own words.
            reply = types.Part(text=results[0]["summary"])
        else:
            # First move: call the tool with the order found in the message.
            reply = types.Part(function_call=types.FunctionCall(name=self.tool, args=order_in(last)))
        yield LlmResponse(content=types.Content(role="model", parts=[reply]))
