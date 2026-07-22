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

- [x] **FANZAボードにも作品説明の自動取得＋メイン投稿の編集保存を追加（MyFansと同機能に）**
  MyFans側で先に作った「取り込み時に説明文も取得して個別ページで見られる」「メイン投稿文を
  テキストエリアで直接編集→💾保存」をFANZA側にも同様に実装。`fetch_and_build.py`に
  Playwrightで商品ページのJSON-LD（`@type: Product`の`description`）を取る
  `fetch_description()`を追加し`item.json`に`description`保存。`build_board.py`の
  個別ページ（`single=True`時のみ）に説明文ブロックと編集可能な`main_block()`
  （テキストエリア＋💾保存＋「作り直しはチャットで直接指示」の注意書き）を追加。
  `serve_board.py`に`/__save_post`エンドポイントを追加し`posts.json`へ保存
  （`serve_schedule.py`からも継承済みで動く）。実データ（deas049）で説明文取得・保存を
  実機確認し、テスト保存分は`build_board.py --regen`で元のキャプションに復元済み。
  ドキュメントも更新：`fanza_auto/README.md`と`.claude/skills/fanza-content/SKILL.md`。
- [x] **MyFansの「🔄 AI再生成」ボタンを撤去（チャット直接指示に一本化）**
  ユーザーから「再生成ボタンを押したらClaude Code（このチャット）が反映される作りにできるか」
  と聞かれ、技術的に不可能と回答（ダッシュボードは別プロセスのHTTPサーバーで、私はチャットで
  呼ばれた時しか動けないため、ボタン押下→即座に私が起動、は実現できない）。ユーザー了承の上、
  「🔄 AI再生成」ボタン・単語入力欄・`/__regen_caption`エンドポイント・`caption.py`の
  `build_from_keywords()`をすべて削除し、代わりに「文章を作り直したいときはチャットで直接
  指示してください」という注意書きに置き換え。💾保存ボタン（手動編集の保存）は維持。
  取り込み時の自動キャプション生成（`caption.py`の`build_main_text`）はそのまま残す
  （これは「作り直し」ではなく初期値づけなので対象外）。
- [x] **MyFansキャプションの型をカテゴリ分け＋実例ナレッジ化**
  ユーザーから実例5本（「インドア美少女との密会がこれ」「同窓会で久々に再会したらこうなるｗｗ」
  「野球拳で負けちゃう〇学校教師さんｗｗｗ」等）を提示され「これを参考にする仕組みに」と依頼。
  実例を`ナレッジ/コンテンツ/X運用ナレッジ_MyFansキャプション型.md`に保存（FANZA側の
  `X運用ナレッジ_勝ち型（バズ型）.md`に相当するMyFans版。ナレッジ→実装の順を保つ）。
  `caption.py`の`TEMPLATES`を単一プールからカテゴリ別（place/event/game/person）に再構成し、
  「同窓会との密会がこれ」のような文法的に不自然な組み合わせを排除。`SAFE_SITUATIONS`にも
  カテゴリを付与（W杯/野球拳/忘年会/新年会を追加）。`build_from_keywords`（AI再生成の自由入力）
  は許可リストに無い単語でも簡易ヒント（「会」→event、「拳」→game、「女/子/さん」等→person）
  でカテゴリを推測するように。実例と近い出力（「野球拳で負けちゃう子ｗｗｗ」等）を確認済み。
- [x] **MyFansのメイン投稿文を個別ページで自由編集＋AI再生成できるように**
  ユーザーから「メイン投稿文を自分で編集して保存ボタンで反映したい、追加で単語を入れて
  AI再生成するボタンも欲しい」と要望。個別ページのメイン投稿ブロックを読み取り専用`<pre>`から
  `<textarea>`に変更し、「💾 保存」（`/__save_post`）と「🔄 AI再生成」（`/__regen_caption`、
  単語欄＋ボタン）を追加。`board.py`に`set_main_text(cid, text)`（`posts.json`のmainだけ上書き）、
  `caption.py`に`build_from_keywords()`（入力単語から1つ選びテンプレートに当てはめる。本文からの
  自動抽出とは別ルート）を追加。保存・再生成どちらも`_rebuild_board()`で個別ページ・全体ボード
  両方を再生成するので、全体ボード側にも即反映される。コピー機能もtextarea対応
  （`.textContent`は編集を反映しないため`.value`を見るよう修正）。実エンドポイントで動作確認済み。
