"""
util/calibration.py — Tilt Trial Arena / Mission Breach
Handles loading, saving, and computing MPU6050 calibration offsets.
"""

import os
import time
import yaml
from src.util.logger import get_logger

logger = get_logger("calibration")

CALIBRATION_FILE = "config/calibration.yaml"


# ── Load / Save ──────────────────────────────────────────────────────────────

def load_calibration() -> dict:
    """
    Load calibration data from config/calibration.yaml.
    Returns defaults if the file does not exist or is malformed.
    """
    defaults = {
        "calibrated": False,
        "accel_offset": {"x": 0.0, "y": 0.0, "z": 0.0},
        "gyro_offset":  {"x": 0.0, "y": 0.0, "z": 0.0},
        "roll_offset":  0.0,
        "pitch_offset": 0.0,
    }
    if not os.path.exists(CALIBRATION_FILE):
        return defaults
    try:
        with open(CALIBRATION_FILE, "r") as fh:
            data = yaml.safe_load(fh)
        if not data:
            return defaults
        # Merge with defaults so missing keys are filled in
        for key, val in defaults.items():
            data.setdefault(key, val)
        return data
    except Exception as exc:
        logger.warning(f"Could not load calibration file: {exc} — using defaults")
        return defaults


def save_calibration(cal_data: dict) -> None:
    """Persist calibration data to config/calibration.yaml."""
    os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
    try:
        with open(CALIBRATION_FILE, "w") as fh:
            yaml.dump(cal_data, fh, default_flow_style=False)
        logger.info("Calibration saved to %s", CALIBRATION_FILE)
    except Exception as exc:
        logger.error("Failed to save calibration: %s", exc)


# ── Active calibration routine ────────────────────────────────────────────────

def run_calibration(mpu_input, sample_count: int = 200, delay_s: float = 0.01) -> dict:
    """
    Collect *sample_count* steady-state samples from the MPU6050 with the wand
    lying flat and still, then compute zero-g / zero-rate offsets.

    Args:
        mpu_input:    An initialised MPU6050 driver (real or mock).
        sample_count: Number of raw samples to average.
        delay_s:      Pause between samples (seconds).

    Returns:
        Calibration dict (also written to disk).
    """
    logger.info("Starting calibration — hold the wand flat and still …")

    ax_sum = ay_sum = az_sum = 0.0
    gx_sum = gy_sum = gz_sum = 0.0

    for i in range(sample_count):
        raw = mpu_input.read_raw()
        ax_sum += raw.get("accel_x", 0.0)
        ay_sum += raw.get("accel_y", 0.0)
        az_sum += raw.get("accel_z", 1.0)
        gx_sum += raw.get("gyro_x",  0.0)
        gy_sum += raw.get("gyro_y",  0.0)
        gz_sum += raw.get("gyro_z",  0.0)
        time.sleep(delay_s)
        if (i + 1) % 50 == 0:
            logger.debug("  … %d / %d samples collected", i + 1, sample_count)

    n = float(sample_count)
    cal = {
        "calibrated": True,
        "accel_offset": {
            "x": ax_sum / n,
            "y": ay_sum / n,
            "z": (az_sum / n) - 1.0,   # gravity-compensated: expected 1g on Z
        },
        "gyro_offset": {
            "x": gx_sum / n,
            "y": gy_sum / n,
            "z": gz_sum / n,
        },
        "roll_offset":  0.0,
        "pitch_offset": 0.0,
    }

    logger.info(
        "Calibration done  accel=(%+.4f, %+.4f, %+.4f)  gyro=(%+.4f, %+.4f, %+.4f)",
        cal["accel_offset"]["x"], cal["accel_offset"]["y"], cal["accel_offset"]["z"],
        cal["gyro_offset"]["x"],  cal["gyro_offset"]["y"],  cal["gyro_offset"]["z"],
    )

    save_calibration(cal)
    return cal
