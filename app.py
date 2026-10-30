"""Bokeh Studio — Assignment 10, October 29, 2026."""
from hashlib import sha256
from html import escape
import logging
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np
from PIL import Image
import streamlit as st

from utils.bokeh import (BokehSettings, ImageInputError, create_focus_mask,
                         calculate_focus_distance, encode_download_image,
                         generate_bokeh, load_image, prepare_depth_map,
                         resize_for_processing)

st.set_page_config(page_title="Bokeh Studio", page_icon="📷", layout="wide",
                   initial_sidebar_state="expanded")
ROOT = Path(__file__).resolve().parent
log = logging.getLogger(__name__)
cv2.setNumThreads(2)
st.html("<style>" + (ROOT / "assets" / "style.css").read_text(encoding="utf-8") + "</style>")

DEFAULTS = {"focus": .22, "range": .18, "blur": 24, "feather": 3,
            "quality": "Balanced · 6 levels", "direction": "Bright = Near",
            "smooth": True, "style": "Natural"}
PRESETS = {"Natural": (24, 3, .18), "Portrait": (32, 4, .14), "Strong": (40, 5, .10)}


def reset() -> None:
    for key, value in DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["upload_epoch"] = st.session_state.get("upload_epoch", 0) + 1
    st.session_state.pop("result", None)
    st.session_state.pop("prepared", None)
    st.session_state.pop("prep_key", None)
    st.session_state["demo"] = False


def preset_changed() -> None:
    style = st.session_state.style
    if style in PRESETS:
        st.session_state.blur, st.session_state.feather, st.session_state.range = PRESETS[style]


def custom() -> None:
    st.session_state.style = "Custom"


def use_demo() -> None:
    reset()
    st.session_state.demo = True


for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)

with st.sidebar:
    st.html('<div class="brand"><span class="brand-icon">◉</span>Bokeh Studio</div>'
            '<div class="brand-sub">A little depth. A different perspective.</div>')
    st.caption("CONTROL PANEL")
    st.subheader("01 / Input images")
    epoch = st.session_state.get("upload_epoch", 0)
    rgb_upload = st.file_uploader("RGB / original image", type=["jpg", "jpeg", "png"], key=f"rgb_{epoch}")
    depth_upload = st.file_uploader("Corresponding depth map", type=["jpg", "jpeg", "png"], key=f"depth_{epoch}")
    st.button("Try the sample scene", key="sample_sidebar", on_click=use_demo, width="stretch",
              help="Load a synthetic botanical still life and its exact depth map.")
    st.divider()
    st.subheader("02 / Depth & focus")
    st.selectbox("Depth interpretation", ["Bright = Near", "Dark = Near"], key="direction",
                 help="After interpretation, focus depth always runs from 0 (near) to 1 (far).")
    st.slider("Focus depth", 0.0, 1.0, step=.01, key="focus", help="0 = nearest · 1 = farthest")
    st.slider("Focus range", .02, .80, step=.01, key="range", on_change=custom,
              help="Full width of the sharp depth band, centered on your focus depth.")
    st.checkbox("Smooth depth boundaries", key="smooth")
    st.divider()
    st.subheader("03 / Bokeh")
    st.selectbox("Bokeh style", ["Natural", "Portrait", "Strong", "Custom"], key="style", on_change=preset_changed)
    st.slider("Blur strength", 0, 40, key="blur", on_change=custom, help="Maximum Gaussian sigma in output pixels.")
    st.slider("Edge feathering", 0, 12, key="feather", on_change=custom, help="Softens transitions in output pixels.")
    st.selectbox("Blur quality", ["Fast · 4 levels", "Balanced · 6 levels", "Fine · 9 levels"], key="quality")
    st.divider()
    generate = st.button("Generate Bokeh", key="generate", type="primary", width="stretch")
    st.button("Reset workspace", key="reset", on_click=reset, width="stretch")
    st.caption("CPU powered · No API keys\n\n20 MB / file · JPG & PNG")

