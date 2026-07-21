#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`works/board.html`（全体ボード）を、動画・画像の切り抜き/作成/削除、アーカイブ操作、
URLを貼っての新規作品取り込みも使える状態で開くための小さなサーバー。

serve_board.py の Handler（配信＋/__cut・/__crop・/__del・/__grab・
/__select_thumb・/__crop_image・/__missav・/__archive・/__unarchive・/__delete_work）を
そのまま再利用し、/__fetch（URL/cidを貼って新規作品を works/ 直下に取り込む）だけを追加する。
取り込みが成功したら、そのままMissAVに一致する動画が上がっていないかも自動で確認する
（手で「🔎 MissAVを確認」を押さなくても、取り込み直後からボード上に あり/なし が出る）。
それ以外の操作の後始末（board.html/archive.html/board_<cid>.html の再生成）は
serve_board.py の Handler 側が共通で行うので、ここで重ねて行う必要はない。

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/serve_schedule.py           # works/board.html を開く
    python3 fanza_auto/scripts/serve_schedule.py 8001      # ポートを指定

止めるとき: Ctrl+C
"""

import functools
import http.server
import json
import subprocess
import sys
import webbrowser

import build_board as BB
import check_missav as CM
import common as C
import schedule_board as SB
import serve_board as SVB

FETCH_PY = str(C.ROOT / "scripts" / "fetch_and_build.py")


class Handler(SVB.Handler):
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/__fetch":
            return self._handle_fetch()
        return super().do_POST()

    def _handle_fetch(self):
        """URL/cid を貼って新規作品を works/ 直下に取り込む。
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

            cmd = [sys.executable, FETCH_PY, token]
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
            entry = next(e for e in after_entries if e["cid"] == cid)

            # 取り込みをトリガに、そのままMissAVに一致する動画が上がっていないか確認する
            # （手でボタンを押さなくても最初から結果が見える。数秒かかる）。
            missav = None
            try:
                missav = CM.check_and_cache(entry["dir"])
            except Exception as ex:
                print(f"  ! MissAV確認に失敗: {ex}")

            BB.build_single(cid, cfg, regen=False)
            SB.build_all(cfg)
            print(f"  ✓ 取り込み完了: {cid}（{entry['title']}）"
                  + (f" ／MissAV: {missav['status']}" if missav else ""))
            return self._json(200, {"ok": True, "cid": cid, "title": entry["title"],
                                    "missav": missav})
        except subprocess.TimeoutExpired:
            return self._json(500, {"ok": False, "error": "処理がタイムアウトしました（5分）"})
        except Exception as ex:
            return self._json(500, {"ok": False, "error": str(ex)})


def main(argv) -> int:
    port_args = [a for a in argv[1:] if a.isdigit()]
    port = int(port_args[0]) if port_args else 8000

    cfg = C.load_config(require_api=False)
    out = SB.build_all(cfg)

    url = f"http://127.0.0.1:{port}/{out.name}"

    handler = functools.partial(Handler)
    try:
        httpd = http.server.ThreadingHTTPServer(("", port), handler)
    except OSError as e:
        print(f"✗ ポート {port} が使えません（{e}）。別ポート例: "
              f"python3 fanza_auto/scripts/serve_schedule.py 8001")
        return 1

    print(f"\n▶ 開く: {url}")
    print(f"  スマホ等からは: http://{SVB.lan_ip()}:{port}/{out.name}")
    print("  ここで動画の切り抜き・アーカイブ・URL取り込みが使えます。")
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
