"""
input/ultrasonic_input.py — Tilt Trial Arena / Mission Breach
HC-SR04 ultrasonic distance sensor driver.

RealUltrasonic  — GPIO trigger/echo timing (Raspberry Pi).
MockUltrasonic  — slow sine-wave oscillation for testing.
create_ultrasonic — factory function.
"""

import math
import time
from src.util.logger import get_logger

logger = get_logger("ultrasonic")

_TIMEOUT_S    = 0.04    # 40 ms pulse timeout (~6.8 m max range)
_SOUND_HALF   = 17150.0  # cm/s  (speed of sound / 2)


class MockUltrasonic:
    def __init__(self, cfg: dict) -> None:
        self._t = 0.0
        self._hazard_cm = float(cfg.get("hazard_distance_cm", 30.0))
        logger.info("MockUltrasonic active — oscillating 20–80 cm")

    def init(self) -> bool:
        return True

    def distance(self) -> float:
        self._t += 0.016
        return 50.0 + math.sin(self._t * 0.4) * 30.0

    def is_hazard(self) -> bool:
        return self.distance() <= self._hazard_cm

    def is_available(self) -> bool:
        return True


class RealUltrasonic:
    def __init__(self, cfg: dict) -> None:
        self._trig  = int(cfg.get("trigger_pin", 23))
        self._echo  = int(cfg.get("echo_pin", 24))
        self._hazard_cm = float(cfg.get("hazard_distance_cm", 30.0))
        self._gpio  = None
        self._available = False

    def init(self) -> bool:
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._trig, GPIO.OUT)
            GPIO.setup(self._echo, GPIO.IN)
            GPIO.output(self._trig, False)
            time.sleep(0.1)            # let sensor settle
            self._gpio      = GPIO
            self._available = True
            logger.info("Ultrasonic — TRIG=%d  ECHO=%d", self._trig, self._echo)
            return True
        except Exception as exc:
            logger.warning("Ultrasonic init failed: %s", exc)
            return False

    def distance(self) -> float:
        """Returns distance in cm, or 999.0 on timeout / error."""
        if not self._available:
            return 999.0
        GPIO = self._gpio
        try:
            # 10 µs trigger pulse
            GPIO.output(self._trig, True)
            time.sleep(0.00001)
            GPIO.output(self._trig, False)

            deadline = time.monotonic() + _TIMEOUT_S
            while GPIO.input(self._echo) == 0:
                if time.monotonic() > deadline:
                    return 999.0
            t_start = time.monotonic()

            deadline = time.monotonic() + _TIMEOUT_S
            while GPIO.input(self._echo) == 1:
                if time.monotonic() > deadline:
                    return 999.0
            t_end = time.monotonic()

            return round((t_end - t_start) * _SOUND_HALF, 1)
        except Exception as exc:
            logger.error("Ultrasonic read error: %s", exc)
            return 999.0

    def is_hazard(self) -> bool:
        return self.distance() <= self._hazard_cm

    def is_available(self) -> bool:
        return self._available


def create_ultrasonic(cfg: dict, mock: bool = False):
    if mock or not cfg.get("enabled", True):
        u = MockUltrasonic(cfg)
        u.init()
        return u
    u = RealUltrasonic(cfg)
    if not u.init():
        logger.warning("Ultrasonic unavailable — using mock")
        u = MockUltrasonic(cfg)
        u.init()
    return u