has_inputs = (rgb_upload is not None and depth_upload is not None) or st.session_state.get("demo", False)
hero_class = "hero hero-loaded" if has_inputs else "hero"
st.html('<div class="topline"><div class="eyebrow">BOKEH STUDIO / DEPTH-AWARE PHOTOGRAPHY</div>'
        '<span class="badge">Assignment 10 · 29 Oct 2026</span></div>'
        f'<div class="{hero_class}"><div class="eyebrow">COMPUTATIONAL PHOTOGRAPHY, MADE SIMPLE</div>'
        '<h1>Bring your subject<br> into <span>focus.</span></h1>'
        '<p>Turn an image and its depth map into a softer, more cinematic frame. '
        'You choose the focus. We take care of the falloff.</p></div>'
        '<div class="workflow"><div class="step"><b>01</b> Upload a pair</div>'
        '<div class="step"><b>02</b> Find your focus</div><div class="step"><b>03</b> Shape the blur</div>'
        '<div class="step"><b>04</b> Compare & export</div></div>')

# Uploaded files always take precedence over demo mode, including partial uploads.
demo = st.session_state.get("demo", False) and rgb_upload is None and depth_upload is None
pair = None
if demo:
    try:
        pair = ((ROOT / "sample_images" / "botanical_rgb.png").read_bytes(),
                (ROOT / "sample_images" / "botanical_depth.png").read_bytes())
    except OSError:
        st.warning("The optional sample is unavailable. Upload your own image pair to continue.")
elif rgb_upload is not None and depth_upload is not None:
    pair = (rgb_upload.getvalue(), depth_upload.getvalue())

if pair is None:
    st.html('<div class="empty"><div class="aperture">◎</div><div class="eyebrow">YOUR NEXT FRAME STARTS HERE</div>'
            '<h2>Two images. One new perspective.</h2>'
            '<p>Upload an RGB image and its corresponding depth map in the control panel '
            'to create your depth-aware Bokeh effect.</p>'
            '<small>JPG / PNG &nbsp; · &nbsp; GRAYSCALE OR RGB DEPTH &nbsp; · &nbsp; PRIVATE TO YOUR SESSION</small></div>')
    st.button("Explore with a sample →", key="sample_main", on_click=use_demo)
    if generate or rgb_upload is not None or depth_upload is not None:
        st.warning("Please upload an RGB image to continue." if rgb_upload is None else
                   "Please upload the corresponding depth map.")
