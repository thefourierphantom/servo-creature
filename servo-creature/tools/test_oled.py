#!/usr/bin/env python3
"""
tools/test_oled.py — OLED SSD1306 hardware test
Cycles through all emotion faces on the 128×64 OLED.

Usage:
    python tools/test_oled.py           # real hardware
    python tools/test_oled.py --mock    # mock (logs to console)
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.util.logger import setup_logger
from src.output.oled_face import create_oled, NEUTRAL, HAPPY, ALERT, ANGRY, HURT, OFF

setup_logger("test_oled")

parser = argparse.ArgumentParser()
parser.add_argument("--mock", action="store_true")
parser.add_argument("--hold", type=float, default=2.0, help="Seconds per face")
args = parser.parse_args()

print("=" * 40)
print("  OLED Face Test")
print("=" * 40)

cfg  = {"enabled": True, "i2c_bus": 1, "address": "0x3C", "width": 128, "height": 64}
oled = create_oled(cfg, mock=args.mock)

if not oled.is_available():
    print("[FAIL] OLED not available — check I2C wiring and address (0x3C)")
    sys.exit(1)

print(f"[OK] OLED initialised (mock={args.mock})")
print(f"Cycling emotions, {args.hold:.1f}s each …\n")


# Fake GameState for testing
class FakeGS:
    def __init__(self):
        self.combo = 0
        self.misses = 0
        self.threat_level = 0
        self.attract_tick = 0.0

    def set(self, combo=0, misses=0, threat=0, tick=0.0):
        self.combo       = combo
        self.misses      = misses
        self.threat_level= threat
        self.attract_tick= tick
        return self


scenarios = [
    ("ATTRACT / OFF",  FakeGS().set(),                      "attract"),
    ("FREEPLAY normal",FakeGS().set(),                      "freeplay"),
    ("HAPPY (combo≥5)",FakeGS().set(combo=5),               "freeplay"),
    ("ALERT (reflex)", FakeGS().set(combo=1),               "reflex"),
    ("ANGRY (boss)",   FakeGS().set(combo=0, threat=4),     "boss"),
    ("HURT (miss×3)",  FakeGS().set(combo=0, misses=4),     "reflex"),
]

for label, gs, mode_name in scenarios:
    gs.mode = type("M", (), {"name": mode_name.upper()})()
    print(f"  → {label}")
    oled.update(gs)
    time.sleep(args.hold)

print("\n[OK] All faces displayed. OLED test complete.")
