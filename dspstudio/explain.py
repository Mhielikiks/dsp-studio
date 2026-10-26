"""Algorithm reference shown inside the app.

Every entry answers the three questions an examiner asks: what does it do,
what is the maths, and what does each knob change. Keys match the option
strings used by the dropdowns so a selection can look itself up.
"""

# tag vocabulary for InfoPanel.set_blocks: 'h' heading, 'eq' equation,
# 'key' parameter name, 'dim' secondary text, '' body text.

NOISE_REDUCTION = {
    "Spectral subtraction": [
        ("h", "Spectral subtraction (Boll, 1979)"),
        ("", "Estimates the noise magnitude spectrum during non-speech frames "
             "and subtracts it from every frame, keeping the noisy phase."),
        ("eq", "|S(f)| = max( |Y(f)| - a*|N(f)| , b*|Y(f)| )"),
        ("eq", "s(t)  = ISTFT( |S(f)| * e^(j*angle(Y(f))) )"),
        ("dim", "Y = noisy spectrum, N = noise estimate, a = over-subtraction, "
                "b = spectral floor."),
        ("key", "Strength"),
        ("", "Sets the over-subtraction factor a (1 to 3). Higher removes more "
             "noise but creates 'musical noise' - isolated tonal artefacts left "
             "where the subtraction over-shoots."),
        ("key", "Noise estimate"),
        ("", "This build profiles the lowest-energy STFT frames rather than the "
             "first 250 ms, so it still works when the recording starts "
             "mid-speech."),
        ("dim", "Best on: stationary broadband noise with pauses. "
                "Weak on: continuous tones with no silence to learn from."),
    ],
    "Wiener filter": [
        ("h", "Wiener filter (frequency domain)"),
        ("", "The minimum mean-square-error linear estimator. Each frequency bin "
             "is scaled by how much of its power is signal rather than noise."),
        ("eq", "H(f) = P_s(f) / ( P_s(f) + P_n(f) )"),
        ("eq", "P_s = max( |Y|^2 - P_n , 0 )      S = H * Y"),
        ("dim", "H -> 1 where the signal dominates, H -> 0 where noise does."),
        ("key", "Strength"),
        ("", "Scales the noise power estimate P_n. Above 1 it is aggressive "
             "(more suppression, more muffling); below 1 it is conservative."),
        ("dim", "Best on: additive stationary noise, speech enhancement. "
                "Optimal in the MSE sense if the statistics are correct."),
    ],
    "Median (de-click)": [
        ("h", "Median filter"),
        ("", "A non-linear rank filter: each sample is replaced by the median of "
             "a sliding window. Impulses are outliers, so they are rejected "
             "outright instead of being smeared like a linear filter would."),
        ("eq", "y[n] = median( x[n-k], ..., x[n], ..., x[n+k] )"),
        ("key", "Kernel / window"),
        ("", "Window length (odd). Removes impulses shorter than half the "
             "window; too long and real transients and waveform peaks get "
             "flattened too. Single-sample clicks need only 3."),
        ("dim", "Best on: clicks, crackle, salt-and-pepper. "
                "Poor on: broadband hiss."),
    ],
    "Moving average (FIR)": [
        ("h", "Moving average - the simplest FIR low-pass"),
        ("eq", "y[n] = (1/M) * sum_{k=0}^{M-1} x[n-k]"),
        ("", "Linear phase, trivial to compute, but a poor frequency response: "
             "the stop-band is a sinc with only -13 dB first side-lobe."),
        ("key", "Kernel / window"),
        ("", "M taps. Cut-off falls roughly as fs/M; more taps means smoother "
             "output and more high-frequency detail lost."),
    ],
    "None": [
        ("h", "Noise reduction bypassed"),
        ("", "The degraded signal passes straight to the filter stage. Use this "
             "to show the filter's contribution on its own."),
    ],
}

