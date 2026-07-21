#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
品番（例: simw003）が MissAV に上がっているかどうかを内部確認するツール。

やること:
  https://missav.live/ja/search/<品番> を（見えないブラウザで）開いて判定する。
  普通の requests では Cloudflare のボット判定で弾かれるため、Playwright で
  実ブラウザを動かして確認する。

判定ロジック（サイトの実際の挙動から）:
  - 完全一致がある場合 … サーバーがその場で結果一覧を描画する（静的なリンク）。
  - 完全一致が無い場合 … サイトは「関連候補」を JS で後から描画する
    （Alpine.js + Recombee のレコメンドAPI・数秒遅れて出る）。
  この描画方式の違いで「あり／なし」を区別する（表示テキストの品番が完全一致するかも
  念のため突き合わせる）。

使い方:
    python3 fanza_auto/scripts/check_missav.py simw003
    python3 fanza_auto/scripts/check_missav.py orecz600

注意:
  - この機能は「MissAVに上がっているかどうかを内部で確認する」用途のみ。
    動画の視聴・ダウンロード・リンク案内は一切行わない。
"""

import datetime
import re
import sys

import common as C

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SEARCH_URL = "https://missav.live/ja/search/{code}"

# 完全一致時：サーバーが直接描画する結果リンク（Alpineのx-text束縛が付いていないもの）
DIRECT_SEL = "div.my-2.text-sm.text-nord4.truncate > a:not([x-text])"
# 完全一致が無い時：JSで後から描画される「関連候補」（Recombeeレコメンド）
RECOMMEND_SEL = 'a[x-text="item.full_title"]'

NAV_TIMEOUT_MS = 30000
DIRECT_WAIT_MS = 4000
RECOMMEND_WAIT_MS = 9000
RECOMMEND_SETTLE_MS = 2500


def _normalize(s: str) -> str:
    """品番の表記ゆれ（ハイフン・大小文字）を無視して比較するための正規化。"""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _leading_code(text: str):
    """"SIMW-003 めい" のような表示テキストから先頭の品番トークンを取り出す。"""
    m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9\-]*)", text or "")
    return m.group(1) if m else ""


def search_missav(code: str, headless: bool = True) -> dict:
    """品番 code がMissAVに存在するか確認する。

    戻り値:
        {"code", "url", "found" (True/False/None), "status" (found/not_found/error),
         "matches": [完全一致した表示タイトル,...],
         "related": [参考として出た関連候補タイトル,...], "error"}
    """
    code = (code or "").strip()
    norm_query = _normalize(code)
    url = SEARCH_URL.format(code=code)
    result = {"code": code, "url": url, "found": None, "status": "error",
              "matches": [], "related": [], "error": None}
    if not code:
        result["error"] = "品番が空です"
        return result

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["error"] = ("playwright が入っていません。"
                           "`pip3 install --break-system-packages playwright` と "
                           "`python3 -m playwright install chromium` を実行してください。")
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            try:
                page = browser.new_page(locale="ja-JP", user_agent=UA)
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

                # 完全一致ならここですぐ描画される
                try:
                    page.wait_for_selector(DIRECT_SEL, timeout=DIRECT_WAIT_MS)
                except Exception:
                    pass
                direct_texts = [t.strip() for t in page.eval_on_selector_all(
                    DIRECT_SEL, "els => els.map(e => e.textContent)") if t and t.strip()]

                if direct_texts:
                    matches = [t for t in direct_texts
                               if _normalize(_leading_code(t)) == norm_query]
                    result["matches"] = matches or direct_texts
                    result["found"] = bool(matches)
                    result["status"] = "found" if matches else "not_found"
                    return result

                # 完全一致が描画されない＝サイトは「関連候補」に切り替える。
                # これがJSで出てくるまで少し待つ。
                try:
                    page.wait_for_selector(RECOMMEND_SEL, timeout=RECOMMEND_WAIT_MS)
                    page.wait_for_timeout(RECOMMEND_SETTLE_MS)
                except Exception:
                    pass
                recommend_texts = [t.strip() for t in page.eval_on_selector_all(
                    RECOMMEND_SEL, "els => els.map(e => e.textContent)") if t and t.strip()]

                exact_in_recommend = [t for t in recommend_texts
                                      if _normalize(_leading_code(t)) == norm_query]
                if exact_in_recommend:
                    result["matches"] = exact_in_recommend
                    result["found"] = True
                    result["status"] = "found"
                else:
                    result["related"] = recommend_texts[:8]
                    result["found"] = False
                    result["status"] = "not_found"
                return result
            finally:
                browser.close()
    except Exception as ex:
        result["error"] = str(ex)
        return result


def check_and_cache(work_dir) -> dict:
    """作品フォルダの item.json を読んでMissAVを確認し、結果を item.json にキャッシュする。
    board_<cid>.html / dashboard.html の「MissAVを確認」ボタン（serve_board.py の
    /__missav）から呼ばれる。"""
    item = C.read_item(work_dir)
    cid = item.get("content_id") or C.cid_of(work_dir)
    r = search_missav(cid)
    cached = {
        "status": r["status"],
        "found": r["found"],
        "matches": r["matches"],
        "related": r["related"],
        "checked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if r["status"] == "error":
        cached["error"] = r["error"]
        return cached
    item["missav"] = cached
    C.write_item(work_dir, item)
    return cached


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("使い方: python3 fanza_auto/scripts/check_missav.py <品番>")
        print("  例) python3 fanza_auto/scripts/check_missav.py simw003")
        return 1
    code = argv[0]
    print(f"🔍 MissAVで「{code}」を検索中…（数秒かかります）")
    r = search_missav(code)

    if r["status"] == "error":
        print(f"✗ 確認に失敗しました: {r['error']}")
        return 2

    if r["found"]:
        print(f"⚠️ あり：MissAVに一致する動画が見つかりました（{r['code']}）")
        for t in r["matches"][:5]:
            print(f"   - {t}")
    else:
        print(f"✓ なし：MissAVに一致する動画は見つかりませんでした（{r['code']}）")
        if r["related"]:
            print("  （参考：関連候補として表示されたタイトル。品番は一致していません）")
            for t in r["related"][:5]:
                print(f"   - {t}")
    print(f"  確認先: {r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
