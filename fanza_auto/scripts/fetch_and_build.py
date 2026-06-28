# -*- coding: utf-8 -*-
"""
FANZA人気動画 → 投稿セット自動生成ツール

やること:
  1. DMMアフィリエイトAPIでFANZAの人気動画を取得（ランキング順）
  2. 各動画の素材をダウンロード
       - 公式サンプル画像（補助用の候補）
       - サンプル動画 mp4（メイン投稿はこれを優先）
       - 動画から「規制セーフな示唆的フレーム」を自動抽出（extract_safe_frames）
  3. メイン投稿×2 / サブのリンクリプライ / ブースターの盛り上げコメント案 を
     1枚の Markdown「投稿シート」にまとめて出力

使い方:
  python3 fetch_and_build.py
  （認証情報はプロジェクト直下の .env から読む。設定は config.json で上書き可能）

注意:
  - 画像/動画は「候補」を出すだけ。実際にどれを使うかは手動で選ぶ。
  - ブースターは弱め運用前提（毎回全部使わない・時間を分散・文面を変える）。
"""

import os
import re
import sys
import json
import shutil
import random
import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests

import templates as T
import safe_criteria as SC
from extract_safe_frames import extract_safe_frames

ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ROOT.parent
API_ENDPOINT = "https://api.dmm.com/affiliate/v3/ItemList"
ACTRESS_ENDPOINT = "https://api.dmm.com/affiliate/v3/ActressSearch"
MOVIE_HOST = "https://cc3001.dmm.co.jp/litevideo/freepv"
MOVIE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36",
    "Referer": "https://www.dmm.co.jp/",
    "Cookie": "age_check_done=1",
}


# ──────────────────────────────────────────────
# 設定読み込み
# ──────────────────────────────────────────────
def load_env(env_path: Path) -> dict:
    """シンプルな .env パーサ（KEY=VALUE 形式）"""
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


def load_config() -> dict:
    cfg_path = ROOT / "config.json"
    cfg = {
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
        # アフィリエイトリンクの差し替え設定（APIが返すURLの af_id / ch / ch_id を上書き）
        "aff_link": {
            "af_id": "mokumoku555-001",
            "ch": "reward_ranking",
            "ch_id": "link",
        },
        "accounts": {"main": "MAIN", "sub": "SUB",
                     "boosters": ["B1", "B2", "B3"]},
    }
    if cfg_path.exists():
        cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))

    env = load_env(PROJECT_ROOT / ".env")
    api_id = cfg.get("api_id") or env.get("DMM_API_ID")
    aff_id = cfg.get("affiliate_id") or env.get("DMM_AFFILIATE_ID")
    if not api_id or not aff_id:
        sys.exit("✗ API_ID / AFFILIATE_ID が見つかりません。"
                 ".env か config.json に設定してください。")
    cfg["api_id"] = api_id
    cfg["affiliate_id"] = aff_id
    return cfg


# ──────────────────────────────────────────────
# DMM API
# ──────────────────────────────────────────────
def fetch_items(cfg: dict) -> list:
    params = {
        "api_id": cfg["api_id"],
        "affiliate_id": cfg["affiliate_id"],
        "site": cfg["site"],
        "service": cfg["service"],
        "floor": cfg["floor"],
        "sort": cfg["sort"],
        "hits": cfg["fetch_count"],
        "output": "json",
    }
    r = requests.get(API_ENDPOINT, params=params, timeout=30)
    r.raise_for_status()
    body = r.json()
    result = body.get("result", {})
    status = result.get("status")
    if str(status) != "200":
        sys.exit(f"✗ API エラー: status={status} / {result}")
    items = result.get("items", [])
    if not items:
        sys.exit("✗ 取得結果が0件でした。floor/service の設定を見直してください。")
    return items


def sample_image_urls(item: dict, limit: int) -> list:
    """公式サンプル画像URL（大きい方優先）を取り出す"""
    box = item.get("sampleImageURL") or {}
    for key in ("sample_l", "sample_s"):
        node = box.get(key) or {}
        imgs = node.get("image") or []
        if imgs:
            return imgs[:limit]
    # サンプル画像が無ければパッケージ画像で代用
    img = item.get("imageURL") or {}
    one = img.get("large") or img.get("list")
    return [one] if one else []


def download(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"  ! 画像DL失敗: {url} ({e})")
        return False


