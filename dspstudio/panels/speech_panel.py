"""Speech analysis workbench: pitch, formants, MFCC and voice activity.

The same enhancement chain as the audio panel can be applied first, so the
effect of denoising on speech features is visible side by side.
"""
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import numpy as np

from .. import dsp_audio as D
from .. import dsp_speech as S
from .. import explain as E
from .. import report as R
from .. import presets as P
from .. import theme as T
from ..plots import (Cursor, PlotPane, plot_heatmap, plot_segments, plot_spectrum,
                     plot_wave, style_axes)
from ..widgets import PlotGrid, SlimScrollbar
from ..widgets import (attach_scroll, Badge, Card, Dropdown, NeonButton,
                       ProgressBar, Slider, StatRow, Toggle, Tooltip)

PHRASES = ["a i u e o", "a e i", "o u a i", "i i a o u e"]


class SpeechPanel(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=T.BG)
        self.app = app
        self.sr = 8000
        self.clean, self.sr = S.synth_utterance(8000)
        self.noisy = self.clean.copy()
        self.processed = self.clean.copy()
        self.name = "synthetic utterance"
        self._busy = False
        self._show_processed = True

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

        self._build_presets(col, P.SPEECH, T.GREEN)

        # -- source
        c = Card(col, "Speech Source", T.GREEN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x")
        NeonButton(r, "LOAD WAV", self.load_wav, T.GREEN, width=96,
                   height=30, icon="↑").pack(side="left")
        NeonButton(r, "RECORD 4s", self.record, T.MAGENTA, width=104,
                   height=30, icon="●").pack(side="left", padx=6)
        self.dd_phrase = Dropdown(b, "Synthesised utterance (vowels)", PHRASES,
                                  command=lambda v: self.synth(), accent=T.GREEN)
        self.dd_phrase.pack(fill="x", pady=(8, 0))
        Tooltip(self.dd_phrase, "Source-filter synthesis: a glottal pulse train "
                                "driven through formant resonators, one vowel "
                                "per symbol. Use it when no microphone is "
                                "available.")
        self.sl_f0 = Slider(b, "Synth pitch F0", 70, 260, 120, fmt="{:.0f}",
                            unit="Hz", accent=T.GREEN, command=lambda v: self.synth())
        self.sl_f0.pack(fill="x")
        self.st_src = StatRow(b, "LOADED", self.name[:22], T.GREEN)
        self.st_src.pack(fill="x")

        # -- degradation + enhancement
        c.fit()

        c = Card(col, "Degrade & Enhance", T.AMBER, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.tg_noise = Toggle(b, "Add noise", False, lambda v: self.run(), T.AMBER)
        self.tg_noise.pack(fill="x")
        self.sl_snr = Slider(b, "Input SNR", -5, 30, 10, fmt="{:.0f}", unit="dB",
                             accent=T.AMBER, command=lambda v: self.run())
        self.sl_snr.pack(fill="x")
        self.dd_denoise = Dropdown(b, "Enhancement", D.DENOISE_METHODS, "None",
                                   command=self._denoise_changed, accent=T.GREEN)
        self.dd_denoise.pack(fill="x")
        self.sl_strength = Slider(b, "Strength", 0.0, 1.0, 0.5, fmt="{:.2f}",
                                  accent=T.GREEN, command=lambda v: self.run())
        self.sl_strength.pack(fill="x")
        self.tg_band = Toggle(b, "Telephone band 300-3400 Hz", False,
                              lambda v: self.run(), T.VIOLET)
        self.tg_band.pack(fill="x")
        Tooltip(self.tg_band, "Band-pass the signal to the classic telephony "
                              "band. Shows how much of a voice survives a "
                              "300-3400 Hz channel.")
        self.tg_preemph = Toggle(b, "Pre-emphasis before analysis", True,
                                 lambda v: self.run(), T.VIOLET)
        self.tg_preemph.pack(fill="x")

        # -- analysis settings
        c.fit()

        c = Card(col, "Analysis Settings", T.CYAN, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.dd_pitch = Dropdown(b, "Pitch algorithm",
                                 ["Autocorrelation", "Cepstrum", "Both"], "Both",
                                 command=self._pitch_changed, accent=T.CYAN)
        self.dd_pitch.pack(fill="x")
        self.sl_frame = Slider(b, "Frame length", 10, 60, 30, fmt="{:.0f}",
                               unit="ms", accent=T.CYAN, command=lambda v: self.run())
        self.sl_frame.pack(fill="x")
        self.sl_hop = Slider(b, "Hop", 5, 25, 10, fmt="{:.0f}", unit="ms",
                             accent=T.CYAN, command=lambda v: self.run())
        self.sl_hop.pack(fill="x")
        self.sl_fmin = Slider(b, "F0 search min", 50, 150, 60, fmt="{:.0f}",
                              unit="Hz", accent=T.CYAN, command=lambda v: self.run())
        self.sl_fmin.pack(fill="x")
        self.sl_fmax = Slider(b, "F0 search max", 200, 600, 400, fmt="{:.0f}",
                              unit="Hz", accent=T.CYAN, command=lambda v: self.run())
        self.sl_fmax.pack(fill="x")
        self.sl_nmfcc = Slider(b, "MFCC coefficients", 8, 20, 13, step=1,
                               fmt="{:.0f}", accent=T.CYAN,
                               command=lambda v: self.run())
        self.sl_nmfcc.pack(fill="x")

        # -- VAD + frame probe
        c.fit()

        c = Card(col, "VAD & Frame Probe", T.MAGENTA, pad=14)
        c.pack(fill="x", pady=(0, 8))
        b = c.body
        self.sl_margin = Slider(b, "VAD threshold margin", 3, 20, 9, fmt="{:.0f}",
                                unit="dB", accent=T.MAGENTA,
                                command=lambda v: self.run())
        self.sl_margin.pack(fill="x")
        self.sl_zcr = Slider(b, "VAD max ZCR", 0.1, 0.8, 0.35, fmt="{:.2f}",
                             accent=T.MAGENTA, command=lambda v: self.run())
        self.sl_zcr.pack(fill="x")
        self.sl_probe = Slider(b, "Formant probe position", 0.0, 1.0, 0.25,
                               fmt="{:.2f}", accent=T.MAGENTA,
                               command=lambda v: self.run())
        self.sl_probe.pack(fill="x")
        Tooltip(self.sl_probe, "Chooses which frame of the utterance the LPC "
                               "spectral envelope and formant estimate are "
                               "computed from.")

        # -- export
        c.fit()

        c = Card(col, "Playback & Export", T.LIME, pad=14)
        c.pack(fill="x", pady=(0, 14))
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x")
        NeonButton(r, "PLAY", lambda: self.play(self.processed), T.LIME,
                   width=78, height=28, icon="▶").pack(side="left")
        NeonButton(r, "ORIGINAL", lambda: self.play(self.clean), T.CYAN,
                   width=92, height=28).pack(side="left", padx=6)
        NeonButton(r, "STOP", self.stop, T.RED, width=64,
                   height=28).pack(side="left")
        r2 = tk.Frame(b, bg=T.PANEL)
        r2.pack(fill="x", pady=8)
        NeonButton(r2, "SAVE WAV", self.save_output, T.LIME, width=96,
                   height=28).pack(side="left")
        NeonButton(r2, "PDF REPORT", self.export_report, T.VIOLET,
                   width=110, height=28).pack(side="left", padx=6)
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
        views = PlotGrid(self, rows=3)
        views.grid(row=0, column=1, sticky="nsew")
        right = views.body
        right.columnconfigure(0, weight=3)
        right.columnconfigure(1, weight=2)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        c = Card(right, "Waveform  ·  voice activity detection", T.GREEN)
        c.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.p_wave = PlotPane(c.body, rows=2, cols=1, height=T.fh(2.9), hspace=0.25)
        self._zcr_axis = self.p_wave.ax(1, 0).twinx()
        self.p_wave.widget.pack(fill="both", expand=True)
        Cursor(self.p_wave, lambda x, y: "t=%.3f s   %.3f" % (x, y))

        c = Card(right, "Pitch track  ·  F0 contour", T.CYAN)
        c.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        self.p_pitch = PlotPane(c.body, height=T.fh(2.4))
        self.p_pitch.widget.pack(fill="both", expand=True)
        Cursor(self.p_pitch, lambda x, y: "t=%.3f s   F0=%.1f Hz" % (x, y))

        c = Card(right, "MFCC & mel spectrogram", T.VIOLET)
        c.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        self.p_mfcc = PlotPane(c.body, rows=2, cols=1, height=T.fh(2.7), hspace=0.45)
        self.p_mfcc.widget.pack(fill="both", expand=True)

        c = Card(right, "LPC envelope & formants", T.MAGENTA)
        c.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        self.p_lpc = PlotPane(c.body, height=T.fh(2.6))
        self.p_lpc.widget.pack(fill="both", expand=True)
        Cursor(self.p_lpc, lambda x, y: "%.0f Hz   %.1f dB" % (x, y))

        c = Card(right, "Cepstrum  ·  quefrency", T.AMBER)
        c.grid(row=1, column=1, sticky="nsew", pady=(0, 8))
        self.p_ceps = PlotPane(c.body, height=T.fh(2.2))
        self.p_ceps.widget.pack(fill="both", expand=True)
        Cursor(self.p_ceps, lambda x, y: "q=%.4f s  (%.0f Hz)" %
               (x, 1.0 / x if x else 0))

        c = Card(right, "Speech Measurements", T.LIME)
        c.grid(row=2, column=1, sticky="nsew")
        b = c.body
        r = tk.Frame(b, bg=T.PANEL)
        r.pack(fill="x", pady=(0, 5))
        self.bd_f0 = Badge(r, "F0 --", T.CYAN, width=100, height=22)
        self.bd_f0.pack(side="left", padx=(0, 6))
        self.bd_voiced = Badge(r, "voiced --", T.GREEN, width=100,
                               height=22)
        self.bd_voiced.pack(side="left")
        self.stats = {}
        for key, label, acc in [
                ("f0", "F0 mean / min / max", T.CYAN),
                ("voiced", "Voiced frames", T.GREEN),
                ("segs", "Speech segments", T.GREEN),
                ("spoken", "Speech / silence", T.TXT),
                ("formants", "Formants F1-F3", T.MAGENTA),
                ("zcr", "Zero-crossing rate", T.VIOLET),
                ("snr", "SNR vs clean", T.AMBER),
                ("mfcc_noisy", "MFCC distance: noisy", T.AMBER),
                ("mfcc_out", "MFCC distance: output", T.GREEN)]:
            row = StatRow(b, label, "--", acc, height=18)
            row.pack(fill="x")
            self.stats[key] = row
        for key in ("mfcc_noisy", "mfcc_out"):
            Tooltip(self.stats[key],
                    "Average distance between the MFCC vectors of this signal "
                    "and the clean one, over the frames that contain speech. "
                    "Lower = sounds closer to the clean voice; 0 = identical. "
                    "Enhancement worked if the output is lower than the noisy "
                    "input.")

    # ------------------------------------------------------------ sources --
    def synth(self):
        self.clean, self.sr = S.synth_utterance(8000, self.dd_phrase.get(),
                                                f0=self.sl_f0.get())
        self.name = "synth: " + self.dd_phrase.get()
        self.st_src.set(self.name[:22])
        self.run()

    def load_wav(self):
        p = filedialog.askopenfilename(title="Open speech WAV",
                                       filetypes=[("WAV audio", "*.wav"),
                                                  ("All files", "*.*")])
        if not p:
            return
        try:
            x, sr = D.load_wav(p)
            if sr > 16000:                      # speech analysis needs no more
                x, sr = D.resample(x, sr, 16000), 16000
            self.clean, self.sr = D.normalize(x) * 0.9, sr
            self.name = os.path.basename(p)
            self.st_src.set(self.name[:22])
            self.run()
            self.app.status("Loaded %s (%.2f s @ %d Hz)" %
                            (self.name, len(x) / sr, sr), T.GREEN)
        except Exception as ex:
            messagebox.showerror("Load failed", str(ex))

    def record(self):
        try:
            import sounddevice as sd
        except Exception:
            messagebox.showinfo("Microphone",
                                "Install 'sounddevice' to record:\n\n"
                                "pip install sounddevice")
            return
        self.prog.start("recording 4 s...")
        self.app.status("Recording - speak now.", T.MAGENTA)

        def work():
            try:
                sr = 16000
                rec = sd.rec(int(4.0 * sr), samplerate=sr, channels=1,
                             dtype="float64")
                sd.wait()
                self.clean = D.normalize(rec.flatten()) * 0.9
                self.sr = sr
                self.name = "microphone 4 s"
                self.after(0, self._after_record)
            except Exception as ex:
                msg = str(ex)               # `ex` is unbound once the except block ends
                self.after(0, lambda: messagebox.showerror("Record failed", msg))

        threading.Thread(target=work, daemon=True).start()

    def _after_record(self):
        self.prog.stop("")
        self.st_src.set(self.name)
        self.run()
        self.app.status("Recording captured - analysing speech.", T.GREEN)

    # -------------------------------------------------------- explanations --
    def _denoise_changed(self, v):
        self.app.explain(E.lookup(E.NOISE_REDUCTION, v))
        self.run()

    def _pitch_changed(self, v):
        key = "Pitch (cepstrum)" if v == "Cepstrum" else "Pitch (autocorrelation)"
        self.app.explain(E.lookup(E.SPEECH, key))
        self.run()

    def on_show(self):
        self.app.explain(E.lookup(E.SPEECH, "MFCC"))

    # ------------------------------------------------------------ pipeline --
    def run(self, *_):
        if self._busy:
            return
        self._busy = True
        try:
            self._pipeline()
        except Exception as ex:
            self.app.status("Speech analysis error: %s" % ex, T.RED)
        finally:
            self._busy = False

    def _pipeline(self):
        sr = self.sr
        y = self.clean.copy()
        if self.tg_noise.get():
            y = D.add_noise(y, "Gaussian (AWGN)", self.sl_snr.get(), sr)
        self.noisy = y

        z = D.denoise(y, sr, self.dd_denoise.get(), self.sl_strength.get(), 21)
        if self.tg_band.get():
            des = D.design_filter("Butterworth (IIR)", "Band-pass", sr,
                                  300, min(3400, sr / 2 * 0.95), 4)
            z = D.apply_filter(z, des, True)
        self.processed = D.normalize(z) * 0.9

        self._analyse()

    def _analyse(self):
        sr = self.sr
        x = self.processed
        a = x if not self.tg_preemph.get() else D.pre_emphasis(x)
        fr_ms, hop_ms = self.sl_frame.get(), self.sl_hop.get()

        # --- voice activity ------------------------------------------------
        speech, vt, energy, zcr, segs = S.vad(
            x, sr, fr_ms, hop_ms, self.sl_margin.get(), self.sl_zcr.get())

        p = self.p_wave
        p.clear()
        ax = p.ax(0, 0)
        wave = x if self._show_processed else self.clean
        wave_segs = segs if self._show_processed else S.vad(
            wave, sr, fr_ms, hop_ms, self.sl_margin.get(), self.sl_zcr.get())[4]
        title = "PROCESSED + VAD SEGMENTS" if self._show_processed else "ORIGINAL + VAD SEGMENTS"
        style_axes(ax, title, None, "Amp", T.GREEN)
        plot_wave(ax, wave, sr, T.SIG_PROC if self._show_processed else T.SIG_ORIG)
        plot_segments(ax, wave_segs, T.GREEN, 0.16, "voiced segment")
        ax.tick_params(axis="x", labelbottom=False)
        p.legend(ax, above=True)

        ax = p.ax(1, 0)
        style_axes(ax, "ENERGY & ZERO-CROSSING RATE", "Time (s)", "dB / ZCR", T.AMBER)
        ax.plot(vt, energy, color=T.AMBER, linewidth=0.9, label="frame energy dB")
        ax2 = self._zcr_axis
        ax2.clear()
        ax2.plot(vt, zcr, color=T.VIOLET, linewidth=0.8, label="ZCR")
        ax2.set_ylim(0, 1)
        ax2.tick_params(colors=T.TXT_DIM, labelsize=T.fs(8))
        for sp in ax2.spines.values():
            sp.set_color(T.STROKE)
        p.draw()

        # --- pitch ---------------------------------------------------------
        mode = self.dd_pitch.get()
        f0a = f0c = None
        if mode in ("Autocorrelation", "Both"):
            f0a, ta, conf = S.pitch_autocorr(a, sr, fr_ms, hop_ms,
                                             self.sl_fmin.get(), self.sl_fmax.get())
        if mode in ("Cepstrum", "Both"):
            f0c, tc = S.pitch_cepstrum(a, sr, fr_ms, hop_ms,
                                       self.sl_fmin.get(), self.sl_fmax.get())
        ax = self.p_pitch.ax()
        self.p_pitch.clear()
        style_axes(ax, "F0 contour (unvoiced frames left blank)", "Time (s)",
                   "F0 (Hz)", T.CYAN)
        plot_segments(ax, segs, T.GREEN, 0.10)
        if f0a is not None:
            ax.plot(ta, f0a, "o-", color=T.CYAN, markersize=2.0, linewidth=1.0,
                    label="autocorrelation")
        if f0c is not None:
            ax.plot(tc, f0c, "o", color=T.MAGENTA, markersize=2.0, alpha=0.75,
                    label="cepstrum")
        ax.set_ylim(self.sl_fmin.get() * 0.8, self.sl_fmax.get() * 1.05)
        ax.set_xlim(0, len(x) / sr)
        self.p_pitch.legend(ax)
        self.p_pitch.draw()

        # --- MFCC ----------------------------------------------------------
        coeffs, log_mel, mt = S.mfcc(x, sr, int(self.sl_nmfcc.get()),
                                     frame_ms=max(20.0, fr_ms), hop_ms=hop_ms)
        p = self.p_mfcc
        p.clear()
        ax = p.ax(0, 0)
        style_axes(ax, "Mel filterbank energies (log)", None, "mel band", T.VIOLET)
        plot_heatmap(ax, log_mel, mt)
        ax.set_xticklabels([])
        ax = p.ax(1, 0)
        style_axes(ax, "MFCC", "Time (s)", "coefficient", T.VIOLET)
        plot_heatmap(ax, coeffs, mt, cmap="viridis")
        p.draw()

        # --- LPC envelope / formants ---------------------------------------
        pos = self.sl_probe.get()
        N = max(256, int(sr * 0.032))
        start = int(min(max(0, len(x) - N - 1), pos * (len(x) - N)))
        frame = x[start:start + N]
        fo, acoef, env = S.formants(frame, sr)
        ax = self.p_lpc.ax()
        self.p_lpc.clear()
        style_axes(ax, "Frame at t = %.2f s" % (start / sr), "Frequency (Hz)",
                   "dB", T.MAGENTA)
        f, mag = D.spectrum(frame, sr)
        plot_spectrum(ax, f, mag - float(np.max(mag)), T.TXT_MUTE, "FFT", floor=-80)
        if env is not None:
            w, m = env
            m = m - float(np.max(m))
            ax.plot(w, m, color=T.MAGENTA, linewidth=1.5, label="LPC envelope")
            for i, fq in enumerate(fo[:4]):
                ax.axvline(fq, color=T.LIME, linestyle="--", linewidth=0.9)
                ax.text(fq, -6, "F%d" % (i + 1), color=T.LIME, fontsize=T.fs(7),
                        ha="center")
        ax.set_xlim(0, sr / 2)
        self.p_lpc.legend(ax)
        self.p_lpc.draw()

        # --- cepstrum ------------------------------------------------------
        q, c = S.cepstrum(frame, sr, 2048)
        ax = self.p_ceps.ax()
        self.p_ceps.clear()
        style_axes(ax, "Real cepstrum of the probe frame", "Quefrency (s)",
                   "amplitude", T.AMBER)
        lo = int(sr / self.sl_fmax.get())
        hi = min(int(sr / self.sl_fmin.get()), len(c) - 1)
        ax.plot(q, c, color=T.AMBER, linewidth=0.8)
        if hi > lo:
            k = lo + int(np.argmax(c[lo:hi]))
            ax.axvline(q[k], color=T.CYAN, linestyle="--", linewidth=1.0)
            ax.text(q[k], float(np.max(c[lo:hi])),
                    "  F0 = %.0f Hz" % (sr / max(k, 1)), color=T.CYAN, fontsize=T.fs(7.5))
        ax.set_xlim(0, min(0.02, q[-1]))
        self.p_ceps.draw()

        # --- metrics -------------------------------------------------------
        summ = S.speech_summary(x, sr)
        s = self.stats
        s["f0"].set("%.0f / %.0f / %.0f Hz" % (summ["f0_mean"], summ["f0_min"],
                                               summ["f0_max"]))
        s["voiced"].set("%.1f %%" % summ["voiced_pct"])
        s["segs"].set("%d" % len(segs))
        s["spoken"].set("%.2f s  /  %.0f %%" % (summ["speech_sec"],
                                                summ["silence_pct"]))
        s["formants"].set(" / ".join("%.0f" % f for f in fo[:3]) + " Hz"
                          if fo else "--")
        s["zcr"].set("%.4f" % summ["zcr_mean"])
        s["snr"].set("%.2f dB" % D.snr_db_aligned(self.clean, self.processed))
        d_noisy = S.mfcc_distance(self.clean, self.noisy, sr)
        d_out = S.mfcc_distance(self.clean, self.processed, sr)
        s["mfcc_noisy"].set("%.2f" % d_noisy)
        s["mfcc_out"].set("%.2f" % d_out, T.GREEN if d_out < d_noisy - 0.05
                          else T.AMBER if d_out <= d_noisy + 0.05 else T.RED)
        self.bd_f0.set("F0 %.0f Hz" % summ["f0_mean"], T.CYAN)
        self.bd_voiced.set("voiced %.0f%%" % summ["voiced_pct"], T.GREEN)
        self._last = dict(segs=segs, formants=fo, summary=summ,
                          mfcc_dist=(d_noisy, d_out))

    # ------------------------------------------------------------ actions --
    def toggle_ab(self):
        self._show_processed = not self._show_processed
        self.app.status("Waveform showing %s" %
                        ("processed" if self._show_processed else "original"),
                        T.CYAN)
        self._analyse()

    def play(self, data):
        if data is None or len(data) < 2:
            return
        x = np.clip(D.normalize(data) * 0.85, -1, 1)
        try:
            import sounddevice as sd
            sd.stop()
            sd.play(x.astype(np.float32), self.sr)
            self.app.status("Playing %.2f s" % (len(x) / self.sr), T.LIME)
            return
        except Exception:
            pass
        try:
            import tempfile
            import winsound
            p = os.path.join(tempfile.gettempdir(), "dspstudio_speech.wav")
            D.save_wav(p, x, self.sr)
            winsound.PlaySound(p, winsound.SND_FILENAME | winsound.SND_ASYNC)
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

    def save_output(self):
        p = filedialog.asksaveasfilename(defaultextension=".wav",
                                         initialfile="speech_processed.wav",
                                         filetypes=[("WAV audio", "*.wav")])
        if not p:
            return
        D.save_wav(p, self.processed, self.sr)
        self.app.status("Saved " + os.path.basename(p), T.GREEN)

    def export_report(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=os.path.basename(
                R.default_path("dsp_speech_report")),
            filetypes=[("PDF report", "*.pdf")])
        if not p:
            return
        su = getattr(self, "_last", {}).get("summary", {})
        fo = getattr(self, "_last", {}).get("formants", [])
        config = [("Source", self.name),
                  ("Sample rate", "%d Hz" % self.sr),
                  ("Noise", "AWGN %.0f dB" % self.sl_snr.get()
                   if self.tg_noise.get() else "none"),
                  ("Enhancement", self.dd_denoise.get()),
                  ("Telephone band", "yes" if self.tg_band.get() else "no"),
                  ("Frame / hop", "%.0f / %.0f ms" % (self.sl_frame.get(),
                                                      self.sl_hop.get())),
                  ("Pitch algorithm", self.dd_pitch.get())]
        metrics = [("F0 mean", "%.1f Hz" % su.get("f0_mean", 0)),
                   ("F0 range", "%.0f - %.0f Hz" % (su.get("f0_min", 0),
                                                    su.get("f0_max", 0))),
                   ("Voiced frames", "%.1f %%" % su.get("voiced_pct", 0)),
                   ("Speech segments", "%d" % len(getattr(self, "_last", {})
                                                  .get("segs", []))),
                   ("Silence", "%.0f %%" % su.get("silence_pct", 0)),
                   ("Formants", " / ".join("%.0f Hz" % f for f in fo[:3])),
                   ("SNR vs clean", "%.2f dB" % D.snr_db_aligned(self.clean,
                                                                 self.processed)),
                   ("MFCC distance noisy / output",
                    "%.2f  /  %.2f  (lower = closer to clean)"
                    % getattr(self, "_last", {}).get("mfcc_dist", (0.0, 0.0)))]
        figs = [("Waveform and voice activity", self.p_wave.fig),
                ("Pitch contour", self.p_pitch.fig),
                ("MFCC and mel spectrogram", self.p_mfcc.fig),
                ("LPC envelope and formants", self.p_lpc.fig),
                ("Cepstrum", self.p_ceps.fig)]
        R.build(p, "Speech analysis", self.name, config, metrics, figs)
        self.app.status("Report written to " + os.path.basename(p), T.GREEN)
