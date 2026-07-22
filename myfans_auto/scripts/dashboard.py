#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MyFansの `works/` に集めた全作品を、まとめて確認・投稿作業するための全体ボード
（`works/board.html`）と、アーカイブした作品の一覧（`works/archive.html`）を作る。
fanza_auto/scripts/schedule_board.py のMyFans向け簡略版（MissAV確認は無い）。

各作品カードには：
  - タイトル・投稿者名
  - 作った切り抜き（cut_*.mp4 / crop_*.mp4）の一覧＋⬇保存・🗑削除
  - ①リンク投稿・②メイン投稿のコピー
  - 個別ボード（board_<投稿ID>.html）へのリンク（動画の再生・切り抜き・画面トリミングはそちら）
  - board.html側：「📦 アーカイブ」ボタン（押すとカードが消え、archive.html に移る）
  - archive.html側：「🗑 完全削除」（フォルダごと消す）「↩ 全体ボードに戻す」の2ボタン

上部のURL欄に自分のMyFansアフィリンクを貼ると取り込める（`myfans_fetch.py`。
タイトル・説明文・サムネ画像のみ）。動画はChrome拡張機能で保存してプロジェクトの
ルートフォルダに置き、「🎬 動画を取り込む」ボタンで対応フォルダに振り分ける
（`import_video.py`）。

アーカイブ状態は各作品の item.json の "archived" に保存する（ブラウザのlocalStorageではなく
サーバー側で永続化。実際の更新は serve.py の /__archive・/__unarchive・/__delete_work が行う）。

使い方（プロジェクトのルートフォルダで実行）:
    python3 myfans_auto/scripts/dashboard.py            # board.html・archive.html を作る
    python3 myfans_auto/scripts/dashboard.py --open     # 作ってそのまま board.html を開く