# ──────────────────────────────────────────────
# サンプル動画（mp4）
#   DMMのサンプル動画は以下のURL命名で直接取得できる:
#   {HOST}/{cidの先頭1文字}/{cidの先頭3文字}/{cid}/{cid}_{画質}.mp4
#   画質: mhb_w(高/~64MB) > dm_w(中/~14MB) > sm_w(軽/~6MB)
# ──────────────────────────────────────────────
def movie_url(cid: str, quality: str) -> str:
    return f"{MOVIE_HOST}/{cid[0]}/{cid[:3]}/{cid}/{cid}_{quality}.mp4"


def download_movie(cid: str, dest: Path, quality: str) -> bool:
    """指定画質→fallbackの順で最初に取れたmp4を保存する"""
    order = [quality] + [q for q in ("dm_w", "mhb_w", "sm_w") if q != quality]
    for q in order:
        url = movie_url(cid, q)
        try:
            r = requests.get(url, headers=MOVIE_HEADERS, timeout=120)
            if r.status_code == 200 and r.headers.get(
                    "Content-Type", "").startswith("video"):
                dest.write_bytes(r.content)
                print(f"  ✓ 動画DL({q}): {len(r.content)//1024//1024}MB {cid}")
                return True
        except Exception as e:
            print(f"  ! 動画DL失敗({q}): {url} ({e})")
    print(f"  ! 動画が見つかりませんでした: {cid}")
    return False


# ──────────────────────────────────────────────
# 文章生成
# ──────────────────────────────────────────────
def build_main_quote_text(pattern: str) -> str:
    """メインが『サブ投稿を引用』するときの本文。型(pattern)のフックを使う。
    リンクは引用元にあるので“引用先を見て”系のCTAでまとめる。"""
    hook = random.choice(T.HOOKS[pattern])
    tease = random.choice(T.MAIN_TEASE)
    cta = random.choice(T.MAIN_QUOTE_CTA)
    tag = random.choice(T.MAIN_TAGS)
    lines = [hook, "", tease, "", cta]
    if tag:
        lines += ["", tag]
    return "\n".join(lines)


def build_sub_text(url: str) -> str:
    # リンクは必ず【】で囲む（スクショの導線に合わせる）
    return random.choice(T.SUB_LINE).format(url=f"【{url}】")


def build_booster_comments(n: int = 2) -> list:
    return random.sample(T.BOOSTER_POOL, k=min(n, len(T.BOOSTER_POOL)))


