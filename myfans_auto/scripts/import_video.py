# -*- coding: utf-8 -*-
"""
プロジェクトのルートフォルダに置いた動画ファイル（Chrome拡張機能でDLしたもの）を、
対応するMyFans作品フォルダへ `sample.mp4` として振り分けるツール。

ダウンロード拡張機能（FetchV Video Download 等）はブラウザのタブタイトルを
そのままファイル名にすることが多く、MyFansの投稿タイトルは
"《本文》 | 《投稿者》さんのプライベートSNS | myfans(マイファンズ)" という形。
これは og:title と同じ文字列（同じ位置で "..." に切られている）なので、
ファイル名の先頭部分と works/ 内の item.json の title を前方一致で突き合わせる。

1つの動画に対して候補が1件だけに絞れたときだけ自動で移動する。
0件（未取込の作品が無い）・複数件（あいまい）のときは移動せず、
どのファイルがどう判定されたかを結果として返す（呼び出し側＝サーバーが
ユーザーに見せて手動判断してもらう）。

使い方（単体実行・確認用）:
    python3 myfans_auto/scripts/import_video.py
"""

import re
import sys
from pathlib import Path

import common as C

VIDEO_EXTS = {".mp4", ".mov", ".m4v"}


def _norm(s: str) -> str:
    """比較用に空白・記号を落として緩く正規化する。"""
    return re.sub(r"[\s　（）()\[\]【】「」『』、。!！?？~〜・….,:;\"'-]+", "", (s or "").lower())


def find_inbox_videos(inbox_dir: Path) -> list:
    if not inbox_dir.is_dir():
        return []
    return sorted(p for p in inbox_dir.iterdir()
                  if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def candidates_for(video_path: Path, entries: list) -> list:
    """この動画ファイルに対応しそうな未取込（sample.mp4が無い）作品フォルダの候補を返す。
    ファイル名の正規化文字列が、作品タイトルの正規化文字列を先頭に含んでいるか
    （逆でもよい＝どちらかがどちらかの前方一致）で判定する。"""
    fname_norm = _norm(video_path.stem)
    hits = []
    for e in entries:
        if e["has_movie"]:
            continue
        title_norm = _norm(e["title"].rstrip("."))   # 末尾の"..."を落として比較を緩める
        creator_norm = _norm(e.get("creator") or "")
        if not title_norm:
            continue
        title_hit = fname_norm.startswith(title_norm) or title_norm.startswith(fname_norm)
        creator_hit = bool(creator_norm) and creator_norm in fname_norm
        if title_hit or creator_hit:
            hits.append(e)
    return hits


def import_videos(inbox_dir: Path, entries: list) -> dict:
    """inbox_dir 内の動画を候補にマッチさせ、確定したものだけ sample.mp4 として移動する。
    戻り値: {"moved": [{"file","dir","title"}], "ambiguous": [{"file","candidates":[title,...]}],
             "unmatched": [file,...]}"""
    result = {"moved": [], "ambiguous": [], "unmatched": []}
    videos = find_inbox_videos(inbox_dir)
    for v in videos:
        hits = candidates_for(v, entries)
        if len(hits) == 1:
            e = hits[0]
            dest = e["dir"] / "sample.mp4"
            v.replace(dest)
            e["has_movie"] = True   # 同じ動画が2つの候補に二重マッチしないようにする
            result["moved"].append({"file": v.name, "dir": e["dir"].name, "title": e["title"]})
        elif len(hits) == 0:
            result["unmatched"].append(v.name)
        else:
            result["ambiguous"].append({
                "file": v.name,
                "candidates": [h["title"] for h in hits],
            })
    return result


def main(argv=None) -> int:
    import board as BB   # 遅延import（単体実行時のみ必要）
    entries = BB.collect()
    r = import_videos(C.PROJECT_ROOT, entries)
    for m in r["moved"]:
        print(f"  ✓ 取り込み: {m['file']} → {m['dir']}/sample.mp4")
    for a in r["ambiguous"]:
        print(f"  ⚠️ 候補が複数あり判定できません: {a['file']} "
              f"→ {' / '.join(a['candidates'])}")
    for u in r["unmatched"]:
        print(f"  ・対応する作品が見つかりません（未取込のURLを先に取り込んでください）: {u}")
    if not (r["moved"] or r["ambiguous"] or r["unmatched"]):
        print("  ルートフォルダに動画ファイルがありません。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
