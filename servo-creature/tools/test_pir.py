#!/usr/bin/env python3
"""
tools/test_pir.py — PIR motion sensor hardware test
Polls the PIR and prints detection events.

Usage:
    python tools/test_pir.py              # real GPIO (requires Pi)
    python tools/test_pir.py --mock       # simulated triggers
    python tools/test_pir.py --pin 18     # custom BCM pin
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.util.logger import setup_logger
from src.input.pir_input import create_pir

setup_logger("test_pir")

parser = argparse.ArgumentParser()
parser.add_argument("--mock",    action="store_true")
parser.add_argument("--pin",     type=int, default=17)
parser.add_argument("--timeout", type=int, default=60,
                    help="Stop after N seconds (0 = infinite)")
args = parser.parse_args()

print("=" * 40)
print("  PIR Motion Sensor Test")
print("=" * 40)

cfg = {"enabled": True, "pin": args.pin}
pir = create_pir(cfg, mock=args.mock)

if not pir.is_available():
    print(f"[FAIL] PIR not available — check GPIO {args.pin}")
    sys.exit(1)

print(f"[OK] PIR initialised on GPIO {args.pin} (mock={args.mock})")
print(f"Watching for motion events … (Ctrl-C to stop)\n")

detect_count = 0
start = time.monotonic()

try:
    while True:
        if pir.triggered():
            detect_count += 1
            ts = time.monotonic() - start
            print(f"  [{ts:>7.2f}s]  MOTION DETECTED  (total: {detect_count})")
        time.sleep(0.05)
        elapsed = time.monotonic() - start
        if args.timeout and elapsed >= args.timeout:
            break
except KeyboardInterrupt:
    pass

print(f"\n[OK] PIR test complete — {detect_count} detection events in {time.monotonic()-start:.1f}s")
