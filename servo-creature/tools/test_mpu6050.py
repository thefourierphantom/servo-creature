#!/usr/bin/env python3
"""
tools/test_mpu6050.py — MPU6050 hardware test
Run on the Pi to verify I2C wiring and read live tilt data.

Usage:
    python tools/test_mpu6050.py               # live read loop
    python tools/test_mpu6050.py --calibrate   # run calibration routine
    python tools/test_mpu6050.py --mock        # simulate without hardware
"""

import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.util.logger import setup_logger
from src.util.calibration import run_calibration, load_calibration
from src.input.mpu6050_input import create_mpu6050

setup_logger("test_mpu6050")

parser = argparse.ArgumentParser()
parser.add_argument("--mock",       action="store_true")
parser.add_argument("--calibrate",  action="store_true")
parser.add_argument("--samples",    type=int, default=200)
parser.add_argument("--count",      type=int, default=0,
                    help="Num readings (0 = infinite)")
args = parser.parse_args()

print("=" * 50)
print("  MPU6050 Hardware Test")
print("=" * 50)

cfg = {"i2c_bus": 1, "address": "0x68", "smoothing_alpha": 0.15}
mpu = create_mpu6050(cfg, mock=args.mock)

if not mpu.is_available():
    print("[FAIL] MPU6050 not available — check I2C wiring and address (0x68)")
    sys.exit(1)

print(f"[OK] MPU6050 initialised (mock={args.mock})")

if args.calibrate:
    print(f"\nCalibrating with {args.samples} samples — hold wand flat and still …")
    cal = run_calibration(mpu, sample_count=args.samples)
    print(f"\nCalibration result:")
    print(f"  accel_offset  x={cal['accel_offset']['x']:+.5f}"
          f"  y={cal['accel_offset']['y']:+.5f}"
          f"  z={cal['accel_offset']['z']:+.5f}")
    print(f"  gyro_offset   x={cal['gyro_offset']['x']:+.5f}"
          f"  y={cal['gyro_offset']['y']:+.5f}"
          f"  z={cal['gyro_offset']['z']:+.5f}")
    print("[OK] Saved to config/calibration.yaml")

# Apply any existing calibration
cal_data = load_calibration()
if hasattr(mpu, "apply_calibration"):
    mpu.apply_calibration(cal_data)

print("\nLive readings (Ctrl-C to stop):\n")
print(f"{'#':>5}  {'ROLL':>8}  {'PITCH':>8}  {'ACCEL_MAG':>10}  {'RAW_ROLL':>10}  {'RAW_PITCH':>10}")
print("-" * 65)

count = 0
try:
    while True:
        data = mpu.read()
        count += 1
        print(
            f"{count:>5}  "
            f"{data['roll']:>+8.2f}  "
            f"{data['pitch']:>+8.2f}  "
            f"{data['accel_mag']:>10.4f}  "
            f"{data.get('raw_roll', 0):>+10.2f}  "
            f"{data.get('raw_pitch', 0):>+10.2f}"
        )
        time.sleep(0.1)
        if args.count and count >= args.count:
            break
except KeyboardInterrupt:
    print("\n[STOP] Test complete.")
