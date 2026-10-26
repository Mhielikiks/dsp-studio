"""Matplotlib canvases themed to match the DSP Studio look."""
import matplotlib
matplotlib.use("TkAgg")
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.ticker import MaxNLocator

from . import theme as T

matplotlib.rcParams["font.family"] = [T.FONT, "DejaVu Sans"]


class _StudioCanvas(FigureCanvasTkAgg):
    def draw(self):
        # A tab may briefly map before its scrollable workspace receives its
        # final geometry. The next Configure event will draw at the real size.
        if self._tkcanvas.winfo_width() < T.ui(80) or self._tkcanvas.winfo_height() < T.ui(80):
            return
        super().draw()


def style_axes(ax, title=None, xlabel=None, ylabel=None, accent=T.TXT_DIM):
    ax.set_facecolor(T.PANEL)
    for side, sp in ax.spines.items():
        sp.set_color(T.STROKE)
        sp.set_linewidth(0.8)
        if side in ("top", "right"):
            sp.set_visible(False)
    ax.tick_params(colors=T.TXT_DIM, labelsize=T.fs(8), length=3, width=0.7)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=3, min_n_ticks=2))
    ax.grid(True, color=T.GRID, linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=accent, fontsize=T.fs(9), fontweight="bold",
                     loc="left", pad=7)
    if xlabel:
        ax.set_xlabel(xlabel, color=T.TXT_DIM, fontsize=T.fs(8))
    if ylabel:
        ax.set_ylabel(ylabel, color=T.TXT_DIM, fontsize=T.fs(8))


class PlotPane:
    """A themed matplotlib figure embedded in a tk widget."""

    def __init__(self, master, rows=1, cols=1, height=3.2, hspace=0.55, wspace=0.22):
        self.fig = Figure(figsize=(6, height), dpi=T.MPL_DPI, facecolor=T.PANEL,
                          layout="constrained")
        self.fig.get_layout_engine().set(w_pad=0.06, h_pad=0.05,
                                         hspace=0.12, wspace=0.08)
        self.axes = self.fig.subplots(rows, cols, squeeze=False)
        self.canvas = _StudioCanvas(self.fig, master=master)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(bg=T.PANEL, highlightthickness=0, bd=0)

    def ax(self, r=0, c=0):
        return self.axes[r][c]

    def clear(self):
        for row in self.axes:
            for a in row:
                a.clear()

    def draw(self):
        # Mapping/resizing the widget schedules its first render. Drawing an
        # unmapped 1-pixel widget cannot produce a useful constrained layout.
        if self.widget.winfo_ismapped():
            self.canvas.draw_idle()

    def legend(self, ax, above=False):
        placement = dict(loc="lower right", bbox_to_anchor=(1, 1.02), borderaxespad=0) \
            if above else dict(loc="upper right")
        leg = ax.legend(**placement, fontsize=T.fs(7.5), framealpha=0.85,
                        facecolor=T.PANEL, edgecolor="none",
                        labelcolor=T.TXT_DIM, handlelength=1.4)
        return leg


