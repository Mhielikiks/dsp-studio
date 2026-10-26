"""Hand-drawn (tk.Canvas) widget set giving DSP Studio its instrument look.

Every hard-coded dimension goes through T.ui() so the toolkit keeps its
proportions on a high-DPI screen instead of being bitmap-stretched by Windows.
"""
import tkinter as tk
from tkinter import font as tkfont

from . import theme as T


def fit_text(widget, text, font, width):
    """Ellipsize a single line without letting it overwrite adjacent content."""
    text = str(text)
    measure = tkfont.Font(root=widget, font=font).measure
    if measure(text) <= width:
        return text
    while text and measure(text + "…") > width:
        text = text[:-1]
    return text + "…" if text else ""


class SlimScrollbar(tk.Canvas):
    """A quiet scrollbar that uses the same palette on Windows and Linux."""

    def __init__(self, master, orient="vertical", command=None, width=9,
                 bg=T.BG, **kw):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         **({"width": T.ui(width)} if orient == "vertical"
                            else {"height": T.ui(width)}))
        self.vertical = orient == "vertical"
        self.command = command
        self.first, self.last = 0.0, 1.0
        self._grab = 0.0
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _length(self):
        return max(1, self.winfo_height() if self.vertical else self.winfo_width())

    def _draw(self):
        self.delete("all")
        if self.last - self.first >= 0.999:
            return
        a, b = self.first * self._length(), self.last * self._length()
        if self.vertical:
            T.round_rect(self, 2, a, self.winfo_width() - 2, b, T.ui(3),
                         fill=T.STROKE_HI, outline="")
        else:
            T.round_rect(self, a, 2, b, self.winfo_height() - 2, T.ui(3),
                         fill=T.STROKE_HI, outline="")

    def _press(self, event):
        pos = (event.y if self.vertical else event.x) / self._length()
        self._grab = pos - self.first if self.first <= pos <= self.last else 0.0
        self._drag(event)

    def _drag(self, event):
        pos = (event.y if self.vertical else event.x) / self._length()
        if self.command:
            self.command("moveto", max(0.0, min(1.0, pos - self._grab)))


class PlotGrid(tk.Frame):
    """Chart workspace with readable minimum sizes and overflow scrolling."""

    def __init__(self, master, rows=2):
        super().__init__(master, bg=T.BG)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=T.BG, bd=0, highlightthickness=0,
                                width=1, height=1, yscrollincrement=T.ui(24))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar = SlimScrollbar(self, command=self.canvas.yview)
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar = SlimScrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.body = tk.Frame(self.canvas, bg=T.BG)
        self._item = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self._min_height = T.ui(rows * (250 if rows == 3 else 310))
        self._min_width = T.ui(840)
        self.canvas.bind("<Configure>", self._resize)
        attach_scroll(self.canvas)

    def _resize(self, event):
        width = max(event.width, self._min_width)
        height = max(event.height, self._min_height)
        self.canvas.itemconfigure(self._item, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))


def attach_scroll(canvas):
    """Route the mouse wheel to `canvas` only while the pointer is over it."""
    def on_wheel(e):
        widget = e.widget
        while widget is not None:
            if widget is canvas:
                if canvas.yview() != (0.0, 1.0):
                    canvas.yview_scroll(-int(e.delta / 120), "units")
                return "break"
            widget = getattr(widget, "master", None)
    # A single ancestor check handles embedded children without stealing the
    # wheel from the other independently scrollable columns.
    canvas.winfo_toplevel().bind("<MouseWheel>", on_wheel, add="+")


def attach_scroll_text(text_widget):
    """Mouse wheel support for a read-only Text widget."""
    def on_wheel(e):
        text_widget.yview_scroll(-int(e.delta / 120), "units")
        return "break"

    text_widget.bind("<MouseWheel>", on_wheel)


