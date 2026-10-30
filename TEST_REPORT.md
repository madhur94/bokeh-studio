# Verification report

Executed October 29, 2026 on Windows, Python 3.12.10. This report records local verification; no public cloud deployment has been performed.

## Clean dependency environment — PASS

A fresh virtual environment was created outside the deliverable. Its runtime dependencies are exactly:

| Package | Version |
|---|---|
| Streamlit | 1.56.0 |
| NumPy | 2.2.6 |
| opencv-python-headless | 4.12.0.88 |
| Pillow | 11.3.0 |

The first ordinary pip install encountered slow downloads and an OpenCV download timeout. Recovery fetched compatible wheels directly from official PyPI, verified every wheel against the SHA-256 digest in PyPI metadata, and installed the declared requirements into the empty environment using a local wheel directory. The wheel directory and recovery helper are development-only and are not needed by the application.

After installation, `python -m pip install -r requirements.txt` succeeded normally with all requirements satisfied. `python -m pip check` returned **No broken requirements found**. The clean environment successfully launched `python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8502`; its health endpoint returned `ok`.

## Automated tests — 14 / 14 PASS

Command: `python -m unittest discover -s tests -v`

Final clean-environment run: **14 tests in 7.884 seconds — OK**.

| Assignment behavior | Evidence |
|---|---|
| Normal RGB + depth | Correct shape/dtype; focus interior remains pixel-identical; background texture loses variance. |
| Mismatched dimensions | RGB and grayscale depth are aligned; uploaded 90×60 RGB / 30×20 RGB depth generates a valid matching output. |
| Bright = Near | Brightest depth maps to interpreted near value 0. |
| Dark = Near | Darkest depth maps to near; interpreted maps are complements. |
| Focus depth changes | High-frequency detail shifts between near and far regions. |
| Blur strength | Stronger blur reduces out-of-focus texture variance. |
| Feathering | Transition contains intermediate values and lower maximum spatial slope. |
| Missing images | Clean empty state and distinct missing RGB / missing depth warnings. |
| Large image | 6000×4000 image resizes to 1600×1067, preserving aspect ratio. |
| Download | PNG reopens correctly; red stays red without BGR swaps. |
| Clean launch / app state | AppTest has no runtime exceptions; demo, generation, presets, custom controls, direction changes, stale results and reset work. |
| Additional cases | Constant depth, corrupt input, BMP content and excessive decoded dimensions rejected; 16-bit depth preserved; zero blur is identity. |

Streamlit AppTest emits its normal “missing ScriptRunContext” warning in the test runner. This is not an application traceback or visible UI error.

## Browser checks — PASS

Verified on the local server using the available desktop Streamlit installation (1.66.1), in addition to the automated suite and clean server on the pinned 1.56.0 version:

- Empty state, sample scene loading, generation success, depth analysis and side-by-side comparison.
- Real browser upload controls accept both supplied sample files; generating the uploaded pair succeeds.
- Browser download creates a valid RGB PNG at 1200×780; decoded with Pillow and verified.
- Desktop layout checked at 1280 px. Primary button text contrast corrected to dark text on pale green.
- Narrow layout checked at 390×844: document width 390 px, main width 380 px, no horizontal overflow; columns stack and sidebar collapses.
- Changing a focus value suppresses the previous render/download until regeneration.
- Final browser smoke check on pinned Streamlit 1.56.0: sample load, depth analysis, generation and download controls displayed successfully; sample generation took 3.24 seconds. The final UI screenshot is from this clean environment.

## Additional performance checks

Timings are illustrative measurements from the available desktop environment, not cloud performance guarantees:

- 1200×780 synthetic sample, 6 levels: approximately 2.2 seconds in a direct engine run; browser runs approximately 2.6–4.7 seconds under other concurrent work.
- 4000×3000 input resized to 1600×1200, 9 levels, maximum blur: approximately 4.9 seconds. A uniform RGB color was preserved exactly.

## Deployment inspection and limits

All direct runtime imports are covered by requirements or Python's standard library. No machine-specific absolute paths, OpenCV GUI calls, keys, or environment variables are used by the project. Sample files are optional for uploaded-image operation. Configuration, CSS, samples and utility paths resolve from the application directory.

Streamlit Community Cloud deployment steps are documented, but deployment under a real GitHub/Cloud account has not been executed. Windows checks do not independently certify a Linux hosting environment. Quality on photographs with hair, transparent surfaces or inaccurate depth remains dependent on the supplied image/depth pair. The sample is intentionally synthetic.
