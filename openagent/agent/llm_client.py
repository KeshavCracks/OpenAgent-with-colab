"""Thin OpenAI-compatible chat-completions client for the llama.cpp server.

No model inference happens locally -- this just speaks HTTP(S) to whatever
endpoint the active provider/session exposes (loopback, an in-runtime exec
bridge relay, or an explicit local endpoint in `remote-workspace` mode).
"""
from __future__ import annotations

import dataclasses
from typing import Any, Callable, Optional

Transport = Callable[[str, dict, dict], dict]  # (url, headers, json_body) -> response json


@dataclasses.dataclass
class ChatResponse:
    raw: dict

    @property
    def message(self) -> dict:
        return self.raw["choices"][0]["message"]

    @property
    def content(self) -> str | None:
        return self.message.get("content")

    @property
    def tool_calls(self) -> list[dict]:
        return self.message.get("tool_calls") or []

    @property
    def finish_reason(self) -> str:
        return self.raw["choices"][0].get("finish_reason", "")

    @property
    def usage(self) -> dict:
        return self.raw.get("usage", {})


class LlamaCppClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        token: str | None = None,
        transport: Optional[Transport] = None,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._transport = transport or self._default_transport

    def _default_transport(self, url: str, headers: dict, json_body: dict) -> dict:
        import requests

        r = requests.post(url, headers=headers, json=json_body, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str = "default",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: dict | None = None,
    ) -> ChatResponse:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
        if extra:
            body.update(extra)
        raw = self._transport(f"{self.base_url}/v1/chat/completions", headers, body)
        return ChatResponse(raw=raw)
