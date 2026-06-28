#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1作品フォルダの sample.mp4 から「いま使っていない別の規制セーフ画像」を1枚選び直す。

HTML の「🔄再選出」ボタン → serve.py → 本スクリプトが呼ばれる想定。
  python3 reselect.py <作品フォルダ>

仕組み:
  - 初回は sample.mp4 から候補を多めに抽出して <フォルダ>/_pool/ に貯める（重いのは初回だけ）。
  - フォルダ内の既存画像（NN.jpg / alt_*.jpg）と見た目が重複しない候補を aHash で判定し、
    まだ使っていない最良候補を alt_<連番>.jpg としてコピーする。
  - 出力は JSON 1行（{"ok":true,"file":"alt_3.jpg"} など）。

候補が尽きたら {"ok":false,"error":"候補がもうありません"} を返す。
"""
import sys
import json
import shutil
from pathlib import Path

import cv2

from extract_safe_frames import extract_safe_frames

POOL_TOP_N = 24          # プールに貯める候補数（多めに抽出）
HASH_HAMMING_DUP = 5     # aHash のハミング距離がこれ以下なら「同じ画像」とみなす


def ahash(path) -> int:
    """8x8 平均ハッシュ。読めなければ 0 を返す。"""
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0
    small = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA)
    avg = small.mean()
    bits = 0
    for v in small.flatten():
        bits = (bits << 1) | (1 if v >= avg else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def is_dup(h: int, existing: list) -> bool:
    return any(hamming(h, e) <= HASH_HAMMING_DUP for e in existing)


def current_images(folder: Path) -> list:
    """フォルダ直下のチョイス済み画像（NN.jpg, alt_*.jpg）。プールは含めない。"""
    imgs = sorted(folder.glob("[0-9][0-9].jpg"))
    imgs += sorted(folder.glob("alt_*.jpg"))
    return imgs


def next_alt_index(folder: Path) -> int:
    n = 0
    for p in folder.glob("alt_*.jpg"):
        try:
            n = max(n, int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return n + 1


def build_pool(folder: Path) -> Path:
    """_pool/ が無ければ sample.mp4 から候補を抽出して作る。"""
    pool = folder / "_pool"
    if pool.exists() and any(pool.glob("safe_*.jpg")):
        return pool
    mp4 = folder / "sample.mp4"
    if not mp4.is_file():
        return pool  # 空のまま返す（呼び出し側でエラーにする）
    extract_safe_frames(
        mp4, pool, top_n=POOL_TOP_N, max_samples=POOL_TOP_N * 4,
        strict=True, verbose=False)
    return pool


def reselect(folder: Path) -> dict:
    if not folder.is_dir():
        return {"ok": False, "error": "フォルダが見つかりません"}
    if not (folder / "sample.mp4").is_file():
        return {"ok": False, "error": "sample.mp4 が無いため再選出できません"}

    pool = build_pool(folder)
    pool_imgs = sorted(pool.glob("safe_*.jpg"))
    if not pool_imgs:
        return {"ok": False, "error": "候補を抽出できませんでした"}

    # 既に使っている画像のハッシュ（重複回避の基準）
    used_hashes = [ahash(p) for p in current_images(folder)]

    for cand in pool_imgs:
        h = ahash(cand)
        if is_dup(h, used_hashes):
            continue
        idx = next_alt_index(folder)
        out_name = f"alt_{idx}.jpg"
        shutil.copyfile(cand, folder / out_name)
        return {"ok": True, "file": out_name}

    return {"ok": False, "error": "候補がもうありません（プールを使い切りました）"}


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"ok": False, "error": "フォルダ未指定"}, ensure_ascii=False))
        return 1
    result = reselect(Path(argv[1]).resolve())
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