else:
    try:
        # Decode per session without retaining user images in a shared cross-session cache.
        input_id = sha256(pair[0] + pair[1]).hexdigest()
        prep_key = (input_id, st.session_state.direction, st.session_state.smooth)
        if st.session_state.get("prep_key") != prep_key:
            with st.spinner("Preparing your image pair…"):
                original = load_image(pair[0])
                depth_image = load_image(pair[1], depth=True)
                image = resize_for_processing(original)
                normalized, depth = prepare_depth_map(depth_image, image.size,
                    bright_is_near=st.session_state.direction == "Bright = Near", smooth=st.session_state.smooth)
                depth_preview = depth_image.copy()
                depth_preview.thumbnail((800, 800))
                # Image display must handle 16-bit depth without clipping everything to white.
                if depth_preview.mode in {"I", "F", "I;16"}:
                    values = np.asarray(depth_preview, np.float32)
                    values = (values - values.min()) / max(float(np.ptp(values)), 1e-6)
                    depth_preview = Image.fromarray((values * 255).astype(np.uint8))
                st.session_state.prepared = (np.asarray(image), normalized, depth,
                    original.size, depth_image.size, np.asarray(depth_preview))
                st.session_state.prep_key = prep_key
                del original, depth_image, image, depth_preview
        rgb, normalized, depth, original_size, depth_size, depth_preview = st.session_state.prepared
        settings = BokehSettings(st.session_state.focus, st.session_state.range,
            st.session_state.blur, st.session_state.feather, int(st.session_state.quality.split("·")[1].split()[0]))
        signature = (prep_key, settings)
        size = rgb.shape[1], rgb.shape[0]
        st.caption(f"✓ {'Sample RGB' if demo else 'RGB image'} loaded · {original_size[0]} × {original_size[1]}   /   "
                   f"✓ Depth map loaded · {depth_size[0]} × {depth_size[1]}" +
                   (f" → aligned to {size[0]} × {size[1]}" if depth_size != size else ""))
        if size != original_size:
            st.info(f"Processing resolution optimized to {size[0]} × {size[1]} (1600 px maximum side). Downloads use this resolution.")
        if demo:
            st.caption("SAMPLE / A synthetic botanical still life with an exact paired depth map. Focus 0.22 highlights the foreground vase.")
        if generate:
            try:
                with st.spinner("Generating depth-aware Bokeh…"):
                    start = perf_counter()
                    output, alpha, amount = generate_bokeh(rgb, depth, settings)
                    st.session_state.result = dict(signature=signature, output=output,
                        png=encode_download_image(output), elapsed=perf_counter() - start)
            except Exception:
                log.exception("Bokeh generation failed")
                st.error("Unable to generate the Bokeh result. Please verify that both inputs are valid images.")
        saved = st.session_state.get("result")
        current = saved is not None and saved["signature"] == signature
        result_tab, depth_tab, compare_tab = st.tabs(["Result", "Depth analysis", "Comparison"])
        with result_tab:
            st.html('<div class="section-title"><h2>Your frame, reimagined.</h2>'
                    f'<span>{"RENDER COMPLETE" if current else "READY TO CREATE"}</span></div>')
            if current:
                st.image(saved["output"], width="stretch")
                st.success(f"Bokeh image generated successfully · {saved['elapsed']:.2f} s")
                st.download_button("Download Bokeh Image ↓", saved["png"], "bokeh_result.png", "image/png",
                                   type="primary", width="stretch", on_click="ignore")
            else:
                st.image(rgb, caption="Original / Adjust the controls, then select Generate Bokeh.", width="stretch")
                if saved:
                    st.info("Your inputs or settings have changed. Generate Bokeh to update the result and download.")
            entries = [("Resolution", f"{size[0]} × {size[1]}"), ("Focus depth", f"{settings.focus_depth:.2f}"),
                       ("Focus range", f"{settings.focus_range:.2f}"), ("Blur strength", f"{settings.blur_strength:g} px"),
                       ("Depth direction", st.session_state.direction)]
            st.html('<div class="info-grid">' + ''.join(f'<div><small>{escape(k)}</small><strong>{escape(v)}</strong></div>'
                                                       for k, v in entries) + '</div>')
        with depth_tab:
            st.caption("Live depth analysis · updates with your controls, before rendering.")
            left, right = st.columns(2)
            left.image(depth_preview, caption="Input depth / original encoding", width="stretch")
            right.image(normalized, caption="Normalized input / 0–1 intensity", clamp=True, width="stretch")
            left, right = st.columns(2)
            left.image(depth, caption="Interpreted depth / black = near, white = far", clamp=True, width="stretch")
            mask = create_focus_mask(calculate_focus_distance(depth, settings.focus_depth), settings.focus_range, settings.feathering)
            right.image(mask, caption="Focus mask / white = sharp, black = defocused", clamp=True, width="stretch")
            st.caption("RGB depth maps are read as luminance; false-color depth needs conversion to scalar depth first.")
        with compare_tab:
            if current:
                before, after = st.columns(2)
                before.image(rgb, caption="ORIGINAL", width="stretch")
                after.image(saved["output"], caption="BOKEH", width="stretch")
            else:
                st.info("Generate a result with your current settings to compare both frames.")
    except ImageInputError as exc:
        st.warning(str(exc))
    except Exception:
        log.exception("Image preparation failed")
        st.error("Unable to prepare this image pair. Please verify that both inputs are valid images.")

st.html('<div class="footer"><span>BOKEH STUDIO &nbsp; / &nbsp; A STUDY IN DEPTH & FOCUS</span>'
        '<span>Processed on the server · No permanent upload storage</span></div>')
