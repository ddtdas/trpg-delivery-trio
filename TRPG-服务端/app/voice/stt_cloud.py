"""TRPG cloud STT adapter (MIT).

OpenAI-compatible audio/transcriptions with explicit mock fallback.
Every result carries ``degraded`` + ``reason`` so callers (and tests)
can always tell live from mock. Secrets from env only.

Python 3.12 compatible. No network at import time.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

__all__ = ["STTResult", "transcribe", "STTError", "MOCK_REASON_NO_KEY"]


class STTError(RuntimeError):
    """STT backend failure (raised only when no fallback is allowed)."""


MOCK_REASON_NO_KEY = "mock: STT_API_KEY unset (no real audio call made)"


@dataclass(frozen=True)
class STTResult:
    text: str
    degraded: bool
    reason: str
    latency_ms: int = 0


def _mock_text(audio_ref: str) -> str:
    return f"[mock 转写] {audio_ref or 'audio'}：雾气在门后退去，露出一枚银钥匙。"


def transcribe(
    audio: bytes | Mapping[str, Any] | str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "whisper-1",
    allow_mock: bool = True,
    http_post: Callable[..., Any] | None = None,
) -> STTResult:
    """Transcribe audio -> STTResult.

    - ``audio``: raw bytes, {"chunks": n} mapping, or a string ref.
    - Without ``api_key`` (env ``STT_API_KEY``) and ``allow_mock``:
      explicit mock result with reason (never raises for missing key).
    - With a key: POST ``{base}/audio/transcriptions`` (httpx or the
      injected ``http_post`` seam); failures raise STTError when
      allow_mock is False, else degrade to mock with the error reason.
    """
    key = api_key if api_key is not None else os.environ.get("STT_API_KEY", "")
    ref = audio if isinstance(audio, str) else (
        f"{len(audio)}B" if isinstance(audio, bytes)
        else f"{audio.get('chunks', '?')}chunks"
    )
    if not key:
        if not allow_mock:
            raise STTError("STT_API_KEY unset and mock not allowed")
        return STTResult(text=_mock_text(str(ref)), degraded=True,
                         reason=MOCK_REASON_NO_KEY, latency_ms=1)
    t0 = time.monotonic()
    try:
        if http_post is not None:
            text = str(http_post(audio, model))
        else:
            import httpx

            url = (base_url or os.environ.get(
                "STT_BASE_URL", "https://api.openai.com/v1")) + "/audio/transcriptions"
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": ("audio.webm", audio if isinstance(audio, bytes) else b"")},
                    data={"model": model},
                )
                resp.raise_for_status()
                text = str(resp.json().get("text", ""))
        if not text.strip():
            raise STTError("empty transcription")
        return STTResult(text=text.strip(), degraded=False, reason="live",
                         latency_ms=int((time.monotonic() - t0) * 1000))
    except STTError:
        raise
    except Exception as exc:  # noqa: BLE001 — degrade with reason
        if not allow_mock:
            raise STTError(f"STT backend failed: {exc}") from exc
        return STTResult(text=_mock_text(str(ref)), degraded=True,
                         reason=f"mock: backend failed ({exc})", latency_ms=1)
