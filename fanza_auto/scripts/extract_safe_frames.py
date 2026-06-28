# -*- coding: utf-8 -*-
"""
サンプル動画から「エロいが X の規制に引っかかりにくい」フレームを抽出する。

判定の考え方（X運用ナレッジ_アダルト規制.md に準拠）:
  - X の Adult/Explicit ランク（全裸・性器・露骨）はおすすめ欄/検索から除外される。
    → 集客メイン投稿には不向き。これらが写るフレームは【除外】。
  - Sensitive ランク（着衣・部分露出・チラ見せ・表情）はリーチが残る。
    → これら "示唆的だが露骨でない" フレームを【採用候補】にする。

技術:
  - cv2 で動画を一定間隔サンプリング
  - nudenet(NudeDetector) で各フレームの露出部位を検出
  - 露骨部位が写るフレームを弾き、示唆的フレームをスコア順に保存

⚠️ 重要（自動判定の限界）:
  nudenet は「年齢」を判定できない。Xのゼロトレランス＝未成年に見える/制服強調は
  別途【人間が目視で必ず除外】すること。出力はあくまで一次フィルタ。
"""

import sys
from pathlib import Path

import cv2
from nudenet import NudeDetector

# 判定基準は safe_criteria に集約（= ナレッジ_アダルト規制.md のコード版）。
from safe_criteria import score_frame as _score_frame


def extract_safe_frames(video_path, out_dir, top_n=6,
                        max_samples=40, detector=None, verbose=True,
                        strict=False):
    """動画から規制セーフな示唆的フレームを top_n 枚保存。保存パスのリストを返す。
    strict=True で「下着・谷間・尻も避ける」立ち上げモード。"""
    video_path = Path(video_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    detector = detector or NudeDetector()

    cap = cv2.VideoCapture(str(video_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    if total <= 0:
        if verbose:
            print(f"  ! 動画を読めません: {video_path}")
        return []

    # 冒頭/末尾の暗転を避け、5%〜95%区間を等間隔サンプリング
    start, end = int(total * 0.05), int(total * 0.95)
    step = max(1, (end - start) // max_samples)
    tmp = out_dir / "_tmp.jpg"

    candidates = []  # (score, sec, reasons, image)
    for fno in range(start, end, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fno)
        ok, frame = cap.read()
        if not ok:
            continue
        cv2.imwrite(str(tmp), frame)
        dets = detector.detect(str(tmp))
        safe, score, reasons = _score_frame(dets, strict=strict)
        if safe and score > 0:
            candidates.append((score, fno / fps, reasons, frame.copy()))
    cap.release()
    if tmp.exists():
        tmp.unlink()

    candidates.sort(key=lambda x: x[0], reverse=True)
    saved = []
    for i, (score, sec, reasons, frame) in enumerate(candidates[:top_n]):
        name = f"safe_{i+1:02d}_{int(sec)}s.jpg"
        cv2.imwrite(str(out_dir / name), frame)
        saved.append(out_dir / name)
        if verbose:
            print(f"    ✓ {name} (score={score:.2f}, {','.join(reasons)})")
    if verbose:
        print(f"  ✓ セーフ候補 {len(saved)}枚 / 検査 {len(candidates)}枚採用 "
              f"({video_path.name})")
    return saved


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使い方: python3 extract_safe_frames.py <動画.mp4> [出力先]")
        sys.exit(1)
    video = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else str(Path(video).parent / "safe_frames")
    extract_safe_frames(video, out)
