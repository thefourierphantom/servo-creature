"""
modes/attract_mode.py — Tilt Trial Arena
ENTER → Testing Ground.  F2 → Endless Reflex.
"""

from src.core.game_state import GameMode


class AttractMode:
    def __init__(self, gs, game_cfg: dict, prompt_cfg: dict) -> None:
        self.gs = gs

    def enter(self) -> None:
        self.gs.session_active = False
        self.gs.prompt         = ""
        self.gs.status_message = "ENTER testing ground  ·  F2 endless reflex"
        self.gs.idle_timer     = 0.0

    def exit(self) -> None:
        self.gs.status_message = ""

    def update(self, dt: float, tilt: dict, actions: list):
        for action in actions:
            if action in ("start", "a", "mode_freeplay"):
                return GameMode.FREEPLAY
            if action == "mode_reflex":
                return GameMode.REFLEX
        return None
