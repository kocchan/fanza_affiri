#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MyFansの全体ボード（`works/board.html`）を、動画・画像の切り抜き/作成/削除、
アーカイブ操作、URL取り込み、ルートフォルダの動画取り込みも使える状態で開くための
小さなサーバー。fanza_auto/scripts/serve_board.py + serve_schedule.py の
MyFans向け統合版（MissAV確認は無い）。

やること:
  1. works/board.html・archive.html を作り直す
  2. works/ を配信（動画のシーク＝Rangeリクエストに対応）
  3. ブラウザで開く
  4. 各カード／個別ページからの操作を受け付ける：
     - ✂ 切り抜く（POST /__cut）・🔲 画面トリミング（/__crop）→ cut_video.py / crop_video.py
     - 📸 静止画切り抜き（/__grab）・🖼 サムネ確定（/__select_thumb・/__crop_image）
     - 🗑 削除（/__del）・📦 アーカイブ／↩ 戻す／🗑 完全削除（/__archive・/__unarchive・/__delete_work）
     - ＋ 取り込む（/__fetch）… URL欄に貼ったMyFansアフィリンクを myfans_fetch.py で取り込む
     - 🎬 動画を取り込む（/__import_video）… プロジェクトのルートフォルダに置いた動画
       （拡張機能でDLしたもの）を import_video.py でタイトル一致の作品フォルダへ振り分ける
     - 💾 保存（/__save_post）… メイン投稿文の手動編集を posts.json に保存
       （文章を作り直したいときはボード上のボタンではなく、Claude Codeのチャットで直接指示する運用）

使い方（プロジェクトのルートフォルダで実行）:
    python3 myfans_auto/scripts/serve.py [ポート]

