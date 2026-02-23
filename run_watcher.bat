@echo off
chcp 65001 >nul
title Mercari OCR フォルダ監視
cd /d "%~dp0"

echo 監視を開始します。終了するにはこのウィンドウを閉じるか Ctrl+C を押してください。
echo.

python -u scripts\watch_drive.py
if errorlevel 1 (
  echo.
  echo エラーで終了しました。watchdog のインストール: pip install watchdog
  pause
)
