"""
output/dashboard_display.py — Tilt Trial Arena / Mission Breach
Pi-optimised Pygame HUD  ·  Future-Tech space aesthetic

Performance strategy:
  • Static backgrounds pre-rendered to a Surface once per mode change (single blit/frame).
  • Dynamic text cached via _Cached — re-rendered only when the value changes.
  • No per-frame alpha Surface allocation (SRCALPHA kept as a reusable slot).
  • Draw-call budget ≈ 15–25 ops/frame.  Target: 30 fps on Pi 3B+ @ 1280×720.

Layout (1280×720):
  ┌──────────────────────────────────────────────────────┐
  │ TOP BAR (0–72):  [MODE]   Title   SCORE  COMBO  FPS  │
  ├──────────────────────────────────────────────────────┤
  │ MAIN (72–620):                                        │
  │  Left 300 px : tilt visualiser (crosshair + bars)   │
  │  Centre 680 px: prompt / mode content (huge text)   │
  │  Right 300 px : session stats                        │
  ├──────────────────────────────────────────────────────┤
  │ BOTTOM (620–720): timer · controls hint · cal status │
  └──────────────────────────────────────────────────────┘
"""

import math
import random
import time
import pygame
from src.util.logger import get_logger

logger = get_logger("dashboard")

# ── Palette — Future-Tech deep-space ──────────────────────────────────────────
C_BG      = (6,   8,  24)          # near-black navy
C_PANEL   = (10,  14,  38)          # panel bg
C_PANEL2  = (14,  20,  52)          # slightly lighter
C_BORDER  = (35,  90, 200)          # neon blue border
C_GRID    = (10,  16,  36)          # grid lines

C_TEAL    = (0,   210, 220)         # bright cyan-teal
C_ORANGE  = (255, 140,   0)
C_RED     = (210,  20,  20)
C_GREEN   = (45,  210,  75)
C_YELLOW  = (255, 205,   0)
C_PURPLE  = (180,  80, 255)
C_BLUE    = (55,  155, 255)
C_WHITE   = (225, 235, 255)         # slightly blue-white
C_GREY    = (120, 140, 175)
C_DIM     = (55,   68,  105)
C_GOLD    = (255, 215,   0)

# Glow tints (used when drawing glow halos around shapes)
C_GLOW_BLUE   = (30,  80, 200, 55)
C_GLOW_TEAL   = (0,  200, 220, 45)
C_GLOW_PURPLE = (140, 50, 255, 40)

# Mode accent colours
MODE_COLOR = {
    "ATTRACT":     C_TEAL,
    "FREEPLAY":    C_BLUE,
    "REFLEX":      C_ORANGE,
    "CALIBRATING": C_YELLOW,
    "PAUSED":      C_YELLOW,
}

# Prompt word → colour
PROMPT_COLOR = {
    "LEFT":    C_BLUE,
    "RIGHT":   C_BLUE,
    "UP":      C_GREEN,
    "DOWN":    C_RED,
    "HOLD":    C_YELLOW,
    "FREEZE":  C_PURPLE,
    "SHAKE":   C_ORANGE,
    "FULL":    (255,  60, 160),
    "NOSE":    C_TEAL,
    "DODGE":   C_ORANGE,
    "DEFAULT": C_WHITE,
}

RESULT_COLOR = {"HIT": C_GREEN, "MISS": C_RED, "FAKE": C_ORANGE}

THREAT_COLOR = [
    (30,  180,  70),
    (80,  200,  40),
    (210, 195,   0),
    (255, 130,   0),
    (210,  35,   0),
    (190,   0,   0),
]


# ── Tiny value-change cache ───────────────────────────────────────────────────

class _Cached:
    """Renders a Surface only when the string value changes."""
    __slots__ = ("_prev", "_surf", "_font", "_color")

    def __init__(self, font: pygame.font.Font, color: tuple) -> None:
        self._font  = font
        self._color = color
        self._prev  = None
        self._surf  = None

    def get(self, text: str) -> pygame.Surface:
        if text != self._prev:
            self._surf = self._font.render(text, True, self._color)
            self._prev = text
        return self._surf

    def set_color(self, color: tuple) -> None:
        if color != self._color:
            self._color = color
            self._prev  = None   # force re-render next call


# ── Helpers ───────────────────────────────────────────────────────────────────

def _glow_rect(surface: pygame.Surface, color: tuple, rect, radius: int = 6,
               glow_alpha: int = 50, glow_expand: int = 8) -> None:
    """Draw a filled rect with a soft outer glow ring (SRCALPHA)."""
    x, y, w, h = rect
    gx = x - glow_expand
    gy = y - glow_expand
    gw = w + glow_expand * 2
    gh = h + glow_expand * 2
    gs = pygame.Surface((gw, gh), pygame.SRCALPHA)
    gc = (color[0], color[1], color[2], glow_alpha)
    pygame.draw.rect(gs, gc, (0, 0, gw, gh), border_radius=radius + glow_expand)
    surface.blit(gs, (gx, gy))
    pygame.draw.rect(surface, color, rect, border_radius=radius)


