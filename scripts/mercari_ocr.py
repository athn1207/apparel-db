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

# Default crop ratios (0–1) for Mercari iPhone layout
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
    preprocess: bool = True,
    contrast_factor: float = 1.5,
) -> dict[str, str]:
    """
    Extract brand and product_name from a single Mercari screenshot using region-based OCR.

    Returns:
        {
          "brand": "...",
          "product_name": "...",
          "raw_brand_text": "...",
          "raw_product_text": "..."
        }
    """
    image_path = Path(image_path)
    if not image_path.exists():
        return {"brand": "", "product_name": "", "raw_brand_text": "", "raw_product_text": "", "raw_price_text": ""}

    brand_region, product_region, price_region = _load_region_config(config_path)
    if config_path and config_path.exists():
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if "preprocess" in cfg:
                preprocess = bool(cfg["preprocess"])
        except Exception:
            pass

    try:
        pil = Image.open(image_path).convert("RGB")
    except Exception as e:
        print(f"ERROR: Could not load image: {image_path}")
        print(f"  {e}")
        return {"brand": "", "product_name": "", "raw_brand_text": "", "raw_product_text": "", "raw_price_text": ""}
    if pil is None or pil.size[0] == 0 or pil.size[1] == 0:
        print(f"ERROR: Could not load image: {image_path} (invalid or empty)")
        return {"brand": "", "product_name": "", "raw_brand_text": "", "raw_product_text": "", "raw_price_text": ""}

    if preprocess:
        try:
            from scripts.ocr_preprocess import preprocess_for_ocr
        except ImportError:
            from ocr_preprocess import preprocess_for_ocr
        def prep(crop_img: Image.Image) -> Image.Image:
            return preprocess_for_ocr(
                crop_img,
                grayscale=True,
                resize_2x_flag=True,
                contrast_factor=contrast_factor,
                adaptive_thresh=True,
                sharpen_flag=True,
            )
    else:
        def prep(crop_img: Image.Image) -> Image.Image:
            return crop_img

    # Brand region — raw OCR only for debug, then process
    brand_crop = _crop_region(pil, brand_region)
    brand_pil = prep(brand_crop)
    raw_brand_text = _run_tesseract(brand_pil)
    print(f"[OCR debug] {image_path.name} — Raw OCR result for brand region: {repr(raw_brand_text)}")
    brand = _extract_brand_from_raw(raw_brand_text)

    # Product name region — raw OCR only for debug, then process
    product_crop = _crop_region(pil, product_region)
    product_pil = prep(product_crop)
    raw_product_text = _run_tesseract(product_pil)
    print(f"[OCR debug] {image_path.name} — Raw OCR result for product name region: {repr(raw_product_text)}")
    product_name = _clean_product_text(raw_product_text)

    # Price region — raw OCR for debug only (no processing)
    price_crop = _crop_region(pil, price_region)
    price_pil = prep(price_crop)
    raw_price_text = _run_tesseract(price_pil)
    print(f"[OCR debug] {image_path.name} — Raw OCR result for price region: {repr(raw_price_text)}")

    return {
        "brand": brand,
        "product_name": product_name,
        "raw_brand_text": raw_brand_text,
        "raw_product_text": raw_product_text,
        "raw_price_text": raw_price_text,
    }


# Allow running as script for one image
if __name__ == "__main__":
    import json
    import sys
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "screenshot_config.json"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not path or not path.exists():
        print("Usage: python mercari_ocr.py <image_path>")
        sys.exit(1)
    result = extract_from_image(path, config_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
