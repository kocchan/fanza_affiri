#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
動画の「画面（フレーム）」を指定アスペクト比＋位置で切り取る（＝画面トリミング）。
任意で「開始〜終了」の時間トリムも同時にかけられる。

使い方:
    python3 crop_video.py <入力> <比率> <位置> [開始] [終了] [出力]

比率(aspect): 2通り
    ・W:H の形＝比率＋位置で自動計算。例）1:1 / 9:16 / 4:5 / 16:9
    ・x,y,w,h の形（カンマ4つ）＝画面上の切り取り範囲を直接ピクセルで指定（手動範囲選択）。
      この場合 位置(pos) は無視（"-" でよい）。
位置(pos)  : center / left / right / top / bottom
             （横長を縦に切るときは left/center/right、縦を横に切るときは top/center/bottom が効く）
時間        : 秒数（5, 12.5）または HH:MM:SS。開始・終了の両方を渡すとその区間だけにする。

例:
    python3 crop_video.py sample.mp4 1:1 center
    python3 crop_video.py sample.mp4 9:16 center 3 12
    python3 crop_video.py sample.mp4 4:5 left 0 8 out.mp4

仕様:
    - フレーム正確・音声保持で再エンコード（cut_video.py と同じ方針）。
    - 出力先を省略すると入力と同じフォルダに crop_<比率>_<位置>[_<開始>-<終了>].mp4 を作る。
"""
import os
import shutil
import subprocess
import sys

from cut_video import parse_time, fmt_tag


def probe_size(path: str):
    """動画の (幅, 高さ) を返す。取れなければ (0, 0)。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        w, h = (out.stdout or "").strip().split(",")[:2]
        return int(w), int(h)
    except Exception:
        return 0, 0


def crop_rect(W: int, H: int, aspect: str, pos: str):
    """元 WxH を aspect(W:H) の比率で最大内接するよう切り取る矩形 (cw, ch, x, y)。"""
    aw, ah = (float(x) for x in aspect.split(":"))
    target = aw / ah
    if W / H > target:
        # 元が目標より横長 → 幅を削る（左右position）
        ch = H
        cw = round(H * target)
    else:
        # 元が目標より縦長 → 高さを削る（上下position）
        cw = W
        ch = round(W / target)
    cw = min(cw, W)
    ch = min(ch, H)
    # 偶数に丸める（H.264 は幅高さ偶数が必要）
    cw -= cw % 2
    ch -= ch % 2

    if pos == "left":
        x = 0
    elif pos == "right":
        x = W - cw
    else:
        x = (W - cw) // 2
    if pos == "top":
        y = 0
    elif pos == "bottom":
        y = H - ch
    else:
        y = (H - ch) // 2
    return cw, ch, x, y


def main(argv):
    if len(argv) < 4:
        print(__doc__)
        return 1

    src = argv[1]
    spec = argv[2]          # "W:H"（比率）または "x,y,w,h"（手動範囲）
    pos = argv[3]
    start = argv[4] if len(argv) >= 5 and argv[4] not in ("", "-") else None
    end = argv[5] if len(argv) >= 6 and argv[5] not in ("", "-") else None
    out = argv[6] if len(argv) >= 7 else None

    if shutil.which("ffmpeg") is None:
        print("エラー: ffmpeg が見つかりません。`brew install ffmpeg` を実行してください。")
        return 1
    if not os.path.isfile(src):
        print(f"エラー: 入力動画が見つかりません: {src}")
        return 1

    W, H = probe_size(src)
    if not W or not H:
        print("エラー: 動画の解像度が取得できませんでした（ffprobe）。")
        return 1

    manual = spec.count(",") == 3     # "x,y,w,h" 形式＝手動範囲選択
    if manual:
        try:
            x, y, cw, ch = (int(round(float(v))) for v in spec.split(","))
        except ValueError:
            print(f"エラー: 範囲は x,y,w,h の数値で指定してください: {spec}")
            return 1
        # 画面内に収め、幅高さは偶数に丸める（H.264の要件）
        x = max(0, min(x, W - 2))
        y = max(0, min(y, H - 2))
        cw = max(2, min(cw, W - x)) & ~1
        ch = max(2, min(ch, H - y)) & ~1
        tag = f"crop_sel_{x}_{y}_{cw}x{ch}"
        desc = f"手動範囲 {cw}x{ch} @({x},{y})"
    else:
        if ":" not in spec:
            print(f"エラー: 比率は W:H（例 1:1）か、範囲 x,y,w,h で指定してください: {spec}")
            return 1
        if pos not in ("center", "left", "right", "top", "bottom"):
            print(f"エラー: 位置は center/left/right/top/bottom のいずれか: {pos}")
            return 1
        cw, ch, x, y = crop_rect(W, H, spec, pos)
        tag = f"crop_{spec.replace(':', 'x')}_{pos}"
        desc = f"切り取り {cw}x{ch}（位置 {pos} / 比率 {spec}）"

    # 出力名
    if out is None:
        base, _ = os.path.splitext(src)
        if start is not None and end is not None:
            tag += f"_{fmt_tag(parse_time(start))}-{fmt_tag(parse_time(end))}"
        out = f"{base}_{tag}.mp4"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    cmd = ["ffmpeg", "-y"]
    # 時間トリムも同時に指定されていれば区間を切る
    if start is not None and end is not None:
        s = parse_time(start)
        e = parse_time(end)
        if e <= s:
            print(f"エラー: 終了({e}s)は開始({s}s)より後にしてください。")
            return 1
        cmd += ["-ss", f"{s:.3f}", "-i", src, "-t", f"{e - s:.3f}"]
    else:
        cmd += ["-i", src]
    cmd += [
        "-vf", f"crop={cw}:{ch}:{x}:{y}",
        # 画質優先：crf 18（ほぼ視覚劣化なし）＋ preset medium（速度と画質のバランス）。
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        out,
    ]

    print(f"画面トリミング: {src}")
    print(f"  元 {W}x{H} → {desc}")
    if start is not None and end is not None:
        print(f"  区間: {parse_time(start):g}s 〜 {parse_time(end):g}s")
    print(f"  出力: {out}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0 or not os.path.isfile(out):
        print(proc.stdout)
        print("エラー: ffmpeg が失敗しました。")
        return proc.returncode or 1

    size = os.path.getsize(out)
    print(f"完了: {out}（{size/1024/1024:.2f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
