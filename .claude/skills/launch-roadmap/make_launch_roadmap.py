# -*- coding: utf-8 -*-
"""
初期アカウント立ち上げロードマップ → コピペ実行用HTMLを生成する（コンセプト駆動）。

このスクリプトは「HTMLの枠（CSS/JS/フェーズ構成）」を担当する純レンダラー。
アカウント固有の中身（コンセプト・表示名・ID・bio・各コピー文・会話例）は
concept.json から受け取る。スキル launch-roadmap が毎回その JSON を作って渡す。

各フェーズは「✅ やること（チェックリスト）」と「📋 コピペ素材（例文）」を見出しで分離。
会話ラリーは “1投稿＝この返信の流れ” をスレッド（会話例）として表示する。

使い方：
  python3 make_launch_roadmap.py [concept.json] [out.html]

concept.json のスキーマ（すべて任意。無い項目は DEFAULT_CONCEPT で補完）：
{
  "name","id","concept_line","id_candidates":[...],"icon_memo","bio",
  "pinned":[A,B],
  "tsubuyaki":[4本],
  "reply_templates":[2本],"question":"問いかけ例",
  "rally_threads":[                      # 会話例（1投稿＝この返信の流れ）。複数可
    [ ["① メイン投稿","..."], ["② サブが返信（無リンク）","..."],
      ["③ メインが返信 ＝リプ往復150倍","..."], ["④ サブがもう一言","..."], ["⑤ メインがまた返信","..."] ],
    [ ... 会話例2 ... ]
  ],
  "shukyaku":[2本],"sub_link":"サブ本文",
  "ogiri":{                              # 任意。あると フェーズ3 が「坊主の大喜利リプ集客」になる
    "target":"坊主（大喜利お題アカウント）など",
    "examples":[ {"odai":"お題テキスト","answer":"大喜利回答（健全・無リンク）"}, ... ]
  }
}
"""
import sys, json, html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

import re

concept_path, out_path = None, None
for a in sys.argv[1:]:
    if a.endswith(".json"):
        concept_path = Path(a)
    else:
        out_path = Path(a)


def safe_name(s):
    """ファイル名に使えない文字を除いた表示名"""
    return re.sub(r'[\\/:*?"<>|\n\r\t]+', "", s).strip() or "アカウント"

