"""
ollama_client.py — Async Ollama client for local inference.

Used by memory extractor, clock assessor, and state manager for
structured output generation. Intentionally thin — just HTTP calls
with robust JSON handling and clear error types.

Does NOT:
- Know anything about campaigns, characters, or prompts
- Retry indefinitely (one retry on malformed JSON, then raises)
- Block — all calls are async
"""

from __future__ import annotations
import asyncio
import json
import re
from typing import Any, Optional

import httpx

from components.config import OLLAMA_HOST, OLLAMA_PORT, OLLAMA_MODEL


# ── Client ────────────────────────────────────────────────────────────────────

class OllamaClient:
    """
    Async wrapper around the Ollama /api/generate endpoint.

    One instance is created at middleware startup and reused.
    Uses httpx.AsyncClient with a long timeout — local inference
    on a 12B model can take 10-30 seconds for complex prompts.
    """

    def __init__(
        self,
        host: str = OLLAMA_HOST,
        port: int = OLLAMA_PORT,
        model: str = OLLAMA_MODEL,
        timeout: float = 120.0,
    ):
        self.model = model
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        # Runtime: httpx.AsyncClient; tests may assign AsyncMock.
        self._client: Any = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return a shared AsyncClient, creating it if needed."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client. Call on middleware shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Core generation ───────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Send a prompt to Ollama and return the response text.

        Args:
            prompt: The user prompt.
            system: Optional system prompt. Injected before the user prompt.
            model:  Override the default model for this call.

        Returns:
            The model's response as a plain string.

        Raises:
            OllamaConnectionError: If Ollama is unreachable.
            OllamaGenerationError: If the request succeeds but generation fails.
        """
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        try:
            response = await self._get_client().post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
        except httpx.ConnectError as e:
            raise OllamaConnectionError(
                f"Could not connect to Ollama at {self.base_url}. "
                f"Is Ollama running? ({e})"
            ) from e
        except httpx.TimeoutException as e:
            raise OllamaConnectionError(
                f"Ollama request timed out after {self.timeout}s. "
                f"Model may still be loading. ({e})"
            ) from e
        except httpx.HTTPStatusError as e:
            raise OllamaGenerationError(
                f"Ollama returned HTTP {e.response.status_code}: {e.response.text}"
            ) from e

        try:
            data = response.json()
            return data["response"]
        except (KeyError, json.JSONDecodeError) as e:
            raise OllamaGenerationError(
                f"Unexpected Ollama response shape: {response.text[:200]}"
            ) from e

    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send a prompt and parse the response as JSON.

        Handles common model failure modes:
        - JSON wrapped in ```json ... ``` markdown fences
        - Leading/trailing whitespace or explanation text
        - Single retry if first parse attempt fails

        Args:
            prompt: The user prompt. Should instruct the model to return JSON only.
            system: Optional system prompt.
            model:  Override the default model.

        Returns:
            Parsed dict.

        Raises:
            OllamaConnectionError: If Ollama is unreachable.
            OllamaGenerationError: If generation fails.
            OllamaJSONError: If the response cannot be parsed as JSON after cleanup.
        """
        raw = await self.generate(prompt=prompt, system=system, model=model)
        
        try:
            return _parse_json_response(raw)
        except OllamaJSONError:
            pass

        # Single retry with an explicit nudge
        retry_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT: Your previous response could not be parsed as JSON. "
            f"Return ONLY a valid JSON object with no other text, "
            f"no markdown fences, no explanation."
        )
        raw = await self.generate(prompt=retry_prompt, system=system, model=model)

        try:
            return _parse_json_response(raw)
        except OllamaJSONError as e:
            raise OllamaJSONError(
                f"Failed to parse JSON after retry. Raw response: {raw[:300]}"
            ) from e

    # ── Diagnostics ───────────────────────────────────────────────────────────

    async def heartbeat(self) -> bool:
        """Return True if Ollama is reachable and the model is available."""
        try:
            response = await self._get_client().get(
                f"{self.base_url}/api/tags",
            )
            response.raise_for_status()
            tags = response.json()
            models = [m["name"] for m in tags.get("models", [])]
            return any(self.model in m for m in models)
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """Return list of available model names."""
        try:
            response = await self._get_client().get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []


# ── JSON parsing helper ───────────────────────────────────────────────────────

def _parse_json_response(raw: str) -> dict[str, Any]:
    """
    Attempt to extract and parse JSON from a model response.

    Handles:
    - Clean JSON: {"key": "value"}
    - Fenced JSON: ```json\n{"key": "value"}\n```
    - Fenced without language tag: ```\n{"key": "value"}\n```
    - Leading/trailing whitespace or newlines

    Raises:
        OllamaJSONError: If no valid JSON object can be extracted.
    """
    text = raw.strip()

    # Strip markdown fences if present
    fenced = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object within surrounding text
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise OllamaJSONError(f"No valid JSON found in response: {raw[:200]}")


# ── Exceptions ────────────────────────────────────────────────────────────────

class OllamaConnectionError(Exception):
    """Ollama is unreachable or timed out."""


class OllamaGenerationError(Exception):
    """Ollama responded but generation failed."""


class OllamaJSONError(Exception):
    """Ollama responded but JSON parsing failed after cleanup and retry."""