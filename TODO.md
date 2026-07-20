# 📋 TODO リスト

> **凡例**
> `- [ ]` 未完　／　`- [x]` 完了　／　🔄 進行中
>
> **編集のしかた**
> - 着手したら項目の頭に 🔄 を付ける（例：`- [ ] 🔄 ...`）
> - 終わったら `- [ ]` を `- [x]` に変えて「✅ 完了」へ移動
> - 1項目 = 「**タイトル** … 内容」で書くと揃ってきれい
>
> **使い方**：「次のTODOやって」「TODOの〇〇やって」で着手 → Claude が作業を可視化しながら進め、終わったら完了へ移動する（ルールは [CLAUDE.md](CLAUDE.md)）。

---

## 🔄 進行中

- [ ] 🔄 **fanza-content の写真を厳選する仕組み**
  X 的に OK な写真だけを源泉から選ぶ。`ナレッジ/規制・安全/` の規制ラインを見ながら自動で絞る。
- [ ] 🔄 **運用法の資料化**
  日々の運用を「誰が見ても理解できる」レベルで資料化（`ナレッジ/`・`ロードマップ/` で整備中）。

---

## ⬜ これからやる

### fanza-content ダッシュボード

- [ ] **画像「コピー」ボタン → X で貼り付け**（D&D調査の結論を受けた実装）
  各画像に「📋画像コピー」を追加し、X の投稿欄に Cmd+V で貼り付けできるように（`ClipboardItem`／PNG・localhost前提）。
  動画は「保存」→ Finder からドラッグの運用で割り切る。詳細は `fanza_auto/メモ_HTMLからXへの投稿方法（DnD調査）.md`。

---

## ✅ 完了

- [x] **1作品だけを動画つきで開くモード（再生・切り抜き・保存）**
  `build_board.py <cid>` で単一作品ボード `works/board_<cid>.html` を生成（動画プレーヤー＋切り抜き
  ツールバー＋保存ボタン＋既存 `cut_*.mp4` 一覧）。`serve_board.py <cid>` が単一ボードを生成→works/配信
  （動画シーク＝Rangeリクエスト対応）→ブラウザで開き、「✂切り抜く」を `/__cut`→`cut_video.py` で処理して
  `cut_<開始>-<終了>.mp4` を保存。パス外アクセス防止・BrokenPipe無視。自動テストで配信200・動画206・
  切り抜き成功・パス外拒否を確認。README/SKILL.md 更新。
- [x] **投稿ボードを刷新（テキスト専用・作品情報を読み込む新ボード）**
  旧ダッシュボード（`serve.py`／`make_post_html.py`／`works/index.html`）を `fanza_auto/_archive/board_v1/` に
  動く状態でアーカイブ（パス定数のみ修正・py_compile確認）。画像の切り抜き・A/B判定は今も旧ボード担当。
  新規に4スクリプト：`common.py`（設定・リンク整形・works走査の共通土台）／`meta.py`（cidから作品情報を
  取り直し `item.json` 保存。既存41作品backfill済み）／`post_text.py`（レビュー評価・収録時間・発売日・
  安全ジャンルから作品ごとに投稿文を1本生成。型を自動選択）／`build_board.py`（`works/board.html` 生成・
  サーバー不要・コピーボタン・検索・投稿済み管理・レビュー順）。`fetch_and_build.py` も `item.json` を保存する
  ように接続し設定を `common.py` に集約。★本文に出すジャンルは `SAFE_GENRES` 許可リスト方式で露骨語・未成年
  連想語を遮断（1640本生成でNG混入ゼロ確認）。該当作品はボードで「画像は要注意」警告。README/SKILL.md 更新。
- [x] **不要な機能の削除（リファクタリング）**
  デッドコードを洗い出して削除（約230行）。`fetch_and_build.py` の旧ランキング単独生成器3関数＋未使用引数 `today`、
  `config.json` の `ranking_main_images`、`safe_criteria.py` の `ENTICING_CLASSES`、`make_post_html.py` の
  `find_latest_date_dir`、一回限り移行ツール `migrate_to_works.py`（＋README手順）を削除。全 .py の py_compile 成功・参照ゼロ確認済み。
- [x] **HTML→X ドラッグ&ドロップ投稿の調査**
  結論：ページからXへ D&D でファイル添付は**ブラウザ制約で不可**。現実解は ①画像＝コピー→Xで貼り付け（Cmd+V）②動画＝保存→Finderからドラッグ。
  自動投稿API は方針（投稿は人手）に反するため不採用。詳細：`fanza_auto/メモ_HTMLからXへの投稿方法（DnD調査）.md`。

### fanza-content HTML の動的化（ダッシュボード）

- [x] **① 投稿ステータス管理**
  各投稿に「投稿済み / 投稿前 / 投稿不可」を切り替え。変更は DB に保存し、再度 HTML を開いても保持。
- [x] **② 動画カット**
  サンプル動画下のツールバーで「開始〜終了」（「現在」ボタンで再生位置取り込み）→ `cut_*.mp4` を作成（`/__cut`＋`cut_video.py`）。
