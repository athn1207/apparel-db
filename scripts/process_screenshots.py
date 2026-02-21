#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# OpenMP の二重読み込みエラーを避ける（EasyOCR/PyTorch 利用時）
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

"""
スクリーンショットを処理し、同一商品をまとめてブランドを読み取る。

使い方:
  1. スクショを screenshots_input/ に置く（タイトルがはっきり見えるもの + 下にスクロールして「項目：ブランド」が写っているもの）
  2. python scripts/process_screenshots.py を実行
  3. 同一商品は「画面上部に途中まで見える商品名」が一致するものとしてグループ化
  4. 「ブランド」が含まれる画像からブランド名を抽出
  5. 結果は suggested_products.json に出力。画像は images/ にコピーされる

必要: pip install easyocr
"""

from pathlib import Path
import json
import re
import shutil
from datetime import date

# プロジェクトのルート（このスクリプトの2つ上のフォルダ）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "screenshots_input"
IMAGES_DIR = PROJECT_ROOT / "images"
DATA_JSON = PROJECT_ROOT / "data" / "data.json"
OUTPUT_JSON = PROJECT_ROOT / "suggested_products.json"


def normalize_text(s: str) -> str:
    """比較用に空白を除き1文字以上にする"""
    if not s or not s.strip():
        return ""
    return re.sub(r"\s+", "", s.strip())


def get_text_in_top_portion(detections: list, img_height: int, top_ratio: float = 0.25) -> str:
    """画像の上側（top_ratio まで）にあるテキストだけを結合して返す。スクロール時に商品名が途中で見える部分の認識用。"""
    top_y_max = img_height * top_ratio
    parts = []
    for (bbox, text, _) in detections:
        # bbox: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] の4点。上端は min(y1,y2,y3,y4)
        ys = [p[1] for p in bbox]
        if min(ys) < top_y_max and text.strip():
            parts.append(text.strip())
    return " ".join(parts) if parts else ""


def get_full_text(detections: list) -> str:
    """検出されたテキストをすべて結合"""
    return " ".join(t.strip() for (_, t, _) in detections if t.strip())


def extract_brand_from_text(full_text: str) -> str:
    """テキストから「ブランド」の後の値を抽出（項目：ブランド のスクショ用）"""
    full_text = full_text.replace("\n", " ")
    # 「ブランド」の直後や「：」の後にある値を取りたい
    for pattern in [
        r"ブランド[:\s：]*([^\s\d][^\n]*?)(?:\s{2,}|\d|$)",
        r"項目[:\s：]*ブランド[:\s：]*([^\s\d][^\n]*?)(?:\s{2,}|\d|$)",
        r"ブランド\s*[：:]\s*([^\s]+)",
    ]:
        m = re.search(pattern, full_text)
        if m:
            val = m.group(1).strip()
            # 長すぎる場合は最初の単語だけ（商品名が混ざらないように）
            if len(val) > 30:
                val = val[:30].strip()
            if val and val not in ("項目", "ブランド", "商品", "メルカリ"):
                return val
    return ""


def same_product_group(top_a: str, full_a: str, top_b: str, full_b: str, min_overlap: int = 3) -> bool:
    """2枚の画像が同一商品かどうか。上側テキストがもう一方の全文に含まれる、または十分な重なりがあれば True。"""
    na = normalize_text(top_a)
    nb = normalize_text(top_b)
    fa = normalize_text(full_a)
    fb = normalize_text(full_b)
    if len(na) < min_overlap and len(nb) < min_overlap:
        return False
    if na and na in fb:
        return True
    if nb and nb in fa:
        return True
    # 共通部分が min_overlap 文字以上あれば同一とみなす
    for i in range(len(na) - min_overlap + 1):
        sub = na[i : i + min_overlap]
        if len(sub) >= min_overlap and sub in fb:
            return True
    for i in range(len(nb) - min_overlap + 1):
        sub = nb[i : i + min_overlap]
        if len(sub) >= min_overlap and sub in fa:
            return True
    return False


