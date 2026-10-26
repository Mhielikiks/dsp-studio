"""One-click scenarios.

A preset is just a set of control values plus a sentence explaining what it
demonstrates. Applying one sets every control at once and reprocesses, so a
complete demonstration is one click instead of a dozen slider drags.
"""
from . import theme as T

# Each entry: (label, accent, {widget attribute: value}, what it shows)

AUDIO = [
    ("HISS REMOVAL", T.GREEN, {
        "tg_noise": True, "dd_noise": "Gaussian (AWGN)", "sl_snr": 5,
        "dd_denoise": "Wiener filter", "sl_strength": 0.55,
        "tg_filter": True, "dd_family": "Butterworth (IIR)",
        "dd_ftype": "Low-pass", "sl_fc1": 1800, "sl_order": 4,
        "tg_zero": True, "sl_gate": 0.0,
        "tg_norm": True,
    }, "Broadband hiss at 5 dB SNR, cleaned by a Wiener filter and a 1.8 kHz "
       "low-pass. Watch the SNR delta chip turn green."),

    ("HUM REMOVAL", T.AMBER, {
        "tg_noise": True, "dd_noise": "Hum 60 Hz + harmonics", "sl_snr": 6,
        "dd_denoise": "None", "tg_filter": True,
        "dd_family": "Elliptic (IIR)", "dd_ftype": "Band-stop (notch)",
        "sl_fc1": 45, "sl_fc2": 80, "sl_order": 6, "tg_zero": True,
        "sl_gate": 0.0, "tg_norm": True,
    }, "Mains interference at 60 Hz removed by a narrow band-stop notch - the "
       "spectrum shows the spike disappear, no denoiser needed."),

    ("CLICK REPAIR", T.MAGENTA, {
        "tg_noise": True, "dd_noise": "Impulse (clicks)", "sl_snr": 10,
        "dd_denoise": "Median (de-click)", "sl_win": 3,
        "tg_filter": False, "sl_gate": 0.0,
        "tg_norm": True,
    }, "Single-sample clicks removed by a 3-sample median filter. A linear "
       "filter would smear them; a longer window would also flatten the "
       "waveform peaks."),

    ("VOICE BAND", T.VIOLET, {
        "tg_noise": True, "dd_noise": "Pink (1/f)", "sl_snr": 8,
        "dd_denoise": "None",
        "tg_filter": True, "dd_family": "Butterworth (IIR)",
        "dd_ftype": "Band-pass", "sl_fc1": 80, "sl_fc2": 3400, "sl_order": 4,
        "tg_zero": True, "sl_gate": 0.0,
        "tg_norm": True,
    }, "Pink noise is strongest at low frequencies. An 80-3400 Hz band-pass "
       "keeps the voice range and drops the rumble below it and the hiss "
       "above it."),

    ("CLEAN / RESET", T.CYAN, {
        "tg_noise": False, "dd_denoise": "None",
        "tg_filter": False, "sl_gate": 0.0,
        "tg_norm": True,
    }, "Everything bypassed - the signal passes through untouched. Use it as "
       "the reference before turning anything on."),
]

SPEECH = [
    ("CLEAN SPEECH", T.GREEN, {
        "tg_noise": False, "dd_denoise": "None", "tg_band": False,
        "tg_preemph": True,
    }, "Baseline: pitch track, formants and MFCCs on a clean utterance."),

    ("NOISY SPEECH", T.AMBER, {
        "tg_noise": True, "sl_snr": 5, "dd_denoise": "None", "tg_band": False,
    }, "The same voice at 5 dB SNR. Watch the pitch track break up and the "
       "MFCC pattern blur - this is why enhancement matters."),

    ("ENHANCED", T.CYAN, {
        "tg_noise": True, "sl_snr": 5, "dd_denoise": "Wiener filter",
        "sl_strength": 0.6, "tg_band": False,
    }, "Same noisy input, now Wiener-filtered. Compare the pitch track and "
       "VAD segments against the previous preset."),

    ("TELEPHONE", T.VIOLET, {
        "tg_noise": True, "sl_snr": 12, "dd_denoise": "Wiener filter",
        "sl_strength": 0.4, "tg_band": True,
    }, "Band-limited to 300-3400 Hz. F1 survives, the higher formants are "
       "cut - why voices sound thin on a phone."),
]

