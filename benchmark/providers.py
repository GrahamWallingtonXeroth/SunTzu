"""
LLM provider abstraction layer.

Wraps different LLM APIs (Anthropic, OpenAI) behind a common interface
so the benchmark is model-agnostic. Each provider tracks token usage
and latency for cost reporting.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    """Response from an LLM API call."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a completion request.

        Args:
            system: System prompt
            messages: List of {role, content} message dicts
            temperature: Sampling temperature (0.0 for deterministic)
            max_tokens: Maximum tokens to generate
        """
        ...

    @abstractmethod
    def complete_with_tools(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a completion request with tool/function calling.

        Returns LLMResponse with tool_calls populated.
        """
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Exact model identifier for reproducibility."""
        ...


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", api_key: str | None = None):
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as err:
                raise ImportError("anthropic package required. Install with: pip install anthropic") from err
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._get_client()
        start = time.monotonic()
        response = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        elapsed = (time.monotonic() - start) * 1000

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=elapsed,
        )

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._get_client()
        start = time.monotonic()
        response = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
            tools=tools,
        )
        elapsed = (time.monotonic() - start) * 1000

        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "name": block.name,
                        "input": block.input,
                        "id": block.id,
                    }
                )

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=elapsed,
            tool_calls=tool_calls,
        )


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self, model: str = "gpt-4o", api_key: str | None = None):
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError as err:
                raise ImportError("openai package required. Install with: pip install openai") from err
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    @property
    def model_id(self) -> str:
        return self._model

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._get_client()
        full_messages = [{"role": "system", "content": system}, *messages]
        start = time.monotonic()
        response = client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = (time.monotonic() - start) * 1000

        content = response.choices[0].message.content or ""
        usage = response.usage

        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=elapsed,
        )

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._get_client()
        full_messages = [{"role": "system", "content": system}, *messages]

        # Convert Anthropic-style tools to OpenAI format
        openai_tools = []
        for tool in tools:
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema", {}),
                    },
                }
            )

        start = time.monotonic()
        response = client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=openai_tools if openai_tools else None,
        )
        elapsed = (time.monotonic() - start) * 1000

        content = response.choices[0].message.content or ""
        tool_calls = []
        if response.choices[0].message.tool_calls:
            import json

            for tc in response.choices[0].message.tool_calls:
                tool_calls.append(
                    {
                        "name": tc.function.name,
                        "input": json.loads(tc.function.arguments),
                        "id": tc.id,
                    }
                )

        usage = response.usage
        return LLMResponse(
            content=content,
            model=response.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=elapsed,
            tool_calls=tool_calls,
        )


class MockProvider(LLMProvider):
    """Mock provider for testing without API calls.

    Returns configurable responses for unit testing the harness.
    """

    def __init__(self, responses: list[str] | None = None, tool_responses: list[list[dict]] | None = None):
        self._responses = list(responses) if responses else []
        self._tool_responses = list(tool_responses) if tool_responses else []
        self._call_count = 0
        self.call_log: list[dict] = []

    @property
    def model_id(self) -> str:
        return "mock-model"

    def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.call_log.append(
            {
                "type": "complete",
                "system": system,
                "messages": messages,
            }
        )
        content = self._responses.pop(0) if self._responses else "Mock response"
        self._call_count += 1
        return LLMResponse(
            content=content,
            model="mock-model",
            input_tokens=100,
            output_tokens=50,
            latency_ms=10.0,
        )

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.call_log.append(
            {
                "type": "complete_with_tools",
                "system": system,
                "messages": messages,
                "tools": [t["name"] for t in tools],
            }
        )
        content = self._responses.pop(0) if self._responses else ""
        tool_calls = self._tool_responses.pop(0) if self._tool_responses else []
        self._call_count += 1
        return LLMResponse(
            content=content,
            model="mock-model",
            input_tokens=100,
            output_tokens=50,
            latency_ms=10.0,
            tool_calls=tool_calls,
        )
