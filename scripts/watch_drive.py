# -*- coding: utf-8 -*-
"""
Google Drive 等のフォルダを監視し、新規画像が追加されたら OCR を実行して data.json に自動追加する。
watchdog 使用。新規ファイルのみ処理し、処理済みは processed/ へ移動。エラー時は failed/ へ。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_watch_config() -> dict:
    """watch_config.json を読み込む。"""
    config_path = PROJECT_ROOT / "watch_config.json"
    default = {
        "watch_folder": "",
        "data_json": "data/data.json",
        "images_dir": "images",
        "processed_dir": "processed",
        "failed_dir": "failed",
    }
    if not config_path.exists():
        logger.warning("watch_config.json が見つかりません。デフォルトを使用します。")
        return default
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k in default:
            if k in data and data[k]:
                default[k] = data[k]
    except Exception as e:
        logger.error("watch_config.json の読み込みに失敗しました: %s", e)
    return default


def get_next_product_id(data_json_path: Path) -> str:
    """data.json から既存の product-XXX の最大番号を取得し、次の id を返す。"""
    if not data_json_path.exists():
        return "product-001"
    try:
        with open(data_json_path, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception:
        return "product-001"
    if not isinstance(items, list):
        return "product-001"
    max_num = 0
    for item in items:
        mid = item.get("id", "")
        m = re.match(r"^.*?(\d+)$", mid)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"product-{max_num + 1:03d}"


def process_new_image(
    image_path: Path,
    config: dict,
) -> bool:
    """
    新規画像 1 枚を処理: OCR → images/ にコピー → data.json に追記 → 元ファイルを processed/ へ移動。
    失敗時は failed/ へ移動して False を返す。
    """
    watch_folder = Path(config["watch_folder"])
    data_json_path = PROJECT_ROOT / config["data_json"]
    images_dir = PROJECT_ROOT / config["images_dir"]
    processed_dir = Path(config["processed_dir"])
    failed_dir = Path(config["failed_dir"])

    # 相対パスの場合はプロジェクトルート基準
    if not processed_dir.is_absolute():
        processed_dir = PROJECT_ROOT / processed_dir
    if not failed_dir.is_absolute():
        failed_dir = PROJECT_ROOT / failed_dir

    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    try:
        # mercari_ocr を呼び出し
        try:
            from scripts import mercari_ocr
        except ImportError:
            import mercari_ocr
        config_path = PROJECT_ROOT / "screenshot_config.json"
        result = mercari_ocr.extract_from_image(image_path, config_path)
        brand = (result.get("brand") or "").strip() or "その他"
        product_name = (result.get("product_name") or "").strip() or "（商品名を編集してください）"

        # 次の id を取得
        product_id = get_next_product_id(data_json_path)
        ext = image_path.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp"):
            ext = ".png"
        image_filename = f"{product_id}_1{ext}"
        dest_image = images_dir / image_filename
        shutil.copy2(image_path, dest_image)
        image_ref = f"images/{image_filename}"

        # data.json に追記
        new_item = {
            "id": product_id,
            "brand": brand,
            "product_name": product_name,
            "price": 0,
            "images": [image_ref],
            "screenshot_count": 1,
            "created_at": date.today().isoformat(),
        }
        if data_json_path.exists():
            try:
                with open(data_json_path, "r", encoding="utf-8") as f:
                    data_list = json.load(f)
            except Exception as e:
                logger.error("data.json の読み込みに失敗: %s", e)
                raise
            if not isinstance(data_list, list):
                data_list = []
        else:
            data_list = []
        data_list.append(new_item)
        with open(data_json_path, "w", encoding="utf-8") as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)

        logger.info("追加しました: id=%s brand=%s product_name=%s", product_id, brand, product_name[:30])

        # 処理済みフォルダへ移動（別ドライブの場合はコピー後に削除）
        dest_processed = processed_dir / image_path.name
        if dest_processed.exists():
            dest_processed = processed_dir / f"{image_path.stem}_{int(time.time())}{image_path.suffix}"
        try:
            shutil.move(str(image_path), str(dest_processed))
        except OSError:
            shutil.copy2(str(image_path), str(dest_processed))
            image_path.unlink(missing_ok=True)
        logger.info("処理済みへ移動: %s", dest_processed.name)
        return True

    except Exception as e:
        logger.exception("処理中にエラー: %s", e)
        try:
            dest_failed = failed_dir / image_path.name
            if dest_failed.exists():
                dest_failed = failed_dir / f"{image_path.stem}_{int(time.time())}{image_path.suffix}"
            try:
                shutil.move(str(image_path), str(dest_failed))
            except OSError:
                shutil.copy2(str(image_path), str(dest_failed))
                image_path.unlink(missing_ok=True)
            logger.info("失敗したファイルを failed へ移動: %s", dest_failed.name)
        except Exception as move_err:
            logger.error("failed への移動に失敗: %s", move_err)
        return False


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in (".png", ".jpg", ".jpeg")


class NewImageHandler:
    """新規ファイルのみ処理する watchdog ハンドラ。"""

    def __init__(self, config: dict):
        self.config = config
        self._processed_paths: set[str] = set()

    def _handle_file(self, src_path: str) -> None:
        """1 ファイルを処理（作成・変更どちらからでも共通）。"""
        path = Path(src_path)
        if not path.is_file() or not is_image_file(path):
            return
        key = str(path.resolve())
        if key in self._processed_paths:
            return
        self._processed_paths.add(key)
        # 同期ドライブではファイルがまだ書き込み中のことがあるので待つ
        time.sleep(2)
        if not path.exists():
            self._processed_paths.discard(key)
            return
        try:
            process_new_image(path, self.config)
        finally:
            self._processed_paths.discard(key)

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_file(event.src_path)

    def on_modified(self, event):
        """Google Drive 等では「新規追加」が modified で来ることがあるため、変更も監視する。"""
        if event.is_directory:
            return
        self._handle_file(event.src_path)


def main():
    config = load_watch_config()
    watch_folder = Path(config["watch_folder"]).resolve()
    if not watch_folder or not watch_folder.exists():
        logger.error("監視フォルダが存在しません: %s", config["watch_folder"])
        logger.info("watch_config.json の watch_folder を Google Drive 内のフォルダパスに設定してください。")
        return 1
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        logger.error("watchdog がインストールされていません。pip install watchdog を実行してください。")
        return 1

    class Handler(FileSystemEventHandler):
        def __init__(self, config: dict):
            self._handler = NewImageHandler(config)

        def on_created(self, event):
            self._handler.on_created(event)

        def on_modified(self, event):
            self._handler.on_modified(event)

    observer = Observer()
    handler = Handler(config)
    observer.schedule(handler, str(watch_folder), recursive=False)
    observer.start()
    logger.info("監視を開始しました: %s (.png / .jpg の新規追加のみ処理)", watch_folder)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    return 0


if __name__ == "__main__":
    sys.exit(main())
