from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.request


@dataclass(frozen=True)
class ProviderResponse:
    data: dict
    tokens: int | None = None


class Provider:
    name = "disabled"

    def complete(self, prompt: str, model: str) -> ProviderResponse:
        raise NotImplementedError


class FakeProvider(Provider):
    name = "fake"

    def complete(self, prompt: str, model: str) -> ProviderResponse:
        if "suggest" in prompt.lower():
            return ProviderResponse({"summary": "AI-generated suggestion requires review.", "patches": []}, 0)
        if "summary" in prompt.lower():
            return ProviderResponse({"summary": "AI-generated summary based only on the supplied artifacts."}, 0)
        return ProviderResponse({"explanation": "AI-generated explanation based only on the supplied artifacts."}, 0)


class HTTPProvider(Provider):
    def __init__(self, name: str, endpoint: str, api_key: str | None):
        self.name, self.endpoint, self.api_key = name, endpoint, api_key

    def complete(self, prompt: str, model: str) -> ProviderResponse:
        if not self.api_key and self.name != "ollama":
            raise RuntimeError("LLM provider is disabled because no API key is configured.")
        if self.name == "anthropic":
            payload = {"model": model, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]}
            headers = {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}
        else:
            payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        request = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read())
        text = body.get("content", [{}])[0].get("text") if self.name == "anthropic" else body.get("choices", [{}])[0].get("message", {}).get("content")
        return ProviderResponse(json.loads(text or "{}"), body.get("usage", {}).get("total_tokens"))


def provider_from_environment() -> Provider:
    name = os.getenv("MIGRATIONGUARD_LLM_PROVIDER", "").lower()
    key = os.getenv("MIGRATIONGUARD_LLM_API_KEY")
    model = os.getenv("MIGRATIONGUARD_LLM_MODEL", "default")
    if name == "fake":
        return FakeProvider()
    if name == "anthropic":
        return HTTPProvider(name, os.getenv("MIGRATIONGUARD_ANTHROPIC_ENDPOINT", "https://api.anthropic.com/v1/messages"), key)
    if name == "openai":
        return HTTPProvider(name, os.getenv("MIGRATIONGUARD_OPENAI_ENDPOINT", "https://api.openai.com/v1/chat/completions"), key)
    if name == "ollama":
        return HTTPProvider(name, os.getenv("MIGRATIONGUARD_OLLAMA_ENDPOINT", "http://localhost:11434/api/chat"), key)
    return Provider()
