"""TRPG image pipeline — cloud gen -> placeholder -> retry (MIT).

Three-level degradation with background-job semantics (no threads here:
pure state machine over caller-provided attempt functions; the caller
schedules retries and polls via ``job_get_status``-shaped dicts).

Levels:
  1. cloud: caller-supplied ``generate`` callable (OpenAI-compatible
     images API in production) returns {"file_url", ...} -> done.
  2. placeholder: deterministic local SVG placeholder (always works,
     clearly marked engine="placeholder") -> done-degraded.
  3. retry: when cloud raises *transient* errors and attempts remain,
     return queued/retry instead of failing.

``ImagePipeError`` (fatal: bad prompt, auth) fails fast without
placeholder fallback... no — v1 policy: even fatal cloud errors end at
the placeholder so the table is never blocked; the error is recorded
in the job record. Only illegal *inputs* (empty prompt) raise.
"""
from __future__ import annotations

import base64
import hashlib
import time
from typing import Any, Callable, Mapping

__all__ = [
    "ImagePipeError",
    "ImageJob",
    "submit_job",
    "poll_job",
    "placeholder_ref",
    "FORBIDDEN_TOKENS",
]

FORBIDDEN_TOKENS = ("nsfw", "explicit", "gore-detail")


class ImagePipeError(ValueError):
    """Illegal image request (empty prompt, forbidden tokens)."""


def placeholder_ref(prompt: str, card_id: str = "") -> dict:
    """Deterministic placeholder SVG data-URL (engine marked)."""
    seed = hashlib.sha256(f"{card_id}:{prompt}".encode("utf-8")).hexdigest()[:8]
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'>"
        f"<rect width='256' height='256' fill='#1e293b'/>"
        f"<text x='128' y='120' fill='#f59e0b' font-size='18' text-anchor='middle'>TRPG 占位图</text>"
        f"<text x='128' y='150' fill='#94a3b8' font-size='12' text-anchor='middle'>#{seed}</text>"
        "</svg>"
    )
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return {
        "file_url": f"data:image/svg+xml;base64,{b64}",
        "prompt": prompt, "engine": "placeholder", "seed": seed,
    }


def _check_request(card_id: str, prompt: str) -> None:
    if not isinstance(card_id, str) or not card_id.strip():
        raise ImagePipeError("card_id must be a non-empty string")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ImagePipeError("prompt must be a non-empty string")
    lowered = prompt.lower()
    for tok in FORBIDDEN_TOKENS:
        if tok in lowered:
            raise ImagePipeError(f"prompt contains forbidden token: {tok}")


def submit_job(card_id: str, prompt: str, job_id: str | None = None) -> dict:
    """Create a queued job record (pure dict, caller persists/polls)."""
    _check_request(card_id, prompt)
    jid = job_id or f"img-{hashlib.sha256(f'{card_id}:{prompt}:{time.time_ns()}'.encode()).hexdigest()[:12]}"
    return {
        "job_id": jid, "kind": "image_generate", "card_id": card_id,
        "prompt": prompt.strip(), "status": "queued",
        "attempts": 0, "result_ref": None, "error": None,
    }


def poll_job(
    job: Mapping[str, Any],
    generate: Callable[[str, str], Mapping[str, Any]] | None = None,
    max_attempts: int = 3,
) -> dict:
    """Advance one job by a single step. Pure w.r.t. inputs (no I/O here).

    - done/failed jobs are returned unchanged (idempotent poll).
    - queued/running: attempt ``generate(prompt, card_id)``:
      success -> done with result_ref; exception -> attempts+1;
      attempts exhausted -> done-degraded with placeholder result_ref
      and recorded error (never hard-failed in v1).
    - generate=None -> straight to placeholder (offline/mock path).
    Returns a NEW dict; input is never mutated.
    """
    if not isinstance(job, Mapping):
        raise ImagePipeError("job must be a mapping")
    if job.get("kind") != "image_generate":
        raise ImagePipeError(f"unknown job kind: {job.get('kind')!r}")
    status = job.get("status")
    if status in ("done", "failed"):
        return dict(job)
    if status not in ("queued", "running"):
        raise ImagePipeError(f"unknown job status: {status!r}")
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be int >= 1")

    out = dict(job)
    prompt = str(job.get("prompt", ""))
    card_id = str(job.get("card_id", ""))
    _check_request(card_id, prompt)

    if generate is None:
        out.update(status="done", result_ref=placeholder_ref(prompt, card_id),
                   error="offline: placeholder used")
        return out
    try:
        ref = generate(prompt, card_id)
        if not isinstance(ref, Mapping) or "file_url" not in ref:
            raise RuntimeError("generate must return a mapping with file_url")
        out.update(status="done", attempts=int(job.get("attempts", 0)) + 1,
                   result_ref=dict(ref), error=None)
        return out
    except Exception as exc:  # noqa: BLE001 — degradation chain records all
        attempts = int(job.get("attempts", 0)) + 1
        out["attempts"] = attempts
        if attempts >= max_attempts:
            out.update(status="done", result_ref=placeholder_ref(prompt, card_id),
                       error=f"degraded after {attempts} attempts: {exc}")
            return out
        out.update(status="running", error=f"attempt {attempts} transient: {exc}")
        return out
