"""Depth-aware defocus. All public color arrays use RGB, never OpenCV BGR."""
from dataclasses import dataclass
from io import BytesIO
from typing import Iterator
import warnings

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_INPUT_PIXELS = 24_000_000
MAX_SIDE = 1600


class ImageInputError(ValueError):
    """A readable, user-facing input validation error."""


@dataclass(frozen=True)
class BokehSettings:
    focus_depth: float = 0.22
    focus_range: float = 0.18
    blur_strength: float = 24.0
    feathering: float = 3.0
    levels: int = 6

    def validate(self) -> None:
        values = (self.focus_depth, self.focus_range, self.blur_strength, self.feathering)
        if not all(np.isfinite(v) for v in values):
            raise ValueError("Settings must be finite numbers.")
        if not (0 <= self.focus_depth <= 1 and 0.01 <= self.focus_range <= 1):
            raise ValueError("Focus depth or range is outside its supported range.")
        if not (0 <= self.blur_strength <= 40 and 0 <= self.feathering <= 12):
            raise ValueError("Blur or feathering is outside its supported range.")
        if not isinstance(self.levels, int) or not 3 <= self.levels <= 10:
            raise ValueError("Choose between 3 and 10 blur levels.")


def load_image(data: bytes, *, depth: bool = False) -> Image.Image:
    """Validate encoded content, apply EXIF orientation, and retain 16-bit depth."""
    if not data or len(data) > MAX_FILE_BYTES:
        raise ImageInputError("Choose a non-empty JPG or PNG smaller than 20 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise ImageInputError("Only JPG, JPEG and PNG images are supported.")
                if source.width * source.height > MAX_INPUT_PIXELS:
                    raise ImageInputError("This image exceeds 24 megapixels. Resize it before uploading.")
                source.load()
                image = ImageOps.exif_transpose(source)
                if depth:
                    # Palette colors must be expanded before luminance conversion.
                    return image.convert("RGB") if image.mode in {"P", "RGBA", "LA"} else image.copy()
                if image.mode in {"RGBA", "LA", "P"}:
                    rgba = image.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, (17, 21, 18, 255))
                    return Image.alpha_composite(background, rgba).convert("RGB")
                return image.convert("RGB")
    except ImageInputError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ImageInputError("Unable to read this image. Upload a valid JPG or PNG.") from exc


