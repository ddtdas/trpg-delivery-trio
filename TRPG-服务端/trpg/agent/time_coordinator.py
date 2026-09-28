"""Time coordinator — W-B2 implementation (DESIGN §2.3) + BW-2 scheduling.

Frozen signatures from W-A3 are unchanged. Deterministic, no I/O:
tick / act_order (DEX desc, tie by name) / check_pace (timeout, cold-field,
off-track, spotlight) / spotlight_next (round-robin) / budget.

BW-2 additions (additive only — no frozen signature changed):
  - player wait clock: record_action / grant_window / wait_clock / wait_stats
    (rolling simulated-clock wait from action submission to the next action
    window of the same player);
  - scene-aware spotlight fairness: spotlight_next(scene_id) guarantees every
    PC >=1 valid action window per scene; spotlight_sequence(scene_id, n)
    returns the fair polling sequence for assertion (no state mutation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimeCoordinator:
    """Round clock / pacing / spotlight / wait-clock driver."""

    def __init__(self, pcs: list[str] | None = None,
                 round_timeout_sec: int = 600,
                 cold_field_rounds: int = 3,
                 act_budgets: dict[str, int] | None = None) -> None:
        self._round = 0
        self._pcs = list(pcs or ["pc_alice", "pc_bob", "pc_cara"])
        self._spot_idx = 0
        self._round_timeout_sec = round_timeout_sec
        self._cold_field_rounds = cold_field_rounds
        self._act_budgets = dict(act_budgets or {"act1_intro": 600,
                                                 "act2_investigate": 1200,
                                                 "act3_showdown": 600})
        self._rounds_since_event = 0
        self._last_scene_id = ""
        self._pc_spot_count = {pc: 0 for pc in self._pcs}
        # -- BW-2 wait clock (rolling simulated-clock wait per player) ----
        self.wait_clock: dict[str, int] = {}
        self._pending_since: dict[str, int] = {}
        self._wait_samples: dict[str, list[int]] = {}
        self._last_grant_at: dict[str, int] = {}
        self._grant_seq: dict[str, int] = {}
        # -- BW-2 scene-aware spotlight fairness --------------------------
        self._scene_id = ""
        self._scene_spot_count: dict[str, int] = {pc: 0 for pc in self._pcs}
        self._scene_spot_idx = 0

    # -- tick ----------------------------------------------------------
    def tick(self, delta: Any) -> Any:
        """Advance the round clock with a SceneDelta -> ClockDelta dict."""
        self._round += 1
        scene_id = ""
        moved = False
        new_clues: list[str] = []
        if isinstance(delta, dict):
            scene_id = str(delta.get("scene_id", ""))
            moved = bool(delta.get("moved", False))
            new_clues = list(delta.get("new_clues", []))
        if new_clues or moved:
            self._rounds_since_event = 0
        else:
            self._rounds_since_event += 1
        if scene_id:
            self._last_scene_id = scene_id
        return {"round": self._round, "ts_wall": _now_iso(),
                "scene_id": self._last_scene_id,
                "idle_rounds": self._rounds_since_event}

    # -- act_order ------------------------------------------------------
    def act_order(self, combat_id: str) -> list[Any]:
        """Precomputed initiative: DEX desc, name-asc tiebreak.

        combat_id format: "name:dex,name:dex,..." (e.g. "alice:60,bob:60").
        Returns [{"actor", "dex", "order"}...] sorted, order 1-based.
        """
        actors: list[tuple[str, int]] = []
        for part in combat_id.split(","):
            part = part.strip()
            if not part:
                continue
            name, _, dex = part.partition(":")
            actors.append((name.strip(), int(dex.strip())))
        actors.sort(key=lambda a: (-a[1], a[0]))
        return [{"actor": name, "dex": dex, "order": i + 1}
                for i, (name, dex) in enumerate(actors)]

    # -- check_pace ------------------------------------------------------
    def check_pace(self, round_elapsed_sec: int = 0,
                   on_track: bool = True) -> list[Any]:
        """Timeout / cold-field / off-track / spotlight reminders.

        Returns list of {"type", "detail"} (possibly empty).
        """
        rems: list[dict[str, str]] = []
        if round_elapsed_sec >= self._round_timeout_sec:
            rems.append({"type": "timeout",
                         "detail": f"round {self._round} exceeded "
                                   f"{self._round_timeout_sec}s"})
        if self._rounds_since_event >= self._cold_field_rounds:
            rems.append({"type": "cold_field",
                         "detail": f"{self._rounds_since_event} idle rounds"})
        if not on_track:
            rems.append({"type": "off_track",
                         "detail": f"scene {self._last_scene_id} off main line"})
        if self._pcs:
            least = min(self._pc_spot_count.values())
            neglected = [pc for pc, n in self._pc_spot_count.items()
                         if n == least and n < self._round // max(len(self._pcs), 1) + 1
                         and self._round >= len(self._pcs)]
            if neglected:
                rems.append({"type": "spotlight",
                             "detail": f"neglected: {','.join(sorted(neglected))}"})
        return rems

    # -- spotlight_next ---------------------------------------------------
    def spotlight_next(self, scene_id: str | None = None) -> str:
        """Next PC to feature (spotlight grant / valid action window).

        Frozen no-arg behaviour is unchanged (global round-robin, existing
        tests). With scene_id the poll is scene-aware and fair: within a
        scene every registered PC gets >=1 grant before any PC gets a 2nd
        (least-count round-robin). Per-scene counts reset on scene change.
        """
        if not self._pcs:
            raise ValueError("no PCs registered")
        if scene_id is None:
            pc = self._pcs[self._spot_idx % len(self._pcs)]
            self._spot_idx += 1
            self._pc_spot_count[pc] = self._pc_spot_count.get(pc, 0) + 1
            return pc
        if scene_id != self._scene_id:
            self._scene_id = scene_id
            self._scene_spot_count = {pc: 0 for pc in self._pcs}
            self._scene_spot_idx = 0
        counts = self._scene_spot_count
        least = min(counts.values())
        candidates = [pc for pc in self._pcs if counts[pc] == least]
        pc = candidates[self._scene_spot_idx % len(candidates)]
        self._scene_spot_idx += 1
        counts[pc] += 1
        self._pc_spot_count[pc] = self._pc_spot_count.get(pc, 0) + 1
        return pc

    def spotlight_sequence(self, scene_id: str, n: int) -> list[str]:
        """Deterministic fair polling sequence for a scene (no mutation).

        Mirrors spotlight_next(scene_id) from a fresh scene: every full cycle
        of len(pcs) consecutive grants contains each PC exactly once. Used by
        tests/sim for the "每玩家每幕 >=1 行动窗口" polling-sequence assertion.
        """
        if not self._pcs:
            raise ValueError("no PCs registered")
        counts = {pc: 0 for pc in self._pcs}
        seq: list[str] = []
        for i in range(n):
            least = min(counts.values())
            candidates = [pc for pc in self._pcs if counts[pc] == least]
            pc = candidates[i % len(candidates)]
            counts[pc] += 1
            seq.append(pc)
        return seq

    # -- BW-2 wait clock ---------------------------------------------------
    def record_action(self, player: str, clock_sec: int) -> dict[str, Any]:
        """Player submits an action at simulated clock clock_sec.

        Marks the start of that player's wait window; the next
        grant_window() call for the same player accumulates the delta.
        """
        self._pending_since[player] = clock_sec
        return {"player": player, "submitted_at": clock_sec}

    def grant_window(self, player: str, clock_sec: int) -> dict[str, Any]:
        """Player receives their next action window at clock_sec.

        wait_sec = simulated-clock delta since the player's last submission
        (0 for a first window / grant without a pending submission);
        wait_clock[player] accumulates the deltas rolling across the game.
        Also tracks the grant-to-grant spacing for pacing statistics.
        """
        submitted = self._pending_since.pop(player, None)
        wait_sec = max(0, clock_sec - submitted) if submitted is not None else 0
        self.wait_clock[player] = self.wait_clock.get(player, 0) + wait_sec
        self._wait_samples.setdefault(player, []).append(wait_sec)
        prev_grant = self._last_grant_at.get(player)
        spacing = (clock_sec - prev_grant) if prev_grant is not None else None
        self._last_grant_at[player] = clock_sec
        self._grant_seq[player] = self._grant_seq.get(player, 0) + 1
        return {"player": player, "granted_at": clock_sec,
                "wait_sec": wait_sec,
                "wait_total": self.wait_clock[player],
                "window_no": self._grant_seq[player],
                "spacing_sec": spacing}

    def wait_stats(self) -> dict[str, Any]:
        """Per-player wait statistics over granted windows (sim clock sec).

        Keys: windows / total_sec / max_sec / avg_sec / last_spacing_sec.
        """
        out: dict[str, Any] = {}
        for pc in self._pcs:
            samples = self._wait_samples.get(pc, [])
            last_grant = self._last_grant_at.get(pc)
            out[pc] = {
                "windows": len(samples),
                "total_sec": self.wait_clock.get(pc, 0),
                "max_sec": max(samples) if samples else 0,
                "avg_sec": (sum(samples) / len(samples)) if samples else 0,
                "last_grant_at": last_grant,
            }
        return out

    # -- budget ------------------------------------------------------------
    def budget(self, act_id: str) -> Any:
        """Per-act time budget -> {"act_id", "budget_sec"}."""
        if act_id not in self._act_budgets:
            raise KeyError(f"unknown act_id: {act_id}")
        return {"act_id": act_id, "budget_sec": self._act_budgets[act_id]}