def plot_wave(ax, x, sr, color=T.SIG_ORIG, label=None, max_points=4000, fill=True):
    """Draw a waveform, decimated with min/max envelope for long signals."""
    n = len(x)
    if n == 0:
        return
    t = np.arange(n) / float(sr)
    if n > max_points:
        k = n // max_points
        m = (n // k) * k
        blocks = x[:m].reshape(-1, k)
        tb = t[:m:k]
        hi, lo = blocks.max(axis=1), blocks.min(axis=1)
        ax.fill_between(tb, lo, hi, color=color, alpha=0.55, linewidth=0, label=label)
        ax.plot(tb, (hi + lo) / 2, color=color, linewidth=0.6, alpha=0.9)
    else:
        ax.plot(t, x, color=color, linewidth=0.9, label=label)
        if fill:
            ax.fill_between(t, 0, x, color=color, alpha=0.18, linewidth=0)
    ax.set_xlim(0, t[-1] if n > 1 else 1)


def plot_spectrum(ax, f, mag_db, color=T.SIG_ORIG, label=None, floor=-110):
    mag_db = np.maximum(mag_db, floor)
    ax.plot(f, mag_db, color=color, linewidth=0.9, label=label)
    ax.fill_between(f, floor, mag_db, color=color, alpha=0.15, linewidth=0)
    ax.set_ylim(floor, max(5, float(np.max(mag_db)) + 6))
    ax.set_xlim(0, f[-1] if len(f) else 1)


def plot_spectrogram(ax, f, t, S, cmap="magma"):
    ax.pcolormesh(t, f, S, shading="auto", cmap=cmap,
                  vmin=np.percentile(S, 5), vmax=np.percentile(S, 99.5))
    ax.set_ylim(0, f[-1] if len(f) else 1)


def show_image(ax, img, cmap=None):
    ax.imshow(np.clip(img, 0, 1), cmap=cmap, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(True)
        sp.set_color(T.STROKE_HI)


class Cursor:
    """Crosshair + value read-out + drag-to-zoom for a PlotPane.

    Left-drag selects an x-range to zoom into, right-click or double-click
    resets, and the pointer position is printed in the corner of the axes.
    """

    def __init__(self, pane, fmt=None, zoom=True):
        self.pane = pane
        self.fmt = fmt or (lambda x, y: "x=%.4g   y=%.4g" % (x, y))
        self.zoom = zoom
        self._art = {}
        self._drag_start = None
        self._home = {}
        c = pane.canvas
        c.mpl_connect("motion_notify_event", self._on_move)
        c.mpl_connect("button_press_event", self._on_press)
        c.mpl_connect("button_release_event", self._on_release)
        c.mpl_connect("axes_leave_event", self._on_leave)

    def _artists(self, ax):
        if ax not in self._art:
            vl = ax.axvline(0, color=T.TXT_DIM, linewidth=0.7, alpha=0.0,
                            zorder=50)
            hl = ax.axhline(0, color=T.TXT_DIM, linewidth=0.7, alpha=0.0,
                            zorder=50)
            tx = ax.text(0.995, 0.03, "", transform=ax.transAxes, ha="right",
                         va="bottom", color=T.CYAN, fontsize=T.fs(7),
                         fontfamily="monospace", zorder=51,
                         bbox=dict(facecolor=T.PANEL_2, edgecolor=T.STROKE_HI,
                                   boxstyle="round,pad=0.25", linewidth=0.6))
            span = ax.axvspan(0, 0, color=T.CYAN, alpha=0.0, zorder=49)
            self._art[ax] = (vl, hl, tx, span)
            self._home[ax] = (ax.get_xlim(), ax.get_ylim())
        return self._art[ax]

    def _on_move(self, ev):
        if ev.inaxes is None:
            return
        vl, hl, tx, span = self._artists(ev.inaxes)
        vl.set_xdata([ev.xdata, ev.xdata])
        hl.set_ydata([ev.ydata, ev.ydata])
        vl.set_alpha(0.55)
        hl.set_alpha(0.35)
        tx.set_text(self.fmt(ev.xdata, ev.ydata))
        if self._drag_start is not None and self._drag_start[0] is ev.inaxes:
            x0 = self._drag_start[1]
            span.set_alpha(0.18)
            span.set_xy([[x0, 0], [x0, 1], [ev.xdata, 1], [ev.xdata, 0]])
        self.pane.canvas.draw_idle()

    def _on_press(self, ev):
        if ev.inaxes is None:
            return
        self._artists(ev.inaxes)
        if ev.button == 3 or ev.dblclick:
            xlim, ylim = self._home.get(ev.inaxes, (None, None))
            if xlim:
                ev.inaxes.set_xlim(xlim)
                ev.inaxes.set_ylim(ylim)
            self.pane.canvas.draw_idle()
        elif ev.button == 1 and self.zoom:
            self._drag_start = (ev.inaxes, ev.xdata)

    def _on_release(self, ev):
        if self._drag_start is None:
            return
        ax, x0 = self._drag_start
        self._drag_start = None
        _, _, _, span = self._artists(ax)
        span.set_alpha(0.0)
        if ev.inaxes is ax and ev.xdata is not None and abs(ev.xdata - x0) > 1e-9:
            lo, hi = sorted([x0, ev.xdata])
            if hi - lo > (ax.get_xlim()[1] - ax.get_xlim()[0]) * 0.01:
                ax.set_xlim(lo, hi)
        self.pane.canvas.draw_idle()

    def _on_leave(self, ev):
        for vl, hl, tx, span in self._art.values():
            vl.set_alpha(0.0)
            hl.set_alpha(0.0)
            tx.set_text("")
            span.set_alpha(0.0)
        self.pane.canvas.draw_idle()


def plot_segments(ax, segments, color=T.GREEN, alpha=0.14, label=None):
    """Shade time ranges (used for voice-activity segments)."""
    for i, (a, b) in enumerate(segments):
        ax.axvspan(a, b, color=color, alpha=alpha, linewidth=0,
                   label=label if i == 0 else None)


def plot_heatmap(ax, M, times=None, cmap="magma", ylabel=None):
    """Feature-matrix heat map (MFCC, mel spectrogram)."""
    extent = [times[0], times[-1], 0, M.shape[0]] if times is not None and len(times) \
        else None
    im = ax.imshow(M, aspect="auto", origin="lower", cmap=cmap,
                   extent=extent, interpolation="nearest",
                   vmin=np.percentile(M, 2), vmax=np.percentile(M, 98))
    if ylabel:
        ax.set_ylabel(ylabel, color=T.TXT_DIM, fontsize=T.fs(8))
    return im
