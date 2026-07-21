#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`works/<投稿予定日>/dashboard.html`（投稿スケジュール管理）を、動画・画像の
切り抜き/作成/削除、URLを貼っての新規作品取り込みも使える状態で開くための
小さなサーバー。

serve_board.py の Handler（配信＋/__cut・/__crop・/__del・/__grab・
/__select_thumb・/__crop_image）をそのまま再利用し、
  - 素材作成/削除の直後に該当日の dashboard.html を作り直すフック
  - /__fetch（URL/cidを貼って新規作品を今の日付フォルダに取り込む）
を追加する。

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/serve_schedule.py                    # 日付フォルダが1つならそれを開く
    python3 fanza_auto/scripts/serve_schedule.py 2026-07-25         # 日付を指定
    python3 fanza_auto/scripts/serve_schedule.py 2026-07-25 8001    # ポートも指定

止めるとき: Ctrl+C
"""

import functools
import http.server
import json
import os
import subprocess
import sys
import urllib.parse
import webbrowser

import build_board as BB
import common as C
import schedule_board as SB
import serve_board as SVB

ROOT = str(C.WORKS_DIR)
FETCH_PY = str(C.ROOT / "scripts" / "fetch_and_build.py")

# サーバー起動時に決まる「今のダッシュボードの日付」。/__fetch はここに取り込む。
TARGET_DATE = None


class Handler(SVB.Handler):
    def do_POST(self):
        path = self.path.split("?")[0]

        if path == "/__fetch":
            return self._handle_fetch()

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

    def _handle_fetch(self):
        """URL/cid を貼って新規作品を TARGET_DATE の日付フォルダに取り込む。
        fetch_and_build.py をサブプロセスで呼ぶ（nudenetの重い読み込みを
        このサーバー本体に持ち込まないため・処理中の詳細ログも取れるため）。"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(body or b"{}")
            token = (req.get("url") or "").strip()
            if not token:
                return self._json(400, {"ok": False, "error": "URLまたはcidを入力してください"})

            cfg = C.load_config(require_api=False)
            before = {e["cid"] for e in BB.collect(cfg)}

            cmd = [sys.executable, FETCH_PY, token, f"--date={TARGET_DATE}"]
            print(f"  ⬇ 取り込み開始: {token}")
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=300)
            log_tail = (r.stdout or "")[-1500:]

            after_entries = BB.collect(cfg)
            after = {e["cid"] for e in after_entries}
            new_cids = after - before

            if not new_cids:
                # 既存/未成年連想で除外/APIで見つからず、のいずれか。ログをそのまま見せる。
                print(log_tail)
                return self._json(200, {"ok": False, "error": "取り込めませんでした。"
                                        "既に登録済みか、規制対象、または見つからない作品です。",
                                        "log": log_tail})

            cid = next(iter(new_cids))
            BB.build_single(cid, cfg, regen=False)
            SB.build_for_date(TARGET_DATE, cfg)
            entry = next(e for e in after_entries if e["cid"] == cid)
            print(f"  ✓ 取り込み完了: {cid}（{entry['title']}）")
            return self._json(200, {"ok": True, "cid": cid, "title": entry["title"]})
        except subprocess.TimeoutExpired:
            return self._json(500, {"ok": False, "error": "処理がタイムアウトしました（5分）"})
        except Exception as ex:
            return self._json(500, {"ok": False, "error": str(ex)})


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
    global TARGET_DATE
    date = resolve_date(argv)
    TARGET_DATE = date
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
