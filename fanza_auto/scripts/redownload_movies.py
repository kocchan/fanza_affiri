#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
works/ の各作品の sample.mp4 を、config.json の movie_quality で落とし直す。

用途：画質設定を変えた（例：dm_w→mhb_w）あと、既存の作品も高画質に入れ替えたいとき。
再生している元動画（sample.mp4）だけを差し替える。あなたが作った切り抜き
（cut_*.mp4）や抽出画像（NN.jpg）はそのまま残す。

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/redownload_movies.py            # 全作品
    python3 fanza_auto/scripts/redownload_movies.py smgd041    # cid 指定
    python3 fanza_auto/scripts/redownload_movies.py --force    # 既に目的画質でも落とし直す
"""

import subprocess
import sys

import common as C
from fetch_and_build import download_movie, movie_url, MOVIE_HEADERS
import requests


def current_height(mp4) -> int:
    """今の sample.mp4 の縦解像度。ffprobe が無ければ 0。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=height", "-of", "csv=p=0", str(mp4)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return int((out.stdout or "0").strip() or 0)
    except Exception:
        return 0


def remote_size(cid: str, quality: str) -> int:
    """指定画質の配信サイズ（bytes）。取れなければ 0。"""
    try:
        r = requests.get(movie_url(cid, quality), headers=MOVIE_HEADERS,
                         timeout=60, stream=True)
        ok = (r.status_code == 200
              and r.headers.get("Content-Type", "").startswith("video"))
        size = int(r.headers.get("Content-Length", 0)) if ok else 0
        r.close()
        return size
    except Exception:
        return 0


def main(argv) -> int:
    cfg = C.load_config()
    quality = cfg.get("movie_quality", "mhb_w")
    args = [a for a in argv[1:] if not a.startswith("-")]
    force = "--force" in argv[1:]

    dirs = C.work_dirs()
    if args:
        wanted = set(args)
        dirs = [d for d in dirs if C.cid_of(d) in wanted]
        if not dirs:
            print(f"該当する作品が見つかりません: {', '.join(args)}")
            return 1

    print(f"▶ sample.mp4 を画質 {quality} で入れ直し: 対象 {len(dirs)} 作品\n")
    done = skip = miss = 0
    for d in dirs:
        cid = C.cid_of(d)
        mp4 = d / "sample.mp4"
        before = current_height(mp4) if mp4.is_file() else 0

        # すでに配信サイズと同等（＝目的画質で持っている）ならスキップ（--force で無視）
        if not force and mp4.is_file():
            rsize = remote_size(cid, quality)
            if rsize and abs(mp4.stat().st_size - rsize) < rsize * 0.05:
                print(f"  ・{d.name} … 既に {quality} 相当（スキップ）")
                skip += 1
                continue

        if download_movie(cid, mp4, quality):
            after = current_height(mp4)
            print(f"  ✓ {d.name} … {before}p → {after}p")
            done += 1
        else:
            print(f"  ✗ {d.name} … 動画が取得できませんでした")
            miss += 1

    print(f"\n完了: 入れ替え {done} / スキップ {skip} / 失敗 {miss}")
    if done:
        print("  ※ 切り抜き(cut_*.mp4)・抽出画像は元のまま。ボードは再読み込みで反映されます。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
