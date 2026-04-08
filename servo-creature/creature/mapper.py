
def map_range(x, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    x = max(in_min, min(in_max, x))
    return out_min + (x - in_min) * (out_max - out_min) / (in_max - in_min)

class TiltMapper:
    def __init__(self, servo_config):
        self.cfg = servo_config
        self.roll_min = -30.0
        self.roll_max = 30.0
        self.pitch_min = -25.0
        self.pitch_max = 25.0

    def puppet_targets(self, roll, pitch):
        head_yaw = map_range(
            roll,
            self.roll_min,
            self.roll_max,
            self.cfg["head_yaw"]["min_angle"],
            self.cfg["head_yaw"]["max_angle"]
        )

        head_pitch = map_range(
            pitch,
            self.pitch_min,
            self.pitch_max,
            self.cfg["head_pitch"]["min_angle"],
            self.cfg["head_pitch"]["max_angle"]
        )

        left_arm = map_range(roll, self.roll_min, self.roll_max, 105, 75)
        right_arm = map_range(roll, self.roll_min, self.roll_max, 75, 105)
        tail = map_range(pitch, self.pitch_min, self.pitch_max, 85, 95)

        return {
            "head_yaw": head_yaw,
            "head_pitch": head_pitch,
            "left_arm": left_arm,
            "right_arm": right_arm,
            "tail": tail
        }
