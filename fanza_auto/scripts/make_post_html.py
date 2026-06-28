#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1日分の投稿フォルダ（output/<日付>/<各投稿>/投稿内容.md ＋ 画像・動画）を
「見やすく・コピーしやすい」1枚の index.html にまとめる。

使い方:
    python3 make_post_html.py [<日付フォルダ>]

    例) python3 make_post_html.py fanza_auto/output/2026-06-21
    省略すると output 配下の最新日付フォルダを使う。

出力:
    <日付フォルダ>/index.html
    （画像・動画は相対パス参照。ブラウザで開けばそのまま表示・コピーできる）
"""
import os
import re
import sys
import glob
import html
import json


IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VID_EXTS = (".mp4", ".mov", ".webm", ".m4v")


def natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def render_md(md, base):
    """投稿内容.md を、コードブロックにコピーボタンを付けつつHTML化する。
    base は code block の連番付与に使う一意プレフィックス。"""
    lines = md.splitlines()
    out = []
    i = 0
    code_idx = 0
    while i < len(lines):
        line = lines[i]

        # フェンスドコードブロック（```）→ コピー可能なボックス
        if line.strip().startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # 終端 ``` を飛ばす
            code_idx += 1
            cid = f"{base}-code-{code_idx}"
            text = "\n".join(buf)
            out.append(
                f'<div class="copybox">'
                f'<button class="copybtn" data-target="{cid}">コピー</button>'
                f'<pre id="{cid}" class="copytext">{html.escape(text)}</pre>'
                f'</div>'
            )
            continue

        s = line.strip()
        if not s:
            i += 1
            continue

        # 見出し
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            level = len(m.group(1))
            lv = min(level + 1, 6)  # ページ全体のh1を避けて1段下げる
            out.append(f"<h{lv}>{inline(m.group(2))}</h{lv}>")
            i += 1
            continue

        # 区切り線
        if re.match(r"^-{3,}$", s):
            out.append("<hr>")
            i += 1
            continue

        # 引用
        if s.startswith(">"):
            out.append(f'<blockquote>{inline(s.lstrip("> ").strip())}</blockquote>')
            i += 1
            continue

        # リスト（- / 数字.）— 連続行をまとめる
        if re.match(r"^([-*]|\d+\.)\s+", s):
            items = []
            ordered = bool(re.match(r"^\d+\.\s+", s))
            while i < len(lines) and re.match(r"^([-*]|\d+\.)\s+", lines[i].strip()):
                item = re.sub(r"^([-*]|\d+\.)\s+", "", lines[i].strip())
                # 「賑やかし」候補のような短い定型文はワンクリックコピー対応
                items.append(f'<li><span class="liline">{inline(item)}</span>'
                             f'<button class="minicopy" data-text="{html.escape(item)}">コピー</button></li>')
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        # 通常段落
        out.append(f"<p>{inline(s)}</p>")
        i += 1

    return "\n".join(out)


def inline(text):
    """インライン記法を最小限HTML化（**bold**, `code`, リンク化）。"""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    text = re.sub(r"(https?://[^\s<>「」【】]+)", r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)
    return text


def img_figure(rel, im):
    """画像1枚ぶんの figure（A/B判定ボタン＋理由＋再選出つき）。
    rel=作品フォルダ名, im=画像ファイル名。"""
    src = html.escape(f"{rel}/{im}")
    return (
        f'<figure class="media img" data-image="{html.escape(im)}">'
        f'<img src="{src}" loading="lazy" data-full="{src}" alt="{html.escape(im)}">'
        f'<figcaption>{html.escape(im)}'
        f' <a class="dl" href="{src}" download>保存</a></figcaption>'
        f'<div class="ab">'
        f'<button class="abtn" data-v="ok">OK</button>'
        f'<button class="abtn" data-v="mid">微妙</button>'
        f'<button class="abtn" data-v="ng">NG</button>'
        f'<button class="rebtn" title="この画像の代わりをサンプル動画から選び直す">🔄再選出</button>'
        f'</div>'
        f'<input class="abreason" type="text" placeholder="理由（任意・ナレッジに記録）">'
        f'</figure>'
    )


def build_card(post_dir, idx):
    name = os.path.basename(post_dir)
    md_path = os.path.join(post_dir, "投稿内容.md")
    md = ""
    if os.path.isfile(md_path):
        with open(md_path, encoding="utf-8") as f:
            md = f.read()

    # 表示名（h1の値があればそれ、なければフォルダ名）
    title = name
    mt = re.search(r"^#\s+(.+)$", md, re.M)
    if mt:
        title = mt.group(1).strip()

    rel = os.path.basename(post_dir)
    files = sorted(os.listdir(post_dir), key=natural_key)
    videos = [f for f in files if f.lower().endswith(VID_EXTS)]
    images = [f for f in files if f.lower().endswith(IMG_EXTS)]

    # 種類で振り分け：
    #   サンプル動画＝元動画（cut_ で始まらない動画）／ 切り抜き動画＝cut_*.mp4
    #   切り抜き画像＝clip_*.jpg（ユーザーが画像切り抜きで作成）／ システム抽出画像＝それ以外
    sample_vids = [v for v in videos if not v.lower().startswith("cut_")]
    cut_vids = [v for v in videos if v.lower().startswith("cut_")]
    clip_imgs = [im for im in images if im.lower().startswith("clip_")]
    sys_imgs = [im for im in images if not im.lower().startswith("clip_")]

    gallery = build_gallery(rel, sample_vids, cut_vids, clip_imgs, sys_imgs)

    body = render_md(md, f"p{idx}")

    return f'''
<section class="card" id="post-{idx}" data-key="{html.escape(rel)}" data-status="pending">
  <div class="cardhead">
    <h2>{html.escape(title)}</h2>
    <span class="folder">{html.escape(rel)}</span>
    <div class="status">
      <button class="stbtn" data-val="pending">投稿前</button>
      <button class="stbtn" data-val="posted">投稿済</button>
      <button class="stbtn" data-val="blocked">不可</button>
    </div>
  </div>
  <div class="grid">
    <div class="text">{body}</div>
    {gallery}
  </div>
</section>'''


def vid_figure(rel, v, is_cut=False):
    """動画1本ぶんの figure。is_cut=True は切り抜き済み（枠強調）。"""
    src = html.escape(f"{rel}/{v}")
    cls = "media vid cut" if is_cut else "media vid"
    return (
        f'<figure class="{cls}">'
        f'<video src="{src}" controls preload="metadata"></video>'
        f'<figcaption>{html.escape(v)}'
        f' <a class="dl" href="{src}" download>保存</a></figcaption>'
        f'</figure>'
    )


def sample_figure(rel, v):
    """サンプル動画（大）＋ 切り抜きツールバー（動画カット／画像切り抜き）。"""
    src = html.escape(f"{rel}/{v}")
    ev = html.escape(v)
    return (
        f'<figure class="media sample" data-video="{ev}">'
        f'<video src="{src}" controls preload="metadata"></video>'
        f'<figcaption>{ev} <span class="samplenote">元動画</span>'
        f' <a class="dl" href="{src}" download>保存</a></figcaption>'
        f'<div class="clipbar" data-video="{ev}">'
        f'<div class="cliprow">'
        f'<span class="cliplbl">🎬 動画</span>'
        f'<input class="cs" type="text" placeholder="開始 0:05">'
        f'<button class="setcur" data-t="cs" title="動画の現在位置を入れる">現在</button>'
        f'<span class="tilde">〜</span>'
        f'<input class="ce" type="text" placeholder="終了 0:12">'
        f'<button class="setcur" data-t="ce" title="動画の現在位置を入れる">現在</button>'
        f'<button class="cutbtn">✂ 動画切り抜き</button>'
        f'</div>'
        f'<div class="cliprow">'
        f'<span class="cliplbl">📷 画像</span>'
        f'<input class="gs" type="text" placeholder="秒 0:08">'
        f'<button class="setcur" data-t="gs" title="動画の現在位置を入れる">現在</button>'
        f'<button class="grabbtn">📷 画像切り抜き</button>'
        f'<span class="grabhint">＝再生中の場面を1枚画像にする</span>'
        f'</div>'
        f'<span class="cutmsg"></span>'
        f'</div>'
        f'</figure>'
    )


def build_gallery(rel, sample_vids, cut_vids, clip_imgs, sys_imgs):
    """メディア列を「サンプル動画 → 切り抜いた素材 → システム抽出画像」の縦並びで組む。"""
    samplecol = "".join(sample_figure(rel, v) for v in sample_vids)
    clips = ("".join(vid_figure(rel, v, is_cut=True) for v in cut_vids)
             + "".join(img_figure(rel, im) for im in clip_imgs))
    sysimgs = "".join(img_figure(rel, im) for im in sys_imgs)

    parts = []
    if samplecol:
        parts.append(f'<div class="samplecol">{samplecol}</div>')
    # 切り抜いた素材（空でも append 先として常に置く）
    clips_inner = clips or '<p class="emptynote">まだありません。上の動画から切り抜くとここに並びます。</p>'
    parts.append(
        '<div class="clipsec">'
        '<div class="sech">✂ 切り抜いた素材（あなたが作成）</div>'
        f'<div class="mediagrid clips">{clips_inner}</div>'
        '</div>')
    if sysimgs:
        parts.append(
            '<div class="syssec">'
            '<div class="sech">🖼 システムが抽出した画像</div>'
            f'<div class="mediagrid sysgrid">{sysimgs}</div>'
            '</div>')
    inner = "".join(parts) if parts else '<p class="nomedia">素材なし</p>'
    return f'<div class="gallery">{inner}</div>'


CSS = """
:root{--bg:#0f1115;--card:#1a1d24;--ac:#ff5277;--tx:#e8e8ea;--mut:#9aa0aa;--box:#0b0c10;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:-apple-system,"Hiragino Sans","Yu Gothic UI",sans-serif;line-height:1.7}
header.top{position:sticky;top:0;z-index:20;background:rgba(15,17,21,.95);backdrop-filter:blur(8px);border-bottom:1px solid #2a2e38;padding:12px 20px}
header.top h1{margin:0 0 8px;font-size:18px}
.nav{display:flex;flex-wrap:wrap;gap:6px}
.nav a{font-size:12px;color:var(--mut);text-decoration:none;background:#22262f;padding:3px 9px;border-radius:999px;border:1px solid #2f343f}
.nav a:hover{color:#fff;border-color:var(--ac)}
.wrap{max-width:1100px;margin:0 auto;padding:18px}
.card{background:var(--card);border:1px solid #262a33;border-radius:14px;margin:18px 0;padding:18px;scroll-margin-top:80px}
.cardhead{display:flex;align-items:baseline;gap:10px;border-bottom:1px solid #2a2e38;padding-bottom:10px;margin-bottom:14px;flex-wrap:wrap}
.cardhead h2{margin:0;font-size:20px;color:#fff}
.folder{font-size:11px;color:var(--mut);font-family:monospace}
.grid{display:grid;grid-template-columns:1fr 460px;gap:20px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.text h3,.text h4,.text h5{margin:16px 0 6px;color:#fff}
.text h3{font-size:15px;color:var(--ac)}
.text p{margin:6px 0;color:#d4d6db}
.text ul,.text ol{margin:6px 0;padding-left:22px}
.text li{margin:4px 0;display:flex;align-items:center;gap:8px}
.liline{flex:1}
.text code{background:#0b0c10;padding:1px 5px;border-radius:4px;font-size:.9em;word-break:break-all}
.text a{color:#7db4ff;word-break:break-all}
blockquote{margin:10px 0;padding:8px 12px;border-left:3px solid var(--ac);background:#21161b;color:#ffd0db;border-radius:0 6px 6px 0}
hr{border:0;border-top:1px solid #2a2e38;margin:14px 0}
.copybox{position:relative;margin:8px 0}
.copytext{background:var(--box);border:1px solid #2a2e38;border-radius:8px;padding:14px 14px;white-space:pre-wrap;word-break:break-all;font-size:13.5px;color:#eaeaea;margin:0;font-family:inherit}
.copybtn{position:absolute;top:8px;right:8px;background:var(--ac);color:#fff;border:0;border-radius:6px;padding:5px 12px;font-size:12px;cursor:pointer;font-weight:700}
.copybtn:hover{filter:brightness(1.1)}
.copybtn.done,.minicopy.done{background:#36c06b}
.minicopy{background:#2f343f;color:#cfd3da;border:0;border-radius:5px;padding:2px 8px;font-size:11px;cursor:pointer;flex:none}
.minicopy:hover{background:#3a4150}
.gallery{display:flex;flex-direction:column;gap:14px;align-content:start}
.mediagrid{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-content:start}
.media{margin:0;background:#0b0c10;border:1px solid #262a33;border-radius:8px;overflow:hidden}
.mediagrid .media.vid{grid-column:1/-1}
.media.vid.cut{border-color:var(--ac)}
.sech{font-size:12px;font-weight:700;color:var(--mut);margin:0 0 6px;letter-spacing:.04em}
.clipsec .sech{color:#ffb0c2}
.emptynote{grid-column:1/-1;color:var(--mut);font-size:12px;margin:0;padding:8px;border:1px dashed #2f343f;border-radius:8px}
.media.sample{border-color:#3a4150}
.media.sample video{max-height:420px}
.samplenote{font-size:10px;color:#1a1d24;background:#7db4ff;border-radius:4px;padding:0 5px;margin-left:4px}
.clipbar{padding:7px 8px;border-top:1px solid #20242c;display:flex;flex-direction:column;gap:6px}
.cliprow{display:flex;gap:5px;align-items:center;flex-wrap:wrap}
.cliplbl{font-size:11px;color:#cfd3da;font-weight:700;min-width:38px}
.tilde{color:var(--mut)}
.clipbar input{width:78px;background:#0b0c10;border:1px solid #2a2e38;color:#eaeaea;border-radius:5px;padding:3px 6px;font-size:11px}
.setcur{font-size:10px;padding:3px 7px;border-radius:5px;border:1px solid #2f343f;background:#22262f;color:#9aa0aa;cursor:pointer}
.setcur:hover{color:#fff;border-color:var(--ac)}
.grabbtn{font-size:11px;padding:3px 10px;border-radius:6px;border:0;background:#7db4ff;color:#0b0c10;cursor:pointer;font-weight:700}
.grabbtn:hover{filter:brightness(1.08)}
.grabbtn:disabled,.cutbtn:disabled{opacity:.5;cursor:default}
.grabhint{font-size:10px;color:var(--mut)}
.media img,.media video{display:block;width:100%;height:auto;cursor:zoom-in;background:#000}
.media figcaption{font-size:11px;color:var(--mut);padding:4px 6px;display:flex;justify-content:space-between;align-items:center}
.dl{color:#7db4ff;text-decoration:none}.dl:hover{text-decoration:underline}
.nomedia{color:var(--mut);font-size:13px}
#lb{position:fixed;inset:0;background:rgba(0,0,0,.92);display:none;align-items:center;justify-content:center;z-index:50;cursor:zoom-out}
#lb img{max-width:94vw;max-height:94vh}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#36c06b;color:#fff;padding:10px 20px;border-radius:8px;font-weight:700;opacity:0;transition:opacity .2s;pointer-events:none;z-index:60}
.toast.show{opacity:1}
.status{display:flex;gap:4px;margin-left:auto}
.stbtn{font-size:11px;padding:3px 9px;border-radius:6px;border:1px solid #2f343f;background:#22262f;color:#9aa0aa;cursor:pointer}
.stbtn:hover{color:#fff}
.stbtn.on[data-val="pending"]{background:#3a4150;color:#fff;border-color:#5a6170}
.stbtn.on[data-val="posted"]{background:#36c06b;color:#fff;border-color:#36c06b}
.stbtn.on[data-val="blocked"]{background:#e0566f;color:#fff;border-color:#e0566f}
section.card[data-status="posted"]{opacity:.5}
section.card[data-status="posted"] .cardhead h2::after{content:" ✅"}
section.card[data-status="blocked"]{opacity:.45}
section.card[data-status="blocked"] .cardhead h2{text-decoration:line-through;color:#e0566f}
.counts{font-size:12px;color:var(--mut);margin-left:8px}
.cut{display:flex;gap:4px;align-items:center;padding:5px 6px;flex-wrap:wrap;border-top:1px solid #20242c}
.cut input{width:88px;background:#0b0c10;border:1px solid #2a2e38;color:#eaeaea;border-radius:5px;padding:3px 6px;font-size:11px}
.cutbtn{font-size:11px;padding:3px 10px;border-radius:6px;border:0;background:var(--ac);color:#fff;cursor:pointer;font-weight:700}
.cutbtn:disabled{opacity:.5;cursor:default}
.cutmsg{font-size:11px;color:var(--mut);flex-basis:100%}
.ab{display:flex;gap:4px;align-items:center;padding:5px 6px;flex-wrap:wrap;border-top:1px solid #20242c}
.abtn{font-size:11px;padding:3px 10px;border-radius:6px;border:1px solid #2f343f;background:#22262f;color:#9aa0aa;cursor:pointer;font-weight:700}
.abtn:hover{color:#fff}
.abtn.on[data-v="ok"]{background:#36c06b;color:#fff;border-color:#36c06b}
.abtn.on[data-v="mid"]{background:#e0b33a;color:#1a1d24;border-color:#e0b33a}
.abtn.on[data-v="ng"]{background:#e0566f;color:#fff;border-color:#e0566f}
.rebtn{font-size:11px;padding:3px 9px;border-radius:6px;border:1px solid #2f343f;background:#22262f;color:#9aa0aa;cursor:pointer;margin-left:auto}
.rebtn:hover{color:#fff;border-color:var(--ac)}
.rebtn:disabled{opacity:.5;cursor:default}
.abreason{width:100%;margin:0 6px 6px;background:#0b0c10;border:1px solid #2a2e38;color:#eaeaea;border-radius:5px;padding:3px 6px;font-size:11px}
figure.media.img[data-v="ok"]{border-color:#36c06b}
figure.media.img[data-v="mid"]{border-color:#e0b33a}
figure.media.img[data-v="ng"]{border-color:#e0566f}
figure.media.img[data-v="ng"] img,figure.media.img[data-v="mid"] img{opacity:.55}
"""

JS = """
function toast(m){var t=document.getElementById('toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(function(){t.classList.remove('show')},1300);}
function todayISO(){var d=new Date();return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);}
async function copyText(txt,btn){try{await navigator.clipboard.writeText(txt);}catch(e){var ta=document.createElement('textarea');ta.value=txt;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove();}if(btn){var o=btn.textContent;btn.textContent='✓ コピー済';btn.classList.add('done');setTimeout(function(){btn.textContent=o;btn.classList.remove('done')},1200);}toast('コピーしました');}
document.addEventListener('click',function(e){
  var ab=e.target.closest('.abtn');
  if(ab){var fg=ab.closest('figure.media.img'); var cd=ab.closest('section.card');
    var rs=fg.querySelector('.abreason'); setVerdict(cd.dataset.key, fg.dataset.image, ab.dataset.v, rs?rs.value.trim():''); return;}
  var rb=e.target.closest('.rebtn'); if(rb){doReselect(rb); return;}
  var sc=e.target.closest('.setcur'); if(sc){setCur(sc); return;}
  var gb=e.target.closest('.grabbtn'); if(gb){doGrab(gb); return;}
  var sb=e.target.closest('.stbtn'); if(sb){var cd=sb.closest('section.card'); if(cd) setStatus(cd.dataset.key, sb.dataset.val); return;}
  var cb=e.target.closest('.cutbtn'); if(cb){doCut(cb); return;}
  var b=e.target.closest('.copybtn');
  if(b){var el=document.getElementById(b.dataset.target);copyText(el.innerText,b);return;}
  var m=e.target.closest('.minicopy');
  if(m){copyText(m.dataset.text,m);return;}
  var img=e.target.closest('.media img');
  if(img){var lb=document.getElementById('lb');lb.querySelector('img').src=img.dataset.full;lb.style.display='flex';return;}
  if(e.target.id==='lb'||e.target.closest('#lb')){document.getElementById('lb').style.display='none';}
});
document.addEventListener('keydown',function(e){if(e.key==='Escape')document.getElementById('lb').style.display='none';});
var PAGE_DATE=window.__PAGE_DATE__||'';
var SKEY='fanza-status-'+PAGE_DATE;
var STATUS={};
function _loadLocal(){try{return JSON.parse(localStorage.getItem(SKEY)||'{}')}catch(e){return{}}}
function _q(key){try{return document.querySelector('section.card[data-key="'+(window.CSS&&CSS.escape?CSS.escape(key):key)+'"]')}catch(e){return null}}
function applyOne(key){var sec=_q(key);if(!sec)return;var st=STATUS[key]||'pending';sec.dataset.status=st;sec.querySelectorAll('.stbtn').forEach(function(b){b.classList.toggle('on',b.dataset.val===st)})}
function updateCounts(){var c={pending:0,posted:0,blocked:0};document.querySelectorAll('section.card').forEach(function(s){var k=s.dataset.status||'pending';c[k]=(c[k]||0)+1});var el=document.getElementById('counts');if(el)el.textContent='投稿済 '+c.posted+' ／ 投稿前 '+c.pending+' ／ 不可 '+c.blocked}
function applyAll(){document.querySelectorAll('section.card').forEach(function(s){applyOne(s.dataset.key)});updateCounts()}
async function saveStatus(){localStorage.setItem(SKEY,JSON.stringify(STATUS));try{await fetch('status.json',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(STATUS,null,2)})}catch(e){}}
function setStatus(key,val){STATUS[key]=val;applyOne(key);updateCounts();saveStatus()}
async function loadStatus(){STATUS=_loadLocal();try{var r=await fetch('status.json?_='+Date.now(),{cache:'no-store'});if(r.ok){STATUS=Object.assign({},STATUS,await r.json());localStorage.setItem(SKEY,JSON.stringify(STATUS))}}catch(e){}applyAll()}
loadStatus();
// 秒→「M:SS」表記（切り抜き入力欄に入れる用）
function fmtT(sec){var s=Math.max(0,sec); var m=Math.floor(s/60); var r=s-m*60; var w=Math.floor(r); var f=r-w; var rs=(w<10?'0':'')+w+(f>0.05?('.'+Math.round(f*10)):''); return m+':'+rs;}
// 「現在」ボタン：そのサンプル動画の再生位置を対象入力欄へ入れる
function setCur(btn){
  var bar=btn.closest('.clipbar'); var fig=btn.closest('figure.sample');
  var vid=fig?fig.querySelector('video'):null; if(!vid){return;}
  var t=btn.dataset.t; var inp=bar.querySelector('.'+t); if(inp){ inp.value=fmtT(vid.currentTime); }
}
async function doCut(btn){
  var box=btn.closest('.clipbar'); var card=btn.closest('section.card'); var msg=box.querySelector('.cutmsg');
  var start=box.querySelector('.cs').value.trim(); var end=box.querySelector('.ce').value.trim();
  var video=box.dataset.video;
  if(!start||!end){ msg.textContent='開始と終了を入力してください（「現在」で動画位置を入れられます）'; return; }
  msg.textContent='動画カット中…（数秒）'; btn.disabled=true;
  try{
    var r=await fetch('/__cut',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir:card.dataset.key, video:video, start:start, end:end})});
    var j=await r.json();
    if(j.ok){
      msg.textContent='✓ 作成: '+j.file;
      var clips=card.querySelector('.clips'); var empty=clips?clips.querySelector('.emptynote'):null; if(empty)empty.remove();
      var s=card.dataset.key+'/'+j.file+'?_='+Date.now();
      var fg=document.createElement('figure'); fg.className='media vid cut';
      fg.innerHTML='<video src="'+s+'" controls preload="metadata"></video>'+
        '<figcaption>'+j.file+' <a class="dl" href="'+card.dataset.key+'/'+j.file+'" download>保存</a></figcaption>';
      if(clips) clips.insertBefore(fg, clips.firstChild);
    } else { msg.textContent='失敗: '+(j.error||'不明'); }
  }catch(e){ msg.textContent='サーバー未起動かも（serve.py 経由で開いてください）'; }
  btn.disabled=false;
}
async function doGrab(btn){
  var box=btn.closest('.clipbar'); var card=btn.closest('section.card'); var msg=box.querySelector('.cutmsg');
  var sec=box.querySelector('.gs').value.trim(); var video=box.dataset.video;
  if(!sec){ var fig=btn.closest('figure.sample'); var vid=fig?fig.querySelector('video'):null; if(vid){sec=fmtT(vid.currentTime);} }
  if(!sec){ msg.textContent='秒を入力するか「現在」を押してください'; return; }
  msg.textContent='画像切り抜き中…'; btn.disabled=true;
  try{
    var r=await fetch('/__grab',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir:card.dataset.key, video:video, sec:sec})});
    var j=await r.json();
    if(j.ok){
      msg.textContent='✓ 画像作成: '+j.file;
      var clips=card.querySelector('.clips'); var empty=clips?clips.querySelector('.emptynote'):null; if(empty)empty.remove();
      if(clips){ var fg=makeImgFigure(card.dataset.key, j.file); clips.insertBefore(fg, clips.firstChild); }
    } else { msg.textContent='失敗: '+(j.error||'不明'); }
  }catch(e){ msg.textContent='サーバー未起動かも（serve.py 経由で開いてください）'; }
  btn.disabled=false;
}

// ── 画像のA/B判定（OK/微妙/NG）────────────────────────────
var VKEY='fanza-verdict-'+PAGE_DATE;
var VERD={};
function _loadV(){try{return JSON.parse(localStorage.getItem(VKEY)||'{}')}catch(e){return{}}}
function _figOf(post,image){
  var esc=function(s){return window.CSS&&CSS.escape?CSS.escape(s):s};
  try{return document.querySelector('section.card[data-key="'+esc(post)+'"] figure.media.img[data-image="'+esc(image)+'"]')}catch(e){return null}
}
function applyVerdict(post,image){
  var fg=_figOf(post,image); if(!fg)return;
  var rec=VERD[post+'/'+image]||{}; var v=rec.v||'';
  fg.dataset.v=v;
  fg.querySelectorAll('.abtn').forEach(function(b){b.classList.toggle('on',b.dataset.v===v)});
  if(rec.reason){var rs=fg.querySelector('.abreason'); if(rs&&!rs.value) rs.value=rec.reason;}
}
function applyAllVerdicts(){document.querySelectorAll('figure.media.img').forEach(function(fg){
  var cd=fg.closest('section.card'); if(cd) applyVerdict(cd.dataset.key, fg.dataset.image);})}
async function saveVerdict(post,image,v,reason){
  localStorage.setItem(VKEY,JSON.stringify(VERD));
  try{await fetch('/__verdict',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({date:todayISO(),post:post,image:image,verdict:v,reason:reason})});
  }catch(e){}
}
function setVerdict(post,image,v,reason){
  VERD[post+'/'+image]={v:v,reason:reason||''};
  applyVerdict(post,image);
  saveVerdict(post,image,v,reason||'');
  toast(v==='ok'?'OK → ナレッジに記録':v==='mid'?'微妙 → ナレッジに記録':'NG → ナレッジに記録');
}
async function loadVerdicts(){
  VERD=_loadV();
  try{var r=await fetch('verdicts.json?_='+Date.now(),{cache:'no-store'});
    if(r.ok){VERD=Object.assign({},VERD,await r.json());localStorage.setItem(VKEY,JSON.stringify(VERD))}}catch(e){}
  applyAllVerdicts();
}
loadVerdicts();
function makeImgFigure(post,file){
  var fg=document.createElement('figure'); fg.className='media img'; fg.dataset.image=file;
  fg.innerHTML='<img src="'+post+'/'+file+'?_='+Date.now()+'" loading="lazy" data-full="'+post+'/'+file+'" alt="'+file+'">'+
    '<figcaption>'+file+' <a class="dl" href="'+post+'/'+file+'" download>保存</a></figcaption>'+
    '<div class="ab"><button class="abtn" data-v="ok">OK</button>'+
    '<button class="abtn" data-v="mid">微妙</button>'+
    '<button class="abtn" data-v="ng">NG</button>'+
    '<button class="rebtn" title="この画像の代わりをサンプル動画から選び直す">🔄再選出</button></div>'+
    '<input class="abreason" type="text" placeholder="理由（任意・ナレッジに記録）">';
  return fg;
}
async function doReselect(btn){
  var card=btn.closest('section.card'); var old=btn.textContent;
  btn.disabled=true; btn.textContent='選出中…';
  try{
    var r=await fetch('/__reselect',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir:card.dataset.key})});
    var j=await r.json();
    if(j.ok){
      var grid=card.querySelector('.sysgrid')||card.querySelector('.clips');
      var fg=makeImgFigure(card.dataset.key, j.file);
      if(grid) grid.appendChild(fg);
      toast('別候補を追加: '+j.file);
    } else { toast('再選出: '+(j.error||'失敗')); }
  }catch(e){ toast('サーバー未起動かも（serve.py 経由で開いてください）'); }
  btn.disabled=false; btn.textContent=old;
}
"""


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))

    # 新構成：works/ 配下の全作品を1枚の常設ダッシュボードに集約する。
    #   引数でフォルダ指定も可（後方互換：旧 output/<日付> も生成できる）。
    if len(argv) >= 2:
        works_dir = os.path.abspath(argv[1])
    else:
        works_dir = os.path.join(here, "..", "works")
        os.makedirs(works_dir, exist_ok=True)

    if not os.path.isdir(works_dir):
        print(f"エラー: フォルダが見つかりません: {works_dir}")
        return 1

    post_dirs = sorted(
        [d for d in glob.glob(os.path.join(works_dir, "*"))
         if os.path.isdir(d) and os.path.isfile(os.path.join(d, "投稿内容.md"))],
        key=lambda p: natural_key(os.path.basename(p)),
    )
    if not post_dirs:
        print(f"作品がまだありません（{works_dir}）。"
              "先に fetch_and_build.py で作品を取得してください。")
        # 空でも器（index.html＋DB）は作る
        post_dirs = []

    title_label = "FANZA 作品ダッシュボード"

    cards = []
    nav = []
    for idx, pd in enumerate(post_dirs):
        cards.append(build_card(pd, idx))
        navlabel = os.path.basename(pd)
        md_p = os.path.join(pd, "投稿内容.md")
        if os.path.isfile(md_p):
            with open(md_p, encoding="utf-8") as f:
                m = re.search(r"^#\s+(.+)$", f.read(), re.M)
                if m:
                    navlabel = m.group(1).strip()
        nav.append(f'<a href="#post-{idx}">{html.escape(navlabel)}</a>')

    body_html = ''.join(cards) if cards else (
        '<p class="nomedia">作品がまだありません。'
        '<code>python3 fetch_and_build.py</code> で取得後、再生成してください。</p>')

    htmlout = f'''<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title_label)}</title>
<style>{CSS}</style>
</head><body>
<header class="top">
  <h1>📋 {html.escape(title_label)}（{len(post_dirs)}作品）<span id="counts" class="counts"></span></h1>
  <nav class="nav">{''.join(nav)}</nav>
</header>
<div class="wrap">
{body_html}
</div>
<div id="lb"><img alt=""></div>
<div id="toast" class="toast"></div>
<script>window.__PAGE_DATE__="works";</script>
<script>{JS}</script>
</body></html>'''

    out_path = os.path.join(works_dir, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(htmlout)

    # ステータス／画像A/B判定の保存用DB（ダッシュボード全体で1つ。無ければ作る）
    for db in ("status.json", "verdicts.json"):
        p = os.path.join(works_dir, db)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write("{}\n")

    print(f"生成しました: {out_path}")
    print(f"  作品数: {len(post_dirs)}件")
    print(f"  ブラウザで開く: open \"{out_path}\"")
    print(f"  共有で開く: python3 {os.path.join(here, 'serve.py')} → http://<IP>:8000/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