DEFAULT_CONCEPT = {
    "name": "夜の当たり研究所",
    "id": "@yoru_atari",
    "concept_line": ("成人・FANZAの“当たり作品”を見抜く目利き＋夜のあるある語り。\n"
                     "R18・無リンクで人間味と信用を育てるメイン集客アカ。\n"
                     "ジャンルは「当たり目利き × 夜のあるある」に固定。"),
    "id_candidates": ["yoru_atari", "atari_labo", "atari_kenkyu", "yoru_atari01"],
    "icon_memo": ("アイコン：露出なしの雰囲気（ネオン/夜景/“当たり”ロゴ風）\n"
                  "ヘッダー：夜・バー・ネオン等のムード系＋一言キャッチ\n"
                  "※プロフ画像・ヘッダーにアダルト画像は規約NG"),
    "bio": ("サンプル数秒で“当たり”を見抜くのが特技。\n"
            "ハズさない一本と、夜のあるある・本音を静かに置いていく場所。\n"
            "語り多め／宣伝は控えめ。\n"
            "📍R18・センシティブ注意｜18歳未満はそっと退場で"),
    "pinned": [
        "はじめまして。\nサンプル数秒で“当たり”を見抜くのだけは自信あります。\n"
        "ハズさない一本と、夜のあるある・本音をゆるく置いてく場所です。\n気が合いそうならフォローどうぞ。",
        "“当たり”だけ静かに置いていく研究所、はじめます。\n"
        "派手な宣伝はしません。良かったやつと、夜の本音だけ。\nわかる人に届けばいい。",
    ],
    "tsubuyaki": [
        "終わった瞬間に部屋の散らかり具合が急に目に入ってくるの、あの落差なんなんだろうな。賢者すぎて掃除始めそうになる。",
        "いい雰囲気の真っ最中に宅配のインターホン鳴って、二人で息止めたまま無言になった。あの数十秒、人生でいちばん長かった。",
        "ちゃんとムード作る派と、勢いで行っちゃう派、どっちが正解だと思う？毎回迷って結局グダる。",
        "結局さ、見た目より“スイッチ入った瞬間の豹変”に弱いんだよな。あのギャップだけで一週間戦える。わかる人いる？",
    ],
    "reply_templates": [
        "これは完全に“当たり”の顔してる。表情だけで持っていかれた。",
        "わかる、こういうギャップ系に一生勝てないんですよね…。",
    ],
    "question": "今年見た中で“事故レベルに良かった”やつ、みんなのも教えてくれない？",
    "rally_threads": [
        [
            ["① メイン投稿", "今年“事故レベルに良かった”やつ、みんなのも教えてくれない？"],
            ["② サブが返信（無リンク）", "自分は雰囲気で選ぶ派です。最近のほんと当たり多くないですか？"],
            ["③ メインが返信 ＝リプ往復150倍", "それ語れる人いて嬉しい。あとでゆっくり話そう"],
            ["④ サブがもう一言", "次のおすすめも気になります"],
            ["⑤ メインがまた返信", "了解、近いうちに“今週の当たり”出すわ"],
        ],
        [
            ["① メイン投稿", "当たり作品の見分け方、結局なにで判断してる？俺はまず表情なんだけど。"],
            ["② サブが返信（無リンク）", "わかる、表情大事。この前見たやつ完全にやられました…"],
            ["③ メインが返信 ＝リプ往復150倍", "表情派、同志だ。サンキュー！"],
        ],
    ],
    "shukyaku": [
        "ランキング上位なの、見て一発で納得した。数字は嘘つかない。\n本編はサンプルの比じゃないらしい。",
        "【速報】これ今年のトップ争い、完全に入ってきた。\n表情だけで持っていく子は強い。",
    ],
    "sub_link": "見たい人用に置いとく↓\n【ここに fanza_auto のアフィリンクを貼る】",
}


def load_concept():
    c = dict(DEFAULT_CONCEPT)
    if concept_path and concept_path.exists():
        c.update(json.loads(concept_path.read_text(encoding="utf-8")))
    return c


