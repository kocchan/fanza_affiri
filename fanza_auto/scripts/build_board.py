#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投稿ボード `works/board.html`（全作品一覧）を作る。

やること:
  works/ の各作品について「作品情報」「投稿文（1本）」「アフィリリンク」を
  1枚のHTMLにまとめ、それぞれワンクリックでコピーできるようにする。

■ 単一作品モード（cid を渡す）
  cid を指定すると、その1作品だけの `works/board_<cid>.html` を作る。
  こちらには動画プレーヤー・切り抜き・保存が付く。
  ただし切り抜き（ffmpeg処理）はサーバー経由でのみ動くので、
  `serve_board.py <cid>` から使うのが基本（file:// 直開きは再生と保存だけ）。

投稿文は一度作ったら `works/posts.json` に保存して固定する。
毎回作り直すと「昨日いいと思った文が今日は変わっている」ことになるため。
文を作り直したいときだけ --regen を付ける。

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/build_board.py            # 全作品の一覧ボード
    python3 fanza_auto/scripts/build_board.py debz015    # その1作品だけ（動画つき）
    python3 fanza_auto/scripts/build_board.py --regen    # 投稿文を作り直す
    python3 fanza_auto/scripts/build_board.py --open     # 作ってそのまま開く
"""

import datetime
import html
import json
import random
import subprocess
import sys
import urllib.parse

import common as C
import post_text as PT

POSTS_JSON = C.WORKS_DIR / "posts.json"
BOARD_HTML = C.WORKS_DIR / "board.html"


def single_board_path(cid: str):
    """単一作品ボードのファイルパス（works/board_<cid>.html）。"""
    safe = "".join(ch for ch in cid if ch.isalnum() or ch in "_-")
    return C.WORKS_DIR / f"board_{safe}.html"


# ──────────────────────────────────────────────
# 投稿文の生成と保存
# ──────────────────────────────────────────────
def load_posts() -> dict:
    if POSTS_JSON.is_file():
        try:
            return json.loads(POSTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_posts(posts: dict) -> None:
    POSTS_JSON.write_text(
        json.dumps(posts, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8")


def ensure_posts(entries: list, regen: bool) -> dict:
    """作品ごとの投稿文を用意する（既にあれば使い回す）。"""
    posts = load_posts()
    made = 0
    for e in entries:
        cid = e["cid"]
        if regen or cid not in posts:
            posts[cid] = PT.build(e["item"], e["aff_url"])
            made += 1
    save_posts(posts)
    if made:
        print(f"  投稿文を生成: {made} 件"
              + ("（--regen で作り直し）" if regen else "（新規のぶんだけ）"))
    return posts


# ──────────────────────────────────────────────
# 作品情報の組み立て
# ──────────────────────────────────────────────
def collect(cfg: dict) -> list:
    """works/ を走査して、ボードに出す作品の情報を集める。"""
    entries = []
    for d in C.work_dirs():
        item = C.read_item(d)
        cid = C.cid_of(d)
        aff_url = item.get("affiliateURL") or ""
        if aff_url:
            aff_url = C.rewrite_aff_url(aff_url, cfg)
        avg, count = PT.review_of(item)
        entries.append({
            "dir": d,
            "cid": cid,
            "item": item,
            "aff_url": aff_url,
            "title": item.get("title") or d.name.split("_", 1)[-1],
            "review_avg": avg,
            "review_count": count,
            "duration": PT.duration_text(item),
            "date": (item.get("date") or "")[:10],
            "maker": ", ".join(
                m.get("name", "") for m in
                ((item.get("iteminfo") or {}).get("maker") or [])),
            "genres": PT.genres_of(item),
            "page_url": item.get("URL") or "",
            "has_meta": bool(item),
            "has_movie": (d / "sample.mp4").is_file(),
            "n_images": len(list(d.glob("[0-9][0-9].jpg"))),
            # 動画まわり（単一作品モードで使う）
            "movie": "sample.mp4" if (d / "sample.mp4").is_file() else "",
            "clips": sorted(p.name for p in d.glob("cut_*.mp4")),
        })
    return entries


def sort_key(e: dict):
    """おすすめ順：レビューが良く、件数がある作品を上に。"""
    avg = e["review_avg"] if e["review_avg"] is not None else 0.0
    # 件数1件の★5.00 より、件数の多い★4.6 を上に出したいので件数で重み付け
    weight = min(e["review_count"], 20) / 20.0
    return (-(avg * (0.5 + 0.5 * weight)), -e["review_count"], e["cid"])


# ──────────────────────────────────────────────
# HTML
# ──────────────────────────────────────────────
CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1a1c1f;--sub:#5c6370;--line:#e2e5ea;
      --accent:#c2185b;--warn:#b45309;--warnbg:#fef3c7;--ok:#0f766e;--okbg:#ccfbf1;}
@media (prefers-color-scheme:dark){
 :root{--bg:#14161a;--card:#1c1f25;--fg:#e8eaed;--sub:#9aa3b0;--line:#2c313a;
       --accent:#f06292;--warn:#fbbf24;--warnbg:#3a2f12;--ok:#5eead4;--okbg:#0f2f2b;}}
*{box-sizing:border-box}
body{margin:0;padding:0 16px 64px;background:var(--bg);color:var(--fg);
 font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Yu Gothic",sans-serif;
 line-height:1.7;-webkit-text-size-adjust:100%}
.wrap{max-width:960px;margin:0 auto}
header{padding:28px 0 16px}
h1{font-size:1.5rem;margin:0 0 6px}
.lead{color:var(--sub);margin:0 0 4px;font-size:.9rem}
.tools{position:sticky;top:0;z-index:5;background:var(--bg);padding:12px 0;
 border-bottom:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input[type=search]{flex:1;min-width:180px;padding:9px 12px;border:1px solid var(--line);
 border-radius:8px;background:var(--card);color:var(--fg);font-size:.95rem}
.chk{display:flex;align-items:center;gap:5px;font-size:.85rem;color:var(--sub);
 white-space:nowrap;cursor:pointer}
.count{font-size:.85rem;color:var(--sub);white-space:nowrap}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
 padding:18px;margin:16px 0}
.card.done{opacity:.5}
.card h2{font-size:1.1rem;margin:0 0 8px;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.cid{font-size:.75rem;color:var(--sub);font-weight:400}
.meta{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.85rem;color:var(--sub);
 margin:0 0 10px}
.meta b{color:var(--fg);font-weight:600}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 12px}
.tag{font-size:.72rem;padding:2px 8px;border-radius:999px;background:var(--bg);
 border:1px solid var(--line);color:var(--sub)}
.tag.warn{background:var(--warnbg);color:var(--warn);border-color:transparent;font-weight:600}
.notice{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:9px 12px;
 font-size:.83rem;margin:0 0 12px}
.pat{display:inline-block;font-size:.75rem;padding:2px 9px;border-radius:999px;
 background:var(--okbg);color:var(--ok);font-weight:600;margin-bottom:10px}
.blk{margin:0 0 14px}
.blk-h{display:flex;justify-content:space-between;align-items:center;gap:8px;
 font-size:.83rem;font-weight:700;margin:0 0 5px}
pre{margin:0;padding:12px;background:var(--bg);border:1px solid var(--line);
 border-radius:8px;white-space:pre-wrap;word-break:break-word;font-size:.9rem;
 font-family:inherit}
pre.link{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.72rem;color:var(--sub)}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);
 border-radius:7px;padding:5px 12px;font-size:.8rem;cursor:pointer;white-space:nowrap;
 font-family:inherit}
button:hover{border-color:var(--accent);color:var(--accent)}
button.copied{background:var(--okbg);color:var(--ok);border-color:transparent}
.foot{display:flex;justify-content:space-between;align-items:center;gap:10px;
 border-top:1px solid var(--line);padding-top:12px;margin-top:4px;flex-wrap:wrap}
a{color:var(--accent)}
.empty{text-align:center;color:var(--sub);padding:40px 0}
/* 動画（単一作品モード） */
.video{margin:0 0 16px}
.video video{width:100%;max-height:70vh;background:#000;border-radius:10px;display:block}
.cuttool{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0 4px}
.cuttool label{font-size:.82rem;color:var(--sub);display:flex;gap:4px;align-items:center}
.cuttool input{width:74px;padding:5px 8px;border:1px solid var(--line);border-radius:6px;
 background:var(--card);color:var(--fg);font-size:.85rem;font-family:ui-monospace,Menlo,monospace}
.cuttool .now{padding:4px 8px;font-size:.74rem}
.cuttool .go{background:var(--accent);color:#fff;border-color:transparent;font-weight:700}
.cuttool .go:hover{opacity:.9;color:#fff}
.hint{font-size:.78rem;color:var(--sub);margin:0 0 8px}
.clips{display:flex;flex-direction:column;gap:12px}
.clip{border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--bg)}
.clip video{width:100%;border-radius:6px;background:#000;display:block;margin-bottom:8px}
.clip-h{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;
 font-size:.82rem;font-weight:700;margin-bottom:6px}
.dl{display:inline-block;border:1px solid var(--line);border-radius:7px;padding:5px 12px;
 font-size:.8rem;text-decoration:none;color:var(--fg)}
.dl:hover{border-color:var(--accent);color:var(--accent)}
.err{color:var(--accent);font-size:.8rem;margin:6px 0 0}
"""

