# Rubric alignment and final demonstration

The instructor-approved scope, as confirmed by the project owner, requires
**audio, speech, image, and video**. All four remain in the program.

The implementation covers the technical categories shown in the supplied
rubric. This is an evidence map, not a predicted grade: system operation must
be demonstrated on the examination machine, and every member must explain
the actual algorithms and results.

| Criterion | Points | Evidence in this application | What to demonstrate |
|---|---:|---|---|
| System Functionality | 25 | Four working processing panels; source loading/generation, processing, playback or frame display, output saving | Load representative files, change settings, compare results, save output; check the microphone and playback on the exam computer |
| DSP Implementation | 20 | NumPy/SciPy-based FFT/STFT, FIR/IIR filtering, Wiener/median denoising, convolution-based blur/restoration, speech analysis and temporal processing in the three DSP engine modules | Explain the processing equations, parameters and library calls actually used; do not claim removed standalone DFT exercises are part of the application |
| Signal Processing Application | 15 | Audio, Speech, Image and Video tabs | Run one meaningful example in each of the four required signal types |
| Filtering and Signal Enhancement | 15 | Audio/speech noise reduction and filtering; image restoration/deconvolution and enhancement; video spatial and temporal denoising | Explain why the selected method suits the noise or blur and show the result |
| Output and Visualization | 10 | Original/degraded/processed waveforms and images, spectra/spectrograms, speech features, video frame comparisons and quality curves | Compare original and processed outputs visually and, for audio/speech, by listening; explain SNR/PSNR/SSIM where used |
| System Design and User Interface | 5 | Consistent dark red theme, four-tab navigation, presets, readable chart headings, scrolling and contextual reference | Navigate the workflow without clipped controls or confusing labels |
| Demonstration and Defense | 10 | Quick Start presets, algorithm reference with formulas/parameter meanings, measurements and optional PDF reports | Every member explains input, algorithm choice, key parameters, output differences and limitations; the program cannot satisfy the oral defense on their behalf |
| **Total** | **100** | | |

## Removed optional extensions

- Benchmark tab, algorithm rankings and robustness sweeps.
- Standalone Theory tab: sampling/aliasing, convolution exercises, pole-zero
  exploration and window-function comparisons.
- Helpers used only by those labs: benchmark engine, direct DFT/convolution
  verification examples, benchmark tables and CSV export.
- Decorative live clock, animated header waveform and splash animation.
- Second trim: duplicate or off-topic options (extra test waveforms, uniform
  and crackle noise, echo, gain, compressor, three extra audio denoisers, two
  extra filter families, box mean, Laplacian sharpen, high-boost, emboss,
  Prewitt and Laplacian edges, the Edges preset) and unused helper code.
  Recoverable from `archive/before-second-trim.zip`.

These are not explicitly required by the supplied rubric. Their relevant DSP
concepts still appear in the processing algorithms and their explanations.
The previous source is recoverable from `archive/optional-labs-before-trim.zip`.

Presets, the reference drawer, numerical measurements and PDF/output saving
remain because they help demonstrate, compare and explain the required work.

## Short demonstration sequence

1. **Audio:** start from the built-in clean demo or `samples/clean_tone.wav`.
   Choose **Hiss Removal**, listen to the noisy and processed signals, and
   compare the waveforms, spectra, spectrograms and SNR. Explain the Wiener
   filter and low-pass cutoff. **Hum Removal** (band-stop notch), **Click
   Repair** (3-sample median) and **Voice Band** (80–3400 Hz band-pass) are
   optional extra examples.
2. **Speech:** use the synthesized utterance or a known clean WAV. Compare
   **Noisy Speech** and **Enhanced**. Explain voice activity detection, pitch,
   formants and MFCCs. The **MFCC distance** rows show how far the noisy input
   and the output are from the clean voice in MFCC space (lower = closer). Press Space to compare the original and processed
   waveform; the heading identifies which signal is visible.
