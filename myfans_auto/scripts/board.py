#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MyFans 1作品ぶんの投稿ボード `works/board_<投稿ID>.html` を作る
（動画プレーヤー・切り抜き・保存つき）。fanza_auto/scripts/build_board.py の
MyFans向け簡略版（レビュー評価・ジャンル・発売日・MissAV確認は無い＝表示しない）。

やること:
  指定した投稿IDの作品について「作品情報」「投稿文（1本）」「アフィリリンク」を
  1枚のHTMLにまとめ、それぞれワンクリックでコピーできるようにする。
  ただし切り抜き（ffmpeg処理）はサーバー経由でのみ動くので、
  `serve.py <投稿ID>` から使うのが基本（file:// 直開きは再生と保存だけ）。

全作品をまとめて見たいときは `dashboard.py`（`works/board.html`）を使う。
アーカイブした作品は `works/archive.html` に集約される（`serve.py` 経由で操作）。

投稿文は一度作ったら `works/posts.json` に保存して固定する。
文を作り直したいときだけ --regen を付ける。

使い方（プロジェクトのルートフォルダで実行）:
    python3 myfans_auto/scripts/board.py <投稿ID>            # その1作品だけ（動画つき）
    python3 myfans_auto/scripts/board.py <投稿ID> --regen    # 投稿文を作り直す
    python3 myfans_auto/scripts/board.py <投稿ID> --open     # 作ってそのまま開く
