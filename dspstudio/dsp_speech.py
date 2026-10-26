"""Speech-specific DSP: pitch, formants, MFCC, voice activity detection."""
import numpy as np
from scipy import signal as sg
from scipy.fft import dct

EPS = 1e-12


# --------------------------------------------------------------- framing ---
def frame_signal(x, sr, frame_ms=30.0, hop_ms=10.0, window="hamming"):
    """Split into overlapping, windowed frames -> (frames[n_frames, N], times)."""
    N = max(8, int(sr * frame_ms / 1000.0))
    H = max(1, int(sr * hop_ms / 1000.0))
    if len(x) < N:
        x = np.pad(x, (0, N - len(x)))
    n_frames = 1 + (len(x) - N) // H
    idx = np.arange(N)[None, :] + H * np.arange(n_frames)[:, None]
    frames = x[idx] * sg.get_window(window, N)[None, :]
    times = (np.arange(n_frames) * H + N / 2.0) / sr
    return frames, times


# ----------------------------------------------------------------- pitch ---
def pitch_autocorr(x, sr, frame_ms=30.0, hop_ms=10.0, fmin=60.0, fmax=400.0):
    """F0 per frame by autocorrelation peak picking. Unvoiced frames -> NaN."""
    frames, times = frame_signal(x, sr, frame_ms, hop_ms)
    lag_min = int(sr / fmax)
    lag_max = min(int(sr / fmin), frames.shape[1] - 1)
    f0 = np.full(len(frames), np.nan)
    conf = np.zeros(len(frames))
    for i, fr in enumerate(frames):
        fr = fr - fr.mean()
        energy = np.dot(fr, fr)
        if energy < 1e-7 or lag_max <= lag_min:
            continue
        r = np.correlate(fr, fr, mode="full")[len(fr) - 1:]
        seg = r[lag_min:lag_max]
        if len(seg) < 3:
            continue
        k = int(np.argmax(seg))
        peak = seg[k] / (r[0] + EPS)
        if peak > 0.3:                       # voiced decision
            lag = lag_min + k
            # parabolic interpolation for sub-sample accuracy
            if 0 < k < len(seg) - 1:
                a, b, c = seg[k - 1], seg[k], seg[k + 1]
                lag += 0.5 * (a - c) / (a - 2 * b + c + EPS)
            f0[i] = sr / lag
        conf[i] = peak
    return median_smooth(f0), times, conf


def median_smooth(f0, k=5, tol=0.3):
    """Median-smooth the voiced track and drop octave slips.

    Autocorrelation pitch detectors pick the wrong peak on the first and last
    frame of a word, which shows up as an isolated spike. A short median fixes
    small wobble; anything still more than `tol` away from the local median was
    a wrong peak, so it is marked unvoiced rather than drawn as a real jump.
    """
    out = f0.copy()
    h = k // 2
    for i in range(len(f0)):
        if np.isnan(f0[i]):
            continue
        win = f0[max(0, i - h):min(len(f0), i + h + 1)]
        win = win[~np.isnan(win)]
        if len(win) < 2:
            continue
        med = float(np.median(win))
        if med > 0 and abs(f0[i] - med) / med > tol:
            out[i] = np.nan                      # octave slip, not real pitch
        else:
            out[i] = med
    return out