"""

import datetime
import html
import sys
import urllib.parse

import common as C
import board as BB


def board_path():
    return C.WORKS_DIR / "board.html"


def archive_path():
    return C.WORKS_DIR / "archive.html"


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


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
.wrap{max-width:1400px;margin:0 auto}
header{padding:28px 0 16px}
.hdr-row{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
h1{font-size:1.5rem;margin:0 0 6px}
.hdr-link{font-size:.85rem;font-weight:600}
.lead{color:var(--sub);margin:0 0 4px;font-size:.9rem}
/* 横一列＋スナップスクロール：カード3枚分くらいが見える幅で並べ、指/トラックパッドで
   スーッとスクロールできるようにする（スマホのフリックにも対応）。 */
.grid{display:flex;gap:16px;margin-top:16px;padding-bottom:12px;overflow-x:auto;
 scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch}
.grid::-webkit-scrollbar{height:10px}
.grid::-webkit-scrollbar-thumb{background:var(--line);border-radius:999px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
 display:flex;flex-direction:column;gap:10px;
 flex:0 0 clamp(280px,31vw,380px);min-width:0;scroll-snap-align:start}
.card h2{font-size:1.02rem;margin:0}
.card h2 .title-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
 overflow:hidden;line-height:1.3;min-height:2.6em}
.card-sub{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;
 gap:6px 10px;margin:0;font-size:.78rem}
.cid{font-size:.72rem;color:var(--sub);font-weight:400}
.meta{font-size:.82rem;color:var(--sub);margin:0}
.notice{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:8px 10px;
 font-size:.78rem;margin:0}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);
 border-radius:7px;padding:6px 12px;font-size:.82rem;cursor:pointer;font-family:inherit}
button:hover{border-color:var(--accent);color:var(--accent)}
button.copied{background:var(--okbg);color:var(--ok);border-color:transparent}
button.delete-btn:hover{border-color:#dc2626;color:#dc2626}
.clips{display:flex;flex-direction:column;gap:8px}
.clip{border:1px solid var(--line);border-radius:8px;padding:0 0 8px;background:var(--bg);
 overflow:hidden}
/* 動画は本来の縦横比のまま、ボックス幅いっぱいに表示する（クロップしない）。
   高さは動画ごとの比率任せなので、縦長・横長が混ざるとカードの高さは揃わない
   （揃えるためにクロップする方を避けるため、これは許容する）。 */
.clip video{width:100%;height:auto;display:block;background:#000;margin-bottom:6px}
.clip .clip-h{padding:0 8px}
/* 複数カットあるときは1本だけ全幅で表示し、左右の矢印（ホバーで表示）で
   切り替えるカルーセルにする（1本の時と同じ「ボックス幅いっぱい」を維持するため）。 */
.clip-carousel{position:relative}
.clip-carousel .clip{display:none}
.clip-carousel .clip.active{display:block}
.car-nav{position:absolute;top:0;bottom:26px;width:34px;display:flex;align-items:center;
 justify-content:center;background:none;border:none;color:#fff;font-size:1.3rem;
 cursor:pointer;opacity:0;transition:opacity .15s;z-index:2;padding:0}
.car-nav:hover{color:#fff;background:rgba(0,0,0,.25)}
.car-prev{left:0}
.car-next{right:0}
.clip-carousel:hover .car-nav{opacity:1}
.car-count{position:absolute;top:6px;right:6px;background:rgba(0,0,0,.55);color:#fff;
 font-size:.68rem;padding:1px 7px;border-radius:999px;z-index:2;pointer-events:none}
.thumbgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;
 min-width:0}
.thumbgrid>*{min-width:0}
.clip.thumb img{width:100%;height:auto;display:block;border-radius:6px;margin-bottom:6px}
/* 動画・サムネがまだ無い時のプレースホルダー。実物と同じくらいの高さになるよう、
   固定pxではなく実物でよくある比率（動画16:9・サムネ4:3）で高さを決める
   （ボックス幅いっぱいに広がるので、幅が変わっても比率で高さが追従する）。 */
.empty-slot{display:flex;flex-direction:column;align-items:center;justify-content:center;
 gap:4px;text-align:center;border:1.5px dashed var(--line);border-radius:6px;
 color:var(--sub);font-size:.78rem;text-decoration:none;padding:8px;box-sizing:border-box;
 aspect-ratio:16/9;background:var(--card)}
.empty-slot:hover{border-color:var(--accent);color:var(--accent)}
.clip .empty-slot{margin:0 8px 6px;width:calc(100% - 16px)}
.empty-slot.thumb{aspect-ratio:4/3;margin-bottom:6px}
.clip-h{display:flex;justify-content:space-between;align-items:center;gap:8px;
 font-size:.76rem;margin-bottom:4px;min-height:31px}
.clip-h>span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.clip-act{display:flex;gap:6px;flex-shrink:0}
.dl{display:inline-block;border:1px solid var(--line);border-radius:7px;padding:4px 10px;
 font-size:.76rem;text-decoration:none;color:var(--fg);white-space:nowrap;flex-shrink:0}
.dl:hover{border-color:var(--accent);color:var(--accent)}
button.del{font-size:.74rem;padding:4px 9px;color:var(--sub);white-space:nowrap;flex-shrink:0}
button.del:hover{border-color:#dc2626;color:#dc2626}
.blk{margin:0}
.blk-h{display:flex;justify-content:space-between;align-items:center;gap:8px;
 font-size:.8rem;font-weight:700;margin:0 0 5px}
pre{margin:0;padding:10px;background:var(--bg);border:1px solid var(--line);
 border-radius:8px;white-space:pre-wrap;word-break:break-word;font-size:.85rem;
 font-family:inherit}
pre.link{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.7rem;color:var(--sub)}
.foot{display:flex;justify-content:space-between;align-items:center;gap:8px;
 border-top:1px solid var(--line);padding-top:10px;flex-wrap:wrap}
.archive-actions{display:flex;gap:8px}
a.open{display:inline-block;font-size:.8rem;font-weight:600;text-decoration:none;
 color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:6px 12px;
 background:var(--card)}
a.open:hover{border-color:var(--accent);color:var(--accent)}
button.archive-btn{border-color:#dc2626;color:#dc2626}
button.archive-btn:hover{background:#dc2626;color:#fff}
.empty{text-align:center;color:var(--sub);padding:40px 0}
.badge{font-size:.72rem;padding:2px 9px;border-radius:999px;background:var(--okbg);color:var(--ok);
 font-weight:600}
.fetchbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
.fetchbar input{flex:1;min-width:240px;padding:9px 12px;border:1px solid var(--line);
 border-radius:8px;background:var(--card);color:var(--fg);font-size:.9rem}
.fetchbar button{background:var(--accent);color:#fff;border-color:transparent;font-weight:700;
 padding:9px 16px;white-space:nowrap}
.fetchbar button:hover{opacity:.9;color:#fff}
.fetchbar button:disabled{opacity:.5;cursor:default}
.step-label{font-size:.82rem;font-weight:700;color:var(--fg);margin:14px 0 6px}
.fetch-status{font-size:.82rem;color:var(--sub)}
.fetch-status.ok{color:var(--ok)}
.fetch-status.err{color:var(--accent)}
.importbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:8px}
.importbar button{background:var(--card);font-weight:700}
"""