def main():
    try:
        import easyocr
    except ImportError:
        print("easyocr が入っていません。次のコマンドでインストールしてください:")
        print("  pip install easyocr")
        return 1

    INPUT_DIR.mkdir(exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)

    image_paths = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        image_paths.extend(INPUT_DIR.glob(ext))
    image_paths = sorted([p for p in image_paths if p.is_file()])

    if not image_paths:
        print(f"{INPUT_DIR} に画像がありません。スクショを置いてから再実行してください。")
        return 1

    print("OCR を読み込み中（初回はモデルダウンロードで時間がかかります）...")
    reader = easyocr.Reader(["ja"], gpu=False)

    # 各画像の OCR 結果と「上側テキスト」を取得
    # 日本語パス対策: PIL で読み numpy 配列にしてから EasyOCR に渡す（パスを OpenCV に渡すと文字化けするため）
    import numpy as np
    from PIL import Image

    image_results = []
    for path in image_paths:
        try:
            with Image.open(path) as pil_im:
                h = pil_im.height
                if pil_im.mode != "RGB":
                    pil_im = pil_im.convert("RGB")
                img_np = np.array(pil_im)
        except Exception as e:
            print(f"警告: {path.name} を読み飛ばします ({e})")
            continue
        detections = reader.readtext(img_np)
        top_text = get_text_in_top_portion(detections, h)
        full_text = get_full_text(detections)
        image_results.append({
            "path": path,
            "top_text": top_text,
            "full_text": full_text,
            "brand": extract_brand_from_text(full_text),
        })

    # 同一商品でグループ化（上側テキストの一致で判定）
    n = len(image_results)
    parent = list(range(n))

    def find(x):
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if same_product_group(
                image_results[i]["top_text"],
                image_results[i]["full_text"],
                image_results[j]["top_text"],
                image_results[j]["full_text"],
            ):
                union(i, j)

    groups = {}
    for i in range(n):
        root = find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(i)

    # 既存の data.json から最大 id を取得して新規 id の連番に使う
    next_id_num = 1
    if DATA_JSON.exists():
        try:
            with open(DATA_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                mid = item.get("id", "")
                m = re.match(r"^.*?(\d+)$", mid)
                if m:
                    next_id_num = max(next_id_num, int(m.group(1)) + 1)
        except Exception:
            pass

    today = date.today().isoformat()
    suggested = []
    for root, indices in groups.items():
        indices = sorted(indices)
        # ブランド: 「ブランド」が含まれる画像から抽出。なければ「その他」
        brand = "その他"
        product_name = ""
        for idx in indices:
            r = image_results[idx]
            if r["brand"]:
                brand = r["brand"]
            # 商品名: 上側テキストが一番長い画像の全文（または上側）を商品名候補に
            if len(r["top_text"]) > len(product_name):
                product_name = r["top_text"] or r["full_text"][:50]
        if not product_name:
            product_name = "（商品名を編集してください）"

        product_id = f"product-{next_id_num:03d}"
        next_id_num += 1
        image_names = []
        for k, idx in enumerate(indices, 1):
            src = image_results[idx]["path"]
            ext = src.suffix.lower()
            dest_name = f"{product_id}_{k}{ext}"
            dest = IMAGES_DIR / dest_name
            shutil.copy2(src, dest)
            image_names.append(f"images/{dest_name}")

        suggested.append({
            "id": product_id,
            "brand": brand,
            "product_name": product_name.strip()[:100],
            "price": 0,
            "images": image_names,
            "screenshot_count": len(image_names),
            "created_at": today,
        })

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(suggested, f, ensure_ascii=False, indent=2)

    print(f"\n処理完了: {len(groups)} 商品にグループ化しました。")
    print(f"  - 結果: {OUTPUT_JSON}")
    print(f"  - コピーした画像: {IMAGES_DIR}")
    print("\n次のステップ:")
    print("  1. suggested_products.json を開き、商品名・ブランドを必要に応じて修正")
    print("  2. data/data.json の [ ] 内に、suggested_products.json の内容をコピーして追記")
    print("  3. git add → commit → push でサイトを更新")
    return 0


if __name__ == "__main__":
    exit(main())
