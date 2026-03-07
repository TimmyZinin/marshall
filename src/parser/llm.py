"""LLM client: MiniMax M2.5 (primary) + Groq Llama 3.3 (fallback)."""
import json
import logging
import time
import httpx

logger = logging.getLogger("marshall.parser.llm")


class LLMClient:
    """Calls MiniMax or Groq to parse logistics messages."""

    def __init__(self, minimax_api_key: str | None = None, groq_api_key: str | None = None):
        self._minimax_key = minimax_api_key
        self._groq_key = groq_api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def parse(self, system_prompt: str, user_prompt: str) -> tuple[dict, str, int, int]:
        """Parse message via LLM. Returns (result_dict, model_name, tokens_used, duration_ms)."""
        if self._minimax_key:
            try:
                return await self._call_minimax(system_prompt, user_prompt)
            except Exception as e:
                logger.warning("MiniMax failed, falling back to Groq: %s", e)

        if self._groq_key:
            return await self._call_groq(system_prompt, user_prompt)

        raise RuntimeError("No LLM API keys configured")

    async def _call_minimax(self, system: str, user: str) -> tuple[dict, str, int, int]:
        start = time.monotonic()
        resp = await self._client.post(
            "https://api.minimax.chat/v1/text/chatcompletion_v2",
            headers={"Authorization": f"Bearer {self._minimax_key}", "Content-Type": "application/json"},
            json={
                "model": "MiniMax-Text-01",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        duration_ms = int((time.monotonic() - start) * 1000)

        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        parsed = _extract_json(content)
        return parsed, "minimax", tokens, duration_ms

    async def _call_groq(self, system: str, user: str) -> tuple[dict, str, int, int]:
        start = time.monotonic()
        resp = await self._client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._groq_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        duration_ms = int((time.monotonic() - start) * 1000)

        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        parsed = _extract_json(content)
        return parsed, "groq", tokens, duration_ms

    async def close(self):
        await self._client.aclose()


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)