def build_phases(c):
    # ── フェーズ2（自分が投稿するもの）。schedule があれば“具体20投稿”を出す ──
    sched = c.get("schedule")
    p2_groups = [{"label": "メインで投稿する（あなたの弾）",
                  "tasks": [
                     "<b>ゴールデンタイム</b>に投稿：20〜22時（最強）／12〜13時／7〜9時／深夜帯",
                     "投稿に<b>問いかけ</b>を混ぜて<b>リプを誘発</b>する",
                     "冒頭1〜2行に強フック（「さらに表示」を押させる）／「保存推奨」でブクマ誘導",
                     "最初の1〜2週間は<b>リンクなし</b>／<b>1日2本（朝・夜のゴールデンタイム）</b>・連投しない",
                  ]}]
    if not sched:
        p2_groups[0]["copies"] = [(f"つぶやき例{i+1}", t) for i, t in enumerate(c["tsubuyaki"])] \
            + [("問いかけ例（リプ誘発）", c["question"])]
        p2_groups.append({"label": "サブで会話を“自作”する（コメント偽装で150倍）",
            "tasks": [
                "サブで<b>“最初のリプ”を付けて口火</b>→メインが返す＝リプ往復<b>150倍</b>を自作（下の会話例の流れ）",
                "サブの返信は<b>数分〜十数分あけて</b>。毎回ちがう文面／<b>毎投稿ではやらない</b>（協調判定リスク）",
            ],
            "threads": c["rally_threads"]})
    phase2 = {"badge": "2", "title": "自分が投稿するもの（メインの“弾”＋サブ自作会話）", "when": "毎日",
              "intro": "メインの投稿と、それに<b>サブで会話を付ける</b>ところまでが“自分で作る”パート。"
                       + ("<b>下は10日×2投稿＝20本の具体プラン</b>（コピペ用・サブ会話つき）。" if sched else ""),
              "groups": p2_groups,
              "notes": [
                 ("info", "スコア早見（いいね=1倍）：自分のリプ往復<b>150倍</b> ＞ 他者リプ27倍 ＞ プロフクリック24倍 ＞ 滞在2分20倍 ＞ ブクマ3倍 ＞ リポスト2倍 ＞ いいね1倍。"),
                 ("warn", "新規期の上限の目安：投稿〜5/日・リプ〜20/日・いいね〜80/日。連打・大量フォローはサーチバン級。疑ったら24〜48h完全放置。"),
                 ("danger", "サブの会話シードは<b>無リンク</b>（リンクはフェーズ5の引用だけ）。各投稿にサブ会話の文面を用意してあるが、<b>実際に毎投稿でやると協調判定リスク</b>。日に1回程度・時間をあけて、使う/使わないを散らす。"),
              ]}
    if sched:
        phase2["schedule"] = sched

    # ── フェーズ3：他人にリプして露出を借りる。ogiri 設定があれば「坊主の大喜利リプ集客」を主軸にする ──
    og = c.get("ogiri")
    if og:
        p3_intro = ("フォロワー0期の最大の露出源は<b>大喜利リプ</b>。<b>坊主</b>のような"
                    "お題募集の大型垢に面白いリプを返し、<b>他人の巨大な露出を借りて</b>プロフへ流す。"
                    "リプ本文は<b>健全・無リンク</b>（エロの仕事はプロフに来てから）。")
        p3_tasks = [
            "<b>大喜利系の大型アカウント（坊主など）のお題</b>に、面白い大喜利リプを返す（<b>健全・無リンク</b>）",
            "リプ文は <b>/ogiri-answers</b> でお題から回答案を作る → 1お題<b>1〜2本だけ</b>選んで返す",
            "リプが伸びる→<b>プロフがクリックされる</b>（=美女系メインへの入口）。bio・固定で受け止める",
            "同ジャンルの伸びてる投稿にも気の利いたリプを。1日<b>〜20件まで</b>・文面は使い回さない",
        ]
        p3_copies = [(f"お題例：{ex['odai']}", ex["answer"]) for ex in og.get("examples", [])] \
            + [(f"通常リプ定型{i+1}", t) for i, t in enumerate(c["reply_templates"])]
        p3_notes = [
            ("info", "ファネル：大喜利リプ（健全）→ リプが伸びる → <b>プロフクリック（いいねの約24倍）</b> → 美女系メイン → 集客。"),
            ("danger", "大喜利リプに<b>下ネタ・露骨・リンク・未成年連想・誹謗中傷</b>は入れない（凍結/通報リスクだけ増える）。滑ってOK・数を打つ。"),
        ]
    else:
        p3_intro = ("フォロワーが少ない初期は、<b>自分から他人の投稿に絡んで</b>見つけてもらう。"
                    "相手のフォロワーにも自分が表示される“巻き込み効果”が狙い。")
        p3_tasks = [
            "同ジャンルの<b>伸びてる投稿に、自分から気の利いたリプ／引用</b>を送る",
            "1日3〜5件。営業臭を出さず自然に。文面は使い回さない",
        ]
        p3_copies = [(f"他人に送るリプ定型{i+1}", t) for i, t in enumerate(c["reply_templates"])]
        p3_notes = [("info", "フォロワー0期の主な露出源。来た本物のリプにも返すと会話が伸びる。")]
    phase3 = {"badge": "3", "title": "他人にリプして露出を借りる（投稿後）", "when": "投稿後すぐ",
              "intro": p3_intro, "tasks": p3_tasks, "copies": p3_copies, "notes": p3_notes}

    return [
    {"badge": "0", "title": "アカウント設計（コンセプト→名前・ID・アイコン）", "when": "最初に",
     "intro": "まず「<b>何のアカウントか</b>」を1つに固める。発信は<b>1ジャンルに統一</b>（ブレるとアルゴが学習できず伸びない）。",
     "tasks": [
        "<b>コンセプトを1行で決める</b>（誰に・何を・どんなキャラ）",
        "<b>表示名</b>を決める（検索/フック語を自然に）",
        "<b>@ID</b>を決める（半角英数4〜15字／被ったら末尾に数字・_）",
        "<b>アイコン・ヘッダーの方向性</b>を決める（<b>アダルト画像は不可</b>）",
        "<b>bioの骨子</b>を決める（専門性＋R18注記）",
     ],
     "copies": [
        ("コンセプト", c["concept_line"]),
        ("表示名（案）", c["name"]),
        ("@ID 候補（上から空きを試す）", "\n".join(c["id_candidates"])),
        ("アイコン/ヘッダーの方向性メモ", c["icon_memo"]),
     ],
     "notes": [("info", "途中でジャンルをブレさせない（関心度評価が下がる）。コンセプトに沿った投稿だけを出す。")]},

    {"badge": "1", "title": "初期設定（登録・公開・プロフ反映）", "when": "Day 0",
     "tasks": [
        "表示言語を<b>日本語</b>に（設定→アクセシビリティ・表示と言語→言語）",
        "<b>鍵を外す（公開）</b>：設定→プライバシーと安全→オーディエンスとタグ付け→「ポストを非公開」OFF",
        "<b>メール＋電話番号認証</b>を済ませる",
        "<b>センシティブ設定ON</b>（設定→プライバシーと安全→自分のメディア設定）",
        "フェーズ0で決めた<b>アイコン・ヘッダー・表示名</b>を反映する",
        "<b>bio</b>を設定する（素材からコピー）",
        "<b>固定ポストを1本</b>投稿して固定する（素材からコピー）",
     ],
     "copies": [("自己紹介（bio）", c["bio"])]
        + [(f"固定ポスト案{chr(65+i)}", t) for i, t in enumerate(c["pinned"])],
     "notes": [("danger", "⚠️ 固定ポスト含め、<b>作成後1〜2週間はリンクを貼らない</b>（アカウントエイジング）。")]},

    phase2,

    phase3,

    {"badge": "4", "title": "集客投稿を混ぜる（無リンク）", "when": "Day 10〜",
     "tasks": [
        "<b>/fanza-content</b> を実行して当日の投稿フォルダを生成",
        "<b>画像/動画を目視で選ぶ</b>（未成年に見える/制服強調は必ず除外＝ゼロトレランス）",
        "<b>メインから無リンクで投稿</b>（センシティブON・動画優先）＋投稿後2時間は即リプ",
     ],
     "copies": [(f"メイン本文{i+1}", t) for i, t in enumerate(c["shukyaku"])],
     "notes": [("info", "リンクは貼らない。続きを聞かれたら<b>サブ投稿を引用</b>する形で流す（次のフェーズ）。")]},

    {"badge": "5", "title": "リンク導線（サブ→メイン引用）", "when": "エイジング後",
     "tasks": [
        "<b>サブ</b>でアフィリンク付き投稿（PCから・リンクは【】囲み）",
        "<b>メイン</b>でそのサブ投稿を<b>引用</b>（メイン本体は無リンク）",
        "時間をあけて<b>賑やかしを1〜2件</b>（サブ投稿へのリプ・文面は微調整）",
     ],
     "copies": [("サブ本文（リンクは差し替え）", c["sub_link"])],
     "notes": []},

    {"badge": "🔁", "title": "毎日のルーティン（慣れたらこれだけ）", "when": "Daily",
     "tasks": [
        "つぶやき2〜4本（時間を散らす・毎回ちがう文）",
        "同ジャンルへ気の利いたリプ3〜5件",
        "集客投稿1本（Sensitive・無リンク）＋投稿後2時間は即リプ",
        "必要なときだけ サブ→メイン引用 でリンク導線",
        "アナリティクスでインプ/エンゲージ確認→伸びた型に寄せる",
     ],
     "copies": [],
     "notes": [("danger", "毎日の絶対NG：<b>未成年連想ワード</b>／<b>露骨表現・煽りすぎ</b>（通報1回＝いいね約738件ぶんのマイナス）／<b>メインに直リンク</b>／<b>同一文・画像の使い回し</b>／<b>機械的な等間隔投稿</b>")]},
    ]


