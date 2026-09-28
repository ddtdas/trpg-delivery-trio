"""TRPG cloud TTS output (MIT).

audio/speech with degradation chain: cloud -> silent-marked -> text
fallback. Replay dedup via content-hash window (pure, bounded).
Secrets from env only. Python 3.12 compatible.
"""
from __future__ import annotations

import hashlib
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["TTSResult", "speak", "TTSError", "DedupWindow", "MOCK_REASON_NO_KEY"]

MOCK_REASON_NO_KEY = "mock: TTS_API_KEY unset (text fallback, no audio)"


class TTSError(RuntimeError):
    """TTS backend failure (no-mock path only)."""


@dataclass(frozen=True)
class TTSResult:
    audio: bytes | None  # None on degraded/text paths
    text: str            # always present: spoken (or would-be-spoken) text
    degraded: bool
    reason: str
    tellement_silent: bool = False
    latency_ms: int = 0


class DedupWindow:
    """Bounded recent-hash window: True = already spoken (skip replay)."""

    def __init__(self, capacity: int = 64) -> None:
        if not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be int >= 1")
        self._seen: deque[str] = deque(maxlen=capacity)

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def check_and_add(self, text: str) -> bool:
        """Return True if duplicate (already in window), else record."""
        if not isinstance(text, str):
            raise TypeError("text must be str")
        k = self.key(text)
        if k in self._seen:
            return True
        self._seen.append(k)
        return False


def speak(
    text: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "tts-1",
    voice: str = "alloy",
    allow_mock: bool = True,
    dedup: DedupWindow | None = None,
    http_post: Callable[..., Any] | None = None,
) -> TTSResult:
    """Speak text -> TTSResult (audio bytes or degraded text fallback)."""
    if not isinstance(text, str) or not text.strip():
        raise TTSError("text must be a non-empty string")
    text = text.strip()
    if dedup is not None and dedup.check_and_add(text):
        return TTSResult(audio=None, text=text, degraded=True,
                         reason="dedup: replay suppressed", tellement_silent=True)
    key = api_key if api_key is not None else os.environ.get("TTS_API_KEY", "")
    if not key:
        if not allow_mock:
            raise TTSError("TTS_API_KEY unset and mock not allowed")
        return TTSResult(audio=None, text=text, degraded=True,
                         reason=MOCK_REASON_NO_KEY, tellement_silent=True, latency_ms=1)
    t0 = time.monotonic()
    try:
        if http_post is not None:
            audio = bytes(http_post(text, model, voice))
        else:
            import httpx

            url = (base_url or os.environ.get(
                "TTS_BASE_URL", "https://api.openai.com/v1")) + "/audio/speech"
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "input": text, "voice": voice},
                )
                resp.raise_for_status()
                audio = resp.content
        if not audio:
            raise TTSError("empty audio response")
        return TTSResult(audio=audio, text=text, degraded=False,
                         reason="live", latency_ms=int((time.monotonic() - t0) * 1000))
    except TTSError:
        raise
    except Exception as exc:  # noqa: BLE001 — degrade with reason
        if not allow_mock:
            raise TTSError(f"TTS backend failed: {exc}") from exc
        return TTSResult(audio=None, text=text, degraded=True,
                         reason=f"mock: backend failed ({exc})",
                         tellement_silent=True, latency_ms=1)
