"""生成附注表格期间层布局 ``backend/data/note_table_period_layout.json``（spec note-pull-header-formula-closure R4）。

    python backend/scripts/gen/gen_note_table_period_layout.py           # 生成（内容不变则不改文件）
    python backend/scripts/gen/gen_note_table_period_layout.py --check   # 只比对，漂移 exit 2

依据 = 底稿模板 xlsx 的附注披露表与单体模板逐表配对（``note_template_workpaper_alignment.compare_all``）；输出确定（无时间戳），
底稿 / 模板 / 白名单不变时重跑字节不变，``--check`` 才能作门禁。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.note_period_layout import LAYOUT_PATH, build_layout_document, render_layout_document  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成附注表格期间层布局")
    parser.add_argument("--check", action="store_true", help="只比对入库文件，有漂移 exit 2")
    args = parser.parse_args(argv)
    doc = build_layout_document()
    text = render_layout_document(doc)
    old = LAYOUT_PATH.read_text(encoding="utf-8") if LAYOUT_PATH.exists() else ""
    counts = {std: {"sections": len(secs), "entries": sum(len(v) for v in secs.values())}
              for std, secs in doc["layouts"].items()}
    if args.check:
        if old != text:
            print(f"期间层布局与底稿 / 模板不一致，请重跑生成器：{LAYOUT_PATH}")
            return 2
        print("期间层布局一致", json.dumps(counts, ensure_ascii=False))
        return 0
    if old != text:
        LAYOUT_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(("已写入 " if old != text else "无变化 ") + str(LAYOUT_PATH))
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
