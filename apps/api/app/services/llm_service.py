"""Thin OpenAI wrapper with graceful fallback when no API key is configured."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_JSON_SUFFIX = (
    "Respond with valid JSON only — no markdown fences, no commentary outside the JSON object."
)


class LlmService:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def is_configured(self) -> bool:
        return bool((settings.openai_api_key or "").strip())

    @property
    def model(self) -> str:
        return (getattr(settings, "openai_model", None) or "gpt-4o-mini").strip()

    def _get_client(self) -> AsyncOpenAI | None:
        if not self.is_configured():
            return None
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def probe_connection(self) -> tuple[bool, str | None]:
        """Lightweight connectivity check for provider status."""
        if not self.is_configured():
            return False, "OPENAI_API_KEY not set"
        client = self._get_client()
        if client is None:
            return False, "OPENAI_API_KEY not set"
        try:
            await client.models.list()
            return True, None
        except Exception as exc:
            msg = str(exc).strip() or exc.__class__.__name__
            logger.warning("OpenAI probe failed: %s", msg)
            return False, msg[:200]

    async def complete_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 600,
        temperature: float = 0.4,
    ) -> str | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            return content.strip() if content else None
        except Exception as exc:
            logger.warning("OpenAI complete_text failed: %s", exc)
            return None

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 900,
        temperature: float = 0.35,
    ) -> dict[str, Any] | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"{system}\n\n{_SYSTEM_JSON_SUFFIX}"},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                return None
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except Exception as exc:
            logger.warning("OpenAI complete_json failed: %s", exc)
            return None

    async def complete_json_with_web_search(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1600,
        web_timeout_s: float = 35.0,
    ) -> dict[str, Any] | None:
        """Use OpenAI Responses API + hosted web_search for live internet grounding.

        Falls back to chat JSON (no browse) if Responses/web_search is unavailable
        or exceeds web_timeout_s — keeps Atlas Insight inside the BFF budget.
        """
        client = self._get_client()
        if client is None:
            return None

        prompt = (
            f"{system}\n\n{_SYSTEM_JSON_SUFFIX}\n\n"
            "You MUST browse the public web for today's sports betting consensus from "
            "analysts, touts, and popular sports bettors before answering.\n\n"
            f"{user}"
        )
        try:

            async def _web_call() -> dict[str, Any]:
                response = await client.responses.create(
                    model=self.model,
                    input=prompt,
                    tools=[{"type": "web_search"}],
                    tool_choice="required",
                    max_output_tokens=max_tokens,
                )
                content = getattr(response, "output_text", None)
                if not content:
                    chunks: list[str] = []
                    for item in getattr(response, "output", None) or []:
                        for part in getattr(item, "content", None) or []:
                            text = getattr(part, "text", None)
                            if text:
                                chunks.append(str(text))
                    content = "\n".join(chunks).strip() or None
                if not content:
                    raise RuntimeError("empty web_search response")
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                    cleaned = re.sub(r"\s*```$", "", cleaned)
                parsed = json.loads(cleaned)
                if not isinstance(parsed, dict):
                    raise RuntimeError("web_search returned non-object JSON")
                parsed["_web_search"] = True
                return parsed

            return await asyncio.wait_for(_web_call(), timeout=max(8.0, web_timeout_s))
        except Exception as exc:
            logger.warning("OpenAI web_search path failed (%s); falling back to chat JSON", exc)

        fallback = await self.complete_json(system=system, user=user, max_tokens=max_tokens, temperature=0.25)
        if fallback is not None:
            fallback["_web_search"] = False
        return fallback


llm_service = LlmService()