3. **Image:** use an original image or synthetic pattern. Choose **Photo
   Denoise** or **Deblur** and show original, degraded and processed images.
   Explain the noise/blur model, chosen restoration method and PSNR/SSIM.
   **Moiré Removal** works on the default zone plate, gradients, circles and
   photos, but not on pictures that are themselves a regular pattern (Bars,
   Checkerboard, `test_pattern.png`): there the notch filter cannot tell the
   pattern from the interference.
4. **Video:** LOAD VIDEO with `samples/moving_scene.mp4` (or use SYNTH CLIP).
   Show **Spatial Only**, then **Spatial + Temporal**, move the frame slider,
   and compare processed frames and the PSNR curve. Explain why averaging the
   same pixel over 5 frames cancels noise, and why neighbours that differ
   (motion) get less weight. **Deblur Clip** is an optional extra: Wiener
   deconvolution per frame, then temporal averaging.
5. Save an output and optionally a PDF report. Each member should be able to
   explain this same input → processing → comparison sequence.

## Interpreting the measurements honestly

SNR, PSNR and SSIM comparisons use the loaded/generated source as the reference.
For a controlled quality demonstration, begin with a clean source and add
known noise or blur inside the program. An already noisy imported file is not
a verified clean reference, so its reference-based score is not proof of
real-world noise removal. Improvement also depends on the input and settings;
do not promise that every filter or preset improves every signal.

Separate preset runs may generate different noise realizations. Use the
original/degraded/processed comparison within a single run for a controlled
before/after demonstration.

The audio and speech **SNR** readouts match the volume of each signal to the
clean reference (least-squares gain) before measuring, because outputs are
normalised and loudness is not noise. With no processing, SNR in and SNR out
are therefore identical. The readout is about 1 dB above the SNR slider at low
settings, because the best-fit gain also shrinks part of the noise.

### Measured preset results (built-in sources, single runs)

| Preset | Before | After |
|---|---:|---:|
| Audio · Hiss Removal | 6.1 dB | 10.0–10.4 dB |
| Audio · Hum Removal | 7.0 dB | 13.4 dB |
| Audio · Click Repair | 10.4 dB | 25.6 dB |
| Audio · Voice Band | 8.6 dB | 11.9–12.5 dB |
| Speech · Enhanced | 6.2 dB | 8.9–9.0 dB |
| Speech · Enhanced, MFCC distance (lower = closer) | 15.1 | 13.9 |
| Image · Photo Denoise | 21.8 dB | 22.9 dB (SSIM 0.93 → 0.96) |
| Image · Scan Repair | 15.3 dB | 21.7 dB (SSIM 0.72 → 0.94) |
| Image · Deblur | 13.3 dB | 16.0 dB (SSIM 0.62 → 0.81) |
| Image · Moiré Removal | 13.4 dB | 20.0 dB (SSIM 0.55 → 0.84) |
| Video · Spatial Only | 21.0 dB | 26.9 dB |
| Video · Spatial + Temporal | 21.0 dB | 31.8 dB |
| Video · Deblur Clip | 18.8 dB | 22.6 dB |

One preset lowers the score on purpose, and that is the point to explain:
**Speech · Telephone** (12.3 → 0.9 dB) removes everything outside 300–3400 Hz
to show what a phone line does, so it no longer matches the full-band
original. Noise reducers that learn
the noise from pauses (Wiener, spectral subtraction) help speech, which has
pauses, but can hurt a steady tone, which has none.

## Verification

- `python tools/verify_core.py`: exercises all four processing paths, speech
  A/B comparison, restoration, video frame output and PDF reports using built-in
  test signals. Does not access the microphone or play audio.
- `python tools/verify_ui.py`: checks graph text bounds and measurement layout
  across the four panels at several window sizes.

The hardware-dependent recording/playback paths and arbitrary external media
still need a rehearsal using the files and devices intended for the exam.
