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
  5. 「📦 アーカイブ」「🗑 完全削除」「↩ 全体ボードに戻す」（POST /__archive・
     /__unarchive・/__delete_work）も受け付ける（全体ボード側で使うボタンだが、
     この共通Handlerを継承する serve_schedule.py からも同じ処理が呼ばれる）

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
import shutil
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path

import build_board as BB
import check_missav as CM
import common as C
import schedule_board as SB

ROOT = str(C.WORKS_DIR)
CUT_PY = str(C.ROOT / "scripts" / "cut_video.py")
CROP_PY = str(C.ROOT / "scripts" / "crop_video.py")
GRAB_PY = str(C.ROOT / "scripts" / "grab_frame.py")
CROP_IMG_PY = str(C.ROOT / "scripts" / "crop_image.py")

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
    #    /__delete_work）─────────────────────
    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/__cut", "/__crop", "/__del",
                        "/__grab", "/__select_thumb", "/__crop_image",
                        "/__missav", "/__archive", "/__unarchive", "/__delete_work"):
            return self.send_error(404, "not found")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(body or b"{}")

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
                cfg = C.load_config(require_api=False)
                try:
                    BB.build_single(cid, cfg, regen=False)
                except Exception as ex:
                    print(f"  ! board_{cid} の再生成に失敗: {ex}")
                SB.build_all(cfg)
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
                cfg = C.load_config(require_api=False)
                SB.build_all(cfg)
                print(f"  🗑 完全削除: {req.get('dir')}")
                return self._json(200, {"ok": True})

            # MissAVに一致する動画が上がっていないかを確認する（Playwrightで実ブラウザ操作・
            # 数秒かかる）。結果は item.json にキャッシュし、ボード/ダッシュボードを作り直す。
            if path == "/__missav":
                folder = self._safe_dir(req.get("dir"))
                if not folder:
                    return self._json(400, {"ok": False, "error": "dir が不正"})
                try:
                    missav = CM.check_and_cache(Path(folder))
                except Exception as ex:
                    return self._json(500, {"ok": False, "error": f"確認処理に失敗: {ex}"})
                if missav.get("status") == "error":
                    return self._json(502, {"ok": False,
                                            "error": missav.get("error") or "確認に失敗しました"})
                print(f"  🔎 MissAV確認: {req.get('dir')} → {missav['status']}")
                self._rebuild_board(req.get("dir"))
                return self._json(200, {"ok": True, "missav": missav})

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
        """切り抜き/削除の直後に board_<cid>.html と全体ボード／アーカイブ一覧を作り直す。
        作り直さないと「消した/作った動画がリロードで元に戻る」ことになる
        （HTMLは静的ファイルで、生成時点のファイル一覧を固定で持つため）。
        単体（serve_board.py）で使っていても全体ボードが古いままにならないよう、
        常に両方を同期する。"""
        work_dir = C.WORKS_DIR / (dir_rel or "")
        cfg = C.load_config(require_api=False)
        try:
            cid = C.cid_of(work_dir)
            BB.build_single(cid, cfg, regen=False)
        except Exception as ex:
            print(f"  ! board_{dir_rel} の再生成に失敗: {ex}")
        try:
            SB.build_all(cfg)
        except Exception as ex:
            print(f"  ! 全体ボードの再生成に失敗: {ex}")


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
