"""Audio / speech DSP engine.

Everything here is pure NumPy + SciPy and returns plain ndarrays so the GUI
layer stays free of signal-processing details.
"""
import numpy as np
from scipy import signal as sg
from scipy.io import wavfile

EPS = 1e-12


# ---------------------------------------------------------------- I/O -----
def load_wav(path, target_sr=None):
    """Read a WAV file -> (float32 mono in [-1,1], sample-rate)."""
    sr, data = wavfile.read(path)
    data = np.asarray(data)
    if data.dtype.kind == "i":
        data = data.astype(np.float64) / np.iinfo(data.dtype).max
    elif data.dtype.kind == "u":
        data = (data.astype(np.float64) - 128) / 128.0
    else:
        data = data.astype(np.float64)
    if data.ndim > 1:                      # stereo -> mono
        data = data.mean(axis=1)
    if target_sr and target_sr != sr:
        data = resample(data, sr, target_sr)
        sr = target_sr
    return data.astype(np.float64), int(sr)


def save_wav(path, x, sr):
    y = np.clip(x, -1.0, 1.0)
    wavfile.write(path, int(sr), (y * 32767).astype(np.int16))


def resample(x, sr_in, sr_out):
    n = int(round(len(x) * sr_out / float(sr_in)))
    return sg.resample(x, n)


