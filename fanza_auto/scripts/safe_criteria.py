# -*- coding: utf-8 -*-
"""
X規制セーフ判定の「単一の基準（Single Source of Truth）」。

このファイルは `ナレッジ/規制・安全/X運用ナレッジ_アダルト規制.md` を
コードに落とし込んだもの。判定ロジックを変えるときは必ずあのナレッジと突き合わせる。

2レイヤーで“X的に大丈夫な写真”を厳選する：

  ① 作品レベル（源泉）: 未成年連想（女子校生/制服/学生/ロリ 等）の作品を弾く。
     → Xゼロトレランス（未成年に見える＝一発永久凍結）の最重要ガード。
        画像解析では年齢を判定できないので、genre/タイトルの“源泉”で落とす。

  ② フレームレベル: 露骨（全裸/性器/露出）= Adult/Explicitランク相当を除外し、
     示唆的（着衣/部分露出/チラ見せ/表情）= Sensitiveランクのフレームだけ採用。
     → 集客メイン投稿は Sensitive に収めないと おすすめ/検索から除外される。
"""

# ──────────────────────────────────────────────
# ① 作品レベル：未成年連想スクリーニング（源泉で弾く）
#   ナレッジ「★FANZA素人系で特に危険な落とし穴」: J系/学生/制服/1●歳 等。
# ──────────────────────────────────────────────

# 先に取り除く“誤検出しやすい成人ワード”（部分一致対策）。
#   例: 「美少女」は成人の定番ジャンル → 「少女」に誤ヒットさせない。
#       「女子大生」「大学生」は成人 → 「学生」「校生」に誤ヒットさせない。
SAFE_ALLOW_TERMS = [
    "美少女",
    "女子大生",
    "大学生",
    "女子アナ",
    "美女",
    "熟女",
]

# 含まれていたら“未成年連想”として作品ごと除外する語（genre名＋タイトルを走査）。
#   ★運用方針（2026-06-21）：制服・学生コスプレ“そのもの”はOK（成人明らか＋谷間/性行為なし）。
#     よって 制服/女子校生/学生 等の“学校テーマ語”は除外しない。
#     ここで弾くのは **あからさまに子供（ロリ/幼児的）** だけ。谷間・性行為は画像レベル＆人の目視で弾く。
MINOR_RISK_TERMS = [
    "ロリ", "合法ロリ", "貧乳ロリ",
    "幼", "あどけ", "童顔", "ミニマム",
    "ランドセル", "体操着", "体操服", "ブルマ", "スクール水着", "スク水",
    "小学", "中学生", "少女", "美少年",
]


def _strip_allow(text: str) -> str:
    for a in SAFE_ALLOW_TERMS:
        text = text.replace(a, "")
    return text


def work_text_blob(item: dict) -> str:
    """作品のタイトル＋genre/keyword/series名を1つの文字列にまとめる。"""
    info = item.get("iteminfo") or {}
    parts = [item.get("title", "") or ""]
    for key in ("genre", "keyword", "series"):
        parts += [(g.get("name") or "") for g in (info.get(key) or [])]
    return " ".join(parts)


def minor_risk(item: dict):
    """(is_risky: bool, hits: list[str]) を返す。
    未成年連想ワードを含む作品は is_risky=True（源泉で除外する対象）。"""
    blob = _strip_allow(work_text_blob(item))
    hits = sorted({t for t in MINOR_RISK_TERMS if t in blob})
    return (bool(hits), hits)


def genres_of(item: dict) -> list:
    info = item.get("iteminfo") or {}
    return [(g.get("name") or "") for g in (info.get("genre") or [])]


# ──────────────────────────────────────────────
# ② フレームレベル：露骨(除外) / 示唆的(採用) の分類（nudenet クラス）
# ──────────────────────────────────────────────

# Adult/Explicitランク相当＝露骨。これが写るフレームは集客投稿に使わない（除外）。
EXPLICIT_CLASSES = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "BUTTOCKS_EXPOSED",
}
# “着衣で示唆的”＝低露出なのにそそる（最も欲しいタイプ）。強めに加点。
COVERED_SUGGESTIVE = {
    "FEMALE_BREAST_COVERED",
    "FEMALE_GENITALIA_COVERED",
    "BUTTOCKS_COVERED",
}
# 軽い肌見せ＝チラ見せ程度。少しだけ加点（ただし合計は頭打ち＝“低露出”を保つ）。
LIGHT_SKIN = {
    "BELLY_EXPOSED",
    "ARMPITS_EXPOSED",
    "FEET_EXPOSED",
}
FACE_CLASSES = {"FACE_FEMALE"}

EXPLICIT_THRESHOLD = 0.30   # これ以上の確信度で露骨部位を検出したら除外
DETECT_MIN_SCORE = 0.25     # ノイズ除去用の下限

