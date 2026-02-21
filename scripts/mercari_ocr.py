# -*- coding: utf-8 -*-
"""
Region-based OCR for Mercari iPhone screenshots (e.g. 1179x2556).
Extracts brand and product_name from fixed crop regions using Tesseract (psm 6, jpn+eng).
Crop ratios and preprocessing are configurable.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image

# iPhone resolution for fixed crop (no auto-detect)
IPHONE_WIDTH = 1179
IPHONE_HEIGHT = 2556
# Zone 1: Product title — x=0, y=1570, full width, height=120
ZONE1_TITLE = {"x": 0, "y": 1570, "width": 1179, "height": 120}
# Zone 2: Brand/status line — directly below Zone 1, height=80
ZONE2_BRAND_STATUS = {"x": 0, "y": 1570 + 120, "width": 1179, "height": 80}
# Legacy single crop (used by extract_product_title_fixed standalone)
PRODUCT_TITLE_CROP = {"x": 0, "y": 1570, "width": 1179, "height": 120}

# Default crop ratios (0–1) for Mercari iPhone layout (used by extract_from_image)
DEFAULT_BRAND_REGION = {"x_min": 0.05, "x_max": 0.95, "y_min": 0.60, "y_max": 0.68}
DEFAULT_PRODUCT_REGION = {"x_min": 0.05, "x_max": 0.95, "y_min": 0.40, "y_max": 0.48}
DEFAULT_PRICE_REGION = {"x_min": 0.05, "x_max": 0.95, "y_min": 0.52, "y_max": 0.60}

# Dot variants to normalize to "・" (middle dot)
DOT_VARIANTS = ["･", "·", ".", "•", "｡"]

# UI words to remove from product name text
PRODUCT_UI_WORDS = ["いいね", "コメント", "商品の説明", "配送料", "税込", "送料込み"]


def _load_region_config(config_path: Path | None) -> tuple[dict, dict, dict]:
    """Load brand_region, product_region, price_region from config. Returns (brand, product, price)."""
    brand = dict(DEFAULT_BRAND_REGION)
    product = dict(DEFAULT_PRODUCT_REGION)
    price = dict(DEFAULT_PRICE_REGION)
    if not config_path or not config_path.exists():
        return brand, product, price
    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, default in (("brand_region", brand), ("product_region", product), ("price_region", price)):
            z = data.get(key)
            if z and isinstance(z, dict):
                for k in ("x_min", "x_max", "y_min", "y_max"):
                    if k in z:
                        default[k] = float(z[k])
    except Exception:
        pass
    return brand, product, price


def _crop_region(pil_img: Image.Image, region: dict) -> Image.Image:
    """Crop image by ratio (0–1). region: x_min, x_max, y_min, y_max."""
    w, h = pil_img.size
    x0 = int(w * region["x_min"])
    x1 = int(w * region["x_max"])
    y0 = int(h * region["y_min"])
    y1 = int(h * region["y_max"])
    return pil_img.crop((x0, y0, x1, y1))


def _crop_fixed_zone(pil_img: Image.Image, zone: dict) -> Image.Image:
    """Crop by fixed pixel zone: x, y, width, height. Clamps to image bounds."""
    w, h = pil_img.size
    left = max(0, min(zone["x"], w - 1))
    top = max(0, min(zone["y"], h - 1))
    right = min(left + zone["width"], w)
    bottom = min(top + zone["height"], h)
    return pil_img.crop((left, top, right, bottom))


def _crop_zone1_title(pil_img: Image.Image) -> Image.Image:
    """Zone 1: Product title. Height 120px. No auto-detect."""
    return _crop_fixed_zone(pil_img, ZONE1_TITLE)


def _crop_zone2_brand_status(pil_img: Image.Image) -> Image.Image:
    """Zone 2: Brand/status line. Height 80px, directly below Zone 1."""
    return _crop_fixed_zone(pil_img, ZONE2_BRAND_STATUS)


def _crop_product_title_fixed(pil_img: Image.Image) -> Image.Image:
    """Crop Zone 1 only (product title). For standalone script."""
    return _crop_zone1_title(pil_img)


def _normalize_dots(text: str) -> str:
    """Replace dot variants with '・'."""
    s = text
    for d in DOT_VARIANTS:
        s = s.replace(d, "・")
    return s


def _extract_brand_from_raw(raw: str) -> str:
    """Split by '・'; if len(parts) >= 3, return parts[1].strip()."""
    raw = _normalize_dots(raw)
    parts = raw.split("・")
    if len(parts) >= 3:
        return parts[1].strip()[:40]
    return raw.strip()[:40]


def _clean_product_text(raw: str) -> str:
    """Remove UI words, price pattern (¥ and numbers), extra line breaks; join to one string."""
    s = raw.strip()
    for w in PRODUCT_UI_WORDS:
        s = re.sub(re.escape(w), "", s)
    s = re.sub(r"¥\s*[\d,]+", "", s)
    s = re.sub(r"\d{1,3}(,\d{3})*\s*円", "", s)
    s = re.sub(r"\n\s*", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()[:150]


def _find_tesseract_cmd() -> str | None:
    """PATH に無い場合、Windows のよくあるインストール先から tesseract.exe を探す。"""
    import shutil
    if shutil.which("tesseract"):
        return None  # PATH で見つかったらそのまま
    for base in (
        Path(r"C:\Program Files\Tesseract-OCR"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR"),
    ):
        exe = base / "tesseract.exe"
        if exe.exists():
            return str(exe)
    return None


def _run_tesseract(pil_img: Image.Image, lang: str = "jpn+eng", psm: int = 6) -> str:
    """Run Tesseract OCR. Returns extracted text."""
    try:
        import pytesseract
    except ImportError:
        return ""
    cmd = _find_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        return (pytesseract.image_to_string(pil_img, lang=lang, config=f"--psm {psm}") or "").strip()
    except Exception:
        return ""


def extract_from_image(
    image_path: Path | str,
    config_path: Path | None = None,
    *,
    preprocess: bool = False,
    contrast_factor: float = 1.5,
) -> dict[str, str]:
    """
    Extract brand and product_name from a single Mercari screenshot.
    Two fixed crop zones (1179x2556): Zone 1 = product title (120px), Zone 2 = brand/status (80px, below Zone 1).
    OCR runs separately per zone. Brand is extracted ONLY from Zone 2 (never from product title).
    Preprocessing disabled. Uses lang="jpn+eng", --psm 6.

    Returns:
        { "brand", "product_name", "raw_brand_text", "raw_product_text", "raw_price_text" }
    """
    image_path = Path(image_path)
    if not image_path.exists():
        return {"brand": "", "product_name": "", "raw_brand_text": "", "raw_product_text": "", "raw_price_text": ""}

    _, _, price_region = _load_region_config(config_path)
    # Preprocessing disabled: OCR on cropped original only. Brand from Zone 2 only, not from title.

    try:
        pil = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"ERROR: Could not load image: {image_path}")
        print(f"  {e}")
        return {"brand": "", "product_name": "", "raw_brand_text": "", "raw_product_text": "", "raw_price_text": ""}
    if pil is None or pil.size[0] == 0 or pil.size[1] == 0:
        print(f"ERROR: Could not load image: {image_path} (invalid or empty)")
        return {"brand": "", "product_name": "", "raw_brand_text": "", "raw_product_text": "", "raw_price_text": ""}

    # Zone 1: Product title only (height 120px). OCR → product_name. Do NOT use for brand.
    zone1_crop = _crop_zone1_title(pil)
    raw_product_text = _run_tesseract(zone1_crop)
    print(f"[Raw OCR] {image_path.name} Zone 1 (title): {repr(raw_product_text)}")
    product_name = _clean_product_text(raw_product_text)

    # Zone 2: Brand/status line only (height 80px, below Zone 1). Brand MUST be extracted from here only.
    zone2_crop = _crop_zone2_brand_status(pil)
    raw_brand_text = _run_tesseract(zone2_crop)
    print(f"[Raw OCR] {image_path.name} Zone 2 (brand/status): {repr(raw_brand_text)}")
    brand = _extract_brand_from_raw(raw_brand_text)

    # Price region — ratio-based (unchanged)
    price_crop = _crop_region(pil, price_region)
    raw_price_text = _run_tesseract(price_crop)
    print(f"[Raw OCR] {image_path.name} price region: {repr(raw_price_text)}")

    return {
        "brand": brand,
        "product_name": product_name,
        "raw_brand_text": raw_brand_text,
        "raw_product_text": raw_product_text,
        "raw_price_text": raw_price_text,
    }


def extract_product_title_fixed(
    image_path: Path | str,
    save_crop_dir: Path | None = None,
) -> dict[str, str]:
    """
    Fixed crop for iPhone 1179x2556. Zone 1 only (product title, height 120px).
    Saves raw cropped image, runs OCR with lang="jpn+eng", config="--psm 6".
    Returns and prints: raw_crop_path, raw_ocr_result.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        return {"raw_crop_path": "", "raw_ocr_result": ""}
    try:
        pil = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"ERROR: Could not load image: {image_path}\n  {e}")
        return {"raw_crop_path": "", "raw_ocr_result": ""}
    crop = _crop_product_title_fixed(pil)
    out_dir = save_crop_dir or (image_path.resolve().parent / "crop_product_title")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    crop_path = out_dir / f"{image_path.stem}_crop.png"
    crop.save(crop_path)
    raw_text = _run_tesseract(crop, lang="jpn+eng", psm=6)
    print("Raw cropped image:", crop_path)
    print("Raw OCR result:", raw_text)
    return {"raw_crop_path": str(crop_path), "raw_ocr_result": raw_text}


# Allow running as script for one image (fixed crop: 1179x2556 product title zone only)
if __name__ == "__main__":
    import sys
    project_root = Path(__file__).resolve().parent.parent
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not path or not path.exists():
        print("Usage: python mercari_ocr.py <image_path>")
        sys.exit(1)
    crop_dir = project_root / "crop_product_title"
    extract_product_title_fixed(path, save_crop_dir=crop_dir)