- [x] **MyFansのメイン投稿文を、本文から場所・シチュエーションを拾って作るように（`caption.py`）**
  個別ページに本文（description）のコピー用ブロックを追加した流れで、ユーザーから「本文から
  『お泊まり会』『エアビー』のような要素を拾って、wwwを使う短いあるある反応文にしてほしい」と
  要望。既存の`post_text.py`（FANZA用）は評価/ジャンル/発売日という構造化データ前提で
  MyFansには使えないため、`myfans_auto/scripts/caption.py`を新規作成：本文から
  「場所・シチュエーション」だけを許可リスト方式で拾う（`SAFE_SITUATIONS`＝エアビー/お泊まり/
  ホテル/合コン/デート等。行為語・ハッシュタグ・未成年連想語は本文にあっても絶対に拾わない）→
  短い反応文テンプレート（「ノリで{kw}した結果がこれwww」等）に当てはめる。該当語が無い投稿は
  `templates.py`の`REACTION_HOOKS`固定文にフォールバック。伏字対応（「エ◯ビー」のように
  記号を挟む表記）も正規表現で吸収。`board.py`の`ensure_posts()`でメイン投稿文だけこれに差し替え、
  リンク投稿・賑やかしは引き続き`post_text.py`を流用。実データ（北岡果林の投稿＝「エアビー行ったら
  そりゃこうなるよねwww」等）で動作確認済み。README/SKILL.md更新。
- [x] **MyFansの本文全文・サンプル動画も自動取得に（Playwrightで年齢確認を通すだけ）**
  ユーザーから「本文をボード上で手動貼り付けするのは嫌、自動で取ってきてほしい」と要望があり調査。
  og:descriptionはMyFans側で短く切られており、これまでは自動取得できないと判断していたが、
  実際にPlaywrightで投稿ページを開いて検証したところ、**年齢確認「はい」をクリックするだけ**
  （ログイン不要・誰でも通す標準導線でボット対策ではない）で、本文全文（DOM上の実テキスト。
  line-clampで見た目は省略されていてもtextContentは全文を持つ）と、**無料公開サンプル動画**
  （`content.mfcdn.jp`の公開HLS配信・ログイン/購入なしで200が返る）が取得できることを確認。
  ログイン自動化（`myfans_login.py`、削除済み）はCloudflare Turnstileに阻まれたが、
  ログインしない匿名ページ閲覧は何も検知されない、という違いがポイント。
  `myfans_fetch.py`を全面改修：①requestsで軽量にog:image/post_id解決→②Playwrightで
  年齢確認突破→本文全文をtitle_prefixからの前方一致で検索（Tailwindクラス名に依存しない
  頑健な方式）→③サンプル動画のm3u8 URLをネットワーク応答から捕捉しffmpegで`sample.mp4`化
  （`-user_agent`/`-headers Referer`必須。無いとCDNに403される）。②が失敗しても①の結果のみで
  続行する設計（壊れやすい部分を落としても全体は動く）。タイトルも本文1行目から取るように変更し
  従来の"..."切れを解消。ダッシュボードの本文貼り付けテキストエリアは不要になったため削除、
  ①②③のステップ表示も「①URL貼り付け（自動で全部取得）／②③（任意・本編が要る時だけ）」に更新。
  `--description`手動上書きはCLI保険用として残す。README/SKILL.md更新。