def resize_for_processing(image: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    if not 1 <= max_side <= MAX_SIDE:
        raise ValueError("Processing size must be between 1 and 1600 pixels.")
    scale = min(1.0, max_side / max(image.size))
    size = tuple(max(1, round(d * scale)) for d in image.size)
    return image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image.copy()


def normalize_depth(depth: np.ndarray) -> np.ndarray:
    values = np.asarray(depth, dtype=np.float32)
    if values.ndim != 2 or not np.isfinite(values).all():
        raise ImageInputError("The depth map must contain finite grayscale values.")
    low, high = float(values.min()), float(values.max())
    if high - low <= 1e-6:
        raise ImageInputError("This depth map is constant. Meaningful depth separation is unavailable.")
    return (values - low) / (high - low)


def prepare_depth_map(image: Image.Image, size: tuple[int, int], *,
                      bright_is_near: bool = True, smooth: bool = True) -> tuple[np.ndarray, np.ndarray]:
    array = np.asarray(image)
    if array.ndim == 3:
        # Float conversion before conversion keeps numeric precision for depth inputs.
        array = cv2.cvtColor(array[..., :3].astype(np.float32), cv2.COLOR_RGB2GRAY)
    normalized = normalize_depth(array)
    if normalized.shape[::-1] != size:
        normalized = cv2.resize(normalized, size, interpolation=cv2.INTER_LINEAR)
    raw = normalized.copy()
    if smooth:
        normalized = cv2.bilateralFilter(normalized, 5, 0.06, 3.0)
    interpreted = 1.0 - normalized if bright_is_near else normalized
    return raw, np.clip(interpreted, 0, 1).astype(np.float32)


def calculate_focus_distance(depth: np.ndarray, focus_depth: float) -> np.ndarray:
    return np.abs(depth - focus_depth)


def smoothstep(value: np.ndarray) -> np.ndarray:
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def refine_mask(mask: np.ndarray, feathering: float) -> np.ndarray:
    if feathering <= 0:
        return mask.astype(np.float32)
    return np.clip(cv2.GaussianBlur(mask, (0, 0), feathering), 0, 1)


def create_focus_mask(distance: np.ndarray, focus_range: float, feathering: float) -> np.ndarray:
    # Width is the full in-focus band; a small depth ramp avoids binary cutouts.
    mask = 1.0 - smoothstep((distance - focus_range / 2) / 0.08)
    return refine_mask(mask, feathering)


def _to_linear(rgb: np.ndarray) -> np.ndarray:
    value = rgb.astype(np.float32) / 255
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def create_blur_pyramid(linear: np.ndarray, alpha: np.ndarray, strength: float,
                        levels: int) -> Iterator[tuple[int, np.ndarray]]:
    """Yield levels individually to bound memory. Gaussian sigma is in output pixels.

    Normalized convolution excludes the sharp subject from defocused source colors,
    reducing its color spilling into the background. A small floor is intentional.
    """
    yield 0, linear
    source_weight = np.maximum(1.0 - alpha, 0.001).astype(np.float32)
    weighted = linear * source_weight[..., None]
    for index in range(1, levels):
        sigma = strength * index / (levels - 1)
        if sigma <= 0:
            yield index, linear
            continue
        denominator = cv2.GaussianBlur(source_weight, (0, 0), sigma)
        numerator = cv2.GaussianBlur(weighted, (0, 0), sigma)
        yield index, numerator / np.maximum(denominator[..., None], 1e-6)


def blend_layers(pyramid: Iterator[tuple[int, np.ndarray]], amount: np.ndarray,
                  levels: int) -> np.ndarray:
    position = amount * (levels - 1)
    result = np.zeros((*amount.shape, 3), np.float32)
    for index, layer in pyramid:
        weight = np.maximum(1.0 - np.abs(position - index), 0)
        result += layer * weight[..., None]
    return result


def apply_depth_aware_blur(rgb: np.ndarray, depth: np.ndarray,
                          settings: BokehSettings) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    settings.validate()
    if rgb.dtype != np.uint8 or rgb.shape != (*depth.shape, 3):
        raise ValueError("Expected matching uint8 RGB and float depth arrays.")
    if max(rgb.shape[:2]) > MAX_SIDE or not np.isfinite(depth).all() or depth.min() < 0 or depth.max() > 1:
        raise ValueError("Depth must be normalized and images must fit the processing limit.")
    distance = calculate_focus_distance(depth, settings.focus_depth)
    alpha = create_focus_mask(distance, settings.focus_range, settings.feathering)
    span = max(settings.focus_depth, 1 - settings.focus_depth) - settings.focus_range / 2
    amount = np.clip((distance - settings.focus_range / 2) / max(span, 0.01), 0, 1)
    amount = refine_mask(amount, settings.feathering)
    linear = _to_linear(rgb)
    blurred = blend_layers(create_blur_pyramid(linear, alpha, settings.blur_strength, settings.levels),
                           amount, settings.levels)
    output = linear * alpha[..., None] + blurred * (1 - alpha[..., None])
    srgb = np.where(output <= 0.0031308, 12.92 * output, 1.055 * np.maximum(output, 0) ** (1 / 2.4) - 0.055)
    return np.clip(np.rint(srgb * 255), 0, 255).astype(np.uint8), alpha, amount


def generate_bokeh(rgb: np.ndarray, depth: np.ndarray,
                    settings: BokehSettings) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return apply_depth_aware_blur(rgb, depth, settings)


def encode_download_image(rgb: np.ndarray) -> bytes:
    buffer = BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG")
    return buffer.getvalue()
