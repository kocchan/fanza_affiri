#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
output フォルダを簡易Webサーバーで配信し、同じWi-Fiのスマホ/PCから見られるようにする。
HTMLからの操作をサーバーが受けて、フォルダ内に反映する：
  - 投稿ステータス（投稿前/投稿済/不可）→ <日付>/status.json に保存
  - 動画カット（◯秒〜◯秒）→ cut_video.py を実行して cut_<開始>-<終了>.mp4 を作る

使い方:
    python3 serve.py [ポート番号]   # 既定 8000
止めるとき: Ctrl+C
"""
import os
import re
import sys
import json
import socket
import mimetypes
import subprocess
import http.server
import socketserver

HERE = os.path.dirname(os.path.abspath(__file__))
# アーカイブ済み（_archive/board_v1/）のため、fanza_auto までは2つ上に遡る。
FANZA_DIR = os.path.dirname(os.path.dirname(HERE))
SCRIPTS_DIR = os.path.join(FANZA_DIR, "scripts")
# 作品ごとフォルダを集約した works/ を配信ルートにする（旧ダッシュボード= works/index.html）。
ROOT = os.path.join(FANZA_DIR, "works")
CUT_PY = os.path.join(SCRIPTS_DIR, "cut_video.py")
GRAB_PY = os.path.join(SCRIPTS_DIR, "grab_frame.py")
RESELECT_PY = os.path.join(SCRIPTS_DIR, "reselect.py")
KNOWLEDGE_MD = os.path.join(
    FANZA_DIR, "..", "ナレッジ", "規制・安全",
    "X運用ナレッジ_画像合否基準（ABテスト）.md")

# A/Bボタン → ナレッジ表のラベル対応
VERDICT_LABEL = {"ok": "いい", "mid": "クリア", "ng": "NG"}


def sakuhin_label(post):
    """作品フォルダ名 <cid>_<作品名> → 表示用「作品名(cid)」。
    旧形式 <連番>_<作品名>_<cid> にも後方互換で対応。"""
    parts = post.split("_")
    if len(parts) >= 3 and parts[0].isdigit():
        # 旧形式（連番_名前_cid）
        return f"{'_'.join(parts[1:-1])}({parts[-1]})"
    if len(parts) >= 2:
        # 新形式（cid_名前）
        cid, name = parts[0], "_".join(parts[1:])
        return f"{name}({cid})"
    return post


def reflect_to_knowledge(date, post, image, verdict, reason):
    """ナレッジMDの「判定ログ」表へ1行 upsert（同じ日付/作品/画像なら更新）。"""
    path = os.path.abspath(KNOWLEDGE_MD)
    if not os.path.isfile(path):
        return
    label = VERDICT_LABEL.get(verdict, verdict)
    sakuhin = sakuhin_label(post)
    img_label = os.path.splitext(image)[0]
    reason = (reason or "").replace("|", "／").replace("\n", " ").strip()

    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    # 表ヘッダ（| 日付 | 作品 | 画像 | 判定 | 理由・視覚特徴 |）を探す
    h = next((i for i, ln in enumerate(lines)
              if ln.strip().startswith("| 日付") and "判定" in ln), None)
    if h is None:
        return
    # ヘッダ＋区切り の次からデータ行
    start = h + 2
    end = start
    while end < len(lines) and lines[end].strip().startswith("|"):
        end += 1

    def cells(ln):
        return [c.strip() for c in ln.strip().strip("|").split("|")]

    new_row = f"| {date} | {sakuhin} | {img_label} | {label} | {reason} |"

    found = False
    for i in range(start, end):
        c = cells(lines[i])
        if len(c) >= 3 and c[0] == date and c[1] == sakuhin and c[2] == img_label:
            keep_reason = reason if reason else (c[4] if len(c) >= 5 else "")
            lines[i] = f"| {date} | {sakuhin} | {img_label} | {label} | {keep_reason} |"
            found = True
            break
    if not found:
        lines.insert(end, new_row)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def lan_ip():
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

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_GET(self):
        """Range リクエスト対応（動画シーク・早送りに必要）。"""
        range_header = self.headers.get("Range", "")
        if not range_header:
            return super().do_GET()

        # ファイルパスを解決
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().do_GET()

        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if not m:
            return super().do_GET()

        file_size = os.path.getsize(path)
        s, e = m.group(1), m.group(2)
        start = int(s) if s else 0
        end = int(e) if e else file_size - 1
        end = min(end, file_size - 1)

        if start > end or start >= file_size:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{file_size}")
            self.end_headers()
            return

        length = end - start + 1
        ctype, _ = mimetypes.guess_type(path)
        ctype = ctype or "application/octet-stream"

        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _safe_under_root(self, *parts):
        if any(".." in p for p in parts):
            return None
        return os.path.join(ROOT, *parts)

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        # ① 動画カット
        if path == "/__cut":
            try:
                req = json.loads(body or b"{}")
                d = (req.get("dir") or "").strip("/")
                video = (req.get("video") or "sample.mp4").strip()
                start = str(req.get("start", "")).strip()
                end = str(req.get("end", "")).strip()
                if not d or not start or not end:
                    return self._json(400, {"ok": False, "error": "dir/start/end が必要"})
                src = self._safe_under_root(*d.split("/"), video)
                if not src or not os.path.isfile(src):
                    return self._json(404, {"ok": False, "error": "動画が見つかりません"})

                def tag(x):
                    return x.replace(":", "-").replace(".", "_")
                out_name = f"cut_{tag(start)}-{tag(end)}.mp4"
                dst = os.path.join(os.path.dirname(src), out_name)
                r = subprocess.run(
                    [sys.executable, CUT_PY, src, start, end, dst],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=300)
                if r.returncode != 0 or not os.path.isfile(dst):
                    return self._json(500, {"ok": False, "error": r.stdout[-400:]})
                return self._json(200, {"ok": True, "file": out_name})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})

        # ①' 画像切り抜き（元動画の指定時刻を1枚画像化）
        if path == "/__grab":
            try:
                req = json.loads(body or b"{}")
                d = (req.get("dir") or "").strip("/")
                video = (req.get("video") or "sample.mp4").strip()
                sec = str(req.get("sec", "")).strip()
                if not d or not sec:
                    return self._json(400, {"ok": False, "error": "dir/sec が必要"})
                src = self._safe_under_root(*d.split("/"), video)
                if not src or not os.path.isfile(src):
                    return self._json(404, {"ok": False, "error": "動画が見つかりません"})

                def tag(x):
                    return x.replace(":", "-").replace(".", "_")
                out_name = f"clip_{tag(sec)}s.jpg"
                dst = os.path.join(os.path.dirname(src), out_name)
                r = subprocess.run(
                    [sys.executable, GRAB_PY, src, sec, dst],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=120)
                if r.returncode != 0 or not os.path.isfile(dst):
                    return self._json(500, {"ok": False, "error": (r.stdout or "")[-400:]})
                return self._json(200, {"ok": True, "file": out_name})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})

        # ② 画像A/B判定 → verdicts.json 保存 ＋ ナレッジMDへ反映
        if path == "/__verdict":
            try:
                req = json.loads(body or b"{}")
                date = (req.get("date") or "").strip("/")
                post = (req.get("post") or "").strip("/")
                image = (req.get("image") or "").strip()
                verdict = (req.get("verdict") or "").strip()
                reason = (req.get("reason") or "").strip()
                if not date or not post or not image or verdict not in VERDICT_LABEL:
                    return self._json(400, {"ok": False, "error": "date/post/image/verdict が必要"})
                # ダッシュボード全体で1つの verdicts.json（works/ 直下）に集約
                vfile = os.path.join(ROOT, "verdicts.json")
                try:
                    with open(vfile, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
                data[f"{post}/{image}"] = {"v": verdict, "reason": reason}
                os.makedirs(os.path.dirname(vfile), exist_ok=True)
                with open(vfile, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                try:
                    reflect_to_knowledge(date, post, image, verdict, reason)
                except Exception as e:
                    return self._json(200, {"ok": True, "knowledge": False, "warn": str(e)})
                return self._json(200, {"ok": True, "knowledge": True})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})

        # ③ OK以外の再選出 → サンプル動画から別候補を1枚追加
        if path == "/__reselect":
            try:
                req = json.loads(body or b"{}")
                d = (req.get("dir") or "").strip("/")
                if not d:
                    return self._json(400, {"ok": False, "error": "dir が必要"})
                folder = self._safe_under_root(*d.split("/"))
                if not folder or not os.path.isdir(folder):
                    return self._json(404, {"ok": False, "error": "フォルダが見つかりません"})
                r = subprocess.run(
                    [sys.executable, RESELECT_PY, folder],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=600)
                last = (r.stdout or "").strip().split("\n")[-1] if r.stdout else ""
                try:
                    return self._json(200, json.loads(last))
                except Exception:
                    return self._json(500, {"ok": False, "error": (r.stdout or "")[-400:]})
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})

        # ④ ステータス保存（status.json への書き込みのみ許可）
        rel = path.lstrip("/")
        if ".." in rel or not rel.endswith("status.json"):
            return self.send_error(403, "forbidden")
        target = os.path.join(ROOT, *rel.split("/"))
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(body)
        except Exception as e:
            return self.send_error(500, str(e))
        self._json(200, {"ok": True})


def main(argv):
    port = int(argv[1]) if len(argv) >= 2 else 8000
    ip = lan_ip()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        print("=" * 56)
        print("  📱 サーバー起動。ブラウザ（PC/スマホ・同一Wi-Fi）で開く：")
        print()
        print(f"    http://{ip}:{port}/            （= works/index.html ダッシュボード）")
        print()
        print("  ・ステータス変更 → works/status.json に保存")
        print("  ・動画カット → cut_<開始>-<終了>.mp4 を作品フォルダに作成")
        print("  ・画像切り抜き → 元動画の指定時刻を clip_<秒>s.jpg として作成")
        print("  ・画像A/B判定(OK/微妙/NG) → works/verdicts.json ＋ ナレッジMDへ反映")
        print("  ・🔄再選出 → サンプル動画から別候補 alt_N.jpg を追加")
        print("  止める: Ctrl+C")
        print("=" * 56)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n停止しました。")


if __name__ == "__main__":
    main(sys.argv)
