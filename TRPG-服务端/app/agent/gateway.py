"""TRPG LLM gateway abstraction (MIT).

OpenAI-compatible multi-endpoint routing with env-only secrets.
Python 3.12 compatible. No network calls at import time.

Iron rule: the gateway only *produces text*; it never writes state.
Callers (AgentSlot/CommandBus) turn text into proposal events that go
through approval. Secrets are read from environment variables at call
time and never logged.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

log = logging.getLogger("trpg.gateway")

# T31: reasoning models (e.g. deepseek-v4-flash) emit empty text at tiny
# budgets; 512 is the configured floor (overridable per provider/model).
DEFAULT_MAX_TOKENS = 512
DEFAULT_EMPTY_RETRY = 1
DEFAULT_MIN_TEXT_CHARS = 1


class GatewayError(RuntimeError):
    """Raised when an endpoint fails (network, auth, bad response)."""


@dataclass(frozen=True)
class GatewayResult:
    text: str
    mode: str  # "live" | "mock-ok" | "degraded-template"
    model: str = ""
    latency_ms: int = 0
    # T31 observability: retry/fallback trail (perf + log markers).
    attempts: int = 1
    empty_retries: int = 0
    perf: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Endpoint:
    """One OpenAI-compatible endpoint.

    T33 semantic ruling (option A): config load expands ${ENV} to the
    LITERAL secret value, and Endpoint holds the literal key in
    ``api_key_value`` — it NEVER re-looks-up env. Use
    ``Endpoint.from_env_name()`` only for code-built chains (tests /
    DEFAULT_CHAIN) where the env indirection is explicit. Secrets never
    enter logs/exceptions (see ``redact_key``).
    """

    name: str
    model: str
    base_url: str
    api_key_env: str = ""
    api_key_value: str = ""
    max_tokens: int = DEFAULT_MAX_TOKENS
    empty_retry: int = DEFAULT_EMPTY_RETRY
    min_text_chars: int = DEFAULT_MIN_TEXT_CHARS

    @classmethod
    def from_env_name(cls, name: str, model: str, base_url: str,
                      api_key_env: str, **kw: Any) -> Endpoint:
        return cls(name=name, model=model, base_url=base_url,
                   api_key_env=api_key_env, api_key_value="", **kw)

    def api_key(self) -> str:
        # Literal value wins (config path); else env lookup (code path).
        if self.api_key_value:
            return self.api_key_value
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return ""


def redact_key(value: str) -> str:
    """T33: secret-safe marker — never more than a presence flag."""
    return "<set>" if value else "<empty>"


def _effective_max_tokens(ep: Endpoint, override: int | None = None) -> int:
    """Explicit call arg wins; else endpoint value; floor at 512."""
    if override is not None:
        return max(int(override), DEFAULT_MAX_TOKENS)
    return max(int(ep.max_tokens or 0), DEFAULT_MAX_TOKENS)


def endpoints_from_config(cfg: Mapping[str, Any]) -> list[Endpoint]:
    """Build endpoints from llm_providers.yaml mapping (T31 configurable,
    T33 semantic A).

    The mapping is expected POST-expansion (i.e. via load_llm_config):
    ``api_key``/``base_url`` arrive as LITERAL values and are stored
    verbatim — no second env lookup. A leftover unexpanded ``${VAR}``
    means the file bypassed the loader and is rejected loudly instead of
    being misread as an env name.
    Shape: {defaults: {max_tokens, empty_retry, min_text_chars},
            primary/fallback/tertiary/local: {name, model, base_url, api_key,
            max_tokens?}}. Missing budgets default to 512.
    """
    defaults = cfg.get("defaults", {}) if isinstance(cfg, Mapping) else {}
    d_max = int(defaults.get("max_tokens", DEFAULT_MAX_TOKENS) or 0) or DEFAULT_MAX_TOKENS
    d_max = max(d_max, DEFAULT_MAX_TOKENS)
    d_retry = int(defaults.get("empty_retry", DEFAULT_EMPTY_RETRY) or 0)
    d_min = int(defaults.get("min_text_chars", DEFAULT_MIN_TEXT_CHARS) or 0) or DEFAULT_MIN_TEXT_CHARS
    out: list[Endpoint] = []
    # SY-1: additive — optional "tertiary" slot between fallback and local
    # (missing section behaves exactly as before).
    for key in ("primary", "fallback", "tertiary", "local"):
        section = cfg.get(key, {}) if isinstance(cfg, Mapping) else {}
        if not isinstance(section, Mapping) or not section:
            continue
        api_key_raw = str(section.get("api_key", ""))
        base_raw = str(section.get("base_url", ""))
        for label, val in (("api_key", api_key_raw), ("base_url", base_raw)):
            if val.startswith("${") and val.endswith("}"):
                raise GatewayError(
                    f"llm_providers {key}.{label} is unexpanded; "
                    f"load via load_llm_config (got {redact_key(val)})")
        out.append(Endpoint(
            name=str(section.get("name", key)),
            model=str(section.get("model", "")),
            base_url=base_raw,
            api_key_env="",
            api_key_value=api_key_raw,
            max_tokens=max(int(section.get("max_tokens", d_max) or 0), DEFAULT_MAX_TOKENS),
            empty_retry=int(section.get("empty_retry", d_retry) or 0),
            min_text_chars=int(section.get("min_text_chars", d_min) or 0) or d_min,
        ))
    return out


PRIMARY_ENDPOINT = Endpoint.from_env_name(
    "newapi", "deepseek-v4-flash",
    "https://newapi.example.com/v1", "NEWAPI_API_KEY",
)
FALLBACK_ENDPOINT = Endpoint.from_env_name(
    "gpt5", "gpt-5.6-luna",
    "https://api.openai.com/v1", "GPT5_API_KEY",
)
LOCAL_ENDPOINT = Endpoint.from_env_name(
    "lm_studio", "local-model",
    "http://127.0.0.1:1234/v1", "LMSTUDIO_API_KEY",
)
DEFAULT_CHAIN: tuple[Endpoint, ...] = (PRIMARY_ENDPOINT, FALLBACK_ENDPOINT, LOCAL_ENDPOINT)


def _to_openai_messages(messages: Sequence[Mapping[str, Any]]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role = str(m.get("role", "user"))
        if role not in ("system", "user", "assistant"):
            raise GatewayError(f"bad message role: {role!r}")
        out.append({"role": role, "content": str(m.get("content", ""))})
    if not out:
        raise GatewayError("empty message list")
    return out


class LLMGateway:
    """Abstract gateway: sync text completion."""

    name: str = "base"

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
    ) -> GatewayResult:
        raise NotImplementedError


def _is_empty_output(text: str, min_chars: int = DEFAULT_MIN_TEXT_CHARS) -> bool:
    """T31 guard: empty or whitespace-only (or abnormally short) output."""
    return len(text.strip()) < max(int(min_chars), 1)


class OpenAICompatGateway(LLMGateway):
    """Single OpenAI-compatible endpoint (lazy SDK import, sync)."""

    def __init__(self, endpoint: Endpoint, timeout_s: float = 30.0) -> None:
        if not endpoint.api_key():
            # T33: redacted — never print the key or its env name value.
            raise GatewayError(
                f"missing api key for endpoint {endpoint.name} "
                f"({redact_key(endpoint.api_key())})")
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.name = f"openai-compat:{endpoint.name}"

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> GatewayResult:
        payload = _to_openai_messages(messages)
        budget = _effective_max_tokens(self.endpoint, max_tokens)
        try:
            from openai import OpenAI  # lazy: no import-time side effects
        except ImportError as exc:
            raise GatewayError("openai SDK not installed") from exc
        attempts = 0
        empty_retries = 0
        last_latency = 0
        while True:
            attempts += 1
            t0 = time.monotonic()
            try:
                client = OpenAI(
                    api_key=self.endpoint.api_key(),
                    base_url=self.endpoint.base_url,
                    timeout=self.timeout_s,
                )
                resp = client.chat.completions.create(
                    model=self.endpoint.model,
                    messages=payload,  # type: ignore[arg-type]
                    max_tokens=budget,
                    temperature=temperature,
                )
                text = (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                raise GatewayError(
                    f"endpoint {self.endpoint.name} failed: {exc}") from exc
            last_latency = int((time.monotonic() - t0) * 1000)
            if not _is_empty_output(text, self.endpoint.min_text_chars):
                return GatewayResult(
                    text=text, mode="live", model=self.endpoint.model,
                    latency_ms=last_latency, attempts=attempts,
                    empty_retries=empty_retries,
                    perf={"llm_first_token_ms": last_latency,
                          "empty_retries": empty_retries,
                          "max_tokens": budget,
                          "endpoint": self.endpoint.name},
                )
            # T31: empty output -> one configured retry, then hard fail
            # (router moves to next endpoint; slot falls back to template).
            log.warning("gateway empty output endpoint=%s model=%s "
                        "attempt=%d max_tokens=%d; retrying",
                        self.endpoint.name, self.endpoint.model,
                        attempts, budget)
            if empty_retries >= max(int(self.endpoint.empty_retry), 0):
                raise GatewayError(
                    f"endpoint {self.endpoint.name} returned empty text "
                    f"after {attempts} attempt(s)")
            empty_retries += 1


class GatewayRouter(LLMGateway):
    """Try endpoints in order; first success wins. All failures -> GatewayError."""

    name = "router"

    def __init__(
        self,
        chain: Sequence[Endpoint] = DEFAULT_CHAIN,
        timeout_s: float = 30.0,
        client_factory: Any | None = None,
    ) -> None:
        if not chain:
            raise ValueError("endpoint chain must be non-empty")
        self.chain = tuple(chain)
        self.timeout_s = timeout_s
        self._factory = client_factory  # test seam: (endpoint) -> LLMGateway
        self.last_errors: list[str] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> GatewayResult:
        _to_openai_messages(messages)  # validate once, fail fast
        errors: list[str] = []
        for ep in self.chain:
            try:
                gw: LLMGateway = (
                    self._factory(ep) if self._factory is not None
                    else OpenAICompatGateway(ep, timeout_s=self.timeout_s)
                )
                # None = let each endpoint apply its own configured budget
                # (floor 512); explicit value still floored at 512.
                return gw.complete(messages, max_tokens=max_tokens,
                                   temperature=temperature)
            except GatewayError as exc:
                errors.append(f"{ep.name}: {exc}")
        self.last_errors = errors
        raise GatewayError("all endpoints failed: " + " | ".join(errors))


class FakeGateway(LLMGateway):
    """Test-only gateway with three states. Never touches the network.

    - "ok": returns the canned text verbatim.
    - "degraded": returns the degrade template (clearly marked, usable).
    - "fault": raises GatewayError like a dead endpoint.
    """

    VALID_MODES = ("ok", "degraded", "fault")

    def __init__(
        self,
        mode: str = "ok",
        canned_text: str = "雾气在门后缓缓退去，露出一枚带血的银钥匙。",
        template: str = "[降级旁白] 主持人请接管叙事：{hint}",
    ) -> None:
        if mode not in self.VALID_MODES:
            raise ValueError(f"FakeGateway mode must be one of {self.VALID_MODES}")
        self.mode = mode
        self.canned_text = canned_text
        self.template = template
        self.name = f"fake:{mode}"
        self.calls: list[dict] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
    ) -> GatewayResult:
        _to_openai_messages(messages)
        self.calls.append({"n_messages": len(list(messages)),
                           "max_tokens": max_tokens})
        if self.mode == "fault":
            raise GatewayError("fake endpoint fault (simulated outage)")
        if self.mode == "degraded":
            hint = ""
            for m in messages:
                if m.get("role") == "user":
                    hint = str(m.get("content", ""))[:60]
            return GatewayResult(
                text=self.template.format(hint=hint or "继续推进剧情"),
                mode="degraded-template", model="fake-degraded", latency_ms=1,
            )
        return GatewayResult(
            text=self.canned_text, mode="mock-ok", model="fake-ok", latency_ms=1,
        )


def gateway_from_env(
    chain: Sequence[Endpoint] = DEFAULT_CHAIN,
    timeout_s: float = 30.0,
) -> GatewayRouter:
    """Build the production router. Keys stay in env; nothing is logged."""
    return GatewayRouter(chain=chain, timeout_s=timeout_s)


def gateway_from_config_file(base: Any | None = None) -> GatewayRouter:
    """Build the router from configs/llm_providers.yaml (T31).

    Falls back to DEFAULT_CHAIN when the file is missing/empty so unit
    tests and minimal checkouts keep working.
    """
    from pathlib import Path

    from app.config import load_llm_config
    try:
        cfg = load_llm_config(base if isinstance(base, Path) else None)
    except FileNotFoundError:
        return GatewayRouter()
    eps = endpoints_from_config(cfg)
    if not eps:
        return GatewayRouter()
    return GatewayRouter(chain=eps)


def redact(value: str) -> str:
    """Redact a secret for logs: keep nothing but length class."""
    if not value:
        return "<empty>"
    return "<set:%d>" % len(value)