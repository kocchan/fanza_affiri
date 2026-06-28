# -*- coding: utf-8 -*-
"""
.claude/skills/*/SKILL.md を走査し、README.md の「使えるスキル」セクション
（<!-- SKILLS:START --> 〜 <!-- SKILLS:END --> の間）を自動生成・更新する。

Stop フック（settings.json）から毎ターン呼ばれる想定。内容に変化が無ければ書き込まない。
スキルが増減すると README が勝手に追従する。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # .claude -> プロジェクトルート
SKILLS = ROOT / ".claude" / "skills"
README = ROOT / "README.md"
START = "<!-- SKILLS:START (自動生成 / .claude/sync_skills_readme.py) -->"
END = "<!-- SKILLS:END -->"


def parse(skill_md: Path):
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm = m.group(1) if m else ""
    def field(key):
        mm = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
        return mm.group(1).strip() if mm else ""
    return field("name"), field("description")


def short(desc: str) -> str:
    desc = desc.strip()
    idx = desc.find("。")           # 最初の一文だけ＝端的に
    if idx != -1:
        return desc[:idx + 1]
    return desc[:80] + ("…" if len(desc) > 80 else "")


def build_list() -> str:
    items = []
    for d in sorted(SKILLS.glob("*/")):
        f = d / "SKILL.md"
        if not f.exists():
            continue
        name, desc = parse(f)
        if name:
            items.append(f"- **/{name}** — {short(desc)}")
    return "\n".join(items) if items else "- （スキルなし）"


def main():
    block = f"{START}\n{build_list()}\n{END}"
    if README.exists():
        text = README.read_text(encoding="utf-8")
        if START in text and END in text:
            new = re.sub(re.escape(START) + r".*?" + re.escape(END), block, text, flags=re.S)
        else:
            new = text.rstrip() + "\n\n## 使えるスキル（/コマンド）\n\n" + block + "\n"
    else:
        new = ("# 324_dmmアフィリエイト（X運用自動化）\n\n"
               "DMM/FANZAアフィリエイトのX運用を支援するプロジェクト。\n\n"
               "## 使えるスキル（/コマンド）\n\n" + block + "\n")
    if not README.exists() or new != README.read_text(encoding="utf-8"):
        README.write_text(new, encoding="utf-8")


try:
    main()
except Exception:
    pass   # フックを止めない（READMEが無くても落とさない）
