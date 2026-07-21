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
    "美脚": "美脚",
    "くびれ": "くびれ",
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

# 「◯◯のギャップが凄まじい」「◯◯な時点で」型で使ってよい語＝人物の外見・雰囲気だけ。
# シチュエーション語（水着/エステ/リフレ/ドキュメンタリー等）は人物の特性ではないので
# 「ギャップ」の対象にならず日本語として破綻する（例：「水着のギャップ」は意味不明）。
TRAIT_WORDS = {
    "スレンダー", "スタイル抜群", "スタイル良し", "美脚", "くびれ", "色白", "黒髪", "めがね",
    "清楚系", "ギャル", "お姉さん", "人妻", "大人の女性", "OL",
}

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


def reaction_lines(item: dict) -> list:
    """作品データ（レビュー・ジャンル・収録時間・発売日）から作れる“リアクション系”
    一文の候補を、取れるだけ全部集めて返す（ユーザー方針 2026-07-21）。

    ★実在の人物・団体の経歴を主張する文は作らない（事実確認できず名誉毀損リスクが高い）。
      使うのは作品自身のデータだけ。

    従来は「①データ試行(60%)→ダメなら固定文」という設計で、実測すると全体の
    半分以上が固定文（作品と無関係）になっていた。ここを「候補を集められるだけ集めて、
    その中からランダムに選ぶ」に変え、データが取れる作品では毎回データ由来の文になる
    ようにしている。"""
    lines = []

    avg, count = review_of(item)
    if avg is not None and count >= 5:
        if avg >= 4.8:
            lines.append(f"★{avg:.1f}なのにまだ知らない人多すぎる")
        elif avg >= 4.3:
            lines.append("今一番売れてる理由がよくわかった")
        else:
            lines.append(f"★{avg:.1f}（{count}件）、賛否あるけど気になって見た")
    elif avg is not None and count > 0:
        lines.append(f"まだ{count}件のレビューだけど★{avg:.1f}、これは伸びる予感")

    # 「◯◯のギャップが凄まじい」型は“人物の特性”を表す語じゃないと日本語として
    # 破綻する（例：「水着のギャップ」「エステな時点で」は意味不明）。
    # TRAIT_WORDS（外見・雰囲気）だけに絞る。
    words = [w for w in safe_genre_words(item, limit=3)
            if w in TRAIT_WORDS]
    if words:
        lines.append(f"{words[0]}のギャップが凄まじすぎるwww")
        lines.append(f"{words[0]}な時点でもう反則でしょ")

    dur = duration_text(item)
    if dur:
        lines.append(f"{dur}ずっと集中して見ちゃった")

    days = days_since_release(item)
    if days is not None:
        if 0 <= days <= 14:
            lines.append("出たばかりなのに、もう話題になり始めてる")
        elif 15 <= days <= 60:
            lines.append("今さらだけど、これ普通に良作だった")

    return lines


def reaction_line(item: dict):
    """reaction_lines() から1つ選ぶ。材料が無ければ None
    （呼び出し側で REACTION_HOOKS にフォールバック）。"""
    lines = reaction_lines(item)
    return random.choice(lines) if lines else None


# ──────────────────────────────────────────────
# 投稿文の組み立て（★短い一文の方が伸びる＝ユーザー方針 2026-07-21）
# ──────────────────────────────────────────────
def build_main_text(item: dict) -> str:
    """メイン投稿（サブを引用する側）。短いリアクション一文だけ（CTA行は付けない）。

    フィードバック（2026-07-22）反映：
      ・「短い一文」のリアクション/ネタ調が伸びる（ユーザー提示サンプルに準拠）。
        旧方式（伏せ字フックMASK_HOOKS・型フックHOOKS[pattern]）は使わない
        ＝「もともとの文章作成方法は忘れて」の指示どおり、この一系統に一本化する。
      ・作品データ（レビュー・ジャンル・収録時間・発売日）が取れる限り、必ずそのデータを
        絡めた一文にする（固定文への逃げを作らない＝以前は約半分が作品と無関係だった）
      ・「気になる人は引用元へ👇」等のCTA行は不要（ユーザー方針）
      ・実在の人物・団体の経歴を主張する文は作らない（名誉毀損リスク。ユーザー提示サンプルの
        「〇〇（実在アイドルグループ）の◯期生辞退した子」型は再提示されたが今回も採用しない）
    """
    # データが1つでも取れれば必ずそれを使う。何も取れない作品のときだけ、
    # 同じ系統の固定リアクション文（REACTION_HOOKS）に頼る。
    return reaction_line(item) or random.choice(T.REACTION_HOOKS)


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
        "main": build_main_text(item),
        "sub": build_sub_text(aff_url),
        "boosters": build_boosters(2),
        "cautions": caution_genres(item),
    }