class Card(tk.Frame):
    """A rounded, bordered panel with an optional header strip."""

    def __init__(self, master, title=None, accent=T.CYAN, pad=12, **kw):
        super().__init__(master, bg=T.BG, highlightthickness=0, **kw)
        self._accent = T.ACCENT
        self.bg = tk.Canvas(self, bg=T.BG, highlightthickness=0, bd=0)
        self.bg.place(x=0, y=0, relwidth=1, relheight=1)

        self.head_h = T.ui(36) if title else 0
        self.title = title
        pad = self._pad = T.ui(pad)
        top = self.head_h + (T.ui(6) if title else pad)
        self.body = tk.Frame(self, bg=T.PANEL, highlightthickness=0)
        self._place = dict(x=pad, y=top, relwidth=1, relheight=1,
                           width=-2 * pad, height=-(top + pad))
        self.body.place(**self._place)
        self.expanded = True
        self._full_h = None
        self.bind("<Configure>", self._redraw)
        if title:                      # the header folds the card away
            self.bg.bind("<Button-1>", self._header_click)
            self.bg.configure(cursor="hand2")

    def _header_click(self, e):
        if e.y <= self.head_h:
            self.toggle()

    def toggle(self):
        self.set_expanded(not self.expanded)

    def set_expanded(self, on):
        """Fold a control card down to its header to save column space."""
        if not self.title or on == self.expanded:
            return
        self.expanded = on
        if on:
            self.body.place(**self._place)
            if self._full_h:
                self.configure(height=self._full_h)
        else:
            self._full_h = self.winfo_height() or self._full_h
            self.body.place_forget()
            self.configure(height=self.head_h + T.ui(6))
        self.pack_propagate(False)
        self._redraw()

    def fit(self, extra=0):
        """Size the card to whatever was packed into its body.

        Fixed heights break as soon as the font size changes, so every control
        card measures its own content instead.
        """
        self.update_idletasks()
        total = 0
        for ch in self.body.winfo_children():
            total += ch.winfo_reqheight()
            try:
                info = ch.pack_info()
            except Exception:
                continue
            total += sum(int(v) for v in str(info.get("pady", 0)).split()
                         if v.lstrip("-").isdigit())
        pad = self._pad
        top = self.head_h + (T.ui(6) if self.title else pad)
        self._full_h = top + total + pad + T.ui(extra)
        self.configure(height=self._full_h)
        self.pack_propagate(False)
        return self

    def _redraw(self, _=None):
        c, w, h = self.bg, self.winfo_width(), self.winfo_height()
        c.delete("all")
        if w < 4 or h < 4:
            return
        T.round_rect(c, 1, 1, w - 2, h - 2, T.ui(12), fill=T.PANEL,
                     outline=T.STROKE, width=1)
        if self.title:
            m = T.ui(14)
            c.create_line(m, self.head_h, w - m, self.head_h, fill=T.STROKE)
            cy = self.head_h / 2
            c.create_rectangle(m, cy - T.ui(7), m + T.ui(3), cy + T.ui(7),
                               fill=self._accent, outline="")
            label = fit_text(c, self.title.upper(), T.F_H2, w - T.ui(66))
            c.create_text(m + T.ui(12), cy, text=label, anchor="w",
                          fill=T.TXT, font=T.F_H2)
            # fold chevron
            cx, s_ = w - T.ui(18), T.ui(4)
            if self.expanded:
                c.create_line(cx - s_, cy - s_ / 2, cx, cy + s_ / 2,
                              cx + s_, cy - s_ / 2, fill=T.TXT_MUTE,
                              width=T.ui(2), capstyle="round", joinstyle="round")
            else:
                c.create_line(cx - s_, cy + s_ / 2, cx, cy - s_ / 2,
                              cx + s_, cy + s_ / 2, fill=T.TXT_MUTE,
                              width=T.ui(2), capstyle="round", joinstyle="round")


