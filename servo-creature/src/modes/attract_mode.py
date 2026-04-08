"""
modes/attract_mode.py — cleaner arcade attract screen.
ENTER goes straight into Reflex. F1 is the gentle freeplay path.
"""

from src.core.game_state import GameMode


class AttractMode:
    def __init__(self, gs, game_cfg: dict, prompt_cfg: dict) -> None:
        self.gs = gs

    def enter(self) -> None:
        self.gs.session_active = False
        self.gs.prompt = ""
        self.gs.status_message = "ENTER start · F1 freeplay · F2 reflex · F3 boss"
        self.gs.idle_timer = 0.0
        self.gs.player_detected = False

    def exit(self) -> None:
        self.gs.status_message = ""

    def update(self, dt: float, tilt: dict, actions: list):
        if abs(tilt.get("roll", 0.0)) > 10.0 or abs(tilt.get("pitch", 0.0)) > 10.0:
            self.gs.player_detected = True
            self.gs.idle_timer = 0.0

        for action in actions:
            if action in ("start", "a", "mode_reflex"):
                return GameMode.REFLEX
            if action == "mode_freeplay":
                return GameMode.FREEPLAY
            if action == "mode_boss":
                return GameMode.BOSS
        return None