#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動画を指定した開始〜終了の区間でカットして保存する。

使い方:
    python3 cut_video.py <入力動画> <開始> <終了> [出力動画]

時間の指定:
    秒数         例) 5  /  12.5
    HH:MM:SS     例) 00:00:05  /  0:01:23.5

例:
    python3 cut_video.py input.mp4 5 12
    python3 cut_video.py "output/.../sample.mp4" 00:00:05 00:00:18 cut.mp4

仕様:
    - 音声を保持したまま、再エンコードで「フレーム正確」にカットする（-c copy より少し遅いが
      指定秒ピッタリで切れる）。
    - 出力先を省略した場合は、入力と同じフォルダに
      <元の名前>_cut_<開始>-<終了>.mp4 を作る。
"""
import os
import sys
import shutil
import subprocess


def parse_time(s: str) -> float:
    """秒数 or HH:MM:SS(.ms) を秒(float)に変換する。"""
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) > 3:
            raise ValueError(f"時間の形式が不正です: {s}")
        parts = [float(p) for p in parts]
        sec = 0.0
        for p in parts:
            sec = sec * 60 + p
        return sec
    return float(s)


def fmt_tag(sec: float) -> str:
    """ファイル名用に秒数を整形（5.0 -> 5, 12.5 -> 12.5）。"""
    if sec == int(sec):
        return str(int(sec))
    return str(sec).replace(".", "_")


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 1

    src = argv[1]
    start = parse_time(argv[2])
    end = parse_time(argv[3])

    if shutil.which("ffmpeg") is None:
        print("エラー: ffmpeg が見つかりません。`brew install ffmpeg` を実行してください。")
        return 1
    if not os.path.isfile(src):
        print(f"エラー: 入力動画が見つかりません: {src}")
        return 1
    if end <= start:
        print(f"エラー: 終了({end}s)は開始({start}s)より後にしてください。")
        return 1

    duration = end - start

    if len(argv) >= 5:
        dst = argv[4]
    else:
        base, _ = os.path.splitext(src)
        dst = f"{base}_cut_{fmt_tag(start)}-{fmt_tag(end)}.mp4"

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

    # -ss を入力前に置きつつ再エンコードすることで、高速かつフレーム正確にカットする。
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", src,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        dst,
    ]

    print(f"カット中: {src}")
    print(f"  区間: {start:g}s 〜 {end:g}s（{duration:g}秒）")
    print(f"  出力: {dst}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print("エラー: ffmpeg が失敗しました。")
        return proc.returncode

    size = os.path.getsize(dst)
    print(f"完了: {dst}（{size/1024/1024:.2f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
