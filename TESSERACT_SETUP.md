# Tesseract のインストール後設定

インストール中に「Add to PATH」や「Japanese」の選択が出なかった場合の対処です。

---

## 1. PATH を通す（必須ではない）

スクリプトは **よくあるインストール先**（`C:\Program Files\Tesseract-OCR` など）を自動で探すので、PATH が通っていなくても動くことがあります。

それでも「tesseract が見つからない」と出る場合は、手動で PATH を追加します。

### まず「tesseract.exe の本当の場所」を確認する

1. **エクスプローラーで検索**  
   - スタートメニュー横の検索ボックスに **tesseract.exe** と入力。  
   - または、エクスプローラーで **C:\** を開き、右上の検索欄に **tesseract.exe** と入力。  
   - 見つかった **tesseract.exe** を右クリック → **ファイルの場所を開く**。  
   - アドレス欄に表示されているパス（例: `C:\Program Files\Tesseract-OCR`）が **PATH に追加するフォルダ**です。**tesseract.exe が入っているそのフォルダ**を追加してください（例: `C:\Program Files\Tesseract-OCR`。末尾に `\tesseract.exe` は付けない）。

2. **環境変数を開く**  
   - スタートメニューで「環境変数」と検索 → **システムの環境変数を編集** を開く。  
   - または **設定 → システム → バージョン情報 → システムの詳細設定 → 環境変数**。

3. **Path に追加**  
   - **ユーザー環境変数** の **Path** を選び **編集**。  
   - **新規** で、手順 1 でメモしたフォルダのパスを**そのまま**貼り付ける（余計なスペースや `\tesseract.exe` を付けない）。  
   - **OK** で閉じる。開いていた「環境変数」のウィンドウも **OK** で閉じる。

4. **必ずターミナルを閉じて、新しく PowerShell を開き直す**。  
   その後、次を実行:
   ```powershell
   tesseract --version
   ```

### PATH を通してもバージョンが出ないとき

- **追加したパスが「tesseract.exe があるフォルダ」になっているか** もう一度確認（例: `C:\Program Files\Tesseract-OCR`）。  
  `C:\Program Files\Tesseract-OCR\tesseract.exe` のように **ファイル名まで入れるとダメ**です。**フォルダだけ**にしてください。
- **ユーザー環境変数** の Path に追加した場合、**そのユーザーでログインした状態で、新しく開いた** PowerShell で試す。
- **PC を再起動**してから、もう一度 `tesseract --version` を試す。

**PATH が通らなくても**、tesseract.exe が `C:\Program Files\Tesseract-OCR` か `C:\Program Files (x86)\Tesseract-OCR` にあれば、**スクリプト（process_screenshots.py）はそのパスを自動で使います**。  
`tesseract --version` は出なくても、**python scripts/process_screenshots.py** を実行して動作するか試してみてください。

---

## 2. 日本語データを追加する（日本語を読ませたい場合）

インストール時に Japanese を選べなかった場合や、**tessdata フォルダがない**場合は、自分でフォルダを作って日本語データを入れます。

### tessdata フォルダがないとき

1. **Tesseract のフォルダを開く**  
   - エクスプローラーで **tesseract.exe** を検索し、**ファイルの場所を開く**。  
   - 表示されたフォルダ（例: `C:\Program Files\Tesseract-OCR`）を開く。

2. **tessdata フォルダを作る**  
   - そのフォルダの中に、**tessdata** という名前の**新しいフォルダ**を作成する。  
   - フルパスは例: `C:\Program Files\Tesseract-OCR\tessdata`

3. **jpn.traineddata をダウンロード**  
   - ブラウザで次の URL を開く:  
     **https://github.com/tesseract-ocr/tessdata/raw/main/jpn.traineddata**  
   - 右クリック → **名前を付けてリンク先を保存**（または「保存」）で、**jpn.traineddata** という名前で保存（保存場所はどこでもよい）。

4. **tessdata にコピー**  
   - ダウンロードした **jpn.traineddata** を、手順 2 で作った **tessdata** フォルダの中にコピー（または移動）する。

5. **eng.traineddata も入れる（英語用）**  
   - 同じく **https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata** を開いてダウンロードし、**tessdata** フォルダに入れる。  
   - スクリプトは `jpn+eng` で読むので、両方あると安心です。

6. これで `lang=jpn+eng` で日本語＋英語が読めるようになります。

---

## まとめ

- **PATH** … スクリプトが自動で `C:\Program Files\Tesseract-OCR` などを探すので、通さなくても動くことが多い。エラーになったら上記のとおり PATH を追加。
- **日本語** … `tessdata` に **jpn.traineddata** を入れれば、インストール時に Japanese を選ばなくても日本語 OCR が使える。