JS = """
// コピー（サブ投稿・メイン投稿・アフィリンク）：ボタンの文字を一時的に「✓ コピーした」に変える。
function flashBtn(btn,msg){const o=btn.textContent;btn.textContent=msg;
  btn.classList.add('copied');setTimeout(()=>{btn.textContent=o;
  btn.classList.remove('copied');},1200);}
function copyText(text,btn){
  const fallback=()=>{const t=document.createElement('textarea');
    t.value=text;t.style.position='fixed';t.style.opacity='0';
    document.body.appendChild(t);t.select();
    try{document.execCommand('copy');flashBtn(btn,'✓ コピーした');}
    catch(e){alert('コピーできませんでした。手で選択してください。');}
    document.body.removeChild(t);};
  if(navigator.clipboard&&window.isSecureContext){
    navigator.clipboard.writeText(text).then(()=>flashBtn(btn,'✓ コピーした'),fallback);
  }else{fallback();}
}
document.addEventListener('click',e=>{
  const b=e.target.closest('button[data-copy]');if(!b)return;
  const el=document.getElementById(b.dataset.copy);
  if(el)copyText(el.textContent,b);
});

// 複数カットのカルーセル：常に1本だけ全幅で表示し、左右の矢印（ホバーで表示）
// またはクリックで前/次に切り替える。切り替えたら隠れた側の動画は一時停止する。
function showClip(carousel,idx){
  const clips=carousel.querySelectorAll(':scope > .clip');
  const n=clips.length;
  const next=((idx%n)+n)%n;
  clips.forEach((c,i)=>{
    const on=i===next;
    c.classList.toggle('active',on);
    if(!on){const v=c.querySelector('video');if(v)v.pause();}
  });
  carousel.dataset.idx=next;
  const cnt=carousel.querySelector('.car-count');
  if(cnt)cnt.textContent=(next+1)+' / '+n;
}
document.addEventListener('click',e=>{
  const b=e.target.closest('.car-nav');if(!b)return;
  e.preventDefault();
  const carousel=b.closest('.clip-carousel');
  const idx=parseInt(carousel.dataset.idx||'0',10);
  showClip(carousel,idx+(b.classList.contains('car-next')?1:-1));
});

// アーカイブ操作（📦アーカイブ／🗑完全削除／↩全体ボードに戻す）。
// board.html・archive.html・board_<投稿ID>.html のどのページから叩いても
// serve.py 側の共通Handlerが処理する。
document.addEventListener('click',async e=>{
  const b=e.target.closest('.archive-btn,.unarchive-btn,.delete-btn');
  if(!b)return;
  if(location.protocol==='file:'){
    alert('この操作は serve.py 経由でのみ動きます。');return;}
  const dir=b.dataset.dir;
  const card=b.closest('.card');
  let url,label;
  if(b.classList.contains('archive-btn')){url='/__archive';label='アーカイブ中…';}
  else if(b.classList.contains('unarchive-btn')){url='/__unarchive';label='戻し中…';}
  else{
    if(!confirm('完全に削除します。元に戻せません。よろしいですか？'))return;
    url='/__delete_work';label='削除中…';
  }
  const old=b.textContent;b.textContent=label;
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

// 切り抜き素材の削除（serve.py が /__del を中継）
document.addEventListener('click',async e=>{
  const b=e.target.closest('button.del');if(!b)return;
  const file=b.dataset.file, dir=b.dataset.dir;
  const clip=b.closest('.clip');
  if(location.protocol==='file:'){alert('削除は serve.py 経由でのみ動きます。');return;}
  if(!confirm(`「${file}」を削除します。元に戻せません。よろしいですか？`))return;
  const old=b.textContent;b.textContent='削除中…';b.disabled=true;
  try{
    const r=await fetch('/__del',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({dir,file})});
    const j=await r.json();
    if(!j.ok){alert('削除に失敗: '+(j.error||'不明なエラー'));b.textContent=old;b.disabled=false;}
    else{clip.remove();}
  }catch(ex){alert('通信に失敗しました: '+ex);b.textContent=old;b.disabled=false;}
});

// URLを貼って新規作品を取り込む（タイトル・本文全文・サムネ・サンプル動画を自動取得）
document.addEventListener('click',async e=>{
  const b=e.target.closest('#fetch-go');if(!b)return;
  const input=document.getElementById('fetch-url');
  const status=document.getElementById('fetch-status');
  const url=input.value.trim();
  status.className='fetch-status';status.textContent='';
  if(!url){status.className='fetch-status err';status.textContent='URLを入力してください';return;}
  if(location.protocol==='file:'){
    status.className='fetch-status err';
    status.textContent='取り込みは serve.py 経由でのみ動きます。';return;}
  const old=b.textContent;b.textContent='取り込み中…';b.disabled=true;input.disabled=true;
  status.className='fetch-status';status.textContent='MyFansから取得中…本文・サムネ・サンプル動画を確認しています（数秒〜十数秒）。';
  try{
    const r=await fetch('/__fetch',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url})});
    const j=await r.json();
    if(!j.ok){
      status.className='fetch-status err';status.textContent='失敗: '+(j.error||'不明なエラー');
      b.textContent=old;b.disabled=false;input.disabled=false;
    }else{
      status.className='fetch-status ok';status.textContent=`✓ 取り込みました: ${j.title}（反映中…）`;
      location.reload();   // 新しいカードを含む最新の board.html を読み直す
    }
  }catch(ex){
    status.className='fetch-status err';status.textContent='通信に失敗しました: '+ex;
    b.textContent=old;b.disabled=false;input.disabled=false;
  }
});
document.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&e.target.id==='fetch-url')document.getElementById('fetch-go').click();
});

// プロジェクトのルートフォルダに置いた動画（拡張機能でDLしたもの）を、
// タイトルの一致で対応する作品フォルダに sample.mp4 として振り分ける。
document.addEventListener('click',async e=>{
  const b=e.target.closest('#import-go');if(!b)return;
  const status=document.getElementById('import-status');
  status.className='fetch-status';status.textContent='';
  if(location.protocol==='file:'){
    status.className='fetch-status err';
    status.textContent='取り込みは serve.py 経由でのみ動きます。';return;}
  const old=b.textContent;b.textContent='取り込み中…';b.disabled=true;
  status.className='fetch-status';status.textContent='ルートフォルダの動画を確認しています…';
  try{
    const r=await fetch('/__import_video',{method:'POST'});
    const j=await r.json();
    if(!j.ok){
      status.className='fetch-status err';status.textContent='失敗: '+(j.error||'不明なエラー');
      b.textContent=old;b.disabled=false;return;
    }
    const parts=[];
    if(j.moved.length)parts.push(`✓ ${j.moved.length}件 取り込みました: `+j.moved.map(m=>m.title).join('、'));
    if(j.ambiguous.length)parts.push(`⚠️ 候補が複数あり判定できない: `+j.ambiguous.map(a=>a.file).join('、'));
    if(j.unmatched.length)parts.push(`・対応する作品が見つからない: `+j.unmatched.join('、'));
    if(!parts.length)parts.push('ルートフォルダに動画ファイルがありません。');
    status.className='fetch-status '+(j.moved.length?'ok':'');
    status.textContent=parts.join(' ／ ');
    b.textContent=old;b.disabled=false;
    if(j.moved.length)location.reload();
  }catch(ex){
    status.className='fetch-status err';status.textContent='通信に失敗しました: '+ex;
    b.textContent=old;b.disabled=false;
  }
});
"""