"""

import datetime
import html
import json
import subprocess
import sys
import urllib.parse

import caption as CAP
import common as C
import post_text as PT
import templates as T

POSTS_JSON = C.WORKS_DIR / "posts.json"


def single_board_path(cid: str):
    """単一作品ボードのファイルパス（works/board_<投稿ID>.html）。"""
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


def set_main_text(cid: str, text: str) -> None:
    """メイン投稿文だけを人の手で上書き保存する（手動編集・AI再生成ボタンの両方から呼ばれる）。"""
    posts = load_posts()
    post = posts.get(cid) or {}
    post["main"] = text
    posts[cid] = post
    save_posts(posts)


def ensure_posts(entries: list, regen: bool) -> dict:
    """作品ごとの投稿文を用意する（既にあれば使い回す）。

    リンク投稿（sub）・賑やかしは post_text.py（FANZA用）をそのまま流用するが、
    メイン投稿だけは本文（description）から場所・シチュエーションを拾って
    その作品らしい短い反応文にする（caption.py）。post_text.py の型選択は
    レビュー/ジャンル前提でMyFansには効かないため、メインはここで作り直す。"""
    posts = load_posts()
    made = 0
    for e in entries:
        cid = e["cid"]
        if regen or cid not in posts:
            post = PT.build(e["item"], e["aff_url"])
            post["main"] = CAP.build_main_text(
                e["item"].get("description", ""), T.REACTION_HOOKS)
            posts[cid] = post
            made += 1
    save_posts(posts)
    if made:
        print(f"  投稿文を生成: {made} 件"
              + ("（--regen で作り直し）" if regen else "（新規のぶんだけ）"))
    return posts


# ──────────────────────────────────────────────
# 作品情報の組み立て
# ──────────────────────────────────────────────
def collect() -> list:
    """works/ を走査して、ボードに出す作品の情報を集める。
    MyFansには評価・ジャンル・発売日・メーカーが無いのでFANZA版のcollect()より項目が少ない。"""
    entries = []
    for d in C.work_dirs():
        item = C.read_item(d)
        cid = C.cid_of(d)
        entries.append({
            "dir": d,
            "cid": cid,
            "item": item,
            "aff_url": item.get("affiliateURL") or "",
            "title": item.get("title") or d.name.split("_", 1)[-1],
            "creator": item.get("creator") or "",
            "page_url": item.get("URL") or "",
            "has_meta": bool(item),
            "has_movie": (d / "sample.mp4").is_file(),
            "n_images": len(list(d.glob("[0-9][0-9].jpg"))),
            # 動画まわり（単一作品モードで使う）
            "movie": "sample.mp4" if (d / "sample.mp4").is_file() else "",
            # 手動で作った素材（区間切り cut_* ＋ 画面トリミング crop_*）
            "clips": sorted(p.name for p in d.glob("*.mp4")
                            if p.name.startswith(("cut_", "crop_"))),
            # サムネの元ネタ候補：取り込んだサムネ画像＋動画から切り抜いた静止画。
            "images": sorted(p.name for p in d.glob("[0-9][0-9].jpg")),
            "grabs": sorted(p.name for p in d.glob("clip_*.jpg")),
            # 確定したサムネ（候補をOK/トリミングして作った成果物）
            "thumbs": sorted(p.name for p in d.glob("thumb_*.jpg")),
        })
    return entries


def sort_key(e: dict):
    """おすすめ順：動画が入っている（＝投稿に使える）作品を上に、あとは取り込み順。"""
    return (0 if e["has_movie"] else 1, e["cid"])


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
textarea.mainedit{width:100%;min-height:80px;margin:0;padding:12px;background:var(--bg);
 border:1px solid var(--line);border-radius:8px;font-size:.9rem;font-family:inherit;
 color:var(--fg);resize:vertical;box-sizing:border-box}
.mainrow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px}
.save-status{font-size:.78rem;color:var(--ok)}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);
 border-radius:7px;padding:5px 12px;font-size:.8rem;cursor:pointer;white-space:nowrap;
 font-family:inherit}
button:hover{border-color:var(--accent);color:var(--accent)}
button.copied{background:var(--okbg);color:var(--ok);border-color:transparent}
.foot{display:flex;justify-content:space-between;align-items:center;gap:10px;
 border-top:1px solid var(--line);padding-top:12px;margin-top:4px;flex-wrap:wrap}
.archive-actions{display:flex;gap:8px}
button.delete-btn:hover{border-color:#dc2626;color:#dc2626}
button.archive-btn{border-color:#dc2626;color:#dc2626}
button.archive-btn:hover{background:#dc2626;color:#fff}
a{color:var(--accent)}
.empty{text-align:center;color:var(--sub);padding:40px 0}
/* 動画（単一作品モード） */
/* 動画ボックス・サムネ画像ボックスを見た目でもはっきり分ける */
.video{margin:0 0 16px;padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--bg)}
.video h3,.thumbtool h3{font-size:1rem;margin:0 0 10px}
.vwrap{position:relative;line-height:0;border-radius:10px;overflow:hidden}
.video video{width:100%;max-height:70vh;background:#000;display:block}
/* 範囲選択オーバーレイ（普段は非表示。選択モードON時だけ有効） */
.sellayer{position:absolute;inset:0;display:none;cursor:crosshair;touch-action:none;
 background:rgba(0,0,0,.25)}
.sellayer.on{display:block}
.sellayer .selbox{position:absolute;border:2px solid #fff;outline:2px solid var(--accent);
 background:rgba(194,24,91,.18);box-shadow:0 0 0 9999px rgba(0,0,0,.35)}
.crow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%}
.crow b{font-size:.8rem;color:var(--fg)}
.selinfo{font-size:.78rem;color:var(--sub)}
.selbtn{font-size:.8rem}
.selbtn.on{background:var(--accent);color:#fff;border-color:transparent}
.cuttool,.croptool{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0 4px;
 padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg)}
.tool-label{font-size:.8rem;font-weight:700;color:var(--fg);width:100%}
.cuttool label,.croptool label{font-size:.82rem;color:var(--sub);display:flex;gap:4px;align-items:center}
.cuttool input[type=text],.cuttool input:not([type]){width:74px}
.cuttool input,.croptool select{padding:5px 8px;border:1px solid var(--line);border-radius:6px;
 background:var(--card);color:var(--fg);font-size:.85rem}
.cuttool input{width:74px;font-family:ui-monospace,Menlo,monospace}
.croptool .chk{gap:5px}
.cuttool .now{padding:4px 8px;font-size:.74rem}
.cuttool .go,.croptool .go{background:var(--accent);color:#fff;border-color:transparent;font-weight:700}
.cuttool .go:hover,.croptool .go:hover{opacity:.9;color:#fff}
.hint{font-size:.78rem;color:var(--sub);margin:0 0 8px}
.clips{display:flex;flex-direction:column;gap:12px}
.clip{border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--bg)}
.clip video{width:100%;border-radius:6px;background:#000;display:block;margin-bottom:8px}
.clip-h{display:flex;justify-content:space-between;align-items:center;gap:8px;
 font-size:.82rem;font-weight:700;margin-bottom:6px}
.clip-h>span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.dl{display:inline-block;border:1px solid var(--line);border-radius:7px;padding:5px 12px;
 font-size:.8rem;text-decoration:none;color:var(--fg);white-space:nowrap;flex-shrink:0}
.dl:hover{border-color:var(--accent);color:var(--accent)}
.clip-act{display:flex;gap:6px;align-items:center;flex-shrink:0}
button.del{font-size:.78rem;padding:5px 10px;color:var(--sub);white-space:nowrap;flex-shrink:0}
button.del:hover{border-color:#dc2626;color:#dc2626}
.err{color:var(--accent);font-size:.8rem;margin:6px 0 0}

/* サムネ画像作成セクション */
/* サムネ画像ボックス（動画ボックスと同じ見た目で、はっきり別のボックスにする） */
.thumbtool{margin:18px 0 0;padding:14px;border:1px solid var(--line);border-radius:12px;
 background:var(--bg)}
.trow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}
.trow b{font-size:.82rem;color:var(--fg);width:100%}
.hintsm{font-size:.76rem;color:var(--sub)}
/* 画像ボックス専用の埋め込み動画プレーヤー（上の動画ボックスとは別・共有しない） */
.gvwrap{max-width:100%;margin:4px 0}
.gvwrap video{width:100%;max-height:50vh;background:#000;display:block}
/* 候補画像：ボックス内で横スクロール（折り返さない） */
.candrow{display:flex;gap:10px;margin:6px 0 4px;overflow-x:auto;padding-bottom:8px;
 scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch}
.candrow::-webkit-scrollbar{height:8px}
.candrow::-webkit-scrollbar-thumb{background:var(--line);border-radius:999px}
.cand{flex:0 0 auto;width:150px;border:2px solid var(--line);border-radius:8px;
 overflow:hidden;cursor:pointer;scroll-snap-align:start;background:var(--card)}
.cand:hover{border-color:var(--accent)}
.cand.active{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent) inset}
.cand img{width:100%;display:block;aspect-ratio:16/9;object-fit:cover}
/* 大きいプレビュー＋ドラッグ選択（ここで直接トリミングできる）
   ★横幅はボックスいっぱいに広げる（width:100%）。.vwrap と img を同じ幅にしておかないと
   ドラッグ選択の座標計算（getBoundingClientRect基準）がズレるので、両方に同じ width:100% を指定する。 */
.bigwrap{margin:10px 0}
.bigwrap .vwrap{width:100%}
.bigwrap img{display:block;width:100%;height:auto;background:#000}
button.go.primary{font-weight:700}
.thumbgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
.clip.thumb{padding:10px}
.clip.thumb img{width:100%;height:auto;display:block;border-radius:8px;margin-bottom:8px}
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
  // textareaは編集中の中身が.valueにしか反映されない（.textContentは初期値のまま）ので分ける。
  if(el)copyText(el.tagName==='TEXTAREA'?el.value:el.textContent,b);
});

// メイン投稿の手動保存（自由に書き換えて💾保存）
document.addEventListener('click',async e=>{
  const b=e.target.closest('.save-main');if(!b)return;
  const dir=b.dataset.dir, ta=document.getElementById(b.dataset.target);
  const stat=document.getElementById('savestat-'+b.dataset.target);
  if(location.protocol==='file:'){alert('保存は serve.py 経由でのみ動きます。');return;}
  const old=b.textContent;b.textContent='保存中…';b.disabled=true;
  try{
    const r=await fetch('/__save_post',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir,main:ta.value})});
    const j=await r.json();
    if(!j.ok){alert('保存に失敗: '+(j.error||'不明なエラー'));}
    else{stat.textContent='✓ 保存しました（全体ボードにも反映）';setTimeout(()=>stat.textContent='',2500);}
  }catch(ex){alert('通信に失敗しました: '+ex);}
  b.textContent=old;b.disabled=false;
});

// アーカイブ操作（📦アーカイブ／🗑完全削除／↩全体ボードに戻す）。
// board.html・archive.html・board_<cid>.html のどのページから叩いても
// serve.py 側の共通Handlerが処理する。
document.addEventListener('click',async e=>{
  const b=e.target.closest('.archive-btn,.unarchive-btn,.delete-btn');
  if(!b)return;
  if(location.protocol==='file:'){
    alert('この操作は serve.py 経由でのみ動きます。');return;}
  const dir=b.dataset.dir;
  const card=b.closest('.card')||b.closest('article');
  let url,label;
  if(b.classList.contains('archive-btn')){url='/__archive';label='アーカイブ中…';}
  else if(b.classList.contains('unarchive-btn')){url='/__unarchive';label='戻し中…';}
  else{
    if(!confirm('完全に削除します。元に戻せません。よろしいですか？'))return;
    url='/__delete_work';label='削除中…';
  }
  const old=b.textContent;b.textContent=label;
  b.disabled=true;
  const sibling=b.parentElement?b.parentElement.querySelectorAll('button'):[];
  sibling.forEach(x=>x.disabled=true);
  try{
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir})});
    const j=await r.json();
    if(!j.ok){alert('失敗: '+(j.error||'不明なエラー'));b.textContent=old;
      sibling.forEach(x=>x.disabled=false);return;}
    if(card)card.remove();
  }catch(ex){alert('通信に失敗しました: '+ex);b.textContent=old;
    sibling.forEach(x=>x.disabled=false);}
});

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

// ── 範囲選択（ドラッグで四角を描く）─────────────────
// 選択結果は sellayer に px（動画の実ピクセル座標）で覚えさせる。
const SEL={};   // uid -> {x,y,w,h}（動画ピクセル）
document.addEventListener('click',e=>{
  const b=e.target.closest('.selbtn');if(!b)return;
  const uid=b.dataset.uid;
  const layer=document.getElementById('sel-'+uid);
  const on=layer.classList.toggle('on');
  b.classList.toggle('on',on);
  b.textContent=on?'▭ 選択中（もう一度で終了）':'▭ 範囲を選ぶ';
});
function bindSelect(layer){
  const uid=layer.id.slice(4);
  let box=null, sx=0, sy=0, drawing=false;
  const info=document.getElementById('si-'+uid);
  const applyBtn=layer.closest('.video').querySelector('button[data-act="croprect"]');
  const pt=ev=>{const r=layer.getBoundingClientRect();
    return {x:Math.max(0,Math.min(ev.clientX-r.left,r.width)),
            y:Math.max(0,Math.min(ev.clientY-r.top,r.height)),r};};
  layer.addEventListener('pointerdown',ev=>{
    ev.preventDefault();drawing=true;const p=pt(ev);sx=p.x;sy=p.y;
    if(box)box.remove();
    box=document.createElement('div');box.className='selbox';layer.appendChild(box);
    layer.setPointerCapture(ev.pointerId);
  });
  layer.addEventListener('pointermove',ev=>{
    if(!drawing||!box)return;const p=pt(ev);
    const x=Math.min(sx,p.x),y=Math.min(sy,p.y),w=Math.abs(p.x-sx),h=Math.abs(p.y-sy);
    box.style.left=x+'px';box.style.top=y+'px';box.style.width=w+'px';box.style.height=h+'px';
  });
  layer.addEventListener('pointerup',ev=>{
    if(!drawing)return;drawing=false;
    const vid=document.getElementById('vid-'+uid);
    const r=layer.getBoundingClientRect();
    const scaleX=(vid.videoWidth||r.width)/r.width, scaleY=(vid.videoHeight||r.height)/r.height;
    const bx=box.offsetLeft*scaleX, by=box.offsetTop*scaleY,
          bw=box.offsetWidth*scaleX, bh=box.offsetHeight*scaleY;
    if(bw<8||bh<8){info.textContent='もう少し大きく囲ってください';applyBtn.disabled=true;return;}
    SEL[uid]={x:Math.round(bx),y:Math.round(by),w:Math.round(bw),h:Math.round(bh)};
    info.textContent=`選択：${SEL[uid].w}×${SEL[uid].h}px`;
    applyBtn.disabled=false;
  });
}
document.querySelectorAll('.sellayer:not(.imgsel)').forEach(bindSelect);

// 実行ボタン：時間切り(cut) / 比率crop / 手動範囲croprect をサーバーに投げる。
document.addEventListener('click',async e=>{
  const b=e.target.closest('button.go');if(!b)return;
  const act=b.dataset.act;                    // 'cut' / 'crop' / 'croprect'
  const box=b.closest('.cuttool,.croptool');
  const uid=box.dataset.uid, dir=box.dataset.dir, movie=box.dataset.movie;
  const err=box.closest('.video').querySelector('.err');
  err.textContent='';
  if(location.protocol==='file:'){
    err.textContent='この機能は serve.py 経由でのみ動きます（今は file:// で開いています）。';return;}

  // 区間の秒（時間で切る欄と共有）
  const s=document.getElementById(box.dataset.start).value.trim();
  const en=document.getElementById(box.dataset.end).value.trim();
  const useRange=()=>{const c=document.getElementById('cr-'+uid);return c&&c.checked;};
  const withRange=(p)=>{
    if(useRange()){
      if(s===''||en===''){err.textContent='「区間も使う」なら開始と終了の秒を入れてください。';return false;}
      if(parseFloat(en)<=parseFloat(s)){err.textContent='終了は開始より後にしてください。';return false;}
      p.start=s;p.end=en;}
    return true;};

  let url, payload, label;
  if(act==='cut'){
    if(s===''||en===''){err.textContent='開始と終了の秒を入れてください。';return;}
    if(parseFloat(en)<=parseFloat(s)){err.textContent='終了は開始より後にしてください。';return;}
    url='/__cut'; payload={dir,video:movie,start:s,end:en}; label='✂ '+s+'〜'+en;
  }else if(act==='croprect'){
    const sel=SEL[uid];
    if(!sel){err.textContent='先に「範囲を選ぶ」で動画上をドラッグしてください。';return;}
    payload={dir,video:movie,rect:`${sel.x},${sel.y},${sel.w},${sel.h}`};
    if(!withRange(payload))return;
    url='/__crop'; label='🔲 選択'+sel.w+'×'+sel.h+(useRange()?(' '+s+'〜'+en):'');
  }else{
    const aspect=document.getElementById('ca-'+uid).value;
    const pos=document.getElementById('cp-'+uid).value;
    payload={dir,video:movie,aspect,pos};
    if(!withRange(payload))return;
    url='/__crop'; label='🔲 '+aspect+' '+pos+(useRange()?(' '+s+'〜'+en):'');
  }

  const old=b.textContent;b.textContent='処理中…';b.disabled=true;
  try{
    const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)});
    const j=await r.json();
    if(!j.ok){err.textContent='失敗: '+(j.error||'不明なエラー');}
    else{addClip(uid,dir,j.file,label);}
  }catch(ex){err.textContent='通信に失敗しました: '+ex;}
  b.textContent=old;b.disabled=false;
});

function addClip(uid,dir,file,label){
  const wrap=document.getElementById('clips-'+uid);
  const src=dir.split('/').map(encodeURIComponent).join('/')+'/'+encodeURIComponent(file);
  const el=document.createElement('div');el.className='clip';el.dataset.file=file;
  el.innerHTML=`<div class="clip-h"><span>${label}　${file}</span>
    <span class="clip-act"><a class="dl" href="${src}" download="${file}">⬇ 保存</a>
    <button class="del" data-file="${file}" data-dir="${dir}">🗑 削除</button></span></div>
    <video controls src="${src}"></video>`;
  wrap.prepend(el);
}

// 作った素材の削除（元動画/元画像は消せない＝サーバー側で cut_/crop_/clip_/thumb_ のみ許可）
document.addEventListener('click',async e=>{
  const b=e.target.closest('button.del');if(!b)return;
  const file=b.dataset.file, dir=b.dataset.dir;
  const clip=b.closest('.clip');
  const scope=b.closest('.video')||b.closest('.thumbtool');
  const err=scope.querySelector('.err');
  err.textContent='';
  if(location.protocol==='file:'){
    err.textContent='削除は serve.py 経由でのみ動きます（今は file:// で開いています）。';return;}
  if(!confirm(`「${file}」を削除します。元に戻せません。よろしいですか？`))return;
  const old=b.textContent;b.textContent='削除中…';b.disabled=true;
  try{
    const r=await fetch('/__del',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir,file})});
    const j=await r.json();
    if(!j.ok){err.textContent='削除に失敗: '+(j.error||'不明なエラー');b.textContent=old;b.disabled=false;}
    else{clip.remove();}
  }catch(ex){err.textContent='通信に失敗しました: '+ex;b.textContent=old;b.disabled=false;}
});

// ── サムネ画像作成：動画切り抜き→候補一覧→大きいプレビューでドラッグ選択→OKで確定 ──
function mediaUrl(dir,file){
  return dir.split('/').map(encodeURIComponent).join('/')+'/'+encodeURIComponent(file);
}

// 確定したサムネ（thumb_*.jpg）を一覧に追加する
function addThumb(uid,dir,file){
  const wrap=document.getElementById('thumbs-'+uid)
    || (()=>{const box=document.createElement('div');box.className='clips thumbgrid';
      box.id='thumbs-'+uid;
      const tt=document.getElementById('cand-'+uid).closest('.thumbtool');
      const empty=document.getElementById('thumbs-'+uid+'-empty');if(empty)empty.remove();
      tt.appendChild(box);return box;})();
  const src=mediaUrl(dir,file);
  const el=document.createElement('div');el.className='clip thumb';el.dataset.file=file;
  el.innerHTML=`<img src="${src}">
    <div class="clip-h"><span>🖼 ${file}</span>
    <span class="clip-act"><a class="dl" href="${src}" download="${file}">⬇ 保存</a>
    <button class="del" data-file="${file}" data-dir="${dir}">🗑 削除</button></span></div>`;
  wrap.prepend(el);
}

// 候補（採用画像／切り抜いた静止画）を一覧に追加する
function addCandidate(uid,dir,file){
  const row=document.getElementById('cand-'+uid);
  const notice=row.querySelector('.notice');if(notice)notice.remove();
  const src=mediaUrl(dir,file);
  const el=document.createElement('div');el.className='cand';el.dataset.file=file;
  el.innerHTML=`<img src="${src}" draggable="false">`;
  row.appendChild(el);
  el.click();   // 切り抜いたその場で大きいプレビューにも出す
}

// 動画の今の再生位置を静止画として切り抜き、候補に追加する（確定はまだしない）
document.addEventListener('click',async e=>{
  const b=e.target.closest('button.grabbtn');if(!b)return;
  const uid=b.dataset.uid,dir=b.dataset.dir,movie=b.dataset.movie;
  const vid=document.getElementById(b.dataset.vid);
  const err=b.closest('.thumbtool').querySelector('.err');
  err.textContent='';
  if(location.protocol==='file:'){err.textContent='この機能は serve.py 経由でのみ動きます。';return;}
  const sec=(Math.round((vid.currentTime||0)*10)/10);
  const old=b.textContent;b.textContent='切り抜き中…';b.disabled=true;
  try{
    const r=await fetch('/__grab',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir,video:movie,sec})});
    const j=await r.json();
    if(!j.ok){err.textContent='失敗: '+(j.error||'不明なエラー');}
    else{addCandidate(uid,dir,j.file);}
  }catch(ex){err.textContent='通信に失敗しました: '+ex;}
  b.textContent=old;b.disabled=false;
});

// 候補クリック → 大きいプレビューに表示し、ドラッグ選択を有効化する
const BIGSEL={};
document.addEventListener('click',e=>{
  const cand=e.target.closest('.cand');if(!cand)return;
  const row=cand.closest('.candrow');
  const uid=row.id.slice(5);   // "cand-" の5文字を除く
  const dir=row.dataset.dir;
  row.querySelectorAll('.cand').forEach(c=>c.classList.remove('active'));
  cand.classList.add('active');
  const file=cand.dataset.file;
  const wrap=document.getElementById('bigwrap-'+uid);
  const img=document.getElementById('bigimg-'+uid);
  const layer=document.getElementById('bigsel-'+uid);
  img.src=mediaUrl(dir,file);
  wrap.dataset.file=file;
  wrap.style.display='';
  layer.classList.add('on');   // ★これが無いと透明な操作面が display:none のままでドラッグが効かない
  document.getElementById('bigsi-'+uid).textContent='ドラッグで範囲を選べます（選ばなければ全体を使用）';
  delete BIGSEL[uid];
  wrap.scrollIntoView({behavior:'smooth',block:'nearest'});
});
function bindBigSelect(layer){
  const uid=layer.id.slice(7);   // "bigsel-" の7文字を除く
  let box=null, sx=0, sy=0, drawing=false;
  const info=document.getElementById('bigsi-'+uid);
  const pt=ev=>{const r=layer.getBoundingClientRect();
    return {x:Math.max(0,Math.min(ev.clientX-r.left,r.width)),
            y:Math.max(0,Math.min(ev.clientY-r.top,r.height)),r};};
  layer.addEventListener('pointerdown',ev=>{
    ev.preventDefault();drawing=true;const p=pt(ev);sx=p.x;sy=p.y;
    if(box)box.remove();
    box=document.createElement('div');box.className='selbox';layer.appendChild(box);
    layer.setPointerCapture(ev.pointerId);
  });
  layer.addEventListener('pointermove',ev=>{
    if(!drawing||!box)return;const p=pt(ev);
    const x=Math.min(sx,p.x),y=Math.min(sy,p.y),w=Math.abs(p.x-sx),h=Math.abs(p.y-sy);
    box.style.left=x+'px';box.style.top=y+'px';box.style.width=w+'px';box.style.height=h+'px';
  });
  layer.addEventListener('pointerup',ev=>{
    if(!drawing)return;drawing=false;
    const img=document.getElementById('bigimg-'+uid);
    const r=layer.getBoundingClientRect();
    const scaleX=(img.naturalWidth||r.width)/r.width, scaleY=(img.naturalHeight||r.height)/r.height;
    const bx=box.offsetLeft*scaleX, by=box.offsetTop*scaleY,
          bw=box.offsetWidth*scaleX, bh=box.offsetHeight*scaleY;
    if(bw<8||bh<8){info.textContent='もう少し大きく囲ってください（選択なしでOKなら画像全体を使います）';
      delete BIGSEL[uid];box.remove();box=null;return;}
    BIGSEL[uid]={x:Math.round(bx),y:Math.round(by),w:Math.round(bw),h:Math.round(bh)};
    info.textContent=`選択：${BIGSEL[uid].w}×${BIGSEL[uid].h}px（このままOKを押すとこの範囲を切り出します）`;
  });
}
document.querySelectorAll('.sellayer.imgsel').forEach(bindBigSelect);

// 確定：選択があればその範囲でトリミング、無ければ画像全体をそのまま採用（どちらも劣化なし）
document.addEventListener('click',async e=>{
  const b=e.target.closest('button[data-act="confirmthumb"]');if(!b)return;
  const uid=b.dataset.uid,dir=b.dataset.dir;
  const wrap=document.getElementById('bigwrap-'+uid);
  const file=wrap.dataset.file;
  const sel=BIGSEL[uid];
  const err=b.closest('.thumbtool').querySelector('.err');
  err.textContent='';
  if(!file){err.textContent='先に候補から画像を選んでください。';return;}
  if(location.protocol==='file:'){err.textContent='この機能は serve.py 経由でのみ動きます。';return;}
  const old=b.textContent;b.textContent='確定中…';b.disabled=true;
  try{
    let r;
    if(sel){
      r=await fetch('/__crop_image',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({dir,image:file,rect:`${sel.x},${sel.y},${sel.w},${sel.h}`})});
    }else{
      r=await fetch('/__select_thumb',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({dir,file})});
    }
    const j=await r.json();
    if(!j.ok){err.textContent='失敗: '+(j.error||'不明なエラー');}
    else{addThumb(uid,dir,j.file);}
  }catch(ex){err.textContent='通信に失敗しました: '+ex;}
  b.textContent=old;b.disabled=false;
});
"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def rel_dir(work_dir) -> str:
    """works/ からの相対パス（例：<cid>_名前 または 進行中/<cid>_名前）。
    サブフォルダに移動した作品でも正しく参照できるように、"/"区切りで返す。"""
    return work_dir.relative_to(C.WORKS_DIR).as_posix()


def rel_media(dir_name: str, file_name: str) -> str:
    """board_<cid>.html（works/直下）から見た動画への相対パス。
    日本語フォルダ名・サブフォルダでも壊れないよう各セグメントをURLエンコードする。"""
    return "/".join(urllib.parse.quote(seg) for seg in dir_name.split("/") + [file_name])


def render_thumbtool(e: dict, uid: str, dir_name: str) -> str:
    """サムネ画像（1枚・高品質）を作るセクション。

    流れ：①動画から静止画を切り抜く（任意・候補に追加される）
          →②候補（採用画像＋切り抜いた静止画）を横スクロールで一覧表示
          →③候補をクリックすると大きくプレビュー、その場でドラッグ選択（任意）
          →④「✅ この画像でOK」で確定＝選択があればその範囲でトリミング、
             無ければ画像全体をそのまま採用（どちらも再圧縮なしでコピーするので劣化しない）。
    動画が無い作品でも②③④（採用画像からの確定・トリミング）は使えるようにする。
    """
    grab_row = ""
    if e["has_movie"]:
        gsrc = rel_media(dir_name, e["movie"])
        # ★このボックス専用の動画プレーヤーを埋め込む（上の「動画を編集する」ボックスとは別・共有しない）。
        grab_row = f"""      <div class="trow"><b>動画から切り抜く（任意・候補に追加されます）：</b></div>
      <div class="vwrap gvwrap">
        <video controls id="gvid-{uid}" src="{gsrc}" preload="metadata"></video>
      </div>
      <div class="trow">
        <button class="grabbtn" data-vid="gvid-{uid}" data-dir="{esc(dir_name)}"
                data-movie="{esc(e['movie'])}" data-uid="{uid}">📸 今の場面を候補に追加</button>
        <span class="hintsm">動画を再生・一時停止して、いい瞬間で押す</span>
      </div>"""

    cands = ""
    for f in list(e["images"]) + list(e["grabs"]):
        isrc = rel_media(dir_name, f)
        cands += (f'<div class="cand" data-file="{esc(f)}">'
                  f'<img src="{isrc}" loading="lazy" draggable="false"></div>')
    cand_row = (f'<div class="candrow" id="cand-{uid}" data-dir="{esc(dir_name)}">'
                f'{cands}</div>' if cands else
                f'<div class="candrow" id="cand-{uid}" data-dir="{esc(dir_name)}">'
                '<p class="notice">候補画像がありません。</p></div>')

    thumbs_html = ""
    for f in e["thumbs"]:
        tsrc = rel_media(dir_name, f)
        thumbs_html += (
            f'<div class="clip thumb" data-file="{esc(f)}">'
            f'<img src="{tsrc}" loading="lazy">'
            f'<div class="clip-h"><span>🖼 {esc(f)}</span>'
            f'<span class="clip-act">'
            f'<a class="dl" href="{tsrc}" download="{esc(f)}">⬇ 保存</a>'
            f'<button class="del" data-file="{esc(f)}" '
            f'data-dir="{esc(dir_name)}">🗑 削除</button></span></div></div>')
    thumbs_block = (f'<div class="clips thumbgrid" id="thumbs-{uid}">{thumbs_html}</div>'
                    if thumbs_html else
                    f'<p class="notice" id="thumbs-{uid}-empty">まだサムネがありません。'
                    '下の候補をクリックして選んでください。</p>')

    return f"""    <div class="thumbtool">
      <h3>🖼 サムネ画像を作る（1枚・高品質推奨）</h3>
{grab_row}
      <div class="trow"><b>候補（クリックで大きく表示）：</b></div>
      {cand_row}

      <div class="bigwrap" id="bigwrap-{uid}" style="display:none">
        <div class="vwrap">
          <img id="bigimg-{uid}" draggable="false">
          <div class="sellayer imgsel" id="bigsel-{uid}"></div>
        </div>
        <div class="trow">
          <span class="selinfo" id="bigsi-{uid}">ドラッグで範囲を選べます（選ばなければ全体を使用）</span>
          <button class="go primary" data-act="confirmthumb" data-uid="{uid}"
                  data-dir="{esc(dir_name)}">✅ この画像でOK</button>
        </div>
      </div>

      <p class="err"></p>
      <p class="hint">候補をクリック→大きい画像の上をドラッグすると範囲を選べます。
         「✅ この画像でOK」で確定（選択が無ければ画像全体をそのまま採用）。
         画質は落とさず、選んだ範囲をそのまま高品質で切り出します。作ったサムネは下に出るので、⬇保存でダウンロード。
         採用画像がぼやけて見える場合は、動画から新しく切り抜くときれいに撮れます。</p>
      {thumbs_block}
    </div>"""


def render_video(e: dict, uid: str) -> str:
    """単一作品モードの動画ブロック（再生＋切り抜き＋保存）。
    動画が無い作品でも、サムネ作成（採用画像の選定・トリミング）は使えるようにする。"""
    dir_name = rel_dir(e["dir"])
    if not e["has_movie"]:
        return ('      <p class="notice">この作品にはサンプル動画がありません'
                '（画像のみ）。</p>\n'
                f'{render_thumbtool(e, uid, dir_name)}')
    src = rel_media(dir_name, e["movie"])

    clips = ""
    for f in e["clips"]:
        csrc = rel_media(dir_name, f)
        icon = "🔲" if f.startswith("crop_") else "✂"
        clips += (f'<div class="clip" data-file="{esc(f)}">'
                  f'<div class="clip-h"><span>{icon} {esc(f)}</span>'
                  f'<span class="clip-act">'
                  f'<a class="dl" href="{csrc}" download="{esc(f)}">⬇ 保存</a>'
                  f'<button class="del" data-file="{esc(f)}" '
                  f'data-dir="{esc(dir_name)}">🗑 削除</button></span></div>'
                  f'<video controls src="{csrc}"></video></div>')

    return f"""      <div class="video">
        <h3>🎬 動画を編集する</h3>
        <div class="vwrap" id="vwrap-{uid}">
          <video controls id="vid-{uid}" src="{src}" preload="metadata"></video>
          <div class="sellayer" id="sel-{uid}"></div>
        </div>

        <div class="cuttool" data-vid="vid-{uid}" data-dir="{esc(dir_name)}"
             data-movie="{esc(e['movie'])}" data-uid="{uid}"
             data-start="cs-{uid}" data-end="ce-{uid}">
          <span class="tool-label">⏱ 時間で切る</span>
          <label>開始<input id="cs-{uid}" inputmode="decimal" placeholder="秒"></label>
          <button class="now" data-for="cs-{uid}">現在</button>
          <label>終了<input id="ce-{uid}" inputmode="decimal" placeholder="秒"></label>
          <button class="now" data-for="ce-{uid}">現在</button>
          <button class="go" data-act="cut">✂ 切り抜く</button>
          <a class="dl" href="{src}" download="{esc(e['cid'])}.mp4">⬇ 元動画を保存</a>
        </div>

        <div class="croptool" data-dir="{esc(dir_name)}" data-movie="{esc(e['movie'])}"
             data-uid="{uid}" data-vid="vid-{uid}" data-layer="sel-{uid}"
             data-start="cs-{uid}" data-end="ce-{uid}">
          <span class="tool-label">🔲 画面を切る（X向けの形に）</span>
          <label class="chk"><input type="checkbox" id="cr-{uid}" checked>上の区間も使う</label>

          <div class="crow">
            <b>A. 範囲を自分で選ぶ：</b>
            <button class="selbtn" data-uid="{uid}">▭ 範囲を選ぶ</button>
            <span class="selinfo" id="si-{uid}">動画の上をドラッグして四角を作る</span>
            <button class="go" data-act="croprect" disabled>この範囲で切る</button>
          </div>

          <div class="crow">
            <b>B. 比率で自動：</b>
            <label>比率
              <select id="ca-{uid}">
                <option value="1:1">正方形 1:1</option>
                <option value="9:16">縦長 9:16</option>
                <option value="4:5">縦 4:5</option>
                <option value="16:9">横 16:9</option>
              </select>
            </label>
            <label>位置
              <select id="cp-{uid}">
                <option value="center">中央</option>
                <option value="left">左</option>
                <option value="right">右</option>
                <option value="top">上</option>
                <option value="bottom">下</option>
              </select>
            </label>
            <button class="go" data-act="crop">比率で切る</button>
          </div>
        </div>

        <p class="err"></p>
        <p class="hint">「現在」で今の再生位置（秒）が入ります。
           <b>時間で切る</b>＝長さを短く、<b>画面を切る</b>＝縦長/正方形など形を変える。
           画面を切るときは <b>A</b> で好きな範囲をドラッグ選択するか、<b>B</b> の比率プリセットが使えます。
           作った動画は下に出るので、⬇保存 → Finder から X にドラッグ。</p>
        <div class="clips" id="clips-{uid}">{clips}</div>
      </div>
{render_thumbtool(e, uid, dir_name)}"""


def render_card(e: dict, post: dict, single: bool = False) -> str:
    cid = e["cid"]
    uid = cid.replace(".", "_")
    dir_name = rel_dir(e["dir"])

    notice = ""
    if not e["has_meta"]:
        notice += ('<p class="notice">作品情報が取れていません。'
                   'myfans_fetch.py で取り込み直してください。</p>')

    def block(label, text, elid, extra_cls=""):
        return f"""      <div class="blk">
        <div class="blk-h"><span>{label}</span>
          <button data-copy="{elid}">コピー</button></div>
        <pre class="{extra_cls}" id="{elid}">{esc(text)}</pre>
      </div>"""

    def main_block(text, elid, dir_name):
        """メイン投稿は自由編集できるようにする（コピー・手動保存）。
        書き直したいときはボード上ではなく、Claude Codeのチャットで直接指示する
        （「〇〇のキャプション作って」等）→ そちらで /__save_post を呼んで保存する。"""
        return f"""      <div class="blk">
        <div class="blk-h"><span>メイン投稿（リンク投稿を引用して出す・リンクは貼らない）</span>
          <button data-copy="{elid}">コピー</button></div>
        <textarea class="mainedit" id="{elid}">{esc(text)}</textarea>
        <div class="mainrow">
          <button class="save-main" data-dir="{esc(dir_name)}" data-target="{elid}">💾 保存</button>
          <span class="save-status" id="savestat-{elid}"></span>
        </div>
        <p class="hintsm">文章を作り直したいときは、ここではなく<b>Claude Codeのチャットで直接指示</b>してください
          （例：「この投稿のキャプション作り直して」）。</p>
      </div>"""

    # 検索は作品名・投稿ID・投稿者名で引けるようにしておく（表示はしない）
    search = f"{e['title']} {cid} {e['creator']}".lower()
    creator_html = (f'<span class="cid">{esc(e["creator"])}さん</span>'
                    if e["creator"] else "")

    description = (e["item"].get("description") or "").strip()
    description_block = (
        block("投稿ページの本文（MyFansから自動取得・参考用）", description,
              f"desc-{uid}")
        if single and description else "")

    parts = [
        f'    <article class="card" data-cid="{esc(cid)}" '
        f'data-search="{esc(search)}">',
        f'      <h2>{esc(e["title"])}{creator_html}</h2>',
        notice,
        render_video(e, uid) if single else "",
        description_block,
        block("リンク投稿（アフィリンクを持たせる側）", post.get("sub", ""),
              f"sub-{uid}"),
        main_block(post.get("main", ""), f"main-{uid}", dir_name) if single else
        block("メイン投稿（リンク投稿を引用して出す・リンクは貼らない）",
              post.get("main", ""), f"main-{uid}"),
    ]

    page = (f'<a href="{esc(e["page_url"])}" target="_blank" '
            f'rel="noopener">MyFansの投稿ページ →</a>') if e["page_url"] else ""
    archived = bool(e["item"].get("archived"))
    archive_html = C.archive_block_html(dir_name, archived)
    parts += [
        '      <div class="foot">',
        f'        <span>{page}</span>',
        f'        {archive_html}',
        "      </div>",
        "    </article>",
    ]
    return "\n".join(p for p in parts if p)


def render_single(e: dict, post: dict) -> str:
    """単一作品ボード（動画つき）のHTML全体。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    card = render_card(e, post, single=True)
    back_html = '<a href="board.html">← 全体ボードへ</a> ／ '

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(e['title'])}｜MyFans 投稿ボード</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{esc(e['title'])} <span class="cid">{esc(e['cid'])}</span></h1>
  <p class="lead">この作品ぶんの投稿ボード。動画は再生・切り抜き・保存ができます。</p>
  <p class="lead">{back_html}更新 {now}</p>
