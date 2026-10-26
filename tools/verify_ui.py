"""Display regression check: run with the project's desktop Python runtime."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import DSPStudio
from dspstudio import theme as T
from dspstudio.plots import PlotPane
from dspstudio.widgets import StatRow


def settle(app, seconds=0.3):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        app.update()
        time.sleep(0.01)


def inspect(app):
    findings = []
    measurements = []
    for key, panel in app.panels.items():
        app.rail.select(list(app.panels).index(key))
        settle(app)
        for name, pane in vars(panel).items():
            if not isinstance(pane, PlotPane):
                continue
            pane.canvas.draw()
            renderer = pane.canvas.get_renderer()
            bounds = pane.fig.bbox
            measurements.append({"panel": key, "plot": name,
                                 "size": [round(bounds.width), round(bounds.height)],
                                 "dpi": pane.fig.dpi,
                                 "ratio": pane.canvas.device_pixel_ratio})
            expected_dpi = 96 * pane.canvas.device_pixel_ratio
            if abs(pane.fig.dpi - expected_dpi) > 0.1:
                findings.append(f"{key}/{name}: duplicate DPI scaling")
            for ax in pane.fig.axes:
                texts = [ax.title, ax._left_title, ax.xaxis.label, ax.yaxis.label,
                         *ax.get_xticklabels(), *ax.get_yticklabels(), *ax.texts]
                for text in texts:
                    if not text.get_visible() or not text.get_text() or text.get_clip_on():
                        continue
                    b = text.get_window_extent(renderer)
                    if (b.x0 < -2 or b.y0 < -2 or b.x1 > bounds.width + 2
                            or b.y1 > bounds.height + 2):
                        findings.append(f"{key}/{name}: clipped text {text.get_text()!r}")
        for stat in getattr(panel, "stats", {}).values():
            if not isinstance(stat, StatRow):
                continue
            if stat.winfo_y() + stat.winfo_height() > stat.master.winfo_height():
                findings.append(f"{key}: metric outside card {stat.label}")
            texts = [i for i in stat.find_all() if stat.type(i) == "text"]
            if len(texts) == 2:
                left, right = [stat.bbox(i) for i in texts]
                if left and right and left[2] > right[0]:
                    findings.append(f"{key}: overlapping metric {stat.label}")
    return measurements, findings


if __name__ == "__main__":
    if "--dpi" in sys.argv:
        dpi = float(sys.argv[sys.argv.index("--dpi") + 1])
        original_fpixels = DSPStudio.winfo_fpixels
        DSPStudio.winfo_fpixels = lambda self, value: (
            dpi if value == "1i" else original_fpixels(self, value))
    app = DSPStudio(show_splash=False)
    errors = []
    original_exception_handler = app.report_callback_exception
    app.report_callback_exception = lambda *args: errors.append(str(args[1]))
    settle(app, 2)
    runs = []
    for size in [None, "1100x740", "1280x820"]:
        if size:
            app.state("normal")
            width, height = (int(n) for n in size.split("x"))
            app.geometry(f"{round(width * T.DPI_FACTOR)}x{round(height * T.DPI_FACTOR)}")
            settle(app)
        print(f"Checking {size or 'maximized'}", flush=True)
        plots, findings = inspect(app)
        runs.append({"window": size or "maximized", "actual_size": [app.winfo_width(), app.winfo_height()],
                     "plots": plots, "findings": findings})
    app.rail.select(0)
    app.state("zoomed")
    settle(app)
    result = {"screen": [app.winfo_screenwidth(), app.winfo_screenheight()],
              "dpi": T.DPI, "scale": T.SCALE, "compact": T.COMPACT,
              "runs": runs, "callback_errors": errors}
    output = Path(__file__).resolve().parent / "ui-checks"
    output.mkdir(exist_ok=True)
    (output / f"ui-verification-{round(T.DPI)}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"dpi": T.DPI, "findings": [run["findings"] for run in runs], "errors": errors}), flush=True)
    if "--keep-open" in sys.argv:
        app.report_callback_exception = original_exception_handler
        app.mainloop()
    else:
        app.quit_app()
        sys.exit(bool(errors or any(run["findings"] for run in runs)))