- [x] **③ 画像の AB テスト＋再選出**
  各画像に「OK / 微妙 / NG」ボタンと理由欄。判定は `verdicts.json` ＋ ナレッジ
  `規制・安全/…画像合否基準（ABテスト）.md` の判定ログ表へ自動反映（再判定は上書き）。
  「🔄再選出」で `sample.mp4` から重複しない別候補 `alt_N.jpg` を追加（`reselect.py`）。`serve.py` 経由で有効。
- [x] **④ 元動画からの切り抜き UI**
  メディア列を「サンプル動画（大）→ 切り抜いた素材 → システム抽出画像」の縦並びに再構成。
  🎬動画切り抜き＋📷画像切り抜き（`/__grab`＋`grab_frame.py`、再生中の場面を `clip_*.jpg` 化）。作成物は即ギャラリーに追加。
- [x] **⑤ 作品ごとフォルダ＋常設ダッシュボード化**
  日付フォルダを廃止し `fanza_auto/works/<cid>_<作品名>/` に一元化。`make_post_html.py` は works/ 全作品を
  1枚の `works/index.html` に集約。`fetch_and_build.py` は既出 cid をスキップして未掲載の新作だけ追加（差分）。
  status/verdicts は `works/` 直下で全体1つに集約。`serve.py` の配信ルートも works/ に変更。
  既存 `output/<日付>` は `migrate_to_works.py` で移行（20作品・status/verdicts 引き継ぎ）。

### スキル・運用基盤

- [x] **競合分析スキルの完了管理**
  解析済みスクショを `競合分析/完了/<日付>/`（＋`_zoom/`）へ移動する `archive_done.py` を追加し、
  SKILL.md に「直下＝未処理キュー／完了フォルダは解析しない」運用と末尾の移動手順を反映。次回は未処理分だけ解析。
- [x] **大喜利リプ集客スキル＋立ち上げロードマップの「大喜利×美女」対応**
  新スキル `/ogiri-answers`（お題を手入力→健全・無リンクの大喜利回答を3〜5本生成）を追加。ノウハウは
  `ナレッジ/集客・導線/X運用ナレッジ_大喜利（坊主リプ集客）.md`（10の型・作法・安全ライン・ファネル）。
  `launch-roadmap` は concept.json の `ogiri` でフェーズ3が「坊主の大喜利リプで露出を借りる→プロフ流入」に切替。
  「大喜利×美女」コンセプト雛形 `ロードマップ/concept_oogiri-bijo.json` も追加。
- [x] **アカウント情報＆ステータスの一元管理**
  アカウント情報をプロジェクト内に保存し、ステータス（運用中 / 凍結 等）も管理できる状態に。
- [x] **初期アカウントのロードマップをコンセプトから開始**
  最初にアカウントコンセプトを作り、アイコン・名前・ID の設定から始まる形に（`/launch-roadmap`）。
- [x] **スキル一覧の README 化＋自動追記 hook**
  できるスキルを README に端的に記載。スキルが増減すると自動で追従（`.claude/sync_skills_readme.py` ＋ Stop フック）。



https://video.dmm.co.jp/amateur/content/?id=erk116&i3_ref=recommend_i2i&i3_ord=8&i3_pst=1&dmmref=2c372329-9a8f4f0a4d9f58928c89ef3b0f00aaa0

https://video.dmm.co.jp/amateur/content/?id=hoi412&i3_ref=recommend_i2i&i3_ord=12&i3_pst=1&dmmref=2c372329-9a8f4f0a4d9f58928c89ef3b0f00aaa0


https://video.dmm.co.jp/amateur/content/?id=simp020&i3_ref=recommend_i2i&i3_ord=31&i3_pst=1&dmmref=2c372329-9a8f4f0a4d9f58928c89ef3b0f00aaa0

https://video.dmm.co.jp/amateur/content/?id=oremo554&i3_ref=recommend_u2i&i3_ord=7&i3_pst=2&dmmref=14404cb3-9a8f4f0a4d9f58928c89ef3b0f00aaa0

https://video.dmm.co.jp/amateur/content/?id=peep190&i3_ref=recommend&i3_ord=4&i3_pst=1&dmmref=pickup_amateur_top&via=amateur_top


https://video.dmm.co.jp/amateur/content/?id=tkk008&i3_ref=ranking&i3_ord=10&i3_pst=2&dmmref=bestseller_ranking_amateur_top&via=amateur_top


https://video.dmm.co.jp/amateur/content/?id=fcz019&i3_ref=ranking&i3_ord=11&i3_pst=2&dmmref=bestseller_ranking_amateur_top&via=amateur_top

https://video.dmm.co.jp/amateur/content/?id=deas076&i3_ref=ranking&i3_ord=24&i3_pst=2&dmmref=bestseller_ranking_amateur_top&via=amateur_top

https://video.dmm.co.jp/amateur/content/?id=deas075&i3_ref=ranking&i3_ord=37&i3_pst=2&dmmref=bestseller_ranking_amateur_top&via=amateur_top

https://video.dmm.co.jp/amateur/content/?id=simw003&utm_medium=dmm_affiliate&utm_source=noeronolife-014&utm_term=dmm.co.jp&utm_campaign=affiliate_toolbar_sp&utm_content=link


https://video.dmm.co.jp/amateur/content/?id=deas049&i3_ref=recommend_i2i&i3_ord=1&i3_pst=1&dmmref=2c372329-9a8f4f0a4d9f58928c89ef3b0f00aaa0
