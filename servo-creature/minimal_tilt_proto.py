import time
import math
from dataclasses import dataclass

import board
import adafruit_mpu6050
from adafruit_servokit import ServoKit


@dataclass
class ServoConfig:
    channel: int
    name: str
    min_angle: float = 70.0
    max_angle: float = 110.0
    neutral_angle: float = 90.0
    reversed: bool = False
    actuation_range: int = 180
    min_pulse: int = 500
    max_pulse: int = 2500


class SafeServo:
    def __init__(self, kit: ServoKit, cfg: ServoConfig):
        self.cfg = cfg
        self.servo = kit.servo[cfg.channel]
        self.servo.actuation_range = cfg.actuation_range
        self.servo.set_pulse_width_range(cfg.min_pulse, cfg.max_pulse)

    def clamp(self, angle: float) -> float:
        return max(self.cfg.min_angle, min(self.cfg.max_angle, angle))

    def write(self, angle: float):
        angle = self.clamp(angle)
        if self.cfg.reversed:
            angle = 180.0 - angle
        self.servo.angle = angle

    def neutral(self):
        self.write(self.cfg.neutral_angle)


def map_range(x, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    x = max(in_min, min(in_max, x))
    return out_min + (x - in_min) * (out_max - out_min) / (in_max - in_min)


def accel_to_roll_pitch(ax, ay, az):
    roll = math.degrees(math.atan2(ay, az))
    pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))
    return roll, pitch


def lowpass(prev, new, alpha=0.25):
    return prev + alpha * (new - prev)


def main():
    print("Starting minimal tilt prototype...")
    i2c = board.I2C()
    mpu = adafruit_mpu6050.MPU6050(i2c)
    kit = ServoKit(channels=16)

    yaw_cfg = ServoConfig(channel=0, name="head_yaw", min_angle=70, max_angle=110, neutral_angle=90)
    pitch_cfg = ServoConfig(channel=1, name="head_pitch", min_angle=70, max_angle=110, neutral_angle=90)

    yaw_servo = SafeServo(kit, yaw_cfg)
    pitch_servo = SafeServo(kit, pitch_cfg)

    yaw_servo.neutral()
    pitch_servo.neutral()
    time.sleep(1.0)

    print("Hold MPU6050 level for calibration...")
    samples = []
    start = time.time()
    while time.time() - start < 2.0:
        ax, ay, az = mpu.acceleration
        samples.append(accel_to_roll_pitch(ax, ay, az))
        time.sleep(0.02)

    roll_zero = sum(r for r, _ in samples) / len(samples)
    pitch_zero = sum(p for _, p in samples) / len(samples)

    print(f"Calibration done. roll_zero={roll_zero:.2f}, pitch_zero={pitch_zero:.2f}")

    filt_roll = 0.0
    filt_pitch = 0.0
    dt = 1.0 / 50.0  # ~50 Hz

    try:
        while True:
            t0 = time.time()

            ax, ay, az = mpu.acceleration
            roll, pitch = accel_to_roll_pitch(ax, ay, az)

            roll -= roll_zero
            pitch -= pitch_zero

            filt_roll = lowpass(filt_roll, roll, alpha=0.25)
            filt_pitch = lowpass(filt_pitch, pitch, alpha=0.25)

            yaw_angle = map_range(filt_roll, -30.0, 30.0, yaw_cfg.min_angle, yaw_cfg.max_angle)
            pitch_angle = map_range(filt_pitch, -25.0, 25.0, pitch_cfg.min_angle, pitch_cfg.max_angle)

            yaw_servo.write(yaw_angle)
            pitch_servo.write(pitch_angle)

            print(
                f"roll={filt_roll:6.2f} pitch={filt_pitch:6.2f} "
                f"yaw={yaw_angle:6.1f} pitch_servo={pitch_angle:6.1f}",
                end="\r",
                flush=True
            )

            elapsed = time.time() - t0
            time.sleep(max(0.0, dt - elapsed))

    except KeyboardInterrupt:
        print("\nEmergency stop -> neutral pose")
        yaw_servo.neutral()
        pitch_servo.neutral()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
