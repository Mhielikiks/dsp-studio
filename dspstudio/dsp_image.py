"""2-D DSP engine: image noise models, restoration, filtering and analysis.

Images are carried as float64 arrays in [0, 1], either HxW (grey) or HxWx3.
"""
import numpy as np
from scipy import ndimage, signal as sg

EPS = 1e-12


# ----------------------------------------------------------------- I/O -----
def load_image(path, max_side=720):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if max(im.size) > max_side:
        s = max_side / float(max(im.size))
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                       Image.LANCZOS)
    return np.asarray(im, dtype=np.float64) / 255.0


def save_image(path, img):
    from PIL import Image
    Image.fromarray(to_u8(img)).save(path)


def to_u8(img):
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def to_gray(img):
    if img.ndim == 2:
        return img
    return img @ np.array([0.299, 0.587, 0.114])


def _per_channel(img, fn):
    if img.ndim == 2:
        return fn(img)
    return np.dstack([fn(img[..., c]) for c in range(img.shape[2])])


def synthetic(kind="checkerboard", size=360):
    """Built-in test images so the lab works without any file."""
    y, x = np.mgrid[0:size, 0:size] / float(size)
    k = kind.lower()
    if k.startswith("checker"):
        g = (((x * 8).astype(int) + (y * 8).astype(int)) % 2).astype(float)
    elif k.startswith("gradient"):
        g = (x + y) / 2.0
    elif k.startswith("circles"):
        r = np.sqrt((x - .5) ** 2 + (y - .5) ** 2)
        g = 0.5 + 0.5 * np.cos(40 * r)
    elif k.startswith("zone"):                      # zone plate: 2-D chirp
        g = 0.5 + 0.5 * np.cos(220 * ((x - .5) ** 2 + (y - .5) ** 2))
    elif k.startswith("bars"):
        g = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 10 * x))
    else:
        g = np.clip(np.sin(10 * x) * np.cos(10 * y), 0, 1)
    return np.dstack([g, g, g])


# ------------------------------------------------------------ corruption ---
IMG_NOISES = ["Gaussian", "Salt & pepper", "Speckle", "Poisson",
              "Periodic (moire)"]


def add_noise(img, kind="Gaussian", amount=0.08):
    k = kind.lower()
    out = img.copy()
    if k.startswith("gauss"):
        out = img + np.random.normal(0, amount, img.shape)
    elif k.startswith("salt"):
        m = np.random.rand(*img.shape[:2])
        sel = m < amount / 2
        out[sel] = 0.0
        sel = m > 1 - amount / 2
        out[sel] = 1.0
    elif k.startswith("speckle"):
        out = img + img * np.random.normal(0, amount, img.shape)
    elif k.startswith("poisson"):
        lam = max(1.0, (1.0 - amount) * 80)
        out = np.random.poisson(np.clip(img, 0, 1) * lam) / lam
    elif k.startswith("periodic"):
        h, w = img.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        pat = amount * 3 * np.sin(2 * np.pi * (xx * 0.18 + yy * 0.11))
        out = img + (pat[..., None] if img.ndim == 3 else pat)
    return np.clip(out, 0, 1)


