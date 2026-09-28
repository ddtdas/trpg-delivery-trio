"""TRPG transcript alignment (MIT). Pure functions.

Segment merging + punctuation normalization for STT output:
- ``merge_segments``: join contiguous segs from the same speaker when
  the gap <= ``max_gap_s`` and the joined text fits ``max_chars``.
- ``normalize_text``: collapse whitespace, ensure CJK-friendly ending
  punctuation (append 。 when the text ends with a bare CJK/alnum run).
Python 3.12 compatible.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

__all__ = ["normalize_text", "merge_segments"]

_WS = re.compile(r"\s+")
_END_PUNCT = ("。", "！", "？", "!", "?", ".", "…", "」", "”")


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    t = _WS.sub(" ", text.strip())
    if not t:
        return t
    if not t.endswith(_END_PUNCT):
        t += "。"
    return t


def _seg_ok(seg: Any, i: int) -> Mapping[str, Any]:
    if not isinstance(seg, Mapping):
        raise TypeError(f"segments[{i}] must be a mapping")
    for key in ("text", "t0", "t1"):
        if key not in seg:
            raise ValueError(f"segments[{i}] missing {key!r}")
    try:
        t0 = float(seg["t0"])
        t1 = float(seg["t1"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"segments[{i}] t0/t1 must be numbers") from exc
    if t1 < t0:
        raise ValueError(f"segments[{i}] t1 < t0")
    if not isinstance(seg["text"], str):
        raise TypeError(f"segments[{i}].text must be str")
    return seg


def merge_segments(
    segments: Sequence[Mapping[str, Any]],
    max_gap_s: float = 1.5,
    max_chars: int = 200,
) -> list[dict]:
    """Merge contiguous same-speaker segments. Pure, order-preserving."""
    if not isinstance(max_gap_s, (int, float)) or max_gap_s < 0:
        raise ValueError("max_gap_s must be >= 0")
    if not isinstance(max_chars, int) or max_chars < 8:
        raise ValueError("max_chars must be int >= 8")
    checked = [_seg_ok(s, i) for i, s in enumerate(segments)]
    out: list[dict] = []
    for seg in checked:
        cur = {
            "text": normalize_text(seg["text"]),
            "t0": float(seg["t0"]), "t1": float(seg["t1"]),
            "speaker": seg.get("speaker"),
        }
        if (
            out and out[-1]["speaker"] == cur["speaker"]
            and cur["t0"] - out[-1]["t1"] <= max_gap_s
            and len(out[-1]["text"]) + len(cur["text"]) + 1 <= max_chars
        ):
            prev = out[-1]
            prev["text"] = normalize_text(prev["text"] + " " + cur["text"])
            prev["t1"] = cur["t1"]
        else:
            out.append(cur)
    return out
