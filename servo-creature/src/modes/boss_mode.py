"""
modes/boss_mode.py — Tilt Trial Arena / Mission Breach
High-intensity Reflex variant.

On top of Reflex:
  • Faster prompts (prompt_duration_sec from boss config)
  • Axis-inversion rounds (left/right or up/down flipped)
  • Fake-out rounds (display reads DODGE but correct answer is FREEZE)
  • Steeper miss penalty and faster threat escalation
  • Threat ramps up after prompt 6 regardless of score
"""

import random
import time
from src.core.game_state import GameMode
from src.util.logger import get_logger

logger = get_logger("boss")

_S_SHOWING = "SHOWING"
_S_RESULT  = "RESULT"
_S_SUMMARY = "SUMMARY"


class BossMode:
    def __init__(self, gs, game_cfg: dict, prompt_cfg: dict, score_engine) -> None:
        self.gs     = gs
        self._gcfg  = game_cfg.get("boss", {})
        self._se    = score_engine

        self._dur        = float(self._gcfg.get("prompt_duration_sec",  1.6))
        self._count      = int(  self._gcfg.get("prompt_count",          20))
        self._fake_p     = float(self._gcfg.get("fake_chance",          0.20))
        self._inv_p      = float(self._gcfg.get("inversion_chance",     0.25))
        self._hold_sec   = float(game_cfg.get("ui", {}).get("result_hold_sec", 0.55))
        self._sum_t      = 5.0

        # Build combined prompt pool (reflex + boss extras)
        pool = (prompt_cfg.get("reflex_prompts", []) +
                prompt_cfg.get("boss_extra_prompts", []))
        self._pool     = self._build(pool)
        self._fakeouts = prompt_cfg.get("boss_fakeouts",
                                        ["⚠ DODGE LEFT", "⚠ DODGE RIGHT", "⚠ DUCK"])

        self._state       = _S_SHOWING
        self._cur_prompt  = None
        self._prompt_idx  = 0
        self._prompt_start= 0.0
        self._state_timer = 0.0

    def _build(self, lst):
        pool = []
        for p in lst:
            if p.get("id") == "shake":
                continue
            for _ in range(int(p.get("weight", 1))):
                pool.append(p)
        return pool or [{"id": "left", "display": "← LEFT", "axis": "roll", "target": -1}]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def enter(self) -> None:
        self.gs.reset_session()
        self.gs.prompt_total = self._count
        self._prompt_idx     = 0
        self._state          = _S_SHOWING
        self._state_timer    = 0.0
        self._next_prompt()
        logger.info("Boss session  n=%d  dur=%.1fs  fake=%.0f%%  inv=%.0f%%",
                    self._count, self._dur, self._fake_p*100, self._inv_p*100)

    def exit(self) -> None:
        self.gs.prompt         = ""
        self.gs.status_message = ""
        self.gs.session_active = False
        self.gs.axis_inverted  = False
        self.gs.is_fake_out    = False

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float, tilt: dict, actions: list) -> GameMode | None:
        self.gs.timer += dt

        for a in actions:
            if a == "select":
                return GameMode.ATTRACT

        if self._state == _S_SHOWING:
            return self._do_showing(tilt)
        if self._state == _S_RESULT:
            return self._do_result(dt)
        if self._state == _S_SUMMARY:
            return self._do_summary(dt, actions)
        return None

    # ── States ────────────────────────────────────────────────────────────────

    def _do_showing(self, tilt) -> GameMode | None:
        elapsed   = time.monotonic() - self._prompt_start
        self.gs.prompt_timer = max(0.0, self._dur - elapsed)

        result = self._se.evaluate(
            tilt            = tilt,
            prompt_id       = self._cur_prompt["id"],
            prompt_start    = self._prompt_start,
            prompt_duration = self._dur,
            axis_inverted   = self.gs.axis_inverted,
            is_fake_out     = self.gs.is_fake_out,
        )
        if result in ("HIT", "MISS", "FAKE"):
            self._state       = _S_RESULT
            self._state_timer = self._hold_sec
            # Ramp threat after mid-point regardless
            if self._prompt_idx >= self._count // 2:
                self.gs.threat_level = min(5, self.gs.threat_level + 1)
        return None

    def _do_result(self, dt) -> GameMode | None:
        self._state_timer -= dt
        if self._state_timer <= 0:
            self._prompt_idx += 1
            if self._prompt_idx >= self._count:
                self._to_summary()
            else:
                self._state = _S_SHOWING
                self._next_prompt()
        return None

    def _do_summary(self, dt, actions) -> GameMode | None:
        self._state_timer -= dt
        for a in actions:
            if a in ("start", "a", "select"):
                return GameMode.ATTRACT
        return GameMode.ATTRACT if self._state_timer <= 0 else None

    # ── Prompt setup ──────────────────────────────────────────────────────────

    def _next_prompt(self) -> None:
        is_fake = random.random() < self._fake_p
        is_inv  = (not is_fake) and (random.random() < self._inv_p)

        if is_fake:
            display = random.choice(self._fakeouts)
            self._cur_prompt = {"id": "freeze", "display": display,
                                "axis": "none", "target": 0}
        else:
            self._cur_prompt = random.choice(self._pool)

        self.gs.prompt            = self._cur_prompt["display"]
        self.gs.axis_inverted     = is_inv
        self.gs.is_fake_out       = is_fake
        self.gs.last_prompt_result= ""
        self._prompt_start        = time.monotonic()
        self.gs.prompt_timer      = self._dur
        self.gs.prompt_index      = self._prompt_idx + 1

        # Minimum threat 2 after first 5 prompts in boss mode
        if self._prompt_idx >= 5 and self.gs.threat_level < 2:
            self.gs.threat_level = 2

    def _to_summary(self) -> None:
        self._state            = _S_SUMMARY
        self._state_timer      = self._sum_t
        self.gs.prompt         = ""
        self.gs.session_active = False
        self.gs.axis_inverted  = False
        self.gs.is_fake_out    = False
        self.gs.status_message = (
            f"BOSS DONE!  {self.gs.score:,} pts  "
            f"{self.gs.accuracy:.0f}% acc  "
            f"best combo ×{self.gs.max_combo}"
        )
        logger.info("Boss done  score=%d  acc=%.1f%%  threat=%d",
                    self.gs.score, self.gs.accuracy, self.gs.threat_level)