FILTERS = {
    "Butterworth (IIR)": [
        ("h", "Butterworth IIR"),
        ("", "Maximally flat magnitude in the pass-band - no ripple anywhere, at "
             "the cost of the slowest transition of the IIR families."),
        ("eq", "|H(w)|^2 = 1 / (1 + (w/wc)^(2N))"),
        ("dim", "Roll-off is 20*N dB/decade. Use when pass-band flatness matters."),
    ],
    "Chebyshev I (IIR)": [
        ("h", "Chebyshev type I"),
        ("", "Allows equal ripple in the pass-band to buy a much steeper "
             "transition than Butterworth at the same order."),
        ("eq", "|H(w)|^2 = 1 / (1 + e^2 * T_N^2(w/wc))"),
        ("dim", "T_N is the Nth Chebyshev polynomial; e sets the ripple."),
    ],
    "Elliptic (IIR)": [
        ("h", "Elliptic (Cauer)"),
        ("", "Ripple in both bands, and in exchange the steepest possible "
             "transition for a given order. Phase response is the worst of the "
             "families - use zero-phase filtering if that matters."),
    ],
    "FIR (Hamming window)": [
        ("h", "Windowed-sinc FIR"),
        ("", "The ideal brick-wall filter is an infinite sinc; truncating it with "
             "a Hamming window gives a realisable linear-phase FIR."),
        ("eq", "h[n] = h_ideal[n] * w[n],   w = Hamming"),
        ("dim", "Always stable and exactly linear phase, but needs many more "
                "taps than an IIR for the same selectivity."),
    ],
}

RESPONSES = {
    "Low-pass": "Keeps frequencies below the cut-off. Use to remove hiss and "
                "anti-alias before down-sampling.",
    "High-pass": "Keeps frequencies above the cut-off. Use to remove DC offset, "
                 "rumble and handling noise.",
    "Band-pass": "Keeps a band between f1 and f2. Use to isolate a voice band "
                 "(300-3400 Hz) or one instrument.",
    "Band-stop (notch)": "Removes a band between f1 and f2. The standard fix "
                         "for 50/60 Hz mains hum and its harmonics.",
}

IMAGE_DENOISE = {
    "Gaussian blur": [
        ("h", "Gaussian low-pass"),
        ("eq", "G(x,y) = (1/(2*pi*s^2)) * e^(-(x^2+y^2)/(2*s^2))"),
        ("", "Separable, isotropic smoothing. Suppresses Gaussian noise well but "
             "blurs edges just as much as noise."),
    ],
    "Median": [
        ("h", "2-D median filter"),
        ("", "Rank filter over a kxk neighbourhood. The standard answer to "
             "salt-and-pepper noise - it removes outliers without the halo a "
             "linear filter leaves."),
    ],
    "Bilateral (edge-preserving)": [
        ("h", "Bilateral filter"),
        ("", "Weights neighbours by distance AND by intensity difference, so it "
             "averages within a region but not across an edge."),
        ("eq", "w = exp(-d^2/(2*ss^2)) * exp(-(I_n - I_c)^2/(2*sr^2))"),
        ("dim", "ss = spatial sigma, sr = range sigma."),
    ],
    "Non-local means (fast)": [
        ("h", "Non-local means"),
        ("", "Averages pixels whose surrounding patches look alike, wherever "
             "they are in the image. Exploits self-similarity, so repeated "
             "texture survives denoising."),
        ("eq", "w(p,q) = exp( -||P(p) - P(q)||^2 / h^2 )"),
    ],
    "Wiener (local)": [
        ("h", "Local (Lee) Wiener filter"),
        ("eq", "y = mu + (max(var - noise,0)/var) * (x - mu)"),
        ("", "Adapts per-neighbourhood: smooths flat areas strongly, detailed "
             "areas lightly."),
    ],
    "FFT low-pass": [
        ("h", "2-D Butterworth low-pass"),
        ("eq", "H(u,v) = 1 / (1 + (D(u,v)/D0)^(2n))"),
        ("", "Filtering done in the 2-D frequency domain: FFT, multiply by H, "
             "inverse FFT. The FFT view shows exactly what is being kept."),
    ],
    "Notch (periodic noise)": [
        ("h", "Notch filter"),
        ("", "Periodic noise appears as isolated bright peaks in the 2-D "
             "spectrum. Zeroing small discs around those peaks removes the "
             "pattern and leaves the image content intact."),
        ("", "A peak is only removed when it is far brighter (10x) than the "
             "spectrum around it, so smooth picture detail is kept."),
        ("dim", "The classic fix for moire, scan lines and half-tone patterns. "
                "Limitation: on a picture that is itself a regular pattern "
                "(stripes, checkerboard) the filter cannot tell the pattern "
                "from the interference."),
    ],
    "None": [("h", "Denoising bypassed"), ("", "Shows the degradation untouched.")],
}

