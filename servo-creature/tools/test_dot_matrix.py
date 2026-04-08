#!/usr/bin/env python3
"""
tools/test_dot_matrix.py — MAX7219 dot matrix hardware test
Cycles through all display patterns: eyes, alert, skull, countdown.

Usage:
    python tools/test_dot_matrix.py           # real hardware (SPI)
    python tools/test_dot_matrix.py --mock    # mock (logs pattern names)
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.util.logger import setup_logger
from src.output.dot_matrix_face import create_dot_matrix

setup_logger("test_dot_matrix")

parser = argparse.ArgumentParser()
parser.add_argument("--mock", action="store_true")
parser.add_argument("--hold", type=float, default=1.5, help="Seconds per pattern")
args = parser.parse_args()

print("=" * 40)
print("  Dot Matrix Test")
print("=" * 40)

cfg = {
    "enabled": True,
    "cascaded": 1,
    "spi_port": 0,
    "spi_device": 0,
    "brightness": 4,
}
dots = create_dot_matrix(cfg, mock=args.mock)

if not dots.is_available():
    print("[FAIL] Dot matrix not available — check SPI wiring")
    sys.exit(1)

print(f"[OK] Dot matrix initialised (mock={args.mock})")
print(f"Cycling patterns, {args.hold:.1f}s each …\n")


# Fake GameState
class FakeGS:
    def __init__(self):
        self.mode          = type("M", (), {"name": "FREEPLAY"})()
        self.threat_level  = 0
        self.laser_broken  = False
        self.combo         = 0
        self.prompt        = ""
        self.attract_tick  = 0.0
        self.axis_inverted = False
        self.is_fake_out   = False


gs = FakeGS()

scenarios = [
    ("Eyes: NORMAL",  lambda g: setattr(g, "threat_level", 0) or setattr(g.mode, "name", "FREEPLAY")),
    ("Eyes: WIDE",    lambda g: setattr(g, "threat_level", 2)),
    ("Eyes: ANGRY",   lambda g: setattr(g.mode, "name", "BOSS")),
    ("ALERT icon",    lambda g: setattr(g, "laser_broken", True)),
    ("SKULL icon",    lambda g: (setattr(g, "threat_level", 4), setattr(g, "laser_broken", False))),
]

for label, setup_fn in scenarios:
    setup_fn(gs)
    print(f"  → {label}")
    dots.update(gs)
    time.sleep(args.hold)

# Countdown
gs.laser_broken  = False
gs.threat_level  = 0
gs.mode.name     = "REFLEX"
for n in (3, 2, 1):
    print(f"  → Countdown: {n}")
    dots.show_countdown(n)
    time.sleep(args.hold)

print("\n[OK] All patterns displayed. Dot matrix test complete.")
