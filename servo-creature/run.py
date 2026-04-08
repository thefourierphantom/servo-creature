import random
import time

from creature.config_loader import load_json
from creature.hardware import make_i2c, make_mpu, make_kit
from creature.imu import IMUReader
from creature.servo_controller import ServoController
from creature.mapper import TiltMapper
from creature.animations import AnimationPlayer
from creature.scoring import ScoreSystem
from creature.ui import show_menu


def puppet_mode(imu, mapper, servos):
    print("Puppet Mode running. Press Ctrl+C to return.")
    try:
        while True:
            roll, pitch = imu.read_tilt()
            targets = mapper.puppet_targets(roll, pitch)
            servos.write_many(targets, max_step=5)
            print(f"roll={roll:6.2f} pitch={pitch:6.2f}", end="\r", flush=True)
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nReturning to menu...")
        servos.neutral_pose()


def challenge_mode(imu, mapper, servos, score, rules):
    print("Challenge Mode running. Press Ctrl+C to return.")
    score.reset()

    targets = [
        ("LEFT", -20, 0),
        ("RIGHT", 20, 0),
        ("UP", 0, -15),
        ("DOWN", 0, 15)
    ]

    hit_window = rules["challenge"]["hit_window_deg"]

    try:
        while True:
            label, target_roll, target_pitch = random.choice(targets)
            print(f"\nTarget: {label}")

            start = time.time()
            success = False

            while time.time() - start < 3.0:
                roll, pitch = imu.read_tilt()
                servo_targets = mapper.puppet_targets(roll, pitch)
                servos.write_many(servo_targets, max_step=5)

                if abs(roll - target_roll) <= hit_window and abs(pitch - target_pitch) <= hit_window:
                    score.register_hit("challenge")
                    print(f"Hit! Score: {score.score}")
                    success = True
                    break

                time.sleep(0.02)

            if not success:
                score.register_miss("challenge")
                print(f"Miss! Score: {score.score}")

    except KeyboardInterrupt:
        print("\nReturning to menu...")
        servos.neutral_pose()


def boss_mode(imu, mapper, servos, score, anims, rules):
    print("Boss Mode running. Press Ctrl+C to return.")
    score.reset()
    hit_window = rules["boss"]["hit_window_deg"]
    tick = 0

    try:
        while True:
            roll, pitch = imu.read_tilt()

            # Boss mode fights back a little
            resistant_roll = -0.6 * roll
            boosted_pitch = 1.2 * pitch

            targets = mapper.puppet_targets(resistant_roll, boosted_pitch)
            servos.write_many(targets, max_step=4)

            if abs(roll) > 18 and abs(pitch) > 10:
                score.register_hit("boss")
                print(f"\nBoss combo! Score: {score.score}")
                anims.play("celebrate")

            if tick % 200 == 0:
                anims.play(random.choice(["scan", "sad", "wave"]))

            tick += 1
            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nReturning to menu...")
        servos.neutral_pose()


def main():
    servo_data = load_json("config/servos.json")
    mode_data = load_json("config/modes.json")
    animation_data = load_json("config/animations.json")
    score_rules = load_json("config/score_rules.json")

    i2c = make_i2c()
    mpu = make_mpu(i2c)
    kit = make_kit(channels=servo_data["pca9685"]["channels"])

    imu = IMUReader(mpu)
    servos = ServoController(kit, servo_data["servos"])
    mapper = TiltMapper(servo_data["servos"])
    anims = AnimationPlayer(servos, animation_data)
    score = ScoreSystem(score_rules)

    servos.neutral_pose()
    print("Hold the MPU6050 level for 2 seconds...")
    imu.calibrate_level()
    print("Calibration complete.")

    while True:
        choice = show_menu()

        if choice == "1":
            puppet_mode(imu, mapper, servos)
        elif choice == "2":
            challenge_mode(imu, mapper, servos, score, score_rules)
        elif choice == "3":
            boss_mode(imu, mapper, servos, score, anims, score_rules)
        elif choice == "4":
            anims.play("celebrate")
        elif choice == "5":
            anims.play("sad")
        elif choice == "6":
            anims.play("scan")
        elif choice == "7":
            anims.play("wave")
        elif choice == "8":
            servos.neutral_pose()
            print("Neutral pose applied.")
        elif choice == "9":
            print("Recalibrating...")
            imu.calibrate_level()
            print("Calibration complete.")
        elif choice == "0":
            servos.neutral_pose()
            print("Exiting.")
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
