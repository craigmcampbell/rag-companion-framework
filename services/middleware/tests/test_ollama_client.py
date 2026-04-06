"""
test_ollama_client.py — Tests for the Ollama client.

Tier 1: Pure logic tests using mocks. No Ollama connection required.
         Tests JSON parsing, error handling, retry behavior, heartbeat.

Tier 2: Live inference tests. Requires Ollama running with mistral-nemo:12b.
         Tests that the model actually responds and returns parseable JSON
         for the kinds of prompts the extractor and assessor will send.
"""

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaGenerationError,
    OllamaJSONError,
    _parse_json_response,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_mock_response(text: str, status: int = 200) -> MagicMock:
    """Build a mock httpx.Response."""
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = {"response": text}
    mock.text = text
    mock.raise_for_status = MagicMock()
    if status >= 400:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status}",
            request=MagicMock(),
            response=mock,
        )
    return mock


def make_client_with_response(response_text: str) -> OllamaClient:
    """Return an OllamaClient whose HTTP calls return a fixed response."""
    client = OllamaClient()
    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(return_value=make_mock_response(response_text))
    mock_http.get = AsyncMock(return_value=make_mock_response("{}"))
    client._client = mock_http
    return client


# ── Tier 1: JSON parsing (pure logic, no async) ───────────────────────────────

def test_parse_clean_json():
    result = _parse_json_response('{"key": "value"}')
    assert result == {"key": "value"}


def test_parse_json_with_whitespace():
    result = _parse_json_response('  \n{"key": "value"}\n  ')
    assert result == {"key": "value"}


def test_parse_fenced_json():
    result = _parse_json_response('```json\n{"key": "value"}\n```')
    assert result == {"key": "value"}


def test_parse_fenced_json_no_language():
    result = _parse_json_response('```\n{"key": "value"}\n```')
    assert result == {"key": "value"}


def test_parse_json_embedded_in_text():
    result = _parse_json_response('Here is the result: {"key": "value"} hope that helps!')
    assert result == {"key": "value"}


def test_parse_json_nested():
    raw = '{"events": ["Garion returned", "Senna noticed"], "significance": "normal"}'
    result = _parse_json_response(raw)
    assert result["events"] == ["Garion returned", "Senna noticed"]


def test_parse_invalid_json_raises():
    try:
        _parse_json_response("this is not json at all")
        assert False, "Should have raised OllamaJSONError"
    except OllamaJSONError:
        pass


def test_parse_empty_raises():
    try:
        _parse_json_response("")
        assert False, "Should have raised OllamaJSONError"
    except OllamaJSONError:
        pass


def test_parse_partial_json_raises():
    try:
        _parse_json_response('{"key": "val')
        assert False, "Should have raised OllamaJSONError"
    except OllamaJSONError:
        pass


# ── Tier 1: Client behavior (mocked HTTP) ────────────────────────────────────

async def test_generate_returns_text():
    client = make_client_with_response("Senna looked up from her work.")
    result = await client.generate("say something")
    assert result == "Senna looked up from her work."


async def test_generate_json_clean_response():
    client = make_client_with_response('{"events": ["test event"]}')
    result = await client.generate_json("extract events")
    assert result == {"events": ["test event"]}


async def test_generate_json_fenced_response():
    client = make_client_with_response('```json\n{"events": ["test event"]}\n```')
    result = await client.generate_json("extract events")
    assert result == {"events": ["test event"]}


async def test_generate_json_retries_on_bad_json():
    """First response is bad JSON, second is good — should succeed via retry."""
    client = OllamaClient()
    mock_http = AsyncMock()
    mock_http.is_closed = False

    call_count = 0

    async def post_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        text = "not json" if call_count == 1 else '{"events": ["recovered"]}'
        return make_mock_response(text)

    mock_http.post = post_side_effect
    client._client = mock_http

    result = await client.generate_json("extract events")
    assert result == {"events": ["recovered"]}
    assert call_count == 2


async def test_generate_json_raises_after_two_failures():
    """Both attempts return bad JSON — should raise OllamaJSONError."""
    client = make_client_with_response("this is not json")
    try:
        await client.generate_json("extract events")
        assert False, "Should have raised OllamaJSONError"
    except OllamaJSONError as e:
        assert "retry" in str(e).lower()


async def test_generate_raises_on_connection_error():
    client = OllamaClient()
    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    client._client = mock_http

    try:
        await client.generate("hello")
        assert False, "Should have raised OllamaConnectionError"
    except OllamaConnectionError as e:
        assert "Ollama" in str(e)


async def test_generate_raises_on_timeout():
    client = OllamaClient()
    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    client._client = mock_http

    try:
        await client.generate("hello")
        assert False, "Should have raised OllamaConnectionError"
    except OllamaConnectionError as e:
        assert "timed out" in str(e).lower()


async def test_generate_raises_on_http_error():
    client = OllamaClient()
    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.post = AsyncMock(return_value=make_mock_response("error", status=500))
    client._client = mock_http

    try:
        await client.generate("hello")
        assert False, "Should have raised OllamaGenerationError"
    except OllamaGenerationError:
        pass


