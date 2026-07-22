# -*- coding: utf-8 -*-
"""
MyFansボード用の共通の土台（works/ の走査・item.json の読み書き・アーカイブボタンHTML）。

fanza_auto/scripts/common.py の同名関数と役割は同じだが、MyFansには
DMMのようなAPI認証・config.json・アフィリンク書き換え（af_id等）・bit.ly短縮・
MissAV確認は存在しないため、それらは持たない軽量版。
"""

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # myfans_auto/
PROJECT_ROOT = ROOT.parent                          # プロジェクト直下
WORKS_DIR = ROOT / "works"

# 投稿文の言い回し（templates.py の REACTION_HOOKS/SUB_LINE/BOOSTER_POOL）と
# post_text.py の文組み立てロジックは、作品データが無くても固定リアクション文に
# フォールバックする汎用的な作りなので、書き直さずFANZA側のものをそのまま使う。
sys.path.insert(0, str(PROJECT_ROOT / "fanza_auto" / "scripts"))

ITEM_JSON = "item.json"
POST_MD = "投稿内容.md"


# ──────────────────────────────────────────────
# works/ の走査
# ──────────────────────────────────────────────
def work_dirs(works_dir: Path = None) -> list:
    """works/ 配下の作品フォルダを名前順で返す（投稿内容.md があるものだけ）。"""
    works_dir = works_dir or WORKS_DIR
    if not works_dir.is_dir():
        return []
    found = {p.parent for p in works_dir.rglob(POST_MD)}
    return sorted(found, key=lambda d: d.name)


def cid_of(work_dir: Path) -> str:
    """フォルダ名 <投稿ID>_<作品名> から投稿IDを取り出す。"""
    return work_dir.name.split("_")[0]


def read_item(work_dir: Path) -> dict:
    path = work_dir / ITEM_JSON
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_item(work_dir: Path, item: dict) -> None:
    (work_dir / ITEM_JSON).write_text(
        json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")


# ──────────────────────────────────────────────
# アーカイブ操作ボタン（board.html / board_<cid>.html で共通・fanza_autoと同仕様）
# ──────────────────────────────────────────────
def archive_block_html(api_dir: str, archived: bool) -> str:
    dir_esc = html.escape(api_dir)
    if archived:
        return (f'<span class="archive-actions" data-dir="{dir_esc}">'
                f'<button class="delete-btn" data-dir="{dir_esc}">🗑 完全削除</button>'
                f'<button class="unarchive-btn" data-dir="{dir_esc}">↩ 全体ボードに戻す</button>'
                f'</span>')
    return (f'<span class="archive-actions" data-dir="{dir_esc}">'
            f'<button class="archive-btn" data-dir="{dir_esc}">📦 アーカイブ</button>'
            f'</span>')
