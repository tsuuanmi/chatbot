# `src/llm/client.py`

## Purpose

Provides asynchronous completion, token streaming, multimodal figure description, health checking, and process-local lifecycle management for an OpenAI-compatible llama.cpp server.

## Responsibilities

- Resolve model, endpoint, authentication, generation parameters, and output limits from settings with constructor overrides for endpoint and model.
- Supply the Vietnamese forensic-genetics system prompt used by workflow context aggregation.
- Verify the llama.cpp health endpoint and confirm the configured model appears in the OpenAI model list.
- Execute non-streaming chat completions and return text content.
- Send configured figure assets as base64 data URLs for deterministic-temperature descriptions.
- Stream text while retaining only bracketed citations allowed by the caller.
- Lazily create, reuse, close, and clear one module-level client instance.

## Non-responsibilities

No prompt-history construction, evidence retrieval, citation semantic validation, workflow routing, retry policy, or persistence. The client does not start or manage the llama.cpp server.

## Key types and functions

- `SYSTEM_PROMPT`: Vietnamese role, scope, evidence, anti-fabrication, and prompt-injection guidance.
- `LLMClient(base_url=None, model=None)`: configures `AsyncOpenAI`, a derived `/health` URL, and a 600-second completion timeout.
- `healthcheck() -> None`: bounds both health/model probes to 10 seconds and validates
  the configured model basename.
- `chat(messages, max_tokens=None, temperature=None) -> str`: performs one non-streaming completion using configured sampling controls.
- `describe_figure(asset, prompt) -> str`: submits a text-plus-image user message with the figure output limit and zero temperature.
- `stream_chat(..., allowed_citations=None) -> AsyncGenerator[str, None]`: streams content and filters complete bracketed tokens against an optional allowlist.
- `close() -> None`: closes the underlying OpenAI client.
- `get_llm_client() -> LLMClient`: returns the lazy module singleton.
- `close_llm_client() -> None`: closes and clears that singleton when present.

## Invariants and errors

- Removing a trailing `/v1` from the configured API base and appending `/health` determines the health URL.
- Model health matching compares the configured name with the final slash-delimited component of each returned model ID.
- A successful health endpoint with no matching model raises `RuntimeError`; HTTP, timeout, authentication, and OpenAI SDK errors propagate.
- `max_tokens=0` falls back to the configured limit because completion methods use `max_tokens or configured_limit`; explicit zero temperature is preserved.
- Empty or null completion content becomes an empty string.
- Streaming ignores empty deltas. With an allowlist, complete `[citation]` text is emitted only when its inner text is allowed; ordinary text is preserved.
- A trailing incomplete bracketed fragment is withheld when an allowlist is active, while it is emitted when citation filtering is disabled.
- `_message_params` is a typing cast only and performs no runtime message validation.
- The lazy singleton is process-local and has no locking around first initialization or close.

## Dependencies

- `openai.AsyncOpenAI` and OpenAI chat message types for compatible model APIs.
- `httpx` for the independent health endpoint request.
- `src.config.settings.get_settings` for endpoint, credentials, model, sampling, and token settings.
- `src.tools.figure_tool.FigureAsset` for multimodal data.
- Loguru for initialization logging.

## Tests

`tests/test_readiness.py::test_application_warmup_functionally_checks_and_warms_dependencies` verifies readiness orchestration calls `healthcheck`. `tests/test_answer.py` verifies workflow integration with `chat` and `stream_chat`, including passage of the allowed citation set. There are no direct unit tests for health model matching, stream citation parsing, singleton lifecycle, or figure-message construction.

## Status

Implemented.
