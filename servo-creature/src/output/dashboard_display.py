"""
output/dashboard_display.py — Tilt Trial Arena / Mission Breach
Pi-optimised Pygame HUD.

Performance strategy:
  • Static backgrounds are pre-rendered to a Surface once per mode change
    and blitted as a single call each frame (avoids ~30 redundant draw ops).
  • Dynamic text is cached: re-rendered only when the underlying value changes.
  • No per-frame alpha Surface allocation (SRCALPHA is kept as a reusable slot).
  • draw call budget per frame ≈ 15–25 operations.
  • Target 30 fps on Pi 3B+ at 1280×720.

Layout (1280×720):
  ┌──────────────────────────────────────────────────────┐
  │ TOP BAR (0–72):  [MODE]   Title   SCORE  COMBO  FPS  │
  ├──────────────────────────────────────────────────────┤
  │ MAIN (72–620):                                        │
  │  Left 300px: tilt visualiser (crosshair + bars)      │
  │  Centre 680px: prompt / mode content (huge text)     │
  │  Right 300px: session stats                          │
  ├──────────────────────────────────────────────────────┤
  │ BOTTOM (620–720): timer · controls hint · cal status │
  └──────────────────────────────────────────────────────┘
"""

import math
import time
import pygame
from src.util.logger import get_logger

logger = get_logger("dashboard")

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG      = (5,   7,  14)
C_PANEL   = (11,  16,  30)
C_PANEL2  = (16,  22,  40)
C_BORDER  = (28,  40,  68)
C_GRID    = (14,  19,  34)

C_TEAL    = (0,   210, 175)
C_ORANGE  = (255, 140,   0)
C_RED     = (210,  20,  20)
C_GREEN   = (45,  210,  75)
C_YELLOW  = (255, 205,   0)
C_PURPLE  = (160,  80, 255)
C_BLUE    = (55,  155, 255)
C_WHITE   = (225, 230, 240)
C_GREY    = (120, 135, 160)
C_DIM     = (50,   58,  80)
C_GOLD    = (255, 215,   0)

# Mode accent colours
MODE_COLOR = {
    "ATTRACT":     C_GREY,
    "FREEPLAY":    C_TEAL,
    "REFLEX":      C_ORANGE,
    "BOSS":        C_RED,
    "CALIBRATING": C_YELLOW,
    "PAUSED":      C_YELLOW,
}

# Prompt key → colour
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
    (30,  180,  70),  # 0
    (80,  200,  40),  # 1
    (210, 195,   0),  # 2
    (255, 130,   0),  # 3
    (210,  35,   0),  # 4
    (190,   0,   0),  # 5
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


# ── Main class ────────────────────────────────────────────────────────────────

