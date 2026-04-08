"""
core/scoring.py — Tilt Trial Arena / Mission Breach
Prompt-evaluation logic used by Reflex and Boss modes.

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
        self._boss_cfg  = game_cfg.get("boss", {})

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
    def base_hit_pts(self) -> int:
        return int(self._score_cfg.get("base_hit_pts", 100))

    @property
    def time_bonus_max(self) -> int:
        return int(self._reflex_cfg.get("time_bonus_max_pts", 50))

    # ── Core evaluation ───────────────────────────────────────────────────────

    def evaluate(
        self,
        tilt: dict,
        prompt_id: str,
        prompt_start: float,
        prompt_duration: float,
        axis_inverted: bool = False,
        is_fake_out: bool   = False,
    ) -> str:
        """
        Determine whether tilt satisfies (or violates) the current prompt.

        Returns one of:
            "HIT"     — correct response within time
            "MISS"    — time expired or clearly wrong direction
            "FAKE"    — fake-out detected (player moved when they shouldn't)
            "PENDING" — still within window, no conclusion yet
        """
        elapsed  = time.monotonic() - prompt_start
        timeout  = elapsed >= prompt_duration

        roll  = tilt.get("roll",  0.0)
        pitch = tilt.get("pitch", 0.0)
        amag  = tilt.get("accel_mag", 1.0)

        if axis_inverted:
            roll  = -roll
            pitch = -pitch

        # Determine if the player is clearly tilted in *any* direction
        player_moved = (
            abs(roll)  > self.threshold or
            abs(pitch) > self.threshold or
            amag       > self.shake_threshold
        )
        player_still = (abs(roll) < self.deadzone and abs(pitch) < self.deadzone)

        pid = prompt_id.lower()

        if is_fake_out:
            # In a fake-out the player must FREEZE.  Moving is a fail.
            if player_moved:
                self._record_fake(prompt_start, prompt_duration)
                return "FAKE"
            if timeout:
                return self._record_hit(prompt_start, prompt_duration)
            return "PENDING"

        # ── Direction prompts ─────────────────────────────────────────────
        hit = False
        if pid in ("left",):
            hit = roll <= -self.threshold
        elif pid in ("right",):
            hit = roll >= self.threshold
        elif pid in ("up", "nose_up"):
            hit = pitch <= -self.threshold
        elif pid in ("down", "nose_down"):
            hit = pitch >= self.threshold
        elif pid in ("full_tilt",):
            hit = abs(roll) >= self.threshold or abs(pitch) >= self.threshold
        elif pid in ("hold", "freeze"):
            # Must hold still for the full duration
            if player_moved:
                self._record_miss()
                return "MISS"
            if timeout:
                return self._record_hit(prompt_start, prompt_duration)
            return "PENDING"
        elif pid == "shake":
            hit = amag > self.shake_threshold

        if hit:
            return self._record_hit(prompt_start, prompt_duration)

        if timeout:
            self._record_miss()
            return "MISS"

        return "PENDING"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _record_hit(self, prompt_start: float, prompt_duration: float) -> str:
        elapsed    = time.monotonic() - prompt_start
        time_bonus = self._calc_time_bonus(elapsed, prompt_duration)
        self.gs.register_hit(self.base_hit_pts + time_bonus)
        return "HIT"

    def _record_miss(self) -> str:
        mode_cfg    = self._boss_cfg if self.gs.mode.name == "BOSS" else self._reflex_cfg
        penalty_pts = int(mode_cfg.get("miss_penalty_pts", 0))
        self.gs.register_miss(penalty_pts)
        return "MISS"

    def _record_fake(self, prompt_start: float, prompt_duration: float) -> str:
        self.gs.register_fake()
        return "FAKE"

    def _calc_time_bonus(self, elapsed: float, duration: float) -> int:
        ratio = max(0.0, 1.0 - elapsed / duration)
        return int(self.time_bonus_max * ratio)
