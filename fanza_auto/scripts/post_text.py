# -*- coding: utf-8 -*-
"""
作品の中身（item.json）を使って、その作品らしい投稿文を1本つくる。

これまでの投稿文はテンプレートのランダム選択だけで、作品の情報を一切見ていなかった。
そのため「どの作品でも同じことを言っている」状態になり、投稿の説得力が出なかった。
ここでは実データ（レビュー評価・件数・収録時間・発売日・ジャンル）を読んで、

  - その作品に合った“勝ち型”を選ぶ（高評価なら記録型、新作なら速報型…）
  - 数字や具体を1行入れる（★4.91・1時間57分・発売◯日 など）

ようにしている。勝ち型そのものは `templates.py`（＝勝ち型ナレッジ）を踏襲する。

★規制の要：投稿文に出してよいジャンルは SAFE_GENRES の**許可リスト方式**。
  リストに無いものは全部落とす。中出し/顔射/盗撮のような露骨語や、
  女子校生/美少女のような未成年連想語が本文に混ざる事故を、仕組みで防ぐ。
"""

import datetime
import json
import random

import common as C
import templates as T

# ──────────────────────────────────────────────
# 投稿文に書いてよいジャンル（許可リスト＝ここに無い語は本文に出さない）
#   値は本文での言い回し。ジャンル名をそのまま出すと硬いので言い換える。
#   ※露骨な行為系（中出し/顔射/フェラ/潮吹き…）と、未成年を連想させる語
#     （女子校生/美少女/女子大生…）は**意図的に1つも入れていない**。
#     作品として扱うのは safe_criteria.py の方針どおりOKだが、
#     X の本文に書いてよいかは別問題（CLAUDE.md の大原則）。
# ──────────────────────────────────────────────
SAFE_GENRES = {
    # 画質・配信（“ちゃんとした作品”の裏付けとして効く）
    "4K": "4K画質",
    "ハイビジョン": "高画質",
    "独占配信": "独占配信",
    "FANZA配信限定": "配信限定",
    # 体型・外見（外見の話に留め、行為には触れない）
    "スレンダー": "スレンダー",
    "巨乳": "スタイル抜群",
    "超乳": "スタイル抜群",
    "美乳": "スタイル良し",
    "巨尻": "スタイル抜群",
    "美脚": "脚がきれい",
    "くびれ": "くびれがすごい",
    "色白": "色白",
    "黒髪": "黒髪",
    "めがね": "めがね",
    # 雰囲気・属性（成人が明らかな属性は積極的に使う＝未成年連想の逆に振れる）
    "清楚": "清楚系",
    "ギャル": "ギャル",
    "お姉さん": "お姉さん",
    "人妻・主婦": "人妻",
    "熟女": "大人の女性",
    "OL": "OL",
    # シチュエーション（健全に言い換えられるものだけ）
    "ドキュメンタリー": "ドキュメンタリー",
    "企画": "企画もの",
    "水着": "水着",
    "エステ": "エステ",
    "マッサージ・リフレ": "リフレ",
    "スポーツ": "スポーツ系",
}

# “きちんとした雰囲気”側 / “スタイル”側。両方そろうとギャップ型が効く。
NEAT_GENRES = {"清楚", "黒髪", "色白", "めがね", "お姉さん", "OL", "人妻・主婦"}
BODY_GENRES = {"巨乳", "超乳", "美乳", "巨尻", "くびれ", "スレンダー", "美脚"}

# ほぼ全作品に付いていて“その作品らしさ”が出ない枠（本文では優先度を下げる）。
QUALITY_GENRES = {"4K", "ハイビジョン", "独占配信", "FANZA配信限定"}
QUALITY_WORDS = {"4K画質", "高画質", "独占配信", "配信限定"}

# 本文には出さないが、画像選びで特に慎重になってほしい作品に付ける印。
#   ここに当たった作品は、ボード上で「画像は要注意」と警告する。
#   （作品自体の採否は safe_criteria.py の方針に従う＝ここでは弾かない）
CAUTION_GENRES = {"女子校生", "美少女", "女子大生", "制服", "コスプレ", "童貞"}


# ──────────────────────────────────────────────
# item.json から使える値を取り出す
# ──────────────────────────────────────────────
def genres_of(item: dict) -> list:
    info = item.get("iteminfo") or {}
    return [g.get("name") or "" for g in (info.get("genre") or [])]


def safe_genre_words(item: dict, limit: int = 2) -> list:
    """本文に出してよいジャンルの言い回しを、重複なしで最大 limit 個返す。

    並べ替えの意図：画質（4K/高画質/独占配信）はどの作品にも付いていて
    「独占配信×高画質」のような無個性な行になりやすい。
    人物の見た目・雰囲気を先に、画質は最後に回す。
    """
    def priority(name: str) -> int:
        if name in NEAT_GENRES or name in BODY_GENRES:
            return 0                      # 見た目・雰囲気（一番その作品らしい）
        if name in QUALITY_GENRES:
            return 2                      # 画質・配信形態（最後の埋め合わせ）
        return 1                          # シチュエーションなど

    names = [g for g in genres_of(item) if g in SAFE_GENRES]
    words, seen = [], set()
    for name in sorted(names, key=priority):
        word = SAFE_GENRES[name]
        if word in seen:
            continue
        seen.add(word)
        words.append(word)
        if len(words) >= limit:
            break
    return words


