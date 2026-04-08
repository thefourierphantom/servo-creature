"""
modes/calibration_mode.py — Tilt Trial Arena / Mission Breach
Non-blocking calibration mode.

Collects MPU6050 samples across multiple game frames so the render loop
stays alive (no blocking sleep). Shows a live progress bar and a result
screen before automatically returning to the previous mode.

Flow:
  enter() ──► SETTLING (hold_sec delay) ──► COLLECTING (N samples)
           ──► RESULT   (return_delay_sec) ──► previous mode
"""

import time
from src.core.game_state import GameMode
from src.util.calibration import save_calibration
from src.util.logger import get_logger

logger = get_logger("calibration_mode")


class CalibrationMode:
    """Full-screen, non-blocking calibration flow."""

    _PHASE_SETTLE   = "SETTLE"
    _PHASE_COLLECT  = "COLLECT"
    _PHASE_RESULT   = "RESULT"

    def __init__(self, gs, mpu_input, game_cfg: dict) -> None:
        self.gs    = gs
        self._mpu  = mpu_input
        self._gcfg = game_cfg.get("calibration", {})

        self._settle_dur   = float(self._gcfg.get("hold_sec",        0.5))
        self._return_dur   = float(self._gcfg.get("return_delay_sec", 2.0))

        # Load total_samples from hardware config (stored at init time)
        self._total        = 0    # set in enter()
        self._phase        = self._PHASE_SETTLE
        self._phase_timer  = 0.0

        # Accumulators
        self._sums = dict(ax=0.0, ay=0.0, az=0.0, gx=0.0, gy=0.0, gz=0.0)
        self._n    = 0

        # Result for display
        self.cal_result: dict | None = None
        # How far along collection is (0.0 → 1.0)
        self.progress: float = 0.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def enter(self, total_samples: int = 150) -> None:
        self._total       = total_samples
        self._phase       = self._PHASE_SETTLE
        self._phase_timer = self._settle_dur
        self._sums        = dict(ax=0.0, ay=0.0, az=0.0, gx=0.0, gy=0.0, gz=0.0)
        self._n           = 0
        self.cal_result   = None
        self.progress     = 0.0
        self.gs.prompt    = ""
        self.gs.status_message = "Hold wand flat and still …"
        logger.info("Calibration started  total_samples=%d", total_samples)

    def exit(self) -> None:
        self.gs.status_message = ""

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, dt: float, _tilt: dict, actions: list) -> GameMode | None:
        """
        Collects ONE raw sample per call (called at mpu_poll_hz or render fps —
        whichever calls this).  Transitions phases automatically.
        Returns desired GameMode when done, else None.
        """
        self._phase_timer -= dt

        if self._phase == self._PHASE_SETTLE:
            if self._phase_timer <= 0:
                self._phase       = self._PHASE_COLLECT
                self._phase_timer = 0.0
            return None

        if self._phase == self._PHASE_COLLECT:
            # Collect one raw sample per update call
            raw = self._mpu.read_raw()
            self._sums["ax"] += raw.get("accel_x", 0.0)
            self._sums["ay"] += raw.get("accel_y", 0.0)
            self._sums["az"] += raw.get("accel_z", 1.0)
            self._sums["gx"] += raw.get("gyro_x",  0.0)
            self._sums["gy"] += raw.get("gyro_y",  0.0)
            self._sums["gz"] += raw.get("gyro_z",  0.0)
            self._n += 1
            self.progress = self._n / self._total

            if self._n >= self._total:
                self._finish()
                self._phase       = self._PHASE_RESULT
                self._phase_timer = self._return_dur
            return None

        if self._phase == self._PHASE_RESULT:
            # Any key skips the delay and returns immediately
            if actions or self._phase_timer <= 0:
                logger.info("Calibration complete — returning to %s",
                            self.gs.previous_mode.name)
                return self.gs.previous_mode
        return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _finish(self) -> None:
        n = float(self._n)
        cal = {
            "calibrated": True,
            "accel_offset": {
                "x": self._sums["ax"] / n,
                "y": self._sums["ay"] / n,
                "z": (self._sums["az"] / n) - 1.0,  # remove 1 g gravity
            },
            "gyro_offset": {
                "x": self._sums["gx"] / n,
                "y": self._sums["gy"] / n,
                "z": self._sums["gz"] / n,
            },
            "roll_offset":  0.0,
            "pitch_offset": 0.0,
        }
        save_calibration(cal)
        if hasattr(self._mpu, "apply_calibration"):
            self._mpu.apply_calibration(cal)
        self.gs.calibrated = True
        self.cal_result    = cal
        self.gs.status_message = "Calibration saved!"
        logger.info(
            "Offsets  ax=%+.4f ay=%+.4f az=%+.4f  gx=%+.4f gy=%+.4f gz=%+.4f",
            cal["accel_offset"]["x"], cal["accel_offset"]["y"], cal["accel_offset"]["z"],
            cal["gyro_offset"]["x"],  cal["gyro_offset"]["y"],  cal["gyro_offset"]["z"],
        )

    # ── Display helpers ───────────────────────────────────────────────────────

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def samples_collected(self) -> int:
        return self._n

    @property
    def total_samples(self) -> int:
        return self._total
