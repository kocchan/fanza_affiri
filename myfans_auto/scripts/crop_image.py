#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静止画（jpg）を指定アスペクト比＋位置、または手動範囲で切り取る（サムネ用トリミング）。
crop_video.py の画像版。Pillow で処理する（劣化を避けるため再圧縮品質は高め）。

使い方:
    python3 crop_image.py <入力.jpg> <比率 または x,y,w,h> [位置] [出力.jpg]

比率(aspect): 2通り
    ・W:H の形＝比率＋位置で自動計算。例）1:1 / 9:16 / 4:5 / 16:9
    ・x,y,w,h の形（カンマ4つ）＝画面上の切り取り範囲を直接ピクセルで指定（手動範囲選択）。
      この場合 位置(pos) は無視（"-" でよい）。
位置(pos): center / left / right / top / bottom

例:
    python3 crop_image.py 01.jpg 1:1 center
    python3 crop_image.py 01.jpg 200,50,480,480 -

仕様:
    - 出力先を省略すると入力と同じフォルダに thumb_<比率or範囲>.jpg を作る。
    - JPEG品質98・4:4:4（色間引きなし）で保存（サムネ用にほぼ無劣化）。
"""
import os
import sys

from PIL import Image


def crop_rect(W: int, H: int, aspect: str, pos: str):
    """元 WxH を aspect(W:H) の比率で最大内接するよう切り取る矩形 (x0, y0, x1, y1)。"""
    aw, ah = (float(x) for x in aspect.split(":"))
    target = aw / ah
    if W / H > target:
        ch = H
        cw = round(H * target)
    else:
        cw = W
        ch = round(W / target)
    cw = min(cw, W)
    ch = min(ch, H)

    if pos == "left":
        x0 = 0
    elif pos == "right":
        x0 = W - cw
    else:
        x0 = (W - cw) // 2
    if pos == "top":
        y0 = 0
    elif pos == "bottom":
        y0 = H - ch
    else:
        y0 = (H - ch) // 2
    return x0, y0, x0 + cw, y0 + ch


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1

    src = argv[1]
    spec = argv[2]              # "W:H"（比率）または "x,y,w,h"（手動範囲）
    pos = argv[3] if len(argv) >= 4 and argv[3] not in ("", "-") else "center"
    out = argv[4] if len(argv) >= 5 else None

    if not os.path.isfile(src):
        print(f"エラー: 入力画像が見つかりません: {src}")
        return 1

    try:
        img = Image.open(src)
        img.load()
    except Exception as e:
        print(f"エラー: 画像を開けませんでした: {e}")
        return 1
    W, H = img.size

    manual = spec.count(",") == 3
    if manual:
        try:
            x, y, cw, ch = (float(v) for v in spec.split(","))
        except ValueError:
            print(f"エラー: 範囲は x,y,w,h の数値で指定してください: {spec}")
            return 1
        x = max(0, min(x, W - 1))
        y = max(0, min(y, H - 1))
        cw = max(1, min(cw, W - x))
        ch = max(1, min(ch, H - y))
        box = (int(x), int(y), int(x + cw), int(y + ch))
        tag = f"sel_{int(x)}_{int(y)}_{int(cw)}x{int(ch)}"
        desc = f"手動範囲 {int(cw)}x{int(ch)} @({int(x)},{int(y)})"
    else:
        if ":" not in spec:
            print(f"エラー: 比率は W:H（例 1:1）か、範囲 x,y,w,h で指定してください: {spec}")
            return 1
        if pos not in ("center", "left", "right", "top", "bottom"):
            print(f"エラー: 位置は center/left/right/top/bottom のいずれか: {pos}")
            return 1
        box = crop_rect(W, H, spec, pos)
        tag = f"{spec.replace(':', 'x')}_{pos}"
        desc = f"切り取り {box[2]-box[0]}x{box[3]-box[1]}（位置 {pos} / 比率 {spec}）"

    if out is None:
        base, _ = os.path.splitext(src)
        out = f"{os.path.dirname(base) or '.'}/thumb_{tag}.jpg"
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    cropped = img.convert("RGB").crop(box)
    # 高画質優先：quality=98（ほぼ無劣化）＋ subsampling=0（4:4:4・色情報を間引かない）。
    cropped.save(out, "JPEG", quality=98, subsampling=0)

    print(f"画像トリミング: {src}")
    print(f"  元 {W}x{H} → {desc}")
    print(f"  出力: {out}")
    print(f"完了: {out}（{os.path.getsize(out)/1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