def caution_genres(item: dict) -> list:
    """画像選びで要注意にしたいジャンル（本文には使わない）。"""
    return [g for g in genres_of(item) if g in CAUTION_GENRES]


def review_of(item: dict):
    """(平均点, 件数) を返す。無ければ (None, 0)。"""
    rv = item.get("review") or {}
    try:
        avg = float(rv.get("average"))
    except (TypeError, ValueError):
        avg = None
    try:
        count = int(rv.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    return avg, count


def duration_text(item: dict) -> str:
    """volume "1:57:00" → "1時間57分"。取れなければ空文字。"""
    vol = (item.get("volume") or "").strip()
    parts = vol.split(":")
    if len(parts) < 2 or not parts[0].isdigit():
        return ""
    h, m = int(parts[0]), int(parts[1])
    if h and m:
        return f"{h}時間{m}分"
    if h:
        return f"{h}時間"
    return f"{m}分" if m else ""


def duration_minutes(item: dict) -> int:
    """収録時間を分に直す。取れなければ 0。"""
    parts = (item.get("volume") or "").strip().split(":")
    if len(parts) < 2 or not parts[0].isdigit():
        return 0
    return int(parts[0]) * 60 + int(parts[1])


def days_since_release(item: dict):
    """発売からの経過日数。分からなければ None。"""
    raw = (item.get("date") or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return (datetime.datetime.now() - d).days
    return None


# ──────────────────────────────────────────────
# 作品に合った“勝ち型”を選ぶ
# ──────────────────────────────────────────────
def choose_pattern(item: dict) -> str:
    """作品の実データから、一番効きそうな型を選ぶ。

    根拠は `ナレッジ/コンテンツ/X運用ナレッジ_勝ち型（バズ型）.md`。
    数字の裏付けがある作品ほど強い型（record/flash）に寄せる。
    """
    avg, count = review_of(item)
    days = days_since_release(item)
    gset = set(genres_of(item))

    # 高評価＋レビューが十分＝社会的証明が最強に効く
    if avg is not None and avg >= 4.7 and count >= 5:
        return "record"
    # 新作は速報体が効く
    if days is not None and days <= 30:
        return "flash"
    # “きちんとした雰囲気”×“スタイル”が両立＝ギャップで見せる
    if (gset & NEAT_GENRES) and (gset & BODY_GENRES):
        return "gap"
    # そこそこ評価が付いている＝断定して背中を押す
    if avg is not None and avg >= 4.3 and count >= 3:
        return "assert"
    # レビューがまだ少ない＝共感・問いかけで会話を作る
    if count <= 2:
        return random.choice(["empathy", "question"])
    return "empathy"


# ──────────────────────────────────────────────
# 具体の1行（数字・作品の中身）をつくる
# ──────────────────────────────────────────────
def evidence_lines(item: dict) -> list:
    """本文に差し込む“具体”の候補行。効きそうな順に返す。"""
    lines = []
    # 点数は“盛らない”。4.2 を「めったに出ない」と書くと嘘くさくなって逆効果なので、
    # 評価帯ごとに言い方を変える。
    avg, count = review_of(item)
    if avg is not None and count >= 3:
        if avg >= 4.8:
            lines.append(f"レビュー★{avg:.2f}（{count}件）。"
                         "この点数はめったに出ない。")
        elif avg >= 4.5:
            lines.append(f"レビュー★{avg:.2f}（{count}件）。"
                         "評価がきれいに揃ってるのが強い。")
        elif avg >= 4.0:
            lines.append(f"レビュー★{avg:.2f}（{count}件）。"
                         "堅実に good が付いてるタイプ。")
        else:
            lines.append(f"レビュー★{avg:.2f}（{count}件）。"
                         "賛否あるけど、刺さる人には刺さるやつ。")
    elif avg is not None and count > 0:
        lines.append(f"まだ{count}件だけど★{avg:.2f}。見つけた人は分かってる。")

    # ジャンルの行は「その作品らしい語」が取れたときだけ。
    # 画質しか無いと「4K画質×高画質」のような中身のない行になるので出さない。
    words = [w for w in safe_genre_words(item, limit=3)
             if w not in QUALITY_WORDS]
    if len(words) >= 2:
        lines.append(f"{words[0]}×{words[1]}、この組み合わせが刺さる人にはハマる。")
    elif words:
        lines.append(f"{words[0]}なのがいい。")

    # 収録時間は“長い/短い”で意味が逆になる。42分に「長さのわりに」は噛み合わない。
    dur = duration_text(item)
    minutes = duration_minutes(item)
    if dur and minutes:
        if minutes >= 90:
            lines.append(f"収録{dur}。この長さで中だるみしないのが強い。")
        elif minutes >= 60:
            lines.append(f"収録{dur}。ちょうど一本ぶんの満足感。")
        else:
            lines.append(f"収録{dur}。ダレる前に終わるのが逆にいい。")

    days = days_since_release(item)
    if days is not None and 0 <= days <= 14:
        lines.append("出たばかりなのに、もう話題になりはじめてる。")
    return lines


# ──────────────────────────────────────────────
# “似てる”比較（★伸ばし用）
#   実名は【AV女優（同業）だけ】。一般芸能人の実名は使わず、
#   “雰囲気”はタイプ表現で匂わせる（肖像権・名誉毀損・凍結を避ける）。
# ──────────────────────────────────────────────
_FAMOUS_CACHE = None


def load_famous_names() -> list:
    """famous_actresses.json（AV女優）の名前リスト。1回だけ読んで使い回す。"""
    global _FAMOUS_CACHE
    if _FAMOUS_CACHE is not None:
        return _FAMOUS_CACHE
    names = []
    path = C.ROOT / "famous_actresses.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            names = [n for n in (data.get("names") or [])
                     if isinstance(n, str) and n.strip()]
        except Exception:
            names = []
    _FAMOUS_CACHE = names
    return names


def compare_line() -> str:
    """“似てる/系”の1行。★実際のAV女優名を使う（ユーザー方針）。
    女優名リストが空のときだけ、実名なしのタイプ表現にフォールバックする。"""
    names = load_famous_names()
    if names:
        return random.choice(T.COMPARE_NAME).format(name=random.choice(names))
    return random.choice(T.COMPARE_TYPE)


def short_review(item: dict):
    """レビューを短く1行に。無ければ None。"""
    avg, count = review_of(item)
    if avg is None:
        return None
    if count < 3:
        return f"まだ{count}件で★{avg:.2f}。見つけた人は目が高い。" if count else None
    if avg >= 4.8:
        return f"★{avg:.2f}（{count}件）はガチ。"
    if avg >= 4.5:
        return f"★{avg:.2f}（{count}件）、評価そろってる。"
    if avg >= 4.0:
        return f"★{avg:.2f}（{count}件）で堅い。"
    return f"★{avg:.2f}（{count}件）。刺さる人には刺さる。"


# ──────────────────────────────────────────────
# 投稿文の組み立て（★短くパッと分かる＝2〜3行）
# ──────────────────────────────────────────────
def build_main_text(item: dict, pattern: str) -> str:
    """メイン投稿（サブを引用する側）。短い伏せ字フック＋刺さる1行＋短いCTA。

    フィードバック（2026-07-19）反映：
      ・伏せ字（A▽/エ□/セッ久 等）で規制を避けつつ“におわせる”
      ・“似てる/系”比較で刺す（実名はAV女優のみ／一般芸能人は使わない）
      ・短くパッと分かる（余計な行を足さない）
    """
    # フックは伏せ字を主役に（＝伸ばし＆短さ）。たまに型フックも混ぜて機械的にしない。
    if random.random() < 0.65:
        hook = random.choice(T.MASK_HOOKS)
    else:
        hook = random.choice(T.HOOKS[pattern])

    # 2行目は「刺さる一言」を1つだけ。比較 or レビュー数字から選ぶ（比較を優先）。
    candidates = [compare_line()]
    rv = short_review(item)
    if rv:
        candidates.append(rv)
    second = candidates[0] if random.random() < 0.6 else random.choice(candidates)

    cta = random.choice(T.MAIN_QUOTE_CTA)
    # 短さ優先：フック→刺さる一言→（1行あけて）CTA。ハッシュタグは付けない。
    return "\n".join([hook, second, "", cta])


def build_sub_text(aff_url: str) -> str:
    """サブ投稿（アフィリンクを持つ側）。リンクは必ず【】で囲む。"""
    return random.choice(T.SUB_LINE).format(url=f"【{aff_url}】")


def build_boosters(n: int = 2) -> list:
    return random.sample(T.BOOSTER_POOL, k=min(n, len(T.BOOSTER_POOL)))


def build(item: dict, aff_url: str, pattern: str = None) -> dict:
    """1作品ぶんの投稿文一式を返す。

    戻り値:
        pattern  … 選ばれた勝ち型のキー
        label    … 型の表示名
        main     … メイン投稿の本文（リンクなし・サブを引用して出す）
        sub      … サブ投稿の本文（アフィリンク入り）
        boosters … 賑やかしコメント
        cautions … 画像選びで要注意なジャンル
    """
    pattern = pattern or choose_pattern(item)
    return {
        "pattern": pattern,
        "label": T.PATTERN_LABEL.get(pattern, pattern),
        "main": build_main_text(item, pattern),
        "sub": build_sub_text(aff_url),
        "boosters": build_boosters(2),
        "cautions": caution_genres(item),
    }
