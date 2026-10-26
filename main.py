"""DSP Studio - entry point.

Per-monitor DPI awareness must be switched on before Tk is imported, or
Windows hands the process a 96 DPI surface and bitmap-stretches it on a
scaled display, which is what makes Tk apps look soft.
"""
import sys


def _enable_dpi_awareness():
    if not sys.platform.startswith("win"):
        return
    import ctypes
    for call in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
                 lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1),
                 lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try:
            call()
            return
        except Exception:
            continue


_enable_dpi_awareness()

from dspstudio.app import DSPStudio  # noqa: E402  (must follow the DPI call)

if __name__ == "__main__":
    DSPStudio().mainloop()
