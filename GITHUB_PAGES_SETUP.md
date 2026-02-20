# GitHub にプッシュして GitHub Pages で公開する手順

## 前提

- GitHub のアカウントを持っていること
- プロジェクトフォルダ: `c:\Users\akiko\OneDrive\デスクトップ\apparel-db`

---

## ステップ1: Git の初回設定（一度だけやればOK）

Git をまだ使ったことがない場合、名前とメールを登録します。

1. **ターミナルを開く**
   - Cursor なら: メニュー **ターミナル** → **新しいターミナル**
   - または `` Ctrl+` ``（バッククォート）

2. **次の2つを実行**（`あなたの名前` と `your@email.com` は自分のものに変える）

   ```bash
   git config --global user.name "あなたの名前"
   git config --global user.email "your@email.com"
   ```

   ※ GitHub に登録したメールアドレスを使うと分かりやすいです。

---

## ステップ2: プロジェクトフォルダに移動

ターミナルで、apparel-db のフォルダに移動します。

```bash
cd "c:\Users\akiko\OneDrive\デスクトップ\apparel-db"
```

成功すると、プロンプトの前にパスが `...\apparel-db` のようになります。

---

## ステップ3: Git リポジトリを初期化して初回コミット

### 3-1. リポジトリを初期化

```bash
git init
```

表示例: `Initialized empty Git repository in .../apparel-db/.git/`

### 3-2. すべてのファイルをステージング（追加）

```bash
git add .
```

`.` は「このフォルダの中の変更すべて」という意味です。エラーが出なければOKです。

### 3-3. 初回コミット

```bash
git commit -m "Initial: static apparel DB site"
```

表示例: `[main (または master) xxxxxxx] Initial: static apparel DB site  X files changed...`

ここまでで、ローカルで Git の履歴が1つできた状態です。

---

## ステップ4: GitHub で新しいリポジトリを作成

ここは **ブラウザで GitHub のサイト** を操作します。

1. **GitHub にログイン**  
   https://github.com を開き、ログインする。

2. **新規リポジトリ作成**
   - 画面右上の **「+」** → **「New repository」** をクリック。

3. **設定を入力**
   - **Repository name**: `apparel-db`（ほかの名前でもOK。あとで `git remote` のURLを合わせる）
   - **Description**: 空欄でOK。例: `Static apparel database site`
   - **Public** を選択。
   - **「Add a README file」」「Add .gitignore」などはチェックしない**（ローカルにすでにファイルがあるため）。
   - **「Create repository」** をクリック。

4. **作成後の画面**
   - 「…or push an existing repository from the command line」という枠が出ます。
   - その中の **2行のコマンド** は、次のステップで使うので、URL だけメモしておくか、画面を開いたままにしておく。
   - リポジトリのURLは `https://github.com/あなたのユーザー名/apparel-db` のような形です。

---

## ステップ5: リモートを追加してプッシュ

GitHub の「場所」を登録して、そこにコードを送ります。

1. **ターミナルは、まだ `apparel-db` フォルダにいる状態で**、以下を実行。

2. **リモートの追加**  
   `あなたのユーザー名` の部分を、自分の GitHub ユーザー名に置き換えて実行。

   ```bash
   git remote add origin https://github.com/あなたのユーザー名/apparel-db.git
   ```

   ※ リポジトリ名を `apparel-db` 以外にした場合は、`.git` の前も同じ名前にする。

3. **ブランチ名を main にする**（Git のバージョンによっては最初から main の場合はそのまま）

   ```bash
   git branch -M main
   ```

4. **プッシュ（GitHub に送る）**

   ```bash
   git push -u origin main
   ```

5. **認証を求められた場合**
   - **Username**: GitHub のユーザー名
   - **Password**: ここでは **パスワードではなく「Personal Access Token (PAT)」** を入力する必要があります。
   - Token を持っていない場合:
     1. GitHub → 右上のアイコン → **Settings**
     2. 左メニュー一番下 **Developer settings** → **Personal access tokens** → **Tokens (classic)**
     3. **Generate new token (classic)** で、メモを付けて発行。スコープで **repo** にチェック。
     4. 表示されたトークンをコピーし、パスワードの代わりに貼り付ける。
   - 成功すると、`Enumerating objects...` のあと `main -> main` のような表示が出て、GitHub のリポジトリにファイルが反映されます。

---

## ステップ6: GitHub Pages を有効にする

1. **リポジトリのページを開く**  
   `https://github.com/あなたのユーザー名/apparel-db`

2. **Settings を開く**
   - リポジトリ上部の **「Settings」** タブをクリック。

3. **Pages の設定**
   - 左メニューで **「Pages」** をクリック。

4. **Build and deployment**
   - **Source**: **「Deploy from a branch」** を選ぶ。
   - **Branch**: ドロップダウンで **「main」**（または master）を選び、フォルダは **「/ (root)」** のまま。
   - **Save** をクリック。

5. **反映を待つ**
   - 画面上部に「Your site is live at https://あなたのユーザー名.github.io/apparel-db/」のような表示が出るまで、1〜2分かかることがあります。
   - 出たらそのURLをクリックして、サイトが表示されるか確認する。

---

## まとめチェックリスト

- [ ] `git config` で名前・メールを設定した
- [ ] `cd` で apparel-db に移動した
- [ ] `git init` → `git add .` → `git commit` で初回コミットした
- [ ] GitHub で新しいリポジトリ（apparel-db）を作成した（README 等は追加しない）
- [ ] `git remote add origin ...` でリモートを追加した
- [ ] `git push -u origin main` でプッシュした（必要なら PAT で認証）
- [ ] Settings → Pages で「Deploy from a branch」・main を選んで保存した
- [ ] 表示された URL でサイトが開けることを確認した

---

## よくあること

- **プッシュで 403 / 認証エラー**  
  → パスワード欄には **Personal Access Token** を入力する。

- **サイトが 404**  
  → Pages の Source が「Deploy from a branch」で、Branch が main（または master）になっているか確認。数分待ってから再度アクセス。

- **あとから変更を反映したい**  
  同じフォルダで編集後、次を実行:
  ```bash
  git add .
  git commit -m "説明メッセージ"
  git push
  ```
