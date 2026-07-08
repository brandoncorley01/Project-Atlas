"""Thin OpenAI wrapper with graceful fallback when no API key is configured."""

from __future__ import annotations

import json
import logging
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


llm_service = LlmService()
