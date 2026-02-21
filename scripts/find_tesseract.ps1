# Tesseract のインストール場所を探す
# 使い方: プロジェクトフォルダで PowerShell を開き:
#   .\scripts\find_tesseract.ps1

$paths = @(
    "C:\Program Files\Tesseract-OCR\tesseract.exe",
    "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "$env:LOCALAPPDATA\Programs\Tesseract-OCR\tesseract.exe",
    "$env:ProgramFiles\Tesseract-OCR\tesseract.exe"
)

Write-Host "--- よくある場所を確認 ---"
foreach ($p in $paths) {
    if (Test-Path $p) {
        Write-Host "[見つかった] $p"
        $dir = Split-Path $p -Parent
        Write-Host "  → PATH に追加するフォルダ: $dir"
    } else {
        Write-Host "[なし] $p"
    }
}
