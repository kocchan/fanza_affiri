# -*- coding: utf-8 -*-
"""
MyFansの投稿URL → works/ 直下への取り込みツール。

2段構えで情報を集める:

  ① requests で投稿ページの公開OGPメタタグ（og:title/description/image）を読む。
     ログイン不要・軽量。ここで post_id・サムネ画像URL・アフィリンク解決ができる。
  ② Playwrightで実際にページを開き（年齢確認「はい」を1回クリックするだけ・ログインはしない）、
     本文全文（og:descriptionは短く切られているため、DOM上の実テキストを直接読む）と、
     無料公開されているサンプル動画（HLS配信のm3u8 URL）を取る。取れたら ffmpeg で
     sample.mp4 として保存する。②が何らかの理由で失敗しても①の結果だけで取り込みを続行する
     （壊れやすい部分を落としても全体は動くようにする）。

  ★ここで自動化しているのは「年齢確認への同意クリック」だけ（誰でも通す標準的な導線で
    ボット対策ではない）。ログイン画面のCloudflare Turnstileは自動化ブラウザを検知して
    失敗することを確認済みなので、ログインが要る情報（購入後の本編動画等）は取りに行かない。
    取得するサンプル動画はログイン・購入なしで誰でも見られる公開プレビューのみ。

貼るURLは**自分がMyFansで発行したアフィリンク**（例:
`https://link.affiliate.myfans.jp/r/<コード>`）にすること。素のURLだと
成果計測されない。取り込みはURLをそのまま `item.json` の `affiliateURL` に
保存するだけで、検証はしない。

使い方:
    python3 myfans_auto/scripts/myfans_fetch.py <MyFansの投稿URL>
    python3 myfans_auto/scripts/myfans_fetch.py <URL> --description <本文>   # 本文を手動指定（任意・上書き）
"""

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests

import common as C

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA}
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

_META_TAG_RE = re.compile(r"<meta\b([^>]*)>", re.I)
_ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')

_FS_BAD = re.compile(r'[\\/:*?"<>|\s（）()\[\]【】「」『』、。!！?？~〜・…]+')


def is_myfans_url(token: str) -> bool:
    return "myfans.jp" in (token or "")


def safe_folder_part(title: str, limit: int = 20) -> str:
    """作品名をフォルダ名向けに短く・安全化する（fetch_and_build.py と同じ方針）。"""
    cleaned = _FS_BAD.sub("", title or "").strip()
    return (cleaned[:limit] or "投稿")


def parse_meta(page_html: str) -> dict:
    """<meta property="og:xxx" content="..."> を属性の並び順に関係なく拾う。"""
    metas = {}
    for tag in _META_TAG_RE.findall(page_html):
        attrs = dict(_ATTR_RE.findall(tag))
        key = attrs.get("property") or attrs.get("name")
        if key and "content" in attrs:
            metas[key] = html.unescape(attrs["content"])
    return metas


def extract_post_id(url: str) -> str:
    m = re.search(r"/posts/([0-9a-fA-F-]{8,})", url)
    if m:
        return m.group(1)
    # フォールバック：クエリの post_id=
    from urllib.parse import parse_qs
    q = parse_qs(urlsplit(url).query)
    if q.get("post_id"):
        return q["post_id"][0]
    return ""


def extract_creator(og_title: str) -> str:
    # 例: "…本文… | モカさんのプライベートSNS | myfans(マイファンズ)"
    m = re.search(r"\|\s*(.+?)さんの.*?SNS\s*\|", og_title or "")
    return m.group(1).strip() if m else ""


def clean_title(og_title: str) -> str:
    # サイト側のサフィックス（" | ◯◯さんの… | myfans(マイファンズ)"）を落として本文だけにする。
    head = (og_title or "").split(" | ")[0].strip()
    return head or (og_title or "").strip() or "(no title)"