RESTORATION = {
    "Wiener deconvolution": [
        ("h", "Wiener deconvolution"),
        ("", "Inverts a known blur while keeping noise amplification bounded."),
        ("eq", "F = ( conj(H) / (|H|^2 + K) ) * G"),
        ("dim", "G = blurred spectrum, H = blur kernel spectrum, K ~ noise/signal."),
        ("key", "Wiener K"),
        ("", "Small K inverts aggressively and amplifies noise; large K is "
             "conservative and leaves residual blur."),
        ("dim", "The image is tiled with its mirror images before the FFT so "
                "its edges do not wrap around and ring. Smoothing the noise "
                "first (e.g. bilateral) stops deblurring from amplifying it."),
    ],
    "Inverse filter": [
        ("h", "Inverse filter"),
        ("eq", "F = G / H"),
        ("", "The naive inverse. Where H is near zero the division explodes, so "
             "noise dominates - the reason Wiener's K term exists. Shown here "
             "deliberately as the failure case."),
    ],
    "Richardson-Lucy": [
        ("h", "Richardson-Lucy deconvolution"),
        ("", "Iterative maximum-likelihood restoration assuming Poisson noise. "
             "Non-negative by construction, which keeps it physically plausible."),
        ("eq", "f_{k+1} = f_k * ( (g / (f_k * h)) * h_flip )"),
        ("dim", "More iterations sharpen further but eventually amplify noise."),
    ],
    "None": [("h", "No deconvolution"), ("", "Set a motion blur length first - "
                                             "deconvolution needs a known kernel.")],
}

ENHANCE = {
    "None": [("h", "Enhancement bypassed"),
             ("", "Shows the denoised/restored result without cosmetic changes.")],
    "Contrast stretch": [
        ("h", "Percentile contrast stretch"),
        ("eq", "y = (x - p2) / (p98 - p2)"),
        ("", "Linear remap between the 2nd and 98th percentile, so a few outlier "
             "pixels cannot waste the whole dynamic range."),
    ],
    "Sharpen (unsharp mask)": [
        ("h", "Unsharp mask"),
        ("eq", "y = x + a * ( x - blur(x) )"),
        ("", "Adds back the high-frequency detail that a blur removes. The "
             "oldest sharpening trick, from darkroom photography."),
    ],
    "Histogram equalization": [
        ("h", "Histogram equalisation"),
        ("eq", "y = CDF(x)"),
        ("", "Remaps intensities through their cumulative distribution so the "
             "histogram spreads out and contrast increases. Applied to luminance "
             "only here, so colours stay natural."),
    ],
    "CLAHE-style (local)": [
        ("h", "Contrast-limited adaptive equalisation"),
        ("", "Equalises each tile separately with a clip limit, so local detail "
             "comes up without the noise blow-up of global equalisation."),
    ],
    "Gamma correction": [
        ("h", "Gamma correction"),
        ("eq", "y = x^(1/gamma)"),
        ("", "Non-linear intensity mapping. gamma > 1 brightens shadows, "
             "gamma < 1 deepens them."),
    ],
    "Edge: Sobel": [
        ("h", "Sobel operator"),
        ("eq", "Gx = [[-1,0,1],[-2,0,2],[-1,0,1]],  G = sqrt(Gx^2 + Gy^2)"),
        ("", "A first-derivative edge detector with built-in smoothing - the "
             "classic discrete gradient estimate."),
    ],
    "Edge: Canny-style": [
        ("h", "Canny-style detector"),
        ("", "Gaussian smoothing, then gradient magnitude, then thresholding. "
             "The full Canny adds non-maximum suppression and hysteresis."),
    ],
}

NOISE_MODELS = {
    "Gaussian (AWGN)": "Additive white Gaussian noise - thermal/electronic noise. "
                       "Flat spectrum, the standard test case.",
    "Pink (1/f)": "Power falls as 1/f - the spectrum of many natural and "
                  "biological processes, and of analogue circuit flicker noise.",
    "Hum 60 Hz + harmonics": "Mains interference at 60 Hz plus 180/300 Hz. "
                             "Narrowband, so a band-stop notch removes it cleanly.",
    "Impulse (clicks)": "Sparse full-scale spikes - vinyl clicks, dropped "
                        "packets. Median filtering is the right tool.",
    "Gaussian": "Additive Gaussian noise on every pixel - sensor noise.",
    "Salt & pepper": "Random pixels forced to pure black or white - dead "
                     "pixels, transmission errors.",
    "Speckle": "Multiplicative noise, n*I - ultrasound, radar, SAR imagery.",
    "Poisson": "Photon shot noise; variance follows the signal level, which is "
               "why it dominates in low light.",
    "Periodic (moire)": "A 2-D sinusoid across the image - scanner patterns and "
                        "interference. Shows as bright peaks in the FFT.",
}

