#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`works/<投稿予定日>/`（例：works/2026-07-25/）に集めた作品を、まとめて確認・投稿作業する
ためのダッシュボード（`works/<日付>/dashboard.html`）を作る。

★ユーザー方針（2026-07-20）：「進行中」という固定フォルダではなく、投稿予定日ごとの
フォルダで管理する。fetch_and_build.py が取り込み時に日付を聞いて works/<日付>/ に置く。

各作品カードには：
  - タイトル・★評価
  - 作った切り抜き（cut_*.mp4 / crop_*.mp4）の一覧＋⬇保存・🗑削除
  - ①サブ投稿・②メイン投稿・アフィリンクのコピー
  - 「投稿済みにする」トグル（ブラウザのlocalStorageに保存・サーバー不要）
  - 個別ボード（board_<cid>.html）へのリンク（動画の再生・切り抜き・画面トリミングはそちら）

使い方（プロジェクトのルートフォルダで実行）:
    python3 fanza_auto/scripts/schedule_board.py                 # 全日付ぶんの dashboard.html を作る
    python3 fanza_auto/scripts/schedule_board.py 2026-07-25       # その日付だけ作る
    python3 fanza_auto/scripts/schedule_board.py 2026-07-25 --open
"""

import datetime
import html
import sys
import urllib.parse

import common as C
import build_board as BB
import post_text as PT


def dashboard_path(date: str):
    return C.WORKS_DIR / date / "dashboard.html"


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
h1{font-size:1.5rem;margin:0 0 6px}
.lead{color:var(--sub);margin:0 0 4px;font-size:.9rem}
/* 横一列＋スナップスクロール：カード3枚分くらいが見える幅で並べ、指/トラックパッドで
   スーッとスクロールできるようにする（スマホのフリックにも対応）。 */
.grid{display:flex;gap:16px;margin-top:16px;padding-bottom:12px;overflow-x:auto;
 scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch}
.grid::-webkit-scrollbar{height:10px}
.grid::-webkit-scrollbar-thumb{background:var(--line);border-radius:999px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
 display:flex;flex-direction:column;gap:10px;
 flex:0 0 clamp(280px,31vw,380px);scroll-snap-align:start}
.card.done{opacity:.55}
.card h2{font-size:1.02rem;margin:0;display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.cid{font-size:.72rem;color:var(--sub);font-weight:400}
.meta{font-size:.82rem;color:var(--sub);margin:0}
video{width:100%;max-height:280px;background:#000;border-radius:8px;display:block}
.notice{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:8px 10px;
 font-size:.78rem;margin:0}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);
 border-radius:7px;padding:6px 12px;font-size:.82rem;cursor:pointer;font-family:inherit}
button:hover{border-color:var(--accent);color:var(--accent)}
button.copied{background:var(--okbg);color:var(--ok);border-color:transparent}
.clips{display:flex;flex-direction:column;gap:8px}
.clip{border:1px solid var(--line);border-radius:8px;padding:8px;background:var(--bg)}
.clip video{max-height:180px;margin-bottom:6px}
.thumbgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.clip.thumb img{width:100%;height:auto;display:block;border-radius:6px;margin-bottom:6px}
.clip-h{display:flex;justify-content:space-between;align-items:center;gap:8px;
 font-size:.76rem;margin-bottom:4px}
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
a.open{font-size:.82rem;font-weight:600}
.empty{text-align:center;color:var(--sub);padding:40px 0}
.badge{font-size:.72rem;padding:2px 9px;border-radius:999px;background:var(--okbg);color:var(--ok);
 font-weight:600}
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

// 投稿済みチェック（ローカル保存）
const DONE='fanza_schedule_done';
const done=new Set(JSON.parse(localStorage.getItem(DONE)||'[]'));
function paint(){document.querySelectorAll('.card').forEach(c=>{
  const on=done.has(c.dataset.cid);c.classList.toggle('done',on);
  const b=c.querySelector('button[data-done]');
  if(b)b.textContent=on?'✓ 投稿済み':'投稿済みにする';});}
document.addEventListener('click',e=>{
  const b=e.target.closest('button[data-done]');if(!b)return;
  const cid=b.closest('.card').dataset.cid;
  done.has(cid)?done.delete(cid):done.add(cid);
  localStorage.setItem(DONE,JSON.stringify([...done]));paint();});
paint();

// 切り抜き素材の削除（serve_schedule.py が /__del を中継）
document.addEventListener('click',async e=>{
  const b=e.target.closest('button.del');if(!b)return;
  const file=b.dataset.file, dir=b.dataset.dir;
  const clip=b.closest('.clip');
  if(location.protocol==='file:'){alert('削除は serve_schedule.py 経由でのみ動きます。');return;}
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
"""


