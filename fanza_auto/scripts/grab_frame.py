#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動画の指定時刻のフレームを1枚の画像として切り抜く（静止画キャプチャ）。

HTML の「📷 画像切り抜き」ボタン → serve.py → 本スクリプトが呼ばれる想定。
  python3 grab_frame.py <入力動画> <秒 or HH:MM:SS> [出力.jpg]

仕様:
  - ffmpeg で指定時刻の1フレームを高画質(jpg)で書き出す。
  - 出力先を省略した場合は、入力と同じフォルダに clip_<秒>.jpg を作る。
"""
import os
import sys
import shutil
import subprocess

from cut_video import parse_time, fmt_tag


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1

    src = argv[1]
    sec = parse_time(argv[2])

    if shutil.which("ffmpeg") is None:
        print("エラー: ffmpeg が見つかりません。`brew install ffmpeg` を実行してください。")
        return 1
    if not os.path.isfile(src):
        print(f"エラー: 入力動画が見つかりません: {src}")
        return 1
    if sec < 0:
        print(f"エラー: 時刻は0以上にしてください: {sec}")
        return 1

    if len(argv) >= 4:
        dst = argv[3]
    else:
        dst = os.path.join(os.path.dirname(os.path.abspath(src)),
                           f"clip_{fmt_tag(sec)}s.jpg")

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

    # -ss を入力前に置いて高速シーク、その時刻の1フレームを書き出す。
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{sec:.3f}",
        "-i", src,
        "-frames:v", "1",
        "-q:v", "1",   # ffmpegの静止画品質は 1=最高〜31=最低。サムネ用に最高品質にする。
        dst,
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0 or not os.path.isfile(dst):
        print(proc.stdout)
        print("エラー: ffmpeg が失敗しました。")
        return proc.returncode or 1

    print(f"完了: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