GENERATORS = {
    "Sine": "A single frequency - one spectral line. The reference case.",
    "Square": "Odd harmonics falling as 1/n; good for showing filter roll-off.",
    "Chirp (sweep)": "Frequency rises with time; the clearest spectrogram demo.",
    "Multi-tone": "Three tones at once - use it to show a band-pass selecting one.",
}

SPEECH = {
    "Pitch (autocorrelation)": [
        ("h", "F0 by autocorrelation"),
        ("", "Voiced speech is quasi-periodic, so its autocorrelation peaks at "
             "the pitch period. The peak lag gives the fundamental frequency."),
        ("eq", "r[k] = sum_n x[n] * x[n+k],   F0 = fs / argmax_k r[k]"),
        ("dim", "Frames whose normalised peak stays below 0.3 are called "
                "unvoiced and left blank on the track."),
    ],
    "Pitch (cepstrum)": [
        ("h", "F0 by cepstrum"),
        ("", "The log spectrum of voiced speech is a slow envelope plus a "
             "periodic ripple at the harmonic spacing. A second transform turns "
             "that ripple into a single peak at the pitch quefrency."),
        ("eq", "c[q] = IDFT( log|DFT(x)| )"),
        ("dim", "Quefrency has units of time; F0 = fs / peak quefrency."),
    ],
    "Formants (LPC)": [
        ("h", "Formants by linear prediction"),
        ("", "Models the vocal tract as an all-pole filter. The pole angles are "
             "the resonances - the formants that distinguish vowels."),
        ("eq", "x[n] ~ -sum_{k=1}^{p} a_k * x[n-k]"),
        ("eq", "H(z) = 1 / A(z),   F_i = angle(pole_i) * fs / (2*pi)"),
        ("dim", "Coefficients come from Levinson-Durbin recursion on the "
                "autocorrelation."),
    ],
    "MFCC": [
        ("h", "Mel-frequency cepstral coefficients"),
        ("", "The standard speech feature. Mimics hearing: mel-spaced bands, log "
             "compression, then a DCT to decorrelate."),
        ("eq", "mel(f) = 2595 * log10(1 + f/700)"),
        ("eq", "MFCC = DCT( log( mel_filterbank( |FFT(frame)|^2 ) ) )"),
        ("dim", "Coefficient 0 is energy; 1-12 carry the spectral shape. The "
                "delta features add how fast each one changes."),
        ("key", "MFCC distance"),
        ("eq", "d = mean_frames sqrt( sum_k=1..12 (c_k - c'_k)^2 )"),
        ("", "How far a signal is from the clean voice in MFCC space, over the "
             "frames with speech. Lower = closer; 0 = identical. Enhancement "
             "worked when the output's distance is below the noisy input's."),
    ],
    "Voice activity detection": [
        ("h", "Energy + zero-crossing VAD"),
        ("", "Speech frames are louder than the noise floor and, for voiced "
             "sounds, cross zero less often than noise does. Combining both "
             "rejects hiss that a pure energy rule would accept."),
        ("eq", "speech = (E[m] > floor + margin) AND (ZCR[m] < limit)"),
        ("dim", "The decision is then smoothed so single-frame glitches do not "
                "fragment a word."),
    ],
}

def lookup(table, key, fallback_title="No description"):
    """Return explainer blocks for `key`, degrading gracefully."""
    if key in table:
        v = table[key]
        return v if isinstance(v, list) else [("h", key), ("", v)]
    for k, v in table.items():                       # prefix match
        if key.lower().startswith(k.lower()[:10]):
            return v if isinstance(v, list) else [("h", k), ("", v)]
    return [("h", fallback_title), ("dim", str(key))]


def tip(table, key):
    """One-paragraph plain text for a tooltip."""
    blocks = lookup(table, key)
    body = [t for tag, t in blocks if tag in ("", "dim")]
    return (blocks[0][1] + "\n\n" + " ".join(body[:2])) if body else blocks[0][1]
