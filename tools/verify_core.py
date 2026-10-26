"""Smoke checks for the four required DSP workflows, without media devices."""
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import DSPStudio
from dspstudio import dsp_audio as D, dsp_image as I, presets as P
from dspstudio.plots import PlotPane


def wait_for_jobs(app, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.update()
        queues = [p.jobs for p in app.panels.values() if hasattr(p, "jobs")]
        if all(not q.busy() and q.outbox.empty() for q in queues):
            return
        time.sleep(0.02)
    raise AssertionError("Background processing did not finish")


def run():
    errors, results = [], {}
    original_status = DSPStudio.status

    def status(app, message, color=None):
        if "error:" in message.lower() or "failed:" in message.lower():
            errors.append(message)
        original_status(app, message, color)

    with patch.object(DSPStudio, "status", status):
        app = DSPStudio(show_window=False, show_splash=False)
        app.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
        try:
            assert list(app.panels) == ["audio", "speech", "image", "video"]
            assert [item[0] for item in app.rail.items] == list(app.panels)
            assert not any(name in sys.modules for name in (
                "dspstudio.benchmark", "dspstudio.panels.bench_panel",
                "dspstudio.panels.theory_panel"))
            assert not app.bind("<Key-5>") and not app.bind("<Key-6>")
            wait_for_jobs(app)

            audio = app.panels["audio"]
            assert not P.apply(audio, P.AUDIO[0][2])
            assert audio.processed.shape == audio.clean.shape
            assert np.isfinite(audio.processed).all()
            assert not np.allclose(audio.processed, audio.noisy)
            results["audio"] = "Noise reduction and filtering produce a valid changed output"

            speech = app.panels["speech"]
            assert not P.apply(speech, P.SPEECH[2][2])
            assert np.isfinite(speech.processed).all()
            processed_trace = speech.p_wave.ax().lines[0].get_ydata().copy()
            speech.toggle_ab()
            original_trace = speech.p_wave.ax().lines[0].get_ydata().copy()
            assert not np.allclose(processed_trace, original_trace)
            assert "ORIGINAL" in speech.p_wave.ax().get_title(loc="left")
            speech.toggle_ab()
            np.testing.assert_allclose(speech.p_wave.ax().lines[0].get_ydata(), processed_trace)
            assert len(speech.p_wave.fig.axes) == 3
            results["speech"] = "Enhancement, analysis and original/processed A/B comparison work"

            image = app.panels["image"]
            assert not P.apply(image, P.IMAGE[2][2])
            video = app.panels["video"]
            assert not P.apply(video, P.VIDEO[2][2])
            wait_for_jobs(app)
            assert image.kernel is not None
            assert image.processed.shape == image.original.shape
            assert np.isfinite(image.processed).all()
            assert not np.allclose(image.processed, image.degraded)
            results["image"] = "Blur restoration produces a valid changed image"
            assert len(video.processed) == len(video.frames) == len(video._psnr_out)
            assert all(np.isfinite(frame).all() for frame in video.processed)
            assert not np.allclose(video.processed[0], video.degraded[0])
            results["video"] = f"Spatial/temporal processing completed all {len(video.frames)} frames"

            check_dir = Path(__file__).resolve().parent / "ui-checks"
            check_dir.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".core-", dir=check_dir) as folder:
                folder = Path(folder).resolve()
                assert folder.is_relative_to(check_dir.resolve()) and folder != check_dir.resolve()
                for name, panel in (("audio", audio), ("speech", speech)):
                    path = folder / f"{name}.wav"
                    D.save_wav(path, panel.processed, panel.sr)
                    samples, sr = D.load_wav(path)
                    assert sr == panel.sr and len(samples) == len(panel.processed)
                path = folder / "image.png"
                I.save_image(path, image.processed)
                assert I.load_image(path).shape == image.processed.shape
                path = folder / "video-frame.png"
                I.save_image(path, video.processed[0])
                assert I.load_image(path).shape == video.processed[0].shape
                for name, panel in app.panels.items():
                    # The hidden test window has no on-screen chart allocation.
                    # Use readable figure dimensions when exercising PDF export.
                    for pane in vars(panel).values():
                        if isinstance(pane, PlotPane):
                            pane.fig.set_size_inches(7.5, 3.6, forward=False)
                    path = folder / f"{name}.pdf"
                    with patch("tkinter.filedialog.asksaveasfilename", return_value=str(path)):
                        panel.export_report()
                    assert path.read_bytes().startswith(b"%PDF-")
                    assert path.stat().st_size > 1000
                results["exports"] = "Audio/speech WAVs, image/video-frame PNGs and four PDF reports saved"
            assert not errors, errors
            output = Path(__file__).resolve().parent / "ui-checks" / "core-verification.json"
            output.parent.mkdir(exist_ok=True)
            output.write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(results, indent=2), flush=True)
        finally:
            app.quit_app()


if __name__ == "__main__":
    run()
