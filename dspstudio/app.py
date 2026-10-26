"""DSP Studio - application shell (splash, header, nav rail, explain drawer)."""
import tkinter as tk
from . import theme as T
from .widgets import InfoPanel, NeonButton

WELCOME = [
    ("h", "Welcome to DSP Studio"),
    ("", "Every panel follows the same chain, left to right:"),
    ("eq", "source  ->  degrade  ->  denoise  ->  filter  ->  enhance"),
    ("", "Set the controls on the left; the plots on the right update as you "
         "go, and the numbers are measured against the clean reference."),
    ("step", "1.  Pick a panel"),
    ("", "Click the rail on the left, or press 1 to 4: Audio, Speech, Image, "
         "Video."),
    ("step", "2.  Start from a preset"),
    ("", "The QUICK START buttons at the top of a panel set up a whole "
         "scenario in one click - hiss removal, hum removal, photo restore. "
         "Then adjust anything you like."),
    ("step", "3.  Read what it did"),
    ("", "MEASUREMENTS shows SNR or PSNR before and after; the delta chip is "
         "green when the processing helped. Press Space to A/B the comparison "
         "pane."),
    ("step", "4.  Ask what an algorithm is"),
    ("", "Select any algorithm and this drawer shows its definition, formula "
         "and what each knob changes. Hover a control for a quick tip."),
    ("step", "5.  Hand in the result"),
    ("", "Ctrl+R writes a PDF of the current panel - configuration, metrics "
         "and every figure. Ctrl+S saves the processed signal itself."),
    ("dim", "Press F1 any time to open or close this drawer."),
]

APP_NAME = "DSP Studio"
APP_SUB = "CPE07A Finals Laboratory Act"


class _NullSplash:
    """Stand-in used by the layout tests, which build the app invisibly."""

    def status(self, msg):
        pass

    def destroy(self):
        pass


class Splash(tk.Toplevel):
    """Loading window shown while the DSP engines and panels are built."""

    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        w, h = T.ui(460), T.ui(230)
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry("%dx%d+%d+%d" % (w, h, x, y))
        self.configure(bg=T.STROKE)
        self.cv = tk.Canvas(self, bg=T.BG, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True, padx=1, pady=1)
        self.msg = "starting..."
        self._draw()

    def status(self, msg):
        self.msg = msg
        self._draw()
        self.update()

    def _draw(self):
        c = self.cv
        c.delete("all")
        w, h = T.ui(458), T.ui(228)
        for i, size in enumerate((8, 16, 24, 28, 24, 16, 8)):
            a = T.ui(size)
            x = w / 2 - T.ui(60) + i * T.ui(20)
            c.create_line(x, T.ui(74) - a, x, T.ui(74) + a,
                          fill=T.mix(T.CYAN, T.MAGENTA, i / 6.0),
                          width=T.ui(8), capstyle="round")
        c.create_text(w / 2, T.ui(128), text=APP_NAME, fill=T.TXT, font=T.F_TITLE)
        c.create_text(w / 2, T.ui(154), text=APP_SUB, fill=T.TXT_DIM,
                      font=T.F_SMALL)
        c.create_text(w / 2, T.ui(196), text=self.msg, fill=T.CYAN,
                      font=T.F_SMALL)


class HeaderBar(tk.Canvas):
    """Simple title strip with access to the algorithm reference."""

    def __init__(self, master, app):
        super().__init__(master, height=T.ui(66), bg=T.BG, highlightthickness=0,
                         bd=0)
        self.app = app
        self.bind("<Configure>", lambda e: self._draw())
        self.help_button = NeonButton(self, "REFERENCE  ·  F1", lambda: app.drawer.toggle(),
                                      T.ACCENT, width=138, height=32)
        self.help_button.place(relx=1, rely=0.5, x=-T.ui(16), anchor="e")

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        T.round_rect(self, 0, 0, w, h + T.ui(12), T.ui(14), fill=T.PANEL,
                     outline=T.STROKE)
        for i, size in enumerate((10, 15, 19, 15, 10)):
            a = T.ui(size)
            x = T.ui(22) + i * T.ui(8)
            self.create_line(x, h / 2 - a, x, h / 2 + a,
                             fill=T.mix(T.CYAN, T.MAGENTA, i / 4.0),
                             width=T.ui(5), capstyle="round")
        self.create_text(T.ui(74), h / 2 - T.ui(10), text=APP_NAME, anchor="w",
                         fill=T.TXT, font=T.F_TITLE)
        self.create_text(T.ui(76), h / 2 + T.ui(14), text=APP_SUB,
                         anchor="w", fill=T.TXT_DIM, font=T.F_SMALL)


