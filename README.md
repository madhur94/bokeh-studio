# Bokeh Studio

**Depth-aware computational photography.** Turn an RGB image and its matching depth map into a selectively focused image, with progressive defocus, soft transitions and a clean, dark editing workspace.

**Assignment 10 · October 29, 2026 · Bokeh Effect Tool**

**Live Vercel app:** [bokeh-studio.vercel.app](https://bokeh-studio.vercel.app/)

[![Deploy on Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=madhur94/bokeh-studio&branch=main&mainModule=app.py)

Source: [madhur94/bokeh-studio](https://github.com/madhur94/bokeh-studio). The deployment button opens Streamlit Community Cloud with this repository, `main` branch and `app.py` entrypoint selected.

### Vercel alternative

The [`vercel/`](vercel/README.md) directory contains a separate Vercel-compatible build: a static interface with a stateless Python/OpenCV function. Import this repository with **Root Directory = `vercel`** and Framework Preset **Other**. It uses the same Bokeh algorithm, with 900 px output and browser-optimized uploads to respect Vercel's request size limit. The Streamlit assignment remains available at the repository root.

## Overview and demo features

- Dual JPG/PNG uploads; grayscale, RGB-luminance and 16-bit PNG depth.
- EXIF orientation correction, depth alignment, float normalization and optional bilateral smoothing.
- Bright = Near / Dark = Near conventions; a consistent **0 = near, 1 = far** focus scale.
- Selectable focal plane and full-width sharp band.
- Progressive Gaussian blur pyramid with continuous depth-based interpolation.
- Soft focus masks, normalized convolution to reduce foreground color spill, and linear-light blending.
- Natural, Portrait, Strong and Custom styles; adjustable blur, feathering and 4/6/9 levels.
- Result, live Depth Analysis and side-by-side Comparison tabs.
- Valid RGB PNG download; stale results are hidden until regenerated.
- Original synthetic sample pair, offline processing, CPU only, no keys, no database.
- Streamlit Community Cloud compatible; four runtime dependencies.

## Project structure

```text
bokeh-effect-tool/
├── app.py
├── requirements.txt
├── README.md
├── TEST_REPORT.md
├── .gitignore
├── .streamlit/
│   └── config.toml
├── assets/
│   └── style.css
├── utils/
│   ├── __init__.py
│   └── bokeh.py
├── sample_images/
│   ├── README.md
│   ├── generate_sample.py
│   ├── botanical_rgb.png
│   └── botanical_depth.png
└── tests/
    └── test_bokeh.py
```

## Installation

Use **Python 3.12** (the tested version) on Windows, macOS or Linux. No GUI OpenCV package is needed.

```bash
git clone https://github.com/madhur94/bokeh-studio.git
cd bokeh-studio
python -m venv .venv
```

Activate on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Or Windows Command Prompt:

```bat
.venv\Scripts\activate.bat
```

On Linux/macOS:

```bash
source .venv/bin/activate
```

Install and run from the project directory:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`. Dependencies are pinned to the versions validated for this delivery. Installing packages needs internet; processing images does not.

## Usage

1. Upload the RGB photograph and its spatially registered depth map, or choose **Try the sample scene**.
2. Select the correct depth interpretation. Focus depth always uses 0 for near and 1 for far, regardless of the input convention.
3. Set **Focus depth** to the subject's interpreted depth. Use Depth Analysis to inspect it.
4. Set **Focus range**, the full width of the in-focus band (a range of 0.18 retains depths ±0.09 around focus).
5. Pick a style or adjust blur strength, feathering and quality. Manual style adjustments select Custom; presets do not change your focal plane.
6. Inspect the live focus mask: white is sharp, black is defocused.
7. Select **Generate Bokeh**, then inspect Result and Comparison.
8. Select **Download Bokeh Image**. The PNG uses the displayed processing resolution.

Changing settings invalidates the previous render and download, so the displayed parameters always describe the exported image. Reset clears uploads, results, retained prepared images and controls.

## Processing pipeline

```text
RGB image → validate/orient → RGB → aspect-preserving resize ─────────────┐
                                                                       │
Depth map → validate/orient → grayscale → float min/max normalization    │
    → align to RGB → optional bilateral filter → interpret near/far      │
    → absolute distance from focus                                     │
    ├→ depth ramp → spatial feathering → soft focus alpha               │
    └→ normalized defocus amount → spatial feathering                   │
                                                                       ↓
Linear RGB → streamed weighted Gaussian blur levels → interpolate levels
                         ↓
            alpha × sharp + (1 − alpha) × defocused
                         ↓
                 sRGB → uint8 RGB → PNG
```

### Exact algorithm

Depth is converted to grayscale luminance when RGB, converted to float32, and normalized using `(d − min) / (max − min)`. A constant map is rejected. Min/max normalization happens before resize so interpolation cannot manufacture missing depth variation. Input depth is bilinearly aligned to the resized RGB image. Optional bilateral filtering uses a 5-pixel neighborhood, range sigma 0.06 and spatial sigma 3. For Bright = Near, interpreted depth is `1 − d`; otherwise it is `d`.

Let `f` be focus depth, `w` the full focus range, and `D = abs(d − f)`.

- Initial sharp alpha is `1 − smoothstep((D − w/2) / 0.08)`, clamped to 0–1.
- Defocus amount is `clip((D − w/2) / max(max(f, 1−f) − w/2, 0.01), 0, 1)`.
- Gaussian feathering (the chosen sigma in output pixels) is applied separately to alpha and defocus amount. Deep inside the sharp band, alpha remains 1.
- RGB is converted from sRGB to linear light. A pyramid of `N` levels has sigma `strength × i / (N−1)`; level 0 is the original.
- Each defocused level uses normalized convolution: `Gaussian(RGB × weight) / Gaussian(weight)`, with `weight = max(1−alpha, 0.001)`. This suppresses contamination from the sharp subject in background blur.
- For each pixel, `position = defocus × (N−1)`. Triangular weights `max(1−abs(position−i), 0)` interpolate adjacent levels continuously.
- Final linear color is `alpha × original + (1−alpha) × interpolated`. It is converted back to sRGB and encoded as RGB PNG, without a BGR channel swap.

Levels are yielded and accumulated one at a time, rather than retained as a full-resolution stack. The loop is over a small number of levels; every pixel operation is vectorized.

## Performance and input safety

- 20 MB encoded limit per file and 24 megapixels decoded per image; content is validated as JPEG or PNG, not trusted from its extension.
- Longest processing side is capped at **1600 px** with aspect ratio preserved. Depth is aligned to that output size; the UI explains any reduction.
- 16-bit depth is retained until normalization. Color-profile conversion is not performed; use sRGB photographs.
- Float32 processing, streamed layers and two OpenCV worker threads limit resource use. Fine quality takes more time. Several concurrent large sessions still require adequate hosting memory.
- Uploads and generated results are retained in Streamlit session memory, not written to disk or a shared application cache. A hosted app transmits uploads to its server; it is not browser-local processing. Streamlit may temporarily retain media/download bytes as part of its normal serving lifecycle.
- Corrupt, unsupported, oversized or constant-depth inputs show readable warnings. Technical exceptions are logged on the server.

## Deploy on Streamlit Community Cloud

1. Push the **contents of this project folder** to a GitHub repository. Include the hidden `.streamlit/config.toml` file, assets and utilities.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/) and connect your GitHub account.
3. Choose **Create app**, then the repository and branch.
4. Set the main file path to **`app.py`**. If you instead commit the parent folder, use `bokeh-effect-tool/app.py` and ensure its dependencies/config are discovered; using this project as repository root is recommended.
5. In Advanced settings select **Python 3.12**. No secrets or environment variables are required.
6. Deploy. Community Cloud installs `requirements.txt` and starts the application. Test the sample and one uploaded pair after deployment.

No source changes or additional system packages are needed. `opencv-python-headless` avoids GUI libraries. Python selection is performed in the deployment UI; a legacy `runtime.txt` is unnecessary. See the official [deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

This delivery includes a locally verified, deployable repository; publishing to your GitHub/Cloud account is a separate account action.

### Optional: Render

Create a Python Web Service from the same repository with build command `pip install -r requirements.txt` and start command `streamlit run app.py --server.address 0.0.0.0 --server.port $PORT`. Select Python 3.12 in the host's environment configuration. Use the project root as the service root. No extra application framework is needed.

## Verification

```bash
python -m unittest discover -s tests -v
pip check
streamlit run app.py --server.headless true
```

Tests use Python's standard library unittest and Streamlit's bundled AppTest; no extra test dependency is required. They check focus preservation, defocus, depth resizing, depth conventions, changing focus, blur strength, feathering, large-image resizing, PNG integrity/color, invalid/constant/unsupported inputs, 16-bit depth and zero-blur identity. AppTest checks empty and missing input states, demo generation, stale render suppression, presets, manual controls, direction changes and reset. See `TEST_REPORT.md` for actual execution results and verification limits.

## Viva notes

| Concept | Concise answer |
|---|---|
| What is Bokeh? | The appearance of out-of-focus areas. Shallow depth of field keeps a narrow depth band sharp and softens other depths. |
| What is a depth map? | An image whose scalar pixel values represent relative scene depth, aligned with the photograph. |
| How is foreground identified? | We use depth distance from a selected focal plane. Any selected depth band can be sharp, including a distant subject. |
| Why normalize? | It gives every valid depth input a common 0–1 scale independent of its numeric intensity range. |
| Why two conventions? | Some depth exports use bright for near; others use dark. Inversion gives a consistent near-to-far scale. |
| How is blur produced? | Gaussian defocus increases progressively with distance outside the sharp focus band. |
| What is a blur pyramid? | Several blur strengths of the same image. Neighboring levels are continuously interpolated per pixel using depth. |
| Why a soft mask? | Depth ramps and spatial feathering reduce abrupt transitions; weighted blur reduces sharp subject color spilling into the background. |
| How is final color calculated? | In linear light, `alpha × sharp + (1−alpha) × depth-blurred`, then convert to sRGB. |
| Why better than binary blur? | Each depth can receive a different degree of defocus instead of only sharp or uniformly blurred. |

## Limitations

This is a single-image, relative-depth Gaussian approximation, not a physical lens renderer. It does not synthesize hidden background, produce aperture-shaped light discs, or model occlusion perfectly. Poor registration, hair, transparent objects and noisy depth can still produce halos. RGB depth is interpreted as luminance, not decoded from an unknown false-color legend. Depth min/max scaling is sensitive to outliers, and relative depth is not calibrated metric distance. Blur affects both near and far out-of-focus regions. Output is capped at 1600 px and does not retain EXIF or ICC metadata. The included scene is synthetic; real-photo quality depends on the supplied depth map.
