"""
output/oled_face.py — Tilt Trial Arena / Mission Breach
Renders simple pixel-art emotion faces on a 128×64 SSD1306 OLED
using luma.oled + Pillow.

Emotions driven by GameState:
  NEUTRAL  — freeplay / idle
  HAPPY    — hit streak (combo ≥ 3)
  ALERT    — reflex / boss, low threat
  ANGRY    — boss mode or threat ≥ 3
  HURT     — miss streak (combo = 0, misses ≥ 3)
  DEAD     — game over (if implemented)
  OFF      — attract mode / blank

MockOLED writes face strings to stdout for testing on laptop.
"""

import math
from src.util.logger import get_logger

logger = get_logger("oled_face")


# ── Emotion enum-ish ──────────────────────────────────────────────────────────

NEUTRAL = "NEUTRAL"
HAPPY   = "HAPPY"
ALERT   = "ALERT"
ANGRY   = "ANGRY"
HURT    = "HURT"
OFF     = "OFF"


def _pick_emotion(gs) -> str:
    """Derive which face to show from GameState."""
    mode = gs.mode.name
    if mode == "ATTRACT":
        return OFF
    if mode == "CALIBRATING":
        return ALERT
    if gs.combo >= 5:
        return HAPPY
    if mode == "BOSS" or gs.threat_level >= 3:
        return ANGRY
    if gs.misses >= 3 and gs.combo == 0:
        return HURT
    if mode in ("REFLEX", "BOSS"):
        return ALERT
    return NEUTRAL


# ── Mock OLED ─────────────────────────────────────────────────────────────────

class MockOLED:
    def __init__(self, cfg: dict) -> None:
        self._last = ""
        logger.info("MockOLED active — emotions logged to console")

    def init(self) -> bool:
        return True

    def update(self, gs) -> None:
        emotion = _pick_emotion(gs)
        if emotion != self._last:
            logger.info("OLED face → %s", emotion)
            self._last = emotion

    def clear(self) -> None:
        pass

    def is_available(self) -> bool:
        return True


# ── Real OLED ─────────────────────────────────────────────────────────────────

class RealOLED:
    """
    Draws pixel faces using Pillow, renders to SSD1306 via luma.oled.
    All draw operations use a 128×64 canvas.
    """

    def __init__(self, cfg: dict) -> None:
        self._cfg       = cfg
        self._device    = None
        self._available = False
        self._last_em   = None
        self._t         = 0.0

    def init(self) -> bool:
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306

            bus  = int(self._cfg.get("i2c_bus", 1))
            addr = int(str(self._cfg.get("address", "0x3C")), 16)
            w    = int(self._cfg.get("width",  128))
            h    = int(self._cfg.get("height",  64))
            rot  = int(self._cfg.get("rotate",   0))

            serial = i2c(port=bus, address=addr)
            self._device    = ssd1306(serial, width=w, height=h, rotate=rot)
            self._available = True
            logger.info("OLED SSD1306 ready  bus=%d  addr=0x%02X  %dx%d", bus, addr, w, h)
            return True
        except Exception as exc:
            logger.warning("OLED init failed: %s", exc)
            return False

    def update(self, gs) -> None:
        if not self._available:
            return
        self._t += 0.016
        emotion = _pick_emotion(gs)
        try:
            from luma.core.render import canvas
            with canvas(self._device) as draw:
                self._draw_face(draw, emotion, gs)
        except Exception as exc:
            logger.error("OLED draw error: %s", exc)

    def _draw_face(self, draw, emotion: str, gs) -> None:
        """
        128×64 pixel face.  Coordinate origin top-left.
        Eyes centred around (42, 22) and (86, 22).
        Mouth centred around (64, 46).
        """
        W, H = 128, 64

        if emotion == OFF:
            return   # blank display

        # ── Eyes ──────────────────────────────────────────────────────────
        blink = int(self._t * 2) % 8 == 0   # quick blink

        if emotion == HAPPY:
            # Curved-up arcs for happiness
            if not blink:
                draw.arc([32, 14, 52, 30], start=0,   end=180, fill="white")
                draw.arc([76, 14, 96, 30], start=0,   end=180, fill="white")
        elif emotion == ANGRY:
            # Slanted angry eyes
            draw.line([32, 14, 52, 22], fill="white", width=3)
            draw.line([76, 22, 96, 14], fill="white", width=3)
            draw.rectangle([36, 16, 50, 26], fill="white")
            draw.rectangle([78, 16, 92, 26], fill="white")
        elif emotion == HURT:
            # X eyes
            draw.line([34, 14, 50, 28], fill="white", width=2)
            draw.line([50, 14, 34, 28], fill="white", width=2)
            draw.line([78, 14, 94, 28], fill="white", width=2)
            draw.line([94, 14, 78, 28], fill="white", width=2)
        else:
            # Normal circles
            if blink:
                draw.rectangle([36, 22, 50, 24], fill="white")
                draw.rectangle([78, 22, 92, 24], fill="white")
            else:
                draw.ellipse([33, 13, 53, 31], fill="white")
                draw.ellipse([75, 13, 95, 31], fill="white")
                # Pupils
                if emotion == ALERT:
                    # look forward-wide
                    draw.ellipse([40, 18, 46, 26], fill="black")
                    draw.ellipse([82, 18, 88, 26], fill="black")
                else:
                    draw.ellipse([39, 19, 47, 27], fill="black")
                    draw.ellipse([81, 19, 89, 27], fill="black")

        # ── Mouth ─────────────────────────────────────────────────────────
        if emotion == HAPPY:
            draw.arc([44, 38, 84, 58], start=0, end=180, fill="white")
        elif emotion == ANGRY:
            draw.arc([44, 46, 84, 58], start=180, end=360, fill="white")
        elif emotion == HURT:
            draw.arc([44, 46, 84, 60], start=180, end=360, fill="white")
        elif emotion == ALERT:
            draw.rectangle([55, 42, 73, 52], fill="white")
        else:
            # Neutral flat mouth
            draw.line([50, 48, 78, 48], fill="white", width=2)

        # ── Combo indicator: dots along bottom ────────────────────────────
        if gs.combo > 0:
            for i in range(min(gs.combo, 8)):
                cx_ = 10 + i * 14
                draw.ellipse([cx_, 57, cx_ + 6, 63], fill="white")

    def clear(self) -> None:
        if self._available and self._device:
            self._device.cleanup()

    def is_available(self) -> bool:
        return self._available


# ── Factory ───────────────────────────────────────────────────────────────────

def create_oled(cfg: dict, mock: bool = False):
    if mock or not cfg.get("enabled", True):
        o = MockOLED(cfg)
        o.init()
        return o
    o = RealOLED(cfg)
    if not o.init():
        logger.warning("OLED unavailable — using mock")
        o = MockOLED(cfg)
        o.init()
    return o
