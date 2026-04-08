#!/usr/bin/env python3
"""
tools/test_ultrasonic.py — HC-SR04 ultrasonic sensor test
Streams live distance readings.

Usage:
    python tools/test_ultrasonic.py                          # real GPIO
    python tools/test_ultrasonic.py --mock                   # simulated
    python tools/test_ultrasonic.py --trig 23 --echo 24     # custom pins
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.util.logger import setup_logger
from src.input.ultrasonic_input import create_ultrasonic

setup_logger("test_ultrasonic")

parser = argparse.ArgumentParser()
parser.add_argument("--mock",    action="store_true")
parser.add_argument("--trig",    type=int, default=23)
parser.add_argument("--echo",    type=int, default=24)
parser.add_argument("--hazard",  type=float, default=30.0,
                    help="Hazard threshold in cm")
parser.add_argument("--count",   type=int, default=0,
                    help="Number of readings (0 = infinite)")
args = parser.parse_args()

print("=" * 50)
print("  HC-SR04 Ultrasonic Sensor Test")
print("=" * 50)

cfg = {
    "enabled":             True,
    "trigger_pin":         args.trig,
    "echo_pin":            args.echo,
    "hazard_distance_cm":  args.hazard,
}
sonic = create_ultrasonic(cfg, mock=args.mock)

if not sonic.is_available():
    print(f"[FAIL] Ultrasonic not available — check GPIO TRIG={args.trig} ECHO={args.echo}")
    sys.exit(1)

print(f"[OK] Ultrasonic init  TRIG={args.trig}  ECHO={args.echo}  hazard≤{args.hazard}cm  (mock={args.mock})")
print(f"\n{'#':>5}  {'DIST (cm)':>10}  {'HAZARD':>8}")
print("-" * 35)

count = 0
try:
    while True:
        dist   = sonic.distance()
        hazard = sonic.is_hazard()
        count += 1
        flag   = " ⚠ HAZARD" if hazard else ""
        print(f"{count:>5}  {dist:>10.1f}  {'YES' if hazard else 'no':>8}{flag}")
        time.sleep(0.1)
        if args.count and count >= args.count:
            break
except KeyboardInterrupt:
    pass

print(f"\n[OK] Ultrasonic test complete — {count} readings taken.")
