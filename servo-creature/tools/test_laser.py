#!/usr/bin/env python3
"""
tools/test_laser.py — Laser beam / photo-interrupter test
Polls the digital input and flags beam-break events.

Usage:
    python tools/test_laser.py              # real GPIO
    python tools/test_laser.py --mock       # simulated (rare random breaks)
    python tools/test_laser.py --pin 25     # custom BCM pin
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.util.logger import setup_logger
from src.input.laser_input import create_laser

setup_logger("test_laser")

parser = argparse.ArgumentParser()
parser.add_argument("--mock",    action="store_true")
parser.add_argument("--pin",     type=int, default=25)
parser.add_argument("--timeout", type=int, default=60)
args = parser.parse_args()

print("=" * 40)
print("  Laser Beam / Trip Detector Test")
print("=" * 40)

cfg = {"enabled": True, "pin": args.pin}
laser = create_laser(cfg, mock=args.mock)

if not laser.is_available():
    print(f"[FAIL] Laser detector not available — check GPIO {args.pin}")
    sys.exit(1)

print(f"[OK] Laser detector on GPIO {args.pin} (active-low, mock={args.mock})")
print("Watching for beam breaks … (Ctrl-C to stop)\n")

break_count = 0
start = time.monotonic()

try:
    while True:
        if laser.is_broken():
            break_count += 1
            ts = time.monotonic() - start
            print(f"  [{ts:>7.2f}s]  ⚡ BEAM BROKEN  (total: {break_count})")
        time.sleep(0.02)
        if args.timeout and (time.monotonic() - start) >= args.timeout:
            break
except KeyboardInterrupt:
    pass

elapsed = time.monotonic() - start
print(f"\n[OK] Laser test complete — {break_count} beam breaks in {elapsed:.1f}s")