class DashboardDisplay:

    # Layout constants (set in __init__ from screen size)
    _TOP_H  = 72
    _BOT_H  = 82
    _LEFT_W = 295
    _RGT_W  = 295

    def __init__(self, screen: pygame.Surface, game_cfg: dict) -> None:
        self._screen   = screen
        self._W, self._H = screen.get_size()
        self._cfg      = game_cfg
        self._show_fps = game_cfg.get("show_fps", True)
        self._t        = 0.0    # animation clock
        self._fps_val  = 0.0
        self._fps_acc  = 0.0
        self._fps_cnt  = 0
        self._last_mode: str = ""
        self._bg_surf: pygame.Surface | None = None

        # Layout derived values
        self._MID_Y  = self._TOP_H
        self._MID_H  = self._H - self._TOP_H - self._BOT_H
        self._CX     = self._LEFT_W              # left edge of centre column
        self._CW     = self._W - self._LEFT_W - self._RGT_W
        self._RX     = self._W - self._RGT_W     # left edge of right column
        self._BOT_Y  = self._H - self._BOT_H

        # ── Fonts (monospace for alignment) ──────────────────────────────
        pygame.font.init()
        def _font(size: int, bold: bool = False) -> pygame.font.Font:
            try:
                return pygame.font.SysFont("monospace", size, bold=bold)
            except Exception:
                return pygame.font.Font(None, size)

        self._f_score  = _font(52, bold=True)
        self._f_prompt = _font(108, bold=True)
        self._f_result = _font(72, bold=True)
        self._f_lg     = _font(42, bold=True)
        self._f_md     = _font(30, bold=True)
        self._f_sm     = _font(21)
        self._f_xs     = _font(17)

        # ── Cached text surfaces ──────────────────────────────────────────
        self._c_score  = _Cached(self._f_score, C_WHITE)
        self._c_combo  = _Cached(self._f_lg,    C_GOLD)
        self._c_mult   = _Cached(self._f_xs,    C_DIM)
        self._c_timer  = _Cached(self._f_md,    C_TEAL)
        self._c_acc    = _Cached(self._f_md,    C_GREEN)
        self._c_hits   = _Cached(self._f_sm,    C_GREEN)
        self._c_misses = _Cached(self._f_sm,    C_RED)
        self._c_prompt = _Cached(self._f_prompt, C_WHITE)
        self._c_fps    = _Cached(self._f_xs,    C_DIM)

        # Reusable flash surface (SRCALPHA)
        self._flash = pygame.Surface((self._W, self._H), pygame.SRCALPHA)

        logger.info("DashboardDisplay  %dx%d", self._W, self._H)

    # ── Public ────────────────────────────────────────────────────────────────

    def render(self, gs, cal_mode=None, fps: float = 0.0) -> None:
        """Main render call — once per frame."""
        self._t  += 0.016
        self._fps_val = fps

        # Rebuild static bg when mode changes
        if gs.mode.name != self._last_mode:
            self._build_bg(gs.mode.name)
            self._last_mode = gs.mode.name

        # Layer 1: static background
        self._screen.blit(self._bg_surf, (0, 0))

        # Layer 2: dynamic elements
        mode = gs.mode.name
        if mode == "CALIBRATING":
            self._draw_calibrating(gs, cal_mode)
        elif mode == "ATTRACT":
            self._draw_attract(gs)
        elif mode == "FREEPLAY":
            self._draw_freeplay(gs)
        elif mode in ("REFLEX", "BOSS"):
            self._draw_game(gs)
        elif mode == "PAUSED":
            self._draw_paused(gs)

        # Top bar dynamic elements
        self._draw_top_dynamic(gs)

        # Debug overlay (toggled with D)
        if gs.debug_mode:
            self._draw_debug(gs)

        # Screen flash
        self._draw_flash(gs)

        # FPS
        if self._show_fps:
            fps_str = f"FPS:{fps:.0f}"
            self._screen.blit(self._c_fps.get(fps_str),
                              (self._W - 70, self._H - 20))

    # ── Static background builder ─────────────────────────────────────────────

    def _build_bg(self, mode_name: str) -> None:
        """Pre-render everything that does not change frame to frame."""
        s = pygame.Surface((self._W, self._H))
        s.fill(C_BG)

        # Subtle grid
        for x in range(0, self._W, 80):
            pygame.draw.line(s, C_GRID, (x, 0), (x, self._H))
        for y in range(0, self._H, 80):
            pygame.draw.line(s, C_GRID, (0, y), (self._W, y))

        # Top bar background
        pygame.draw.rect(s, C_PANEL, (0, 0, self._W, self._TOP_H))
        pygame.draw.line(s, C_BORDER, (0, self._TOP_H - 1), (self._W, self._TOP_H - 1), 2)

        # Mode tag
        mc = MODE_COLOR.get(mode_name, C_GREY)
        tag_w = 190
        pygame.draw.rect(s, (int(mc[0]*0.18), int(mc[1]*0.18), int(mc[2]*0.18)),
                         (10, 10, tag_w, 52), border_radius=6)
        pygame.draw.rect(s, mc, (10, 10, tag_w, 52), width=2, border_radius=6)
        tag_surf = self._f_md.render(f"[ {mode_name} ]", True, mc)
        s.blit(tag_surf, (10 + (tag_w - tag_surf.get_width()) // 2, 10 + (52 - tag_surf.get_height()) // 2))

        # Title
        title = self._f_md.render("NSBE RADAR CHASER", True, C_GOLD)
        s.blit(title, (self._W // 2 - title.get_width() // 2, self._TOP_H // 2 - title.get_height() // 2))

        # Bottom bar background
        pygame.draw.rect(s, C_PANEL, (0, self._BOT_Y, self._W, self._BOT_H))
        pygame.draw.line(s, C_BORDER, (0, self._BOT_Y), (self._W, self._BOT_Y), 2)

        # Bottom: keyboard hint
        hints = (
            "[ENTER] Start   [F2] Reflex   [F3] Boss   "
            "[R] Recalibrate   [D] Debug   [Q] Quit"
        )
        hint_surf = self._f_xs.render(hints, True, C_DIM)
        s.blit(hint_surf, (self._W // 2 - hint_surf.get_width() // 2, self._BOT_Y + 10))

        # Column separators (only for game modes)
        if mode_name in ("FREEPLAY", "REFLEX", "BOSS"):
            pygame.draw.line(s, C_BORDER,
                             (self._CX, self._MID_Y), (self._CX, self._BOT_Y), 1)
            pygame.draw.line(s, C_BORDER,
                             (self._RX, self._MID_Y), (self._RX, self._BOT_Y), 1)

        # Static labels in top bar
        score_lbl = self._f_xs.render("SCORE", True, C_DIM)
        combo_lbl = self._f_xs.render("COMBO", True, C_DIM)
        s.blit(score_lbl, (216, 10))
        s.blit(combo_lbl, (216, 38))

        self._bg_surf = s

    # ── Top bar (dynamic part) ────────────────────────────────────────────────

    def _draw_top_dynamic(self, gs) -> None:
        scr = self._screen
        # Score
        scr.blit(self._c_score.get(f"{gs.score:,}"), (280, 8))
        # Combo
        combo_col = C_GOLD if gs.combo > 3 else C_WHITE
        self._c_combo.set_color(combo_col)
        scr.blit(self._c_combo.get(f"×{gs.combo}"), (280, 36))
        # Multiplier sub-text
        scr.blit(self._c_mult.get(f"({gs.combo_multiplier:.1f}×)"), (380, 46))

        # Threat bar (right of top bar)
        tx = self._W - 260
        threat_lbl = self._f_xs.render("THREAT", True, C_DIM)
        scr.blit(threat_lbl, (tx, 10))
        cell_w = 34
        for i in range(5):
            rx = tx + i * (cell_w + 4)
            col = THREAT_COLOR[min(gs.threat_level, 5)] if i < gs.threat_level else C_PANEL2
            pygame.draw.rect(scr, col, (rx, 30, cell_w, 22), border_radius=3)
            pygame.draw.rect(scr, C_BORDER, (rx, 30, cell_w, 22), width=1, border_radius=3)

    # ── Attract screen ────────────────────────────────────────────────────────

    def _draw_attract(self, gs) -> None:
        cx = self._W // 2
        cy = self._H // 2

        pulse = int(200 + 55 * math.sin(self._t * 1.8))

        # Big title
        t1 = self._f_prompt.render("NSBE", True, C_GOLD)
        t2 = self._f_prompt.render("RADAR CHASER", True, C_WHITE)
        self._screen.blit(t1, (cx - t1.get_width() // 2, cy - 200))
        self._screen.blit(t2, (cx - t2.get_width() // 2, cy - 90))

        sub = self._f_md.render("Lock in. Read the motion. Chase the score.", True, C_GREY)
        self._screen.blit(sub, (cx - sub.get_width() // 2, cy + 30))

        # Blinking start prompt
        if int(self._t * 2) % 2 == 0:
            start = self._f_lg.render("► Press ENTER to start ◄", True, C_ORANGE)
            self._screen.blit(start, (cx - start.get_width() // 2, cy + 88))

        # Mode shortcuts
        shortcuts = [
            ("[F2] REFLEX MODE  — 15 timed prompts",   C_ORANGE),
            ("[F3] BOSS MODE    — 20 prompts + fakes",  C_RED),
            ("[ENTER] EASY MODE — 5 seconds per prompt", C_TEAL),
        ]
        for i, (txt, col) in enumerate(shortcuts):
            s = self._f_sm.render(txt, True, col)
            self._screen.blit(s, (cx - s.get_width() // 2, cy + 160 + i * 32))

        

    def _draw_controls_box(self, x: int, y: int) -> None:
        """Small keyboard reference card."""
        items = [
            ("ENTER",   "Start / confirm"),
            ("ESC",     "Back to attract"),
            ("F2",      "Reflex mode"),
            ("F3",      "Boss mode"),
            ("R",       "Recalibrate wand"),
            ("D",       "Debug overlay"),
            ("Q",       "Quit"),
        ]
        box_w, box_h = 560, 20 + len(items) * 24 + 12
        pygame.draw.rect(self._screen, C_PANEL, (x, y, box_w, box_h), border_radius=6)
        pygame.draw.rect(self._screen, C_BORDER, (x, y, box_w, box_h), width=1, border_radius=6)
        hdr = self._f_xs.render("KEYBOARD CONTROLS", True, C_DIM)
        self._screen.blit(hdr, (x + box_w // 2 - hdr.get_width() // 2, y + 6))
        for i, (key, desc) in enumerate(items):
            ky = y + 26 + i * 24
            ks = self._f_xs.render(f"  {key:<10}", True, C_YELLOW)
            ds = self._f_xs.render(desc,            True, C_WHITE)
            self._screen.blit(ks, (x + 10, ky))
            self._screen.blit(ds, (x + 130, ky))

    # ── Freeplay screen ───────────────────────────────────────────────────────

    def _draw_freeplay(self, gs) -> None:
        self._draw_tilt_panel(gs)
        # Centre: instruction + values
        cx = self._CX + self._CW // 2
        cy = self._MID_Y + self._MID_H // 2

        hdr = self._f_lg.render("FREEPLAY", True, C_TEAL)
        self._screen.blit(hdr, (cx - hdr.get_width() // 2, cy - 100))

        roll  = gs.tilt.get("roll", 0.0)
        pitch = gs.tilt.get("pitch", 0.0)
        rv = self._f_md.render(f"ROLL   {roll:>+7.1f}°", True, C_BLUE)
        pv = self._f_md.render(f"PITCH  {pitch:>+7.1f}°", True, C_PURPLE)
        self._screen.blit(rv, (cx - rv.get_width() // 2, cy - 30))
        self._screen.blit(pv, (cx - pv.get_width() // 2, cy + 14))

        tip = self._f_sm.render("Press F2 or ENTER for Reflex →", True, C_DIM)
        self._screen.blit(tip, (cx - tip.get_width() // 2, cy + 80))

    # ── Game screen (Reflex + Boss) ───────────────────────────────────────────

    def _draw_game(self, gs) -> None:
        self._draw_tilt_panel(gs)
        self._draw_prompt_panel(gs)
        self._draw_stats_panel(gs)

    # ── Left: tilt visualiser ─────────────────────────────────────────────────

    def _draw_tilt_panel(self, gs) -> None:
        roll   = gs.tilt.get("roll",  0.0)
        pitch  = gs.tilt.get("pitch", 0.0)
        thresh = float(self._cfg.get("tilt", {}).get("threshold_deg",
                 self._cfg.get("mpu6050", {}).get("threshold_deg", 22.0)))
        pad    = 18
        x0     = 0
        w      = self._LEFT_W
        y0     = self._MID_Y
        h      = self._MID_H

        # ── Crosshair ────────────────────────────────────────────────────
        cxp = x0 + w // 2
        cyp = y0 + (h - 90) // 2 + y0 // 4
        rad = min(w, h - 100) // 2 - 30

        # Background circle
        pygame.draw.circle(self._screen, C_PANEL, (cxp, cyp), rad)
        # Cardinal rings
        pygame.draw.circle(self._screen, C_BORDER, (cxp, cyp), rad, 1)
        pygame.draw.circle(self._screen, C_BORDER, (cxp, cyp), rad // 2, 1)
        # Cross
        pygame.draw.line(self._screen, C_DIM, (cxp - rad, cyp), (cxp + rad, cyp), 1)
        pygame.draw.line(self._screen, C_DIM, (cxp, cyp - rad), (cxp, cyp + rad), 1)
        # Threshold ring
        tr = int(rad * thresh / 90.0)
        pygame.draw.circle(self._screen, (30, 60, 30), (cxp, cyp), tr, 1)

        # Dot position
        dx = cxp + int(roll  * rad / 90.0)
        dy = cyp + int(pitch * rad / 90.0)
        dx = max(x0 + 4, min(x0 + w - 4, dx))
        dy = max(y0 + 4, min(y0 + h - 4 - 90, dy))
        inside = abs(roll) < thresh and abs(pitch) < thresh
        dot_col = C_GREEN if inside else C_ORANGE
        pygame.draw.circle(self._screen, dot_col, (dx, dy), 11)
        pygame.draw.circle(self._screen, C_WHITE, (dx, dy), 11, 2)

        # ── Axis bars ────────────────────────────────────────────────────
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
                sx = midx if px > 0 else midx + px
                bar_col = C_GREEN if abs(val) >= thresh else col
                pygame.draw.rect(self._screen, bar_col, (sx, by + 18, abs(px), 12), border_radius=2)
            pygame.draw.line(self._screen, C_DIM, (midx, by + 16), (midx, by + 32), 2)
            pygame.draw.rect(self._screen, C_BORDER, (bx, by + 18, bw, 12), width=1, border_radius=3)

        # Tilt label
        lbl = self._f_xs.render("TILT WAND", True, C_DIM)
        self._screen.blit(lbl, (cxp - lbl.get_width() // 2, y0 + 10))

    # ── Centre: prompt panel ──────────────────────────────────────────────────

    def _draw_prompt_panel(self, gs) -> None:
        cx   = self._CX + self._CW // 2
        cy   = self._MID_Y + self._MID_H // 2 - 30
        mode = gs.mode.name

        # ── Inversion / fake warning ──────────────────────────────────────
        if gs.axis_inverted:
            inv = self._f_sm.render("⚡ AXES INVERTED", True, C_RED)
            self._screen.blit(inv, (cx - inv.get_width() // 2, self._MID_Y + 14))

        # ── Result display (during hold) ──────────────────────────────────
        if gs.result_hold_timer > 0 and gs.last_prompt_result:
            rc  = RESULT_COLOR.get(gs.last_prompt_result, C_WHITE)
            rs  = self._f_result.render(gs.last_prompt_result, True, rc)
            self._screen.blit(rs, (cx - rs.get_width() // 2, cy - 60))
            # Score popup
            if gs.score_delta and gs.score_delta_timer > 0:
                alpha = min(255, int(gs.score_delta_timer * 360))
                sign  = "+" if gs.score_delta >= 0 else ""
                ps    = self._f_md.render(f"{sign}{gs.score_delta} pts", True, rc)
                ps.set_alpha(alpha)
                self._screen.blit(ps, (cx - ps.get_width() // 2, cy + 30))
            return

        # ── Active prompt ─────────────────────────────────────────────────
        if not gs.session_active or not gs.prompt:
            return

        # Prompt colour from first alphabetic word
        key = "".join(c for c in gs.prompt.split()[0] if c.isalpha()).upper()
        pcol = PROMPT_COLOR.get(key, PROMPT_COLOR["DEFAULT"])
        self._c_prompt.set_color(pcol)

        # Fake-out flag
        if gs.is_fake_out:
            ftag = self._f_sm.render("FAKE-OUT — FREEZE!", True, C_ORANGE)
            self._screen.blit(ftag, (cx - ftag.get_width() // 2, self._MID_Y + 14))

        # Big prompt text
        ps = self._c_prompt.get(gs.prompt)
        self._screen.blit(ps, (cx - ps.get_width() // 2, cy - ps.get_height() // 2))

        # Countdown bar
        if gs.prompt_timer > 0:
            mode_dur_key = "boss" if mode == "BOSS" else "reflex"
            total = float(self._cfg.get(mode_dur_key, {}).get("prompt_duration_sec", 2.5))
            ratio = max(0.0, min(1.0, gs.prompt_timer / total))
            bar_y = cy + ps.get_height() // 2 + 20
            bar_w = self._CW - 60
            bar_x = self._CX + 30
            bar_h = 16
            # Track
            pygame.draw.rect(self._screen, C_PANEL2, (bar_x, bar_y, bar_w, bar_h), border_radius=6)
            # Fill — colour shifts from green → yellow → red
            if ratio > 0.5:
                bc = C_GREEN
            elif ratio > 0.25:
                bc = C_YELLOW
            else:
                bc = C_RED
            fill_w = int(bar_w * ratio)
            if fill_w > 0:
                pygame.draw.rect(self._screen, bc, (bar_x, bar_y, fill_w, bar_h), border_radius=6)
            pygame.draw.rect(self._screen, C_BORDER, (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=6)

        # Progress indicator
        if gs.prompt_total > 0:
            prog = self._f_xs.render(f"Prompt {gs.prompt_index} / {gs.prompt_total}", True, C_DIM)
            self._screen.blit(prog, (cx - prog.get_width() // 2,
                                      self._BOT_Y - 24))

    # ── Right: session stats ──────────────────────────────────────────────────

    def _draw_stats_panel(self, gs) -> None:
        x   = self._RX + 18
        y   = self._MID_Y + 20

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

        # Hits / Misses
        self._screen.blit(self._c_hits.get(f"HIT   {gs.hits:>4}"),  (x, y)); y += 26
        self._screen.blit(self._c_misses.get(f"MISS  {gs.misses:>4}"), (x, y)); y += 36

        # Max combo
        mc = self._f_sm.render(f"MAX COMBO  ×{gs.max_combo}", True, C_GOLD)
        self._screen.blit(mc, (x, y)); y += 34

        # Calibration status
        cal_t = "CALIBRATED ✓" if gs.calibrated else "NOT CALIBRATED"
        cal_c = C_GREEN if gs.calibrated else C_YELLOW
        cs = self._f_xs.render(cal_t, True, cal_c)
        self._screen.blit(cs, (x, y)); y += 26

        # Elapsed timer
        mins = int(gs.timer) // 60
        secs = int(gs.timer) % 60
        ts = self._f_xs.render(f"TIME  {mins:02d}:{secs:02d}", True, C_DIM)
        self._screen.blit(ts, (x, y)); y += 28

        # Status message
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
            h1 = self._f_lg.render("CALIBRATION", True, C_YELLOW)
            h2 = self._f_md.render("Hold the wand FLAT and STILL", True, C_WHITE)
            h3 = self._f_sm.render("Starting in a moment …", True, C_DIM)
            for i, s in enumerate((h1, h2, h3)):
                self._screen.blit(s, (cx - s.get_width() // 2, cy - 80 + i * 55))

        elif phase == "COLLECT":
            n    = cal_mode.samples_collected
            tot  = cal_mode.total_samples
            prog = cal_mode.progress

            h1   = self._f_lg.render("CALIBRATING …", True, C_YELLOW)
            self._screen.blit(h1, (cx - h1.get_width() // 2, cy - 110))

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
            h1 = self._f_lg.render("CALIBRATION COMPLETE ✓", True, C_GREEN)
            self._screen.blit(h1, (cx - h1.get_width() // 2, cy - 80))

            if cal_mode.cal_result:
                cal = cal_mode.cal_result
                ao  = cal["accel_offset"]
                lines = [
                    f"accel x={ao['x']:+.4f}  y={ao['y']:+.4f}  z={ao['z']:+.4f}",
                    "Saved to config/calibration.yaml",
                ]
                for i, line in enumerate(lines):
                    ls = self._f_sm.render(line, True, C_DIM)
                    self._screen.blit(ls, (cx - ls.get_width() // 2, cy + i * 28))

            h3 = self._f_sm.render("Press any key to continue …", True, C_GREY)
            self._screen.blit(h3, (cx - h3.get_width() // 2, cy + 100))

    # ── Paused screen ─────────────────────────────────────────────────────────

    def _draw_paused(self, gs) -> None:
        cx, cy = self._W // 2, self._H // 2
        s1 = self._f_lg.render("⏸  PAUSED", True, C_YELLOW)
        s2 = self._f_sm.render("Press ENTER to resume  |  ESC to quit session", True, C_DIM)
        self._screen.blit(s1, (cx - s1.get_width() // 2, cy - 30))
        self._screen.blit(s2, (cx - s2.get_width() // 2, cy + 30))

    # ── Debug overlay ─────────────────────────────────────────────────────────

    def _draw_debug(self, gs) -> None:
        """Semi-transparent overlay with raw sensor and axis mapping data."""
        bx, by, bw, bh = 10, self._TOP_H + 6, 370, 220
        ov = pygame.Surface((bw, bh), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 185))
        self._screen.blit(ov, (bx, by))
        pygame.draw.rect(self._screen, C_BORDER, (bx, by, bw, bh), width=1)

        t = gs.tilt
        cfg_t = self._cfg.get("mpu6050", self._cfg.get("tilt", {}))
        lines = [
            ("DEBUG OVERLAY", C_YELLOW),
            (f"  game  roll={t.get('roll',0):>+7.1f}°  pitch={t.get('pitch',0):>+7.1f}°", C_TEAL),
            (f"  raw   roll={t.get('raw_roll',0):>+7.1f}°  pitch={t.get('raw_pitch',0):>+7.1f}°", C_GREY),
            (f"  accel_mag = {t.get('accel_mag',1.0):.3f} g", C_DIM),
            (f"  swap_axes={cfg_t.get('swap_axes', False)}"
             f"  inv_x={cfg_t.get('invert_x', False)}"
             f"  inv_y={cfg_t.get('invert_y', False)}", C_DIM),
            (f"  deadzone={cfg_t.get('deadzone_deg',4)}°"
             f"  thresh={cfg_t.get('threshold_deg',22)}°"
             f"  sens={cfg_t.get('sensitivity',1.0)}", C_DIM),
            (f"  mode={gs.mode.name}  cal={gs.calibrated}"
             f"  combo={gs.combo}  threat={gs.threat_level}", C_DIM),
            (f"  FPS={self._fps_val:.1f}", C_GREEN),
        ]
        for i, (txt, col) in enumerate(lines):
            s = self._f_xs.render(txt, True, col)
            self._screen.blit(s, (bx + 6, by + 6 + i * 24))

    # ── Screen flash ──────────────────────────────────────────────────────────

    def _draw_flash(self, gs) -> None:
        if gs.result_flash_timer <= 0:
            return
        result = gs.last_prompt_result
        if result == "HIT":
            col = (0, 160, 60)
        elif result in ("MISS", "FAKE"):
            col = (160, 0, 0)
        else:
            return
        # Intensity ramps down with timer
        alpha = min(60, int(gs.result_flash_timer * 220))
        self._flash.fill((*col, alpha))
        self._screen.blit(self._flash, (0, 0))
