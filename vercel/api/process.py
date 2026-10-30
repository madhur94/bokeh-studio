"""Stateless Vercel function; each request uses the assignment's original engine."""
import base64
import binascii
from http.server import BaseHTTPRequestHandler
import json
import logging
from time import perf_counter

MAX_PAYLOAD = 4_200_000


def process_payload(payload):
    # Lazy imports keep health checks independent of OpenCV initialization.
    import cv2
    import numpy as np
    from PIL import Image
    from io import BytesIO
    from engine.bokeh import (BokehSettings, ImageInputError, load_image,
        resize_for_processing, prepare_depth_map, generate_bokeh, encode_download_image)

    if not isinstance(payload, dict):
        raise ValueError("Send an image pair and valid settings.")
    def decode(name):
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Please upload the {name} image.")
        try:
            return base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The uploaded image data is invalid.") from None
    params = payload.get("settings", {})
    if not isinstance(params, dict):
        raise ValueError("Invalid Bokeh settings.")
    for key in ("bright_is_near", "smooth"):
        if key in params and not isinstance(params[key], bool):
            raise ValueError("Depth settings must be true or false.")
    levels = params.get("levels", 6)
    if isinstance(levels, bool) or not isinstance(levels, int):
        raise ValueError("Blur levels must be a whole number.")
    settings = BokehSettings(float(params.get("focus_depth", .22)),
        float(params.get("focus_range", .18)), float(params.get("blur_strength", 24)),
        float(params.get("feathering", 3)), levels)
    settings.validate()
    cv2.setNumThreads(2)
    start = perf_counter()
    source = load_image(decode("rgb"))
    depth_image = load_image(decode("depth"), depth=True)
    image = resize_for_processing(source, 900)
    raw, depth = prepare_depth_map(depth_image, image.size,
        bright_is_near=params.get("bright_is_near", True), smooth=params.get("smooth", True))
    result, mask, _ = generate_bokeh(np.asarray(image), depth, settings)
    def preview(array):
        buf = BytesIO()
        im = Image.fromarray(np.uint8(np.clip(array, 0, 1) * 255))
        im.thumbnail((480, 480))
        im.save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    response = dict(result=base64.b64encode(encode_download_image(result)).decode("ascii"),
        normalized=preview(raw), depth=preview(depth), mask=preview(mask),
        width=image.width, height=image.height, seconds=round(perf_counter()-start, 2))
    if len(json.dumps(response)) > MAX_PAYLOAD:
        raise ImageInputError("The result is too large to return. Try a smaller input image.")
    return response


class handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_json(200, {"status": "ok", "service": "Bokeh Studio"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_PAYLOAD:
                self.send_json(413, {"error": "The image pair is too large. Choose smaller images."})
                return
            if "application/json" not in self.headers.get("Content-Type", ""):
                self.send_json(415, {"error": "Send the image pair as JSON."})
                return
            payload = json.loads(self.rfile.read(length))
            self.send_json(200, process_payload(payload))
        except (ValueError, TypeError, OverflowError) as exc:
            self.send_json(400, {"error": str(exc) or "Please check your input images and settings."})
        except Exception:
            logging.exception("Bokeh generation failed")
            self.send_json(500, {"error": "Unable to generate Bokeh. Please verify both images and try again."})