def motion_blur(img, length=15, angle=0.0):
    k = np.zeros((length, length))
    k[length // 2, :] = 1.0
    k = ndimage.rotate(k, angle, reshape=False, order=1)
    k /= k.sum() + EPS
    return np.clip(_per_channel(img, lambda c: sg.convolve2d(c, k, mode="same",
                                                             boundary="symm")), 0, 1), k


# ------------------------------------------------- denoise / restoration ---
IMG_DENOISE = ["Gaussian blur", "Median", "Bilateral (edge-preserving)",
               "Non-local means (fast)", "Wiener (local)", "FFT low-pass",
               "Notch (periodic noise)", "None"]


def bilateral(img, d=5, sigma_s=2.0, sigma_r=0.12):
    """Edge-preserving smoothing, separable-free brute force on a small window."""
    def f(c):
        pad = d
        p = np.pad(c, pad, mode="reflect")
        acc = np.zeros_like(c)
        wsum = np.zeros_like(c)
        for dy in range(-d, d + 1):
            for dx in range(-d, d + 1):
                shifted = p[pad + dy:pad + dy + c.shape[0],
                            pad + dx:pad + dx + c.shape[1]]
                gs = np.exp(-(dx * dx + dy * dy) / (2 * sigma_s ** 2))
                gr = np.exp(-((shifted - c) ** 2) / (2 * sigma_r ** 2))
                w = gs * gr
                acc += w * shifted
                wsum += w
        return acc / (wsum + EPS)
    return np.clip(_per_channel(img, f), 0, 1)


def nlm_fast(img, h=0.12, patch=3, search=5):
    """Non-local means on a decimated search window (keeps it interactive)."""
    def f(c):
        k = np.ones((patch, patch)) / (patch * patch)
        acc = np.zeros_like(c)
        wsum = np.zeros_like(c)
        for dy in range(-search, search + 1, 2):
            for dx in range(-search, search + 1, 2):
                shifted = np.roll(np.roll(c, dy, axis=0), dx, axis=1)
                d2 = sg.convolve2d((c - shifted) ** 2, k, mode="same", boundary="symm")
                w = np.exp(-d2 / (h ** 2 + EPS))
                acc += w * shifted
                wsum += w
        return acc / (wsum + EPS)
    return np.clip(_per_channel(img, f), 0, 1)


def wiener_local(img, size=5, noise=None):
    """Local (Lee) Wiener filter; flat regions divide by zero, so clean up NaNs."""
    def f(c):
        with np.errstate(divide="ignore", invalid="ignore"):
            out = sg.wiener(c, mysize=size, noise=noise)
        return np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(_per_channel(img, f), 0, 1)


def fft_lowpass(img, cutoff=0.25, order=2):
    """Butterworth low-pass applied in the 2-D frequency domain."""
    def f(c):
        h, w = c.shape
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt(((yy - h / 2) / (h / 2)) ** 2 + ((xx - w / 2) / (w / 2)) ** 2)
        H = 1.0 / (1.0 + (d / max(cutoff, 1e-3)) ** (2 * order))
        F = np.fft.fftshift(np.fft.fft2(c))
        return np.real(np.fft.ifft2(np.fft.ifftshift(F * H)))
    return np.clip(_per_channel(img, f), 0, 1)


def notch_filter(img, strength=0.9, radius=4, keep=0.08, ratio=10.0, win=31):
    """Kill isolated spectral peaks - removes periodic / moire noise.

    A frequency is only notched when it is both among the strongest in the
    spectrum and `ratio` times brighter than its local neighbourhood. Periodic
    interference makes sharp spikes; a picture's own detail (a zone plate, a
    texture) spreads energy smoothly, so it is left alone.
    """
    def f(c):
        F = np.fft.fftshift(np.fft.fft2(c))
        mag = np.abs(F)
        h, w = c.shape
        cy, cx = h // 2, w // 2
        m = mag.copy()
        yy, xx = np.mgrid[0:h, 0:w]
        dc = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        m[dc < max(keep * min(h, w), 3)] = 0          # protect low frequencies
        thresh = np.percentile(m, 99.9)
        local = ndimage.uniform_filter(mag, size=win) + EPS
        mask = np.ones_like(mag)
        peaks = np.argwhere((m > thresh) & (mag / local > ratio))
        for py, px in peaks:
            d = np.sqrt((yy - py) ** 2 + (xx - px) ** 2)
            mask *= np.where(d < radius, 1.0 - strength, 1.0)
        return np.real(np.fft.ifft2(np.fft.ifftshift(F * mask)))
    return np.clip(_per_channel(img, f), 0, 1)


def denoise(img, method, amount=1.0, ksize=3):
    m = method.lower()
    if m.startswith("gaussian"):
        return np.clip(_per_channel(img, lambda c: ndimage.gaussian_filter(c, amount * 2)), 0, 1)
    if m.startswith("median"):
        k = max(3, int(ksize) | 1)
        return np.clip(_per_channel(img, lambda c: ndimage.median_filter(c, size=k)), 0, 1)
    if m.startswith("bilateral"):
        return bilateral(img, d=max(2, int(ksize) // 2), sigma_s=1 + amount * 2,
                         sigma_r=0.05 + amount * 0.15)
    if m.startswith("non-local"):
        return nlm_fast(img, h=0.05 + amount * 0.15)
    if m.startswith("wiener"):
        return wiener_local(img, size=max(3, int(ksize) | 1))
    if m.startswith("fft"):
        return fft_lowpass(img, cutoff=max(0.05, 0.6 - amount * 0.45))
    if m.startswith("notch"):
        return notch_filter(img, strength=min(0.99, amount))
    return img.copy()


def _deconvolve(img, kernel, gain):
    """Apply a frequency-domain inverse `gain(H)` to each channel.

    The FFT treats the picture as if it repeats side by side, so the left
    edge would be deblurred against the right one and ring. Tiling the image
    with its mirror images makes that repetition seamless (each edge meets a
    copy of itself); the original quarter is cropped back out afterwards.
    """
    kh, kw = kernel.shape

    def f(c):
        h, w = c.shape
        cp = np.block([[c, c[:, ::-1]], [c[::-1, :], c[::-1, ::-1]]])
        kp = np.zeros(cp.shape)
        kp[:kh, :kw] = kernel
        kp = np.roll(kp, -(kh // 2), axis=0)
        kp = np.roll(kp, -(kw // 2), axis=1)
        H = np.fft.fft2(kp)
        return np.real(np.fft.ifft2(gain(H) * np.fft.fft2(cp)))[:h, :w]
    return np.clip(_per_channel(img, f), 0, 1)


def wiener_deconvolve(img, kernel, K=0.01):
    """Frequency-domain Wiener deblurring given the degradation kernel."""
    return _deconvolve(img, kernel, lambda H: np.conj(H) / (np.abs(H) ** 2 + K))


def inverse_filter(img, kernel, eps=0.05):
    return _deconvolve(img, kernel,
                       lambda H: 1.0 / np.where(np.abs(H) < eps, eps, H))


def richardson_lucy(img, kernel, iters=15):
    """Iterative RL deconvolution (classic image restoration)."""
    def f(c):
        est = np.full_like(c, 0.5)
        kf = kernel[::-1, ::-1]
        for _ in range(iters):
            conv = sg.convolve2d(est, kernel, mode="same", boundary="symm") + EPS
            est *= sg.convolve2d(c / conv, kf, mode="same", boundary="symm")
        return est
    return np.clip(_per_channel(img, f), 0, 1)



def temporal_average(frames, radius=2, sigma=0.08):
    """Motion-adaptive average of each frame with its neighbours in time.

    Every pixel is averaged with the same pixel in the `radius` frames before
    and after. Noise is independent between frames, so it cancels. Where
    something moved, the neighbour looks different, and its weight
    w = exp(-d^2 / 2 sigma^2) falls towards zero - so moving edges are not
    smeared into ghosts.
    """
    out = []
    for i, cur in enumerate(frames):
        num, den = np.zeros_like(cur), np.zeros(cur.shape[:2] + (1,) * (cur.ndim - 2))
        for j in range(max(0, i - radius), min(len(frames), i + radius + 1)):
            d = (frames[j] - cur) ** 2
            if d.ndim == 3:
                d = d.mean(axis=2, keepdims=True)
            w = np.exp(-d / (2 * sigma * sigma))
            num += w * frames[j]
            den += w
        out.append(np.clip(num / den, 0, 1))
    return out

# ------------------------------------------------------------ enhancement --
IMG_ENHANCE = ["None", "Sharpen (unsharp mask)", "Histogram equalization",
               "CLAHE-style (local)", "Gamma correction", "Contrast stretch",
               "Edge: Sobel", "Edge: Canny-style"]


def unsharp(img, sigma=2.0, amount=1.0):
    blur = _per_channel(img, lambda c: ndimage.gaussian_filter(c, sigma))
    return np.clip(img + amount * (img - blur), 0, 1)


def hist_equalize(img):
    def f(c):
        hist, bins = np.histogram(c.flatten(), 256, (0, 1))
        cdf = hist.cumsum().astype(np.float64)
        cdf /= cdf[-1] + EPS
        return np.interp(c.flatten(), bins[:-1], cdf).reshape(c.shape)
    if img.ndim == 2:
        return f(img)
    # equalize luminance only so colours stay natural
    g = to_gray(img)
    eq = f(g)
    ratio = (eq + EPS) / (g + EPS)
    return np.clip(img * ratio[..., None], 0, 1)


def clahe_like(img, tiles=8, clip=0.02):
    def f(c):
        h, w = c.shape
        out = np.zeros_like(c)
        th, tw = max(1, h // tiles), max(1, w // tiles)
        for i in range(0, h, th):
            for j in range(0, w, tw):
                blk = c[i:i + th, j:j + tw]
                hist, bins = np.histogram(blk.flatten(), 64, (0, 1))
                hist = np.minimum(hist, clip * blk.size + 1)
                cdf = hist.cumsum().astype(np.float64)
                cdf /= cdf[-1] + EPS
                out[i:i + th, j:j + tw] = np.interp(blk.flatten(), bins[:-1],
                                                    cdf).reshape(blk.shape)
        return ndimage.uniform_filter(out, size=3)
    return np.clip(_per_channel(img, f), 0, 1)


def gamma(img, g=1.0):
    return np.clip(img ** (1.0 / max(g, 1e-3)), 0, 1)


def contrast_stretch(img, lo_p=2, hi_p=98):
    lo, hi = np.percentile(img, [lo_p, hi_p])
    return np.clip((img - lo) / (hi - lo + EPS), 0, 1)


def edges(img, kind="sobel", thresh=0.25):
    g = to_gray(img)
    k = kind.lower()
    if "sobel" in k:
        gx = ndimage.sobel(g, 0)
        gy = ndimage.sobel(g, 1)
        e = np.hypot(gx, gy)
    else:                                            # Canny-style
        sm = ndimage.gaussian_filter(g, 1.4)
        gx, gy = ndimage.sobel(sm, 0), ndimage.sobel(sm, 1)
        mag = np.hypot(gx, gy)
        mag /= mag.max() + EPS
        e = (mag > thresh).astype(float)
    e = e / (e.max() + EPS)
    return np.dstack([e, e, e])


def enhance(img, method, amount=1.0, gamma_v=1.0, thresh=0.25):
    m = method.lower()
    if m.startswith("sharpen"):
        return unsharp(img, sigma=1.5, amount=amount * 1.5)
    if m.startswith("histogram"):
        return hist_equalize(img)
    if m.startswith("clahe"):
        return clahe_like(img)
    if m.startswith("gamma"):
        return gamma(img, gamma_v)
    if m.startswith("contrast"):
        return contrast_stretch(img)
    if m.startswith("edge"):
        return edges(img, m.split(":")[-1], thresh)
    return img.copy()


# -------------------------------------------------------------- analysis ---
def fft_magnitude(img):
    """log-magnitude spectrum, centred, normalised to [0,1] for display."""
    g = to_gray(img)
    F = np.fft.fftshift(np.fft.fft2(g))
    m = np.log1p(np.abs(F))
    return m / (m.max() + EPS)


def histogram(img, bins=128):
    if img.ndim == 2:
        h, e = np.histogram(img, bins, (0, 1))
        return {"Y": (e[:-1], h)}
    out = {}
    for i, name in enumerate(["R", "G", "B"]):
        h, e = np.histogram(img[..., i], bins, (0, 1))
        out[name] = (e[:-1], h)
    return out


def psnr(a, b):
    m = float(np.mean((np.clip(a, 0, 1) - np.clip(b, 0, 1)) ** 2))
    if m < EPS:
        return 99.0
    return float(10 * np.log10(1.0 / m))


def mse(a, b):
    return float(np.mean((a - b) ** 2))


def ssim(a, b):
    """Global SSIM on the luminance channel (gaussian weighted)."""
    x, y = to_gray(a), to_gray(b)
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    mx = ndimage.gaussian_filter(x, 1.5)
    my = ndimage.gaussian_filter(y, 1.5)
    sxx = ndimage.gaussian_filter(x * x, 1.5) - mx * mx
    syy = ndimage.gaussian_filter(y * y, 1.5) - my * my
    sxy = ndimage.gaussian_filter(x * y, 1.5) - mx * my
    s = ((2 * mx * my + C1) * (2 * sxy + C2)) / \
        ((mx ** 2 + my ** 2 + C1) * (sxx + syy + C2) + EPS)
    return float(np.mean(s))


def sharpness(img):
    """Variance of the Laplacian - higher is crisper."""
    return float(np.var(ndimage.laplace(to_gray(img))))


def entropy(img):
    h, _ = np.histogram(to_gray(img), 256, (0, 1))
    p = h / (h.sum() + EPS)
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))
