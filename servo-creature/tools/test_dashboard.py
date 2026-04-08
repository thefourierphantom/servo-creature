#!/usr/bin/env python3
"""
tools/test_dashboard.py — Dashboard display standalone test
Renders the Pygame dashboard with a fully fake GameState that animates
through different modes/values, so you can verify layout on any screen.

Usage:
    python tools/test_dashboard.py
    python tools/test_dashboard.py --fullscreen
    python tools/test_dashboard.py --width 1920 --height 1080

Press  ← →  to cycle scenes,  Q  to quit.
"""

import sys
import os
import math
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pygame
from src.util.logger import setup_logger
from src.core.game_state import GameState, GameMode
from src.output.dashboard_display import DashboardDisplay

setup_logger("test_dashboard")

parser = argparse.ArgumentParser()
parser.add_argument("--width",      type=int, default=1280)
parser.add_argument("--height",     type=int, default=720)
parser.add_argument("--fullscreen", action="store_true")
args = parser.parse_args()

pygame.init()
flags  = pygame.FULLSCREEN if args.fullscreen else 0
screen = pygame.display.set_mode((args.width, args.height), flags)
pygame.display.set_caption("Dashboard Test")
clock  = pygame.time.Clock()

game_cfg = {
    "fps": 60,
    "display": {"width": args.width, "height": args.height},
    "tilt":    {"threshold_deg": 25.0, "deadzone_deg": 3.0},
    "reflex":  {"prompt_duration_sec": 2.5},
    "ui":      {"result_display_ms": 600},
    "scoring": {},
}

dash = DashboardDisplay(screen, game_cfg)
gs   = GameState()
t    = 0.0
scene = 0

SCENES = [
    "attract",
    "freeplay",
    "reflex_active",
    "reflex_hit",
    "reflex_miss",
    "boss_active",
    "boss_inverted",
    "calibrating",
    "paused",
]

def setup_scene(gs, name, t):
    gs.tilt = {
        "roll":  math.sin(t * 0.8) * 38.0,
        "pitch": math.cos(t * 0.55) * 28.0,
        "accel_mag": 1.0,
    }
    if name == "attract":
        gs.mode = GameMode.ATTRACT
        gs.player_detected = (int(t) % 8) > 4
    elif name == "freeplay":
        gs.mode = GameMode.FREEPLAY
        gs.session_active = False
    elif name == "reflex_active":
        gs.mode           = GameMode.REFLEX
        gs.session_active = True
        gs.score          = 1450
        gs.combo          = 4
        gs.hits           = 9
        gs.misses         = 2
        gs.timer          = 34.7
        gs.threat_level   = 1
        gs.prompt         = "← LEFT"
        gs.prompt_timer   = 2.5 - (t % 2.5)
        gs._prompt_index  = 10
        gs._prompt_total  = 15
        gs.last_prompt_result = ""
        gs.calibrated     = True
    elif name == "reflex_hit":
        gs.mode           = GameMode.REFLEX
        gs.session_active = True
        gs.score          = 2600
        gs.combo          = 7
        gs.hits           = 13
        gs.misses         = 1
        gs.timer          = 52.1
        gs.threat_level   = 0
        gs.prompt         = "↑ UP"
        gs.prompt_timer   = 1.2
        gs.last_prompt_result = "HIT"
        gs.result_flash_timer = 0.15
        gs.calibrated = True
    elif name == "reflex_miss":
        gs.mode = GameMode.REFLEX
        gs.session_active = True
        gs.score = 800; gs.combo = 0; gs.hits = 4; gs.misses = 5
        gs.threat_level = 3; gs.timer = 28.0
        gs.prompt = "↓ DOWN"; gs.prompt_timer = 0.0
        gs.last_prompt_result = "MISS"; gs.result_flash_timer = 0.25
        gs.calibrated = True
    elif name == "boss_active":
        gs.mode = GameMode.BOSS
        gs.session_active = True
        gs.score = 3900; gs.combo = 3; gs.hits = 8; gs.misses = 4
        gs.threat_level = 3; gs.timer = 47.3
        gs.prompt = "⚡ FULL TILT"; gs.prompt_timer = 0.8
        gs.last_prompt_result = ""; gs.axis_inverted = False
        gs.calibrated = True
    elif name == "boss_inverted":
        gs.mode = GameMode.BOSS; gs.session_active = True
        gs.score = 4100; gs.combo = 2; gs.hits = 9; gs.misses = 6
        gs.threat_level = 4; gs.timer = 61.0
        gs.prompt = "← LEFT"; gs.prompt_timer = 1.1
        gs.axis_inverted = True
        gs.last_prompt_result = "FAKE"
        gs.result_flash_timer = 0.2
        gs.calibrated = True
    elif name == "calibrating":
        gs.mode = GameMode.CALIBRATING; gs.session_active = False
    elif name == "paused":
        gs.mode = GameMode.PAUSED; gs.session_active = True

print("Scene cycling test.  ← → to change, Q to quit.\n")

running = True
while running:
    dt = clock.tick(60) / 1000.0
    t += dt
    gs.attract_tick = t

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                running = False
            if event.key == pygame.K_RIGHT:
                scene = (scene + 1) % len(SCENES)
            if event.key == pygame.K_LEFT:
                scene = (scene - 1) % len(SCENES)

    setup_scene(gs, SCENES[scene], t)
    pygame.display.set_caption(f"Dashboard Test — scene {scene+1}/{len(SCENES)}: {SCENES[scene]}")
    dash.render(gs)
    pygame.display.flip()

pygame.quit()
print("[OK] Dashboard test complete.")