FACE_WEIGHT = 1.0           # 顔（表情）＝engagement。ナレッジ「表情で見せる」
COVERED_WEIGHT = 1.5        # 着衣の示唆＝“低露出だけどそそる”の主役。最重視。
SKIN_WEIGHT = 0.3           # 軽い肌見せは少しだけ
SKIN_CAP = 1.0              # 肌見せスコアの上限（露出を盛っても伸びない＝低露出を優先）
NO_FACE_PENALTY = 0.4       # 顔なし＝身体だけの曖昧カットは大きく減点

# ── strict（立ち上げモード）：A/Bテストの学びを反映 ──
#   NGの実態＝①性行為/性的状況（＝男性が写る）②谷間 ③下着/尻 ④モザイク。
#   いい＝女性ソロ・着衣・顔出し・谷間なし。→ strictは下記を“フレームごと除外”する。
MALE_PRESENCE_CLASSES = {         # 男性が写る＝性的状況の可能性大 → 除外
    "FACE_MALE",
    "MALE_BREAST_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
}
MALE_PRESENCE_THRESHOLD = 0.30
STRICT_EXCLUDE_CLASSES = {        # あからさまな下着/尻 → フレームごと除外
    "FEMALE_GENITALIA_COVERED",   # パンツ/股間
    "BUTTOCKS_COVERED",           # お尻
}
STRICT_EXCLUDE_THRESHOLD = 0.45
STRICT_CLEAVAGE_EXCLUDE = 0.50    # 胸の谷間（着衣胸）がこの確信度以上 → 除外
STRICT_FACE_WEIGHT = 1.3          # 女性の顔・表情を重視
STRICT_SKIN_CAP = 0.4             # 肌見せはさらに控えめに


def score_frame(detections, strict=False):
    """フレームの (is_safe, score, reasons) を返す。

    strict=False（normal）: 「低露出だけどそそる」。着衣の示唆(covered)＋顔を最重視。
    strict=True（立ち上げモード）: **下着・谷間・尻も避ける**。
        - パンツ/尻のあからさまなカットは除外。
        - 胸の谷間（着衣胸）は強く減点 → 顔・表情中心の“ふつうの可愛い”カットが上位に。
    どちらも露骨（全裸/性器/露出）は必ず除外。"""
    # strict（立ち上げ）は露骨判定も敏感に（低確信の露骨でも弾く）
    ex_thr = 0.20 if strict else EXPLICIT_THRESHOLD
    explicit = [d for d in detections
                if d["class"] in EXPLICIT_CLASSES
                and d["score"] >= ex_thr]
    if explicit:
        return False, 0.0, sorted({d["class"] for d in explicit})

    reasons = sorted({d["class"] for d in detections
                      if d["score"] >= DETECT_MIN_SCORE})
    face = max((d["score"] for d in detections
                if d["class"] in FACE_CLASSES), default=0.0)

    if strict:
        # ① 男性が写る＝性的状況の可能性大 → フレームごと除外
        male = [d for d in detections
                if d["class"] in MALE_PRESENCE_CLASSES
                and d["score"] >= MALE_PRESENCE_THRESHOLD]
        if male:
            return False, 0.0, sorted({d["class"] for d in male})
        # ② 下着/尻のあからさま、③ 谷間（着衣胸の確信度高） → 除外
        block = [d for d in detections if (
            (d["class"] in STRICT_EXCLUDE_CLASSES
             and d["score"] >= STRICT_EXCLUDE_THRESHOLD)
            or (d["class"] == "FEMALE_BREAST_COVERED"
                and d["score"] >= STRICT_CLEAVAGE_EXCLUDE))]
        if block:
            return False, 0.0, sorted({d["class"] for d in block})
        # ④ 女性の顔が無いカットは使わない（“いい”＝女性ソロ・顔出し）
        if face <= 0:
            return False, 0.0, reasons
        skin = sum(d["score"] for d in detections
                   if d["class"] in LIGHT_SKIN and d["score"] >= DETECT_MIN_SCORE)
        score = face * STRICT_FACE_WEIGHT + min(skin, STRICT_SKIN_CAP) * SKIN_WEIGHT
        return True, score, reasons

    covered = sum(d["score"] for d in detections
                  if d["class"] in COVERED_SUGGESTIVE
                  and d["score"] >= DETECT_MIN_SCORE)
    skin = sum(d["score"] for d in detections
               if d["class"] in LIGHT_SKIN
               and d["score"] >= DETECT_MIN_SCORE)

    score = face * FACE_WEIGHT + covered * COVERED_WEIGHT \
        + min(skin, SKIN_CAP) * SKIN_WEIGHT
    if face <= 0:
        score *= NO_FACE_PENALTY  # 顔の無い身体だけカットは大きく下げる

    return True, score, reasons