def copy_block(label: str, text: str, elid: str, extra_cls: str = "") -> str:
    """コピー可能な1ブロック（build_board.py の block() と同じ見た目）。"""
    return f"""      <div class="blk">
        <div class="blk-h"><span>{label}</span>
          <button data-copy="{elid}">コピー</button></div>
        <pre class="{extra_cls}" id="{elid}">{esc(text)}</pre>
      </div>"""


def render_card(e: dict, post: dict, archived: bool) -> str:
    cid = e["cid"]
    # board.html / archive.html は works/ 直下にあるので、<video src> 等の相対リンクと
    # /__del 等API向けのパス（BB.rel_dir、works/直下基準）は同じ値になる。
    dir_name = BB.rel_dir(e["dir"])
    board_url = f"board_{urllib.parse.quote(cid)}.html"

    # ★ユーザー方針（2026-07-22）：全体ボードでは★評価を表示しない
    #   （並び順はこれまで通りレビューの良い順を維持。表示だけ外す）。

    # ★ユーザー方針（2026-07-20）：このボードには元のサンプル動画は出さず、
    #   「カットした動画（cut_/crop_）」だけを載せる。編集前の元動画を見たいときは
    #   個別ページ（board_<cid>.html）を開く。
    n_clips = len(e["clips"])
    clips_html = ""
    for i, f in enumerate(e["clips"]):
        csrc = BB.rel_media(dir_name, f)
        icon = "🔲" if f.startswith("crop_") else "✂"
        active = " active" if i == 0 else ""
        clips_html += (
            f'<div class="clip{active}"><video controls preload="metadata" src="{csrc}"></video>'
            f'<div class="clip-h"><span>{icon} {esc(f)}</span>'
            f'<span class="clip-act">'
            f'<a class="dl" href="{csrc}" download="{esc(f)}">⬇ 保存</a>'
            f'<button class="del" data-file="{esc(f)}" '
            f'data-dir="{esc(dir_name)}">🗑 削除</button></span></div></div>')
    if n_clips >= 2:
        # 複数カットは常にボックス幅いっぱいで1本ずつ表示し、左右の矢印
        # （ホバーで表示）で切り替えるカルーセルにする。
        clips_block = (
            f'<div class="clip-carousel" data-idx="0">{clips_html}'
            '<button class="car-nav car-prev" aria-label="前の動画">‹</button>'
            '<button class="car-nav car-next" aria-label="次の動画">›</button>'
            f'<span class="car-count">1 / {n_clips}</span></div>')
    elif clips_html:
        clips_block = clips_html
    else:
        clips_block = ('<div class="clip empty-clip">'
                       f'<a class="empty-slot" href="{board_url}" target="_blank" rel="noopener">'
                       'まだ動画がありません<br>＋ 作成する →</a>'
                       '<div class="clip-h">&nbsp;</div></div>')

    # 完成したサムネ画像（thumb_*.jpg）も、ここから保存・削除できるようにする。
    thumbs_html = ""
    for f in e["thumbs"]:
        tsrc = BB.rel_media(dir_name, f)
        thumbs_html += (
            f'<div class="clip thumb" data-file="{esc(f)}">'
            f'<img src="{tsrc}" loading="lazy">'
            f'<div class="clip-h"><span>🖼 {esc(f)}</span>'
            f'<span class="clip-act">'
            f'<a class="dl" href="{tsrc}" download="{esc(f)}">⬇ 保存</a>'
            f'<button class="del" data-file="{esc(f)}" '
            f'data-dir="{esc(dir_name)}">🗑 削除</button></span></div></div>')
    thumbs_block = (f'<div class="clips thumbgrid">{thumbs_html}</div>' if thumbs_html else
                   f'<div class="clips thumbgrid"><a class="empty-slot thumb" href="{board_url}" '
                   f'target="_blank" rel="noopener">まだサムネがありません<br>'
                   f'＋ 作成する →</a></div>')

    board_url = f"board_{urllib.parse.quote(cid)}.html"
    uid = cid.replace(".", "_")

    # ここでもアフィリンク・投稿文をコピーできるように
    # （個別ページを開かなくても、このボードだけで投稿作業を完結できる）。
    copy_blocks = (
        copy_block("リンク投稿（アフィリンクを持たせる側）", post.get("sub", ""), f"sub-{uid}")
        + copy_block("メイン投稿（リンク投稿を引用して出す）", post.get("main", ""), f"main-{uid}")
    )

    archive_html = C.archive_block_html(dir_name, archived)
    creator = f"　{esc(e['creator'])}さん" if e.get("creator") else ""

    return f"""    <article class="card" data-cid="{esc(cid)}">
      <h2><span class="title-text">{esc(e['title'])}</span></h2>
      <p class="card-sub"><span class="cid">{esc(cid)}{creator}</span>
        <a class="open" href="{board_url}" target="_blank" rel="noopener">🎬 動画・画像を編集する →</a></p>
      {clips_block}
      {thumbs_block}
      {copy_blocks}
      <div class="foot">
        {archive_html}
      </div>
    </article>"""


