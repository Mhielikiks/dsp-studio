"""Video workbench: frame-by-frame 2-D DSP with a scrubber and clip export.

Frames are decoded once into memory (capped), processed on a worker thread so
the window stays responsive, then played back or written out.
"""
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

MAX_FRAMES = 150
DEBLUR_K = 0.05             # Wiener noise-to-signal term for clip deblurring
MAX_SIDE = 420


class VideoPanel(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.jobs = JobQueue(self)
        self.frames = []            # original frames, float [0,1]
        self.degraded = []
        self.processed = []
        self.fps = 24.0
        self.name = "synthetic clip"
        self.idx = 0
        self._playing = False
        self._play_job = None
        self._show_processed = True

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_controls()
        self._build_views()
        self.make_synthetic()

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

        self._build_presets(col, P.VIDEO, T.AMBER)

        c = Card(col, "Video Source", T.AMBER, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x")
        NeonButton(r, "LOAD VIDEO", self.load_video, T.AMBER, width=116,
                   height=30, icon="↑").pack(side="left")
        NeonButton(r, "SYNTH CLIP", self.make_synthetic, T.VIOLET,
                   width=110, height=30).pack(side="left", padx=6)
        self.st_src = StatRow(b, "CLIP", "synthetic", T.AMBER)
        self.st_src.pack(fill="x", pady=(8, 0))
        self.st_info = StatRow(b, "FRAMES / SIZE / FPS", "--", T.TXT)
        self.st_info.pack(fill="x")
        Tooltip(c, "Frames are decoded once into memory (capped at %d frames, "
                   "%d px) so every frame can be reprocessed instantly."
                % (MAX_FRAMES, MAX_SIDE))

        c.fit()

        c = Card(col, "Degradation", T.AMBER, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.tg_noise = Toggle(b, "Add noise per frame", True,
                               lambda v: self.reprocess(), T.AMBER)
        self.tg_noise.pack(fill="x")
        self.dd_noise = Dropdown(b, "Noise model", I.IMG_NOISES, "Gaussian",
                                 command=self._noise_changed, accent=T.AMBER)
        self.dd_noise.pack(fill="x")
        self.sl_amount = Slider(b, "Amount", 0.01, 0.3, 0.07, fmt="{:.3f}",
                                accent=T.AMBER, command=lambda v: self.reprocess())
        self.sl_amount.pack(fill="x")
        self.sl_blur = Slider(b, "Motion blur", 0, 21, 0, step=1, fmt="{:.0f}",
                              unit="px", accent=T.AMBER,
                              command=lambda v: self.reprocess())
        self.sl_blur.pack(fill="x")

        c.fit()

        c = Card(col, "Per-frame Processing", T.GREEN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.dd_denoise = Dropdown(b, "Spatial denoiser", I.IMG_DENOISE, "Median",
                                   command=self._denoise_changed, accent=T.GREEN)
        self.dd_denoise.pack(fill="x")
        self.sl_strength = Slider(b, "Strength", 0.0, 1.0, 0.4, fmt="{:.2f}",
                                  accent=T.GREEN, command=lambda v: self.reprocess())
        self.sl_strength.pack(fill="x")
        self.sl_k = Slider(b, "Kernel", 3, 9, 3, step=2, fmt="{:.0f}", unit="px",
                           accent=T.GREEN, command=lambda v: self.reprocess())
        self.sl_k.pack(fill="x")
        self.tg_deblur = Toggle(b, "Wiener deblur", False,
                                lambda v: self.reprocess(), T.CYAN)
        self.tg_deblur.pack(fill="x")
        Tooltip(self.tg_deblur,
                "Inverts the motion blur added above with Wiener deconvolution "
                "(K = %.2f), frame by frame. Has no effect when motion blur is 0."
                % DEBLUR_K)
        self.tg_temporal = Toggle(b, "Temporal averaging (5 frames)", True,
                                  lambda v: self.reprocess(), T.CYAN)
        self.tg_temporal.pack(fill="x")
        Tooltip(self.tg_temporal,
                "Averages each pixel with the same pixel in the 2 frames before "
                "and after. Noise is independent between frames so it cancels - "
                "the 2-D filter cannot do this. Neighbours that differ (motion) "
                "get less weight, so moving edges are not smeared.")
        self.dd_enh = Dropdown(b, "Enhancement", I.IMG_ENHANCE, "None",
                               command=self._enh_changed, accent=T.MAGENTA)
        self.dd_enh.pack(fill="x")
        self.sl_amt = Slider(b, "Amount", 0.0, 2.0, 1.0, fmt="{:.2f}",
                             accent=T.MAGENTA, command=lambda v: self.reprocess())
        self.sl_amt.pack(fill="x")

        c.fit()

        c = Card(col, "Playback", T.LIME, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x")
        self.btn_play = NeonButton(r, "PLAY", self.toggle_play, T.LIME,
                                   width=84, height=30, icon="▶")
        self.btn_play.pack(side="left")
        NeonButton(r, "◀ PREV", lambda: self.step(-1), T.CYAN, width=80,
                   height=30).pack(side="left", padx=6)
        NeonButton(r, "NEXT ▶", lambda: self.step(1), T.CYAN, width=80,
                   height=30).pack(side="left")
        self.sl_frame = Slider(b, "Frame", 0, 1, 0, step=1, fmt="{:.0f}",
                               accent=T.LIME, command=self._scrub)
        self.sl_frame.pack(fill="x", pady=(6, 0))
        self.sl_fps = Slider(b, "Playback rate", 2, 30, 12, step=1, fmt="{:.0f}",
                             unit="fps", accent=T.LIME)
        self.sl_fps.pack(fill="x")

        c.fit()

        c = Card(col, "Export", T.VIOLET, pad=14)
        c.pack(fill="x", pady=(0, 14))
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x")
        NeonButton(r, "SAVE CLIP", self.save_output, T.VIOLET, width=102,
                   height=28).pack(side="left")
        NeonButton(r, "SAVE FRAME", self.save_frame, T.CYAN, width=108,
                   height=28).pack(side="left", padx=6)
        NeonButton(r, "PDF", self.export_report, T.LIME, width=56,
                   height=28).pack(side="left")
        self.prog = ProgressBar(b, accent=T.VIOLET)
        self.prog.pack(fill="x", pady=(8, 0))
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

        c = Card(right, "Frame view  ·  degraded vs processed", T.AMBER)
        c.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.p_frame = PlotPane(c.body, rows=1, cols=2, height=T.fh(3.3), wspace=0.06)
        self.p_frame.widget.pack(fill="both", expand=True)

        c = Card(right, "Temporal profile  ·  quality across the clip", T.CYAN)
        c.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.p_time = PlotPane(c.body, height=T.fh(2.3))
        self.p_time.widget.pack(fill="both", expand=True)
        Cursor(self.p_time, lambda x, y: "frame %.0f   %.2f dB" % (x, y))

        c = Card(right, "Frame difference  ·  what was removed", T.MAGENTA)
        c.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        self.p_diff = PlotPane(c.body, rows=1, cols=2, height=T.fh(2.6), wspace=0.06)
        self.p_diff.widget.pack(fill="both", expand=True)

        c = Card(right, "Clip Metrics", T.LIME)
        c.grid(row=1, column=1, sticky="nsew")
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x", pady=(0, 5))
        self.bd_psnr = Badge(r, "PSNR --", T.GREEN, width=104, height=22)
        self.bd_psnr.pack(side="left", padx=(0, 6))
        self.bd_state = Badge(r, "idle", T.TXT_DIM, width=104, height=22)
        self.bd_state.pack(side="left")
        self.stats = {}
        for key, label, acc in [("frames", "Frames / fps", T.TXT),
                                ("size", "Resolution", T.TXT),
                                ("psnr_in", "PSNR degraded (mean)", T.AMBER),
                                ("psnr_out", "PSNR processed (mean)", T.GREEN),
                                ("gain", "Mean improvement", T.GREEN),
                                ("ssim", "SSIM processed (mean)", T.CYAN),
                                ("frame_psnr", "This frame PSNR", T.MAGENTA),
                                ("flow", "Inter-frame motion", T.VIOLET),
                                ("time", "Processing time", T.TXT)]:
            row = StatRow(b, label, "--", acc, height=18)
            row.pack(fill="x")
            self.stats[key] = row

    # ------------------------------------------------------------ sources --
    def make_synthetic(self):
        """A moving-target clip: a disc and bars sweeping across the frame."""
        n, size = 60, 220
        y, x = np.mgrid[0:size, 0:size] / float(size)
        frames = []
        for k in range(n):
            t = k / float(n)
            cx, cy = 0.25 + 0.5 * t, 0.5 + 0.22 * np.sin(2 * np.pi * t)
            disc = (np.sqrt((x - cx) ** 2 + (y - cy) ** 2) < 0.13).astype(float)
            bars = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 9 * (x - 0.3 * t)))
            g = np.clip(0.25 + 0.45 * bars * (1 - disc) + 0.75 * disc, 0, 1)
            frames.append(np.dstack([g, g * 0.92 + 0.05, g * 0.8 + 0.12]))
        self.frames = frames
        self.fps = 24.0
        self.name = "synthetic clip (moving disc + bars)"
        self._after_load()

    def load_video(self):
        p = filedialog.askopenfilename(
            title="Open video",
            filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv *.webm"),
                       ("All files", "*.*")])
        if not p:
            return
        self.prog.start("decoding video...")

        def work(progress):
            return self._decode(p, progress)

        def done(res):
            self.prog.stop("")
            if not res:
                messagebox.showinfo(
                    "Video", "Reading video needs OpenCV or imageio:\n\n"
                             "pip install opencv-python")
                return
            self.frames, self.fps = res
            self.name = os.path.basename(p)
            self._after_load()

        self.jobs.submit("decode", work, done,
                         lambda f, m: self.prog.set(f, m),
                         lambda ex: self.app.status("Decode failed: %s" % ex, T.RED))

    def _decode(self, path, progress):
        frames, fps = [], 24.0
        try:
            import cv2
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or MAX_FRAMES
            step = max(1, total // MAX_FRAMES)
            i = 0
            while len(frames) < MAX_FRAMES:
                ok, fr = cap.read()
                if not ok:
                    break
                if i % step == 0:
                    frames.append(self._fit(fr[:, :, ::-1] / 255.0))
                    progress(len(frames) / float(MAX_FRAMES), "decoding frames...")
                i += 1
            cap.release()
            fps = fps / step
        except Exception:
            try:
                import imageio.v3 as iio
                for i, fr in enumerate(iio.imiter(path)):
                    if len(frames) >= MAX_FRAMES:
                        break
                    frames.append(self._fit(np.asarray(fr) / 255.0))
                    progress(len(frames) / float(MAX_FRAMES), "decoding frames...")
            except Exception:
                return None
        return (frames, max(1.0, fps)) if frames else None

    @staticmethod
    def _fit(frame):
        frame = np.asarray(frame, dtype=np.float64)
        if frame.ndim == 2:
            frame = np.dstack([frame] * 3)
        frame = frame[..., :3]
        h, w = frame.shape[:2]
        if max(h, w) > MAX_SIDE:
            s = MAX_SIDE / float(max(h, w))
            from PIL import Image
            frame = np.asarray(Image.fromarray(I.to_u8(frame)).resize(
                (max(1, int(w * s)), max(1, int(h * s))))) / 255.0
        return frame

    def _after_load(self):
        n = len(self.frames)
        self.idx = 0
        self.sl_frame.hi = max(1, n - 1)
        self.sl_frame.set(0)
        h, w = self.frames[0].shape[:2]
        self.st_src.set(self.name[:22])
        self.st_info.set("%d  /  %dx%d  /  %.1f" % (n, w, h, self.fps))
        self.stats["frames"].set("%d  @ %.1f fps" % (n, self.fps))
        self.stats["size"].set("%d x %d px" % (w, h))
        self.reprocess()

    # ---------------------------------------------------------- processing --
    def reprocess(self, *_):
        if not self.frames:
            return
        self.bd_state.set("processing", T.AMBER)
        self.prog.start("processing frames...")
        cfg = dict(noise=self.tg_noise.get(), model=self.dd_noise.get(),
                   amount=self.sl_amount.get(), blur=int(self.sl_blur.get()),
                   method=self.dd_denoise.get(), strength=self.sl_strength.get(),
                   k=int(self.sl_k.get()), temporal=self.tg_temporal.get(),
                   deblur=self.tg_deblur.get(),
                   enh=self.dd_enh.get(), amt=self.sl_amt.get())

        frames = self.frames

        def work(progress):
            import time
            t0 = time.perf_counter()
            deg, kernel = [], None
            for i, fr in enumerate(frames):
                y = fr
                if cfg["blur"] >= 3:
                    y, kernel = I.motion_blur(y, cfg["blur"], 0.0)
                if cfg["noise"]:
                    y = I.add_noise(y, cfg["model"], cfg["amount"])
                deg.append(y)
                progress(0.35 * i / len(frames), "degrading frames...")

            out = []
            for i, y in enumerate(deg):
                z = I.denoise(y, cfg["method"], cfg["strength"], cfg["k"])
                if cfg["deblur"] and kernel is not None:
                    z = I.wiener_deconvolve(z, kernel, DEBLUR_K)
                out.append(z)
                progress(0.35 + 0.4 * i / len(frames), "filtering frames...")
            if cfg["temporal"]:
                progress(0.8, "temporal averaging...")
                out = I.temporal_average(out)
            if cfg["enh"] != "None":
                out = [I.enhance(z, cfg["enh"], cfg["amt"], 1.0, 0.3) for z in out]
            out = [np.clip(z, 0, 1) for z in out]

            psnr_in = [I.psnr(a, b) for a, b in zip(frames, deg)]
            psnr_out = [I.psnr(a, b) for a, b in zip(frames, out)]
            ssim_out = [I.ssim(a, b) for a, b in
                        list(zip(frames, out))[::max(1, len(out) // 12)]]
            motion = [float(np.mean(np.abs(frames[i] - frames[i - 1])))
                      for i in range(1, len(frames))]
            progress(1.0, "done")
            return dict(deg=deg, out=out, psnr_in=psnr_in, psnr_out=psnr_out,
                        ssim=ssim_out, motion=motion,
                        secs=time.perf_counter() - t0)

        self.jobs.submit("frames", work, self._done,
                         lambda f, m: self.prog.set(f, m),
                         lambda ex: self._failed(ex))

    def _failed(self, ex):
        self.prog.stop("")
        self.bd_state.set("error", T.RED)
        self.app.status("Video processing failed: %s" % ex, T.RED)

    def _done(self, res):
        self.prog.stop("")
        self.bd_state.set("ready", T.GREEN)
        self.degraded, self.processed = res["deg"], res["out"]
        pi = float(np.mean(res["psnr_in"]))
        po = float(np.mean(res["psnr_out"]))
        s = self.stats
        s["psnr_in"].set("%.2f dB" % pi)
        s["psnr_out"].set("%.2f dB" % po)
        s["gain"].set("%+.2f dB" % (po - pi), T.GREEN if po > pi else T.RED)
        s["ssim"].set("%.4f" % float(np.mean(res["ssim"])))
        s["flow"].set("%.4f mean |diff|" % (float(np.mean(res["motion"]))
                                            if res["motion"] else 0.0))
        s["time"].set("%.2f s for %d frames" % (res["secs"], len(self.frames)))
        self.bd_psnr.set("PSNR %.1f dB" % po, T.GREEN if po > pi else T.AMBER)
        self._psnr_in, self._psnr_out = res["psnr_in"], res["psnr_out"]
        self._draw_profile()
        self._draw_frame()
        self.app.status("Processed %d frames in %.2f s (%+.2f dB)." %
                        (len(self.frames), res["secs"], po - pi), T.GREEN)

    # -------------------------------------------------------------- views --
    def _draw_frame(self):
        if not self.processed:
            return
        i = min(self.idx, len(self.processed) - 1)
        orig, deg, out = self.frames[i], self.degraded[i], self.processed[i]
        self.p_frame.clear()
        left = deg if self._show_processed else orig
        lname = "Degraded input" if self._show_processed else "Original"
        for col, (im, name, acc) in enumerate([(left, lname, T.AMBER),
                                               (out, "Processed", T.GREEN)]):
            ax = self.p_frame.ax(0, col)
            show_image(ax, im)
            ax.set_title("%s   ·   frame %d / %d" % (name, i + 1, len(self.frames)),
                         color=acc, fontsize=T.fs(8.5), fontweight="bold", pad=5)
        self.p_frame.draw()

        self.p_diff.clear()
        d1 = np.abs(deg - orig)
        d2 = np.abs(out - orig)
        for col, (im, name, acc) in enumerate([(d1, "Degradation", T.AMBER),
                                               (d2, "Residual error", T.MAGENTA)]):
            ax = self.p_diff.ax(0, col)
            show_image(ax, np.clip(im * 4.0, 0, 1))
            ax.set_title("%s  (x4)" % name, color=acc, fontsize=T.fs(8), pad=4)
        self.p_diff.draw()
        self.stats["frame_psnr"].set("%.2f dB" % I.psnr(orig, out))

    def _draw_profile(self):
        ax = self.p_time.ax()
        self.p_time.clear()
        style_axes(ax, "PSNR per frame", "Frame index", "dB", T.CYAN)
        n = np.arange(len(self._psnr_in))
        ax.plot(n, self._psnr_in, color=T.AMBER, linewidth=1.0, label="degraded")
        ax.plot(n, self._psnr_out, color=T.GREEN, linewidth=1.2, label="processed")
        ax.fill_between(n, self._psnr_in, self._psnr_out,
                        where=np.array(self._psnr_out) >= np.array(self._psnr_in),
                        color=T.GREEN, alpha=0.15, linewidth=0)
        self._marker = ax.axvline(self.idx, color=T.CYAN, linewidth=1.0,
                                  linestyle="--")
        ax.set_xlim(0, max(1, len(n) - 1))
        self.p_time.legend(ax)
        self.p_time.draw()

    # ---------------------------------------------------------- transport --
    def _scrub(self, v):
        self.idx = int(v)
        if self.processed:
            self._draw_frame()
            try:
                self._marker.set_xdata([self.idx, self.idx])
                self.p_time.draw()
            except Exception:
                pass

    def step(self, d):
        if not self.frames:
            return
        self.idx = (self.idx + d) % len(self.frames)
        self.sl_frame.set(self.idx)
        self._scrub(self.idx)

    def toggle_play(self):
        self._playing = not self._playing
        self.btn_play.set_text("PAUSE" if self._playing else "PLAY")
        if self._playing:
            self._tick()

    def _tick(self):
        if not self._playing or not self.processed:
            return
        self.step(1)
        self._play_job = self.after(int(1000 / max(2, self.sl_fps.get())), self._tick)

    def toggle_ab(self):
        self._show_processed = not self._show_processed
        self.app.status("Left pane shows %s" %
                        ("degraded input" if self._show_processed else "original"),
                        T.CYAN)
        self._draw_frame()

    def shutdown(self):
        self._playing = False
        self.jobs.cancel_all()

    # ------------------------------------------------------- explanations --
    def _noise_changed(self, v):
        self.app.explain(E.lookup(E.NOISE_MODELS, v))
        self.reprocess()

    def _denoise_changed(self, v):
        self.app.explain(E.lookup(E.IMAGE_DENOISE, v))
        self.reprocess()

    def _enh_changed(self, v):
        self.app.explain(E.lookup(E.ENHANCE, v))
        self.reprocess()

    # ------------------------------------------------------------ exports --
    def save_frame(self):
        if not self.processed:
            return
        p = filedialog.asksaveasfilename(defaultextension=".png",
                                         initialfile="frame_%03d.png" % self.idx,
                                         filetypes=[("PNG image", "*.png")])
        if p:
            I.save_image(p, self.processed[self.idx])
            self.app.status("Saved " + os.path.basename(p), T.GREEN)

    def save_output(self):
        """Write the processed clip: MP4 if a writer exists, else a PNG folder."""
        if not self.processed:
            return
        p = filedialog.asksaveasfilename(defaultextension=".mp4",
                                         initialfile="processed_clip.mp4",
                                         filetypes=[("MP4 video", "*.mp4"),
                                                    ("PNG sequence", "*.png")])
        if not p:
            return
        frames = [I.to_u8(f) for f in self.processed]
        try:
            import cv2
            h, w = frames[0].shape[:2]
            vw = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*"mp4v"),
                                 max(1.0, self.fps), (w, h))
            if not vw.isOpened():
                raise RuntimeError("writer unavailable")
            for f in frames:
                vw.write(f[:, :, ::-1])
            vw.release()
            self.app.status("Clip written to " + os.path.basename(p), T.GREEN)
            return
        except Exception:
            pass
        try:
            import imageio
            imageio.mimwrite(p, frames, fps=max(1.0, self.fps))
            self.app.status("Clip written to " + os.path.basename(p), T.GREEN)
            return
        except Exception:
            pass
        folder = os.path.splitext(p)[0] + "_frames"
        os.makedirs(folder, exist_ok=True)
        for i, f in enumerate(self.processed):
            I.save_image(os.path.join(folder, "frame_%04d.png" % i), f)
        self.app.status("No video writer found - wrote %d PNG frames to %s"
                        % (len(self.processed), os.path.basename(folder)), T.AMBER)

    def export_report(self):
        if not self.processed:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=os.path.basename(R.default_path("dsp_video_report")),
            filetypes=[("PDF report", "*.pdf")])
        if not p:
            return
        pi, po = float(np.mean(self._psnr_in)), float(np.mean(self._psnr_out))
        config = [("Clip", self.name),
                  ("Frames", "%d @ %.1f fps" % (len(self.frames), self.fps)),
                  ("Noise", "%s %.3f" % (self.dd_noise.get(), self.sl_amount.get())
                   if self.tg_noise.get() else "none"),
                  ("Motion blur", "%d px" % int(self.sl_blur.get())),
                  ("Spatial denoiser", self.dd_denoise.get()),
                  ("Wiener deblur", "on (K = %.2f)" % DEBLUR_K
                   if self.tg_deblur.get() else "off"),
                  ("Temporal averaging", "5 frames, motion-adaptive"
                   if self.tg_temporal.get() else "off"),
                  ("Enhancement", self.dd_enh.get())]
        metrics = [("PSNR degraded (mean)", "%.2f dB" % pi),
                   ("PSNR processed (mean)", "%.2f dB" % po),
                   ("Improvement", "%+.2f dB" % (po - pi)),
                   ("Best frame", "%.2f dB" % max(self._psnr_out)),
                   ("Worst frame", "%.2f dB" % min(self._psnr_out))]
        R.build(p, "Video processing", self.name, config, metrics,
                [("Frame comparison", self.p_frame.fig),
                 ("PSNR across the clip", self.p_time.fig),
                 ("Degradation and residual", self.p_diff.fig)])
        self.app.status("Report written to " + os.path.basename(p), T.GREEN)
