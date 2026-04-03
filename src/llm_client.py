"""LLM client wrapper for OpenAI calls."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from openai import OpenAI

from src.config import LLMConfig


class LLMClient:
    """Wrapper around OpenAI API for structured LLM calls."""

    def __init__(self, config: LLMConfig | None = None):
        self._config = config or LLMConfig()
        self._client = OpenAI(api_key=self._config.api_key)

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        history: List[Dict[str, str]] | None = None,
        temperature: float | None = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> str:
        """Send a chat completion request and return the content."""
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        kwargs: Dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._config.temperature,
            "max_tokens": self._config.max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        history: List[Dict[str, str]] | None = None,
        temperature: float | None = None,
    ) -> Dict[str, Any]:
        """Send a chat request and parse JSON response."""
        raw = self.chat(
            system_prompt=system_prompt,
            user_message=user_message,
            history=history,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return json.loads(raw)
