"""Behavioral tests; run with python -m unittest discover -s tests -v."""
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
from streamlit.testing.v1 import AppTest

from utils.bokeh import (BokehSettings, ImageInputError, load_image,
    resize_for_processing, normalize_depth, prepare_depth_map,
    calculate_focus_distance, create_focus_mask, generate_bokeh, encode_download_image)


def encoded(image, fmt="PNG"):
    stream = BytesIO()
    image.save(stream, format=fmt)
    return stream.getvalue()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        y, x = np.mgrid[:128, :192]
        checker = (((x // 3 + y // 3) % 2) * 255).astype(np.uint8)
        self.rgb = np.stack([checker, np.roll(checker, 2, 0), 255-checker], axis=-1)
        self.depth = np.where(x < 96, .2, 1).astype(np.float32)

    def test_load_and_generate(self):
        image = load_image(encoded(Image.fromarray(self.rgb)))
        output, mask, amount = generate_bokeh(np.asarray(image), self.depth, BokehSettings())
        self.assertEqual(output.shape, self.rgb.shape)
        self.assertEqual(output.dtype, np.uint8)
        np.testing.assert_array_equal(output[:, :60], self.rgb[:, :60])
        self.assertLess(output[:, 130:].var(), self.rgb[:, 130:].var())
        self.assertTrue(np.all((mask >= 0) & (mask <= 1)))
        self.assertGreater(amount[:, 130:].mean(), amount[:, :60].mean())

    def test_resize_and_rgb_depth(self):
        small = np.tile(np.linspace(0, 255, 12, dtype=np.uint8), (8, 1))
        gray = Image.fromarray(small)
        raw, depth = prepare_depth_map(gray.convert("RGB"), (192, 128), smooth=False)
        self.assertEqual(depth.shape, (128, 192))
        self.assertAlmostEqual(float(depth.min()), 0)
        self.assertAlmostEqual(float(depth.max()), 1)
        np.testing.assert_allclose(raw, prepare_depth_map(gray, (192, 128), smooth=False)[0], atol=1e-6)

    def test_depth_direction(self):
        image = Image.fromarray(np.array([[0, 100, 255], [0, 100, 255]], np.uint8))
        _, bright = prepare_depth_map(image, image.size, bright_is_near=True, smooth=False)
        _, dark = prepare_depth_map(image, image.size, bright_is_near=False, smooth=False)
        np.testing.assert_allclose(bright + dark, 1)
        self.assertEqual(bright[0, -1], 0)
        self.assertEqual(dark[0, 0], 0)

    def test_focus_change(self):
        near, _, _ = generate_bokeh(self.rgb, self.depth, BokehSettings(focus_depth=.2))
        far, _, _ = generate_bokeh(self.rgb, self.depth, BokehSettings(focus_depth=1))
        self.assertGreater(near[:, :60].var(), far[:, :60].var())
        self.assertGreater(far[:, 130:].var(), near[:, 130:].var())

    def test_blur_strength(self):
        low = generate_bokeh(self.rgb, self.depth, BokehSettings(blur_strength=2))[0]
        high = generate_bokeh(self.rgb, self.depth, BokehSettings(blur_strength=24))[0]
        self.assertLess(high[:, 130:].var(), low[:, 130:].var())

    def test_feathering(self):
        distance = calculate_focus_distance(self.depth, .2)
        hard = create_focus_mask(distance, .1, 0)
        soft = create_focus_mask(distance, .1, 5)
        self.assertGreater(np.count_nonzero((soft > .01) & (soft < .99)), 0)
        self.assertLess(np.max(np.abs(np.diff(soft, axis=1))), np.max(np.abs(np.diff(hard, axis=1))))

    def test_large_image(self):
        result = resize_for_processing(Image.new("RGB", (6000, 4000)))
        self.assertEqual(result.size, (1600, 1067))

    def test_download_rgb(self):
        red = np.full((20, 30, 3), (255, 0, 0), np.uint8)
        output = generate_bokeh(red, np.tile(np.linspace(0, 1, 30, dtype=np.float32), (20, 1)), BokehSettings())[0]
        payload = encode_download_image(output)
        with Image.open(BytesIO(payload)) as decoded:
            self.assertEqual(decoded.format, "PNG")
            np.testing.assert_array_equal(np.asarray(decoded), red)

    def test_constant_invalid_and_unsupported(self):
        with self.assertRaisesRegex(ImageInputError, "constant"):
            normalize_depth(np.ones((20, 20)))
        for data in (b"garbage", b"", encoded(Image.new("RGB", (10, 10)), "BMP")):
            with self.assertRaises(ImageInputError):
                load_image(data)
        with patch("utils.bokeh.MAX_INPUT_PIXELS", 10):
            with self.assertRaisesRegex(ImageInputError, "megapixels"):
                load_image(encoded(Image.new("RGB", (4, 4))))

    def test_16bit_depth(self):
        values = np.array([[1000, 2000, 4000]], np.uint16)
        image = load_image(encoded(Image.fromarray(values)), depth=True)
        raw, _ = prepare_depth_map(image, image.size, smooth=False)
        np.testing.assert_allclose(raw, [[0, 1/3, 1]], atol=1e-6)

    def test_zero_blur_identity(self):
        output = generate_bokeh(self.rgb, self.depth, BokehSettings(blur_strength=0))[0]
        np.testing.assert_array_equal(output, self.rgb)


class AppTests(unittest.TestCase):
    def test_uploaded_pair_mismatch_and_download(self):
        y, x = np.mgrid[:60, :90]
        rgb = np.stack([x * 2, y * 3, x + y], axis=-1).astype(np.uint8)
        depth = np.tile(np.linspace(0, 255, 30, dtype=np.uint8), (20, 1))
        uploads = [BytesIO(encoded(Image.fromarray(rgb))), BytesIO(encoded(Image.fromarray(depth).convert("RGB")))]
        with patch("streamlit.file_uploader", side_effect=uploads * 2):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
            app.button(key="generate").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("successfully" in item.value for item in app.success))
        self.assertEqual(app.session_state["result"]["output"].shape, rgb.shape)
        png = app.session_state["result"]["png"]
        self.assertEqual(Image.open(BytesIO(png)).size, (90, 60))

    def test_missing_depth_and_constant_map(self):
        rgb = BytesIO(encoded(Image.new("RGB", (30, 20), "red")))
        with patch("streamlit.file_uploader", side_effect=[rgb, None]):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        self.assertTrue(any("corresponding depth" in item.value for item in app.warning))
        constant = BytesIO(encoded(Image.new("L", (30, 20), 100)))
        with patch("streamlit.file_uploader", side_effect=[rgb, constant]):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        self.assertTrue(any("constant" in item.value for item in app.warning))
        self.assertEqual(len(app.exception), 0)

    def test_empty_missing_demo_generate_stale_and_reset(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        app.button(key="generate").click().run()  # Generate with no images.
        self.assertIn("RGB image", app.warning[0].value)
        app.button(key="sample_sidebar").click().run()  # Load sample.
        self.assertEqual(len(app.exception), 0)
        app.button(key="generate").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("successfully" in item.value for item in app.success))
        self.assertEqual(len(app.get("download_button")), 1)
        app.slider(key="focus").set_value(.7).run()
        self.assertEqual(len(app.get("download_button")), 0)
        self.assertTrue(any("changed" in item.value for item in app.info))
        app.selectbox(key="style").select("Portrait").run()
        self.assertEqual(app.slider(key="blur").value, 32)
        app.slider(key="blur").set_value(18).run()
        self.assertEqual(app.selectbox(key="style").value, "Custom")
        app.selectbox(key="direction").select("Dark = Near").run()
        self.assertEqual(len(app.exception), 0)
        app.button(key="reset").click().run()
        self.assertEqual(app.slider(key="focus").value, .22)
        self.assertFalse(app.session_state["demo"])


if __name__ == "__main__":
    unittest.main()
