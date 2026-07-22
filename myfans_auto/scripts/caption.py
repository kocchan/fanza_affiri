# -*- coding: utf-8 -*-
"""
MyFansの投稿本文（description）から、短い"あるある反応"ふうのメイン投稿文を作る。

fanza_auto/scripts/post_text.py はレビュー評価・ジャンル・発売日という構造化データから
型を選ぶが、MyFansにはそれが無く、あるのは投稿ページの自由記述の本文だけ。
ここでは本文から「場所・シチュエーション」を表す**安全な単語だけ**を許可リストで拾い、
短い反応文テンプレートに当てはめる。

★許可リスト方式（post_text.py の SAFE_GENRES と同じ考え方）：
  本文には行為語（ハメ撮り/フェラ等）や未成年連想語がハッシュタグ等で混ざっていることがある。
  それらは絶対に拾わない・使わない。拾うのは「場所・シーン」を表す当たり障りのない語だけ。

★型はカテゴリ別（場所/人物属性/イベント/ゲーム）に分けている。「同窓会との密会がこれ」のような
  文法的に不自然な組み合わせを避けるため、カテゴリが合うテンプレートだけを使う。

型テンプレートの元ネタ・実例は `ナレッジ/コンテンツ/X運用ナレッジ_MyFansキャプション型.md`。
新しい型を思いついたら、まずそのナレッジに実例を足してからここに反映する。
"""

import random
import re

# 本文から拾ってよい「場所・シチュエーション」ワード（許可リスト）。
# 値は (キャプションでの言い回し, カテゴリ)。行為語・体位語・未成年連想語は意図的に一切含めない。
# 上から順に検索し、最初に一致したものを使う（複数一致時は先頭優先＝リストの並び＝優先度）。
SAFE_SITUATIONS = [
    # 「エ◯ビー」のように伏字を挟むことがあるため、エ・ビーの間は1文字任意で許容する。
    (r"エ.{0,1}ビー|Air ?[Bb]nb", "エアビー", "place"),
    (r"お泊まり会|お泊まりデート|お泊まり|泊まりに行", "お泊まり", "place"),
    (r"ラブホ|ホテル", "ホテル", "place"),
    (r"温泉旅行|温泉", "温泉旅行", "place"),
    (r"社員旅行|旅行", "旅行", "place"),
    (r"合コン", "合コン", "place"),
    (r"飲み会|宅飲み", "飲み会", "place"),
    (r"女子会", "女子会", "place"),
    (r"オフ会", "オフ会", "place"),
    (r"コンカフェ", "コンカフェ", "place"),
    (r"歌舞伎町", "歌舞伎町", "place"),
    (r"クラブ", "クラブ", "place"),
    (r"合宿", "合宿", "place"),
    (r"出張", "出張", "place"),
    (r"デート", "デート", "place"),
    (r"同窓会", "同窓会", "event"),
    (r"ワールドカップ|Ｗ杯|W杯", "W杯", "event"),
    (r"忘年会", "忘年会", "event"),
    (r"新年会", "新年会", "event"),
    (r"野球拳", "野球拳", "game"),
]

# カテゴリごとの短文テンプレート（{kw}に単語が入る）。
# place=場所・行為シチュエーション／event=同窓会等のイベント／
# game=野球拳等のゲーム／person=人物属性（AI再生成の自由入力でのみ使う）。
# 元ネタ・実例は ナレッジ/コンテンツ/X運用ナレッジ_MyFansキャプション型.md（ユーザー提示実例）。
TEMPLATES_BY_CATEGORY = {
    "place": [
        "ノリで{kw}した結果がこれwww",
        "{kw}行ったらそりゃこうなるよねwww",
        "男女で{kw}したらそりゃこうなるwww",
        "{kw}の誘惑に勝てる人いる？www",
        "{kw}に誘われたら断れない自信あるwww",
        "まさか{kw}でこうなるとは思わなかったwww",
        "{kw}なう→気づいたらこうなってましたwww",
    ],
    "event": [
        "{kw}で久々に再会したらこうなるｗｗ",
        "まさか{kw}でこうなるとは思わなかったwww",
        "{kw}なう→気づいたらこうなってましたwww",
        "まだ{kw}気分の女さんｗｗｗｗ",
    ],
    "game": [
        "{kw}で負けちゃう子ｗｗｗ",
        "{kw}なう→気づいたらこうなってましたwww",
    ],
    "person": [
        "{kw}との密会がこれ",
        "{kw}に目をつけられるとこうなる",
    ],
}

def extract_situation(description: str):
    """本文から最初に見つかった安全なシチュエーションワードを (表示形, カテゴリ) で返す。
    無ければ (None, None)。"""
    text = description or ""
    for pattern, label, category in SAFE_SITUATIONS:
        if re.search(pattern, text):
            return label, category
    return None, None


def build_main_text(description: str, fallback_hooks: list) -> str:
    """本文から短い反応文を1本作る。シチュエーションが拾えなければ固定フックにフォールバックする
    （fallback_hooksは fanza_auto/scripts/templates.py の REACTION_HOOKS を渡す想定）。

    ★文章を作り直したいときは、この自動生成ではなくClaude Codeのチャットで直接指示する運用
    （ユーザー方針・2026-07-23）。ここでの自動生成は取り込み時の初期値だけを担う。"""
    kw, category = extract_situation(description)
    if kw:
        return random.choice(TEMPLATES_BY_CATEGORY[category]).format(kw=kw)
    return random.choice(fallback_hooks) if fallback_hooks else ""
