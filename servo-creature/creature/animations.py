import time

class AnimationPlayer:
    def __init__(self, servo_controller, animations):
        self.servos = servo_controller
        self.animations = animations

    def play(self, name, step_sleep=0.02):
        if name not in self.animations:
            print(f"Animation '{name}' not found")
            return

        frames = self.animations[name]
        start = time.time()
        index = 0

        while index < len(frames):
            elapsed = time.time() - start
            if elapsed >= frames[index]["t"]:
                pose = {k: v for k, v in frames[index].items() if k != "t"}
                self.servos.write_many(pose, max_step=8)
                index += 1
            time.sleep(step_sleep)

