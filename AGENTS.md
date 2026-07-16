# AIモデル・リーダーボード検索アプリ

## 変更してはいけないファイル

- `.htaccess` と `index.cgi` は、Keio のCGI環境でFlaskを起動・URLを振り分けるための設定である。
- これらのファイルは**一切変更しない**。内容、削除、整形、パーミッション変更を含む。

## 実行・配置

- アプリ本体は `app.py`、SQLiteデータベースは `leaderboard.db` を使用する。
- 本番配置に必要なものは `app.py`、`index.cgi`、`.htaccess`、`leaderboard.db`、`templates/`、`static/` である。
- `dataset/` と `build_leaderboard_db.py` はDB再構築用であり、通常の本番実行には不要である。
- `app.py` と `index.cgi`、ディレクトリは `755`、それ以外の通常ファイルは `644` とする。

## データモデル

- 使用テーブルは `organizations`、`licenses`、`models`、`arenas`、`leaderboard_results`。
- `leaderboard_result_view` は、結果・モデル・組織・ライセンス・Arenaを結合するビューである。
- 組織LeaderboardとライセンスLeaderboardの集計には、必ず `leaderboard_result_view` を使用する。
- `leaderboard_results` には、検索高速化のため次の複合インデックスを持たせる。

  ```sql
  CREATE INDEX idx_results_filter
  ON leaderboard_results(arena_id, category, leaderboard_publish_date);
  ```

- DBを再構築する場合も、`build_leaderboard_db.py` でこのインデックスを作成する。
- データ対象は rating を持つ14 Arenaである。agent系データは `score` ベースでスキーマが異なるため対象外とする。

## 画面と機能

### Leaderboard: `/`

- モデル名、Arena、組織、ライセンス、カテゴリ、公開日で評価結果を絞り込む。
- キーワード検索対象はモデル名のみ。
- Arenaはプルダウンではなく、Chat / Code / Image / Video のホバーメニューで選ぶ。
- Style Control対応Arenaはトグルで通常版・Style Control版を切り替える。
- 初期条件は `text` / `overall` / 最新公開日。組織・ライセンスは未指定とする。
- `overall` はカテゴリ候補の先頭に表示する。
- 表示列は順位、Rank Spread、モデル名、Arena、組織、ライセンス、レート、レート範囲、投票数。
- 初期並びはレート降順。レート・投票数の見出しで昇順／降順を切り替える。一度に有効な並び替え列は1つだけ。
- Rank Spreadは `rating_lower` と `rating_upper` から最良順位・最悪順位を算出して表示する。
- 1ページ50件。前後移動、ページ番号、省略記号からのページ指定を提供する。
- 検索、並び替え、ページ移動、リセットは非同期で結果表を更新し、URLも `history.pushState` で更新する。
- 結果更新中はレコード数の右に `LOADING` スピナーを表示する。
- `/api/leaderboard` はLeaderboardの結果表HTMLと正規化済みフィルター値をJSONで返す。

### 組織Leaderboard: `/organizations`

- Arena、カテゴリ、公開日で組織別の集計を絞り込む。
- 組織ごとに掲載モデル数、平均レート、最高レートを表示する。
- 3つの集計列の見出しで昇順／降順を切り替える。評価指標のプルダウンは設けない。
- 行内の開閉UIで、その組織のモデル一覧をレート降順で表示する。
- 並び替え・ページ移動は非同期更新し、`LOADING` スピナーを表示する。

### ライセンスLeaderboard: `/licenses`

- Arena、カテゴリ、公開日でライセンス別の集計を絞り込む。
- ライセンスごとに掲載モデル数、平均レート、最高レートを表示する。
- 3つの集計列の見出しで昇順／降順を切り替える。
- 行内の開閉UIで、そのライセンスのモデル一覧をレート降順で表示する。
- 並び替え・ページ移動は非同期更新し、`LOADING` スピナーを表示する。

### 詳細URL

- `/organizations/<organization_id>`：組織の基本情報、集計、評価結果。
- `/licenses/<license_id>`：ライセンスに対応するモデル一覧。

## 実装ルール

- 検索条件はGETパラメータを使用し、URL共有・再読み込みで同じ状態を再現できるようにする。
- SQLの値は必ず `?` プレースホルダで渡す。
- `ORDER BY` の列・方向は、アプリ側で許可したホワイトリストから選択する。ユーザー入力をそのままSQL文字列へ連結しない。
- データ参照専用とし、Webアプリから `INSERT`、`UPDATE`、`DELETE` を実行しない。
- 該当データがない場合は、サーバーエラーではなく「該当するデータはありません」と表示する。
- `templates/` にJinjaテンプレート、`static/css/style.css` にCSS、`static/js/app.js` にJavaScriptを配置する。
- 非同期処理はURLの絶対パスに依存させない。`https://user.keio.ac.jp/~USER/dm_app/` のようなサブディレクトリ配置でも動作させる。