# -------------------------------------------------- synthetic test signals -
def generate(kind, sr=8000, dur=2.0, freq=440.0, amp=0.6):
    """Build a reference test signal for the lab."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    k = kind.lower()
    if k == "sine":
        x = np.sin(2 * np.pi * freq * t)
    elif k == "square":
        x = sg.square(2 * np.pi * freq * t)
    elif k == "chirp (sweep)":
        x = sg.chirp(t, f0=freq * 0.1, f1=min(freq * 8, sr * 0.45), t1=dur, method="linear")
    elif k == "multi-tone":
        x = (np.sin(2 * np.pi * freq * t)
             + 0.6 * np.sin(2 * np.pi * freq * 3 * t)
             + 0.35 * np.sin(2 * np.pi * freq * 7.5 * t)) / 2.0
    else:
        x = np.sin(2 * np.pi * freq * t)
    return amp * normalize(np.asarray(x, dtype=np.float64)), sr


# ------------------------------------------------------------- corruption --
def add_noise(x, kind="gaussian (awgn)", snr_db=10.0, sr=8000):
    """Contaminate a clean signal so enhancement can be demonstrated."""
    k = kind.lower()
    n = len(x)
    if k.startswith("gaussian"):
        noise = np.random.randn(n)
    elif k.startswith("pink"):
        w = np.fft.rfft(np.random.randn(n))
        f = np.arange(len(w)) + 1.0
        noise = np.fft.irfft(w / np.sqrt(f), n)
    elif k.startswith("hum"):                       # 60 Hz mains + harmonics
        t = np.arange(n) / sr
        noise = (np.sin(2 * np.pi * 60 * t)
                 + 0.4 * np.sin(2 * np.pi * 180 * t)
                 + 0.2 * np.sin(2 * np.pi * 300 * t))
    elif k.startswith("impulse"):                   # salt & pepper clicks
        noise = np.zeros(n)
        idx = np.random.choice(n, max(1, n // 200), replace=False)
        noise[idx] = np.random.choice([-1.0, 1.0], len(idx))
    else:
        noise = np.random.randn(n)

    p_sig = np.mean(x ** 2) + EPS
    p_noi = np.mean(noise ** 2) + EPS
    scale = np.sqrt(p_sig / (p_noi * (10 ** (snr_db / 10.0))))
    return x + scale * noise


# ----------------------------------------------------------------- filters -
FILTER_FAMILIES = ["Butterworth (IIR)", "Chebyshev I (IIR)", "Elliptic (IIR)",
                   "FIR (Hamming window)"]
FILTER_TYPES = ["Low-pass", "High-pass", "Band-pass", "Band-stop (notch)"]
_BTYPE = {"Low-pass": "lowpass", "High-pass": "highpass",
          "Band-pass": "bandpass", "Band-stop (notch)": "bandstop"}


def design_filter(family, ftype, sr, fc1, fc2=None, order=4, ripple=1.0, atten=40.0):
    """Return (sos_or_taps, is_fir). Cut-offs are clipped to a valid band."""
    nyq = sr / 2.0
    btype = _BTYPE[ftype]
    if btype in ("bandpass", "bandstop"):
        lo, hi = sorted([max(fc1, 1.0), max(fc2 or fc1 * 2, 2.0)])
        hi = min(hi, nyq * 0.99)
        lo = min(lo, hi * 0.95)
        wn = [lo / nyq, hi / nyq]
    else:
        wn = min(max(fc1, 1.0), nyq * 0.99) / nyq

    if family.startswith("FIR"):
        taps = order * 8 + 1                       # odd length
        if btype == "highpass" or btype == "bandstop":
            taps += (taps + 1) % 2
        b = sg.firwin(taps, wn, window="hamming",
                      pass_zero=btype in ("lowpass", "bandstop"))
        return b, True

    kw = {}
    if family.startswith("Butter"):
        ft = "butter"
    elif family.startswith("Chebyshev"):
        ft, kw["rp"] = "cheby1", ripple
    else:
        ft, kw["rp"], kw["rs"] = "ellip", ripple, atten
    sos = sg.iirfilter(order, wn, btype=btype, ftype=ft, output="sos", **kw)
    return sos, False


def apply_filter(x, design, zero_phase=True):
    coeffs, is_fir = design
    if is_fir:
        if zero_phase and len(x) > 3 * len(coeffs):
            return sg.filtfilt(coeffs, [1.0], x)
        return sg.lfilter(coeffs, [1.0], x)
    if zero_phase:
        return sg.sosfiltfilt(coeffs, x)
    return sg.sosfilt(coeffs, x)


def filter_response(design, sr, n=1024):
    coeffs, is_fir = design
    if is_fir:
        w, h = sg.freqz(coeffs, [1.0], worN=n, fs=sr)
    else:
        w, h = sg.sosfreqz(coeffs, worN=n, fs=sr)
    mag = 20 * np.log10(np.abs(h) + EPS)
    phase = np.unwrap(np.angle(h))
    return w, mag, phase


# ---------------------------------------------------- noise reduction ------
DENOISE_METHODS = ["Spectral subtraction", "Wiener filter", "Median (de-click)",
                   "Moving average (FIR)", "None"]


def spectral_subtraction(x, sr, nfft=1024, hop=None, over_sub=2.0,
                         floor=0.02, noise_sec=0.25):
    """Classic Boll spectral subtraction with an over-subtraction factor."""
    hop = hop or nfft // 4
    win = sg.get_window("hann", nfft)
    f, t, Z = sg.stft(x, fs=sr, window=win, nperseg=nfft, noverlap=nfft - hop)
    mag, phase = np.abs(Z), np.angle(Z)
    noise_mag = _noise_profile(mag, max(1, int(noise_sec * sr / hop)))
    clean = mag - over_sub * noise_mag
    clean = np.maximum(clean, floor * mag)          # spectral floor
    _, y = sg.istft(clean * np.exp(1j * phase), fs=sr, window=win,
                    nperseg=nfft, noverlap=nfft - hop)
    return _fit(y, len(x))


def wiener_denoise(x, sr, nfft=1024, noise_sec=0.25, alpha=1.0):
    """Frequency-domain Wiener gain H = S/(S+N)."""
    hop = nfft // 4
    win = sg.get_window("hann", nfft)
    f, t, Z = sg.stft(x, fs=sr, window=win, nperseg=nfft, noverlap=nfft - hop)
    p = np.abs(Z) ** 2
    pn = _noise_profile(p, max(1, int(noise_sec * sr / hop))) * alpha
    gain = np.maximum(p - pn, 0) / (p + EPS)
    _, y = sg.istft(Z * gain, fs=sr, window=win, nperseg=nfft, noverlap=nfft - hop)
    return _fit(y, len(x))


def _noise_profile(S, nframes):
    """Noise template taken from the quietest frames, not blindly from the start.

    Using the lowest-energy frames keeps the estimate valid even when the
    recording starts mid-speech.
    """
    energy = S.sum(axis=0)
    k = min(max(nframes, 3), S.shape[1])
    idx = np.argsort(energy)[:k]
    return np.mean(S[:, idx], axis=1, keepdims=True)


def denoise(x, sr, method, strength=1.0, window=31):
    m = method.lower()
    if m.startswith("spectral"):
        return spectral_subtraction(x, sr, over_sub=1.0 + 2.0 * strength)
    if m.startswith("wiener"):
        return wiener_denoise(x, sr, alpha=strength)
    if m.startswith("median"):
        k = int(window) | 1
        return sg.medfilt(x, kernel_size=max(3, k))
    if m.startswith("moving"):
        k = max(3, int(window))
        return np.convolve(x, np.ones(k) / k, mode="same")
    return x.copy()


# ------------------------------------------------------- enhancement -------
def normalize(x, peak=1.0):
    m = np.max(np.abs(x)) + EPS
    return x / m * peak


def pre_emphasis(x, a=0.97):
    return np.append(x[0], x[1:] - a * x[:-1])


def amplitude_envelope(x, sr, ms=20):
    k = max(3, int(sr * ms / 1000.0))
    return np.sqrt(np.convolve(x ** 2, np.ones(k) / k, mode="same"))


def noise_gate(x, sr, threshold=0.02, ms=20):
    env = amplitude_envelope(x, sr, ms)
    return x * (env > threshold)


# ------------------------------------------------------------- analysis ----
def spectrum(x, sr, nfft=None, db=True):
    n = nfft or int(2 ** np.ceil(np.log2(max(len(x), 256))))
    n = min(n, 1 << 16)
    w = np.hanning(min(len(x), n))
    seg = x[:len(w)] * w
    X = np.fft.rfft(seg, n)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    mag = np.abs(X) / (len(w) / 2 + EPS)
    return (f, 20 * np.log10(mag + EPS)) if db else (f, mag)


def spectrogram(x, sr, nfft=512):
    f, t, S = sg.spectrogram(x, fs=sr, nperseg=nfft,
                             noverlap=int(nfft * 0.75), window="hann")
    return f, t, 10 * np.log10(S + EPS)


def snr_db(clean, test):
    n = min(len(clean), len(test))
    c, t = clean[:n], test[:n]
    return 10 * np.log10((np.sum(c ** 2) + EPS) / (np.sum((c - t) ** 2) + EPS))


def snr_db_aligned(clean, test):
    """SNR after the least-squares gain match, so loudness is not counted as noise.

    Outputs are normalised, so their level is arbitrary. Scaling `test` by the
    gain that best fits `clean` makes the noisy input and the processed output
    comparable: an untouched signal scores the same before and after.
    """
    n = min(len(clean), len(test))
    c, t = clean[:n], test[:n]
    g = np.dot(c, t) / (np.dot(t, t) + EPS)
    return snr_db(c, g * t)


def mse(a, b):
    n = min(len(a), len(b))
    return float(np.mean((a[:n] - b[:n]) ** 2))


def rms(x):
    return float(np.sqrt(np.mean(x ** 2) + EPS))


def rms_db(x):
    return 20 * np.log10(rms(x) + EPS)


def zero_crossing_rate(x):
    return float(np.mean(np.abs(np.diff(np.sign(x))) > 0))


def spectral_centroid(x, sr):
    f, mag = spectrum(x, sr, db=False)
    return float(np.sum(f * mag) / (np.sum(mag) + EPS))


def dominant_freq(x, sr):
    f, mag = spectrum(x, sr, db=False)
    return float(f[int(np.argmax(mag))])


def thd_percent(x, sr, harmonics=5):
    """Total harmonic distortion relative to the fundamental."""
    f, mag = spectrum(x, sr, db=False)
    i0 = int(np.argmax(mag))
    f0 = f[i0]
    if f0 <= 0:
        return 0.0
    fund = mag[i0]
    h = 0.0
    for k in range(2, harmonics + 2):
        idx = int(np.argmin(np.abs(f - k * f0)))
        if idx < len(mag):
            h += mag[idx] ** 2
    return float(100.0 * np.sqrt(h) / (fund + EPS))


def _fit(y, n):
    y = np.asarray(y, dtype=np.float64)
    if len(y) >= n:
        return y[:n]
    return np.pad(y, (0, n - len(y)))
