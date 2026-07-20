#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`works/<投稿予定日>/dashboard.html`（投稿スケジュール管理）を、動画・画像の
切り抜き/作成/削除も使える状態で開くための小さなサーバー。

serve_board.py の Handler（配信＋/__cut・/__crop・/__del・/__grab・
/__select_thumb・/__crop_image）をそのまま再利用し、素材作成/削除の直後に
該当日の dashboard.html を作り直すフックだけを足す。

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/serve_schedule.py                    # 日付フォルダが1つならそれを開く
    python3 fanza_auto/scripts/serve_schedule.py 2026-07-25         # 日付を指定
    python3 fanza_auto/scripts/serve_schedule.py 2026-07-25 8001    # ポートも指定

止めるとき: Ctrl+C
"""

import functools
import http.server
import os
import sys
import urllib.parse
import webbrowser

import common as C
import schedule_board as SB
import serve_board as SVB

ROOT = str(C.WORKS_DIR)


class Handler(SVB.Handler):
    def do_POST(self):
        path = self.path.split("?")[0]
        result = super().do_POST()
        # 動画の切り抜き/画面トリミング/削除、画像の切り抜き/選択/トリミングの直後は、
        # dashboard.html を作り直しておく（存在する日付ぶん全部）。作り直さないと
        # 「消した/作ったはずの素材がリロードで元に戻る」＝静的HTMLが古い一覧のままになる。
        if path in ("/__cut", "/__crop", "/__del",
                    "/__grab", "/__select_thumb", "/__crop_image"):
            try:
                SB.main(["schedule_board.py"])
            except Exception as ex:
                print(f"  ! dashboard.html の再生成に失敗: {ex}")
        return result


def resolve_date(argv) -> str:
    """引数から対象日付を決める。省略時は日付フォルダが1つだけならそれを使う。"""
    positional = [a for a in argv[1:] if not a.isdigit()]
    if positional:
        date = positional[0]
        if not C.DATE_RE.match(date):
            sys.exit(f"✗ 日付は YYYY-MM-DD の形式で指定してください: {date}")
        return date

    dates = C.date_dirs()
    if not dates:
        sys.exit("✗ works/ に日付フォルダがありません。"
                 "先に fetch_and_build.py で作品を取り込んでください。")
    if len(dates) > 1:
        names = ", ".join(d.name for d in dates)
        sys.exit(f"✗ 日付フォルダが複数あります。指定してください: {names}\n"
                 f"  例) python3 fanza_auto/scripts/serve_schedule.py {dates[0].name}")
    return dates[0].name


def main(argv) -> int:
    date = resolve_date(argv)
    port_args = [a for a in argv[1:] if a.isdigit()]
    port = int(port_args[0]) if port_args else 8000

    cfg = C.load_config(require_api=False)
    out = SB.build_for_date(date, cfg)

    # 日付フォルダ名はASCIIだが、将来日本語混在も考えて念のためエンコードする。
    rel = os.path.relpath(out, C.WORKS_DIR)
    url_path = "/".join(urllib.parse.quote(seg) for seg in rel.split(os.sep))
    url = f"http://127.0.0.1:{port}/{url_path}"

    handler = functools.partial(Handler)
    try:
        httpd = http.server.ThreadingHTTPServer(("", port), handler)
    except OSError as e:
        print(f"✗ ポート {port} が使えません（{e}）。別ポート例: "
              f"python3 fanza_auto/scripts/serve_schedule.py 8001")
        return 1

    print(f"\n▶ 開く: {url}")
    print(f"  スマホ等からは: http://{SVB.lan_ip()}:{port}/{url_path}")
    print("  ここで動画の切り抜き・削除が使えます。")
    print("  止めるとき: Ctrl+C\n")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
