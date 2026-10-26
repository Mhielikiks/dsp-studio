"""One-click project report.

Collects the figures a panel is currently showing, the pipeline configuration
and the measured metrics into a single multi-page PDF that can be submitted
as documentation.
"""
import os
from datetime import datetime

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from . import theme as T

TITLE = "DSP STUDIO - PROCESSING REPORT"


def _cover(title, subtitle, config, metrics):
    """Title page: what was run, with what settings, and what came out."""
    fig = Figure(figsize=(8.27, 11.69), dpi=150, facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.add_patch(Rectangle((0, 0.90), 1, 0.10, color=T.BG,
                           transform=ax.transAxes))
    ax.text(0.06, 0.945, TITLE, color="white", fontsize=15, fontweight="bold",
            va="center")
    ax.text(0.06, 0.915, subtitle, color="#9fb3cf", fontsize=9, va="center")

    ax.text(0.06, 0.86, title, fontsize=13, fontweight="bold", color="#10203a")
    ax.text(0.06, 0.835, datetime.now().strftime("Generated %d %B %Y  %H:%M"),
            fontsize=8, color="#5b6b82")

    y = 0.79
    ax.text(0.06, y, "PIPELINE CONFIGURATION", fontsize=9, fontweight="bold",
            color="#0b7285")
    y -= 0.018
    ax.plot([0.06, 0.94], [y, y], color="#c7d3e0", linewidth=0.8)
    y -= 0.022
    for k, v in config:
        ax.text(0.07, y, str(k), fontsize=8.5, color="#44546a")
        ax.text(0.93, y, str(v), fontsize=8.5, color="#10203a", ha="right",
                family="monospace")
        y -= 0.0185

    y -= 0.015
    ax.text(0.06, y, "MEASUREMENTS", fontsize=9, fontweight="bold", color="#0b7285")
    y -= 0.018
    ax.plot([0.06, 0.94], [y, y], color="#c7d3e0", linewidth=0.8)
    y -= 0.022
    for k, v in metrics:
        ax.text(0.07, y, str(k), fontsize=8.5, color="#44546a")
        ax.text(0.93, y, str(v), fontsize=8.5, color="#10203a", ha="right",
                family="monospace")
        y -= 0.0185

    ax.text(0.06, 0.04,
            "Produced by DSP Studio - Tkinter + NumPy/SciPy digital signal "
            "processing workbench.", fontsize=7.5, color="#8294aa")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    return fig


def _figure_page(src_fig, caption):
    """Re-render a live (dark) figure onto a white A4 page."""
    import io
    buf = io.BytesIO()
    src_fig.savefig(buf, format="png", dpi=160, facecolor=T.PANEL,
                    bbox_inches="tight")
    buf.seek(0)
    import matplotlib.image as mpimg
    img = mpimg.imread(buf)

    fig = Figure(figsize=(8.27, 11.69), dpi=150, facecolor="white")
    ax = fig.add_axes([0.06, 0.10, 0.88, 0.80])
    ax.imshow(img)
    ax.axis("off")
    fig.text(0.06, 0.94, caption, fontsize=11, fontweight="bold", color="#10203a")
    fig.text(0.06, 0.055, TITLE, fontsize=7, color="#8294aa")
    return fig


def build(path, title, subtitle, config, metrics, figures):
    """Write the PDF. `figures` is [(caption, matplotlib Figure), ...]."""
    with PdfPages(path) as pdf:
        pdf.savefig(_cover(title, subtitle, config, metrics))
        for caption, fig in figures:
            if fig is not None:
                pdf.savefig(_figure_page(fig, caption))
        d = pdf.infodict()
        d["Title"] = title
        d["Subject"] = "Digital Signal Processing final project report"
        d["Creator"] = "DSP Studio"
    return path


def default_path(stem, ext=".pdf", folder=None):
    folder = folder or os.getcwd()
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    return os.path.join(folder, "%s_%s%s" % (stem, stamp, ext))
