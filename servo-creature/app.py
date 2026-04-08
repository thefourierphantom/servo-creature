#!/usr/bin/env python3
"""
app.py — Tilt Trial Arena / Mission Breach
──────────────────────────────────────────
Core build: MPU6050 wand + HDMI monitor + keyboard.
No other hardware is required.

Keyboard:
  ENTER / Space → Testing Ground / confirm
  ESC           → Back to attract
  F2            → Reflex mode
  F3            → Boss mode
  R             → Recalibrate MPU6050
  D             → Toggle debug overlay
  Arrow keys    → Simulate tilt (mock mode)
  Q             → Quit

Run:
  python app.py                  # reads config/hardware.yaml
  python app.py --mock           # force mock mode (laptop dev)
  MOCK_HARDWARE=1 python app.py  # same via env var
  python app.py --fullscreen     # kiosk mode
"""

import os
import sys
import time
import argparse
import yaml
import pygame

sys.path.insert(0, os.path.dirname(__file__))

from src.util.logger     import setup_logger, get_logger
from src.util.calibration import load_calibration

from src.core.game_state import GameState, GameMode
from src.core.scoring    import ScoreEngine

from src.input.mpu6050_input    import create_mpu6050
from src.input.controller_input import ControllerInput

from src.output.dashboard_display import DashboardDisplay

from src.modes.attract_mode      import AttractMode
from src.modes.freeplay_mode     import FreeplayMode
from src.modes.reflex_mode       import ReflexMode
from src.modes.boss_mode         import BossMode
from src.modes.calibration_mode  import CalibrationMode


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path: str) -> dict:
    try:
        with open(path, "r") as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"[WARN] {path}: {exc}")
        return {}


