"""Shared oxblood palette, typography and display scaling for DSP Studio."""

# ---- palette -------------------------------------------------------------
BG        = "#100c0e"
PANEL     = "#1b1417"
PANEL_2   = "#281c21"
STROKE    = "#3a272e"
STROKE_HI = "#64404b"

TXT       = "#f3e9e9"
TXT_DIM   = "#bca7ad"
TXT_MUTE  = "#967e87"

ACCENT    = "#e35b70"
CYAN      = ACCENT      # compatibility names used by the processing panels
MAGENTA   = "#f192a3"
VIOLET    = "#bf8fa7"
LIME      = "#d5b99a"
AMBER     = "#dca86a"
RED       = "#ff6d80"
GREEN     = "#92b5a1"   # reserved for successful results

GRID      = "#33242b"
SIG_ORIG  = "#d4c4ca"
SIG_PROC  = ACCENT
SIG_NOISE = AMBER

# ---- type ----------------------------------------------------------------
FONT       = "Segoe UI"
FONT_MONO  = "Consolas"

F_TITLE    = (FONT, 17, "bold")
F_H1       = (FONT, 13, "bold")
F_H2       = (FONT, 10, "bold")
F_BODY     = (FONT, 9)
F_SMALL    = (FONT, 8)
F_LABEL    = (FONT, 8, "bold")
F_MONO     = (FONT_MONO, 9)
F_MONO_S   = (FONT_MONO, 8)


# ---- canvas drawing helpers ---------------------------------------------
def round_rect(cv, x1, y1, x2, y2, r=10, **kw):
    """Draw a rounded rectangle polygon on a tk.Canvas."""
    r = min(r, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return cv.create_polygon(pts, smooth=True, splinesteps=24, **kw)


def _hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(c1, c2, t):
    """Blend c1 -> c2 by t in [0,1] (t=0 -> c1)."""
    a, b = _hex2rgb(c1), _hex2rgb(c2)
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


mix = _mix


# ---- responsive / high-DPI scaling ---------------------------------------
# The app is DPI-aware (see main.py), so on a 200% display Tk hands us the
# real 2880x1920 surface at 192 DPI instead of a blurry 2x-stretched bitmap.
# Text and widget dimensions use one shared pixel scale; Matplotlib's backend
# applies its own pixel ratio to a 96 DPI base figure.
COMPACT = False
SCALE = 1.0          # pixel scale (includes the DPI factor)
DPI = 96.0
DPI_FACTOR = 1.0
MPL_DPI = 96         # TkAgg applies the display pixel ratio itself, exactly once

# Readability bump in points, added to every font. 0 is the default,
# 1 or 2 provides larger presentation/projector sizing. One number to
# change if the interface reads too small or too large.
UI_FONT_STEP = 0
FONT_STEP = UI_FONT_STEP


def apply_scale(screen_h, screen_w=1920, dpi=96.0, font_step=None):
    """Pick fonts and a pixel scale from the screen size and its DPI."""
    global COMPACT, SCALE, DPI, DPI_FACTOR, MPL_DPI, FONT_STEP
    global F_TITLE, F_H1, F_H2, F_BODY, F_SMALL, F_LABEL, F_MONO, F_MONO_S

    DPI = float(dpi or 96.0)
    DPI_FACTOR = max(1.0, DPI / 96.0)
    MPL_DPI = 96
    font_step = UI_FONT_STEP if font_step is None else font_step
    FONT_STEP = font_step

    # the compact decision is about usable area, so judge it in logical pixels
    logical_h = screen_h / DPI_FACTOR
    logical_w = screen_w / DPI_FACTOR
    COMPACT = logical_h < 820 or logical_w < 1300
    SCALE = (0.90 if COMPACT else 1.0) * DPI_FACTOR

    # Negative Tk sizes are pixels: text follows the same scale as its widget.
    # This also prevents a later TkAgg map event from changing control fonts.
    F_TITLE = font(18, "bold")
    F_H1 = font(13, "bold")
    F_H2 = font(9, "bold")
    F_BODY = font(9.5)
    F_SMALL = font(8)
    F_LABEL = font(8, "bold")
    F_MONO = font(9, mono=True)
    F_MONO_S = font(8, mono=True)
    return COMPACT


def ui(px):
    """Scale a pixel dimension for the current screen and DPI."""
    return int(round(px * SCALE))


def font(points, weight=None, mono=False):
    family = FONT_MONO if mono else FONT
    size = -max(9, ui((points + FONT_STEP) * 96 / 72))
    return (family, size, weight) if weight else (family, size)


def fh(inches):
    """Scale a Matplotlib figure height (inches; DPI is applied separately)."""
    return inches * (0.9 if COMPACT else 1.0)


def fs(points):
    """Scale a Matplotlib font size (points) for readability."""
    return (points + FONT_STEP) * (0.9 if COMPACT else 1.0)