def render(entries: list, posts: dict, archived: bool, other_count: int) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = "\n".join(
        render_card(e, posts.get(e["cid"], {}), archived)
        for e in entries)

    if archived:
        title = "アーカイブ一覧"
        lead = ("アーカイブした作品の一覧。「🗑 完全削除」でフォルダごと消去、"
                "「↩ 全体ボードに戻す」で全体ボードに戻せます。")
        nav = f'<a class="hdr-link" href="board.html">← 全体ボードに戻る（{other_count}件）</a>'
        empty_msg = "アーカイブされた作品はありません。"
        fetchbar = ""
    else:
        title = "全体ボード"
        lead = ("投稿に使う作品をまとめて確認・コピー作業する。"
                "詳しい画像/動画編集は各作品の個別ページで行う。")
        nav = f'<a class="hdr-link" href="archive.html">🗄 アーカイブ一覧（{other_count}件）→</a>'
        empty_msg = "works/ に作品がありません。"
        fetchbar = """  <p class="step-label">① MyFansの投稿URL（自分のアフィリンク）を貼り付け
     （タイトル・本文・サムネ・無料サンプル動画まで自動取得されます）</p>
  <div class="fetchbar">
    <input type="text" id="fetch-url" placeholder="MyFansの投稿URL（自分のアフィリンク）を貼り付け">
    <button id="fetch-go">＋ 取り込む</button>
    <span class="fetch-status" id="fetch-status"></span>
  </div>
  <p class="step-label">②（任意）本編の動画を使いたいときは、拡張機能
     （FetchV Video Download 等）で保存し、プロジェクトのルートフォルダに配置</p>
  <p class="step-label">③（任意）動画を取り込む</p>
  <div class="importbar">
    <button id="import-go">🎬 動画を取り込む</button>
    <span class="fetch-status" id="import-status">プロジェクトのルートフォルダに置いた動画を、対応する作品フォルダへ振り分けます。</span>
  </div>
"""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}｜MyFans</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="hdr-row">
    <h1>{esc(title)} <span class="badge">{len(entries)}件</span></h1>
    {nav}
  </div>
  <p class="lead">{lead}</p>
  <p class="lead">更新 {now}</p>
{fetchbar}</header>
<div class="grid">
{cards}
</div>
<p class="empty" style="display:{'block' if not entries else 'none'}">
   {esc(empty_msg)}</p>
