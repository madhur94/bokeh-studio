import base64
from io import BytesIO
import json
from pathlib import Path
import unittest
import urllib.request
import urllib.error
from unittest.mock import Mock

import numpy as np
from PIL import Image
from api.process import process_payload, handler


class ApiTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.pair = {name: base64.b64encode((root / "public/sample_images" / file).read_bytes()).decode()
            for name, file in [("rgb", "botanical_rgb.png"), ("depth", "botanical_depth.png")]}

    def test_sample_and_color_output(self):
        result = process_payload(self.pair)
        output = Image.open(BytesIO(base64.b64decode(result["result"])))
        self.assertEqual(output.format, "PNG")
        self.assertEqual(output.mode, "RGB")
        self.assertEqual(output.size, (900, 585))
        self.assertLess(len(json.dumps(result)), 4200000)
        for key in ("normalized", "depth", "mask"):
            preview = Image.open(BytesIO(base64.b64decode(result[key])))
            self.assertLessEqual(max(preview.size), 480)

    def test_invalid_settings_and_input(self):
        for payload in ({}, {**self.pair, "depth":"garbage!"},
            {**self.pair,"settings":{"levels":4.2}},
            {**self.pair,"settings":{"focus_depth":float("nan")}},
            {**self.pair,"settings":{"smooth":"false"}}):
            with self.assertRaises((ValueError, TypeError)):
                process_payload(payload)

    def test_constant_depth_and_16bit(self):
        buffer=BytesIO();Image.new("L",(10,10),128).save(buffer,"PNG")
        with self.assertRaisesRegex(ValueError,"constant"):
            process_payload({**self.pair,"depth":base64.b64encode(buffer.getvalue()).decode()})
        buffer=BytesIO();Image.fromarray(np.tile(np.linspace(1000,4000,40,dtype=np.uint16),(30,1))).save(buffer,"PNG")
        result=process_payload({**self.pair,"depth":base64.b64encode(buffer.getvalue()).decode(),"settings":{"bright_is_near":False,"blur_strength":0}})
        self.assertEqual(result["width"],900)

    def test_engine_matches_original(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual((root/"engine/bokeh.py").read_bytes(),(root.parent/"utils/bokeh.py").read_bytes())

    def test_local_http(self):
        for payload, expected in [(self.pair,200), ({},400)]:
            body=json.dumps(payload).encode()
            endpoint=handler.__new__(handler)
            endpoint.headers={"Content-Length":str(len(body)),"Content-Type":"application/json"}
            endpoint.rfile=BytesIO(body);endpoint.wfile=BytesIO()
            endpoint.send_response=Mock();endpoint.send_header=Mock();endpoint.end_headers=Mock()
            endpoint.do_POST()
            endpoint.send_response.assert_called_once_with(expected)
            result=json.loads(endpoint.wfile.getvalue())
            self.assertEqual(result["width"],900) if expected==200 else self.assertIn("error",result)

    def test_http_payload_limits(self):
        for headers, expected in [({"Content-Length":"4200001"},413),
            ({"Content-Length":"2","Content-Type":"text/plain"},415)]:
            endpoint=handler.__new__(handler);endpoint.headers=headers;endpoint.rfile=BytesIO(b'{}');endpoint.wfile=BytesIO()
            endpoint.send_response=Mock();endpoint.send_header=Mock();endpoint.end_headers=Mock()
            endpoint.do_POST();endpoint.send_response.assert_called_once_with(expected)


if __name__=="__main__":
    unittest.main()