- [x] **MyFans専用ダッシュボード（`myfans_auto/`）を新設・FANZAとは別ボードに**
  当初はFANZAの `works/board.html` にMyFansも混在させる案で実装したが、DMMとMyFansはアフィリエイトの
  仕組み（クリエイターごとに別アフィリンク・APIなし）や投稿元データが大きく異なり運用感が合わないため、
  ユーザー指示で完全に別プロジェクト `myfans_auto/`（`fanza_auto/`と同じ構成：`works/`・`scripts/`）に分離。
  `fanza_auto/scripts/{build_board,schedule_board,serve_board,common}.py` はFANZA向けの状態に完全revert
  （`git checkout --`）。`myfans_auto/scripts/` に `common.py`（軽量版）・`board.py`（旧build_board.py相当）・
  `dashboard.py`（旧schedule_board.py相当）・`serve.py`（旧serve_board+serve_schedule統合・MissAV除去）・
  `myfans_fetch.py`（投稿URLの公開OGPメタタグだけを読む取り込み。ログイン不要・タイトル/説明文/サムネ画像のみ）・
  `import_video.py`（新規）・`cut_video.py`等の切り抜き4本（fanza_autoからコピーし完全独立）を新規作成。
  投稿文生成（`post_text.py`/`templates.py`）は空データに自動フォールバックする既存挙動を活かし
  `fanza_auto/scripts/`からsys.path経由でそのまま再利用（書き直さず）。
  **動画の自動取得は断念**：Playwrightでのログイン自動化（`myfans_login.py`）を試したが、
  ログイン画面のCloudflare Turnstileが自動化ブラウザを検知し失敗（検証済み・スクショで確認）。
  回避技術（フィンガープリント偽装等）はプラットフォームの意図的な自動化対策を突破する行為のため不実装。
  → 運用は「①URLでタイトル/サムネ取込→②人がChrome拡張機能（FetchV Video Download等）で動画を保存し
  プロジェクトルートに置く→③ボードの『🎬 動画を取り込む』ボタンでタイトル一致の作品フォルダへ
  `sample.mp4`として自動振り分け」の3段構成に（`import_video.py`のタイトル前方一致マッチングで実装・
  実データで動作確認済み）。新スキル `/myfans-content` を追加、`myfans_auto/README.md`・ルート`README.md`・
  `.claude/skills/fanza-content/SKILL.md`（MyFans混在記述を削除しリンクだけ残す）を更新。
- [x] **投稿ボードを日付フォルダ方式から全体ボード＋アーカイブ方式に戻す**
  「日付ごとのボード」をやめ、`works/board.html`（全作品）＋`works/archive.html`（アーカイブ済み）の
  2枚構成に統合。もともとSKILL.md/README.mdは「日付フォルダは作らない」設計のままで、
  2026-07-20頃に入った日付フォルダ化（`schedule_board.py`）だけがドキュメントより先行していたため、
  今回はその巻き戻しにあたる。`fetch_and_build.py`も日付プロンプト（`prompt_post_date`・`--date=`）を廃止し
  `works/<cid>_名前/`に直接保存する方式へ復帰。既存12+1作品は`works/`直下へ移動してフラット化
  （`common.py`の`date_dirs`/`date_of`等も削除）。「投稿済みにする」（localStorageで薄く塗りつぶすだけ）を
  廃止し、「📦アーカイブ」ボタン（`item.json`の`archived`にサーバー側で永続化・押すとカードが消える）に置換。
  アーカイブ一覧側には「🗑完全削除」（フォルダごと`shutil.rmtree`・元に戻せない）と
  「↩全体ボードに戻す」の2ボタン。エンドポイント`/__archive`・`/__unarchive`・`/__delete_work`は
  `serve_board.py`の共通Handlerに追加（`board_<cid>.html`個別ページにも同じアーカイブボタンを設置し一貫性を保つ）。
  `schedule_board.py`・`serve_schedule.py`を全面書き換え、`fanza_auto/README.md`・ルート`README.md`・
  `.claude/skills/fanza-content/SKILL.md`も同期。ダミーフォルダでarchive/unarchive/完全削除の
  エンドポイントを実地テスト済み。
- [x] **MissAV存在チェック機能（品番の流出確認）**
  品番からMissAV（https://missav.live/ja/search/<品番>）に一致する動画が上がっているかを内部確認する機能を追加。
  `check_missav.py`（Playwrightで実ブラウザを操作。requestsだとCloudflareのJS認証で403になるため）。
  完全一致時はサーバーが即描画・一致なし時はJSで関連候補を後から描画するというサイト側の挙動の違いで
  「あり／なし」を判定。CLI単体（`python3 fanza_auto/scripts/check_missav.py <品番>`）に加え、
  board_<cid>.html・dashboard.htmlの各カードに「🔎 MissAVを確認」ボタンを追加（`serve_board.py`の`/__missav`）。
  結果は`item.json`の`missav`にキャッシュし、バッジ表示（⚠️あり／✓なし）。動画の視聴・DL・リンク案内は一切しない、
  内部確認専用の機能。
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