class NavRail(tk.Canvas):
    """Vertical tab rail with a sliding accent indicator."""

    def __init__(self, master, items, on_select):
        self.cell = T.ui(82)
        super().__init__(master, width=T.ui(88), bg=T.BG, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.items = items              # [(key, label, glyph, accent)]
        self.on_select = on_select
        self.active = 0
        self._hover = -1
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(-1))
        self.bind("<Configure>", lambda e: self._draw())

    def _index_at(self, y):
        i = int((y - T.ui(12)) // self.cell)
        return i if 0 <= i < len(self.items) else -1

    def _set_hover(self, i):
        if i != self._hover:
            self._hover = i
            self._draw()

    def _motion(self, e):
        self._set_hover(self._index_at(e.y))

    def _click(self, e):
        i = self._index_at(e.y)
        if i >= 0:
            self.select(i)

    def select(self, i):
        self.active = i
        self._draw()
        self.on_select(self.items[i][0])

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        T.round_rect(self, 0, 0, w, h, T.ui(14), fill=T.PANEL, outline=T.STROKE)
        box = self.cell - T.ui(10)
        for i, (key, label, glyph, accent) in enumerate(self.items):
            y = T.ui(12) + i * self.cell
            on = i == self.active
            hov = i == self._hover
            m = T.ui(7)
            if on:
                T.round_rect(self, m, y, w - m, y + box, T.ui(10),
                             fill=T.mix(T.PANEL, accent, 0.16),
                             outline=T.mix(accent, T.PANEL, 0.3))
                self.create_rectangle(T.ui(2), y + box * 0.25, T.ui(5),
                                      y + box * 0.75, fill=accent, outline="")
            elif hov:
                T.round_rect(self, m, y, w - m, y + box, T.ui(10), fill=T.PANEL_2,
                             outline="")
            col = accent if on else (T.TXT_DIM if hov else T.TXT_MUTE)
            self.create_text(w / 2, y + box * 0.36, text=glyph, fill=col,
                             font=T.font(19))
            for li, part in enumerate(label.split("\n")):
                self.create_text(w / 2, y + box * 0.72 + li * T.ui(12), text=part,
                                 fill=col, font=T.F_LABEL)
            self.create_text(w - m, y + T.ui(11), text=str(i + 1), anchor="e",
                             fill=T.mix(col, T.PANEL, 0.6), font=T.F_SMALL)


class StatusBar(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, height=T.ui(32), bg=T.BG, highlightthickness=0,
                         bd=0)
        self.msg = "Ready."
        self.color = T.TXT_DIM
        self.hint = "F1 explain  ·  1-4 switch panel  ·  Space A/B  ·  " \
                    "Ctrl+R report  ·  Esc quit"
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, msg, color=None):
        self.msg = msg
        self.color = color or T.TXT_DIM
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        T.round_rect(self, 0, -T.ui(12), w, h, T.ui(12), fill=T.PANEL,
                     outline=T.STROKE)
        r = T.ui(4)
        self.create_oval(T.ui(16) - r, h / 2 - r, T.ui(16) + r, h / 2 + r,
                         fill=self.color, outline="")
        self.create_text(T.ui(30), h / 2, text=self.msg, anchor="w",
                         fill=self.color, font=T.F_SMALL)
        self.create_text(w - T.ui(16), h / 2, anchor="e", fill=T.TXT_MUTE,
                         font=T.F_SMALL, text=self.hint)


class ExplainDrawer(tk.Frame):
    """Right-hand drawer holding the algorithm reference for the active control."""

    def __init__(self, master, app):
        super().__init__(master, bg=T.BG, width=T.ui(360))
        self.app = app
        self.open = False
        self.bg = tk.Canvas(self, bg=T.BG, highlightthickness=0, bd=0)
        self.bg.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg.bind("<Configure>", self._draw_bg)

        head = tk.Frame(self, bg=T.PANEL)
        head.place(x=T.ui(14), y=T.ui(12), relwidth=1, width=-T.ui(28),
                   height=T.ui(32))
        tk.Label(head, text="ALGORITHM REFERENCE", bg=T.PANEL, fg=T.TXT,
                 font=T.F_H2).pack(side="left")
        NeonButton(head, "CLOSE", self.hide, T.RED, width=70,
                   height=26).pack(side="right")

        self.info = InfoPanel(self, accent=T.CYAN)
        self.info.place(x=T.ui(16), y=T.ui(54), relwidth=1, relheight=1,
                        width=-T.ui(32), height=-T.ui(68))
        self.set_blocks(WELCOME)

    def _draw_bg(self, _=None):
        c = self.bg
        c.delete("all")
        w, h = self.bg.winfo_width(), self.bg.winfo_height()
        if w < 4:
            return
        T.round_rect(c, 1, 1, w - 2, h - 2, 12, fill=T.PANEL, outline=T.STROKE)
        c.create_line(T.ui(14), T.ui(48), w - T.ui(14), T.ui(48),
                      fill=T.STROKE)

    def set_blocks(self, blocks):
        self.info.set_blocks(blocks)

    def show(self):
        if not self.open:
            self.place(relx=1, y=0, relheight=1, width=T.ui(370), anchor="ne")
            self.lift()
            self.open = True

    def hide(self):
        if self.open:
            self.place_forget()
            self.open = False

    def toggle(self):
        self.hide() if self.open else self.show()