class NeonButton(tk.Canvas):
    """Flat rounded button with hover glow."""

    def __init__(self, master, text, command=None, accent=T.CYAN,
                 width=120, height=30, filled=False, icon=None, font=None,
                 bg=T.PANEL, scaled=True):
        if scaled:
            width, height = T.ui(width), T.ui(height)
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.text, self.command, self.accent = text, command, accent
        self.filled, self.icon = filled, icon
        self.font = font or T.F_LABEL
        self._hover = False
        self._disabled = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def set_text(self, text):
        self.text = text
        self._draw()

    def _draw(self, sunken=False):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w, h = int(self["width"]), int(self["height"])
        a = self.accent
        if self._disabled:
            fill, outline, fg = T.PANEL_2, T.STROKE, T.TXT_MUTE
        elif self.filled:
            fill = T.mix(a, T.BG, 0.12 if self._hover else 0.28)
            outline, fg = a, T.TXT
        else:
            fill = T.mix(T.PANEL, a, 0.18 if self._hover else 0.07)
            outline = T.mix(a, T.PANEL, 0.0 if self._hover else 0.45)
            fg = a if self._hover else T.mix(a, T.TXT, 0.3)
        off = T.ui(1) if sunken else 0
        r = T.ui(9)
        if self._hover and not self._disabled:
            T.round_rect(self, 1, 1 + off, w - 1, h - 1 + off, r + T.ui(1),
                         fill="", outline=T.mix(a, T.PANEL, 0.72), width=T.ui(3))
        T.round_rect(self, T.ui(2), T.ui(2) + off, w - T.ui(3), h - T.ui(3) + off,
                     r, fill=fill, outline=outline, width=1)
        label = "%s  %s" % (self.icon, self.text) if self.icon else self.text
        self.create_text(w / 2, h / 2 + off, text=label, fill=fg, font=self.font)

    def _on_enter(self, _):
        if not self._disabled:
            self._hover = True
            self._draw()

    def _on_leave(self, _):
        self._hover = False
        self._draw()

    def _on_press(self, _):
        if not self._disabled:
            self._draw(sunken=True)

    def _on_release(self, _):
        if self._disabled:
            return
        self._draw()
        if self.command:
            self.command()


class Slider(tk.Canvas):
    """Horizontal slider with a live value read-out (linear or log mapping).

    The whole row is a hit target; the wheel and arrow keys nudge the value, so
    it does not need pixel-accurate dragging.
    """

    def __init__(self, master, label, lo, hi, value=None, step=None,
                 fmt="{:.2f}", unit="", accent=T.CYAN, command=None,
                 width=250, height=44, log=False, bg=T.PANEL):
        super().__init__(master, width=T.ui(width), height=T.ui(height), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.label, self.lo, self.hi = label, float(lo), float(hi)
        self.step, self.fmt, self.unit = step, fmt, unit
        self.accent, self.command, self.log = accent, command, log
        self.val = float(value if value is not None else lo)
        self._hover = False
        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._click)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Left>", lambda e: self._nudge(-1))
        self.bind("<Right>", lambda e: self._nudge(1))
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _to_t(self, v):
        import math
        if self.log:
            return (math.log10(max(v, 1e-9)) - math.log10(self.lo)) / \
                   (math.log10(self.hi) - math.log10(self.lo))
        return (v - self.lo) / (self.hi - self.lo)

    def _from_t(self, t):
        import math
        t = min(1.0, max(0.0, t))
        if self.log:
            return 10 ** (math.log10(self.lo) + t *
                          (math.log10(self.hi) - math.log10(self.lo)))
        return self.lo + t * (self.hi - self.lo)

    def get(self):
        return self.val

    def set(self, v, notify=False):
        v = min(self.hi, max(self.lo, float(v)))
        if self.step:                   # snap to lo, lo+step, ... (3, 5, 7 for odd kernels)
            v = min(self.hi, self.lo + round((v - self.lo) / self.step) * self.step)
        self.val = v
        self._draw()
        if notify and self.command:
            self.command(self.val)

    def _nudge(self, direction):
        span = self.hi - self.lo
        delta = self.step if self.step else span / 100.0
        self.set(self.val + direction * delta, notify=True)
        return "break"

    def _click(self, e):
        w = self.winfo_width()
        m = T.ui(12)
        self.focus_set()
        self.set(self._from_t((e.x - m) / max(1, w - 2 * m)))

    def _release(self, _):
        if self.command:
            self.command(self.val)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        self.create_text(T.ui(2), T.ui(10), text=self.label.upper(), anchor="w",
                         fill=T.TXT if self._hover else T.TXT_DIM, font=T.F_SMALL)
        self.create_text(w - T.ui(2), T.ui(10), anchor="e", fill=self.accent,
                         font=T.F_MONO_S,
                         text=self.fmt.format(self.val) +
                         (" " + self.unit if self.unit else ""))
        m = T.ui(12)
        y = h - T.ui(13)
        tw = T.ui(5)
        self.create_line(m, y, w - m, y, fill=T.STROKE, width=tw, capstyle="round")
        x = m + self._to_t(self.val) * (w - 2 * m)
        if x > m + 1:
            self.create_line(m, y, x, y, fill=self.accent, width=tw,
                             capstyle="round")
        kr = T.ui(10 if self._hover else 9)
        self.create_oval(x - kr, y - kr, x + kr, y + kr,
                         fill=T.mix(self.accent, T.BG, 0.72), outline=self.accent,
                         width=T.ui(2))
        ir = T.ui(3.5)
        self.create_oval(x - ir, y - ir, x + ir, y + ir, fill=self.accent,
                         outline="")


