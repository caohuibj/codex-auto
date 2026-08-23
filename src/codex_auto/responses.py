"""OpenAI Responses API adapter with strict JSON-schema outputs."""

from __future__ import annotations

import json
import os
from typing import Any, TypeVar

from pydantic import BaseModel

from codex_auto.config import ModelRoute, ProviderConfig
from codex_auto.models import UsageRecord

OutputT = TypeVar("OutputT", bound=BaseModel)


class ResponsesClientError(RuntimeError):
    pass


def _read_int(value: Any, attribute: str, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, dict):
        raw = value.get(attribute, default)
    else:
        raw = getattr(value, attribute, default)
    return int(raw or 0)


class OpenAIResponsesClient:
    """Thin SDK adapter; the orchestration core depends only on the ResponsesClient protocol."""

    def __init__(self, provider_name: str, config: ProviderConfig) -> None:
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            raise ResponsesClientError(
                f"required API key environment variable {config.api_key_env!r} is not set"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - packaging guards this in production
            raise ResponsesClientError("install the 'openai' package to use this adapter") from exc

        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": config.timeout_seconds}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = OpenAI(**kwargs)
        self.provider_name = provider_name
        self.store = config.store

    def complete(
        self,
        *,
        phase: str,
        route: ModelRoute,
        instructions: str,
        input_data: dict[str, Any],
        output_type: type[OutputT],
        metadata: dict[str, str],
    ) -> tuple[OutputT, UsageRecord]:
        schema_name = output_type.__name__.lower()
        request: dict[str, Any] = {
            "model": route.model,
            "instructions": instructions,
            "input": json.dumps(input_data, ensure_ascii=False),
            "max_output_tokens": route.max_output_tokens,
            "metadata": metadata,
            "parallel_tool_calls": False,
            "store": self.store,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": output_type.model_json_schema(),
                }
            },
        }
        if route.reasoning_effort is not None:
            request["reasoning"] = {"effort": route.reasoning_effort}
        if route.temperature is not None:
            request["temperature"] = route.temperature

        response = self._client.responses.create(**request)
        status = getattr(response, "status", "completed")
        if status != "completed":
            raise ResponsesClientError(
                f"Responses API did not complete (response={getattr(response, 'id', '?')}, "
                f"status={status})"
            )
        output_text = getattr(response, "output_text", "")
        if not output_text:
            raise ResponsesClientError(
                f"Responses API returned no output_text (response={getattr(response, 'id', '?')})"
            )
        try:
            output = output_type.model_validate_json(output_text)
        except ValueError as exc:
            raise ResponsesClientError("Responses API returned invalid structured output") from exc

        usage = getattr(response, "usage", None)
        input_details = (
            usage.get("input_tokens_details")
            if isinstance(usage, dict)
            else getattr(usage, "input_tokens_details", None)
        )
        output_details = (
            usage.get("output_tokens_details")
            if isinstance(usage, dict)
            else getattr(usage, "output_tokens_details", None)
        )
        usage_record = UsageRecord(
            phase=phase,
            provider=self.provider_name,
            model=route.model,
            response_id=str(getattr(response, "id", "unknown")),
            input_tokens=_read_int(usage, "input_tokens"),
            cached_input_tokens=_read_int(input_details, "cached_tokens"),
            output_tokens=_read_int(usage, "output_tokens"),
            reasoning_tokens=_read_int(output_details, "reasoning_tokens"),
            total_tokens=_read_int(usage, "total_tokens"),
        )
        return output, usage_record
