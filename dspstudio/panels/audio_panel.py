"""Audio / Speech workbench: acquire -> corrupt -> denoise -> filter -> enhance."""
import os
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np

from .. import dsp_audio as D
from .. import explain as E
from .. import report as R
from .. import presets as P
from .. import theme as T
from ..plots import (Cursor, PlotPane, plot_spectrogram, plot_spectrum,
                     plot_wave, style_axes)
from ..widgets import PlotGrid, SlimScrollbar, fit_text
from ..widgets import (attach_scroll, Badge, Card, Dropdown, LevelMeter,
                       NeonButton, Slider, StatRow, Toggle, Tooltip)

GEN_KINDS = ["Sine", "Square", "Chirp (sweep)", "Multi-tone"]
NOISE_KINDS = ["Gaussian (AWGN)", "Pink (1/f)", "Hum 60 Hz + harmonics",
               "Impulse (clicks)"]


class AudioPanel(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.sr = 8000
        self.clean = np.zeros(1)
        self.noisy = np.zeros(1)
        self.processed = np.zeros(1)
        self.source_name = "none"
        self._design = None
        self._busy = False

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_controls()
        self._build_views()
        self.load_demo()

    # ------------------------------------------------------------ layout --
    def _build_controls(self):
        wrap = tk.Frame(self, bg=T.BG, width=T.ui(330))
        wrap.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        wrap.grid_propagate(False)

        cv = tk.Canvas(wrap, bg=T.BG, highlightthickness=0, width=T.ui(330))
        sb = SlimScrollbar(wrap, orient="vertical", command=cv.yview,
                          bg=T.PANEL, troughcolor=T.BG, bd=0,
                          highlightthickness=0, activebackground=T.CYAN, width=8)
        col = tk.Frame(cv, bg=T.BG)
        col.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=col, anchor="nw", width=T.ui(314))
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        attach_scroll(cv)

        self._build_presets(col, P.AUDIO, T.CYAN)

        # ---------------- source ----------------
        c = Card(col, "Signal Source", T.CYAN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        row = tk.Frame(b, bg=T.PANEL)
        row.pack(fill="x")
        NeonButton(row, "LOAD WAV", self.load_wav, T.CYAN, width=96, height=30,
                   icon="↑").pack(side="left")
        NeonButton(row, "RECORD", self.record_mic, T.MAGENTA, width=90, height=30,
                   icon="●").pack(side="left", padx=6)
        NeonButton(row, "DEMO", self.load_demo, T.VIOLET, width=72, height=30
                   ).pack(side="left")

        self.dd_gen = Dropdown(b, "Generate waveform", GEN_KINDS, "Sine",
                               command=self._gen_changed, accent=T.CYAN)
        self.dd_gen.pack(fill="x", pady=(10, 2))
        self.sl_freq = Slider(b, "Frequency", 20, 3500, 440, fmt="{:.0f}", unit="Hz",
                              log=True, accent=T.CYAN, command=lambda v: self.generate())
        self.sl_freq.pack(fill="x")
        self.sl_dur = Slider(b, "Duration", 0.2, 5.0, 2.0, fmt="{:.1f}", unit="s",
                             accent=T.CYAN, command=lambda v: self.generate())
        self.sl_dur.pack(fill="x")
        Tooltip(self.dd_gen, "Pick a test waveform. Each one exercises a "
                             "different part of the chain - a chirp shows the "
                             "spectrogram, a multi-tone shows filter "
                             "selectivity.")
        self.lbl_src = StatRow(b, "LOADED", "demo", T.CYAN)
        self.lbl_src.pack(fill="x", pady=(4, 0))

        # ---------------- degradation ----------------
        c.fit()

        c = Card(col, "Noise / Degradation", T.AMBER, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.tg_noise = Toggle(b, "Inject noise", True, lambda v: self.run(), T.AMBER)
        self.tg_noise.pack(fill="x", pady=(0, 4))
        self.dd_noise = Dropdown(b, "Noise model", NOISE_KINDS, NOISE_KINDS[0],
                                 command=self._noise_changed, accent=T.AMBER)
        self.dd_noise.pack(fill="x")
        self.sl_snr = Slider(b, "Input SNR", -5, 30, 8, fmt="{:.0f}", unit="dB",
                             accent=T.AMBER, command=lambda v: self.run())
        self.sl_snr.pack(fill="x")
        Tooltip(self.sl_snr, "Signal-to-noise ratio of the degraded input. "
                             "Lower is harder: below about 0 dB the noise "
                             "carries more power than the signal.")

        # ---------------- noise reduction ----------------
        c.fit()

        c = Card(col, "Noise Reduction", T.GREEN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.dd_denoise = Dropdown(b, "Algorithm", D.DENOISE_METHODS,
                                   "Wiener filter",
                                   command=self._denoise_changed, accent=T.GREEN)
        self.dd_denoise.pack(fill="x")
        self.sl_strength = Slider(b, "Strength", 0.0, 1.0, 0.5, fmt="{:.2f}",
                                  accent=T.GREEN, command=lambda v: self.run())
        self.sl_strength.pack(fill="x")
        self.sl_win = Slider(b, "Kernel / window", 3, 101, 21, step=2, fmt="{:.0f}",
                             unit="smp", accent=T.GREEN, command=lambda v: self.run())
        self.sl_win.pack(fill="x")

        # ---------------- filtering ----------------
        c.fit()

        c = Card(col, "Digital Filter", T.VIOLET, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.tg_filter = Toggle(b, "Filter enabled", True, lambda v: self.run(), T.VIOLET)
        self.tg_filter.pack(fill="x", pady=(0, 4))
        self.dd_family = Dropdown(b, "Family", D.FILTER_FAMILIES, D.FILTER_FAMILIES[0],
                                  command=self._family_changed, accent=T.VIOLET)
        self.dd_family.pack(fill="x")
        self.dd_ftype = Dropdown(b, "Response", D.FILTER_TYPES, "Low-pass",
                                 command=self._ftype_changed, accent=T.VIOLET)
        self.dd_ftype.pack(fill="x")
        self.sl_fc1 = Slider(b, "Cut-off f1", 20, 3900, 1500, fmt="{:.0f}", unit="Hz",
                             log=True, accent=T.VIOLET, command=lambda v: self.run())
        self.sl_fc1.pack(fill="x")
        self.sl_fc2 = Slider(b, "Cut-off f2 (band)", 40, 3950, 2400, fmt="{:.0f}",
                             unit="Hz", log=True, accent=T.VIOLET,
                             command=lambda v: self.run())
        self.sl_fc2.pack(fill="x")
        self.sl_order = Slider(b, "Order", 1, 12, 4, step=1, fmt="{:.0f}",
                               accent=T.VIOLET, command=lambda v: self.run())
        self.sl_order.pack(fill="x")
        self.tg_zero = Toggle(b, "Zero-phase (filtfilt)", True, lambda v: self.run(),
                              T.VIOLET)
        self.tg_zero.pack(fill="x", pady=(2, 0))
        Tooltip(self.tg_zero, "filtfilt runs the filter forwards then backwards, "
                              "cancelling phase distortion at the cost of "
                              "doubling the effective order. Turn it off to see "
                              "the causal phase shift in the waveform.")

        # ---------------- enhancement ----------------
        c.fit()

        c = Card(col, "Signal Enhancement", T.MAGENTA, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.sl_gate = Slider(b, "Noise gate", 0.0, 0.2, 0.0, fmt="{:.3f}",
                              accent=T.MAGENTA, command=lambda v: self.run())
        self.sl_gate.pack(fill="x")
        self.tg_norm = Toggle(b, "Normalize output", True, lambda v: self.run(), T.MAGENTA)
        self.tg_norm.pack(fill="x")

        # ---------------- transport ----------------
        c.fit()

        c = Card(col, "Transport & Export", T.LIME, pad=14)
        c.pack(fill="x", pady=(0, 14))
        b = c.body
        r1 = tk.Frame(b, bg=T.PANEL)
        r1.pack(fill="x")
        NeonButton(r1, "CLEAN", lambda: self.play(self.clean), T.CYAN, width=84,
                   height=30, icon="▶").pack(side="left")
        NeonButton(r1, "NOISY", lambda: self.play(self.noisy), T.AMBER, width=84,
                   height=30, icon="▶").pack(side="left", padx=6)
        NeonButton(r1, "PROCESSED", lambda: self.play(self.processed), T.LIME,
                   width=106, height=30, icon="▶").pack(side="left")
        r2 = tk.Frame(b, bg=T.PANEL)
        r2.pack(fill="x", pady=8)
        NeonButton(r2, "STOP", self.stop, T.RED, width=84, height=28).pack(side="left")
        NeonButton(r2, "SAVE WAV", self.save_wav, T.LIME, width=100, height=28,
                   icon="↓").pack(side="left", padx=6)
        NeonButton(r2, "PDF REPORT", self.export_report, T.VIOLET,
                   width=96, height=28).pack(side="left")
        self.meter = LevelMeter(b, height=10)
        self.meter.pack(fill="x", pady=(2, 0))
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
        views = PlotGrid(self, rows=3)
        views.grid(row=0, column=1, sticky="nsew")
        right = views.body
        right.columnconfigure(0, weight=3)
        right.columnconfigure(1, weight=2)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=3)
        right.rowconfigure(2, weight=3)

        # time domain
        c = Card(right, "Time Domain  ·  waveform comparison", T.CYAN)
        c.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.p_time = PlotPane(c.body, rows=3, cols=1, height=T.fh(4.0), hspace=0.42)
        self.p_time.widget.pack(fill="both", expand=True)
        Cursor(self.p_time, lambda x, y: "t=%.4f s   %.4f" % (x, y))

        # spectrum
        c = Card(right, "Frequency Domain  ·  FFT magnitude", T.MAGENTA)
        c.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.p_spec = PlotPane(c.body, height=T.fh(2.6))
        self.p_spec.widget.pack(fill="both", expand=True)
        Cursor(self.p_spec, lambda x, y: "%.1f Hz   %.1f dB" % (x, y))

        # spectrogram
        c = Card(right, "Spectrogram  ·  STFT time-frequency", T.VIOLET)
        c.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        self.p_sgram = PlotPane(c.body, rows=1, cols=2, height=T.fh(2.4), wspace=0.16)
        self.p_sgram.widget.pack(fill="both", expand=True)

        # filter response
        c = Card(right, "Filter Response", T.VIOLET)
        c.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        self.p_resp = PlotPane(c.body, rows=2, cols=1, height=T.fh(3.4), hspace=1.1)
        self.p_resp.widget.pack(fill="both", expand=True)
        Cursor(self.p_resp, lambda x, y: "%.1f Hz   %.2f dB" % (x, y))

        # metrics
        c = Card(right, "Measurements", T.LIME)
        c.grid(row=1, column=1, sticky="nsew", pady=(0, 8))
        b = c.body
        self.badges = tk.Frame(b, bg=T.PANEL)
        self.badges.pack(fill="x", pady=(0, 6))
        self.bd_snr = Badge(self.badges, "SNR --", T.GREEN, width=104, height=22)
        self.bd_snr.pack(side="left", padx=(0, 6))
        self.bd_gain = Badge(self.badges, "Δ --", T.CYAN, width=104, height=22)
        self.bd_gain.pack(side="left")
        self.stats = {}
        for key, label, acc in [
            ("sr", "Sample rate / length", T.TXT),
            ("snr_in", "SNR  noisy vs clean", T.AMBER),
            ("snr_out", "SNR  processed vs clean", T.GREEN),
            ("mse", "MSE  processed vs clean", T.TXT),
            ("rms", "RMS level / peak", T.CYAN),
            ("zcr", "Zero-crossing rate", T.VIOLET),
            ("cent", "Spectral centroid", T.VIOLET),
            ("dom", "Dominant frequency", T.MAGENTA),
            ("thd", "THD", T.MAGENTA),
        ]:
            r = StatRow(b, label, "--", acc, height=18)
            r.pack(fill="x")
            self.stats[key] = r

        # pipeline view
        c = Card(right, "Processing Chain", T.CYAN)
        c.grid(row=2, column=1, sticky="nsew")
        self.chain = tk.Canvas(c.body, bg=T.PANEL, highlightthickness=0)
        self.chain.pack(fill="both", expand=True)
        self.chain.bind("<Configure>", lambda e: self._draw_chain())

    # ------------------------------------------------------------ sources --
    def load_demo(self):
        """Speech-like demo: two formant-ish tones + an AM envelope."""
        sr = 8000
        t = np.arange(int(sr * 2.0)) / sr
        env = 0.5 + 0.5 * np.sin(2 * np.pi * 2.3 * t) ** 2
        x = (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 740 * t)
             + 0.25 * np.sin(2 * np.pi * 1180 * t))
        self.clean = D.normalize(x * env) * 0.8
        self.sr = sr
        self.source_name = "demo (synthetic vowel)"
        self._after_load()

    def generate(self):
        kind = self.dd_gen.get()
        self.clean, self.sr = D.generate(kind, sr=8000, dur=self.sl_dur.get(),
                                         freq=self.sl_freq.get())
        self.source_name = "generated: " + kind
        self._after_load()

    def load_wav(self):
        p = filedialog.askopenfilename(title="Open WAV file",
                                       filetypes=[("WAV audio", "*.wav"), ("All", "*.*")])
        if not p:
            return
        try:
            self.clean, self.sr = D.load_wav(p)
            self.clean = D.normalize(self.clean) * 0.9
            self.source_name = os.path.basename(p)
            self._after_load()
            self.app.status("Loaded %s  (%.2f s @ %d Hz)" %
                            (self.source_name, len(self.clean) / self.sr, self.sr), T.GREEN)
        except Exception as ex:
            messagebox.showerror("Load failed", str(ex))

    def record_mic(self):
        try:
            import sounddevice as sd
        except Exception:
            messagebox.showinfo("Microphone", "Install 'sounddevice' to record:\n\n"
                                              "pip install sounddevice")
            return
        sec = 3.0
        self.app.status("Recording %.0f s from microphone..." % sec, T.MAGENTA)

        def work():
            try:
                sr = 16000
                rec = sd.rec(int(sec * sr), samplerate=sr, channels=1, dtype="float64")
                sd.wait()
                self.clean = D.normalize(rec.flatten()) * 0.9
                self.sr = sr
                self.source_name = "microphone (%.0f s)" % sec
                self.after(0, self._after_load)
                self.after(0, lambda: self.app.status("Recording captured.", T.GREEN))
            except Exception as ex:
                msg = str(ex)               # `ex` is unbound once the except block ends
                self.after(0, lambda: messagebox.showerror("Record failed", msg))

        threading.Thread(target=work, daemon=True).start()

    def _after_load(self):
        nyq = self.sr / 2.0
        self.sl_fc1.hi = nyq * 0.98
        self.sl_fc2.hi = nyq * 0.99
        self.sl_fc1.set(min(self.sl_fc1.get(), nyq * 0.9))
        self.sl_fc2.set(min(self.sl_fc2.get(), nyq * 0.95))
        self.lbl_src.set(self.source_name[:22])
        self.run()

    # ---------------------------------------------------------- pipeline --
    def run(self, *_):
        if self._busy:
            return
        self._busy = True
        try:
            self._pipeline()
        except Exception as ex:
            self.app.status("Processing error: %s" % ex, T.RED)
        finally:
            self._busy = False

    def _pipeline(self):
        sr = self.sr
        x = self.clean

        # 1. degradation
        y = x.copy()
        if self.tg_noise.get():
            y = D.add_noise(y, self.dd_noise.get(), self.sl_snr.get(), sr)
        self.noisy = y

        # 2. noise reduction
        z = D.denoise(y, sr, self.dd_denoise.get(),
                      self.sl_strength.get(), int(self.sl_win.get()))

        # 3. filtering
        self._design = None
        if self.tg_filter.get():
            self._design = D.design_filter(
                self.dd_family.get(), self.dd_ftype.get(), sr,
                self.sl_fc1.get(), self.sl_fc2.get(), int(self.sl_order.get()))
            z = D.apply_filter(z, self._design, self.tg_zero.get())

        # 4. enhancement
        if self.sl_gate.get() > 0.001:
            z = D.noise_gate(z, sr, self.sl_gate.get())
        if self.tg_norm.get():
            z = D.normalize(z) * 0.95
        self.processed = z

        self._redraw()
        self._update_stats()
        self._draw_chain()

    # ------------------------------------------------------------- views --
    def _redraw(self):
        sr = self.sr
        p = self.p_time
        p.clear()
        rows = [(p.ax(0, 0), self.clean, T.SIG_ORIG, "ORIGINAL / CLEAN"),
                (p.ax(1, 0), self.noisy, T.SIG_NOISE, "DEGRADED (NOISY INPUT)"),
                (p.ax(2, 0), self.processed if getattr(self, "_show_processed", True)
                 else self.clean,
                 T.SIG_PROC if getattr(self, "_show_processed", True) else T.SIG_ORIG,
                 "PROCESSED OUTPUT" if getattr(self, "_show_processed", True)
                 else "CLEAN REFERENCE  (A/B - press Space)")]
        for i, (ax, data, col, name) in enumerate(rows):
            style_axes(ax, None, None, "Amp", col)
            plot_wave(ax, data, sr, col)
            lim = max(0.05, float(np.max(np.abs(data))) * 1.15)
            ax.set_ylim(-lim, lim)
            ax.text(0.0, 1.03, name, transform=ax.transAxes, va="bottom",
                    ha="left", color=col, fontsize=T.fs(7.5),
                    fontweight="bold")
            if i < 2:
                ax.set_xticklabels([])
        p.ax(2, 0).set_xlabel("Time (s)", color=T.TXT_MUTE, fontsize=T.fs(7.5))
        p.draw()

        # spectrum overlay
        ax = self.p_spec.ax()
        self.p_spec.clear()
        style_axes(ax, "Magnitude spectrum (dB)", "Frequency (Hz)", "dB", T.MAGENTA)
        f, m = D.spectrum(self.clean, sr)
        plot_spectrum(ax, f, m, T.SIG_ORIG, "clean")
        f, m = D.spectrum(self.noisy, sr)
        plot_spectrum(ax, f, m, T.SIG_NOISE, "noisy")
        f, m = D.spectrum(self.processed, sr)
        plot_spectrum(ax, f, m, T.SIG_PROC, "processed")
        self.p_spec.legend(ax)
        self.p_spec.draw()

        # spectrograms
        self.p_sgram.clear()
        for i, (data, name) in enumerate([(self.noisy, "Input"),
                                          (self.processed, "Output")]):
            ax = self.p_sgram.ax(0, i)
            style_axes(ax, "STFT · " + name, "Time (s)",
                       "Hz" if i == 0 else None, T.VIOLET)
            fq, tt, S = D.spectrogram(data, sr, 256)
            plot_spectrogram(ax, fq, tt, S)
        self.p_sgram.draw()

        # filter response
        self.p_resp.clear()
        a1, a2 = self.p_resp.ax(0, 0), self.p_resp.ax(1, 0)
        style_axes(a1, "Magnitude response", None, "dB", T.VIOLET)
        style_axes(a2, "Phase response", "Frequency (Hz)", "rad", T.VIOLET)
        if self._design is not None:
            w, mag, ph = D.filter_response(self._design, sr)
            a1.plot(w, mag, color=T.VIOLET, linewidth=1.1)
            a1.fill_between(w, -120, mag, color=T.VIOLET, alpha=0.15, linewidth=0)
            a1.axhline(-3, color=T.AMBER, linestyle="--", linewidth=0.7)
            a1.set_ylim(-80, 8)
            a1.set_xlim(0, sr / 2)
            a2.plot(w, ph, color=T.MAGENTA, linewidth=1.0)
            a2.set_xlim(0, sr / 2)
            for fc in ([self.sl_fc1.get(), self.sl_fc2.get()]
                       if "Band" in self.dd_ftype.get() else [self.sl_fc1.get()]):
                a1.axvline(fc, color=T.CYAN, linestyle=":", linewidth=0.8)
        else:
            a1.text(0.5, 0.5, "filter bypassed", ha="center", va="center",
                    color=T.TXT_MUTE, fontsize=T.fs(8), transform=a1.transAxes)
        self.p_resp.draw()

    def _update_stats(self):
        s = self.stats
        sr = self.sr
        s["sr"].set("%d Hz  /  %.2f s" % (sr, len(self.clean) / sr))
        snr_in = D.snr_db_aligned(self.clean, self.noisy)
        snr_out = D.snr_db_aligned(self.clean, self.processed)
        s["snr_in"].set("%.2f dB" % snr_in)
        s["snr_out"].set("%.2f dB" % snr_out)
        s["mse"].set("%.3e" % D.mse(self.clean, self.processed))
        s["rms"].set("%.1f dBFS  /  %.3f" % (D.rms_db(self.processed),
                                             float(np.max(np.abs(self.processed)))))
        s["zcr"].set("%.4f" % D.zero_crossing_rate(self.processed))
        s["cent"].set("%.1f Hz" % D.spectral_centroid(self.processed, sr))
        s["dom"].set("%.1f Hz" % D.dominant_freq(self.processed, sr))
        s["thd"].set("%.2f %%" % D.thd_percent(self.processed, sr))

        delta = snr_out - snr_in
        self.bd_snr.set("SNR %.1f dB" % snr_out,
                        T.GREEN if snr_out > snr_in else T.AMBER)
        self.bd_gain.set(("Δ %+.1f dB" % delta),
                         T.GREEN if delta > 0 else T.RED)
        self.meter.set_level(min(1.0, float(np.max(np.abs(self.processed)))))

    def _draw_chain(self):
        c = self.chain
        c.delete("all")
        w = c.winfo_width()
        if w < 10:
            return
        steps = [("SOURCE", self.source_name[:20], T.CYAN, True),
                 ("DEGRADE", self.dd_noise.get() if self.tg_noise.get() else "bypass",
                  T.AMBER, self.tg_noise.get()),
                 ("DENOISE", self.dd_denoise.get(), T.GREEN,
                  self.dd_denoise.get() != "None"),
                 ("FILTER", "%s %s" % (self.dd_ftype.get(),
                                       self.dd_family.get().split(" ")[0])
                  if self.tg_filter.get() else "bypass",
                  T.VIOLET, self.tg_filter.get()),
                 ("ENHANCE", " · ".join(
                     [n for n, on in (("gate", self.sl_gate.get() > 0.001),
                                      ("norm", self.tg_norm.get())) if on]) or "none",
                  T.MAGENTA, self.sl_gate.get() > 0.001 or self.tg_norm.get()),
                 ("OUTPUT", "%.2f s · %d Hz" % (len(self.processed) /
                                                max(self.sr, 1), self.sr), T.LIME, True)]
        h = c.winfo_height()
        gap = (h - T.ui(8)) / len(steps)
        box = gap - T.ui(6)
        y = T.ui(4)
        for i, (name, detail, col, on) in enumerate(steps):
            acc = col if on else T.TXT_MUTE
            T.round_rect(c, T.ui(2), y, w - T.ui(2), y + box, T.ui(6),
                         fill=T.mix(T.PANEL_2, acc, 0.10 if on else 0.0),
                         outline=T.mix(acc, T.PANEL, 0.45), width=1)
            cy = y + box / 2
            c.create_oval(T.ui(12), cy - T.ui(3), T.ui(18), cy + T.ui(3),
                          fill=acc, outline="")
            c.create_text(T.ui(28), cy, text=name, anchor="w", fill=acc,
                          font=T.F_LABEL)
            detail = fit_text(c, detail, T.F_SMALL, w - T.ui(126))
            c.create_text(T.ui(112), cy, text=detail, anchor="w",
                          fill=T.TXT_DIM, font=T.F_SMALL)
            y += gap

    # ---------------------------------------------------------- transport --
    def play(self, data):
        if data is None or len(data) < 2:
            return
        x = np.clip(D.normalize(data) * 0.85, -1, 1)
        try:
            import sounddevice as sd
            sd.stop()
            sd.play(x.astype(np.float32), self.sr)
            self.app.status("Playing %.2f s @ %d Hz" % (len(x) / self.sr, self.sr), T.LIME)
            return
        except Exception:
            pass
        try:
            import winsound
            p = os.path.join(tempfile.gettempdir(), "dspstudio_play.wav")
            D.save_wav(p, x, self.sr)
            winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
            self.app.status("Playing (winsound fallback)", T.LIME)
        except Exception as ex:
            self.app.status("Playback unavailable: %s" % ex, T.RED)

    def stop(self):
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        self.app.status("Playback stopped.", T.TXT_DIM)

    def save_wav(self):
        p = filedialog.asksaveasfilename(defaultextension=".wav",
                                         initialfile="processed.wav",
                                         filetypes=[("WAV audio", "*.wav")])
        if not p:
            return
        D.save_wav(p, self.processed, self.sr)
        self.app.status("Saved " + os.path.basename(p), T.GREEN)

    # ------------------------------------------------------ explanations --
    def _gen_changed(self, v):
        self.app.explain(E.lookup(E.GENERATORS, v))
        self.generate()

    def _noise_changed(self, v):
        self.app.explain(E.lookup(E.NOISE_MODELS, v))
        self.run()

    def _denoise_changed(self, v):
        self.app.explain(E.lookup(E.NOISE_REDUCTION, v))
        self.run()

    def _family_changed(self, v):
        self.app.explain(E.lookup(E.FILTERS, v))
        self.run()

    def _ftype_changed(self, v):
        blocks = E.lookup(E.FILTERS, self.dd_family.get())
        blocks = blocks + [("h", v), ("", E.RESPONSES.get(v, ""))]
        self.app.explain(blocks)
        self.run()

    def on_show(self):
        self.app.explain(E.lookup(E.NOISE_REDUCTION, self.dd_denoise.get()))

    # ---------------------------------------------------------- A/B view --
    def toggle_ab(self):
        """Flip the third waveform between the processed and the clean signal."""
        self._show_processed = not getattr(self, "_show_processed", True)
        self.app.status("Bottom trace: %s" %
                        ("processed output" if self._show_processed
                         else "clean reference (A/B)"), T.CYAN)
        self._redraw()

    # ------------------------------------------------------------ report --
    def export_report(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=os.path.basename(R.default_path("dsp_audio_report")),
            filetypes=[("PDF report", "*.pdf")])
        if not p:
            return
        snr_in = D.snr_db_aligned(self.clean, self.noisy)
        snr_out = D.snr_db_aligned(self.clean, self.processed)
        config = [("Source", self.source_name),
                  ("Sample rate", "%d Hz" % self.sr),
                  ("Duration", "%.2f s (%d samples)" % (len(self.clean) / self.sr,
                                                        len(self.clean))),
                  ("Noise model", self.dd_noise.get() if self.tg_noise.get()
                   else "none"),
                  ("Input SNR", "%.0f dB" % self.sl_snr.get()),
                  ("Noise reduction", self.dd_denoise.get()),
                  ("Strength / window", "%.2f  /  %d" % (self.sl_strength.get(),
                                                         int(self.sl_win.get()))),
                  ("Filter", "%s %s" % (self.dd_ftype.get(), self.dd_family.get())
                   if self.tg_filter.get() else "bypassed"),
                  ("Cut-off", "%.0f Hz / %.0f Hz" % (self.sl_fc1.get(),
                                                     self.sl_fc2.get())),
                  ("Order / phase", "%d  /  %s" % (int(self.sl_order.get()),
                                                   "zero-phase"
                                                   if self.tg_zero.get()
                                                   else "causal")),
                  ("Noise gate / normalise", "%.3f  /  %s" % (
                      self.sl_gate.get(), "yes" if self.tg_norm.get() else "no"))]
        metrics = [("SNR noisy vs clean", "%.2f dB" % snr_in),
                   ("SNR processed vs clean", "%.2f dB" % snr_out),
                   ("Improvement", "%+.2f dB" % (snr_out - snr_in)),
                   ("MSE", "%.3e" % D.mse(self.clean, self.processed)),
                   ("RMS level", "%.4f (%.1f dBFS)" % (D.rms(self.processed),
                                                       D.rms_db(self.processed))),
                   ("Zero-crossing rate", "%.4f" %
                    D.zero_crossing_rate(self.processed)),
                   ("Spectral centroid", "%.1f Hz" %
                    D.spectral_centroid(self.processed, self.sr)),
                   ("Dominant frequency", "%.1f Hz" %
                    D.dominant_freq(self.processed, self.sr)),
                   ("THD", "%.2f %%" % D.thd_percent(self.processed, self.sr))]
        figs = [("Time domain", self.p_time.fig),
                ("Magnitude spectrum", self.p_spec.fig),
                ("Spectrograms", self.p_sgram.fig),
                ("Filter response", self.p_resp.fig)]
        R.build(p, "Audio enhancement", self.source_name, config, metrics, figs)
        self.app.status("Report written to " + os.path.basename(p), T.GREEN)

    def save_output(self):
        self.save_wav()
