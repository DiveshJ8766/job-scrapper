import json

import httpx
import pytest

from pipeline.classify.llm import LLMClient, PermanentLLMError, TransientLLMError


def client_with(handler, provider="gemini", model="gemini-2.5-flash-lite"):
    c = LLMClient(provider, model, "test-key")
    c._http = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def test_gemini_request_and_usage():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["key"] = req.headers["x-goog-api-key"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": '{"a":1}'}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 800, "candidatesTokenCount": 30, "thoughtsTokenCount": 5},
        })

    r = client_with(handler).complete_json("sys", "user")
    assert seen["url"].endswith("/models/gemini-2.5-flash-lite:generateContent")
    assert seen["key"] == "test-key"
    gc = seen["body"]["generationConfig"]
    assert gc["temperature"] == 0.0 and gc["responseMimeType"] == "application/json"
    assert gc["responseSchema"]["properties"]["role"]["enum"][0] == "Frontend Developer"
    assert (r.text, r.input_tokens, r.output_tokens) == ('{"a":1}', 800, 35)


def test_openai_request_and_usage():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"b":2}'}}],
            "usage": {"prompt_tokens": 700, "completion_tokens": 25},
        })

    r = client_with(handler, "openai", "gpt-4o-mini").complete_json("sys", "user")
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["response_format"]["json_schema"]["strict"] is True
    assert seen["body"]["temperature"] == 0.0
    assert (r.input_tokens, r.output_tokens) == (700, 25)


def test_openai_reasoning_model_omits_temperature():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}], "usage": {}})

    client_with(handler, "openai", "gpt-5-mini").complete_json("s", "u")
    assert "temperature" not in seen["body"]


@pytest.mark.parametrize("status,exc", [(429, TransientLLMError), (503, TransientLLMError),
                                        (400, PermanentLLMError), (401, PermanentLLMError)])
def test_error_classification(status, exc):
    c = client_with(lambda req: httpx.Response(status, text="err"))
    with pytest.raises(exc):
        c.complete_json("s", "u")


def test_missing_key_is_permanent():
    with pytest.raises(PermanentLLMError):
        LLMClient("gemini", "m", "")