JS = """
function flash(btn,msg){const o=btn.textContent;btn.textContent=msg;
 btn.classList.add('copied');setTimeout(()=>{btn.textContent=o;
 btn.classList.remove('copied')},1200);}

// file:// で開くと navigator.clipboard が使えないブラウザがあるので、
// 古いやり方（textarea + execCommand）に必ず落とせるようにしておく。
function copyText(text,btn){
  const fallback=()=>{const t=document.createElement('textarea');
    t.value=text;t.style.position='fixed';t.style.opacity='0';
    document.body.appendChild(t);t.select();
    try{document.execCommand('copy');flash(btn,'✓ コピーした');}
    catch(e){alert('コピーできませんでした。手で選択してください。');}
    document.body.removeChild(t);};
  if(navigator.clipboard&&window.isSecureContext){
    navigator.clipboard.writeText(text).then(()=>flash(btn,'✓ コピーした'),fallback);
  }else{fallback();}
}

document.addEventListener('click',e=>{
  const b=e.target.closest('button[data-copy]');
  if(!b)return;
  const el=document.getElementById(b.dataset.copy);
  if(el)copyText(el.textContent,b);
});

// 「投稿した」印はブラウザに保存する（サーバー不要）。
const DONE='fanza_board_done';
const done=new Set(JSON.parse(localStorage.getItem(DONE)||'[]'));
function paint(){document.querySelectorAll('.card').forEach(c=>{
  const on=done.has(c.dataset.cid);
  c.classList.toggle('done',on);
  const b=c.querySelector('button[data-done]');
  if(b)b.textContent=on?'✓ 投稿済み':'投稿済みにする';});filter();}
document.addEventListener('click',e=>{
  const b=e.target.closest('button[data-done]');
  if(!b)return;
  const cid=b.closest('.card').dataset.cid;
  done.has(cid)?done.delete(cid):done.add(cid);
  localStorage.setItem(DONE,JSON.stringify([...done]));paint();});

// 検索・絞り込みは一覧ボードにだけある（単一作品モードには無いので null 許容）。
const q=document.getElementById('q'),hide=document.getElementById('hide'),
      cnt=document.getElementById('cnt'),empty=document.getElementById('empty');
function filter(){
  if(!cnt)return;
  const s=q?q.value.trim().toLowerCase():'';let n=0;
  document.querySelectorAll('.card').forEach(c=>{
    const hit=!s||c.dataset.search.includes(s);
    const show=hit&&!(hide&&hide.checked&&done.has(c.dataset.cid));
    c.style.display=show?'':'none';if(show)n++;});
  cnt.textContent=n+' 件';
  if(empty)empty.style.display=n?'none':'';}
if(q)q.addEventListener('input',filter);
if(hide)hide.addEventListener('change',filter);
paint();

// ── 動画の切り抜き（単一作品モード）────────────────
// 「現在」ボタン：入力欄に動画の再生位置（秒）を入れる。
function secStr(v){return (Math.round(v*10)/10).toString();}
document.addEventListener('click',e=>{
  const b=e.target.closest('button.now');if(!b)return;
  const box=b.closest('.cuttool');
  const vid=document.getElementById(box.dataset.vid);
  const inp=document.getElementById(b.dataset.for);
  if(vid&&inp)inp.value=secStr(vid.currentTime||0);
});

// 「切り抜く」ボタン：サーバーに cut を投げ、返ってきた mp4 を下に足す。
document.addEventListener('click',async e=>{
  const b=e.target.closest('button.go');if(!b)return;
  const box=b.closest('.cuttool');
  const dir=box.dataset.dir, movie=box.dataset.movie;
  const s=document.getElementById(box.dataset.start).value.trim();
  const en=document.getElementById(box.dataset.end).value.trim();
  const err=box.parentElement.querySelector('.err');
  err.textContent='';
  if(s===''||en===''){err.textContent='開始と終了の秒を入れてください。';return;}
  if(parseFloat(en)<=parseFloat(s)){err.textContent='終了は開始より後にしてください。';return;}
  if(location.protocol==='file:'){
    err.textContent='切り抜きは serve_board.py 経由でのみ動きます（このページは file:// で開いています）。';return;}
  const old=b.textContent;b.textContent='切り抜き中…';b.disabled=true;
  try{
    const r=await fetch('/__cut',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir,video:movie,start:s,end:en})});
    const j=await r.json();
    if(!j.ok){err.textContent='失敗: '+(j.error||'不明なエラー');}
    else{addClip(box.dataset.uid,dir,j.file,s+'〜'+en);}
  }catch(ex){err.textContent='通信に失敗しました: '+ex;}
  b.textContent=old;b.disabled=false;
});

function addClip(uid,dir,file,range){
  const wrap=document.getElementById('clips-'+uid);
  const src=dir.split('/').map(encodeURIComponent).join('/')+'/'+encodeURIComponent(file);
  const el=document.createElement('div');el.className='clip';
  el.innerHTML=`<div class="clip-h"><span>✂ ${range}　${file}</span>
    <a class="dl" href="${src}" download="${file}">⬇ 保存</a></div>
    <video controls src="${src}"></video>`;
  wrap.prepend(el);
}
"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def rel_media(dir_name: str, file_name: str) -> str:
    """board_<cid>.html（works/直下）から見た動画への相対パス。
    日本語フォルダ名でも壊れないよう各セグメントをURLエンコードする。"""
    return (urllib.parse.quote(dir_name) + "/" + urllib.parse.quote(file_name))


def render_video(e: dict, uid: str) -> str:
    """単一作品モードの動画ブロック（再生＋切り抜き＋保存）。"""
    if not e["has_movie"]:
        return ('      <p class="notice">この作品にはサンプル動画がありません'
                '（画像のみ）。</p>')
    dir_name = e["dir"].name
    src = rel_media(dir_name, e["movie"])

    clips = ""
    for f in e["clips"]:
        csrc = rel_media(dir_name, f)
        clips += (f'<div class="clip"><div class="clip-h"><span>✂ {esc(f)}</span>'
                  f'<a class="dl" href="{csrc}" download="{esc(f)}">⬇ 保存</a></div>'
                  f'<video controls src="{csrc}"></video></div>')

    return f"""      <div class="video">
        <video controls id="vid-{uid}" src="{src}" preload="metadata"></video>
        <div class="cuttool" data-vid="vid-{uid}" data-dir="{esc(dir_name)}"
             data-movie="{esc(e['movie'])}" data-uid="{uid}"
             data-start="cs-{uid}" data-end="ce-{uid}">
          <label>開始<input id="cs-{uid}" inputmode="decimal" placeholder="秒"></label>
          <button class="now" data-for="cs-{uid}">現在</button>
          <label>終了<input id="ce-{uid}" inputmode="decimal" placeholder="秒"></label>
          <button class="now" data-for="ce-{uid}">現在</button>
          <button class="go">✂ 切り抜く</button>
          <a class="dl" href="{src}" download="{esc(e['cid'])}.mp4">⬇ 動画を保存</a>
        </div>
        <p class="err"></p>
        <p class="hint">「現在」を押すと今の再生位置（秒）が入ります。
           切り抜いた動画は下に出るので、⬇保存 → Finder から X にドラッグ。</p>
        <div class="clips" id="clips-{uid}">{clips}</div>
      </div>"""


def render_card(e: dict, post: dict, single: bool = False) -> str:
    cid = e["cid"]
    uid = cid.replace(".", "_")
    cautions = post.get("cautions") or []

    # メタ情報の行
    bits = []
    if e["review_avg"] is not None:
        bits.append(f"★<b>{e['review_avg']:.2f}</b>"
                    f"（{e['review_count']}件）")
    if e["duration"]:
        bits.append(f"収録 <b>{esc(e['duration'])}</b>")
    if e["date"]:
        bits.append(f"発売 {esc(e['date'])}")
    if e["maker"]:
        bits.append(f"メーカー {esc(e['maker'])}")
    assets = []
    if e["has_movie"]:
        assets.append("動画あり")
    if e["n_images"]:
        assets.append(f"画像{e['n_images']}枚")
    if assets:
        bits.append(" / ".join(assets))

    tags = "".join(
        f'<span class="tag{" warn" if g in PT.CAUTION_GENRES else ""}">{esc(g)}</span>'
        for g in e["genres"])

    notice = ""
    if cautions:
        notice = (f'<p class="notice">⚠️ このジャンルが付いています：'
                  f'<b>{esc("・".join(cautions))}</b>。'
                  f'投稿文には出していませんが、<b>画像は未成年に見えないか必ず目視で確認</b>'
                  f'してから使ってください。</p>')
    if not e["has_meta"]:
        notice += ('<p class="notice">作品情報が取れていません（配信終了の可能性）。'
                   '<code>meta.py</code> で取り直せます。</p>')

    def block(label, text, elid, extra_cls=""):
        return f"""      <div class="blk">
        <div class="blk-h"><span>{label}</span>
          <button data-copy="{elid}">コピー</button></div>
        <pre class="{extra_cls}" id="{elid}">{esc(text)}</pre>
      </div>"""

    boosters = "\n".join(f"・{b}" for b in post.get("boosters", []))
    search = f"{e['title']} {cid} {' '.join(e['genres'])} {e['maker']}".lower()

    parts = [
        f'    <article class="card" data-cid="{esc(cid)}" '
        f'data-search="{esc(search)}">',
        f'      <h2>{esc(e["title"])}<span class="cid">{esc(cid)}</span></h2>',
        f'      <p class="meta">{" ".join(bits)}</p>',
        f'      <div class="tags">{tags}</div>' if tags else "",
        notice,
        render_video(e, uid) if single else "",
        f'      <span class="pat">型：{esc(post.get("label", ""))}</span>',
        block("① サブ投稿（リンクを持たせる側）", post.get("sub", ""),
              f"sub-{uid}"),
        block("② メイン投稿（①を引用して出す・リンクは貼らない）",
              post.get("main", ""), f"main-{uid}"),
    ]
    if boosters:
        parts.append(block("③ 賑やかし（サブへのリプ・1〜2件だけ）",
                           boosters, f"bst-{uid}"))
    if e["aff_url"]:
        parts.append(block("アフィリエイトリンク（単体）", e["aff_url"],
                           f"aff-{uid}", "link"))

    page = (f'<a href="{esc(e["page_url"])}" target="_blank" '
            f'rel="noopener">FANZAの作品ページ →</a>') if e["page_url"] else ""
    parts += [
        '      <div class="foot">',
        f'        <span>{page}</span>',
        '        <button data-done="1">投稿済みにする</button>',
        "      </div>",
        "    </article>",
    ]
    return "\n".join(p for p in parts if p)


def render(entries: list, posts: dict) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = "\n".join(render_card(e, posts.get(e["cid"], {}))
                      for e in entries)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FANZA 投稿ボード</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>FANZA 投稿ボード</h1>
  <p class="lead">作品情報・投稿文・アフィリリンクをコピーして使うボード。
     評価の高い作品から順に並んでいます。</p>
  <p class="lead">流れは <b>①サブ投稿（リンク付き）を出す → ②メインでそれを引用</b>。
     メイン投稿にリンクは貼りません。画像の選定・切り抜きは旧ボードで行います。</p>
  <p class="lead">更新 {now} ／ 全 {len(entries)} 作品</p>
</header>
<div class="tools">
  <input type="search" id="q" placeholder="作品名・cid・ジャンルで絞り込み">
  <label class="chk"><input type="checkbox" id="hide">投稿済みを隠す</label>
  <span class="count" id="cnt">{len(entries)} 件</span>
</div>
{cards}
<p class="empty" id="empty" style="display:none">該当する作品がありません。</p>
</div>
<script>{JS}</script>
</body>
</html>
"""


