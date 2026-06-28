#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
競合分析が終わったスクリーンショットを「完了」フォルダへ移動する。

競合分析スキルの最後に呼ぶ：
  python3 archive_done.py [サブフォルダ名]

仕組み:
  - `競合分析/` 直下のスクショ（*.png）＝「未処理キュー」とみなす。
  - 解析が終わったらこのスクリプトで `競合分析/完了/[サブフォルダ名]/` へ移動する。
  - 拡大版 `_zoom/*.png` も併せて `完了/[サブフォルダ名]/_zoom/` へ移動する。
  - スワイプファイル（競合分析_*.md）は成果物なので動かさない。
  → 次回スキルを使うと、直下に残っている未処理スクショだけを解析すればよい状態になる。

サブフォルダ名を省略すると `完了/` 直下へ移動する（実行日でまとめたいときは
スキル側から日付 "2026-06-22" のように渡す）。
"""
import os
import sys
import shutil
from pathlib import Path

# このスクリプトは <root>/.claude/skills/competitor-analysis/ に置かれている
ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "競合分析"
DONE = BASE / "完了"


def unique_dest(dst: Path) -> Path:
    """同名ファイルがあれば _2, _3 … を付けて衝突回避。"""
    if not dst.exists():
        return dst
    stem, suf = dst.stem, dst.suffix
    i = 2
    while True:
        cand = dst.with_name(f"{stem}_{i}{suf}")
        if not cand.exists():
            return cand
        i += 1


def main(argv):
    if not BASE.is_dir():
        print(f"エラー: 競合分析フォルダが見つかりません: {BASE}")
        return 1

    sub = argv[1].strip("/ ") if len(argv) >= 2 and argv[1].strip() else ""
    dest_dir = DONE / sub if sub else DONE
    dest_zoom = dest_dir / "_zoom"

    # 直下のスクショ（*.png）＝未処理キュー
    shots = sorted(p for p in BASE.glob("*.png") if p.is_file())
    zooms = sorted(p for p in (BASE / "_zoom").glob("*.png")) if (BASE / "_zoom").is_dir() else []

    if not shots and not zooms:
        print("移動対象のスクショはありません（すでに完了済み）。")
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for p in shots:
        d = unique_dest(dest_dir / p.name)
        shutil.move(str(p), str(d))
        print(f"  → 完了/{(sub + '/') if sub else ''}{d.name}")
        moved += 1
    if zooms:
        dest_zoom.mkdir(parents=True, exist_ok=True)
        for p in zooms:
            d = unique_dest(dest_zoom / p.name)
            shutil.move(str(p), str(d))
            moved += 1
        print(f"  → 拡大版 {len(zooms)}枚を 完了/{(sub + '/') if sub else ''}_zoom/ へ")

    print(f"✓ {moved}個を完了フォルダへ移動しました: {dest_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
