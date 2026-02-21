#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# OpenMP の二重読み込みエラーを避ける（EasyOCR/PyTorch 利用時）
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

"""
スクリーンショットを処理し、ブランド・メルカリタイトル（商品名）を読み取る。

使い方:
  1. スクショを screenshots_input/ に置く（タイトルが写っているもの + 下にスクロールして「項目：ブランド」が写っているもの）
  2. python scripts/process_screenshots.py を実行
  3. 同一商品は「画面上部に途中まで見えるテキスト」が一致するものとしてグループ化
  4. 「ブランド」が含まれる画像からブランド名を抽出（そのスクショはサイトには載せない）
  5. メルカリタイトルをそのまま商品名として抜き出し、商品ごとに1件として出力（ブランドの下に商品がぶら下がる形）
  6. 結果は suggested_products.json に出力。画像は images/ にコピーされる

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
CONFIG_JSON = PROJECT_ROOT / "screenshot_config.json"

# 座標固定用ゾーン（screenshot_config.json があれば上書き。割合は 0〜1）
def _load_zone_config() -> dict:
    out = {}
    if not CONFIG_JSON.exists():
        return out
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in ("brand_zone", "product_name_zone"):
            z = data.get(key)
            if z and isinstance(z, dict):
                out[key] = {
                    "y_min": float(z.get("y_min", 0)),
                    "y_max": float(z.get("y_max", 1)),
                    "x_min": float(z.get("x_min", 0)),
                    "x_max": float(z.get("x_max", 1)),
                }
    except Exception:
        pass
    return out


def _config_use_mercari_iphone_ocr() -> bool:
    """screenshot_config.json で use_mercari_iphone_ocr または ocr_engine: tesseract なら True"""
    if not CONFIG_JSON.exists():
        return False
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("use_mercari_iphone_ocr") is True:
            return True
        if data.get("ocr_engine") == "tesseract":
            return True
        return False
    except Exception:
        return False


ZONE_CONFIG = _load_zone_config()

# 「ブランド」の右隣・直下に来る「値」として扱わないラベル（メルカリの項目名のみ除外し、それ以外はすべてブランド名として採用）
BRAND_VALUE_EXCLUDE = (
    "項目", "ブランド", "商品", "メルカリ", "出品者", "カテゴリ", "カテゴリー",
    "送料", "商品の説明", "カード", "フォロー", "コメント", "共有",
)
# ブランド値として明らかに不正なフレーズ（含んでいたら採用しない）
BRAND_INVALID_CONTAINS = (
    "商品の状態", "配送料の負担", "配送の方法", "発送までの日数", "配送元の地域",
    "らくらくメルカリ", "匿名配送", "内容をコピー", "値下げ依頼", "ご遠慮",
)


def normalize_text(s: str) -> str:
    """比較用に空白を除き1文字以上にする"""
    if not s or not s.strip():
        return ""
    return re.sub(r"\s+", "", s.strip())


def _is_valid_brand(s: str) -> bool:
    """ブランド名として採用してよいか。UI文言・説明文が混ざっていれば False"""
    if not s or len(s) > 40:
        return False
    t = s.strip()
    if any(inv in t for inv in BRAND_INVALID_CONTAINS):
        return False
    if any(ex in t for ex in ("商品の状態", "配送料", "負担", "発送", "地域", "カテゴリ")):
        return False
    return True


def _brand_between_dots(s: str) -> str:
    """
    「L・JACOB COHEN・目立った傷や汚れなし」のような行から、
    1番目と2番目の ・（中黒）の間の文字列をブランド名として返す。
    ・が2個以上なければそのまま strip して返す。
    """
    t = (s or "").strip()
    parts = t.split("・")
    if len(parts) >= 3:
        return parts[1].strip()[:40]
    return t[:40]


def get_text_in_top_portion(detections: list, img_height: int, top_ratio: float = 0.35) -> str:
    """画像の上側（top_ratio まで）にあるテキストだけを結合して返す。メルカリタイトル・スクロール時の商品名認識用。"""
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


def _bbox_height(bbox: list) -> float:
    """bbox の高さを返す（フォントサイズの目安）"""
    ys = [p[1] for p in bbox]
    return max(ys) - min(ys)


# 商品名として明らかに不正（説明文・UIが混ざった結果＝ここで切る）
PRODUCT_NAME_INVALID_CONTAINS = (
    "商品の状態", "配送料の負担", "配送の方法", "発送までの日数", "配送元の地域",
    "らくらくメルカリ", "匿名配送", "内容をコピー", "値下げ依頼",
    "目立った傷や汚れ", "時間前", "送料込み", "日以内で売れた", "出品してみません",
)


def _looks_like_product_name(s: str) -> bool:
    """商品名らしい文字列か。説明文やOCRノイズなら False"""
    if not s or len(s) < 2:
        return False
    if any(inv in s for inv in PRODUCT_NAME_INVALID_CONTAINS):
        return False
    # 商品名によくある要素が含まれるか：【】・アルファベット/数字が3文字以上・サイズ/色
    if "【" in s or "】" in s:
        return True
    alnum = re.findall(r"[A-Za-z0-9]", s)
    if len(alnum) >= 3:
        return True
    if "サイズ" in s or "濃紺" in s or "ブラック" in s or "ホワイト" in s or "ネイビー" in s:
        return True
    # 誤検出の括弧・記号だらけで【】やアルファベットがほとんどない場合はノイズ
    if re.search(r"[』」']", s) and "】" not in s and "【" not in s and len(alnum) < 3:
        return False
    if len(s) <= 4:
        return False
    good = re.sub(r"[^A-Za-z0-9\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u0020\u00b7\u301c\u2014]", "", s)
    if len(good) < len(s) * 0.4:
        return False
    return True


# 商品名ゾーンから除外するラベル・UI文言（メルカリの項目名・状態説明など）
PRODUCT_NAME_ZONE_EXCLUDE = (
    "メルカリ", "送料", "お気に入り", "ブランド", "カテゴリ", "カテゴリー", "出品者", "商品の説明",
    "項目", "円", "￥", "フォロー", "コメント", "共有", "カード", "この商品",
    "目立った傷や汚れ", "傷や汚れなし", "時間前", "送料込み",
)
# 商品名として採用しないパターン（状態・補足行。「L ブランド・状態」など）
PRODUCT_NAME_LINE_EXCLUDE_PATTERNS = (
    "目立った傷", "傷や汚れ", "時間前", "送料込み", "なし」",
)


def get_product_name_zone_text(detections: list, img_height: int, img_width: int = 0) -> str:
    """
    メルカリの商品スクショで「商品画像の真下・ハートと吹き出しの真下」のテキストを抽出する。
    screenshot_config.json の product_name_zone があればその座標（割合0〜1）で固定。
    """
    zone = ZONE_CONFIG.get("product_name_zone")
    if zone and img_width > 0:
        y_min = img_height * zone["y_min"]
        y_max = img_height * zone["y_max"]
        x_min = img_width * zone["x_min"]
        x_max = img_width * zone["x_max"]
    else:
        y_min = img_height * 0.35
        y_max = img_height * 0.55
        x_min = 0
        x_max = img_width if img_width > 0 else 99999
    in_zone = []
    for (bbox, text, _) in detections:
        t = (text or "").strip()
        if not t or len(t) < 2:
            continue
        if any(ex in t for ex in PRODUCT_NAME_ZONE_EXCLUDE):
            continue
        if any(pat in t for pat in PRODUCT_NAME_LINE_EXCLUDE_PATTERNS):
            continue
        cx, cy = _bbox_center(bbox)
        if not (x_min <= cx <= x_max):
            continue
        if y_min <= cy <= y_max:
            h = _bbox_height(bbox)
            in_zone.append((cy, h, t))
    if not in_zone:
        return ""
    # フォントが大きい順→上から。商品名は大きいので上位を採用（状態説明は上記で除外済み）
    in_zone.sort(key=lambda x: (-x[1], x[0]))
    parts = []
    for (_, _, t) in in_zone[:4]:
        if not t:
            continue
        if any(ex in t for ex in PRODUCT_NAME_ZONE_EXCLUDE):
            continue
        if any(pat in t for pat in PRODUCT_NAME_LINE_EXCLUDE_PATTERNS):
            continue
        if any(inv in t for inv in ("時間前", "送料込み", "目立った傷")):
            break
        parts.append(t)
        if len(" ".join(parts)) > 90:
            break
    raw = " ".join(parts).strip()
    # 結合結果に状態説明が混ざっていたら、その手前までで切る（OCRが1ブロックにした場合の保険）
    for sep in ("目立った傷", "傷や汚れ", "時間前", "送料込み"):
        if sep in raw:
            raw = raw[: raw.find(sep)].strip()
            break
    return raw[:150]


def _bbox_center(bbox: list) -> tuple:
    """bbox の中心 (x, y) を返す。bbox は [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]"""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs) / 4, sum(ys) / 4)


def extract_brand_from_detections(detections: list, img_height: int, img_width: int) -> str:
    """
    メルカリの「ブランド」項目を、OCR の位置情報またはテキスト順で抽出する。
    screenshot_config.json の brand_zone があれば、その範囲内の検出だけを使う（座標固定）。
    """
    if not detections:
        return ""
    # 座標固定: brand_zone が設定されていれば、その範囲内の検出だけに絞る
    zone = ZONE_CONFIG.get("brand_zone")
    if zone and img_width > 0:
        y_min = img_height * zone["y_min"]
        y_max = img_height * zone["y_max"]
        x_min = img_width * zone["x_min"]
        x_max = img_width * zone["x_max"]
        filtered = []
        for (bbox, text, conf) in detections:
            cx, cy = _bbox_center(bbox)
            if x_min <= cx <= x_max and y_min <= cy <= y_max:
                filtered.append((bbox, text, conf))
        detections = filtered if filtered else detections
    full_text = get_full_text(detections)
    # 座標固定時: ゾーン内が「L・JACOB COHEN・目立った傷や汚れなし」のような1行なら、・と・の間を採用
    if zone and detections:
        cand = _brand_between_dots(full_text)
        if cand and _is_valid_brand(cand):
            return cand
    # まず「ブランド」を含む検出を探す
    brand_idx = None
    brand_cx = None
    brand_cy = None
    for i, (bbox, text, _) in enumerate(detections):
        t = (text or "").strip()
        if not t:
            continue
        if "ブランド" in t:
            brand_idx = i
            brand_cx, brand_cy = _bbox_center(bbox)
            break
    if brand_idx is not None:
        # 同じブロックに「ブランド」の直後テキストがあればそれを優先（例: "項目 ブランド JACOB COHEN"）
        _, brand_block_text, _ = detections[brand_idx]
        if brand_block_text:
            after = re.split(r"ブランド\s*[：:]?\s*", brand_block_text, 1)
            if len(after) > 1:
                rest = after[-1].strip()
                for stop in ("商品の状態", "配送料の負担", "配送の方法", "カテゴリ"):
                    if stop in rest:
                        rest = rest[: rest.find(stop)].strip()
                rest = re.split(r"\s*カテゴリ(?:ー)?\s*", rest)[0].strip()
                rest = re.split(r"\s{2,}", rest)[0].strip()
                cand = _brand_between_dots(rest)
                if cand and _is_valid_brand(cand):
                    return cand

        # 「ブランド」の右隣または直下のテキストをブランド名とする（アルファベット・カタカナ・漢字・数字いずれでも可）
        y_tolerance = img_height * 0.18
        candidates_same_line = []
        candidates_below = []
        for i, (bbox, text, _) in enumerate(detections):
            if i == brand_idx:
                continue
            t = (text or "").strip()
            if not t or len(t) > 50:
                continue
            if t in BRAND_VALUE_EXCLUDE or t.startswith("カテゴリ"):
                continue
            cx, cy = _bbox_center(bbox)
            if abs(cy - brand_cy) <= y_tolerance and cx > brand_cx:
                candidates_same_line.append((cx - brand_cx, t))
            elif cy > brand_cy and abs(cx - brand_cx) <= img_width * 0.5:
                candidates_below.append((cy - brand_cy, t))
        # 同一行は x 順に並べ、「カテゴリー」等の手前まで結合して1つのブランド名にする（"JACOB" "COHEN" → "JACOB COHEN"）
        if candidates_same_line:
            candidates_same_line.sort(key=lambda x: x[0])
            parts = []
            for (_, t) in candidates_same_line:
                if t in BRAND_VALUE_EXCLUDE or t.startswith("カテゴリ"):
                    break
                parts.append(t)
            if parts:
                cand = _brand_between_dots(" ".join(parts).strip())
                if cand and _is_valid_brand(cand):
                    return cand
        if candidates_below:
            candidates_below.sort(key=lambda x: x[0])
            parts = []
            for (_, t) in candidates_below:
                if t in BRAND_VALUE_EXCLUDE or t.startswith("カテゴリ"):
                    break
                parts.append(t)
            if parts:
                cand = _brand_between_dots(" ".join(parts).strip())
                if cand and _is_valid_brand(cand):
                    return cand
    return extract_brand_from_text(full_text)


def extract_brand_from_text(full_text: str) -> str:
    """
    「ブランド」の直後～次の項目（カテゴリー等）の手前までをブランド名として抽出する。
    OCRの検出順がバラバラでも、文中の「ブランド」をすべて試して有効な値を返す。
    """
    s = full_text.replace("\n", " ").replace("\r", " ")
    if "ブランド" not in s:
        return ""

    def take_brand_from_rest(rest: str) -> str:
        rest = re.sub(r"^[：:\s]+", "", rest[:60].strip())
        part = re.split(r"\s*カテゴリ(?:ー)?\s*", rest)[0].strip()
        part = re.split(r"\s{2,}|\d+円", part)[0].strip()
        for stop in ("ファッション", "メンズ", "レディース", "パンツ", "デニム", "シャツ", "スニーカー"):
            if stop in part:
                part = part[: part.find(stop)].strip()
        part = part[:40].strip()
        cand = _brand_between_dots(part)
        if cand and cand not in BRAND_VALUE_EXCLUDE and _is_valid_brand(cand):
            return cand
        # アルファベット2語だけ抜く（JACOB COHEN など）
        m = re.match(r"^([A-Za-z][A-Za-z0-9\s\-]+?)(?:\s|$|/|カテゴリ)", part)
        if m:
            val = _brand_between_dots(m.group(1).strip())
            if val and _is_valid_brand(val):
                return val
        return ""

    # 最初の「ブランド」の直後から取得
    idx = s.find("ブランド") + 3
    out = take_brand_from_rest(s[idx : idx + 80])
    if out:
        return out
    # 正規表現で「ブランド」直後のアルファベット塊を全文から検索（OCR順不同の保険）
    for m in re.finditer(r"ブランド\s*[：:]?\s*([A-Za-z][A-Za-z0-9\s・\-]+?)(?=\s+カテゴリ|\s{2,}|\s*/\s*ファッション|$)", s):
        val = _brand_between_dots(m.group(1).strip())
        if val and _is_valid_brand(val):
            return val
    # 文中のすべての「ブランド」位置を試す（検出順が前後している場合）
    start = 0
    while True:
        i = s.find("ブランド", start)
        if i < 0:
            break
        start = i + 1
        out = take_brand_from_rest(s[i + 3 : i + 85])
        if out:
            return out
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
    use_mercari_ocr = _config_use_mercari_iphone_ocr()
    if not use_mercari_ocr:
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

    image_results = []

    if use_mercari_ocr:
        # Region-based Tesseract OCR (Mercari iPhone: crop regions, preprocess, psm 6, jpn+eng)
        try:
            from scripts import mercari_ocr
        except ImportError:
            try:
                import mercari_ocr
            except ImportError:
                print("mercari_ocr を読み込めません。scripts/mercari_ocr.py と scripts/ocr_preprocess.py を確認してください。")
                return 1
        print("Mercari iPhone 用の領域OCR（Tesseract）で読み取ります...")
        for path in image_paths:
            try:
                result = mercari_ocr.extract_from_image(path, CONFIG_JSON)
            except Exception as e:
                print(f"警告: {path.name} を読み飛ばします ({e})")
                continue
            raw_product = (result.get("raw_product_text") or "")[:300]
            raw_brand = (result.get("raw_brand_text") or "")[:200]
            raw_price = (result.get("raw_price_text") or "")[:100]
            product_name_zone = (result.get("product_name") or "").strip()
            brand = (result.get("brand") or "").strip()
            image_results.append({
                "path": path,
                "top_text": raw_product[:200],
                "full_text": raw_product,
                "product_name_zone": product_name_zone,
                "brand": brand,
                "has_brand_label": False,
                "raw_brand_text": raw_brand,
                "raw_product_text": raw_product,
                "raw_price_text": raw_price,
            })
    else:
        # EasyOCR (従来)
        print("OCR を読み込み中（初回はモデルダウンロードで時間がかかります）...")
        reader = easyocr.Reader(["ja"], gpu=False)
        import numpy as np
        from PIL import Image
        for path in image_paths:
            try:
                with Image.open(path) as pil_im:
                    h, w = pil_im.height, pil_im.width
                    if pil_im.mode != "RGB":
                        pil_im = pil_im.convert("RGB")
                    img_np = np.array(pil_im)
            except Exception as e:
                print(f"警告: {path.name} を読み飛ばします ({e})")
                continue
            detections = reader.readtext(img_np)
            top_text = get_text_in_top_portion(detections, h)
            full_text = get_full_text(detections)
            product_name_zone = get_product_name_zone_text(detections, h, w)
            brand = extract_brand_from_detections(detections, h, w)
            if not brand:
                brand = extract_brand_from_text(full_text)
            has_brand = "ブランド" in full_text
            image_results.append({
                "path": path,
                "top_text": top_text,
                "full_text": full_text,
                "product_name_zone": product_name_zone,
                "brand": brand,
                "has_brand_label": has_brand,
            })

    # デバッグ: OCRで読み取った内容をファイルに保存（ブランド・商品名が取れないときに確認用）
    debug_path = PROJECT_ROOT / "ocr_debug.json"
    try:
        debug_data = [
            {
                "file": r["path"].name,
                "top_text": r["top_text"],
                "product_name_zone": r.get("product_name_zone", ""),
                "full_text": (r.get("full_text") or "")[:500],
                "brand_extracted": r["brand"],
                "has_brand_label": r["has_brand_label"],
                "raw_brand_text": r.get("raw_brand_text", ""),
                "raw_product_text": (r.get("raw_product_text") or "")[:500],
                "raw_price_text": r.get("raw_price_text", ""),
            }
            for r in image_results
        ]
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(debug_data, f, ensure_ascii=False, indent=2)
        print(f"  - デバッグ: {debug_path} に各画像のOCR結果を保存しました")
    except Exception as e:
        print(f"  - デバッグ保存スキップ: {e}")

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

    # メルカリタイトルを抜き出す（商品画像の真下・ハートと吹き出しの真下の大きい1〜2行を優先）
    def _trim_product_name_raw(t: str, max_len: int = 120) -> str:
        """説明文・UIが混ざっていたらその手前で切り、長すぎれば先頭だけ使う"""
        s = (t or "").strip()
        for inv in PRODUCT_NAME_INVALID_CONTAINS:
            if inv in s:
                s = s[: s.find(inv)].strip()
        # メルカリタイトルは【で始まることが多いので、【から始まる部分だけ使う
        if "【" in s:
            s = s[s.find("【"):].strip()
            for inv in PRODUCT_NAME_INVALID_CONTAINS:
                if inv in s:
                    s = s[: s.find(inv)].strip()
        if len(s) > max_len:
            s = s[:max_len].strip()
        return s

    def get_product_name_from_group(indices: list) -> str:
        title_candidates = [image_results[i] for i in indices if not image_results[i].get("has_brand_label")]
        if not title_candidates:
            return "（商品名を編集してください）"
        # まず「商品名ゾーン」（画像直下・アイコン直下の大きいテキスト）を使う
        best_zone = max(title_candidates, key=lambda r: len(r.get("product_name_zone") or ""))
        raw = (best_zone.get("product_name_zone") or "").strip()
        raw = _trim_product_name_raw(raw, max_len=100)
        if not raw or not _looks_like_product_name(raw):
            # ゾーンで取れない場合は top_text を優先（画面上部＝タイトル）、長い場合は先頭120文字で切ってからトリム
            best = max(title_candidates, key=lambda r: len(r.get("top_text") or ""))
            top = (best.get("top_text") or "").strip()
            full = (best.get("full_text") or "").strip()
            raw = (top or full).strip()
            raw = _trim_product_name_raw(raw, max_len=120)
        if not raw or not _looks_like_product_name(raw):
            return "（商品名を編集してください）"
        return re.sub(r"\s+", " ", raw)[:120]

    today = date.today().isoformat()
    suggested = []
    for root, indices in groups.items():
        indices = sorted(indices)
        brand = "その他"
        for idx in indices:
            r = image_results[idx]
            if r["brand"]:
                brand = r["brand"]
                break
        product_name = get_product_name_from_group(indices)
        display_indices = [i for i in indices if not image_results[i].get("has_brand_label")]
        if not display_indices:
            continue
        product_id = f"product-{next_id_num:03d}"
        next_id_num += 1
        image_names = []
        for k, idx in enumerate(display_indices, 1):
            src = image_results[idx]["path"]
            ext = src.suffix.lower()
            dest_name = f"{product_id}_{k}{ext}"
            dest = IMAGES_DIR / dest_name
            shutil.copy2(src, dest)
            image_names.append(f"images/{dest_name}")

        suggested.append({
            "id": product_id,
            "brand": brand,
            "product_name": product_name,
            "price": 0,
            "images": image_names,
            "screenshot_count": len(image_names),
            "created_at": today,
        })

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(suggested, f, ensure_ascii=False, indent=2)

    print(f"\n処理完了: {len(groups)} 商品にグループ化しました（ブランドごとに商品がぶら下がる形で出力）。")
    print(f"  - 結果: {OUTPUT_JSON}")
    print(f"  - コピーした画像: {IMAGES_DIR}")
    print("\n次のステップ:")
    print("  1. suggested_products.json を開き、商品名・ブランドを必要に応じて修正")
    print("  2. data/data.json の [ ] 内に、suggested_products.json の内容をコピーして追記")
    print("  3. git add → commit → push でサイトを更新")
    return 0


if __name__ == "__main__":
    exit(main())
