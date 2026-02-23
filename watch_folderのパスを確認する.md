# 「監視フォルダが存在しません」のとき

## 正しいパスを確認する手順

1. **エクスプローラー**を開く（Win + E）。
2. 左の一覧で **「PC」**（または「このPC」）をクリック。
3. **Google Drive** のドライブ（例: **G:**）をダブルクリックして開く。  
   ※ G: がなければ、表示されているドライブ名を開く。
4. 中にある **「マイドライブ」** または **「My Drive」** をダブルクリック。
5. **MercariScreenshots** というフォルダがなければ、**右クリック → 新規作成 → フォルダー** で作成し、名前を **MercariScreenshots** にする。そのフォルダを開く。
6. 画面上部の **アドレスバー**（パスが表示されている欄）を **クリック** するとパスが選択されるので、**Ctrl+C** でコピー。  
   例: `G:\My Drive\MercariScreenshots` や `G:\マイドライブ\MercariScreenshots`
7. プロジェクトフォルダ内の **watch_config.json** をメモ帳などで開く。
8. **watch_folder** の値に、コピーしたパスを貼り付ける。  
   **注意:** バックスラッシュ `\` は **2つ** ずつ書く。  
   - 例: コピーしたパスが `G:\My Drive\MercariScreenshots` なら  
     `"watch_folder":"G:\\My Drive\\MercariScreenshots"` と書く。
9. 保存してから、もう一度 **run_watcher.bat** を実行する。

## よくあるパス

- 英語表示: `G:\My Drive\MercariScreenshots`
- 日本語表示: `G:\マイドライブ\MercariScreenshots`
- ドライブレター（G:）は PC によって **H:** や別の文字になっていることがあります。エクスプローラーで表示されているものをそのまま使ってください。