def copy_block(label: str, text: str, elid: str, extra_cls: str = "") -> str:
    """コピー可能な1ブロック（build_board.py の block() と同じ見た目）。"""
    return f"""      <div class="blk">
        <div class="blk-h"><span>{label}</span>
          <button data-copy="{elid}">コピー</button></div>
        <pre class="{extra_cls}" id="{elid}">{esc(text)}</pre>
      </div>"""


def render_card(e: dict, post: dict, date_dir) -> str:
    cid = e["cid"]
    # dashboard.html は works/<日付>/ 直下にあるので、<video src> 等の相対リンクは
    # そこからの相対パス（dir_name）にする。BB.rel_dir は works/ 直下基準なので、
    # そのまま使うと「<日付>/」が二重に付いて 404 になる。
    # 一方 /__del API（serve_schedule.py→_safe_dir）は works/ 直下基準のパスを
    # 期待するので、そちらは api_dir（BB.rel_dir）を別に使う。
    dir_name = e["dir"].relative_to(date_dir).as_posix()
    api_dir = BB.rel_dir(e["dir"])

    bits = []
    if e["review_avg"] is not None:
        bits.append(f"★{e['review_avg']:.2f}（{e['review_count']}件）")
    meta = f'<p class="meta">{" / ".join(bits)}</p>' if bits else ""

    # ★ユーザー方針（2026-07-20）：このダッシュボードには元のサンプル動画は出さず、
    #   「カットした動画（cut_/crop_）」だけを載せる。編集前の元動画を見たいときは
    #   個別ページ（board_<cid>.html）を開く。
    clips_html = ""
    for f in e["clips"]:
        csrc = BB.rel_media(dir_name, f)
        icon = "🔲" if f.startswith("crop_") else "✂"
        clips_html += (
            f'<div class="clip"><video controls preload="metadata" src="{csrc}"></video>'
            f'<div class="clip-h"><span>{icon} {esc(f)}</span>'
            f'<span class="clip-act">'
            f'<a class="dl" href="{csrc}" download="{esc(f)}">⬇ 保存</a>'
            f'<button class="del" data-file="{esc(f)}" '
            f'data-dir="{esc(api_dir)}">🗑 削除</button></span></div></div>')
    clips_block = (f'<div class="clips">{clips_html}</div>' if clips_html else
                   '<p class="notice">まだカットされた動画がありません。'
                   '個別ページで動画を切り抜くとここに表示されます。</p>')

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
            f'data-dir="{esc(api_dir)}">🗑 削除</button></span></div></div>')
    thumbs_block = (f'<div class="clips thumbgrid">{thumbs_html}</div>' if thumbs_html else
                   '<p class="notice">まだサムネ画像がありません。'
                   '個別ページで作るとここに表示されます。</p>')

    # ★ユーザー方針（2026-07-20）：未成年連想ジャンルのオンページ警告・
    #   投稿日時/アカウント/メモの入力フォームは不要（画像は毎回目視確認済み、
    #   スケジュールは「投稿済みにする」トグル1つで十分とのこと）。
    #   caution_genres() 自体は削除せず、生成時のターミナルログにだけ残す。
    cautions = PT.caution_genres(e["item"])
    if cautions:
        print(f"  ⚠️ {cid}: {'・'.join(cautions)} のジャンル付き。"
              "画像は未成年に見えないか目視で確認してください。")

    board_url = f"../board_{urllib.parse.quote(cid)}.html"
    uid = cid.replace(".", "_")

    # ★ユーザー方針（2026-07-20）：ここでもアフィリンク・投稿文をコピーできるように
    # （個別ページを開かなくても、このダッシュボードだけで投稿作業を完結できる）。
    copy_blocks = (
        copy_block("① サブ投稿（リンクを持たせる側）", post.get("sub", ""), f"sub-{uid}")
        + copy_block("② メイン投稿（①を引用して出す）", post.get("main", ""), f"main-{uid}")
        + (copy_block("アフィリエイトリンク（単体）", e["aff_url"], f"aff-{uid}", "link")
           if e["aff_url"] else "")
    )

    return f"""    <article class="card" data-cid="{esc(cid)}">
      <h2>{esc(e['title'])}<span class="cid">{esc(cid)}</span></h2>
      {meta}
      {clips_block}
      {thumbs_block}
      {copy_blocks}
      <div class="foot">
        <a class="open" href="{board_url}" target="_blank" rel="noopener">📄 個別ページを開く（投稿文コピー・詳細編集）→</a>
        <button data-done="1">投稿済みにする</button>
      </div>
    </article>"""