class DSPStudio(tk.Tk):
    def __init__(self, show_window=True, show_splash=True):
        super().__init__()
        self.withdraw()
        dpi = float(self.winfo_fpixels("1i"))
        T.apply_scale(self.winfo_screenheight(), self.winfo_screenwidth(), dpi)
        try:                      # keep Tk's own font scaling honest
            self.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass

        self.title("%s - %s" % (APP_NAME, APP_SUB))
        self.configure(bg=T.BG)
        self.geometry("%dx%d" % (T.ui(1460), T.ui(880)))
        self.minsize(T.ui(1100), T.ui(680))
        self._set_icon()

        splash = Splash(self) if show_splash else _NullSplash()
        splash.status("loading DSP engines...")

        HeaderBar(self, self).pack(fill="x", padx=T.ui(12), pady=(T.ui(10), T.ui(8)))

        mid = tk.Frame(self, bg=T.BG)
        mid.pack(fill="both", expand=True, padx=T.ui(12))

        items = [("audio", "AUDIO", "♫", T.ACCENT),
                 ("speech", "SPEECH", "◔", T.ACCENT),
                 ("image", "IMAGE", "◰", T.ACCENT),
                 ("video", "VIDEO", "▶", T.ACCENT)]
        self.rail = NavRail(mid, items, self.show)
        self.rail.pack(side="left", fill="y", padx=(0, 10))

        self.drawer = ExplainDrawer(mid, self)       # packed on demand (right)

        self.stack = tk.Frame(mid, bg=T.BG)
        self.stack.pack(side="left", fill="both", expand=True)

        self.status_bar = StatusBar(self)
        self.status_bar.pack(fill="x", padx=12, pady=(8, 10))

        # panels are imported lazily so the splash can report progress
        from .panels.audio_panel import AudioPanel
        from .panels.speech_panel import SpeechPanel
        from .panels.image_panel import ImagePanel
        from .panels.video_panel import VideoPanel

        self.panels = {}
        for key, cls, msg in [("audio", AudioPanel, "building audio workbench..."),
                              ("speech", SpeechPanel, "building speech analyser..."),
                              ("image", ImagePanel, "building image lab..."),
                              ("video", VideoPanel, "building video processor...")]:
            splash.status(msg)
            self.panels[key] = cls(self.stack, self)

        self.current = None
        self.rail.select(0)
        self._bind_keys()
        self.drawer.set_blocks(WELCOME)

        splash.destroy()
        if show_window:
            self.deiconify()
            try:
                self.state("zoomed")
            except Exception:
                pass
            self._style_titlebar()
        self.status("Ready - %s layout. Press F1 for the algorithm reference."
                    % ("compact" if T.COMPACT else "full"), T.GREEN)

    # ------------------------------------------------------------ chrome --
    def _style_titlebar(self):
        """Match the native Windows title bar to the workbench, when supported."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
            color = ctypes.c_int(int(T.BG[5:7] + T.BG[3:5] + T.BG[1:3], 16))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)
        except (AttributeError, OSError):
            pass

    def _set_icon(self):
        """Draw the app icon at runtime so no binary asset is needed."""
        try:
            from PIL import Image, ImageDraw, ImageTk
            im = Image.new("RGBA", (64, 64), T.BG)
            d = ImageDraw.Draw(im)
            bars = [(14, 22), (24, 12), (34, 6), (44, 16)]
            cols = [T.ACCENT, T.MAGENTA, T.RED, T.VIOLET]
            for (x, a), col in zip(bars, cols):
                d.rounded_rectangle([x, 32 - a, x + 6, 32 + a], 3, fill=col)
            self._icon = ImageTk.PhotoImage(im)
            self.iconphoto(True, self._icon)
        except Exception:
            pass

    def _bind_keys(self):
        for i in range(len(self.rail.items)):
            self.bind("<Key-%d>" % (i + 1), lambda e, k=i: self.rail.select(k))
        self.bind("<F1>", lambda e: self.drawer.toggle())
        self.bind("<Control-r>", lambda e: self._call_current("export_report"))
        self.bind("<Control-s>", lambda e: self._call_current("save_output"))
        self.bind("<space>", lambda e: self._call_current("toggle_ab"))
        self.bind("<Escape>", lambda e: self.quit_app())
        self.protocol("WM_DELETE_WINDOW", self.quit_app)

    def _call_current(self, method):
        fn = getattr(self.current, method, None)
        if callable(fn):
            fn()
        return "break"

    # ------------------------------------------------------------- panels --
    def show(self, key):
        if self.current:
            self.current.pack_forget()
        self.current = self.panels[key]
        self.current.pack(fill="both", expand=True)
        fn = getattr(self.current, "on_show", None)
        if callable(fn):
            fn()

    def explain(self, blocks, open_drawer=False):
        """Push algorithm documentation into the drawer."""
        self.drawer.set_blocks(blocks)
        if open_drawer:
            self.drawer.show()

    def status(self, msg, color=None):
        self.status_bar.set(msg, color)
        self.update_idletasks()

    def quit_app(self):
        for p in self.panels.values():
            fn = getattr(p, "shutdown", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        self.destroy()