def render_single(e: dict, post: dict) -> str:
    """単一作品ボード（動画つき）のHTML全体。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    card = render_card(e, post, single=True)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(e['title'])}｜FANZA 投稿ボード</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{esc(e['title'])} <span class="cid">{esc(e['cid'])}</span></h1>
  <p class="lead">この作品ぶんの投稿ボード。動画は再生・切り抜き・保存ができます。</p>
  <p class="lead"><a href="board.html">← 全作品の一覧へ</a> ／ 更新 {now}</p>
</header>
{card}
</div>
<script>{JS}</script>
</body>
</html>
"""


def build_single(cid: str, cfg: dict, regen: bool):
    """cid 1件ぶんのボードを生成してパスを返す。見つからなければ None。"""
    entries = collect(cfg)
    match = next((e for e in entries if e["cid"] == cid), None)
    if match is None:
        avail = ", ".join(sorted(e["cid"] for e in entries))
        print(f"✗ cid={cid} の作品が works/ に見つかりません。")
        print(f"  使える cid: {avail}")
        return None
    posts = ensure_posts([match], regen=regen)
    out = single_board_path(cid)
    out.write_text(render_single(match, posts.get(cid, {})), encoding="utf-8")
    print(f"✓ 単一作品ボードを作りました: {out}")
    if not match["has_movie"]:
        print("  ※ この作品にはサンプル動画がありません（切り抜きは使えません）。")
    return out


