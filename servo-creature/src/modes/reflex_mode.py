"""
modes/reflex_mode.py — Tilt Trial Arena / Mission Breach
Endless reflex challenge — survive until you rack up max_misses total misses.

Speed curve (exponential decay per prompt):
  duration = max(dur_floor, dur_start × dur_rate ^ n)
  n=0: 3.0s → n=20: 2.2s → n=40: 1.6s → n=60: 1.2s → n=90+: 0.85s floor

Arm delay:
  Each prompt is NOT evaluated for the first eval_delay_sec seconds after it
  appears.  This prevents carry-over tilt from the previous prompt from
  registering as an immediate miss on the next one.

Death:
  Game over when gs.misses reaches max_misses (default 10).
"""

import random
import time
from src.core.game_state import GameMode
from src.util.logger import get_logger

logger = get_logger("reflex")

_S_SHOWING  = "SHOWING"
_S_RESULT   = "RESULT"
_S_GAMEOVER = "GAMEOVER"


class ReflexMode:
    def __init__(self, gs, game_cfg: dict, prompt_cfg: dict, score_engine) -> None:
        self.gs    = gs
        self._gcfg = game_cfg.get("reflex", {})
        self._se   = score_engine
        self._pool = self._build_pool(prompt_cfg.get("reflex_prompts", []))

        # Speed-ramp
        self._dur_start = float(self._gcfg.get("dur_start",  3.0))
        self._dur_floor = float(self._gcfg.get("dur_floor",  0.85))
        self._dur_rate  = float(self._gcfg.get("dur_rate",   0.985))

        # Death
        self._max_misses = int(self._gcfg.get("max_misses", 10))

        # Arm delay — how long after a new prompt appears before we evaluate
        self._eval_delay = float(self._gcfg.get("eval_delay_sec", 0.35))

        # Timing
        self._hold          = float(game_cfg.get("ui", {}).get("result_hold_sec", 0.34))
        self._gameover_hold = 7.0
        self._recenter_win  = float(self._gcfg.get("recenter_window_sec", 2.0))

        self._state        = _S_SHOWING
        self._prompt_start = 0.0
        self._cur_prompt: dict | None = None
        self._state_timer  = 0.0
        self._arming_timer = 0.0
        self._armed = False

    # ── Prompt pool ───────────────────────────────────────────────────────────

    def _build_pool(self, lst: list) -> list:
        pool = []
        for p in lst:
            if p.get("id") == "shake":
                continue
            for _ in range(int(p.get("weight", 1))):
                pool.append(p)
        if not pool:
            pool = [{"id": "left", "display": "← LEFT", "axis": "roll", "target": -1}]
        return pool

    # ── Speed / wave helpers ──────────────────────────────────────────────────

    def _current_dur(self) -> float:
        n = self.gs.prompt_index
        return max(self._dur_floor, self._dur_start * (self._dur_rate ** n))

    def _current_wave(self) -> int:
        return self.gs.prompt_index // 10 + 1

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def enter(self) -> None:
        self.gs.reset_session()
        self.gs.prompt_total = 0   # 0 → signals "endless" to dashboard
        self._state       = _S_SHOWING
        self._state_timer = 0.0
        self._next_prompt()
        logger.info(
            "Reflex ENDLESS  dur=%.1f→%.2fs  rate=%.3f  max_misses=%d  arm_delay=%.2fs",
            self._dur_start, self._dur_floor, self._dur_rate,
            self._max_misses, self._eval_delay,
        )

    def exit(self) -> None:
        self.gs.prompt            = ""
        self.gs.status_message    = ""
        self.gs.session_active    = False
        self.gs.awaiting_recenter = False
        self.gs.recenter_timer    = 0.0
        self.gs.game_over         = False

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float, tilt: dict, actions: list) -> GameMode | None:
        self.gs.timer += dt

        for a in actions:
            if a == "select":
                return GameMode.ATTRACT

        if self._state == _S_SHOWING:
            return self._do_showing(dt, tilt)
        if self._state == _S_RESULT:
            return self._do_result(dt)
        if self._state == _S_GAMEOVER:
            return self._do_gameover(dt, actions)
        return None

    # ── States ────────────────────────────────────────────────────────────────

    def _do_showing(self, dt: float, tilt: dict) -> GameMode | None:
        dur = self._current_dur()
        now = time.monotonic()

        # ── Arm delay ────────────────────────────────────────────────────
        # For the first eval_delay_sec after a prompt appears, show the full
        # timer bar but don't evaluate yet.  This absorbs carry-over tilt.
        arm_elapsed = now - self._prompt_start
        if arm_elapsed < self._eval_delay:
            self.gs.prompt_timer = dur
            return None

        # Evaluate against the post-arm window
        eval_start = self._prompt_start + self._eval_delay
        eval_dur   = max(0.1, dur - self._eval_delay)

        elapsed = now - eval_start
        self.gs.prompt_timer = max(0.0, eval_dur - elapsed)

        result = self._se.evaluate(
            tilt            = tilt,
            prompt_id       = self._cur_prompt["id"],
            prompt_start    = eval_start,
            prompt_duration = eval_dur,
        )
        if result in ("HIT", "MISS"):
            self._state       = _S_RESULT
            self._state_timer = self._hold
        return None

    def _do_result(self, dt: float) -> GameMode | None:
        self._state_timer -= dt
        if self._state_timer > 0:
            return None

        # ── Death check ───────────────────────────────────────────────────
        if self.gs.misses >= self._max_misses:
            self._to_gameover()
            return None

        # Next prompt
        self.gs.prompt_index += 1
        self._update_status()
        self._state = _S_SHOWING
        self._next_prompt()
        return None

    def _do_gameover(self, dt: float, actions: list) -> GameMode | None:
        self._state_timer -= dt
        for a in actions:
            if a in ("start", "a", "select"):
                return GameMode.ATTRACT
        if self._state_timer <= 0:
            return GameMode.ATTRACT
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _next_prompt(self) -> None:
        self._cur_prompt   = random.choice(self._pool)
        self.gs.prompt     = self._cur_prompt["display"]
        self._prompt_start = time.monotonic()

    def _update_status(self) -> None:
        wave = self._current_wave()
        dur  = self._current_dur()
        remaining_misses = self._max_misses - self.gs.misses
        self.gs.status_message = f"Wave {wave}  ·  {dur:.1f}s  ·  {remaining_misses} miss left"

    def _to_gameover(self) -> None:
        self.gs.game_over      = True
        self.gs.session_active = False
        self.gs.prompt         = ""
        self._state            = _S_GAMEOVER
        self._state_timer      = self._gameover_hold
        logger.info(
            "GAME OVER  survived=%d  score=%d  misses=%d  max_combo=%d",
            self.gs.prompt_index, self.gs.score,
            self.gs.misses, self.gs.max_combo,
        )