止めるとき: Ctrl+C
"""

import functools
import http.server
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

import board as BB
import common as C
import dashboard as DB
import import_video as IV
import myfans_fetch as MF

ROOT = str(C.WORKS_DIR)
CUT_PY = str(C.ROOT / "scripts" / "cut_video.py")
CROP_PY = str(C.ROOT / "scripts" / "crop_video.py")
GRAB_PY = str(C.ROOT / "scripts" / "grab_frame.py")
CROP_IMG_PY = str(C.ROOT / "scripts" / "crop_image.py")
FETCH_PY = str(C.ROOT / "scripts" / "myfans_fetch.py")

# サムネ用に選べる「採用画像」の命名規則（01.jpg〜）。これ以外のjpgは選ばせない。
IMAGE_RE = re.compile(r"^\d{2}\.jpg$")


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
        """works/ 配下の作品フォルダを許可（サブフォルダ内でもよい）。
        正規化した実パスが ROOT の外に出ていないかで、親参照(..)によるパス外
        アクセスだけを弾く（"/" 自体は 進行中/<cid>_... のネストのため許可）。"""
        name = (name or "").strip("/")
        if not name:
            return None
        root_real = os.path.realpath(ROOT)
        folder = os.path.realpath(os.path.join(ROOT, name))
        if not (folder == root_real or folder.startswith(root_real + os.sep)):
            return None
        if not os.path.isdir(folder):
            return None
        return folder

    def _resolve_src(self, req):
        """dir/video を検証して元動画のフルパスを返す。ダメなら (None, エラー応答用dict)。"""
        folder = self._safe_dir(req.get("dir"))
        video = (req.get("video") or "sample.mp4").strip()
        if not folder:
            return None, {"ok": False, "error": "dir が不正"}
        if os.path.basename(video) != video:
            return None, {"ok": False, "error": "動画名が不正"}
        src = os.path.join(folder, video)
        if not os.path.isfile(src):
            return None, {"ok": False, "error": "動画が見つかりません"}
        return src, None

    @staticmethod
    def _tag(x):
        return str(x).replace(":", "-").replace(".", "_")

    @staticmethod
    def _cleanup(path):
        """途中で失敗したときの壊れた出力ファイルを消す。"""
        try:
            if path and os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass

    # ── 動画の切り抜き（/__cut）・画面トリミング（/__crop）・削除（/__del）
    #    ・静止画切り抜き（/__grab）・採用画像から選ぶ（/__select_thumb）
    #    ・画像トリミング（/__crop_image）・アーカイブ（/__archive・/__unarchive・
    #    /__delete_work）・URL取り込み（/__fetch）・動画取り込み（/__import_video）
    #    ─────────────────────
    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/__cut", "/__crop", "/__del",
                        "/__grab", "/__select_thumb", "/__crop_image",
                        "/__archive", "/__unarchive", "/__delete_work",
                        "/__fetch", "/__import_video", "/__save_post"):
            return self.send_error(404, "not found")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(body or b"{}")

            # URL欄に貼ったMyFansアフィリンクを取り込む（タイトル・説明文・サムネ画像のみ）。
            if path == "/__fetch":
                return self._handle_fetch(req)

            # プロジェクトのルートフォルダに置いた動画を、タイトル一致で対応フォルダへ振り分ける。
            if path == "/__import_video":
                return self._handle_import_video()

            # メイン投稿文の手動保存（posts.json の main を上書き）。
            # 文章を作り直したいときはボード上のボタンではなくチャットでClaudeに指示する運用。
            if path == "/__save_post":
                folder = self._safe_dir(req.get("dir"))
                if not folder:
                    return self._json(400, {"ok": False, "error": "dir が不正"})
                cid = C.cid_of(Path(folder))
                text = (req.get("main") or "").strip()
                BB.set_main_text(cid, text)
                self._rebuild_board(req.get("dir"))
                print(f"  💾 保存: {req.get('dir')} のメイン投稿文を更新")
                return self._json(200, {"ok": True, "text": text})

            # 作品をアーカイブする／アーカイブから戻す（item.json の "archived" を更新）。
            if path in ("/__archive", "/__unarchive"):
                folder = self._safe_dir(req.get("dir"))
                if not folder:
                    return self._json(400, {"ok": False, "error": "dir が不正"})
                folder = Path(folder)
                item = C.read_item(folder)
                item["archived"] = (path == "/__archive")
                C.write_item(folder, item)
                cid = C.cid_of(folder)
                try:
                    BB.build_single(cid, regen=False)
                except Exception as ex:
                    print(f"  ! board_{cid} の再生成に失敗: {ex}")
                DB.build_all()
                verb = "アーカイブしました" if item["archived"] else "全体ボードに戻しました"
                print(f"  📦 {req.get('dir')} を{verb}")
                return self._json(200, {"ok": True})

            # 作品フォルダごと完全に削除する（元に戻せない）。
            if path == "/__delete_work":
                folder = self._safe_dir(req.get("dir"))
                if not folder:
                    return self._json(400, {"ok": False, "error": "dir が不正"})
                cid = C.cid_of(Path(folder))
                shutil.rmtree(folder)
                single_html = BB.single_board_path(cid)
                if single_html.is_file():
                    single_html.unlink()
                DB.build_all()
                print(f"  🗑 完全削除: {req.get('dir')}")
                return self._json(200, {"ok": True})

            # 作った素材（cut_/crop_の動画、clip_/thumb_の画像）だけを削除する。
            # 元動画・採用画像・他ファイルは消せない。
            if path == "/__del":
                folder = self._safe_dir(req.get("dir"))
                name = (req.get("file") or "").strip()
                if not folder:
                    return self._json(400, {"ok": False, "error": "dir が不正"})
                ok_mp4 = name.startswith(("cut_", "crop_")) and name.endswith(".mp4")
                ok_jpg = name.startswith(("clip_", "thumb_")) and name.endswith(".jpg")
                if os.path.basename(name) != name or not (ok_mp4 or ok_jpg):
                    return self._json(400, {"ok": False,
                                            "error": "削除できるのは cut_/crop_(mp4) か "
                                                     "clip_/thumb_(jpg) だけです"})
                target = os.path.join(folder, name)
                if not os.path.isfile(target):
                    return self._json(404, {"ok": False, "error": "ファイルが見つかりません"})
                os.remove(target)
                print(f"  🗑 削除: {req.get('dir')}/{name}")
                self._rebuild_board(req.get("dir"))
                return self._json(200, {"ok": True, "file": name})

            # 候補画像（採用画像 or 動画から切り抜いた静止画）を、そのままサムネとして確定する。
            if path == "/__select_thumb":
                folder = self._safe_dir(req.get("dir"))
                name = (req.get("file") or "").strip()
                if not folder:
                    return self._json(400, {"ok": False, "error": "dir が不正"})
                if (os.path.basename(name) != name
                        or not (IMAGE_RE.match(name) or name.startswith("clip_"))):
                    return self._json(400, {"ok": False,
                                            "error": "選べるのは候補画像（採用画像 or 切り抜き画像）だけです"})
                src_img = os.path.join(folder, name)
                if not os.path.isfile(src_img):
                    return self._json(404, {"ok": False, "error": "画像が見つかりません"})
                base = os.path.splitext(name)[0]
                out_name = f"thumb_pick_{base}.jpg"
                dst = os.path.join(folder, out_name)
                n = 2
                while os.path.isfile(dst):   # 同じ画像を複数回選んだら連番にする
                    out_name = f"thumb_pick_{base}_{n}.jpg"
                    dst = os.path.join(folder, out_name)
                    n += 1
                shutil.copyfile(src_img, dst)
                print(f"  🖼 サムネ選択: {req.get('dir')}/{out_name}（元 {name}）")
                self._rebuild_board(req.get("dir"))
                return self._json(200, {"ok": True, "file": out_name})

            # 既存画像（採用画像・作成済みサムネ）を範囲選択でトリミングする。
            if path == "/__crop_image":
                folder = self._safe_dir(req.get("dir"))
                name = (req.get("image") or "").strip()
                rect = (req.get("rect") or "").strip()
                if not folder:
                    return self._json(400, {"ok": False, "error": "dir が不正"})
                if (os.path.basename(name) != name or not name.endswith(".jpg")
                        or not (IMAGE_RE.match(name)
                                or name.startswith(("clip_", "thumb_")))):
                    return self._json(400, {"ok": False, "error": "元画像が不正"})
                src_img = os.path.join(folder, name)
                if not os.path.isfile(src_img):
                    return self._json(404, {"ok": False, "error": "元画像が見つかりません"})
                parts = rect.split(",")
                if len(parts) != 4 or not all(
                        p.strip().lstrip("-").replace(".", "", 1).isdigit()
                        for p in parts):
                    return self._json(400, {"ok": False, "error": "rect は x,y,w,h の数値"})
                x, y, w, h = (int(float(p)) for p in parts)
                out_name = f"thumb_sel_{x}_{y}_{w}x{h}.jpg"
                dst = os.path.join(folder, out_name)
                cmd = [sys.executable, CROP_IMG_PY, src_img, rect, "-", dst]
                r = subprocess.run(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, timeout=30)
                if r.returncode != 0 or not os.path.isfile(dst):
                    self._cleanup(dst)
                    return self._json(500, {"ok": False,
                                            "error": (r.stdout or "")[-400:]})
                print(f"  🖼 画像トリミング: {req.get('dir')}/{out_name}")
                self._rebuild_board(req.get("dir"))
                return self._json(200, {"ok": True, "file": out_name})

            # 以下は動画（sample.mp4）を対象にする処理
            src, err = self._resolve_src(req)
            if err:
                return self._json(400, err)

            if path == "/__grab":
                sec = str(req.get("sec", "")).strip()
                if sec == "":
                    return self._json(400, {"ok": False, "error": "sec が必要"})
                try:
                    float(sec)
                except ValueError:
                    return self._json(400, {"ok": False, "error": "sec は数値"})
                out_name = f"clip_{self._tag(sec)}s.jpg"
                dst = os.path.join(os.path.dirname(src), out_name)
                cmd = [sys.executable, GRAB_PY, src, sec, dst]
                r = subprocess.run(cmd, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, timeout=30)
                if r.returncode != 0 or not os.path.isfile(dst):
                    self._cleanup(dst)
                    return self._json(500, {"ok": False,
                                            "error": (r.stdout or "")[-400:]})
                print(f"  📸 静止画切り抜き: {req.get('dir')}/{out_name}")
                self._rebuild_board(req.get("dir"))
                return self._json(200, {"ok": True, "file": out_name})

            if path == "/__cut":
                start = str(req.get("start", "")).strip()
                end = str(req.get("end", "")).strip()
                if not start or not end:
                    return self._json(400, {"ok": False, "error": "start/end が必要"})
                out_name = f"cut_{self._tag(start)}-{self._tag(end)}.mp4"
                cmd = [sys.executable, CUT_PY, src, start, end,
                       os.path.join(os.path.dirname(src), out_name)]
                label = "✂ 切り抜き"
            else:  # /__crop（画面トリミング）
                start = str(req.get("start", "")).strip()
                end = str(req.get("end", "")).strip()
                rect = (req.get("rect") or "").strip()
                if rect:
                    # 手動範囲："x,y,w,h"（数値4つ）
                    parts = rect.split(",")
                    if len(parts) != 4 or not all(
                            p.strip().lstrip("-").replace(".", "", 1).isdigit()
                            for p in parts):
                        return self._json(400, {"ok": False,
                                                "error": "rect は x,y,w,h の数値"})
                    spec, pos = rect, "-"
                    xs = "_".join(str(int(float(p))) for p in parts)
                    name = f"crop_sel_{xs}"
                else:
                    aspect = (req.get("aspect") or "").strip()
                    pos = (req.get("pos") or "center").strip()
                    if ":" not in aspect:
                        return self._json(400, {"ok": False,
                                                "error": "aspect か rect が必要"})
                    if pos not in ("center", "left", "right", "top", "bottom"):
                        return self._json(400, {"ok": False, "error": "pos が不正"})
                    spec = aspect
                    name = f"crop_{aspect.replace(':', 'x')}_{pos}"
                if start and end:
                    name += f"_{self._tag(start)}-{self._tag(end)}"
                out_name = name + ".mp4"
                cmd = [sys.executable, CROP_PY, src, spec, pos,
                       start, end, os.path.join(os.path.dirname(src), out_name)]
                label = "🔲 画面トリミング"

            dst = os.path.join(os.path.dirname(src), out_name)
            try:
                r = subprocess.run(cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, timeout=300)
            except subprocess.TimeoutExpired:
                self._cleanup(dst)
                return self._json(500, {"ok": False, "error": "処理がタイムアウトしました"})
            if r.returncode != 0 or not os.path.isfile(dst):
                self._cleanup(dst)   # 失敗時に壊れた部分ファイルを残さない
                return self._json(500, {"ok": False,
                                        "error": (r.stdout or "")[-400:]})
            print(f"  {label}: {req.get('dir')}/{out_name}")
            self._rebuild_board(req.get("dir"))
            return self._json(200, {"ok": True, "file": out_name})
        except Exception as ex:
            return self._json(500, {"ok": False, "error": str(ex)})

    def _rebuild_board(self, dir_rel):
        """切り抜き/削除の直後に board_<投稿ID>.html と全体ボード／アーカイブ一覧を作り直す。
        作り直さないと「消した/作った動画がリロードで元に戻る」ことになる
        （HTMLは静的ファイルで、生成時点のファイル一覧を固定で持つため）。"""
        work_dir = C.WORKS_DIR / (dir_rel or "")
        try:
            cid = C.cid_of(work_dir)
            BB.build_single(cid, regen=False)
        except Exception as ex:
            print(f"  ! board_{dir_rel} の再生成に失敗: {ex}")
        try:
            DB.build_all()
        except Exception as ex:
            print(f"  ! 全体ボードの再生成に失敗: {ex}")

    def _handle_fetch(self, req):
        """URL欄に貼ったMyFansアフィリンクを myfans_fetch.py をサブプロセスで呼んで取り込む。
        本文全文・サンプル動画はPlaywrightで実ページを開いて自動取得する（数秒〜十数秒かかる）。
        req に description があれば --description で渡す（自動取得が失敗したときの手動上書き用。
        現在のUIからは送られないが、後方互換のため残す）。"""
        token = (req.get("url") or "").strip()
        description = (req.get("description") or "").strip()
        if not token:
            return self._json(400, {"ok": False, "error": "URLを入力してください"})
        try:
            before = {e["cid"] for e in BB.collect()}
            cmd = [sys.executable, FETCH_PY, token]
            if description:
                cmd += ["--description", description]
            print(f"  ⬇ 取り込み開始: {token}")
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=120)
            log_tail = (r.stdout or "")[-1500:]

            after_entries = BB.collect()
            new_cids = {e["cid"] for e in after_entries} - before
            if not new_cids:
                print(log_tail)
                return self._json(200, {"ok": False,
                                        "error": "取り込めませんでした。既に登録済みか、"
                                                 "URLが不正、または取得に失敗しました。",
                                        "log": log_tail})

            cid = next(iter(new_cids))
            entry = next(e for e in after_entries if e["cid"] == cid)
            BB.build_single(cid, regen=False)
            DB.build_all()
            print(f"  ✓ 取り込み完了: {cid}（{entry['title']}）")
            return self._json(200, {"ok": True, "cid": cid, "title": entry["title"]})
        except subprocess.TimeoutExpired:
            return self._json(500, {"ok": False, "error": "処理がタイムアウトしました"})
        except Exception as ex:
            return self._json(500, {"ok": False, "error": str(ex)})

    def _handle_import_video(self):
        """プロジェクトのルートフォルダに置いた動画を、タイトル一致で対応する作品フォルダに
        sample.mp4 として振り分ける（import_video.py）。"""
        try:
            entries = BB.collect()
            result = IV.import_videos(C.PROJECT_ROOT, entries)
            for m in result["moved"]:
                print(f"  ✓ 動画取り込み: {m['file']} → {m['dir']}/sample.mp4")
            if result["moved"]:
                for cid in {e["cid"] for e in entries
                           if any(m["dir"] == e["dir"].name for m in result["moved"])}:
                    BB.build_single(cid, regen=False)
                DB.build_all()
            return self._json(200, {"ok": True, **result})
        except Exception as ex:
            return self._json(500, {"ok": False, "error": str(ex)})


def main(argv) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    port = int(args[0]) if args and args[0].isdigit() else 8000

    out = DB.build_all()

    url = f"http://127.0.0.1:{port}/{out.name}"
    handler = functools.partial(Handler)
    try:
        httpd = http.server.ThreadingHTTPServer(("", port), handler)
    except OSError as e:
        print(f"✗ ポート {port} が使えません（{e}）。別ポート例: "
              f"python3 myfans_auto/scripts/serve.py 8001")
        return 1

    print(f"\n▶ 開く: {url}")
    print(f"  スマホ等からは: http://{lan_ip()}:{port}/{out.name}")
    print("  ここで動画の切り抜き・アーカイブ・URL/動画取り込みが使えます。")
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