def main(argv) -> int:
    flags = set(a for a in argv[1:] if a.startswith("--"))
    positional = [a for a in argv[1:] if not a.startswith("--")]
    cfg = C.load_config(require_api=False)
    regen = "--regen" in flags

    # cid が渡されたら、その1作品だけのボード（動画つき）を作る。
    if positional:
        cid = positional[0]
        out = build_single(cid, cfg, regen)
        if out is None:
            return 1
        print("  切り抜きを使うには: "
              f"python3 fanza_auto/scripts/serve_board.py {cid}")
        if "--open" in flags:
            subprocess.run(["open", str(out)], check=False)
        return 0

    entries = collect(cfg)
    if not entries:
        print("works/ に作品フォルダがありません。"
              "先に fetch_and_build.py を実行してください。")
        return 1

    no_meta = [e for e in entries if not e["has_meta"]]
    if no_meta:
        print(f"  ※ 作品情報が無いフォルダが {len(no_meta)} 件あります。"
              "`python3 fanza_auto/scripts/meta.py` で取得できます。")

    posts = ensure_posts(entries, regen=regen)
    entries.sort(key=sort_key)
    BOARD_HTML.write_text(render(entries, posts), encoding="utf-8")

    print(f"✓ ボードを作りました: {BOARD_HTML}")
    print(f"  {len(entries)} 作品 ／ 投稿文は works/posts.json に保存"
          "（作り直すときは --regen）")
    if "--open" in flags:
        subprocess.run(["open", str(BOARD_HTML)], check=False)
    else:
        print(f"  開く: open {BOARD_HTML}")
    return 0


if __name__ == "__main__":
    random.seed()
    sys.exit(main(sys.argv))
