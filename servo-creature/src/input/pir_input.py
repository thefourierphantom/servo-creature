"""
input/pir_input.py — Tilt Trial Arena / Mission Breach
PIR passive-infrared motion sensor driver.

RealPIR    — GPIO BCM input (Raspberry Pi).
MockPIR    — fires a simulated trigger every N seconds.
create_pir — factory function.
"""

import time
import random
from src.util.logger import get_logger

logger = get_logger("pir")


class MockPIR:
    def __init__(self, cfg: dict) -> None:
        self._interval = 20.0   # seconds between simulated triggers
        self._last     = 0.0
        logger.info("MockPIR active — triggers every %.0f s", self._interval)

    def init(self) -> bool:
        return True

    def triggered(self) -> bool:
        """Returns True once per simulated detect event (edge, not level)."""
        now = time.monotonic()
        if now - self._last >= self._interval:
            self._last = now
            logger.debug("MockPIR: simulated trigger")
            return True
        return False

    def is_available(self) -> bool:
        return True


class RealPIR:
    def __init__(self, cfg: dict) -> None:
        self._pin       = int(cfg.get("pin", 17))
        self._gpio      = None
        self._available = False
        self._prev      = False

    def init(self) -> bool:
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.IN)
            self._gpio      = GPIO
            self._available = True
            logger.info("PIR on GPIO %d (BCM)", self._pin)
            return True
        except Exception as exc:
            logger.warning("PIR init failed: %s", exc)
            return False

    def triggered(self) -> bool:
        """
        Returns True on the rising edge only (new detection event).
        Polling-friendly; call once per frame.
        """
        if not self._available:
            return False
        try:
            current = bool(self._gpio.input(self._pin))
            edge    = current and not self._prev
            self._prev = current
            if edge:
                logger.debug("PIR: motion detected")
            return edge
        except Exception as exc:
            logger.error("PIR read error: %s", exc)
            return False

    def is_available(self) -> bool:
        return self._available


def create_pir(cfg: dict, mock: bool = False):
    if mock or not cfg.get("enabled", True):
        p = MockPIR(cfg)
        p.init()
        return p
    p = RealPIR(cfg)
    if not p.init():
        logger.warning("PIR unavailable — using mock")
        p = MockPIR(cfg)
        p.init()
    return p