def esc(s):
    return html.escape(s, quote=False)


def render(phases):
    tid = [0]
    def task(t):
        tid[0] += 1
        i = f"t{tid[0]}"
        return (f'<div class="task"><input type="checkbox" id="{i}">'
                f'<label for="{i}">{t}</label></div>')
    def copy(label, text):
        return ('<div class="copy cpwrap"><div class="top"><span class="t">'
                f'{esc(label)}</span><button onclick="cp(this)">コピー</button></div>'
                f'<pre class="cptext">{esc(text)}</pre></div>')
    def note(kind, text):
        return f'<div class="note {kind}">{text}</div>'
    def thread(rows):
        msgs = []
        for i, (role, text) in enumerate(rows):
            side = "main" if "メイン" in role else ("sub" if "サブ" in role else "main")
            hot = " hot" if "150" in role else ""
            indent = min(i, 4) * 18
            msgs.append(
                f'<div class="msg cpwrap {side}{hot}" style="margin-left:{indent}px">'
                f'<div class="mhead"><span class="role {side}">{esc(role)}</span>'
                f'<button onclick="cp(this)">コピー</button></div>'
                f'<div class="mtext cptext">{esc(text)}</div></div>')
        return '<div class="thread">' + "".join(msgs) + '</div>'

    def threads_html(rows_list):
        out = []
        for idx, rows in enumerate(rows_list):
            out.append(f'<div class="thlabel">会話例{idx+1}（1投稿＝この返信の流れ）</div>')
            out.append(thread(rows))
        return out

    def schedule_html(days):
        out = []
        for d in days:
            out.append(f'<div class="subhead">📅 Day {d["day"]}（{len(d["posts"])}投稿）</div>')
            for p in d["posts"]:
                label = f'{p.get("slot","")}・{p.get("kind","投稿")}'
                out.append(copy(label, p["text"]))
                if p.get("rally"):
                    out.append('<div class="thlabel">↳ サブで会話を自作（このリプを付ける）</div>')
                    out.append(thread([
                        ["② サブが返信（無リンク）", p["rally"]["sub"]],
                        ["③ メインが返信 ＝150倍", p["rally"]["main"]],
                    ]))
        return out

    blocks = []
    for p in phases:
        body = []
        if p.get("intro"):
            body.append(note("info", p["intro"]))
        if p.get("groups"):
            # フェーズ内を複数のラベル付きグループに分けて表示
            for g in p["groups"]:
                body.append(f'<div class="subhead">{g["label"]}</div>')
                body += [task(t) for t in g.get("tasks", [])]
                if g.get("copies"):
                    body.append('<div class="grid">')
                    body += [copy(l, t) for l, t in g["copies"]]
                    body.append('</div>')
                if g.get("threads"):
                    body += threads_html(g["threads"])
            if p.get("schedule"):
                body += schedule_html(p["schedule"])
        else:
            if p.get("tasks"):
                body.append('<div class="subhead">✅ やること</div>')
                body += [task(t) for t in p["tasks"]]
            if p.get("copies") or p.get("threads"):
                body.append('<div class="subhead">📋 コピペ素材</div>')
            if p.get("copies"):
                body.append('<div class="grid">')
                body += [copy(l, t) for l, t in p["copies"]]
                body.append('</div>')
            if p.get("threads"):
                body += threads_html(p["threads"])
        for kind, text in p["notes"]:
            body.append(note(kind, text))
        blocks.append(
            '<div class="phase"><h2><span class="badge">'
            f'{p["badge"]}</span>{esc(p["title"])}'
            f'<span class="when">{esc(p["when"])}</span></h2>'
            f'<div class="body">{"".join(body)}</div></div>')
    return "\n".join(blocks)