</div>
<script>{JS}</script>
</body>
</html>
"""


def build_all():
    """works/board.html（未アーカイブ）と works/archive.html（アーカイブ済み）の
    両方を作り直す。件数バッジを常に正しく保つため、呼ぶたびに両方書き出す。"""
    entries = BB.collect()
    active = [e for e in entries if not e["item"].get("archived")]
    archived = [e for e in entries if e["item"].get("archived")]
    active.sort(key=BB.sort_key)
    archived.sort(key=BB.sort_key)

    posts = BB.ensure_posts(entries, regen=False)

    board_path().write_text(
        render(active, posts, archived=False, other_count=len(archived)), encoding="utf-8")
    archive_path().write_text(
        render(archived, posts, archived=True, other_count=len(active)), encoding="utf-8")
    print(f"✓ 全体ボードを作りました: {board_path()}"
          f"（{len(active)} 作品／アーカイブ {len(archived)} 作品）")
    return board_path()


def main(argv) -> int:
    flags = set(a for a in argv[1:] if a.startswith("--"))
    out = build_all()
    if "--open" in flags:
        import subprocess
        subprocess.run(["open", str(out)], check=False)
    else:
        print("  切り抜き・アーカイブ・URL/動画取り込みを使うには: "
              "python3 myfans_auto/scripts/serve.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
