"""TRPG voice: browser MediaRecorder opus uplink receiver (MIT).

Pure frame validation + import-batch assembly. The HTTP/WS transport
lives in app/web/ (rest.audio_import already exists); this module owns
the domain rules: AUDIO_CHUNK shape, per-chunk size caps, import batch
-> TRANSCRIPT_APPENDED payload assembly.

Python 3.12 compatible.
"""
from __future__ import annotations

import base64
from typing import Any, Mapping, Sequence

__all__ = [
    "VoiceInputError",
    "validate_chunk",
    "assemble_import",
    "MAX_CHUNK_BYTES",
    "MAX_BATCH_CHUNKS",
]

MAX_CHUNK_BYTES = 256 * 1024  # 256 KiB decoded audio per chunk
MAX_BATCH_CHUNKS = 600  # 10 min @ 1 chunk/s


class VoiceInputError(ValueError):
    """Illegal uplink input (bad mime, bad base64, oversize...)."""


def validate_chunk(frame: Mapping[str, Any]) -> dict:
    """Validate one AUDIO_CHUNK client frame. Returns normalized dict."""
    if not isinstance(frame, Mapping):
        raise VoiceInputError("chunk frame must be a mapping")
    if frame.get("kind") != "AUDIO_CHUNK":
        raise VoiceInputError(f"expected AUDIO_CHUNK, got {frame.get('kind')!r}")
    if frame.get("mime") != "audio/opus":
        raise VoiceInputError(f"mime must be audio/opus, got {frame.get('mime')!r}")
    player_id = frame.get("player_id")
    if not isinstance(player_id, str) or not player_id.strip():
        raise VoiceInputError("player_id must be a non-empty string")
    blob = frame.get("chunk_base64")
    if not isinstance(blob, str) or not blob:
        raise VoiceInputError("chunk_base64 must be a non-empty string")
    try:
        raw = base64.b64decode(blob, validate=True)
    except Exception as exc:
        raise VoiceInputError(f"chunk_base64 is not valid base64: {exc}") from exc
    if len(raw) == 0:
        raise VoiceInputError("decoded chunk is empty")
    if len(raw) > MAX_CHUNK_BYTES:
        raise VoiceInputError(f"chunk {len(raw)}B exceeds {MAX_CHUNK_BYTES}B cap")
    seq = frame.get("seq", 0)
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise VoiceInputError("seq must be int >= 0")
    return {
        "kind": "AUDIO_CHUNK",
        "campaign": str(frame.get("campaign", "")),
        "player_id": player_id.strip(),
        "mime": "audio/opus",
        "chunk_bytes": len(raw),
        "seq": seq,
    }


def assemble_import(
    campaign_id: str,
    player_id: str,
    chunks_base64: Sequence[str],
) -> dict:
    """Assemble a file-import batch -> TRANSCRIPT_APPENDED payload dict.

    Never decodes full audio semantics (cloud STT does that); validates
    shape + caps and returns the payload the caller persists.
    """
    if not isinstance(campaign_id, str) or not campaign_id.strip():
        raise VoiceInputError("campaign_id must be a non-empty string")
    if not isinstance(player_id, str) or not player_id.strip():
        raise VoiceInputError("player_id must be a non-empty string")
    if not isinstance(chunks_base64, (list, tuple)) or not chunks_base64:
        raise VoiceInputError("chunks_base64 must be a non-empty list")
    if len(chunks_base64) > MAX_BATCH_CHUNKS:
        raise VoiceInputError(f"batch {len(chunks_base64)} exceeds {MAX_BATCH_CHUNKS} chunks")
    total = 0
    for i, blob in enumerate(chunks_base64):
        if not isinstance(blob, str) or not blob:
            raise VoiceInputError(f"chunks_base64[{i}] must be a non-empty string")
        try:
            total += len(base64.b64decode(blob, validate=True))
        except Exception as exc:
            raise VoiceInputError(f"chunks_base64[{i}] invalid base64: {exc}") from exc
    if total > MAX_CHUNK_BYTES * MAX_BATCH_CHUNKS:
        raise VoiceInputError("import batch exceeds total size cap")
    return {
        "campaign_id": campaign_id.strip(),
        "seg": {
            "text": f"[imported {len(chunks_base64)} chunks, {total}B]",
            "t0": 0.0, "t1": 0.0, "speaker": player_id.strip(),
        },
        "source": "import",
    }