def fetch_post(token: str):
    """MyFansの投稿ページを取得し、(post_id, meta, resolved_url) を返す（軽量・requestsのみ）。
    取得できない/投稿ページでない場合は例外を投げる。"""
    r = requests.get(token, headers=HEADERS, timeout=30, allow_redirects=True)
    r.raise_for_status()
    resolved_url = r.url
    if "myfans.jp" not in urlsplit(resolved_url).netloc:
        raise ValueError(f"MyFansのページに解決できませんでした（→ {resolved_url}）")
    post_id = extract_post_id(resolved_url)
    if not post_id:
        raise ValueError(f"投稿IDが取れませんでした（URL: {resolved_url}）")
    metas = parse_meta(r.text)
    if not metas.get("og:title"):
        raise ValueError("投稿情報（og:title）が取れませんでした。"
                         "非公開/削除された投稿の可能性があります。")
    return post_id, metas, resolved_url


def fetch_full_details(url: str, title_prefix: str, timeout_ms: int = 30000):
    """実ブラウザでページを開き、本文全文とサンプル動画のm3u8 URLを取る。
    年齢確認の「はい」だけクリックする（ログインはしない）。
    何らかの理由で失敗しても例外は投げず (None, None) を返す
    （呼び出し側はog:descriptionのみ・動画無しにフォールバックする）。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ・playwright未導入のため本文全文/サンプル動画の自動取得はスキップ"
              "（`pip3 install --break-system-packages playwright && "
              "python3 -m playwright install chromium`）")
        return None, None

    m3u8_urls = []

    def on_response(resp):
        if ".m3u8" in resp.url and resp.url not in m3u8_urls:
            m3u8_urls.append(resp.url)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(locale="ja-JP", user_agent=UA)
                page.on("response", on_response)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(2500)
                # 年齢確認（誰でも通す標準的な導線。既読み等で出ない場合はそのまま続行）
                try:
                    page.get_by_text("はい", exact=True).first.click(timeout=5000)
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                # サンプル動画プレーヤーをクリックすると再生準備が始まりm3u8が要求される
                try:
                    page.locator("video").first.click(timeout=4000)
                except Exception:
                    pass
                page.wait_for_timeout(2500)

                description = None
                if title_prefix:
                    description = page.evaluate(
                        """(prefix) => {
                          let best = '';
                          document.querySelectorAll('body *').forEach(el => {
                            if (el.children.length === 0) {
                              const t = (el.textContent||'').trim();
                              if (t.startsWith(prefix) && t.length > best.length) best = t;
                            }
                          });
                          return best || null;
                        }""", title_prefix)
                video_url = m3u8_urls[0] if m3u8_urls else None
                return description, video_url
            finally:
                browser.close()
    except Exception as e:
        print(f"  ・本文全文/サンプル動画の自動取得に失敗（タイトル/サムネのみで続行）: {e}")
        return None, None


def existing_post_ids(works_dir: Path) -> set:
    have = set()
    for d in C.work_dirs(works_dir):
        item = C.read_item(d)
        pid = item.get("content_id") or C.cid_of(d)
        if pid:
            have.add(pid)
    return have


def download_image(url: str, dest: Path) -> bool:
    if not url:
        return False
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"  ! サムネ画像DL失敗: {url} ({e})")
        return False


def download_sample_video(m3u8_url: str, dest: Path) -> bool:
    """無料公開されているサンプル動画（HLS）をffmpegでmp4として保存する。
    配信元CDNはブラウザらしいUser-Agent/Refererが無いと403を返すため明示的に渡す。"""
    if not m3u8_url:
        return False
    cmd = [
        FFMPEG, "-y",
        "-user_agent", UA,
        "-headers", "Referer: https://myfans.jp/\r\n",
        "-i", m3u8_url,
        "-c", "copy",
        str(dest),
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, timeout=120)
        if r.returncode != 0 or not dest.is_file():
            print(f"  ! サンプル動画DL失敗: {(r.stdout or '')[-300:]}")
            return False
        return True
    except Exception as e:
        print(f"  ! サンプル動画DL失敗: {e}")
        return False


def build_post_content(title: str, creator: str, token: str, description: str,
                       has_video: bool) -> str:
    lines = [
        f"# {title}",
        "",
        "サイト: MyFans",
    ]
    if creator:
        lines.append(f"投稿者: {creator}さん")
    lines += [
        f"リンク: {token}",
        "",
    ]
    if description:
        lines += ["## 本文", "", description, ""]
    if has_video:
        lines += ["> ✓ サンプル動画（無料公開プレビュー）を sample.mp4 として自動取得済み。", ""]
    else:
        lines += [
            "> ⚠️ サンプル動画は自動取得できませんでした。動画を切り抜きたいときは、",
            "> このフォルダに手動で `sample.mp4` という名前で動画ファイルを置いてください。",
            "",
        ]
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # --description <本文> … 自動取得（Playwrightでの本文抽出）が失敗したときの手動上書き用。
    manual_description = ""
    if "--description" in argv:
        i = argv.index("--description")
        if i + 1 < len(argv):
            manual_description = argv[i + 1]
            del argv[i:i + 2]
        else:
            del argv[i]

    tokens = [a for a in argv if not a.startswith("-")]
    if not tokens:
        print("使い方: python3 myfans_auto/scripts/myfans_fetch.py <MyFansの投稿URL> "
              "[--description <本文>]")
        return 1
    token = tokens[0].strip()
    if not is_myfans_url(token):
        print(f"✗ MyFansのURLではありません: {token}")
        return 1

    works_dir = C.WORKS_DIR
    works_dir.mkdir(parents=True, exist_ok=True)

    print(f"▶ MyFans取り込み: {token}")
    try:
        post_id, metas, resolved_url = fetch_post(token)
    except Exception as e:
        print(f"✗ 取得に失敗しました: {e}")
        return 1

    if post_id in existing_post_ids(works_dir):
        print(f"  ・{post_id} は既に works/ にあります（スキップ）。")
        return 0

    og_title = metas.get("og:title", "")
    short_title = clean_title(og_title)
    creator = extract_creator(og_title)
    image_url = metas.get("og:image", "")

    print("  ⏳ 本文全文とサンプル動画を確認中…（実ブラウザで開くので数秒〜十数秒かかります）")
    full_description, video_m3u8 = fetch_full_details(resolved_url, short_title[:12])

    description = manual_description.strip() or full_description or metas.get("og:description", "")
    # タイトルは本文全文の1行目（＝見出し）が取れればそちらを使う。og:titleは"..."で切られている。
    first_line = (full_description or "").split("\n")[0].strip()
    title = first_line or short_title

    folder = works_dir / f"{post_id}_{safe_folder_part(title)}"
    folder.mkdir(parents=True, exist_ok=True)

    item = {
        "content_id": post_id,
        "title": title,
        "creator": creator,
        "description": description,
        "affiliateURL": token,
        "URL": resolved_url,
        "date": "",
        "review": {},
        "iteminfo": {"genre": [], "maker": []},
        "volume": "",
        "archived": False,
    }
    C.write_item(folder, item)

    n_images = 0
    if download_image(image_url, folder / "01.jpg"):
        n_images = 1

    has_video = download_sample_video(video_m3u8, folder / "sample.mp4")

    (folder / C.POST_MD).write_text(
        build_post_content(title, creator, token, description, has_video),
        encoding="utf-8")

    print(f"  ✓ {folder.name}/ … 画像{n_images}枚（サムネ）"
          + ("+ sample.mp4（サンプル動画）" if has_video else "")
          + f" + {C.POST_MD}")
    print(f"\n✓ 完成: MyFans作品を追加 → {folder}")
    print(f"\n  全体ボード: python3 {C.ROOT / 'scripts' / 'serve.py'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
