"""
input/controller_input.py — Tilt Trial Arena / Mission Breach
Handles 8BitDo Zero 2 over Bluetooth (via pygame.joystick) with full
keyboard fallback so the game is always playable without a controller.

Usage pattern:
    # once per frame in the pygame event loop:
    for event in pygame.event.get():
        controller.process_event(event)

    actions = controller.consume_events()   # list[str] e.g. ["start", "a"]

    # in mock mode, poll keyboard arrow-key tilt override:
    if mock:
        tilt = controller.get_tilt_override()
"""

import pygame
from src.util.logger import get_logger

logger = get_logger("controller")


# ── Action → label maps ───────────────────────────────────────────────────────

# Keyboard → action  (keyboard fallback always active)
_KEY_MAP = {
    pygame.K_RETURN:    "start",
    pygame.K_ESCAPE:    "select",
    pygame.K_SPACE:     "a",
    pygame.K_BACKSPACE: "b",
    pygame.K_r:         "recalibrate",
    pygame.K_p:         "pause",
    pygame.K_d:         "debug",
    pygame.K_F1:        "mode_freeplay",
    pygame.K_F2:        "mode_reflex",
    pygame.K_q:         "quit",
}

# Arrow keys drive mock tilt (handled separately via held-key state)
_TILT_KEYS = {pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN}

# Default 8BitDo Zero 2 button indices (SDL2 / Linux HID mode)
# These can be overridden in hardware.yaml: controller.btn_*
_DEFAULT_BTN = {
    "start":  7,
    "select": 6,
    "a":      0,
    "b":      1,
    "x":      3,
    "y":      4,
    "lb":     4,
    "rb":     5,
}

_MOCK_TILT_SPEED = 45.0   # degrees when arrow key held


class ControllerInput:
    """
    Wraps joystick and keyboard into a unified action queue.
    All interaction is event-driven; no polling of hardware state.
    """

    def __init__(self, hw_cfg: dict = None) -> None:
        hw_cfg        = hw_cfg or {}
        self._joystick = None
        self._event_queue: list = []
        self._held_keys: set    = set()
        self._available = False

        # Build button → action map from config (with defaults)
        self._btn_map: dict[int, str] = {}
        for action, default_idx in _DEFAULT_BTN.items():
            key     = f"btn_{action}"
            idx     = hw_cfg.get(key, default_idx)
            self._btn_map[int(idx)] = action

    def init(self) -> None:
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        if count > 0:
            self._joystick = pygame.joystick.Joystick(0)
            self._joystick.init()
            self._available = True
            logger.info("Controller: '%s'", self._joystick.get_name())
        else:
            logger.info("No controller detected — keyboard fallback active")

    # ── Per-frame event ingestion ─────────────────────────────────────────────

    def process_event(self, event: pygame.event.Event) -> None:
        """Feed every pygame event here each frame."""
        self._event_queue.append(event)

        if event.type == pygame.KEYDOWN:
            self._held_keys.add(event.key)
        elif event.type == pygame.KEYUP:
            self._held_keys.discard(event.key)

    def consume_events(self) -> list[str]:
        """
        Drain the event queue and return a list of action strings.
        Clears the queue after reading.
        """
        actions: list[str] = []

        for event in self._event_queue:
            # Keyboard actions
            if event.type == pygame.KEYDOWN:
                action = _KEY_MAP.get(event.key)
                if action:
                    actions.append(action)

            # Joystick buttons
            elif event.type == pygame.JOYBUTTONDOWN and self._available:
                action = self._btn_map.get(event.button)
                if action:
                    actions.append(action)

            # D-pad (hat) as directional tilt prompts (optional override)
            elif event.type == pygame.JOYHATMOTION and self._available:
                hx, hy = event.value
                if hx == -1: actions.append("tilt_left")
                if hx ==  1: actions.append("tilt_right")
                if hy ==  1: actions.append("tilt_up")
                if hy == -1: actions.append("tilt_down")

        self._event_queue.clear()
        return actions

    # ── Mock-mode tilt override ───────────────────────────────────────────────

    def get_tilt_override(self) -> dict | None:
        """
        Returns a tilt dict driven by arrow keys, or None if no keys held.
        Only used in mock mode.
        """
        roll  = 0.0
        pitch = 0.0
        active = False

        if pygame.K_LEFT  in self._held_keys: roll  = -_MOCK_TILT_SPEED; active = True
        if pygame.K_RIGHT in self._held_keys: roll  =  _MOCK_TILT_SPEED; active = True
        if pygame.K_UP    in self._held_keys: pitch = -_MOCK_TILT_SPEED; active = True
        if pygame.K_DOWN  in self._held_keys: pitch =  _MOCK_TILT_SPEED; active = True

        if not active:
            return None
        return {"roll": roll, "pitch": pitch, "accel_mag": 1.0}

    def is_available(self) -> bool:
        return self._available