HTML = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>初期アカウント立ち上げロードマップ｜__NAME__</title>
<style>
:root{--bg:#0a0e14;--panel:#151a23;--panel2:#1c2230;--line:#2a3344;--txt:#e7ecf3;--sub:#9fb0c3;--accent:#1d9bf0;--green:#00ba7c;--warn:#f4a52a;--danger:#f4385a;--gold:#ffd24a}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(1200px 600px at 50% -10%,#16202e 0%,var(--bg) 60%);color:var(--txt);font-family:-apple-system,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;line-height:1.7;padding:36px 14px}
.wrap{max-width:880px;margin:0 auto}
header{text-align:center;margin-bottom:18px}
.x-logo{font-weight:900;font-size:26px;background:#000;color:#fff;width:50px;height:50px;display:inline-flex;align-items:center;justify-content:center;border-radius:13px;margin-bottom:12px;border:1px solid var(--line)}
h1{font-size:24px;font-weight:800}
.lead{color:var(--sub);margin-top:8px;font-size:14px}
.acct{display:inline-flex;gap:8px;align-items:center;margin-top:12px;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:13px}
.acct b{color:#fff}.acct .id{color:var(--accent)}
.concept{max-width:620px;margin:12px auto 0;background:#10283b;border:1px solid #244a6b;border-radius:12px;padding:12px 16px;color:#cfe5f7;font-size:13px;white-space:pre-wrap;text-align:left}
.prog{position:sticky;top:0;z-index:5;background:#0a0e14ee;backdrop-filter:blur(6px);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:18px 0 24px;display:flex;align-items:center;gap:12px}
.bar{flex:1;height:9px;background:var(--panel2);border-radius:999px;overflow:hidden}
.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent),var(--green));transition:.3s}
.prog small{color:var(--sub);font-size:12px;white-space:nowrap}
.reset{background:none;border:1px solid var(--line);color:var(--sub);border-radius:8px;padding:4px 9px;font-size:11px;cursor:pointer}
.phase{margin:20px 0;border:1px solid var(--line);border-radius:16px;overflow:hidden;background:var(--panel)}
.phase>h2{display:flex;align-items:center;gap:12px;padding:15px 18px;font-size:18px;background:linear-gradient(135deg,#10283b,#141b29);border-bottom:1px solid var(--line)}
.phase .badge{flex:none;width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-weight:800;background:var(--panel2);border:1px solid var(--line);font-size:14px}
.phase .when{margin-left:auto;font-size:11px;color:var(--sub);background:#0e2233;border:1px solid #244a6b;padding:3px 10px;border-radius:999px}
.body{padding:12px 18px 18px}
.subhead{font-size:12px;font-weight:800;color:#7fb6e6;letter-spacing:.4px;margin:16px 0 6px;border-left:3px solid var(--accent);padding-left:8px}
.task{display:flex;gap:11px;padding:9px 0;border-bottom:1px dashed #232b39;align-items:flex-start}
.task:last-child{border-bottom:0}
.task input{appearance:none;flex:none;width:21px;height:21px;margin-top:2px;border:2px solid #3a475c;border-radius:6px;cursor:pointer;position:relative;transition:.15s}
.task input:checked{background:var(--green);border-color:var(--green)}
.task input:checked::after{content:"\\2713";position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#04150f;font-weight:900;font-size:13px}
.task label{cursor:pointer;font-size:14.5px}
.task.done label{color:#5f6f82;text-decoration:line-through}
.copy{margin:10px 0;border:1px solid var(--line);border-radius:11px;background:var(--panel2);overflow:hidden}
.copy .top{display:flex;align-items:center;gap:8px;padding:7px 12px;background:#0f1622;border-bottom:1px solid var(--line);font-size:12px;color:var(--sub)}
.copy .top .t{font-weight:700;color:#cdd9e7}
.copy button{margin-left:auto;background:var(--accent);color:#fff;border:0;border-radius:7px;padding:5px 12px;font-size:12px;font-weight:700;cursor:pointer}
.copy button.ok{background:var(--green)}
.copy pre{padding:12px 14px;white-space:pre-wrap;word-break:break-word;font-family:inherit;font-size:13.5px;color:#eef4fb}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:620px){.grid{grid-template-columns:1fr}}
.thlabel{font-size:12px;color:var(--sub);margin:14px 0 4px;font-weight:700}
.thread{border:1px solid var(--line);border-radius:12px;padding:10px;background:#10151e;margin-bottom:10px}
.msg{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin:6px 0}
.msg.main{border-color:#244a6b}.msg.sub{border-color:#5a4a1d}
.msg.hot{border-color:var(--green);box-shadow:0 0 0 1px #00ba7c55}
.mhead{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.role{font-size:11px;font-weight:700;padding:2px 9px;border-radius:999px}
.role.main{background:#0e2233;color:#6ec5ff;border:1px solid #244a6b}
.role.sub{background:#241c10;color:#f0c06a;border:1px solid #5a4a1d}
.msg .mhead button{margin-left:auto;background:var(--accent);color:#fff;border:0;border-radius:7px;padding:4px 10px;font-size:11px;font-weight:700;cursor:pointer}
.msg .mhead button.ok{background:var(--green)}
.mtext{font-size:13.5px;color:#eef4fb;white-space:pre-wrap}
.note{margin:12px 0;border-radius:11px;padding:11px 14px;font-size:13px}
.note.warn{background:#251f10;border:1px solid #5a4a1d;color:#f0dca0}
.note.danger{background:#2a1119;border:1px solid #5e2031;color:#ffb3c1}
.note.info{background:#0e2233;border:1px solid #244a6b;color:#bfe0fb}
.note b{color:#fff}
footer{margin-top:26px;border-top:1px solid var(--line);padding-top:16px;color:var(--sub);font-size:12.5px;text-align:center}
</style></head><body><div class="wrap">
<header>
  <div class="x-logo">&#120143;</div>
  <h1>初期アカウント立ち上げロードマップ</h1>
  <p class="lead">各フェーズは「✅やること」と「📋コピペ素材」に分けてあります。</p>
  <div class="acct">メイン：<b>__NAME__</b> <span class="id">__ID__</span></div>
  <div class="concept">__CONCEPT__</div>
</header>
<div class="prog"><div class="bar"><i id="barFill"></i></div><small id="progTxt">0 / 0 完了</small><button class="reset" onclick="resetAll()">リセット</button></div>
__BLOCKS__
<footer>チェック状態はこのブラウザに自動保存されます（リセットで全解除）。<br>元ナレッジ：ナレッジ/アカウント立ち上げ/ ／ 数理：ナレッジ/集客・導線/アルゴリズム解析（2026）</footer>
</div>
<script>
function cp(btn){var el=btn.closest('.cpwrap').querySelector('.cptext');navigator.clipboard.writeText(el.innerText).then(function(){var o=btn.textContent;btn.textContent='コピー\\u2713';btn.classList.add('ok');setTimeout(function(){btn.textContent=o;btn.classList.remove('ok')},1200)})}
var KEY='x-launch-roadmap-'+(document.title);
var boxes=[].slice.call(document.querySelectorAll('.task input[type=checkbox]'));
var saved=JSON.parse(localStorage.getItem(KEY)||'{}');
function update(){var done=0;boxes.forEach(function(b){if(b.checked){done++;b.closest('.task').classList.add('done')}else b.closest('.task').classList.remove('done')});var pct=boxes.length?Math.round(done/boxes.length*100):0;document.getElementById('barFill').style.width=pct+'%';document.getElementById('progTxt').textContent=done+' / '+boxes.length+' 完了（'+pct+'%）'}
boxes.forEach(function(b){if(saved[b.id])b.checked=true;b.addEventListener('change',function(){saved[b.id]=b.checked;localStorage.setItem(KEY,JSON.stringify(saved));update()})});
function resetAll(){if(confirm('チェックを全部リセットしますか？')){localStorage.removeItem(KEY);boxes.forEach(function(b){b.checked=false});update()}}
update();
</script></body></html>"""


def main():
    c = load_concept()
    phases = build_phases(c)
    # 出力先：明示が無ければ「ロードマップ/<アカウント名>_立ち上げロードマップ.html」
    out = out_path or (ROOT / "ロードマップ" / f"{safe_name(c['name'])}_立ち上げロードマップ.html")
    page = (HTML.replace("__NAME__", esc(c["name"]))
                .replace("__ID__", esc(c["id"]))
                .replace("__CONCEPT__", esc(c["concept_line"]))
                .replace("__BLOCKS__", render(phases)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    n = sum(len(p.get("tasks", [])) for p in phases)
    print(f"✓ 生成: {out}")
    print(f"  コンセプト: {c['name']} {c['id']} / フェーズ{len(phases)} / タスク{n}件")


if __name__ == "__main__":
    main()
