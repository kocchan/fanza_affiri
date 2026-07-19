# -*- coding: utf-8 -*-
"""
スクリプト共通の土台（設定読み込み・アフィリリンク整形・works/ の走査）。

ここに置いているのは「重い依存を持たない」処理だけ。
`fetch_and_build.py` は nudenet（画像判定）を読み込むため起動が重いので、
ボード生成やメタ取得はこのモジュールだけを使って軽く動くようにしている。
"""

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
    return cfg


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
    """works/ 配下の作品フォルダを名前順で返す（投稿内容.md があるものだけ）。"""
    works_dir = works_dir or WORKS_DIR
    if not works_dir.is_dir():
        return []
    return sorted(
        (d for d in works_dir.iterdir()
         if d.is_dir() and (d / POST_MD).is_file()),
        key=lambda d: d.name)


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
