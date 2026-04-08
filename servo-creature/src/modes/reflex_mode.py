"""
modes/reflex_mode.py — Tilt Trial Arena / Mission Breach
Timed prompt challenge — the core game mode.

Flow per session:
  enter() → reset_session()
  SHOWING  → evaluate tilt each frame → HIT or MISS
  RESULT   → hold feedback screen briefly → next prompt or SUMMARY
  SUMMARY  → display final score → ATTRACT after delay or key press
"""

import random
import time
from src.core.game_state import GameMode
from src.util.logger import get_logger

logger = get_logger("reflex")

_S_SHOWING = "SHOWING"
_S_RESULT  = "RESULT"
_S_SUMMARY = "SUMMARY"


class ReflexMode:
    def __init__(self, gs, game_cfg: dict, prompt_cfg: dict, score_engine) -> None:
        self.gs     = gs
        self._gcfg  = game_cfg.get("reflex", {})
        self._se    = score_engine
        self._pool  = self._build_pool(prompt_cfg.get("reflex_prompts", []))
        self._dur   = float(self._gcfg.get("prompt_duration_sec", 2.5))
        self._count = int(  self._gcfg.get("prompt_count", 15))
        self._hold  = float(game_cfg.get("ui", {}).get("result_hold_sec", 0.55))
        self._sum_t = 4.5       # summary display seconds

        self._state        = _S_SHOWING
        self._prompt_start = 0.0
        self._cur_prompt   = None
        self._prompt_idx   = 0
        self._state_timer  = 0.0

    # ── Pool ──────────────────────────────────────────────────────────────────

    def _build_pool(self, lst: list) -> list:
        pool = []
        for p in lst:
            if p.get("id") == "shake":
                continue
            for _ in range(int(p.get("weight", 1))):
                pool.append(p)
        if not pool:
            pool = [{"id": "hold", "display": "◉ HOLD", "axis": "none", "target": 0}]
        return pool

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def enter(self) -> None:
        self.gs.reset_session()
        self.gs.prompt_total = self._count
        self._prompt_idx     = 0
        self._state          = _S_SHOWING
        self._state_timer    = 0.0
        self._next_prompt()
        logger.info("Reflex session  n=%d  dur=%.1fs", self._count, self._dur)

    def exit(self) -> None:
        self.gs.prompt         = ""
        self.gs.status_message = ""
        self.gs.session_active = False

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

    def _do_showing(self, tilt: dict) -> GameMode | None:
        elapsed  = time.monotonic() - self._prompt_start
        remaining = max(0.0, self._dur - elapsed)
        self.gs.prompt_timer = remaining

        result = self._se.evaluate(
            tilt            = tilt,
            prompt_id       = self._cur_prompt["id"],
            prompt_start    = self._prompt_start,
            prompt_duration = self._dur,
        )
        if result in ("HIT", "MISS"):
            self._state       = _S_RESULT
            self._state_timer = self._hold
        return None

    def _do_result(self, dt: float) -> GameMode | None:
        self._state_timer -= dt
        if self._state_timer <= 0:
            self._prompt_idx += 1
            if self._prompt_idx >= self._count:
                self._to_summary()
            else:
                self._state = _S_SHOWING
                self._next_prompt()
        return None

    def _do_summary(self, dt: float, actions: list) -> GameMode | None:
        self._state_timer -= dt
        for a in actions:
            if a in ("start", "a", "select"):
                return GameMode.ATTRACT
        if self._state_timer <= 0:
            return GameMode.ATTRACT
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _next_prompt(self) -> None:
        self._cur_prompt          = random.choice(self._pool)
        self.gs.prompt            = self._cur_prompt["display"]
        self.gs.last_prompt_result= ""
        self.gs.axis_inverted     = False
        self.gs.is_fake_out       = False
        self._prompt_start        = time.monotonic()
        self.gs.prompt_timer      = self._dur
        self.gs.prompt_index      = self._prompt_idx + 1

    def _to_summary(self) -> None:
        self._state       = _S_SUMMARY
        self._state_timer = self._sum_t
        self.gs.prompt    = ""
        self.gs.session_active = False
        self.gs.status_message = (
            f"DONE!  {self.gs.score:,} pts  "
            f"{self.gs.accuracy:.0f}% acc  "
            f"best combo ×{self.gs.max_combo}"
        )
        logger.info("Reflex done  score=%d  acc=%.1f%%  combo=%d",
                    self.gs.score, self.gs.accuracy, self.gs.max_combo)
