"""Image / video-frame workbench: 2-D filtering, restoration and enhancement."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np

from .. import dsp_image as I
from .. import explain as E
from .. import report as R
from .. import presets as P
from .. import theme as T
from ..jobs import JobQueue
from ..plots import Cursor, PlotPane, show_image, style_axes
from ..widgets import PlotGrid, SlimScrollbar
from ..widgets import (attach_scroll, Badge, Card, Dropdown, NeonButton,
                       ProgressBar, Slider, StatRow, Toggle, Tooltip)

SYNTH = ["Checkerboard", "Gradient", "Circles", "Zone plate", "Bars"]
DEBLUR = ["None", "Wiener deconvolution", "Inverse filter", "Richardson-Lucy"]


class ImagePanel(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.original = I.synthetic("Zone plate")
        self.degraded = self.original.copy()
        self.processed = self.original.copy()
        self.kernel = None
        self.name = "zone plate (synthetic)"
        self._busy = False
        self._show_degraded = True
        self.jobs = JobQueue(self)

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_controls()
        self._build_views()
        self.run()

    # ------------------------------------------------------------ layout --
    def _build_controls(self):
        wrap = tk.Frame(self, bg=T.BG, width=T.ui(330))
        wrap.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        wrap.grid_propagate(False)
        cv = tk.Canvas(wrap, bg=T.BG, highlightthickness=0, width=T.ui(330))
        sb = SlimScrollbar(wrap, orient="vertical", command=cv.yview, bg=T.PANEL,
                          troughcolor=T.BG, bd=0, highlightthickness=0, width=8)
        col = tk.Frame(cv, bg=T.BG)
        col.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=col, anchor="nw", width=T.ui(314))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        attach_scroll(cv)

        self._build_presets(col, P.IMAGE, T.MAGENTA)

        # source
        c = Card(col, "Image Source", T.CYAN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x")
        NeonButton(r, "LOAD IMAGE", self.load_image, T.CYAN, width=120, height=30,
                   icon="↑").pack(side="left")
        NeonButton(r, "VIDEO FRAME", self.load_video_frame, T.VIOLET, width=124,
                   height=30).pack(side="left", padx=6)
        self.dd_synth = Dropdown(b, "Synthetic test pattern", SYNTH, "Zone plate",
                                 command=lambda v: self.use_synth(), accent=T.CYAN)
        self.dd_synth.pack(fill="x", pady=(8, 0))
        self.lbl_src = StatRow(b, "LOADED", self.name[:22], T.CYAN)
        self.lbl_src.pack(fill="x", pady=(2, 0))

        # degradation
        c.fit()

        c = Card(col, "Degradation Model", T.AMBER, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.tg_noise = Toggle(b, "Add noise", True, lambda v: self.run(), T.AMBER)
        self.tg_noise.pack(fill="x", pady=(0, 2))
        self.dd_noise = Dropdown(b, "Noise model", I.IMG_NOISES, "Gaussian",
                                 command=self._noise_changed, accent=T.AMBER)
        self.dd_noise.pack(fill="x")
        self.sl_amount = Slider(b, "Noise amount", 0.01, 0.4, 0.08, fmt="{:.3f}",
                                accent=T.AMBER, command=lambda v: self.run())
        self.sl_amount.pack(fill="x")
        self.sl_blur = Slider(b, "Motion blur length", 0, 31, 0, step=1, fmt="{:.0f}",
                              unit="px", accent=T.AMBER, command=lambda v: self.run())
        self.sl_blur.pack(fill="x")
        Tooltip(self.sl_blur, "Convolves each frame with a line kernel - the "
                              "classic motion-blur degradation model. Set it "
                              "above 0 to enable deconvolution.")
        self.sl_angle = Slider(b, "Blur angle", 0, 180, 0, fmt="{:.0f}", unit="deg",
                               accent=T.AMBER, command=lambda v: self.run())
        self.sl_angle.pack(fill="x")

        # denoise
        c.fit()

        c = Card(col, "Noise Reduction (2-D)", T.GREEN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.dd_denoise = Dropdown(b, "Algorithm", I.IMG_DENOISE, "Median",
                                   command=self._denoise_changed, accent=T.GREEN)
        self.dd_denoise.pack(fill="x")
        self.sl_strength = Slider(b, "Strength", 0.0, 1.0, 0.4, fmt="{:.2f}",
                                  accent=T.GREEN, command=lambda v: self.run())
        self.sl_strength.pack(fill="x")
        self.sl_k = Slider(b, "Kernel size", 3, 11, 3, step=2, fmt="{:.0f}", unit="px",
                           accent=T.GREEN, command=lambda v: self.run())
        self.sl_k.pack(fill="x")

        # restoration
        c.fit()

        c = Card(col, "Restoration (deblur)", T.CYAN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.dd_deblur = Dropdown(b, "Deconvolution", DEBLUR, "None",
                                  command=self._deblur_changed, accent=T.CYAN)
        self.dd_deblur.pack(fill="x")
        self.sl_k_noise = Slider(b, "Wiener K / regularisation", 0.001, 0.2, 0.02,
                                 fmt="{:.3f}", log=True, accent=T.CYAN,
                                 command=lambda v: self.run())
        self.sl_k_noise.pack(fill="x")
        Tooltip(self.sl_k_noise, "Wiener K, the noise-to-signal term. Small K "
                                 "inverts the blur harder and amplifies noise; "
                                 "large K is safer but leaves blur.")

        # enhancement
        c.fit()

        c = Card(col, "Enhancement", T.MAGENTA, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.dd_enh = Dropdown(b, "Operator", I.IMG_ENHANCE, "Sharpen (unsharp mask)",
                               command=self._enh_changed, accent=T.MAGENTA)
        self.dd_enh.pack(fill="x")
        self.sl_amt = Slider(b, "Amount", 0.0, 3.0, 1.0, fmt="{:.2f}",
                             accent=T.MAGENTA, command=lambda v: self.run())
        self.sl_amt.pack(fill="x")
        self.sl_gamma = Slider(b, "Gamma / edge threshold", 0.2, 3.0, 1.0, fmt="{:.2f}",
                               accent=T.MAGENTA, command=lambda v: self.run())
        self.sl_gamma.pack(fill="x")

        # export
        c.fit()

        c = Card(col, "Export", T.LIME, pad=14)
        c.pack(fill="x", pady=(0, 14))
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x")
        NeonButton(r, "SAVE RESULT", self.save_image, T.LIME, width=126, height=30,
                   icon="↓").pack(side="left")
        NeonButton(r, "PDF REPORT", self.export_report, T.VIOLET,
                   width=120, height=30).pack(side="left", padx=6)
        self.bd_state = Badge(b, "idle", T.TXT_DIM, width=120,
                              height=22)
        self.bd_state.pack(anchor="w", pady=(6, 0))
        self.prog = ProgressBar(b, accent=T.LIME)
        self.prog.pack(fill="x")
        c.fit()

    # ------------------------------------------------------------ presets --
    def _build_presets(self, col, presets, accent):
        """QUICK START card: each button configures a whole scenario."""
        c = Card(col, "Quick Start", accent, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        tk.Label(b, text="One click sets up a complete demonstration.",
                 bg=T.PANEL, fg=T.TXT_DIM, font=T.F_SMALL, anchor="w",
                 justify="left").pack(fill="x", pady=(0, 6))
        self._presets = presets
        row = None
        for i, (label, acc, mapping, why) in enumerate(presets):
            if i % 2 == 0:
                row = tk.Frame(b, bg=T.PANEL)
                row.pack(fill="x", pady=2)
            btn = NeonButton(row, label, lambda m=mapping, w=why, n=label:
                             self._apply_preset(n, m, w), acc, width=132,
                             height=30)
            btn.pack(side="left", padx=(0, 6))
            Tooltip(btn, why)
        c.fit()
        return c

    def _apply_preset(self, name, mapping, why):
        P.apply(self, mapping)
        self.app.status("%s - %s" % (name, why), T.CYAN)
        self.app.explain([("h", name.title()),
                          ("", why),
                          ("dim", "Every control below was set by this preset - "
                                  "change anything you like from here.")])

    def _build_views(self):
        views = PlotGrid(self, rows=2)
        views.grid(row=0, column=1, sticky="nsew")
        right = views.body
        right.columnconfigure(0, weight=3)
        right.columnconfigure(1, weight=2)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=2)

        c = Card(right, "Image Pipeline  ·  original → degraded → restored", T.CYAN)
        c.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.p_img = PlotPane(c.body, rows=1, cols=3, height=T.fh(3.4), wspace=0.08)
        self.p_img.widget.pack(fill="both", expand=True)

        c = Card(right, "2-D Frequency Domain  ·  FFT log-magnitude", T.VIOLET)
        c.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.p_fft = PlotPane(c.body, rows=1, cols=3, height=T.fh(2.4), wspace=0.08)
        self.p_fft.widget.pack(fill="both", expand=True)

        c = Card(right, "Histogram", T.MAGENTA)
        c.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        self.p_hist = PlotPane(c.body, rows=2, cols=1, height=T.fh(3.0), hspace=0.6)
        self.p_hist.widget.pack(fill="both", expand=True)
        Cursor(self.p_hist, lambda x, y: "level %.3f   count %.0f" % (x, y))

        c = Card(right, "Quality Metrics", T.LIME)
        c.grid(row=1, column=1, sticky="nsew")
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x", pady=(0, 6))
        self.bd_psnr = Badge(r, "PSNR --", T.GREEN, width=106, height=22)
        self.bd_psnr.pack(side="left", padx=(0, 6))
        self.bd_ssim = Badge(r, "SSIM --", T.CYAN, width=106, height=22)
        self.bd_ssim.pack(side="left")
        self.stats = {}
        for key, label, acc in [
            ("size", "Resolution", T.TXT),
            ("psnr_in", "PSNR  degraded", T.AMBER),
            ("psnr_out", "PSNR  restored", T.GREEN),
            ("mse", "MSE  restored", T.TXT),
            ("ssim", "SSIM  restored", T.CYAN),
            ("sharp_in", "Sharpness  in / out", T.AMBER),
            ("entropy", "Entropy (bits)", T.VIOLET),
            ("mean", "Mean / std intensity", T.TXT),
            ("time", "Processing time", T.TXT_DIM),
        ]:
            row = StatRow(b, label, "--", acc, height=18)
            row.pack(fill="x")
            self.stats[key] = row

    # ------------------------------------------------------------ sources --
    def use_synth(self):
        self.original = I.synthetic(self.dd_synth.get())
        self.name = self.dd_synth.get() + " (synthetic)"
        self.lbl_src.set(self.name[:22])
        self.run()

    def load_image(self):
        p = filedialog.askopenfilename(
            title="Open image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp"),
                       ("All files", "*.*")])
        if not p:
            return
        try:
            self.original = I.load_image(p)
            self.name = os.path.basename(p)
            self.lbl_src.set(self.name[:22])
            self.run()
            self.app.status("Loaded image %s  (%dx%d)" %
                            (self.name, self.original.shape[1],
                             self.original.shape[0]), T.GREEN)
        except Exception as ex:
            messagebox.showerror("Load failed", str(ex))

    def load_video_frame(self):
        """Grab the first frame of a video (needs imageio or opencv)."""
        p = filedialog.askopenfilename(
            title="Open video",
            filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv"), ("All files", "*.*")])
        if not p:
            return
        frame = None
        try:
            import cv2
            cap = cv2.VideoCapture(p)
            ok, fr = cap.read()
            cap.release()
            if ok:
                frame = fr[:, :, ::-1].astype(np.float64) / 255.0
        except Exception:
            try:
                import imageio.v3 as iio
                frame = np.asarray(next(iio.imiter(p))).astype(np.float64) / 255.0
            except Exception:
                frame = None
        if frame is None:
            messagebox.showinfo("Video frame",
                                "Reading video frames needs OpenCV or imageio:\n\n"
                                "pip install opencv-python")
            return
        h, w = frame.shape[:2]
        if max(h, w) > 720:
            s = 720.0 / max(h, w)
            from PIL import Image
            frame = np.asarray(Image.fromarray(I.to_u8(frame)).resize(
                (int(w * s), int(h * s)))) / 255.0
        self.original = frame
        self.name = os.path.basename(p) + " [frame 0]"
        self.lbl_src.set(self.name[:22])
        self.run()

    # ---------------------------------------------------------- pipeline --
    def run(self, *_):
        """Queue a pipeline pass on a worker thread so the window stays live."""
        cfg = dict(blur=int(self.sl_blur.get()), angle=self.sl_angle.get(),
                   noise=self.tg_noise.get(), model=self.dd_noise.get(),
                   amount=self.sl_amount.get(), method=self.dd_denoise.get(),
                   strength=self.sl_strength.get(), k=int(self.sl_k.get()),
                   deblur=self.dd_deblur.get(), K=self.sl_k_noise.get(),
                   enh=self.dd_enh.get(), amt=self.sl_amt.get(),
                   gamma=self.sl_gamma.get())
        img = self.original
        self.bd_state.set("processing", T.AMBER)
        self.prog.start("processing image...")

        def work(progress):
            import time
            t0 = time.perf_counter()
            y = img.copy()
            kernel = None
            if cfg["blur"] >= 3:
                y, kernel = I.motion_blur(y, cfg["blur"], cfg["angle"])
            progress(0.2, "degrading...")
            if cfg["noise"]:
                y = I.add_noise(y, cfg["model"], cfg["amount"])
            progress(0.35, "denoising...")
            z = I.denoise(y, cfg["method"], cfg["strength"], cfg["k"])
            progress(0.7, "restoring...")
            mode = cfg["deblur"]
            if mode != "None" and kernel is not None:
                if mode.startswith("Wiener"):
                    z = I.wiener_deconvolve(z, kernel, cfg["K"])
                elif mode.startswith("Inverse"):
                    z = I.inverse_filter(z, kernel, max(cfg["K"], 0.01))
                else:
                    z = I.richardson_lucy(z, kernel, iters=12)
            progress(0.88, "enhancing...")
            z = I.enhance(z, cfg["enh"], cfg["amt"], cfg["gamma"],
                          cfg["gamma"] / 3.0)
            progress(1.0, "done")
            return y, z, kernel, time.perf_counter() - t0

        self.jobs.submit("image", work, self._done,
                         lambda f, m: self.prog.set(f, m), self._failed)

    def _failed(self, ex):
        self.prog.stop("")
        self.bd_state.set("error", T.RED)
        self.app.status("Image error: %s" % ex, T.RED)

    def _done(self, res):
        self.degraded, self.processed, self.kernel, secs = res
        self.prog.stop("")
        self.bd_state.set("ready", T.GREEN)
        self._redraw()
        self._update_stats()
        self.stats["time"].set("%.0f ms" % (secs * 1000))

    def _redraw(self):
        self.p_img.clear()
        mid = self.degraded if getattr(self, "_show_degraded", True) else self.original
        mid_name = "Degraded" if getattr(self, "_show_degraded", True)             else "Original (A/B)"
        for i, (im, name, col) in enumerate([
                (self.original, "Original", T.CYAN),
                (mid, mid_name, T.AMBER),
                (self.processed, "Processed", T.MAGENTA)]):
            ax = self.p_img.ax(0, i)
            show_image(ax, im)
            ax.set_title(name, color=col, fontsize=T.fs(8.5), fontweight="bold", pad=5)
        self.p_img.draw()

        self.p_fft.clear()
        for i, (im, name, col) in enumerate([
                (self.original, "Original", T.CYAN),
                (self.degraded, "Degraded", T.AMBER),
                (self.processed, "Processed", T.MAGENTA)]):
            ax = self.p_fft.ax(0, i)
            show_image(ax, I.fft_magnitude(im), cmap="magma")
            ax.set_title("FFT · " + name, color=col, fontsize=T.fs(8), pad=5)
        self.p_fft.draw()

        self.p_hist.clear()
        for r, (im, name, col) in enumerate([(self.degraded, "Degraded", T.AMBER),
                                             (self.processed, "Processed", T.MAGENTA)]):
            ax = self.p_hist.ax(r, 0)
            style_axes(ax, "Histogram · " + name,
                       "Intensity" if r == 1 else None, "count", col)
            for ch, (bins, h) in I.histogram(im).items():
                c = {"R": T.RED, "G": T.GREEN, "B": T.CYAN, "Y": T.TXT}[ch]
                ax.fill_between(bins, 0, h, color=c, alpha=0.35, linewidth=0)
                ax.plot(bins, h, color=c, linewidth=0.8, label=ch)
            ax.set_xlim(0, 1)
            self.p_hist.legend(ax)
        self.p_hist.draw()

    def _update_stats(self):
        s = self.stats
        o, d, p = self.original, self.degraded, self.processed
        s["size"].set("%d x %d px" % (o.shape[1], o.shape[0]))
        p_in, p_out = I.psnr(o, d), I.psnr(o, p)
        s["psnr_in"].set("%.2f dB" % p_in)
        s["psnr_out"].set("%.2f dB" % p_out)
        s["mse"].set("%.3e" % I.mse(o, p))
        sm = I.ssim(o, p)
        s["ssim"].set("%.4f" % sm)
        s["sharp_in"].set("%.4f  /  %.4f" % (I.sharpness(d), I.sharpness(p)))
        s["entropy"].set("%.3f" % I.entropy(p))
        s["mean"].set("%.4f  /  %.4f" % (float(np.mean(p)), float(np.std(p))))
        self.bd_psnr.set("PSNR %.1f dB" % p_out, T.GREEN if p_out > p_in else T.AMBER)
        self.bd_ssim.set("SSIM %.3f" % sm, T.CYAN)

    # ------------------------------------------------------------ export --
    def save_image(self):
        p = filedialog.asksaveasfilename(defaultextension=".png",
                                         initialfile="processed.png",
                                         filetypes=[("PNG image", "*.png")])
        if not p:
            return
        I.save_image(p, self.processed)
        self.app.status("Saved " + os.path.basename(p), T.GREEN)

    # ------------------------------------------------------ explanations --
    def _noise_changed(self, v):
        self.app.explain(E.lookup(E.NOISE_MODELS, v))
        self.run()

    def _denoise_changed(self, v):
        self.app.explain(E.lookup(E.IMAGE_DENOISE, v))
        self.run()

    def _deblur_changed(self, v):
        self.app.explain(E.lookup(E.RESTORATION, v))
        self.run()

    def _enh_changed(self, v):
        self.app.explain(E.lookup(E.ENHANCE, v))
        self.run()

    def on_show(self):
        self.app.explain(E.lookup(E.IMAGE_DENOISE, self.dd_denoise.get()))

    # ---------------------------------------------------------- A/B view --
    def toggle_ab(self):
        """Flip the middle pane between the degraded input and the original."""
        self._show_degraded = not getattr(self, "_show_degraded", True)
        self.app.status("Middle pane: %s" %
                        ("degraded input" if self._show_degraded
                         else "original (A/B)"), T.MAGENTA)
        self._redraw()

    # ------------------------------------------------------------ report --
    def export_report(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=os.path.basename(R.default_path("dsp_image_report")),
            filetypes=[("PDF report", "*.pdf")])
        if not p:
            return
        o, d, z = self.original, self.degraded, self.processed
        config = [("Image", self.name),
                  ("Resolution", "%d x %d px" % (o.shape[1], o.shape[0])),
                  ("Noise model", "%s  %.3f" % (self.dd_noise.get(),
                                                self.sl_amount.get())
                   if self.tg_noise.get() else "none"),
                  ("Motion blur", "%d px at %.0f deg" % (int(self.sl_blur.get()),
                                                         self.sl_angle.get())),
                  ("Denoiser", "%s  (strength %.2f, kernel %d)" %
                   (self.dd_denoise.get(), self.sl_strength.get(),
                    int(self.sl_k.get()))),
                  ("Restoration", "%s  (K = %.3f)" % (self.dd_deblur.get(),
                                                      self.sl_k_noise.get())),
                  ("Enhancement", "%s  (amount %.2f)" % (self.dd_enh.get(),
                                                         self.sl_amt.get()))]
        metrics = [("PSNR degraded", "%.2f dB" % I.psnr(o, d)),
                   ("PSNR restored", "%.2f dB" % I.psnr(o, z)),
                   ("Improvement", "%+.2f dB" % (I.psnr(o, z) - I.psnr(o, d))),
                   ("MSE", "%.3e" % I.mse(o, z)),
                   ("SSIM", "%.4f" % I.ssim(o, z)),
                   ("Sharpness degraded", "%.5f" % I.sharpness(d)),
                   ("Sharpness restored", "%.5f" % I.sharpness(z)),
                   ("Entropy", "%.3f bits" % I.entropy(z))]
        figs = [("Image pipeline", self.p_img.fig),
                ("2-D frequency domain", self.p_fft.fig),
                ("Histograms", self.p_hist.fig)]
        R.build(p, "Image restoration", self.name, config, metrics, figs)
        self.app.status("Report written to " + os.path.basename(p), T.GREEN)

    def save_output(self):
        self.save_image()

    def shutdown(self):
        self.jobs.cancel_all()
