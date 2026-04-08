"""
core/game_state.py — Tilt Trial Arena / Mission Breach
Single source of truth for all runtime state.

Key additions vs v1:
  raw_tilt     — offset-corrected angles before axis mapping (for debug overlay)
  debug_mode   — toggle debug overlay (D key)
  score_delta  — last point change shown as "+N" popup
  prompt_index / prompt_total — progress through current session
"""

from enum import Enum, auto
from src.util.logger import get_logger

logger = get_logger("game_state")


class GameMode(Enum):
    ATTRACT     = auto()
    FREEPLAY    = auto()
    REFLEX      = auto()
    BOSS        = auto()
    PAUSED      = auto()
    CALIBRATING = auto()


class GameState:
    def __init__(self) -> None:
        # ── Mode ─────────────────────────────────────────────────────────
        self.mode:          GameMode = GameMode.ATTRACT
        self.previous_mode: GameMode = GameMode.ATTRACT

        # ── Session stats ─────────────────────────────────────────────────
        self.score:        int   = 0
        self.combo:        int   = 0
        self.max_combo:    int   = 0
        self.hits:         int   = 0
        self.misses:       int   = 0
        self.session_active: bool = False
        self.prompt_index: int   = 0   # 1-based, for HUD "Prompt N / M"
        self.prompt_total: int   = 0

        # ── Timing ────────────────────────────────────────────────────────
        self.timer:             float = 0.0   # session elapsed time
        self.prompt_timer:      float = 0.0   # seconds remaining for current prompt
        self.idle_timer:        float = 0.0

        # ── Sensor data ───────────────────────────────────────────────────
        # tilt: fully mapped game axes (what scoring sees)
        self.tilt: dict = {"roll": 0.0, "pitch": 0.0, "accel_mag": 1.0,
                           "raw_roll": 0.0, "raw_pitch": 0.0}

        # ── HUD / feedback fields ─────────────────────────────────────────
        self.prompt:              str   = ""
        self.last_prompt_result:  str   = ""    # "HIT" | "MISS" | "FAKE" | ""
        self.result_flash_timer:  float = 0.0   # screen flash countdown
        self.result_hold_timer:   float = 0.0   # how long HIT/MISS label stays

        self.score_delta:         int   = 0     # last change, shown as "+N"
        self.score_delta_timer:   float = 0.0   # popup countdown

        self.threat_level: int   = 0   # 0–5
        self.calibrated:   bool  = False
        self.status_message: str = ""
        self.awaiting_recenter: bool = False
        self.recenter_timer:    float = 0.0

        # ── Boss flags ────────────────────────────────────────────────────
        self.axis_inverted: bool = False
        self.is_fake_out:   bool = False

        # ── Dev / debug ───────────────────────────────────────────────────
        self.debug_mode:   bool  = False
        self.attract_tick: float = 0.0

    # ── Derived ───────────────────────────────────────────────────────────────

    @property
    def accuracy(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100.0) if total > 0 else 0.0

    @property
    def combo_multiplier(self) -> float:
        step = 0.5
        return min(1.0 + self.combo * step, 5.0)

    # ── Mode transition ───────────────────────────────────────────────────────

    def transition(self, new_mode: GameMode) -> None:
        if new_mode == self.mode:
            return
        logger.info("Mode  %s → %s", self.mode.name, new_mode.name)
        self.previous_mode = self.mode
        self.mode = new_mode

    # ── Session ───────────────────────────────────────────────────────────────

    def reset_session(self) -> None:
        self.score             = 0
        self.combo             = 0
        self.max_combo         = 0
        self.hits              = 0
        self.misses            = 0
        self.timer             = 0.0
        self.prompt_timer      = 0.0
        self.prompt_index      = 0
        self.prompt_total      = 0
        self.threat_level      = 0
        self.prompt            = ""
        self.last_prompt_result= ""
        self.result_flash_timer= 0.0
        self.result_hold_timer = 0.0
        self.score_delta       = 0
        self.score_delta_timer = 0.0
        self.axis_inverted     = False
        self.is_fake_out       = False
        self.awaiting_recenter = False
        self.recenter_timer    = 0.0
        self.session_active    = True

    # ── Scoring ───────────────────────────────────────────────────────────────

    def add_score(self, base_pts: int) -> int:
        earned = int(base_pts * self.combo_multiplier)
        self.score += earned
        return earned

    def register_hit(self, base_pts: int = 100,
                     flash_sec: float = 0.18, hold_sec: float = 0.55) -> int:
        self.combo     += 1
        self.max_combo  = max(self.combo, self.max_combo)
        self.hits      += 1
        self.threat_level = max(0, self.threat_level - 1)
        earned = self.add_score(base_pts)
        self.last_prompt_result = "HIT"
        self.result_flash_timer = flash_sec
        self.result_hold_timer  = hold_sec
        self.score_delta        = earned
        self.score_delta_timer  = 0.8
        return earned

    def register_miss(self, penalty_pts: int = 0,
                      flash_sec: float = 0.28, hold_sec: float = 0.55) -> None:
        self.combo     = 0
        self.misses   += 1
        self.threat_level = min(5, self.threat_level + 1)
        self.score     = max(0, self.score - penalty_pts)
        self.last_prompt_result = "MISS"
        self.result_flash_timer = flash_sec
        self.result_hold_timer  = hold_sec
        self.score_delta        = -penalty_pts if penalty_pts else 0
        self.score_delta_timer  = 0.6

    def register_fake(self, flash_sec: float = 0.28, hold_sec: float = 0.55) -> None:
        self.combo     = 0
        self.misses   += 1
        self.threat_level = min(5, self.threat_level + 2)
        self.last_prompt_result = "FAKE"
        self.result_flash_timer = flash_sec
        self.result_hold_timer  = hold_sec
        self.score_delta        = 0
        self.score_delta_timer  = 0.6

    # ── Serialise ─────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "mode":           self.mode.name,
            "score":          self.score,
            "combo":          self.combo,
            "max_combo":      self.max_combo,
            "combo_mult":     self.combo_multiplier,
            "hits":           self.hits,
            "misses":         self.misses,
            "accuracy":       self.accuracy,
            "timer":          self.timer,
            "prompt_timer":   self.prompt_timer,
            "prompt_index":   self.prompt_index,
            "prompt_total":   self.prompt_total,
            "threat_level":   self.threat_level,
            "calibrated":     self.calibrated,
            "tilt":           self.tilt,
            "prompt":         self.prompt,
            "last_result":    self.last_prompt_result,
            "axis_inverted":  self.axis_inverted,
            "is_fake_out":    self.is_fake_out,
            "awaiting_recenter": self.awaiting_recenter,
            "recenter_timer": self.recenter_timer,
            "session_active": self.session_active,
            "debug_mode":     self.debug_mode,
        }