def _fps_smooth(prev: float, measured: float, alpha: float = 0.1) -> float:
    return prev + alpha * (measured - prev)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="NSBE Radar Chaser")
    parser.add_argument("--mock",       action="store_true")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--config",     default="config/hardware.yaml")
    args = parser.parse_args()

    # ── Logging ───────────────────────────────────────────────────────────────
    setup_logger("tilt_arena")
    log = get_logger("main")
    log.info("═══ NSBE Radar Chaser ═══")

    # ── Config ────────────────────────────────────────────────────────────────
    hw_cfg     = _load(args.config)
    game_cfg   = _load("config/game.yaml")
    prompt_cfg = _load("config/prompts.yaml")

    mock = args.mock or bool(os.environ.get("MOCK_HARDWARE")) or hw_cfg.get("mock_mode", False)
    if mock:
        log.info("MOCK MODE — all hardware simulated")

    # ── Pygame ────────────────────────────────────────────────────────────────
    pygame.init()

    disp   = game_cfg.get("display", {})
    W      = int(disp.get("width",  1280))
    H      = int(disp.get("height",  720))
    full   = args.fullscreen or disp.get("fullscreen", False)
    flags  = pygame.FULLSCREEN if full else 0
    screen = pygame.display.set_mode((W, H), flags)
    pygame.display.set_caption("NSBE Radar Chaser")

    target_fps      = int(game_cfg.get("fps", 30))
    mpu_poll_hz     = float(game_cfg.get("mpu_poll_hz", 20))
    mpu_interval    = 1.0 / mpu_poll_hz

    clock           = pygame.time.Clock()
    log.info("Display %dx%d  fps=%d  mpu_poll_hz=%.0f  mock=%s",
             W, H, target_fps, mpu_poll_hz, mock)

    # ── Hardware ──────────────────────────────────────────────────────────────
    mpu_cfg = hw_cfg.get("mpu6050", {})
    mpu     = create_mpu6050(mpu_cfg, mock=mock)

    cal_data = load_calibration()
    if hasattr(mpu, "apply_calibration"):
        mpu.apply_calibration(cal_data)

    controller = ControllerInput(hw_cfg.get("controller", {}))
    controller.init()

    # ── Game state ────────────────────────────────────────────────────────────
    gs              = GameState()
    gs.calibrated   = cal_data.get("calibrated", False)
    score_engine    = ScoreEngine(gs, game_cfg)

    # Expose threshold to dashboard via game_cfg (dashboard reads from cfg)
    game_cfg["mpu6050"] = mpu_cfg   # make MPU config visible to dashboard

    # ── Modes ─────────────────────────────────────────────────────────────────
    cal_mode = CalibrationMode(gs, mpu, game_cfg)

    mode_map = {
        GameMode.ATTRACT:     AttractMode(gs, game_cfg, prompt_cfg),
        GameMode.FREEPLAY:    FreeplayMode(gs, game_cfg, prompt_cfg, score_engine),
        GameMode.REFLEX:      ReflexMode(gs, game_cfg, prompt_cfg, score_engine),
        GameMode.BOSS:        BossMode(gs, game_cfg, prompt_cfg, score_engine),
        GameMode.CALIBRATING: cal_mode,
    }

    dashboard  = DashboardDisplay(screen, game_cfg)
    cur_mode   = mode_map[GameMode.ATTRACT]
    cur_mode.enter()

    # ── Loop state ────────────────────────────────────────────────────────────
    running        = True
    last_mpu_time  = 0.0
    last_tilt      = {"roll": 0.0, "pitch": 0.0, "accel_mag": 1.0,
                      "raw_roll": 0.0, "raw_pitch": 0.0}
    smooth_fps     = float(target_fps)

    log.info("Game loop starting …")

    while running:
        dt        = clock.tick(target_fps) / 1000.0
        now       = time.monotonic()
        smooth_fps = _fps_smooth(smooth_fps, 1.0 / max(dt, 0.001))

        # ── Pygame event processing ───────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            controller.process_event(event)

        actions = controller.consume_events()

        if "quit" in actions:
            running = False
            continue

        # ── Global toggles (always active) ────────────────────────────────
        if "debug" in actions:
            gs.debug_mode = not gs.debug_mode
            actions = [a for a in actions if a != "debug"]

        # ── MPU poll (rate-limited independently of render) ───────────────
        if now - last_mpu_time >= mpu_interval:
            raw_tilt = mpu.read()

            # In mock mode: keyboard arrow keys override tilt
            if mock:
                override = controller.get_tilt_override()
                if override:
                    raw_tilt = override
                    if hasattr(mpu, "set_manual"):
                        mpu.set_manual(override["roll"], override["pitch"])
                elif hasattr(mpu, "clear_manual"):
                    mpu.clear_manual()

            last_tilt      = raw_tilt
            last_mpu_time  = now

            # Feed one raw sample to calibration mode if active
            if gs.mode == GameMode.CALIBRATING:
                desired = cal_mode.update(dt, last_tilt, actions)
                if desired and desired != gs.mode:
                    cur_mode.exit()
                    gs.transition(desired)
                    cur_mode = mode_map.get(desired, mode_map[GameMode.ATTRACT])
                    cur_mode.enter()
                # Don't run the normal mode update during calibration
                gs.tilt = last_tilt
                _tick_timers(gs, dt)
                dashboard.render(gs, cal_mode=cal_mode, fps=smooth_fps)
                pygame.display.flip()
                continue

        gs.tilt = last_tilt

        # ── Recalibrate action (R key) ────────────────────────────────────
        if "recalibrate" in actions and gs.mode != GameMode.CALIBRATING:
            cur_mode.exit()
            gs.transition(GameMode.CALIBRATING)
            total = int(mpu_cfg.get("calibration_samples", 150))
            cal_mode.enter(total_samples=total)
            cur_mode = mode_map[GameMode.CALIBRATING]
            actions  = [a for a in actions if a != "recalibrate"]

        # ── Mode update ───────────────────────────────────────────────────
        desired = cur_mode.update(dt, last_tilt, actions)

        if desired and desired != gs.mode:
            cur_mode.exit()
            gs.transition(desired)
            cur_mode = mode_map.get(desired, mode_map[GameMode.ATTRACT])
            cur_mode.enter()

        # ── Tick global timers ────────────────────────────────────────────
        _tick_timers(gs, dt)

        # ── Render ────────────────────────────────────────────────────────
        dashboard.render(gs, cal_mode=None, fps=smooth_fps)
        pygame.display.flip()

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("Shutting down …")
    pygame.quit()
    if not mock:
        try:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
        except Exception:
            pass
    log.info("Done.")


def _tick_timers(gs: GameState, dt: float) -> None:
    """Decrement all per-frame countdown timers in GameState."""
    if gs.session_active:
        gs.timer += dt
    gs.result_flash_timer  = max(0.0, gs.result_flash_timer  - dt)
    gs.result_hold_timer   = max(0.0, gs.result_hold_timer   - dt)
    gs.score_delta_timer   = max(0.0, gs.score_delta_timer   - dt)
    gs.attract_tick       += dt
    gs.idle_timer         += dt


if __name__ == "__main__":
    main()
