"""
input/laser_input.py — Tilt Trial Arena / Mission Breach
Laser beam / photo-interrupter trip detector.

Wiring assumption: photo-receiver is pulled HIGH when beam is intact.
Beam broken → GPIO goes LOW → is_broken() returns True.

RealLaser   — GPIO input with pull-up (Raspberry Pi).
MockLaser   — random rare triggers for testing.
create_laser — factory function.
"""

import random
import time
from src.util.logger import get_logger

logger = get_logger("laser")


class MockLaser:
    def __init__(self, cfg: dict) -> None:
        self._p_break = 0.0008   # ~0.08 % chance per frame → rare
        logger.info("MockLaser active — %.4f break probability per frame", self._p_break)

    def init(self) -> bool:
        return True

    def is_broken(self) -> bool:
        result = random.random() < self._p_break
        if result:
            logger.debug("MockLaser: simulated beam break")
        return result

    def is_available(self) -> bool:
        return True


class RealLaser:
    """
    Reads a digital input that is normally HIGH (beam intact).
    Pulls LOW when the photo-interrupter is blocked (beam broken).
    """

    def __init__(self, cfg: dict) -> None:
        self._pin       = int(cfg.get("pin", 25))
        self._gpio      = None
        self._available = False

    def init(self) -> bool:
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._gpio      = GPIO
            self._available = True
            logger.info("Laser detector on GPIO %d (BCM, active-low)", self._pin)
            return True
        except Exception as exc:
            logger.warning("Laser init failed: %s", exc)
            return False

    def is_broken(self) -> bool:
        if not self._available:
            return False
        try:
            return not bool(self._gpio.input(self._pin))
        except Exception as exc:
            logger.error("Laser read error: %s", exc)
            return False

    def is_available(self) -> bool:
        return self._available


def create_laser(cfg: dict, mock: bool = False):
    if mock or not cfg.get("enabled", True):
        l = MockLaser(cfg)
        l.init()
        return l
    l = RealLaser(cfg)
    if not l.init():
        logger.warning("Laser unavailable — using mock")
        l = MockLaser(cfg)
        l.init()
    return l
