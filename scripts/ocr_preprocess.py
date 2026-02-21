# -*- coding: utf-8 -*-
"""
Modular image preprocessing for OCR (Mercari iPhone screenshots).
Each step can be used independently; pipeline runs: grayscale → resize 2x → contrast → adaptive threshold → sharpen.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


def to_grayscale(img: np.ndarray | Image.Image) -> np.ndarray:
    """Convert to grayscale. Accepts RGB numpy (H,W,3) or PIL Image."""
    if isinstance(img, Image.Image):
        img = np.array(img)
    if img.ndim == 3:
        # RGB -> luminance
        return np.round(0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]).astype(np.uint8)
    return img


def resize_2x(img: np.ndarray) -> np.ndarray:
    """Upscale by 2x (better for small text)."""
    from PIL import Image as PILImage
    pil = PILImage.fromarray(img)
    w, h = pil.size
    pil = pil.resize((w * 2, h * 2), PILImage.Resampling.LANCZOS)
    return np.array(pil)


def increase_contrast(img: np.ndarray, factor: float = 1.5) -> np.ndarray:
    """Increase contrast. factor > 1 strengthens contrast."""
    pil = Image.fromarray(img)
    enhancer = ImageEnhance.Contrast(pil)
    pil = enhancer.enhance(factor)
    return np.array(pil)


def adaptive_threshold(img: np.ndarray, block_size: int = 15, c: int = 8) -> np.ndarray:
    """Adaptive threshold for uneven lighting. Prefer odd block_size."""
    try:
        import cv2
    except ImportError:
        return img
    if block_size % 2 == 0:
        block_size += 1
    return cv2.adaptiveThreshold(
        img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c
    )


def sharpen(img: np.ndarray) -> np.ndarray:
    """Sharpen image (helps thin text)."""
    pil = Image.fromarray(img)
    pil = pil.filter(ImageFilter.SHARPEN)
    return np.array(pil)


def preprocess_for_ocr(
    img: np.ndarray | Image.Image,
    *,
    grayscale: bool = True,
    resize_2x_flag: bool = True,
    contrast_factor: float = 1.5,
    adaptive_thresh: bool = True,
    sharpen_flag: bool = True,
) -> Image.Image:
    """
    Full pipeline for OCR: grayscale → resize 2x → contrast → adaptive threshold → sharpen.
    Returns PIL Image for pytesseract.
    """
    if isinstance(img, Image.Image):
        img = np.array(img.convert("RGB") if img.mode != "L" else img)
    if img.ndim == 3:
        img = to_grayscale(img)
    elif grayscale:
        pass  # already gray
    if resize_2x_flag:
        img = resize_2x(img)
    if contrast_factor and contrast_factor != 1.0:
        img = increase_contrast(img, factor=contrast_factor)
    if adaptive_thresh:
        img = adaptive_threshold(img)
    if sharpen_flag:
        img = sharpen(img)
    return Image.fromarray(img)
