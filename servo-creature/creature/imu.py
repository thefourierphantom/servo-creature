
import math
import time

class IMUReader:
    def __init__(self, mpu, alpha=0.25):
        self.mpu = mpu
        self.alpha = alpha
        self.roll_zero = 0.0
        self.pitch_zero = 0.0
        self.roll_filtered = 0.0
        self.pitch_filtered = 0.0

    @staticmethod
    def accel_to_roll_pitch(ax, ay, az):
        roll = math.degrees(math.atan2(ay, az))
        pitch = math.degrees(math.atan2(-ax, math.sqrt(ay * ay + az * az)))
        return roll, pitch

    def calibrate_level(self, duration_sec=2.0, sample_delay=0.02):
        samples = []
        start = time.time()
        while time.time() - start < duration_sec:
            ax, ay, az = self.mpu.acceleration
            samples.append(self.accel_to_roll_pitch(ax, ay, az))
            time.sleep(sample_delay)

        self.roll_zero = sum(r for r, _ in samples) / len(samples)
        self.pitch_zero = sum(p for _, p in samples) / len(samples)

    def read_tilt(self):
        ax, ay, az = self.mpu.acceleration
        roll, pitch = self.accel_to_roll_pitch(ax, ay, az)

        roll -= self.roll_zero
        pitch -= self.pitch_zero

        self.roll_filtered += self.alpha * (roll - self.roll_filtered)
        self.pitch_filtered += self.alpha * (pitch - self.pitch_filtered)

        return self.roll_filtered, self.pitch_filtered

