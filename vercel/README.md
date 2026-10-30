# Bokeh Studio on Vercel

**Production:** [https://bokeh-studio.vercel.app/](https://bokeh-studio.vercel.app/)

This alternative deployment keeps the assignment's Python/OpenCV blur engine and replaces Streamlit's persistent UI with a static HTML/CSS/JavaScript interface and a stateless Python function. The original Streamlit app remains in the repository root.

## Deploy

Import `madhur94/bokeh-studio` in Vercel. Set **Root Directory** to **`vercel`**, Framework Preset to **Other**, and leave build and install commands unset. Python is pinned to 3.12. Vercel installs the three Python dependencies in this directory and serves `/api/process` as a function. No keys, database or storage service is required.

## Local verification

```bash
pip install -r requirements.txt
python dev_server.py
```

Open `http://127.0.0.1:8503`. For Vercel-specific emulation, use `vercel dev` when the CLI is available.

## Behavior and limits

- Same depth normalization, direction handling, focus controls, progressive Gaussian pyramid, weighted convolution and linear-light blending as the Streamlit build.
- Maximum processing side is **900 px**. RGB is resized and encoded as high-quality JPEG in the browser; output is PNG.
- Depth files up to 1.2 MB are sent unchanged, preserving 16-bit depth. Larger 8-bit inputs are resized in the browser. Larger 16-bit PNGs are rejected with a resizing instruction to avoid silently reducing depth precision.
- Prepared JSON request and response are capped at 4.2 MB, below Vercel's 4.5 MB function payload ceiling. Raw inputs still have a 20 MB per-file and 24-megapixel limit.
- Analysis views update after Generate, and are invalidated when controls change. No uploaded images are persisted. The browser retains previews until reset or the page closes.
- The static UI does not wait for Python to start. The first image generation can still incur a Python/OpenCV cold start. Moving hosts is not a guarantee of faster image processing.
- `engine/bokeh.py` is a byte-for-byte deployment copy of `../utils/bokeh.py`; sync it whenever the shared algorithm changes. Sample PNGs are copied to keep this deployment root self-contained.

## Verification

On October 30, 2026, six tests passed under Python 3.12 using the pinned NumPy/OpenCV/Pillow packages: sample rendering and PNG encoding; invalid settings/base64; constant and 16-bit depth; original-engine equality; POST handler success/error; and request size/MIME limits. Run `python -m unittest discover -s tests -v` from this directory.

`node --check public/app.js` passed. A separate DOM test exercised sample preparation, request submission, result/download state, control-change invalidation and reset. This is not a browser layout test. The local server started successfully, but socket-based HTTP testing was restricted by the workspace; the POST protocol was tested directly with in-memory request/response streams. Production verification is recorded separately after an actual Vercel deployment.

### Production verification — October 30, 2026

Vercel deployment `dpl_Bd2S5NBm4SazdfYGbkMXgQe81wrr` reached READY. The static interface and `/api/process` health check returned HTTP 200. A real POST of the bundled sample pair to the public production endpoint returned a valid **900×585 RGB PNG**, verified with Pillow. Engine time was **0.94 s** and total request time approximately **3.49 s** in that test; timings vary and cold starts can take longer.

Deployment was made directly through the Vercel integration using the tested source files because the account's GitHub-to-Vercel integration was not installed. The complete source is published in GitHub, but automatic deployments on Git pushes are not connected yet. To enable them later, install Vercel's GitHub integration and link this repository with root directory `vercel`.
