# -*- coding: utf-8 -*-
"""
スクリプト共通の土台（設定読み込み・アフィリリンク整形・works/ の走査）。

ここに置いているのは「重い依存を持たない」処理だけ。
`fetch_and_build.py` は nudenet（画像判定）を読み込むため起動が重いので、
ボード生成やメタ取得はこのモジュールだけを使って軽く動くようにしている。
"""

import html
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent      # fanza_auto/
PROJECT_ROOT = ROOT.parent                          # プロジェクト直下
WORKS_DIR = ROOT / "works"

ITEM_JSON = "item.json"        # 作品フォルダに置くメタ情報（DMM APIの生データ）
POST_MD = "投稿内容.md"

DEFAULT_CONFIG = {
    "site": "FANZA",
    "service": "digital",
    "floor": "videoa",
    "sort": "rank",
    "fetch_count": 100,
    "posts_per_day": 20,
    "avoid_repeats": True,
    "sample_images_per_item": 20,
    "images_per_post": 10,
    "post_slots": ["夜", "朝"],
    "download_movie": True,
    "movie_quality": "dm_w",
    "movie_all": False,
    "extract_safe": True,
    "safe_frames_top_n": 10,
    # ★ユーザー方針（2026-07-20）：bit.ly短縮は使わず、元のフルURLをそのまま使う。
    #   shorten_url() はこのフラグを見て、false なら何もせず元URLを返す。
    "shorten_links": False,
    "aff_link": {
        "af_id": "mokumoku555-001",
        "ch": "reward_ranking",
        "ch_id": "link",
    },
    "accounts": {"main": "MAIN", "sub": "SUB", "boosters": ["B1", "B2", "B3"]},
}


def load_env(env_path: Path = None) -> dict:
    """シンプルな .env パーサ（KEY=VALUE 形式）"""
    env_path = env_path or (PROJECT_ROOT / ".env")
    data = {}
    if not env_path.exists():
        return data
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def load_config(require_api: bool = True) -> dict:
    """config.json ＋ .env を読んで設定を組み立てる。

    require_api=False なら API 認証が無くても落ちない（ボード生成など
    ネットを使わない用途はこちら）。
    """
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))   # deep copy
    cfg_path = ROOT / "config.json"
    if cfg_path.exists():
        cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))

    env = load_env()
    api_id = cfg.get("api_id") or env.get("DMM_API_ID")
    aff_id = cfg.get("affiliate_id") or env.get("DMM_AFFILIATE_ID")
    if require_api and not (api_id and aff_id):
        sys.exit("✗ API_ID / AFFILIATE_ID が見つかりません。"
                 ".env か config.json に設定してください。")
    cfg["api_id"] = api_id
    cfg["affiliate_id"] = aff_id
    cfg["bitly_token"] = cfg.get("bitly_token") or env.get("BITLY_TOKEN")
    return cfg


BITLY_API = "https://api-ssl.bitly.com/v4/shorten"


def shorten_url(url: str, cfg: dict) -> str:
    """アフィリンクを bit.ly で短縮する。config.json の shorten_links が false
    （既定）なら何もせず元のフルURLを返す。トークン未設定・失敗時も同様に元URLのまま
    （短縮は任意機能なので、失敗しても投稿文生成自体は止めない）。"""
    cfg = cfg or {}
    if not cfg.get("shorten_links", False):
        return url
    token = cfg.get("bitly_token")
    if not url or not token:
        return url
    try:
        import requests
        r = requests.post(
            BITLY_API,
            headers={"Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"},
            json={"long_url": url}, timeout=10)
        # bit.ly は新規作成成功で 201（既存URLの再取得で200）を返す。両方成功扱い。
        if r.status_code in (200, 201):
            return r.json().get("link") or url
        print(f"  ! bit.ly短縮に失敗（status={r.status_code}）: {r.text[:200]}")
    except Exception as e:
        print(f"  ! bit.ly短縮に失敗: {e}")
    return url


def rewrite_aff_url(url: str, cfg: dict) -> str:
    """APIが返す affiliateURL の af_id / ch / ch_id を config 設定で上書きする。
    lurl（遷移先）はそのまま維持する。設定が無ければ元のURLを返す。"""
    overrides = (cfg or {}).get("aff_link") or {}
    if not url or not overrides:
        return url
    parts = urlsplit(url)
    # keep_blank_values: lurl のエンコード済みクエリを壊さないため
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key in ("af_id", "ch", "ch_id"):
        if overrides.get(key) is not None:
            query[key] = overrides[key]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(query), parts.fragment))


# ──────────────────────────────────────────────
# works/ の走査
# ──────────────────────────────────────────────
def work_dirs(works_dir: Path = None) -> list:
    """works/ 配下の作品フォルダを名前順で返す（投稿内容.md があるものだけ）。

    サブフォルダ（例：works/進行中/<cid>_.../）に入れた作品も見つけられるよう、
    直下だけでなく再帰的に探す（rglob）。"""
    works_dir = works_dir or WORKS_DIR
    if not works_dir.is_dir():
        return []
    found = {p.parent for p in works_dir.rglob(POST_MD)}
    return sorted(found, key=lambda d: d.name)


def cid_of(work_dir: Path) -> str:
    """フォルダ名 <cid>_<作品名> から cid を取り出す。
    旧形式 <連番>_<作品名>_<cid> にも後方互換で対応する。"""
    parts = work_dir.name.split("_")
    if len(parts) >= 3 and parts[0].isdigit():
        return parts[-1]
    return parts[0]


def read_item(work_dir: Path) -> dict:
    """作品フォルダの item.json を読む。無ければ空 dict。"""
    path = work_dir / ITEM_JSON
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_item(work_dir: Path, item: dict) -> None:
    """作品フォルダに item.json を保存する。"""
    (work_dir / ITEM_JSON).write_text(
        json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")


# ──────────────────────────────────────────────
# MissAV確認ボタン（board_<cid>.html / dashboard.html で共通の見た目）
#   実際のチェック処理（check_missav.py・Playwright）はサーバー側
#   （serve_board.py の /__missav）でのみ動く。ここは表示用のHTMLだけ組み立てる。
#   結果は item.json の "missav" にキャッシュされ、再チェックするまで使い回す。
# ──────────────────────────────────────────────
def missav_block_html(item: dict, api_dir: str, uid: str) -> str:
    cached = (item or {}).get("missav") or {}
    status = cached.get("status")
    if status == "found":
        badge = '<span class="missav-badge found">⚠️ MissAVにあり</span>'
    elif status == "not_found":
        badge = '<span class="missav-badge clear">✓ MissAVになし</span>'
    else:
        badge = ""
    checked_at = html.escape(cached.get("checked_at") or "")
    note = f'<span class="missav-note">確認 {checked_at}</span>' if checked_at else ""
    label = "再確認" if status else "🔎 MissAVを確認"
    box_id = f"missav-{uid}"
    return (f'<div class="missav" id="{box_id}">{badge}{note} '
            f'<button class="missav-btn" data-dir="{html.escape(api_dir)}" '
            f'data-target="{box_id}">{label}</button></div>')


# ──────────────────────────────────────────────
# アーカイブ操作ボタン（board.html / board_<cid>.html で共通）
#   全体ボード側：📦 アーカイブ（1ボタン）
#   アーカイブ一覧側：🗑 完全削除／↩ 全体ボードに戻す（2ボタン）
#   実処理（item.json の "archived" 更新・フォルダ削除）はサーバー側
#   （serve_board.py の /__archive・/__unarchive・/__delete_work）でのみ動く。
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