class Dropdown(tk.Canvas):
    """Custom option menu that matches the theme."""

    def __init__(self, master, label, options, value=None, command=None,
                 accent=T.CYAN, width=220, height=46, bg=T.PANEL):
        super().__init__(master, width=T.ui(width), height=T.ui(height), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.label, self.options = label, list(options)
        self.command, self.accent = command, accent
        self.value = value or self.options[0]
        self._hover = False
        self.bind("<Button-1>", self._open)
        self.bind("<Enter>", lambda e: self._hover_set(True))
        self.bind("<Leave>", lambda e: self._hover_set(False))
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _hover_set(self, v):
        self._hover = v
        self._draw()

    def get(self):
        return self.value

    def set(self, v, notify=False):
        self.value = v
        self._draw()
        if notify and self.command:
            self.command(v)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        self.create_text(T.ui(2), T.ui(12), text=self.label.upper(), anchor="w",
                         fill=T.TXT if self._hover else T.TXT_DIM, font=T.F_SMALL)
        y0, y1 = T.ui(21), h - T.ui(2)
        T.round_rect(self, 1, y0, w - 2, y1, T.ui(8),
                     fill=T.mix(T.PANEL_2, self.accent, 0.12 if self._hover else 0.0),
                     outline=self.accent if self._hover else T.STROKE_HI, width=1)
        self.create_text(T.ui(11), (y0 + y1) / 2, text=self.value, anchor="w",
                         fill=T.TXT, font=T.F_BODY)
        cx, cy, s = w - T.ui(15), (y0 + y1) / 2, T.ui(5)
        self.create_polygon(cx - s, cy - s * 0.5, cx + s, cy - s * 0.5,
                            cx, cy + s * 0.7, fill=self.accent, outline="")

    def _open(self, _):
        m = tk.Menu(self, tearoff=0, bg=T.PANEL_2, fg=T.TXT,
                    activebackground=T.STROKE_HI, activeforeground=T.TXT,
                    bd=0, relief="flat", font=T.F_BODY)
        for o in self.options:
            m.add_command(label=o, command=lambda v=o: self.set(v, notify=True))
        m.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height())