IMAGE = [
    ("PHOTO DENOISE", T.GREEN, {
        "tg_noise": True, "dd_noise": "Gaussian", "sl_amount": 0.09,
        "sl_blur": 0, "dd_denoise": "Bilateral (edge-preserving)",
        "sl_strength": 0.5, "sl_k": 5, "dd_deblur": "None",
        "dd_enh": "None", "sl_amt": 1.0,
    }, "Sensor noise removed with a bilateral filter, which averages inside "
       "regions but not across edges. Check PSNR and SSIM."),

    ("SCAN REPAIR", T.AMBER, {
        "tg_noise": True, "dd_noise": "Salt & pepper", "sl_amount": 0.08,
        "sl_blur": 0, "dd_denoise": "Median", "sl_k": 5,
        "dd_deblur": "None", "dd_enh": "Sharpen (unsharp mask)", "sl_amt": 0.8,
    }, "Dead-pixel speckle cleaned by a median filter, then sharpened back."),

    ("DEBLUR", T.CYAN, {
        "tg_noise": True, "dd_noise": "Gaussian", "sl_amount": 0.02,
        "sl_blur": 13, "sl_angle": 25,
        "dd_denoise": "Bilateral (edge-preserving)", "sl_strength": 0.5,
        "sl_k": 5, "dd_deblur": "Wiener deconvolution", "sl_k_noise": 0.02,
        "dd_enh": "None",
    }, "Motion blur inverted by Wiener deconvolution. Deblurring amplifies "
       "noise, so a bilateral filter smooths it first. Try the inverse filter "
       "next to see why the regularisation term K exists."),

    ("MOIRE REMOVAL", T.MAGENTA, {
        "tg_noise": True, "dd_noise": "Periodic (moire)", "sl_amount": 0.12,
        "sl_blur": 0, "dd_denoise": "Notch (periodic noise)",
        "sl_strength": 0.95, "dd_deblur": "None", "dd_enh": "None",
    }, "Periodic interference shows as bright peaks in the 2-D FFT; the notch "
       "filter zeroes exactly those peaks and leaves the picture."),
]

VIDEO = [
    ("NOISY CLIP", T.AMBER, {
        "tg_noise": True, "dd_noise": "Gaussian", "sl_amount": 0.09,
        "sl_blur": 0, "dd_denoise": "None", "tg_deblur": False,
        "tg_temporal": False, "dd_enh": "None",
    }, "The degraded clip with no processing - the reference to beat."),

    ("SPATIAL ONLY", T.CYAN, {
        "tg_noise": True, "dd_noise": "Gaussian", "sl_amount": 0.09,
        "sl_blur": 0, "dd_denoise": "Median", "sl_k": 3,
        "tg_deblur": False, "tg_temporal": False, "dd_enh": "None",
    }, "A 2-D filter applied frame by frame. Note the PSNR gain."),

    ("SPATIAL + TEMPORAL", T.GREEN, {
        "tg_noise": True, "dd_noise": "Gaussian", "sl_amount": 0.09,
        "sl_blur": 0, "dd_denoise": "Median", "sl_k": 3,
        "tg_deblur": False, "tg_temporal": True, "dd_enh": "None",
    }, "The same filter plus motion-adaptive averaging over 5 frames. Noise "
       "is independent between frames so it cancels - a 2-D filter cannot do "
       "this. Compare the PSNR curve with the previous preset."),

    ("DEBLUR CLIP", T.MAGENTA, {
        "tg_noise": True, "dd_noise": "Gaussian", "sl_amount": 0.03,
        "sl_blur": 11, "dd_denoise": "None", "tg_deblur": True,
        "tg_temporal": True, "dd_enh": "None",
    }, "Motion-blurred, noisy footage: Wiener deconvolution inverts the blur "
       "in each frame, then temporal averaging removes the noise it "
       "amplified."),
]


def apply(panel, mapping, run=True):
    """Set every named control on `panel`, then reprocess once.

    Widgets are set without firing their own callbacks so the pipeline runs a
    single time at the end instead of once per control.
    """
    missing = []
    for attr, value in mapping.items():
        w = getattr(panel, attr, None)
        if w is None:
            missing.append(attr)
            continue
        try:
            w.set(value)
        except Exception:
            missing.append(attr)
    if run:
        runner = getattr(panel, "reprocess", None) or getattr(panel, "run", None)
        if runner:
            runner()
    return missing
