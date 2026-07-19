#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
単一作品ボードを「動画の切り抜きも使える」状態で開くための小さなサーバー。

`build_board.py <cid>` で作る単一作品ボードは、再生と保存だけなら file:// で開けるが、
切り抜き（ffmpeg処理）はサーバーが要る。このスクリプトが：

  1. その cid の board_<cid>.html を作り直し
  2. works/ を配信（動画のシーク＝Rangeリクエストに対応）
  3. ブラウザで開く
  4. ボードからの「✂ 切り抜く」（POST /__cut）を受けて cut_video.py を実行し、
     cut_<開始>-<終了>.mp4 を作品フォルダに保存して返す

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/serve_board.py <cid> [ポート]
    例) python3 fanza_auto/scripts/serve_board.py debz015

止めるとき: Ctrl+C
"""

import functools
import http.server
import json
import mimetypes
import os
import re
import socket
import subprocess
import sys
import webbrowser

import build_board as BB
import common as C

ROOT = str(C.WORKS_DIR)
CUT_PY = str(C.ROOT / "scripts" / "cut_video.py")


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, fmt, *args):
        pass  # 静かに動かす

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    # ── 動画のシーク（Rangeリクエスト）に対応 ──────────────
    def do_GET(self):
        range_header = self.headers.get("Range", "")
        if not range_header:
            return super().do_GET()
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().do_GET()
        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if not m:
            return super().do_GET()

        size = os.path.getsize(path)
        s, e = m.group(1), m.group(2)
        start = int(s) if s else 0
        end = int(e) if e else size - 1
        end = min(end, size - 1)
        if start > end or start >= size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        length = end - start + 1
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        # 動画のシーク中はブラウザが途中で接続を切ることがある。
        # そのときの BrokenPipe は正常動作なので黙って無視する。
        try:
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, code, obj):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _safe_dir(self, name: str):
        """works/ 直下の作品フォルダだけを許可（パス外・親参照を弾く）。"""
        name = (name or "").strip("/")
        if not name or "/" in name or ".." in name:
            return None
        folder = os.path.join(ROOT, name)
        if not os.path.isdir(folder):
            return None
        return folder

    # ── 切り抜き（POST /__cut）──────────────────────────
    def do_POST(self):
        if self.path.split("?")[0] != "/__cut":
            return self.send_error(404, "not found")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(body or b"{}")
            folder = self._safe_dir(req.get("dir"))
            video = (req.get("video") or "sample.mp4").strip()
            start = str(req.get("start", "")).strip()
            end = str(req.get("end", "")).strip()
            if not folder or not start or not end:
                return self._json(400, {"ok": False, "error": "dir/start/end が必要"})
            if os.path.basename(video) != video:
                return self._json(400, {"ok": False, "error": "動画名が不正"})
            src = os.path.join(folder, video)
            if not os.path.isfile(src):
                return self._json(404, {"ok": False, "error": "動画が見つかりません"})

            def tag(x):
                return x.replace(":", "-").replace(".", "_")
            out_name = f"cut_{tag(start)}-{tag(end)}.mp4"
            dst = os.path.join(folder, out_name)
            r = subprocess.run(
                [sys.executable, CUT_PY, src, start, end, dst],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, timeout=300)
            if r.returncode != 0 or not os.path.isfile(dst):
                return self._json(500, {"ok": False,
                                        "error": (r.stdout or "")[-400:]})
            print(f"  ✂ 切り抜き: {req.get('dir')}/{out_name}")
            return self._json(200, {"ok": True, "file": out_name})
        except subprocess.TimeoutExpired:
            return self._json(500, {"ok": False, "error": "処理がタイムアウトしました"})
        except Exception as ex:
            return self._json(500, {"ok": False, "error": str(ex)})


def main(argv) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print("使い方: python3 fanza_auto/scripts/serve_board.py <cid> [ポート]")
        print("  例) python3 fanza_auto/scripts/serve_board.py debz015")
        return 1
    cid = args[0]
    port = int(args[1]) if len(args) >= 2 else 8000

    cfg = C.load_config(require_api=False)
    out = BB.build_single(cid, cfg, regen=False)
    if out is None:
        return 1

    url = f"http://127.0.0.1:{port}/{out.name}"
    handler = functools.partial(Handler)
    try:
        httpd = http.server.ThreadingHTTPServer(("", port), handler)
    except OSError as e:
        print(f"✗ ポート {port} が使えません（{e}）。別ポート例: "
              f"python3 fanza_auto/scripts/serve_board.py {cid} 8001")
        return 1

    print(f"\n▶ 開く: {url}")
    print(f"  スマホ等からは: http://{lan_ip()}:{port}/{out.name}")
    print("  「✂ 切り抜く」でこのサーバーが動画をカットします。")
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
