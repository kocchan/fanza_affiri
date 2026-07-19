# 旧ボード（board_v1）— アーカイブ

新しいテキスト専用ボード（`works/board.html`）に移行したため、ここに退避した**旧ダッシュボード**一式。
**消していない・そのまま動く**ので、新ボードで困ったらいつでも戻れる。

## 何が入っているか

| ファイル | 役割 |
|---|---|
| `serve.py` | 旧ボード用のローカルサーバー。ステータス管理・動画カット・画像切り抜き・A/B判定を受け付ける |
| `make_post_html.py` | `works/index.html`（旧ダッシュボード）を生成する |

`works/index.html` 本体は **`works/` に置いたまま**にしてある（画像・動画を相対パスで参照しているため、
動かすと表示が壊れる）。

## 使い方（戻したいとき）

```bash
# プロジェクトのルートフォルダで実行
python3 fanza_auto/_archive/board_v1/make_post_html.py   # works/index.html を作り直す
python3 fanza_auto/_archive/board_v1/serve.py            # 旧ボードを開く
```

## 新ボードとの関係

- **データは共用**。`works/<cid>_<作品名>/` の画像・`sample.mp4`・`投稿内容.md`、
  および `works/status.json` / `works/verdicts.json` は新旧どちらからも同じものを見る。
- **画像まわり（A/B判定・切り抜き・再選出）は今もこの旧ボードが担当**。
  新ボードはテキスト（作品情報・投稿文・アフィリリンク）専用で、画像機能は載せていない。
- 画像・動画の取得と規制セーフ抽出は `scripts/fetch_and_build.py` 側にあり、こちらは現役のまま。

## 移動にあたって直した箇所

`_archive/board_v1/` に降りたぶん、フォルダを2つ上に遡るようパス定数だけ修正した（中身のロジックは無変更）。

- `serve.py` … `FANZA_DIR` を2階層上に。`cut_video.py` / `grab_frame.py` / `reselect.py` は `scripts/` を参照
- `make_post_html.py` … 既定の `works_dir` を2階層上に