def render(date: str, entries: list, posts: dict, date_dir) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = "\n".join(
        render_card(e, posts.get(e["cid"], {}), date_dir)
        for e in entries)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(date)} の投稿スケジュール</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{esc(date)} の投稿 <span class="badge">{len(entries)}件</span></h1>
  <p class="lead">この日に投稿する作品をまとめて確認・コピー作業する。
     詳しい画像/動画編集は各作品の個別ページで行う。</p>
  <p class="lead">更新 {now}</p>
</header>
<div class="grid">
{cards}
</div>
<p class="empty" style="display:{'block' if not entries else 'none'}">
   works/{esc(date)}/ に作品がありません。</p>
</div>
<script>{JS}</script>
</body>
</html>
"""


def build_for_date(date: str, cfg: dict):
    """指定した日付フォルダ（works/<date>/）ぶんの dashboard.html を作る。
    対象作品が無くても空のダッシュボードを作る（後で作品を足せるように）。"""
    date_dir = C.WORKS_DIR / date
    entries = [e for e in BB.collect(cfg) if date_dir in e["dir"].parents]
    entries.sort(key=BB.sort_key)

    posts = BB.ensure_posts(entries, regen=False)
    date_dir.mkdir(parents=True, exist_ok=True)
    out = dashboard_path(date)
    out.write_text(render(date, entries, posts, date_dir), encoding="utf-8")
    print(f"✓ {date} のダッシュボードを作りました: {out}（{len(entries)} 作品）")
    return out


def main(argv) -> int:
    cfg = C.load_config(require_api=False)
    flags = set(a for a in argv[1:] if a.startswith("--"))
    positional = [a for a in argv[1:] if not a.startswith("--")]

    if positional:
        date = positional[0]
        if not C.DATE_RE.match(date):
            print(f"✗ 日付は YYYY-MM-DD の形式で指定してください: {date}")
            return 1
        out = build_for_date(date, cfg)
        if "--open" in flags:
            import subprocess
            subprocess.run(["open", str(out)], check=False)
        return 0

    # 日付指定が無ければ、存在する日付フォルダぶん全部を作り直す。
    dates = C.date_dirs()
    if not dates:
        print("works/ に日付フォルダ（YYYY-MM-DD）がありません。"
              "先に fetch_and_build.py で作品を取り込んでください。")
        return 1
    for d in dates:
        build_for_date(d.name, cfg)
    print("  切り抜き・削除を使うには: "
          "python3 fanza_auto/scripts/serve_schedule.py <日付>")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