</header>
{card}
</div>
<script>{JS}</script>
</body>
</html>
"""


def build_single(cid: str, regen: bool):
    """投稿ID 1件ぶんのボードを生成してパスを返す。見つからなければ None。"""
    entries = collect()
    match = next((e for e in entries if e["cid"] == cid), None)
    if match is None:
        avail = ", ".join(sorted(e["cid"] for e in entries))
        print(f"✗ 投稿ID={cid} の作品が works/ に見つかりません。")
        print(f"  使える投稿ID: {avail}")
        return None
    posts = ensure_posts([match], regen=regen)
    out = single_board_path(cid)
    out.write_text(render_single(match, posts.get(cid, {})), encoding="utf-8")
    print(f"✓ 単一作品ボードを作りました: {out}")
    if not match["has_movie"]:
        print("  ※ この作品にはまだ動画がありません（拡張機能でDL→ルートフォルダに置いて"
              "「🎬 動画を取り込む」で反映してください）。")
    return out


def rebuild_all(regen: bool = False) -> int:
    """works/ 配下の全作品ぶんの個別ボードを作り直す。
    テンプレート（このファイルのHTML/CSS/JS）を変更したときに、
    「一部の作品だけ再生成し忘れる」を防ぐための一括コマンド。
    dashboard.py が入っていれば、全体ボード／アーカイブ一覧も合わせて作り直す。"""
    entries = collect()
    if not entries:
        print("works/ に作品フォルダがありません。")
        return 1
    for e in entries:
        build_single(e["cid"], regen)
    print(f"\n✓ 個別ボード {len(entries)} 件を再生成しました。")

    try:
        import dashboard as DB
        DB.build_all()
        print("✓ 全体ボード／アーカイブ一覧も再生成しました。")
    except Exception:
        pass
    return 0


def main(argv) -> int:
    flags = set(a for a in argv[1:] if a.startswith("--"))
    positional = [a for a in argv[1:] if not a.startswith("--")]
    regen = "--regen" in flags

    # --all：全作品の個別ボード（＋全体ボード／アーカイブ一覧）を一括で作り直す。
    if "--all" in flags:
        return rebuild_all(regen)

    # 投稿IDを指定して、その1作品だけのボード（動画つき）を作る。
    # 全作品一覧は dashboard.py（works/board.html・works/archive.html）が担う。
    if not positional:
        print("使い方: python3 myfans_auto/scripts/board.py <投稿ID> [--open] [--regen]")
        print("       python3 myfans_auto/scripts/board.py --all [--regen]   # 全作品を一括再生成")
        return 1

    cid = positional[0]
    out = build_single(cid, regen)
    if out is None:
        return 1
    print("  切り抜きを使うには: "
          f"python3 myfans_auto/scripts/serve.py {cid}")
    if "--open" in flags:
        subprocess.run(["open", str(out)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
