
from creature.safety import clamp, slew_limit

class ServoController:
    def __init__(self, kit, servo_config):
        self.kit = kit
        self.servo_config = servo_config
        self.current_angles = {}

        for name, cfg in servo_config.items():
            servo = self.kit.servo[cfg["channel"]]
            servo.actuation_range = cfg.get("actuation_range", 180)
            servo.set_pulse_width_range(
                cfg.get("min_pulse", 500),
                cfg.get("max_pulse", 2500)
            )
            self.current_angles[name] = cfg["neutral_angle"]

    def _apply_reverse(self, name, angle):
        if self.servo_config[name].get("reversed", False):
            return 180 - angle
        return angle

    def write(self, name, angle, max_step=None):
        cfg = self.servo_config[name]
        angle = clamp(angle, cfg["min_angle"], cfg["max_angle"])

        if max_step is not None:
            angle = slew_limit(self.current_angles[name], angle, max_step)

        self.kit.servo[cfg["channel"]].angle = self._apply_reverse(name, angle)
        self.current_angles[name] = angle

    def write_many(self, angles: dict, max_step=None):
        for name, angle in angles.items():
            if name in self.servo_config:
                self.write(name, angle, max_step=max_step)

    def neutral_pose(self):
        for name, cfg in self.servo_config.items():
            self.write(name, cfg["neutral_angle"])

