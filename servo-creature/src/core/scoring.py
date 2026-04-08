"""
core/scoring.py — Tilt Trial Arena / Mission Breach
Prompt-evaluation logic used by Reflex mode.

ScoreEngine is stateless with respect to the session — it reads from
GameState and delegates writes back to it via gs.register_hit / miss.
"""

import time
from src.util.logger import get_logger

logger = get_logger("scoring")


class ScoreEngine:
    """
    Evaluates whether the player's current tilt matches a prompt and
    records the result in the provided GameState.
    """

    def __init__(self, game_state, game_cfg: dict) -> None:
        self.gs         = game_state
        self._gcfg      = game_cfg
        self._tilt_cfg  = game_cfg.get("tilt", {})
        self._score_cfg = game_cfg.get("scoring", {})
        self._reflex_cfg= game_cfg.get("reflex", {})

    # ── Configuration helpers ─────────────────────────────────────────────────

    @property
    def threshold(self) -> float:
        return float(self._tilt_cfg.get("threshold_deg", 25.0))

    @property
    def deadzone(self) -> float:
        return float(self._tilt_cfg.get("deadzone_deg", 3.0))

    @property
    def shake_threshold(self) -> float:
        return float(self._tilt_cfg.get("shake_accel_threshold", 2.5))

    @property
    def recenter_deadzone(self) -> float:
        cfg_val = self._tilt_cfg.get("recenter_deadzone_deg")
        if cfg_val is not None:
            return float(cfg_val)
        return max(8.0, self.deadzone * 2.0)

    @property
    def base_hit_pts(self) -> int:
        return int(self._score_cfg.get("base_hit_pts", 100))

    @property
    def time_bonus_max(self) -> int:
        return int(self._reflex_cfg.get("time_bonus_max_pts", 50))

    @property
    def miss_penalty(self) -> int:
        return int(self._reflex_cfg.get("miss_penalty_pts", 80))

    def is_centered(self, tilt: dict) -> bool:
        roll  = abs(tilt.get("roll",  0.0))
        pitch = abs(tilt.get("pitch", 0.0))
        return roll <= self.recenter_deadzone and pitch <= self.recenter_deadzone

    def register_recenter_timeout(self) -> str:
        logger.debug("Recenter timeout → MISS")
        return self._record_miss()

    # ── Core evaluation ───────────────────────────────────────────────────────

    def evaluate(
        self,
        tilt: dict,
        prompt_id: str,
        prompt_start: float,
        prompt_duration: float,
    ) -> str:
        """
        Determine whether tilt satisfies the current prompt.

        Returns one of:
            "HIT"     — correct response within time
            "MISS"    — time expired or clearly wrong direction
            "PENDING" — still within window, no conclusion yet
        """
        elapsed = time.monotonic() - prompt_start
        timeout = elapsed >= prompt_duration

        roll  = tilt.get("roll",  0.0)
        pitch = tilt.get("pitch", 0.0)
        amag  = tilt.get("accel_mag", 1.0)

        player_moved = (
            abs(roll)  > self.threshold or
            abs(pitch) > self.threshold or
            amag       > self.shake_threshold
        )

        pid = prompt_id.lower()

        # ── Direction prompts ─────────────────────────────────────────────
        hit = False
        if pid == "left":
            hit = roll <= -self.threshold
        elif pid == "right":
            hit = roll >= self.threshold
        elif pid in ("up", "nose_up"):
            hit = pitch <= -self.threshold
        elif pid in ("down", "nose_down"):
            hit = pitch >= self.threshold
        elif pid == "full_tilt":
            hit = abs(roll) >= self.threshold or abs(pitch) >= self.threshold
        elif pid in ("hold", "freeze"):
            # Use angle-only check — ignores accel_mag to avoid sensor
            # vibration noise causing false misses on a physical wand.
            player_moved_hold = abs(roll) > self.threshold or abs(pitch) > self.threshold
            if player_moved_hold:
                return self._record_miss()
            if timeout:
                return self._record_hit(prompt_start, prompt_duration)
            return "PENDING"
        elif pid == "shake":
            hit = amag > self.shake_threshold

        if hit:
            return self._record_hit(prompt_start, prompt_duration)
        if timeout:
            return self._record_miss()
        return "PENDING"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _record_hit(self, prompt_start: float, prompt_duration: float) -> str:
        elapsed    = time.monotonic() - prompt_start
        time_bonus = self._calc_time_bonus(elapsed, prompt_duration)
        self.gs.register_hit(self.base_hit_pts + time_bonus)
        logger.debug("HIT  +%d pts  (time_bonus=%d)", self.base_hit_pts + time_bonus, time_bonus)
        return "HIT"

    def _record_miss(self) -> str:
        self.gs.register_miss(penalty_pts=self.miss_penalty)
        logger.debug("MISS  -%d pts", self.miss_penalty)
        return "MISS"

    def _calc_time_bonus(self, elapsed: float, duration: float) -> int:
        if duration <= 0:
            return 0
        ratio = 1.0 - (elapsed / duration)
        return int(self.time_bonus_max * max(0.0, ratio))