def _glow_text(surface: pygame.Surface, font: pygame.font.Font,
               text: str, color: tuple, pos: tuple,
               glow_color: tuple | None = None, glow_r: int = 2) -> None:
    """Blit text with a 1-px multi-direction drop-shadow glow."""
    gc = glow_color or (min(255, color[0]//2), min(255, color[1]//2), min(255, color[2]//2))
    ghost = font.render(text, True, gc)
    x, y = pos
    for dx in (-glow_r, 0, glow_r):
        for dy in (-glow_r, 0, glow_r):
            if dx != 0 or dy != 0:
                surface.blit(ghost, (x + dx, y + dy))
    surface.blit(font.render(text, True, color), pos)


# ── Main class ────────────────────────────────────────────────────────────────

class DashboardDisplay:

    _TOP_H  = 72
    _BOT_H  = 82
    _LEFT_W = 295
    _RGT_W  = 295

    def __init__(self, screen: pygame.Surface, game_cfg: dict) -> None:
        self._screen   = screen
        self._W, self._H = screen.get_size()
        self._cfg      = game_cfg
        self._show_fps = game_cfg.get("show_fps", True)
        self._t        = 0.0
        self._fps_val  = 0.0
        self._last_mode: str = ""
        self._bg_surf: pygame.Surface | None = None

        # Persistent star seed so stars don't regenerate every frame
        self._star_seed = 42

        # Layout derived values
        self._MID_Y  = self._TOP_H
        self._MID_H  = self._H - self._TOP_H - self._BOT_H
        self._CX     = self._LEFT_W
        self._CW     = self._W - self._LEFT_W - self._RGT_W
        self._RX     = self._W - self._RGT_W
        self._BOT_Y  = self._H - self._BOT_H

        # ── Font resolution — prefer rounded sans-serif for the space-tech look
        pygame.font.init()

        def _best_font(size: int, bold: bool = False) -> pygame.font.Font:
            candidates = ["impact", "ubuntubold", "ubuntu", "freesansbold",
                          "freesans", "liberationsans", "dejavusans", "monospace"]
            if bold:
                candidates = ["impact", "ubuntubold", "freesansbold",
                               "liberationsansbold", "dejavusansbold"] + candidates
            for name in candidates:
                path = pygame.font.match_font(name, bold=bold)
                if path:
                    try:
                        return pygame.font.Font(path, size)
                    except Exception:
                        pass
            return pygame.font.SysFont("monospace", size, bold=bold)

        self._f_score  = _best_font(52, bold=True)
        self._f_prompt = _best_font(108, bold=True)
        self._f_result = _best_font(72,  bold=True)
        self._f_lg     = _best_font(42,  bold=True)
        self._f_md     = _best_font(30,  bold=True)
        self._f_sm     = _best_font(21)
        self._f_xs     = _best_font(17)
        self._f_title  = _best_font(28,  bold=True)

        # ── Cached text surfaces
        self._c_score  = _Cached(self._f_score, C_WHITE)
        self._c_combo  = _Cached(self._f_lg,    C_GOLD)
        self._c_mult   = _Cached(self._f_xs,    C_DIM)
        self._c_timer  = _Cached(self._f_md,    C_TEAL)
        self._c_acc    = _Cached(self._f_md,    C_GREEN)
        self._c_hits   = _Cached(self._f_sm,    C_GREEN)
        self._c_misses = _Cached(self._f_sm,    C_RED)
        self._c_prompt = _Cached(self._f_prompt, C_WHITE)
        self._c_fps    = _Cached(self._f_xs,    C_DIM)

        # Reusable SRCALPHA surface for flashes
        self._flash = pygame.Surface((self._W, self._H), pygame.SRCALPHA)

        logger.info("DashboardDisplay  %dx%d  (Future-Tech skin)", self._W, self._H)

    # ── Public ────────────────────────────────────────────────────────────────

    def render(self, gs, cal_mode=None, fps: float = 0.0) -> None:
        """Main render call — once per frame."""
        self._t      += 0.016
        self._fps_val = fps

        if gs.mode.name != self._last_mode:
            self._build_bg(gs.mode.name)
            self._last_mode = gs.mode.name

        # Layer 1: pre-rendered static background
        self._screen.blit(self._bg_surf, (0, 0))

        # Layer 2: dynamic elements
        mode = gs.mode.name
        if mode == "CALIBRATING":
            self._draw_calibrating(gs, cal_mode)
        elif mode == "ATTRACT":
            self._draw_attract(gs)
        elif mode == "FREEPLAY":
            self._draw_freeplay(gs)
        elif mode == "REFLEX":
            if gs.game_over:
                self._draw_gameover(gs)
            else:
                self._draw_game(gs)
        elif mode == "PAUSED":
            self._draw_paused(gs)

        self._draw_top_dynamic(gs)

        if gs.debug_mode:
            self._draw_debug(gs)

        self._draw_flash(gs)

        if self._show_fps:
            fps_str = f"FPS:{fps:.0f}"
            self._screen.blit(self._c_fps.get(fps_str),
                              (self._W - 72, self._H - 20))

    # ── Static background builder ─────────────────────────────────────────────

    def _build_bg(self, mode_name: str) -> None:
        """Pre-render every element that does not change frame-to-frame."""
        rng = random.Random(self._star_seed)
        s = pygame.Surface((self._W, self._H))
        s.fill(C_BG)

        # ── Star field ───────────────────────────────────────────────────
        # Tiny dim stars
        for _ in range(180):
            sx = rng.randint(0, self._W)
            sy = rng.randint(0, self._H)
            br = rng.randint(60, 160)
            tint = rng.choice([(br, br, br+20), (br, br+10, br+30), (br+10, br, br+20)])
            pygame.draw.circle(s, tint, (sx, sy), 1)

        # Medium brighter stars
        for _ in range(40):
            sx = rng.randint(0, self._W)
            sy = rng.randint(0, self._H)
            br = rng.randint(160, 220)
            tint = rng.choice([(br, br, 255), (255, 255, br), (br, 255, 255)])
            pygame.draw.circle(s, tint, (sx, sy), 2)

        # 4-point sparkle stars (like in the reference image)
        sparkle_positions = [(rng.randint(0, self._W), rng.randint(0, self._H))
                             for _ in range(14)]
        for (sx, sy) in sparkle_positions:
            bc = rng.choice([C_WHITE, C_TEAL, C_BLUE, (200, 180, 255)])
            arm = rng.choice([5, 7, 9])
            pygame.draw.line(s, bc, (sx - arm, sy), (sx + arm, sy), 1)
            pygame.draw.line(s, bc, (sx, sy - arm), (sx, sy + arm), 1)
            pygame.draw.line(s, bc, (sx - arm//2, sy - arm//2),
                             (sx + arm//2, sy + arm//2), 1)
            pygame.draw.line(s, bc, (sx + arm//2, sy - arm//2),
                             (sx - arm//2, sy + arm//2), 1)
            pygame.draw.circle(s, C_WHITE, (sx, sy), 1)

        # ── Subtle diagonal scan lines ────────────────────────────────────
        scan_col = (12, 18, 45)
        for x in range(-self._H, self._W, 40):
            pygame.draw.line(s, scan_col, (x, 0), (x + self._H, self._H), 1)

        # ── Blue nebula glow at top-centre (planet rim from reference) ────
        glow_surf = pygame.Surface((self._W, 180), pygame.SRCALPHA)
        for r, alpha in [(340, 10), (280, 15), (220, 20), (160, 18), (100, 12)]:
            pygame.draw.ellipse(glow_surf, (30, 90, 220, alpha),
                                (self._W // 2 - r, -r // 2, r * 2, r), 4)
        s.blit(glow_surf, (0, 0))

        # ── Top bar ───────────────────────────────────────────────────────
        mc = MODE_COLOR.get(mode_name, C_TEAL)
        # Gradient strip: draw thin horizontal slices darkening top→bottom
        for i in range(self._TOP_H):
            blend = i / self._TOP_H
            r = int(10 + 4 * blend)
            g = int(14 + 6 * blend)
            b = int(38 + 14 * blend)
            pygame.draw.line(s, (r, g, b), (0, i), (self._W, i))
        # Bottom border of top bar — glowing mode-accent line
        pygame.draw.line(s, mc, (0, self._TOP_H - 2), (self._W, self._TOP_H - 2), 2)
        gline = pygame.Surface((self._W, 6), pygame.SRCALPHA)
        gline.fill((mc[0], mc[1], mc[2], 40))
        s.blit(gline, (0, self._TOP_H - 4))

        # Mode tag
        tag_w = 198
        _glow_rect(s, (int(mc[0]*0.15), int(mc[1]*0.15), int(mc[2]*0.18)),
                   (10, 10, tag_w, 52), radius=6, glow_alpha=40, glow_expand=6)
        pygame.draw.rect(s, mc, (10, 10, tag_w, 52), width=2, border_radius=6)
        tag_surf = self._f_md.render(f"[ {mode_name} ]", True, mc)
        s.blit(tag_surf, (10 + (tag_w - tag_surf.get_width()) // 2,
                          10 + (52 - tag_surf.get_height()) // 2))

        # Title — with glow
        title_text = "NSBE  //  RADAR COMMAND"
        _glow_text(s, self._f_title, title_text, C_WHITE,
                   (self._W // 2 - self._f_title.size(title_text)[0] // 2,
                    self._TOP_H // 2 - self._f_title.size(title_text)[1] // 2),
                   glow_color=(50, 110, 255), glow_r=2)

        # Static label dividers in top bar
        score_lbl = self._f_xs.render("SCORE", True, C_DIM)
        combo_lbl = self._f_xs.render("COMBO", True, C_DIM)
        mult_lbl  = self._f_xs.render("MULT",  True, C_DIM)
        s.blit(score_lbl, (220, 8))
        s.blit(combo_lbl, (450, 8))
        s.blit(mult_lbl,  (620, 8))
        div_col = (30, 50, 100)
        pygame.draw.line(s, div_col, (430, 10), (430, 62), 1)
        pygame.draw.line(s, div_col, (600, 10), (600, 62), 1)

        # ── Bottom bar ────────────────────────────────────────────────────
        for i in range(self._BOT_H):
            blend = 1.0 - i / self._BOT_H
            r = int(8  + 4  * blend)
            g = int(12 + 6  * blend)
            b = int(32 + 14 * blend)
            pygame.draw.line(s, (r, g, b),
                             (0, self._BOT_Y + i), (self._W, self._BOT_Y + i))
        pygame.draw.line(s, mc, (0, self._BOT_Y), (self._W, self._BOT_Y), 2)
        glbot = pygame.Surface((self._W, 6), pygame.SRCALPHA)
        glbot.fill((mc[0], mc[1], mc[2], 35))
        s.blit(glbot, (0, self._BOT_Y))

        hints = ("[ENTER] Testing Ground   [F2] Endless Reflex   "
                 "[R] Recalibrate   [D] Debug   [Q] Quit")
        hint_surf = self._f_xs.render(hints, True, C_DIM)
        s.blit(hint_surf, (self._W // 2 - hint_surf.get_width() // 2,
                           self._BOT_Y + 10))

        # ── Column separators (game modes only) ──────────────────────────
        if mode_name in ("FREEPLAY", "REFLEX"):
            sep_col = (25, 50, 110)
            pygame.draw.line(s, sep_col,
                             (self._CX, self._MID_Y), (self._CX, self._BOT_Y), 1)
            pygame.draw.line(s, sep_col,
                             (self._RX, self._MID_Y), (self._RX, self._BOT_Y), 1)

        self._bg_surf = s

    # ── Top bar (dynamic part) ────────────────────────────────────────────────

    def _draw_top_dynamic(self, gs) -> None:
        scr = self._screen
        # Score
        scr.blit(self._c_score.get(f"{gs.score:,}"), (220, 16))
        # Combo
        combo_col = C_GOLD if gs.combo > 3 else C_WHITE
        self._c_combo.set_color(combo_col)
        scr.blit(self._c_combo.get(f"×{gs.combo}"), (450, 20))
        # Multiplier sub-text
        scr.blit(self._c_mult.get(f"{gs.combo_multiplier:.1f}×"), (628, 24))

        # Threat bar
        tx = self._W - 272
        threat_lbl = self._f_xs.render("THREAT", True, C_DIM)
        scr.blit(threat_lbl, (tx, 8))
        cell_w = 34
        for i in range(5):
            rx = tx + i * (cell_w + 4)
            col = THREAT_COLOR[min(gs.threat_level, 5)] if i < gs.threat_level else C_PANEL2
            pygame.draw.rect(scr, col, (rx, 28, cell_w, 24), border_radius=4)
            pygame.draw.rect(scr, C_BORDER, (rx, 28, cell_w, 24), width=1, border_radius=4)

    # ── Attract screen ────────────────────────────────────────────────────────

    def _draw_attract(self, gs) -> None:
        cx = self._W // 2
        cy = self._H // 2
        scr = self._screen

        # Animated background glow ring (pulsing)
        pulse = 0.5 + 0.5 * math.sin(self._t * 1.6)
        glow_r = int(200 + 60 * pulse)
        glow_s = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_s, (20, 60, 180, 18), (glow_r, glow_r), glow_r)
        pygame.draw.circle(glow_s, (0, 120, 220, 10), (glow_r, glow_r), glow_r, 4)
        scr.blit(glow_s, (cx - glow_r, cy - glow_r - 60))

        # Big title — double-layered glow
        title_col = int(210 + 45 * math.sin(self._t * 1.2))
        t1_col    = (title_col, title_col, 255)
        _glow_text(scr, self._f_prompt, "NSBE", t1_col,
                   (cx - self._f_prompt.size("NSBE")[0] // 2, cy - 200),
                   glow_color=(20, 60, 200), glow_r=3)

        _glow_text(scr, self._f_prompt, "RADAR CHASER", C_WHITE,
                   (cx - self._f_prompt.size("RADAR CHASER")[0] // 2, cy - 90),
                   glow_color=(30, 30, 120), glow_r=2)

        # Subtitle
        sub = self._f_md.render("Lock in.  Read the motion.  Chase the score.", True, C_GREY)
        scr.blit(sub, (cx - sub.get_width() // 2, cy + 30))

        # Blinking start prompt
        if int(self._t * 2) % 2 == 0:
            start_text = "▶  Press ENTER for TESTING GROUND  ◀"
            _glow_text(scr, self._f_lg, start_text, C_TEAL,
                       (cx - self._f_lg.size(start_text)[0] // 2, cy + 90),
                       glow_color=(0, 100, 120), glow_r=2)

        # Mode shortcuts — glowing panels
        shortcuts = [
            ("[ENTER]  TESTING GROUND — practice & feel out the wand", C_TEAL),
            ("[F2]     ENDLESS REFLEX — survive as long as you can",   C_ORANGE),
        ]
        box_x = cx - 330
        for i, (txt, col) in enumerate(shortcuts):
            by = cy + 168 + i * 36
            # Thin glowing pill
            pygame.draw.rect(scr, (int(col[0]*0.12), int(col[1]*0.12), int(col[2]*0.12)),
                             (box_x - 4, by - 4, 660, 28), border_radius=4)
            pygame.draw.rect(scr, col, (box_x - 4, by - 4, 660, 28), width=1, border_radius=4)
            surf = self._f_sm.render(txt, True, col)
            scr.blit(surf, (box_x + 8, by))

    # ── Keyboard controls box ─────────────────────────────────────────────────

    def _draw_controls_box(self, x: int, y: int) -> None:
        items = [
            ("ENTER",  "Testing ground"),
            ("ESC",    "Back to attract"),
            ("F2",     "Endless Reflex mode"),
            ("R",      "Recalibrate wand"),
            ("D",      "Debug overlay"),
            ("Q",      "Quit"),
        ]
        box_w, box_h = 560, 20 + len(items) * 24 + 12
        pygame.draw.rect(self._screen, C_PANEL, (x, y, box_w, box_h), border_radius=6)
        pygame.draw.rect(self._screen, C_BORDER, (x, y, box_w, box_h), width=1, border_radius=6)
        hdr = self._f_xs.render("KEYBOARD CONTROLS", True, C_TEAL)
        self._screen.blit(hdr, (x + box_w // 2 - hdr.get_width() // 2, y + 6))
        for i, (key, desc) in enumerate(items):
            ky = y + 26 + i * 24
            ks = self._f_xs.render(f"  {key:<10}", True, C_YELLOW)
            ds = self._f_xs.render(desc,           True, C_WHITE)
            self._screen.blit(ks, (x + 10, ky))
            self._screen.blit(ds, (x + 130, ky))

    # ── Freeplay screen ───────────────────────────────────────────────────────

    def _draw_freeplay(self, gs) -> None:
        self._draw_tilt_panel(gs)
        cx = self._CX + self._CW // 2
        cy = self._MID_Y + self._MID_H // 2

        _glow_text(self._screen, self._f_lg, "TESTING GROUND", C_TEAL,
                   (cx - self._f_lg.size("TESTING GROUND")[0] // 2, cy - 100),
                   glow_color=(0, 100, 120), glow_r=2)

        roll  = gs.tilt.get("roll",  0.0)
        pitch = gs.tilt.get("pitch", 0.0)
        rv = self._f_md.render(f"ROLL   {roll:>+7.1f}°",  True, C_BLUE)
        pv = self._f_md.render(f"PITCH  {pitch:>+7.1f}°", True, C_PURPLE)
        self._screen.blit(rv, (cx - rv.get_width() // 2, cy - 30))
        self._screen.blit(pv, (cx - pv.get_width() // 2, cy + 14))

        tip = self._f_sm.render("Press F2 for Reflex challenge  or  F3 for Boss", True, C_DIM)
        self._screen.blit(tip, (cx - tip.get_width() // 2, cy + 80))

    # ── Game screen (Reflex + Boss) ───────────────────────────────────────────

    def _draw_game(self, gs) -> None:
        self._draw_tilt_panel(gs)
        self._draw_prompt_panel(gs)
        self._draw_stats_panel(gs)

    # ── Left: tilt visualiser ─────────────────────────────────────────────────

    def _draw_tilt_panel(self, gs) -> None:
        roll   = gs.tilt.get("roll",   0.0)
        pitch  = gs.tilt.get("pitch",  0.0)
        thresh = float(self._cfg.get("tilt", {}).get(
                    "threshold_deg",
                    self._cfg.get("mpu6050", {}).get("threshold_deg", 22.0)))
        pad = 18
        x0  = 0
        w   = self._LEFT_W
        y0  = self._MID_Y
        h   = self._MID_H

        # Crosshair
        cxp = x0 + w // 2
        cyp = y0 + (h - 90) // 2 + y0 // 4
        rad = min(w, h - 100) // 2 - 30

        # Background circle with soft glow
        glow_c = pygame.Surface((rad * 2 + 20, rad * 2 + 20), pygame.SRCALPHA)
        pygame.draw.circle(glow_c, (30, 80, 180, 25), (rad + 10, rad + 10), rad + 10)
        self._screen.blit(glow_c, (cxp - rad - 10, cyp - rad - 10))
        pygame.draw.circle(self._screen, C_PANEL, (cxp, cyp), rad)

        # Rings & cross
        pygame.draw.circle(self._screen, C_BORDER, (cxp, cyp), rad,    1)
        pygame.draw.circle(self._screen, (25, 50, 110), (cxp, cyp), rad // 2, 1)
        pygame.draw.line(self._screen, (20, 40, 90), (cxp - rad, cyp), (cxp + rad, cyp), 1)
        pygame.draw.line(self._screen, (20, 40, 90), (cxp, cyp - rad), (cxp, cyp + rad), 1)

        # Threshold ring (green tint)
        tr = int(rad * thresh / 90.0)
        pygame.draw.circle(self._screen, (20, 80, 40), (cxp, cyp), tr, 1)

        # Moving dot
        dx = cxp + int(roll  * rad / 90.0)
        dy = cyp + int(pitch * rad / 90.0)
        dx = max(x0 + 4, min(x0 + w - 4, dx))
        dy = max(y0 + 4, min(y0 + h - 4 - 90, dy))
        inside  = abs(roll) < thresh and abs(pitch) < thresh
        dot_col = C_TEAL if inside else C_ORANGE
        # Glow ring around dot
        gd = pygame.Surface((32, 32), pygame.SRCALPHA)
        pygame.draw.circle(gd, (dot_col[0], dot_col[1], dot_col[2], 55), (16, 16), 14)
        self._screen.blit(gd, (dx - 16, dy - 16))
        pygame.draw.circle(self._screen, dot_col, (dx, dy), 9)
        pygame.draw.circle(self._screen, C_WHITE,  (dx, dy), 9, 2)

        # Axis bars
        by1 = y0 + h - 78
        by2 = y0 + h - 44
        bx  = x0 + pad
        bw  = w - pad * 2
        midx = x0 + w // 2

        for val, col, label, by in ((roll, C_BLUE, "ROLL", by1), (pitch, C_PURPLE, "PITCH", by2)):
            lbl = self._f_xs.render(f"{label} {val:>+.0f}°", True, col)
            self._screen.blit(lbl, (bx, by))
            pygame.draw.rect(self._screen, C_PANEL2, (bx, by + 18, bw, 12), border_radius=3)
            px = int((val / 90.0) * (bw // 2))
            if px != 0:
                sx      = midx if px > 0 else midx + px
                bar_col = C_GREEN if abs(val) >= thresh else col
                pygame.draw.rect(self._screen, bar_col, (sx, by + 18, abs(px), 12), border_radius=2)
            pygame.draw.line(self._screen, C_DIM, (midx, by + 16), (midx, by + 32), 2)
            pygame.draw.rect(self._screen, C_BORDER, (bx, by + 18, bw, 12), width=1, border_radius=3)

        lbl = self._f_xs.render("TILT WAND", True, C_DIM)
        self._screen.blit(lbl, (cxp - lbl.get_width() // 2, y0 + 10))

    # ── Centre: prompt panel ──────────────────────────────────────────────────

    def _draw_prompt_panel(self, gs) -> None:
        cx   = self._CX + self._CW // 2
        cy   = self._MID_Y + self._MID_H // 2 - 30
        mode = gs.mode.name

        # Inversion warning
        if gs.axis_inverted:
            inv = self._f_sm.render("⚡  AXES INVERTED", True, C_RED)
            self._screen.blit(inv, (cx - inv.get_width() // 2, self._MID_Y + 14))

        # Result display (hold phase)
        if gs.result_hold_timer > 0 and gs.last_prompt_result:
            rc = RESULT_COLOR.get(gs.last_prompt_result, C_WHITE)
            _glow_text(self._screen, self._f_result, gs.last_prompt_result, rc,
                       (cx - self._f_result.size(gs.last_prompt_result)[0] // 2, cy - 60),
                       glow_r=3)
            if gs.score_delta and gs.score_delta_timer > 0:
                alpha = min(255, int(gs.score_delta_timer * 360))
                sign  = "+" if gs.score_delta >= 0 else ""
                ps    = self._f_md.render(f"{sign}{gs.score_delta} pts", True, rc)
                ps.set_alpha(alpha)
                self._screen.blit(ps, (cx - ps.get_width() // 2, cy + 30))
            return

        if not gs.session_active or not gs.prompt:
            return

        # Prompt colour
        key  = "".join(c for c in gs.prompt.split()[0] if c.isalpha()).upper()
        pcol = PROMPT_COLOR.get(key, PROMPT_COLOR["DEFAULT"])
        self._c_prompt.set_color(pcol)

        # Re-centre lock bar
        if gs.awaiting_recenter:
            lock = self._f_sm.render("RE-CENTER TO ARM SCORING", True, C_YELLOW)
            self._screen.blit(lock, (cx - lock.get_width() // 2, self._MID_Y + 14))
            wait_total = 2.8 if mode == "FREEPLAY" else 2.0
            ratio  = max(0.0, min(1.0, gs.recenter_timer / wait_total))
            bar_y  = self._MID_Y + 42
            bar_w  = self._CW - 180
            bar_x  = self._CX + 90
            pygame.draw.rect(self._screen, C_PANEL2, (bar_x, bar_y, bar_w, 10), border_radius=5)
            if ratio > 0:
                pygame.draw.rect(self._screen, C_YELLOW, (bar_x, bar_y, int(bar_w * ratio), 10), border_radius=5)
            pygame.draw.rect(self._screen, C_BORDER, (bar_x, bar_y, bar_w, 10), width=1, border_radius=5)

        # Fake-out tag
        if gs.is_fake_out:
            ftag = self._f_sm.render("FAKE-OUT — FREEZE!", True, C_ORANGE)
            self._screen.blit(ftag, (cx - ftag.get_width() // 2, self._MID_Y + 58))

        # Big prompt — glowing
        ps = self._c_prompt.get(gs.prompt)
        px = cx - ps.get_width() // 2
        py = cy - ps.get_height() // 2
        # Soft glow behind prompt text
        gsurf = pygame.Surface((ps.get_width() + 40, ps.get_height() + 20), pygame.SRCALPHA)
        gc = (pcol[0]//3, pcol[1]//3, pcol[2]//3, 35)
        gsurf.fill(gc)
        self._screen.blit(gsurf, (px - 20, py - 10))
        self._screen.blit(ps, (px, py))

        # Countdown bar
        if gs.prompt_timer > 0:
            mode_dur_key = "boss" if mode == "BOSS" else "reflex"
            total  = float(self._cfg.get(mode_dur_key, {}).get("prompt_duration_sec", 2.5))
            ratio  = max(0.0, min(1.0, gs.prompt_timer / total))
            bar_y  = cy + ps.get_height() // 2 + 20
            bar_w  = self._CW - 60
            bar_x  = self._CX + 30
            bar_h  = 16
            pygame.draw.rect(self._screen, C_PANEL2, (bar_x, bar_y, bar_w, bar_h), border_radius=6)
            bc = C_GREEN if ratio > 0.5 else (C_YELLOW if ratio > 0.25 else C_RED)
            fw = int(bar_w * ratio)
            if fw > 0:
                pygame.draw.rect(self._screen, bc, (bar_x, bar_y, fw, bar_h), border_radius=6)
            pygame.draw.rect(self._screen, C_BORDER, (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=6)

        # Wave / progress indicator (endless mode: prompt_total == 0)
        wave = gs.prompt_index // 10 + 1
        if gs.prompt_total == 0:
            prog_txt = f"Wave {wave}  ·  {gs.prompt_index} survived"
        else:
            prog_txt = f"Prompt {gs.prompt_index} / {gs.prompt_total}"
        prog = self._f_xs.render(prog_txt, True, C_DIM)
        self._screen.blit(prog, (cx - prog.get_width() // 2, self._BOT_Y - 24))

    # ── Right: session stats ──────────────────────────────────────────────────

    def _draw_stats_panel(self, gs) -> None:
        x = self._RX + 18
        y = self._MID_Y + 20

        def row(text, surf, dy=0):
            nonlocal y
            lbl = self._f_xs.render(text, True, C_DIM)
            self._screen.blit(lbl,  (x, y))
            self._screen.blit(surf, (x, y + 16))
            y += 16 + surf.get_height() + 10 + dy

        # Accuracy
        ac = C_GREEN if gs.accuracy >= 75 else (C_YELLOW if gs.accuracy >= 50 else C_RED)
        self._c_acc.set_color(ac)
        row("ACCURACY", self._c_acc.get(f"{gs.accuracy:.0f}%"))

        self._screen.blit(self._c_hits.get(f"HIT   {gs.hits:>4}"),   (x, y)); y += 26
        self._screen.blit(self._c_misses.get(f"MISS  {gs.misses:>4}"), (x, y)); y += 36

        mc = self._f_sm.render(f"MAX COMBO  ×{gs.max_combo}", True, C_GOLD)
        self._screen.blit(mc, (x, y)); y += 34

        cal_t = "CALIBRATED ✓" if gs.calibrated else "NOT CALIBRATED"
        cal_c = C_GREEN if gs.calibrated else C_YELLOW
        cs = self._f_xs.render(cal_t, True, cal_c)
        self._screen.blit(cs, (x, y)); y += 26

        mins = int(gs.timer) // 60
        secs = int(gs.timer) % 60
        ts = self._f_xs.render(f"TIME  {mins:02d}:{secs:02d}", True, C_DIM)
        self._screen.blit(ts, (x, y)); y += 28

        if gs.status_message:
            sm = self._f_xs.render(gs.status_message, True, C_ORANGE)
            self._screen.blit(sm, (x, y))

    # ── Calibration screen ────────────────────────────────────────────────────

    def _draw_calibrating(self, gs, cal_mode) -> None:
        cx = self._W // 2
        cy = self._H // 2

        if cal_mode is None:
            s = self._f_lg.render("Calibrating …", True, C_YELLOW)
            self._screen.blit(s, (cx - s.get_width() // 2, cy - 30))
            return

        phase = cal_mode.phase

        if phase == "SETTLE":
            _glow_text(self._screen, self._f_lg, "CALIBRATION", C_YELLOW,
                       (cx - self._f_lg.size("CALIBRATION")[0] // 2, cy - 80),
                       glow_color=(120, 100, 0), glow_r=2)
            h2 = self._f_md.render("Hold the wand FLAT and STILL", True, C_WHITE)
            h3 = self._f_sm.render("Starting in a moment …", True, C_DIM)
            self._screen.blit(h2, (cx - h2.get_width() // 2, cy - 20))
            self._screen.blit(h3, (cx - h3.get_width() // 2, cy + 40))

        elif phase == "COLLECT":
            n    = cal_mode.samples_collected
            tot  = cal_mode.total_samples
            prog = cal_mode.progress

            _glow_text(self._screen, self._f_lg, "CALIBRATING …", C_YELLOW,
                       (cx - self._f_lg.size("CALIBRATING …")[0] // 2, cy - 110),
                       glow_color=(120, 100, 0), glow_r=2)
            h2 = self._f_md.render("Keep wand flat and still", True, C_WHITE)
            self._screen.blit(h2, (cx - h2.get_width() // 2, cy - 50))

            # Progress bar
            bx, bw, bh = cx - 260, 520, 28
            by = cy
            pygame.draw.rect(self._screen, C_PANEL2, (bx, by, bw, bh), border_radius=8)
            fw = int(bw * prog)
            if fw > 0:
                pygame.draw.rect(self._screen, C_TEAL, (bx, by, fw, bh), border_radius=8)
            pygame.draw.rect(self._screen, C_BORDER, (bx, by, bw, bh), width=2, border_radius=8)

            cnt = self._f_sm.render(f"{n} / {tot} samples   ({prog*100:.0f}%)", True, C_DIM)
            self._screen.blit(cnt, (cx - cnt.get_width() // 2, cy + 38))

        elif phase == "RESULT":
            _glow_text(self._screen, self._f_lg, "CALIBRATION COMPLETE ✓", C_GREEN,
                       (cx - self._f_lg.size("CALIBRATION COMPLETE ✓")[0] // 2, cy - 80),
                       glow_color=(0, 80, 20), glow_r=2)
            if cal_mode.cal_result:
                ao = cal_mode.cal_result["accel_offset"]
                lines = [
                    f"accel x={ao['x']:+.4f}  y={ao['y']:+.4f}  z={ao['z']:+.4f}",
                    "Saved to config/calibration.yaml",
                ]
                for i, line in enumerate(lines):
                    ls = self._f_sm.render(line, True, C_DIM)
                    self._screen.blit(ls, (cx - ls.get_width() // 2, cy + i * 28))
            h3 = self._f_sm.render("Press any key to continue …", True, C_GREY)
            self._screen.blit(h3, (cx - h3.get_width() // 2, cy + 100))

    # ── Game Over screen ──────────────────────────────────────────────────────

    def _draw_gameover(self, gs) -> None:
        cx = self._W // 2
        cy = self._H // 2

        # Pulsing red glow behind title
        pulse = 0.5 + 0.5 * math.sin(self._t * 3.0)
        gr    = int(180 + 60 * pulse)
        glow_r = 260
        gs_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(gs_surf, (gr, 10, 10, 22), (glow_r, glow_r), glow_r)
        self._screen.blit(gs_surf, (cx - glow_r, cy - glow_r - 20))

        # "GAME OVER" title
        _glow_text(self._screen, self._f_prompt, "GAME OVER", C_RED,
                   (cx - self._f_prompt.size("GAME OVER")[0] // 2, cy - 190),
                   glow_color=(100, 0, 0), glow_r=4)

        # Stats panel (dark pill)
        stats = [
            ("FINAL SCORE",    f"{gs.score:,}",      C_WHITE),
            ("PROMPTS SURVIVED", str(gs.prompt_index), C_TEAL),
            ("WAVE REACHED",   str(gs.prompt_index // 10 + 1), C_ORANGE),
            ("MAX COMBO",      f"×{gs.max_combo}",   C_GOLD),
            ("ACCURACY",       f"{gs.accuracy:.0f}%", C_GREEN if gs.accuracy >= 60 else C_YELLOW),
        ]
        panel_w, row_h = 460, 38
        panel_h = len(stats) * row_h + 24
        px = cx - panel_w // 2
        py = cy - 80

        panel_bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel_bg.fill((10, 14, 40, 200))
        self._screen.blit(panel_bg, (px, py))
        pygame.draw.rect(self._screen, C_BORDER, (px, py, panel_w, panel_h), width=1, border_radius=6)

        for i, (label, value, col) in enumerate(stats):
            ry = py + 12 + i * row_h
            lbl = self._f_xs.render(label, True, C_DIM)
            val = self._f_md.render(value, True, col)
            self._screen.blit(lbl, (px + 18, ry))
            self._screen.blit(val, (px + panel_w - val.get_width() - 18, ry))

        # Flashing continue prompt
        if int(self._t * 2) % 2 == 0:
            cont = self._f_sm.render("Press any key to continue …", True, C_GREY)
            self._screen.blit(cont, (cx - cont.get_width() // 2, py + panel_h + 22))

    # ── Paused screen ─────────────────────────────────────────────────────────

    def _draw_paused(self, gs) -> None:
        cx, cy = self._W // 2, self._H // 2
        _glow_text(self._screen, self._f_lg, "⏸  PAUSED", C_YELLOW,
                   (cx - self._f_lg.size("⏸  PAUSED")[0] // 2, cy - 30),
                   glow_color=(120, 100, 0), glow_r=2)
        s2 = self._f_sm.render("Press ENTER to resume  |  ESC to quit session", True, C_DIM)
        self._screen.blit(s2, (cx - s2.get_width() // 2, cy + 30))

    # ── Debug overlay ─────────────────────────────────────────────────────────

    def _draw_debug(self, gs) -> None:
        """Semi-transparent overlay with raw sensor and axis-mapping data."""
        bx, by, bw, bh = 10, self._TOP_H + 6, 380, 230
        ov = pygame.Surface((bw, bh), pygame.SRCALPHA)
        ov.fill((4, 6, 20, 200))
        self._screen.blit(ov, (bx, by))
        pygame.draw.rect(self._screen, C_BORDER, (bx, by, bw, bh), width=1, border_radius=4)

        t     = gs.tilt
        cfg_t = self._cfg.get("mpu6050", self._cfg.get("tilt", {}))
        lines = [
            ("DEBUG OVERLAY", C_YELLOW),
            (f"  game  roll={t.get('roll',0):>+7.1f}°  pitch={t.get('pitch',0):>+7.1f}°", C_TEAL),
            (f"  raw   roll={t.get('raw_roll',0):>+7.1f}°  pitch={t.get('raw_pitch',0):>+7.1f}°", C_GREY),
            (f"  accel_mag = {t.get('accel_mag', 1.0):.3f} g", C_DIM),
            (f"  swap={cfg_t.get('swap_axes',False)}"
             f"  inv_x={cfg_t.get('invert_x',False)}"
             f"  inv_y={cfg_t.get('invert_y',False)}", C_DIM),
            (f"  dz={cfg_t.get('deadzone_deg',4)}°"
             f"  thresh={cfg_t.get('threshold_deg',22)}°"
             f"  sens={cfg_t.get('sensitivity',1.0)}", C_DIM),
            (f"  FPS={self._fps_val:.1f}  debug_mode={gs.debug_mode}", C_DIM),
        ]
        for i, (txt, col) in enumerate(lines):
            surf = self._f_xs.render(txt, True, col)
            self._screen.blit(surf, (bx + 8, by + 8 + i * 30))

    # ── Screen flash ──────────────────────────────────────────────────────────

    def _draw_flash(self, gs) -> None:
        """Full-screen colour flash on hit / miss."""
        if not getattr(gs, "flash_timer", 0) or gs.flash_timer <= 0:
            return
        fc = RESULT_COLOR.get(getattr(gs, "flash_result", ""), None)
        if fc is None:
            return
        alpha = min(130, int(gs.flash_timer * 400))
        self._flash.fill((fc[0], fc[1], fc[2], alpha))
        self._screen.blit(self._flash, (0, 0))
