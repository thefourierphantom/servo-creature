#!/usr/bin/env python3
"""
tools/test_controller.py — 8BitDo Zero 2 / keyboard controller test
Opens a Pygame window and prints every action emitted by ControllerInput.

Usage:
    python tools/test_controller.py
    (no --mock flag needed — keyboard is always available)

Press Q or close the window to exit.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pygame
from src.util.logger import setup_logger
from src.input.controller_input import ControllerInput

setup_logger("test_controller")

pygame.init()
screen = pygame.display.set_mode((640, 360))
pygame.display.set_caption("Controller Test — press keys / buttons")
clock  = pygame.time.Clock()
font   = pygame.font.SysFont("monospace", 20)

ctrl = ControllerInput()
ctrl.init()

print("=" * 50)
print("  Controller / Keyboard Input Test")
print("=" * 50)
print(f"Controller connected: {ctrl.is_available()}")
print("Actions will be printed here and shown on screen.\n")

BLACK  = (0,   0,   0)
GREEN  = (50, 220, 80)
CYAN   = (0,  220, 180)
GREY   = (120, 130, 150)
history = []

running = True
while running:
    clock.tick(60)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        ctrl.process_event(event)

    actions = ctrl.consume_events()
    for a in actions:
        if a == "quit":
            running = False
        history.append(a)
        print(f"  ACTION: {a}")
    history = history[-12:]   # keep last 12

    # Mock tilt
    tilt = ctrl.get_tilt_override()

    screen.fill(BLACK)
    screen.blit(font.render("Controller / Keyboard Test", True, CYAN), (20, 18))
    screen.blit(font.render(
        f"Controller: {'CONNECTED' if ctrl.is_available() else 'keyboard only'}",
        True, GREEN if ctrl.is_available() else GREY
    ), (20, 52))

    if tilt:
        screen.blit(font.render(
            f"Tilt override: roll={tilt['roll']:+.0f}  pitch={tilt['pitch']:+.0f}",
            True, (255, 180, 0)
        ), (20, 82))

    screen.blit(font.render("Recent actions:", True, GREY), (20, 118))
    for i, a in enumerate(reversed(history)):
        alpha = max(80, 255 - i * 18)
        col   = (alpha, min(255, alpha + 50), alpha)
        screen.blit(font.render(f"  {a}", True, col), (20, 142 + i * 22))

    screen.blit(font.render("[Q] Quit", True, GREY), (20, 330))
    pygame.display.flip()

pygame.quit()
print("\n[OK] Controller test complete.")
