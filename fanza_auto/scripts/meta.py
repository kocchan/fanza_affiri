#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作品のメタ情報（タイトル・収録時間・レビュー・発売日・ジャンル・メーカー）を
DMMアフィリエイトAPIから取り直して、作品フォルダに `item.json` として保存する。

もともと works/ には画像・sample.mp4・投稿内容.md しか残っておらず、
「どんな作品なのか」の情報が消えていた。投稿文をその作品らしく書くには
この情報が要るので、ここで拾い直して常に手元に置いておく。

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/meta.py            # item.json が無い作品だけ埋める
    python3 fanza_auto/scripts/meta.py --all      # 全作品を取り直す（情報の更新）
    python3 fanza_auto/scripts/meta.py deas009    # cid を指定して個別に取り直す
"""

import sys
import time

import requests

import common as C

API_ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"

# cid だけでは作品がどのフロアか分からないので、設定のフロア→よく使う順に探す。
FLOOR_CANDIDATES = ["videoc", "videoa", "videob"]

REQUEST_INTERVAL = 0.3   # APIへの連続アクセスを軽く空ける


def fetch_item_by_cid(cid: str, cfg: dict) -> dict:
    """cid 1件ぶんのメタ情報を取得する。見つからなければ空 dict。"""
    floors = [cfg.get("floor")] + [f for f in FLOOR_CANDIDATES
                                   if f != cfg.get("floor")]
    for floor in floors:
        if not floor:
            continue
        params = {
            "api_id": cfg["api_id"],
            "affiliate_id": cfg["affiliate_id"],
            "site": cfg["site"],
            "service": cfg["service"],
            "floor": floor,
            "cid": cid,
            "hits": 1,
            "output": "json",
        }
        try:
            r = requests.get(API_ENDPOINT, params=params, timeout=30)
            r.raise_for_status()
            result = r.json().get("result", {})
        except Exception as e:
            print(f"  ! {cid}: 取得に失敗（floor={floor}） {e}")
            continue
        if str(result.get("status")) != "200":
            continue
        items = result.get("items") or []
        if items:
            return items[0]
        time.sleep(REQUEST_INTERVAL)
    return {}


def enrich(item: dict, cfg: dict) -> dict:
    """保存前に、投稿づくりで使う値を整えて足しておく。"""
    item = dict(item)
    # APIが返すリンクは af_id が既定値なので、config.json の設定で上書きする
    item["affiliateURL"] = C.rewrite_aff_url(item.get("affiliateURL", ""), cfg)
    return item


def update_work(work_dir, cfg: dict, force: bool = False) -> str:
    """1作品ぶんの item.json を作る。戻り値は "saved" / "skip" / "miss"。"""
    if not force and C.read_item(work_dir):
        return "skip"
    cid = C.cid_of(work_dir)
    item = fetch_item_by_cid(cid, cfg)
    if not item:
        print(f"  ✗ {work_dir.name} … cid={cid} が API で見つからなかった"
              "（配信終了の可能性）")
        return "miss"
    C.write_item(work_dir, enrich(item, cfg))
    review = item.get("review") or {}
    print(f"  ✓ {work_dir.name} … {item.get('title', '?')} "
          f"／★{review.get('average', '-')}（{review.get('count', 0)}件）"
          f"／{item.get('volume', '-')}")
    return "saved"


def main(argv) -> int:
    cfg = C.load_config()
    args = [a for a in argv[1:] if not a.startswith("-")]
    force = "--all" in argv[1:]

    dirs = C.work_dirs()
    if args:
        wanted = set(args)
        dirs = [d for d in dirs if C.cid_of(d) in wanted]
        force = True
        if not dirs:
            print(f"該当する作品フォルダが見つかりません: {', '.join(args)}")
            return 1

    if not dirs:
        print("works/ に作品フォルダがありません。")
        return 1

    mode = "全作品を取り直し" if force else "item.json が無い作品だけ取得"
    print(f"作品メタ情報の取得（{mode}）: {len(dirs)} 件")

    counts = {"saved": 0, "skip": 0, "miss": 0}
    for d in dirs:
        counts[update_work(d, cfg, force=force)] += 1

    print(f"\n完了: 保存 {counts['saved']} 件 / "
          f"取得済みスキップ {counts['skip']} 件 / 見つからず {counts['miss']} 件")
    if counts["miss"]:
        print("※ 見つからなかった作品は配信終了の可能性。"
              "ボードには投稿内容.md の情報だけで表示されます。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