def pitch_cepstrum(x, sr, frame_ms=30.0, hop_ms=10.0, fmin=60.0, fmax=400.0):
    """F0 per frame from the real cepstrum (quefrency peak)."""
    frames, times = frame_signal(x, sr, frame_ms, hop_ms)
    q_min, q_max = int(sr / fmax), min(int(sr / fmin), frames.shape[1] // 2)
    f0 = np.full(len(frames), np.nan)
    for i, fr in enumerate(frames):
        if np.dot(fr, fr) < 1e-7 or q_max <= q_min:
            continue
        spec = np.abs(np.fft.rfft(fr, 2 * frames.shape[1]))
        ceps = np.fft.irfft(np.log(spec + EPS))
        seg = ceps[q_min:q_max]
        if len(seg) < 3:
            continue
        k = int(np.argmax(seg))
        if seg[k] > 0.06 * (np.std(ceps) + EPS) * 10:
            f0[i] = sr / (q_min + k)
    return f0, times


def cepstrum(x, sr, nfft=2048):
    """Real cepstrum of one segment, for the quefrency display."""
    seg = x[:nfft] * np.hanning(min(len(x), nfft))
    spec = np.abs(np.fft.rfft(seg, nfft))
    c = np.fft.irfft(np.log(spec + EPS))
    q = np.arange(len(c)) / float(sr)
    return q[:len(c) // 2], c[:len(c) // 2]


# -------------------------------------------------------------- formants ---
def lpc(frame, order):
    """Levinson-Durbin solution of the autocorrelation normal equations."""
    r = np.correlate(frame, frame, mode="full")[len(frame) - 1:len(frame) + order]
    if len(r) < order + 1 or r[0] < EPS:
        return np.zeros(order + 1)
    a = np.zeros(order + 1)
    a[0] = 1.0
    e = r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / (e + EPS)
        a_new = a.copy()
        a_new[1:i + 1] += k * a[i - 1::-1][:i]
        a = a_new
        e *= (1 - k * k)
        if e <= 0:
            break
    return a


def formants(x, sr, order=None, n=4):
    """Estimate the first `n` formant frequencies from the LPC pole angles."""
    order = order or int(2 + sr / 1000)
    seg = x * np.hamming(len(x))
    seg = np.append(seg[0], seg[1:] - 0.97 * seg[:-1])    # pre-emphasis
    a = lpc(seg, order)
    if not np.any(a[1:]):
        return [], None, None
    roots = np.roots(a)
    roots = roots[np.imag(roots) > 0.01]
    roots = roots[np.abs(roots) < 1.0]
    if len(roots) == 0:
        return [], a, None
    freqs = np.sort(np.angle(roots) * sr / (2 * np.pi))
    bws = -0.5 * (sr / (2 * np.pi)) * np.log(np.abs(roots))
    order_idx = np.argsort(np.angle(roots))
    bws = bws[order_idx]
    keep = (freqs > 90) & (freqs < sr / 2 - 200) & (bws < 700)
    return list(freqs[keep][:n]), a, lpc_envelope(a, sr)


def lpc_envelope(a, sr, n=512):
    """Spectral envelope |1/A(z)| in dB, for overlay on the FFT spectrum."""
    w, h = sg.freqz([1.0], a, worN=n, fs=sr)
    return w, 20 * np.log10(np.abs(h) + EPS)


# ------------------------------------------------------------------ MFCC ---
def mel_filterbank(sr, nfft, n_mels=26, fmin=0.0, fmax=None):
    fmax = fmax or sr / 2.0
    to_mel = lambda f: 2595.0 * np.log10(1.0 + f / 700.0)
    to_hz = lambda m: 700.0 * (10 ** (m / 2595.0) - 1.0)
    pts = to_hz(np.linspace(to_mel(fmin), to_mel(fmax), n_mels + 2))
    bins = np.floor((nfft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, nfft // 2 + 1))
    for m in range(1, n_mels + 1):
        l, c, r = bins[m - 1], bins[m], bins[m + 1]
        if c == l:
            c += 1
        if r <= c:
            r = c + 1
        for k in range(l, min(c, fb.shape[1])):
            fb[m - 1, k] = (k - l) / float(c - l)
        for k in range(c, min(r, fb.shape[1])):
            fb[m - 1, k] = (r - k) / float(r - c)
    return fb, pts[1:-1]


def mfcc(x, sr, n_mfcc=13, n_mels=26, frame_ms=25.0, hop_ms=10.0, nfft=512):
    """Standard MFCC front-end: pre-emphasis, mel filterbank, log, DCT-II."""
    y = np.append(x[0], x[1:] - 0.97 * x[:-1])
    frames, times = frame_signal(y, sr, frame_ms, hop_ms)
    nfft = max(nfft, frames.shape[1])
    power = (np.abs(np.fft.rfft(frames, nfft)) ** 2) / nfft
    fb, _ = mel_filterbank(sr, nfft, n_mels)
    mel = power @ fb.T
    log_mel = np.log(mel + EPS)
    coeffs = dct(log_mel, type=2, axis=1, norm="ortho")[:, :n_mfcc]
    return coeffs.T, log_mel.T, times          # [n_mfcc, frames], [n_mels, frames]


def mfcc_distance(ref, test, sr, n_mfcc=13, floor_db=30.0):
    """Average Euclidean distance between MFCC vectors; lower = closer.

    d = mean over frames of sqrt( sum_k (c_k - c'_k)^2 ),  k = 1 .. n_mfcc-1
    Coefficient 0 only measures loudness, so it is left out - a louder copy
    of the same voice scores 0. Only frames where `ref` has speech (within
    `floor_db` of its loudest frame) count, so silent gaps do not dominate.
    """
    c_ref, log_mel, _ = mfcc(ref, sr, n_mfcc)
    c_test, _, _ = mfcc(test, sr, n_mfcc)
    n = min(c_ref.shape[1], c_test.shape[1])
    energy = 10 * np.log10(np.exp(log_mel[:, :n]).sum(axis=0) + EPS)
    keep = energy > energy.max() - floor_db
    d = np.sqrt(np.sum((c_ref[1:, :n] - c_test[1:, :n]) ** 2, axis=0))
    return float(np.mean(d[keep])) if keep.any() else 0.0


def delta(feat, width=2):
    """First-order temporal derivative of a feature matrix."""
    n = feat.shape[1]
    out = np.zeros_like(feat)
    denom = 2.0 * sum(i * i for i in range(1, width + 1))
    pad = np.pad(feat, ((0, 0), (width, width)), mode="edge")
    for t in range(n):
        acc = np.zeros(feat.shape[0])
        for i in range(1, width + 1):
            acc += i * (pad[:, t + width + i] - pad[:, t + width - i])
        out[:, t] = acc / denom
    return out


# ------------------------------------------------- voice activity detection -
def vad(x, sr, frame_ms=25.0, hop_ms=10.0, energy_margin_db=9.0, zcr_max=0.35):
    """Energy + zero-crossing VAD. Returns a per-frame mask and merged segments."""
    frames, times = frame_signal(x, sr, frame_ms, hop_ms, window="boxcar")
    energy = 10 * np.log10(np.mean(frames ** 2, axis=1) + EPS)
    zcr = np.mean(np.abs(np.diff(np.sign(frames), axis=1)) > 0, axis=1)
    # Adaptive threshold: `margin` above the noise floor, but never so high
    # that it swallows the whole utterance when silence is only a few frames.
    floor = np.percentile(energy, 10)
    peak = np.percentile(energy, 95)
    thresh = floor + min(energy_margin_db, 0.5 * max(peak - floor, 0.0))
    speech = (energy > thresh) & (zcr < zcr_max)

    # smooth: drop 1-frame glitches, bridge short gaps
    s = speech.astype(int)
    for _ in range(2):
        s = np.convolve(s, np.ones(3), mode="same") >= 2
        s = s.astype(int)
    speech = s.astype(bool)

    segs, start = [], None
    for i, v in enumerate(speech):
        if v and start is None:
            start = times[i]
        elif not v and start is not None:
            segs.append((start, times[i]))
            start = None
    if start is not None:
        segs.append((start, times[-1]))
    segs = [(a, b) for a, b in segs if b - a > 0.04]
    return speech, times, energy, zcr, segs


def speech_summary(x, sr):
    """One-shot speech report used by the metrics panel."""
    f0, t, conf = pitch_autocorr(x, sr)
    voiced = ~np.isnan(f0)
    speech, _, energy, zcr, segs = vad(x, sr)
    total = len(x) / float(sr)
    spoken = sum(b - a for a, b in segs)
    return {
        "f0_mean": float(np.nanmean(f0)) if voiced.any() else 0.0,
        "f0_min": float(np.nanmin(f0)) if voiced.any() else 0.0,
        "f0_max": float(np.nanmax(f0)) if voiced.any() else 0.0,
        "voiced_pct": 100.0 * float(np.mean(voiced)),
        "segments": len(segs),
        "speech_sec": spoken,
        "silence_pct": 100.0 * (1.0 - spoken / max(total, EPS)),
        "zcr_mean": float(np.mean(zcr)),
        "energy_db": float(np.mean(energy)),
    }


# ----------------------------------------------- synthetic speech source ---
VOWELS = {                      # F1, F2, F3 in Hz (adult male averages)
    "a": (730, 1090, 2440),
    "e": (530, 1840, 2480),
    "i": (270, 2290, 3010),
    "o": (570, 840, 2410),
    "u": (300, 870, 2240),
}


def synth_vowel(vowel, sr, dur, f0=120.0, f0_drift=-8.0):
    """Source-filter synthesis: glottal pulse train through formant resonators."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    # glottal source: pulse train with a falling pitch contour
    f0_t = f0 + f0_drift * (t / max(dur, 1e-6)) + 2.0 * np.sin(2 * np.pi * 4.5 * t)
    phase = 2 * np.pi * np.cumsum(f0_t) / sr
    src = np.zeros(n)
    marks = np.where(np.diff(np.floor(phase / (2 * np.pi))) > 0)[0]
    src[marks] = 1.0
    src = sg.lfilter([1.0], [1.0, -0.94], src)          # glottal low-pass tilt

    y = np.zeros(n)
    for i, (f, bw, amp) in enumerate(zip(VOWELS[vowel], (80, 110, 160),
                                         (1.0, 0.65, 0.35))):
        r = np.exp(-np.pi * bw / sr)
        theta = 2 * np.pi * f / sr
        a = [1.0, -2 * r * np.cos(theta), r * r]
        y += amp * sg.lfilter([1 - r], a, src)
    env = np.minimum(1.0, np.minimum(t, dur - t) / 0.03)  # attack / release
    return y * env


def synth_utterance(sr=8000, pattern="a i u e o", vowel_dur=0.32, gap=0.12,
                    f0=120.0):
    """A short spoken-like phrase: vowels separated by silence.

    Gives the speech panel something realistic to analyse when no microphone
    or recording is available.
    """
    parts = []
    for i, v in enumerate(pattern.split()):
        v = v if v in VOWELS else "a"
        parts.append(synth_vowel(v, sr, vowel_dur, f0 + (i % 3) * 6))
        parts.append(np.zeros(int(sr * gap)))
    x = np.concatenate(parts) if parts else np.zeros(int(sr * 0.5))
    x = x / (np.max(np.abs(x)) + EPS) * 0.85
    return x, sr
