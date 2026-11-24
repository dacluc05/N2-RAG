import json

from google import genai
from google.genai import types
import httpx
from pydantic import SecretStr
import pytest

from finsight.agents import Gemini
from finsight.schema import Drafts, Selection
from finsight.transport import Budget, ProviderError


def test_official_sdk_sends_structured_output_schema(config):
    config = config.model_copy(update={"gemini_model":"test-model","gemini_api_key":SecretStr("test-key")})

    def respond(request):
        payload = json.loads(request.content)
        assert request.url.path.endswith("/models/test-model:generateContent")
        assert request.headers["x-goog-api-key"]=="test-key"
        generation = payload["generationConfig"]
        assert generation["responseMimeType"]=="application/json"
        assert "claims" in generation["responseJsonSchema"]["properties"]
        return httpx.Response(200,json={"candidates":[{"content":{"parts":[{"text":'{"claims": []}'}],
                                                                "role":"model"},"finishReason":"STOP"}],
                                        "usageMetadata":{"promptTokenCount":10,"candidatesTokenCount":4}})

    budget = Budget(8,0,1)
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = genai.Client(api_key="test-key",http_options=types.HttpOptions(httpx_client=transport))
        model = Gemini(config,budget,client=client)
        assert model.ask("Trả danh sách rỗng",{},Drafts).claims==[]
        assert budget.counts["gemini_input_tokens"]==10
        assert budget.counts["gemini_output_tokens"]==4
        with pytest.raises(ProviderError,match="hết ngân sách"):
            model.ask("Trả danh sách rỗng",{},Selection)
        model.close()


def test_schema_rejection_retries_json_and_reuses_that_mode(config):
    config = config.model_copy(update={"gemini_model":"test-model","gemini_api_key":SecretStr("test-key")})
    structured_calls = []

    def respond(request):
        payload = json.loads(request.content)
        structured = "responseJsonSchema" in payload["generationConfig"]
        structured_calls.append(structured)
        if structured:
            return httpx.Response(400, json={"error":{"code":400,"message":"Schema rejected","status":"INVALID_ARGUMENT"}})
        return httpx.Response(200, json={"candidates":[{"content":{"parts":[{"text":'{"claims": []}'}]}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = genai.Client(api_key="test-key", http_options=types.HttpOptions(httpx_client=transport))
        model = Gemini(config, Budget(8, 0, 3), client=client)
        assert model.ask("Trả danh sách rỗng", {}, Drafts).claims == []
        assert model.ask("Trả danh sách rỗng", {}, Drafts).claims == []
        assert structured_calls == [True, False, False]
        model.close()


def test_incomplete_json_is_retried_with_more_output_tokens(config):
    config = config.model_copy(update={"gemini_model":"test-model","gemini_api_key":SecretStr("test-key")})
    limits = []

    def respond(request):
        limits.append(json.loads(request.content)["generationConfig"]["maxOutputTokens"])
        first = len(limits) == 1
        return httpx.Response(200, json={"candidates":[{"finishReason":"MAX_TOKENS" if first else "STOP",
            "content":{"parts":[{"text":'{"claims":' if first else '{"claims": []}'}]}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = genai.Client(api_key="test-key", http_options=types.HttpOptions(httpx_client=transport))
        model = Gemini(config, Budget(8, 0, 2), client=client)
        assert model.ask("Trả JSON", {}, Drafts).claims == []
        assert limits == [max(4096, config.gemini_output_tokens), 8192]
        model.close()


def test_validation_retry_contains_actionable_feedback(config):
    config = config.model_copy(update={"gemini_model":"test-model","gemini_api_key":SecretStr("test-key")})
    prompts = []
    def respond(request):
        payload = json.loads(request.content)
        prompts.append(str(payload["systemInstruction"]))
        value = '{"claims": "bad"}' if len(prompts) == 1 else '{"claims": []}'
        return httpx.Response(200,json={"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":value}]}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = genai.Client(api_key="test-key",http_options=types.HttpOptions(httpx_client=transport))
        model = Gemini(config,Budget(8,0,2),client=client)
        assert model.ask("Trả JSON",{},Drafts).claims == []
        assert "list_type" in prompts[1] and "claims" in prompts[1]
        model.close()


def test_service_failure_is_not_reported_as_schema_failure(config):
    config = config.model_copy(update={"gemini_model":"test-model","gemini_api_key":SecretStr("test-key")})
    def respond(request):
        return httpx.Response(503,json={"error":{"code":503,"message":"Unavailable","status":"UNAVAILABLE"}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = genai.Client(api_key="test-key",http_options=types.HttpOptions(httpx_client=transport))
        model = Gemini(config,Budget(8,0,1),client=client)
        with pytest.raises(ProviderError,match="tạm quá tải"):
            model.ask("Trả JSON",{},Drafts)
        model.close()


def test_temporary_overload_recovers_with_one_budgeted_retry(config):
    config = config.model_copy(update={"gemini_model":"test-model","gemini_api_key":SecretStr("test-key")})
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503,json={"error":{"code":503,"message":"Unavailable","status":"UNAVAILABLE"}})
        return httpx.Response(200,json={"candidates":[{"content":{"parts":[{"text":'{"claims": []}'}]}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        client = genai.Client(api_key="test-key",http_options=types.HttpOptions(httpx_client=transport))
        budget = Budget(8,0,2)
        model = Gemini(config,budget,client=client)
        assert model.ask("Trả JSON",{},Drafts).claims == []
        assert len(calls) == budget.counts["model"] == 2
        model.close()
