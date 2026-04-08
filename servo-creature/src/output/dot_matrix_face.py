"""
output/dot_matrix_face.py — Tilt Trial Arena / Mission Breach
Renders alert icons, eye patterns, and countdowns on a MAX7219 8×8
LED dot-matrix module via luma.led_matrix.

Display patterns (each is a list of 8 bytes, MSB = left column):
  eyes_normal, eyes_alert, eyes_angry, alert_icon, countdown 3/2/1

MockDotMatrix logs pattern names to console.
"""

from src.util.logger import get_logger

logger = get_logger("dot_matrix")


# ── 8×8 bitmap patterns ───────────────────────────────────────────────────────
# Each row is 8 bits (columns left → right), MSB = left

_P_EYES_NORMAL = [
    0b00000000,
    0b01100110,
    0b01100110,
    0b00000000,
    0b00000000,
    0b10000001,
    0b01000010,
    0b00111100,
]

_P_EYES_WIDE = [
    0b01100110,
    0b11111111,
    0b11111111,
    0b01100110,
    0b00000000,
    0b00111100,
    0b01000010,
    0b10000001,
]

_P_EYES_ANGRY = [
    0b11000011,
    0b01100110,
    0b01100110,
    0b11000011,
    0b00000000,
    0b00111100,
    0b01000010,
    0b10000001,
]

_P_EYES_BLINK = [
    0b00000000,
    0b00000000,
    0b11111111,
    0b00000000,
    0b00000000,
    0b10000001,
    0b01000010,
    0b00111100,
]

_P_ALERT = [
    0b00011000,
    0b00111100,
    0b00111100,
    0b01111110,
    0b01111110,
    0b11111111,
    0b00011000,
    0b00000000,
]

_P_SKULL = [
    0b00111100,
    0b01111110,
    0b11011011,
    0b11111111,
    0b11111111,
    0b01111110,
    0b01111110,
    0b01111110,
]

_P_BLANK = [0x00] * 8

_P_DIGITS = {
    "3": [0b11111110, 0b10000010, 0b11111110, 0b10000010, 0b11111110, 0b00000000, 0b00000000, 0b00000000],
    "2": [0b11111110, 0b00000010, 0b11111110, 0b10000000, 0b11111110, 0b00000000, 0b00000000, 0b00000000],
    "1": [0b01000000, 0b11000000, 0b01000000, 0b01000000, 0b11100000, 0b00000000, 0b00000000, 0b00000000],
    "!": [0b00011000, 0b00011000, 0b00011000, 0b00000000, 0b00011000, 0b00000000, 0b00000000, 0b00000000],
}


def _pick_pattern(gs) -> list:
    """Choose which 8-byte pattern to send based on GameState."""
    mode = gs.mode.name
    threat = gs.threat_level

    if mode == "ATTRACT":
        return _P_EYES_BLINK if int(gs.attract_tick * 2) % 4 == 0 else _P_EYES_NORMAL

    if mode == "CALIBRATING":
        return _P_BLANK

    if gs.laser_broken:
        return _P_ALERT

    if mode == "BOSS":
        return _P_SKULL if threat >= 3 else _P_EYES_ANGRY

    if threat >= 4:
        return _P_SKULL
    if threat >= 2:
        return _P_EYES_WIDE
    if mode == "REFLEX":
        return _P_EYES_WIDE if gs.prompt else _P_EYES_NORMAL

    return _P_EYES_NORMAL


# ── Mock ──────────────────────────────────────────────────────────────────────

class MockDotMatrix:
    def __init__(self, cfg: dict) -> None:
        self._last = None
        logger.info("MockDotMatrix active — pattern names logged")

    def init(self) -> bool:
        return True

    def update(self, gs) -> None:
        pat = _pick_pattern(gs)
        if pat != self._last:
            logger.debug("DotMatrix pattern changed")
            self._last = pat

    def show_countdown(self, n: int) -> None:
        logger.info("DotMatrix countdown: %d", n)

    def is_available(self) -> bool:
        return True


# ── Real MAX7219 ──────────────────────────────────────────────────────────────

class RealDotMatrix:
    def __init__(self, cfg: dict) -> None:
        self._cfg       = cfg
        self._device    = None
        self._available = False

    def init(self) -> bool:
        try:
            from luma.led_matrix.device import max7219
            from luma.core.interface.serial import spi, noop

            port       = int(self._cfg.get("spi_port",   0))
            device_id  = int(self._cfg.get("spi_device", 0))
            cascaded   = int(self._cfg.get("cascaded",   1))
            brightness = int(self._cfg.get("brightness", 4))

            serial  = spi(port=port, device=device_id, gpio=noop())
            self._device = max7219(serial, cascaded=cascaded,
                                   block_orientation=-90)
            self._device.contrast(brightness * 16)
            self._available = True
            logger.info("MAX7219 ready  SPI%d.%d  cascaded=%d", port, device_id, cascaded)
            return True
        except Exception as exc:
            logger.warning("DotMatrix init failed: %s", exc)
            return False

    def update(self, gs) -> None:
        if not self._available:
            return
        pat = _pick_pattern(gs)
        self._send(pat)

    def show_countdown(self, n: int) -> None:
        if not self._available:
            return
        pat = _P_DIGITS.get(str(n), _P_BLANK)
        self._send(pat)

    def _send(self, pattern: list) -> None:
        try:
            from luma.core.render import canvas
            from PIL import Image
            img = Image.new("1", (8, 8))
            for row_idx, byte in enumerate(pattern[:8]):
                for col_idx in range(8):
                    bit = (byte >> (7 - col_idx)) & 1
                    img.putpixel((col_idx, row_idx), bit)
            self._device.display(img)
        except Exception as exc:
            logger.error("DotMatrix send error: %s", exc)

    def is_available(self) -> bool:
        return self._available


# ── Factory ───────────────────────────────────────────────────────────────────

def create_dot_matrix(cfg: dict, mock: bool = False):
    if mock or not cfg.get("enabled", True):
        d = MockDotMatrix(cfg)
        d.init()
        return d
    d = RealDotMatrix(cfg)
    if not d.init():
        logger.warning("DotMatrix unavailable — using mock")
        d = MockDotMatrix(cfg)
        d.init()
    return d