class Toggle(tk.Canvas):
    """Switch control. The whole row is clickable."""

    def __init__(self, master, label, value=False, command=None,
                 accent=T.CYAN, width=200, height=26, bg=T.PANEL):
        super().__init__(master, width=T.ui(width), height=T.ui(height), bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.label, self.value = label, bool(value)
        self.command, self.accent = command, accent
        self._hover = False
        self.bind("<Button-1>", lambda e: self.set(not self.value, notify=True))
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _hov(self, v):
        self._hover = v
        self._draw()

    def get(self):
        return self.value

    def set(self, v, notify=False):
        self.value = bool(v)
        self._draw()
        if notify and self.command:
            self.command(self.value)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        cy = h / 2
        tw, th = T.ui(44), T.ui(11)
        x1 = w - tw - T.ui(2)
        T.round_rect(self, x1, cy - th, x1 + tw, cy + th, th,
                     fill=T.mix(T.PANEL_2, self.accent, 0.75 if self.value else 0.0),
                     outline=self.accent if self.value else
                     (T.TXT_DIM if self._hover else T.STROKE_HI), width=1)
        kr = T.ui(8)
        kx = x1 + (tw - T.ui(13) if self.value else T.ui(13))
        self.create_oval(kx - kr, cy - kr, kx + kr, cy + kr,
                         fill=T.BG if self.value else T.TXT_MUTE, outline="")
        self.create_text(T.ui(2), cy, text=self.label, anchor="w",
                         fill=T.TXT if (self.value or self._hover) else T.TXT_DIM,
                         font=T.F_BODY)


class LevelMeter(tk.Canvas):
    """Segmented VU-style meter."""

    def __init__(self, master, width=180, height=16, segments=28, bg=T.PANEL):
        super().__init__(master, width=T.ui(width), height=T.ui(height), bg=bg,
                         highlightthickness=0, bd=0)
        self.segments, self.level = segments, 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set_level(self, v):
        self.level = min(1.0, max(0.0, float(v)))
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        n = self.segments
        sw = w / n
        lit = int(self.level * n)
        for i in range(n):
            t = i / max(1, n - 1)
            col = T.GREEN if t < 0.6 else (T.AMBER if t < 0.85 else T.RED)
            self.create_rectangle(i * sw + 1, 1, (i + 1) * sw - 1, h - 1,
                                  fill=col if i < lit else T.mix(T.PANEL_2, col, 0.08),
                                  outline="")


class Badge(tk.Canvas):
    """Small pill used for status / metric chips."""

    def __init__(self, master, text="", accent=T.CYAN, width=116, height=25,
                 bg=T.PANEL):
        super().__init__(master, width=T.ui(width), height=T.ui(height), bg=bg,
                         highlightthickness=0, bd=0)
        self.text, self.accent = text, accent
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def set(self, text, accent=None):
        self.text = text
        if accent:
            self.accent = accent
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w, h = int(self["width"]), int(self["height"])
        T.round_rect(self, 1, 1, w - 2, h - 2, h / 2,
                     fill=T.mix(T.PANEL, self.accent, 0.16),
                     outline=T.mix(self.accent, T.PANEL, 0.5), width=1)
        self.create_text(w / 2, h / 2, text=self.text, fill=self.accent,
                         font=T.F_SMALL)


class StatRow(tk.Canvas):
    """label .......... value  (monospace read-out)"""

    def __init__(self, master, label, value="--", accent=T.TXT,
                 width=240, height=20, bg=T.PANEL):
        super().__init__(master, width=T.ui(width), height=T.ui(max(height, 18)), bg=bg,
                         highlightthickness=0, bd=0)
        self.label, self.value, self.accent = label, value, accent
        self.tip = Tooltip(self, "%s: %s" % (label, value))
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def set(self, value, accent=None):
        self.value = value
        self.tip.set_text("%s: %s" % (self.label, value))
        if accent:
            self.accent = accent
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w = int(self["width"])
        value_width = tkfont.Font(root=self, font=T.F_MONO_S).measure(str(self.value))
        label = fit_text(self, self.label, T.F_SMALL, w - value_width - T.ui(14))
        self.create_text(0, h / 2, text=label, anchor="w",
                         fill=T.TXT_DIM, font=T.F_SMALL)
        self.create_text(w, h / 2, text=self.value, anchor="e",
                         fill=self.accent, font=T.F_MONO_S)


class Tooltip:
    """Dark hover tooltip. Attach with Tooltip(widget, "text")."""

    _open = None

    def __init__(self, widget, text, delay=420, width=320):
        self.widget, self.text = widget, text
        self.delay, self.width = delay, T.ui(width)
        self._after = None
        self._win = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")

    def set_text(self, text):
        self.text = text

    def _schedule(self, _=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self):
        if self._win or not self.text:
            return
        if Tooltip._open is not None:
            Tooltip._open._hide()
        x = self.widget.winfo_rootx() + T.ui(14)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + T.ui(6)
        self._win = tk.Toplevel(self.widget)
        self._win.wm_overrideredirect(True)
        self._win.configure(bg=T.STROKE_HI)
        lbl = tk.Label(self._win, text=self.text, justify="left", bg=T.PANEL_2,
                       fg=T.TXT, font=T.F_SMALL, wraplength=self.width,
                       padx=T.ui(11), pady=T.ui(8), bd=0)
        lbl.pack(padx=1, pady=1)
        self._win.wm_geometry("+%d+%d" % (x, y))
        try:
            self._win.attributes("-topmost", True)
        except Exception:
            pass
        Tooltip._open = self

    def _hide(self, _=None):
        self._cancel()
        if self._win:
            self._win.destroy()
            self._win = None
        if Tooltip._open is self:
            Tooltip._open = None


class ProgressBar(tk.Canvas):
    """Thin determinate / indeterminate progress strip with a caption."""

    def __init__(self, master, width=260, height=26, accent=T.CYAN, bg=T.PANEL):
        super().__init__(master, width=T.ui(width), height=T.ui(height), bg=bg,
                         highlightthickness=0, bd=0)
        self.accent, self.frac, self.msg = accent, 0.0, ""
        self.active = False
        self._march = 0.0
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def start(self, msg="working..."):
        self.active, self.msg, self.frac = True, msg, 0.0
        self._animate()

    def set(self, frac, msg=None):
        self.frac = max(0.0, min(1.0, float(frac)))
        if msg is not None:
            self.msg = msg
        self._draw()

    def stop(self, msg=""):
        self.active, self.frac, self.msg = False, 0.0, msg
        self._draw()

    def _animate(self):
        if not self.active:
            return
        self._march = (self._march + 0.02) % 1.0
        self._draw()
        self.after(40, self._animate)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            return
        y = h - T.ui(8)
        hw = T.ui(4)
        self.create_text(0, T.ui(10), text=self.msg, anchor="w",
                         fill=self.accent if self.active else T.TXT_MUTE,
                         font=T.F_SMALL)
        T.round_rect(self, 0, y - hw, w, y + hw, hw, fill=T.PANEL_2, outline="")
        if not self.active:
            return
        if self.frac > 0:
            T.round_rect(self, 0, y - hw, max(T.ui(8), w * self.frac), y + hw, hw,
                         fill=self.accent, outline="")
            self.create_text(w, T.ui(10), text="%d%%" % (self.frac * 100),
                             anchor="e", fill=self.accent, font=T.F_MONO_S)
        else:
            run = T.ui(100)
            x = self._march * (w + run) - run
            T.round_rect(self, max(0, x), y - hw, min(w, x + run), y + hw, hw,
                         fill=self.accent, outline="")


class InfoPanel(tk.Frame):
    """Scrollable rich-ish text block used by the algorithm explainer."""

    def __init__(self, master, bg=T.PANEL, accent=T.CYAN):
        super().__init__(master, bg=bg, highlightthickness=0)
        self.accent = accent
        self.txt = tk.Text(self, bg=bg, fg=T.TXT, bd=0, highlightthickness=0,
                           wrap="word", font=T.F_BODY, padx=T.ui(2), pady=T.ui(2),
                           spacing1=T.ui(2), spacing2=T.ui(2), spacing3=T.ui(5),
                           cursor="arrow")
        sb = SlimScrollbar(self, orient="vertical", command=self.txt.yview,
                          bg=T.PANEL, troughcolor=bg, bd=0,
                          highlightthickness=0, width=9)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.txt.tag_configure("h", foreground=accent, font=T.F_H2,
                               spacing1=T.ui(9), spacing3=T.ui(4))
        self.txt.tag_configure("eq", foreground=T.LIME, font=T.F_MONO,
                               lmargin1=T.ui(14), lmargin2=T.ui(14),
                               spacing1=T.ui(4), spacing3=T.ui(4))
        self.txt.tag_configure("dim", foreground=T.TXT_DIM)
        self.txt.tag_configure("key", foreground=T.AMBER, font=T.F_LABEL)
        self.txt.tag_configure("step", foreground=T.CYAN, font=T.F_LABEL,
                               spacing1=T.ui(7))
        self.txt.configure(state="disabled")
        attach_scroll_text(self.txt)

    def set_blocks(self, blocks):
        """blocks: list of (tag, text); tag in {'h','eq','dim','key','step',''}."""
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        for tag, text in blocks:
            self.txt.insert("end", text + "\n", tag if tag else ())
        self.txt.configure(state="disabled")
        self.txt.yview_moveto(0)