async def test_generate_includes_system_prompt():
    client = make_client_with_response("response text")
    await client.generate("user prompt", system="you are helpful")
    call_kwargs = client._client.post.call_args.kwargs
    payload = call_kwargs.get("json", {})
    assert payload.get("system") == "you are helpful"


async def test_generate_no_system_prompt_by_default():
    client = make_client_with_response("response text")
    await client.generate("user prompt")
    call_kwargs = client._client.post.call_args.kwargs
    payload = call_kwargs.get("json", {})
    assert "system" not in payload


async def test_generate_model_override():
    client = make_client_with_response("response text")
    await client.generate("prompt", model="llama3")
    call_kwargs = client._client.post.call_args.kwargs
    payload = call_kwargs.get("json", {})
    assert payload["model"] == "llama3"


async def test_heartbeat_true_when_model_available():
    client = OllamaClient(model="mistral-nemo:12b")
    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "models": [{"name": "mistral-nemo:12b"}]
    }
    mock_http.get = AsyncMock(return_value=mock_response)
    client._client = mock_http

    assert await client.heartbeat() is True


async def test_heartbeat_false_when_model_missing():
    client = OllamaClient(model="mistral-nemo:12b")
    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"models": [{"name": "llama3"}]}
    mock_http.get = AsyncMock(return_value=mock_response)
    client._client = mock_http

    assert await client.heartbeat() is False


async def test_heartbeat_false_on_connection_error():
    client = OllamaClient()
    mock_http = AsyncMock()
    mock_http.is_closed = False
    mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    client._client = mock_http

    assert await client.heartbeat() is False


# ── Tier 2: Live inference ────────────────────────────────────────────────────

async def run_live_inference():
    """
    Requires Ollama running with mistral-nemo:12b.
    Tests that the model returns valid JSON for extraction-style prompts.
    """
    client = OllamaClient()

    # Verify connectivity first
    reachable = await client.heartbeat()
    if not reachable:
        raise AssertionError(
            "Ollama not reachable or mistral-nemo:12b not available. "
            "Run: ollama pull mistral-nemo:12b"
        )

    # Test 1: Basic JSON generation
    result = await client.generate_json(
        prompt="""Extract memory from this exchange. Return JSON only, no other text.

User: The contact wanted double. I paid what you gave me and walked.
Assistant: Senna looked up. "He was testing you. You did right."

Return this exact structure:
{
  "events": ["list of things that happened"],
  "revelations": ["list of things learned"],
  "state_changes": ["list of how things shifted"],
  "notable_quote": "one memorable line or null"
}"""
    )

    assert isinstance(result, dict), "Response should be a dict"
    assert "events" in result, "Response should have events key"
    assert isinstance(result["events"], list), "events should be a list"

    # Test 2: Model correctly identifies a low-signal exchange
    result2 = await client.generate_json(
        prompt="""Is this exchange worth remembering long-term?
        
User: Do you want tea?
Assistant: Please. Thank you.

Return JSON only:
{
  "worth_remembering": true or false,
  "reason": "brief explanation"
}"""
    )

    assert "worth_remembering" in result2, "Response should have worth_remembering key"
    assert result2["worth_remembering"] is False, \
        "Tea exchange should not be marked as worth remembering"

    await client.close()


# ── Test runner ───────────────────────────────────────────────────────────────

async def run(tier: int = 1):
    tier1_tests = [
        # Pure logic
        test_parse_clean_json,
        test_parse_json_with_whitespace,
        test_parse_fenced_json,
        test_parse_fenced_json_no_language,
        test_parse_json_embedded_in_text,
        test_parse_json_nested,
        test_parse_invalid_json_raises,
        test_parse_empty_raises,
        test_parse_partial_json_raises,
    ]

    tier1_async_tests = [
        # Mocked HTTP
        test_generate_returns_text,
        test_generate_json_clean_response,
        test_generate_json_fenced_response,
        test_generate_json_retries_on_bad_json,
        test_generate_json_raises_after_two_failures,
        test_generate_raises_on_connection_error,
        test_generate_raises_on_timeout,
        test_generate_raises_on_http_error,
        test_generate_includes_system_prompt,
        test_generate_no_system_prompt_by_default,
        test_generate_model_override,
        test_heartbeat_true_when_model_available,
        test_heartbeat_false_when_model_missing,
        test_heartbeat_false_on_connection_error,
    ]

    failed = []

    for test in tier1_tests:
        try:
            test()
        except Exception as e:
            failed.append((test.__name__, str(e)))

    for test in tier1_async_tests:
        try:
            await test()
        except Exception as e:
            failed.append((test.__name__, str(e)))

    if failed:
        msg = "\n".join(f"  {name}: {err}" for name, err in failed)
        raise AssertionError(f"{len(failed)} tier 1 test(s) failed:\n{msg}")

    if tier >= 2:
        await run_live_inference()