def build_ranking_main_text(name3: str, name2: str) -> str:
    """ランキング投稿のメイン本文（2位・3位＝有名女優の実名／1位は伏せる・無リンク）。"""
    lines = [
        random.choice(T.RANK_TITLE),
        "",
        T.RANK_TIER3.format(names=name3),
        T.RANK_TIER2.format(names=name2),
        random.choice(T.RANK_WITHHOLD),
        "",
        random.choice(T.RANK_MAIN_CTA),
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 有名女優（固定リスト）と顔写真（ActressSearch）
#   ランキングの2位/3位に出す“みんなが知ってる名前”の出どころ。
#   1位は本命の素人作品なのでここには含めない。
# ──────────────────────────────────────────────
def load_famous_names() -> list:
    path = ROOT / "famous_actresses.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [n for n in (data.get("names") or []) if isinstance(n, str) and n.strip()]
    except Exception:
        return []


def fetch_actress_image_url(cfg: dict, name: str) -> str:
    """女優名から顔写真URL（大きい方優先）を返す。取れなければ空文字。"""
    params = {
        "api_id": cfg["api_id"],
        "affiliate_id": cfg["affiliate_id"],
        "keyword": name,
        "hits": 1,
        "output": "json",
    }
    try:
        r = requests.get(ACTRESS_ENDPOINT, params=params, timeout=20)
        r.raise_for_status()
        acts = (r.json().get("result", {}) or {}).get("actress") or []
        if not acts:
            return ""
        img = acts[0].get("imageURL") or {}
        return img.get("large") or img.get("small") or ""
    except Exception as e:
        print(f"  ! 女優画像の取得失敗: {name} ({e})")
        return ""


# ──────────────────────────────────────────────
# 使用済み作品の履歴（日をまたいで作品が被らないようにする）
# ──────────────────────────────────────────────
USED_PATH = ROOT / "output" / "_used.json"


def load_used() -> dict:
    """{content_id: 最後に使った日付} を返す"""
    if USED_PATH.exists():
        try:
            return json.loads(USED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_used(used: dict) -> None:
    USED_PATH.parent.mkdir(parents=True, exist_ok=True)
    USED_PATH.write_text(
        json.dumps(used, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")


def screen_items(items: list, cfg: dict):
    """源泉スクリーニング：未成年連想（女子校生/制服/学生/ロリ等）の作品を除外する。
    返り値: (clean_items, skipped) ／ skipped は (item, hits) のリスト。
    Xゼロトレランス（未成年に見える＝一発永久凍結）の最重要ガード。"""
    if not cfg.get("screen_minor_risk", True):
        return items, []
    clean, skipped = [], []
    for it in items:
        risky, hits = SC.minor_risk(it)
        if risky:
            skipped.append((it, hits))
        else:
            clean.append(it)
    return clean, skipped


def select_items(items: list, cfg: dict, today: str) -> list:
    """ランキング上位から、過去に使っていない作品を posts_per_day 件選ぶ。
    同じ日付の再実行では、その日に記録した分は『未使用扱い』にして再現性を保つ。"""
    n = cfg.get("posts_per_day", 2)
    if not cfg.get("avoid_repeats", True):
        return items[:n]

    used = load_used()
    blocked = {c: d for c, d in used.items() if d != today}  # 今日の分は除外

    chosen, chosen_cids = [], set()
    for it in items:
        if len(chosen) >= n:
            break
        cid = it.get("content_id")
        if cid in blocked or cid in chosen_cids:
            continue
        chosen.append(it)
        chosen_cids.add(cid)

    if len(chosen) < n:
        # 未使用の新作が足りない → 過去作品を「最後に使った日が古い順」で補充
        rest = [it for it in items if it.get("content_id") not in chosen_cids]
        rest.sort(key=lambda it: blocked.get(it.get("content_id"), "0000-00-00"))
        for it in rest:
            if len(chosen) >= n:
                break
            chosen.append(it)
            chosen_cids.add(it.get("content_id"))
        print("  ⚠️ 未使用の新作が足りないため、過去作品を古い順に補充しました"
              "（config の fetch_count を増やすと回避しやすい）")
    return chosen


def record_used(chosen: list, today: str) -> None:
    used = load_used()
    for it in chosen:
        cid = it.get("content_id")
        if cid:
            used[cid] = today
    save_used(used)


# ──────────────────────────────────────────────
# 1投稿ぶんのフォルダを作る
#   フォルダ名: <日付>_<朝or夜>_<作品名(短縮)>
#   中身: 画像10枚(01〜10.jpg) ＋ sample.mp4(取れた時) ＋ 投稿内容.md
# ──────────────────────────────────────────────
_FS_BAD = re.compile(r'[\\/:*?"<>|\s（）()\[\]【】「」『』、。!！?？~〜・…]+')


def safe_folder_part(title: str, limit: int = 14) -> str:
    """作品名をフォルダ名向けに短く・安全化する。
    ＆や/を含む複数名タイトルは最初の名前だけ採用する。"""
    head = re.split(r"[＆&/／]", title)[0]
    cleaned = _FS_BAD.sub("", head).strip()
    return (cleaned[:limit] or "作品")


def build_post(item, rank, cfg, out_dir, detector,
               pattern="empathy", famous=None):
    """1作品ぶんの独立フォルダを生成して (folder, 画像枚数) を返す。
    フォルダ名＝ <連番>_<作品名>_<cid>（朝/夜は付けない／cidで一意）。"""
    title = item.get("title", "(no title)")
    cid = item.get("content_id", f"item{rank}")
    aff_url = rewrite_aff_url(item.get("affiliateURL", ""), cfg)

    # 新構成：作品ごとフォルダ <cid>_<作品名>（日付・連番なし＝ダッシュボードで一意）
    name = f"{cid}_{safe_folder_part(title)}"
    folder = out_dir / name
    folder.mkdir(parents=True, exist_ok=True)
    work = folder / "_src"             # 作業用（最後に削除）
    work.mkdir(exist_ok=True)

    print(f"▶ #{rank} {title} ({cid}) 〔型:{pattern}〕")

    # 公式サンプル画像
    official = []
    for i, u in enumerate(sample_image_urls(item, cfg.get("sample_images_per_item", 20))):
        dest = work / f"o{i+1:02d}.jpg"
        if download(u, dest):
            official.append(dest)

    # サンプル動画 → セーフフレーム抽出（動画は folder 直下に残す）
    safe = []
    if cfg.get("download_movie", True):
        mp4 = folder / "sample.mp4"
        if download_movie(cid, mp4, cfg.get("movie_quality", "dm_w")):
            if cfg.get("extract_safe", True) and detector is not None:
                safe = list(extract_safe_frames(
                    mp4, work / "safe",
                    top_n=cfg.get("safe_frames_top_n", 10), detector=detector,
                    strict=(cfg.get("safe_level", "strict") == "strict")))

    # 画像を組み立てる。★A/Bの学び：女性ソロ・着衣・顔出し・谷間なしの“セーフフレーム”だけ採用。
    #   strict（立ち上げ）では公式サンプル画像は使わない（露骨/性的状況/コラージュが混じるため）。
    #   セーフフレームが want 未満なら、無理に埋めず少ない枚数のままにする（汚い画像で水増ししない）。
    want = cfg.get("images_per_post", 4)
    strict = (cfg.get("safe_level", "strict") == "strict")
    sources = safe if strict else (safe + official)
    n_images = 0
    for src in sources:
        if n_images >= want:
            break
        n_images += 1
        shutil.copyfile(src, folder / f"{n_images:02d}.jpg")
    if n_images == 0:
        print(f"  ⚠️ {cid}: strict条件を満たすセーフ画像が0枚。手動で素材を用意するか除外を検討。")

    # 投稿内容ファイル（型ごとに本文・導線を出し分け）
    (folder / "投稿内容.md").write_text(
        render_post_content(item, rank, aff_url, n_images, cfg,
                            pattern, famous or []),
        encoding="utf-8")

    shutil.rmtree(work, ignore_errors=True)
    has_mv = (folder / "sample.mp4").exists()
    print(f"  ✓ {name}/ … 画像{n_images}枚"
          + (" + sample.mp4" if has_mv else "") + " + 投稿内容.md")
    return folder, n_images


# ──────────────────────────────────────────────
# アフィリエイトリンクの差し替え
# ──────────────────────────────────────────────
def rewrite_aff_url(url: str, cfg: dict) -> str:
    """APIが返す affiliateURL の af_id / ch / ch_id を config 設定で上書きする。
    lurl（遷移先）はそのまま維持する。設定が無ければ元のURLを返す。"""
    overrides = cfg.get("aff_link") or {}
    if not url or not overrides:
        return url
    parts = urlsplit(url)
    # keep_blank_values: lurl のエンコード済みクエリを壊さないため
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key in ("af_id", "ch", "ch_id"):
        if overrides.get(key) is not None:
            query[key] = overrides[key]
    new_query = urlencode(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


# ──────────────────────────────────────────────
# 投稿内容ファイルのレンダリング（型 pattern ごとに本文・導線を出し分け）
#   ・ranking 型 … メイン無リンクで「2/3位＝有名女優・1位＝この作品を伏せる」→
#                   リプで動画（答え）→ リプでアフィリンク（スレ連結）。
#   ・その他の型 … サブ（リンク）→ メイン引用（型のフック）→ 賑やかし。
# ──────────────────────────────────────────────
def _post_header(item, rank, n_images, cfg, pattern):
    title = item.get("title", "(no title)")
    return [
        f"# {rank:02d} {safe_folder_part(title)}",
        "",
    ]


def render_post_content(item, rank, aff_url, n_images, cfg, pattern, famous):
    """型(pattern)に応じて『投稿内容.md』を出し分ける。"""
    if pattern == "ranking" and len(famous) >= 2:
        return _render_ranking_style(item, rank, aff_url, n_images, cfg, famous)
    return _render_quote_style(item, rank, aff_url, n_images, cfg, pattern)


def _render_quote_style(item, rank, aff_url, n_images, cfg, pattern):
    """サブ（リンク）→ メイン引用（型のフック）→ 賑やかし。"""
    accounts = cfg["accounts"]
    sub_text = build_sub_text(aff_url)
    main_text = build_main_quote_text(pattern)
    boosters = build_booster_comments(2)

    L = _post_header(item, rank, n_images, cfg, pattern)
    if pattern == "gap":
        L.append("> 💡 ギャップ型：1枚目に“きちんとした雰囲気”、2枚目で印象が変わる"
                 "並びにすると効く。\n")
    L += [
        f"## ① サブ投稿（@{accounts['sub']}）― 画像/動画＋アフィリンク",
        "```",
        sub_text,
        "```",
        "",
        f"## ② メイン投稿（@{accounts['main']}）― ①を“引用”して投稿（型："
        f"{T.PATTERN_LABEL.get(pattern, pattern)}）",
        "```",
        main_text,
        "```",
        "",
        "## ③ 賑やかし（サブへのリプライ・弱め・1〜2件だけ／文面は微調整）",
    ]
    L += [f"- 「{c}」" for c in boosters]
    L.append("")
    return "\n".join(L)


def _render_ranking_style(item, rank, aff_url, n_images, cfg, famous):
    """ランキング＋伏せ＋スレ連結を、この1作品で完結させる。
    メイン無リンクで「3位/2位＝有名女優・1位＝この作品を伏せる」→ リプで動画→ リプでリンク。"""
    accounts = cfg["accounts"]
    name3, name2 = random.sample(famous, k=2)
    main_text = build_ranking_main_text(name3, name2)
    reply_video = random.choice(T.RANK_REPLY_VIDEO)
    sub_link = build_sub_text(aff_url)
    boosters = build_booster_comments(2)

    L = _post_header(item, rank, n_images, cfg, "ranking")
    L += [
        f"## ① メイン投稿（@{accounts['main']}）― 無リンク・画像01〜{n_images:02d}.jpg添付"
        f"（1位は伏せる／3位 {name3}・2位 {name2}）",
        "```",
        main_text,
        "```",
        "",
        f"## ② リプ①（@{accounts['main']} 自己リプ）― 1位の答え＋ `sample.mp4` を添付",
        "```",
        reply_video,
        "```",
        "",
        f"## ③ リプ②（@{accounts['sub']}）― 1位（この作品）のアフィリンク",
        "```",
        sub_link,
        "```",
        "",
        "## ④ 賑やかし（任意・弱め・1〜2件）",
    ]
    L += [f"- 「{c}」" for c in boosters]
    L.append("")
    return "\n".join(L)


# ──────────────────────────────────────────────
# 審査チェックリスト（人の最終目視用）
#   自動フィルタは年齢を判定できない → ナレッジ準拠の目視チェックを人が行う。
# ──────────────────────────────────────────────
def write_screening_report(out_dir: Path, today: str, chosen: list,
                           skipped: list, cfg: dict) -> None:
    L = [
        f"# 🛡️ 写真の源泉・審査チェックリスト（{today}）",
        "",
        "出典基準：`ナレッジ/規制・安全/X運用ナレッジ_アダルト規制.md`",
        "",
        "> 自動判定は**年齢を判定できない**。ここはあくまで一次フィルタ。"
        "**投稿前に人が下のチェックを必ず実施**すること。",
        "",
        "## メイン投稿に使う画像の目視チェック（全作品共通）",
        "",
        "- [ ] 全裸・性器・露骨な性行為が**写っていない**（→ Sensitiveランク内）",
        "- [ ] 示唆的に留める（着衣・部分露出・チラ見せ・表情で見せる）",
        "- [ ] **未成年に見えない**（制服/学生強調NG・明らかに成人の構図）",
        "- [ ] 投稿時に**センシティブ設定をON**",
        "- [ ] プロフィール画像・ヘッダーには使わない",
        "",
        "---",
        "",
        f"## ① 源泉スクリーニングで自動除外した作品（{len(skipped)}件）",
        "未成年連想ワードを genre/タイトルに含むため、**採用候補から自動で外した**もの。",
        "",
    ]
    if skipped:
        L += ["| content_id | タイトル | ヒット語 |", "|---|---|---|"]
        for it, hits in skipped:
            L.append(f"| `{it.get('content_id','')}` | "
                     f"{it.get('title','')[:24]} | {'・'.join(hits)} |")
    else:
        L.append("（除外なし、またはスクリーニング無効）")
    L += [
        "",
        f"## ② 採用した作品（{len(chosen)}件）― genreを見て最終判断",
        "クリーン判定済みだが、**画像は1枚ずつ目視**して上のチェックを通すこと。",
        "",
        "| content_id | タイトル | genre（抜粋） |",
        "|---|---|---|",
    ]
    for it in chosen:
        gs = "・".join(SC.genres_of(it)[:6])
        L.append(f"| `{it.get('content_id','')}` | "
                 f"{it.get('title','')[:20]} | {gs} |")
    L.append("")
    (out_dir / "00_審査チェックリスト.md").write_text("\n".join(L), encoding="utf-8")
    print("  ✓ 00_審査チェックリスト.md（人の最終目視用）")


# ──────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────
def existing_cids(works_dir: Path) -> set:
    """works/ 配下の作品フォルダ（<cid>_<作品名>）から既出 cid を集める。"""
    cids = set()
    if not works_dir.is_dir():
        return cids
    for p in works_dir.glob("*"):
        if p.is_dir() and (p / "投稿内容.md").is_file():
            cids.add(p.name.split("_")[0])
    return cids


def main():
    cfg = load_config()
    today = datetime.date.today().isoformat()

    # 新構成：作品ごとフォルダを works/ に永続化（日付フォルダは作らない）。
    out_dir = ROOT / "works"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"▶ FANZA {cfg['floor']} を {cfg['sort']} 順で {cfg['fetch_count']}件取得中…")
    items = fetch_items(cfg)

    # ★源泉スクリーニング：未成年連想（女子校生/制服/学生/ロリ等）を作品ごと除外
    clean, skipped = screen_items(items, cfg)
    if cfg.get("screen_minor_risk", True):
        print(f"  🛡️ 未成年連想スクリーニング: {len(skipped)}件を除外 / "
              f"クリーン {len(clean)}件（ナレッジ_アダルト規制.md 準拠）")
        for it, hits in skipped[:8]:
            print(f"     ✕ {it.get('content_id')} {it.get('title','')[:18]} "
                  f"← {','.join(hits)}")
        if len(skipped) > 8:
            print(f"     …ほか {len(skipped)-8}件")

    # ★差分追加：すでにダッシュボード（works/）にある cid はスキップし、未掲載の新作だけ採用。
    have = existing_cids(out_dir)
    max_new = cfg.get("max_new_per_run", cfg.get("posts_per_day", 20))
    chosen, seen = [], set()
    for it in clean:
        cid = it.get("content_id")
        if not cid or cid in have or cid in seen:
            continue
        chosen.append(it)
        seen.add(cid)
        if len(chosen) >= max_new:
            break

    if not chosen:
        print(f"  ✓ 新規作品はありません（既存 {len(have)}作品はすべて掲載済み）。")
        print(f"  ダッシュボード更新: python3 {ROOT / 'scripts' / 'make_post_html.py'}")
        return
    titles = " / ".join(it.get("title", "?") for it in chosen)
    print(f"  取得 {len(items)}件 → 既存 {len(have)}作品はスキップ → "
          f"新規 {len(chosen)}件を追加: {titles}")

    # nudenetの検出器は重いので一度だけ生成して使い回す
    detector = None
    if cfg.get("download_movie", True) and cfg.get("extract_safe", True):
        from nudenet import NudeDetector
        detector = NudeDetector()

    # 勝ち型ナレッジの“型”を全投稿に散らす。有名女優名は ranking 型で使う。
    famous = load_famous_names()
    rotation = T.PATTERN_ROTATION

    built = []
    for idx, item in enumerate(chosen):
        pattern = rotation[idx % len(rotation)]
        if pattern == "ranking" and len(famous) < 2:
            pattern = "record"   # 有名女優名が無ければ記録型にフォールバック
        folder, n_images = build_post(
            item, idx + 1, cfg, out_dir, detector,
            pattern=pattern, famous=famous)
        built.append((folder, n_images))

    # ★審査チェックリスト（人の最終目視用・ナレッジ準拠）。works/ 直下に最新分を残す。
    write_screening_report(out_dir, today, chosen, skipped, cfg)

    print(f"\n✓ 完成: {len(built)}作品を追加（各投稿に勝ち型を適用）→ {out_dir}")
    for folder, n in built:
        print(f"   - {folder.name}/  （画像{n}枚 + 投稿内容.md）")
    print(f"\n  ダッシュボード更新: python3 {ROOT / 'scripts' / 'make_post_html.py'}")


if __name__ == "__main__":
    main()
