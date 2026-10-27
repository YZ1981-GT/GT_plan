"""生成附注表格标题行库目录 ``backend/data/note_table_header_library.json``。

spec: consol-note-header-library-and-node-reaggregate（Task 4）

用法::

    python backend/scripts/seed/build_note_table_header_library.py           # 生成并打印统计
    python backend/scripts/seed/build_note_table_header_library.py --check   # 只比对，漂移 exit 2

输出确定（无时间戳）：词表 / 种子 / 映射不变时重跑字节不变，``--check`` 才能作门禁。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.note_table_header_catalog import (  # noqa: E402
    CORRESPONDENCE_PATH,
    LIBRARY_PATH,
    build_catalog,
    check_catalog,
    render_catalog,
    render_correspondence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成附注表格标题行库目录")
    parser.add_argument("--check", action="store_true", help="只比对入库目录，有漂移 exit 2")
    args = parser.parse_args(argv)
    if args.check:
        diff = check_catalog()
        if diff:
            print(f"[DRIFT] 库目录与当前词表 / 种子生成结果不一致（重跑本脚本后审 diff 再提交）：")
            for line in diff:
                print("  " + line)
            return 2
        print(f"[OK] {LIBRARY_PATH.name} + {CORRESPONDENCE_PATH.name} 与生成结果一致")
        return 0
    catalog = build_catalog()
    for path, text_fn, label in [
        (LIBRARY_PATH, render_catalog, "主库"),
        (CORRESPONDENCE_PATH, render_correspondence, "对应表"),
    ]:
        text = text_fn(catalog)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        changed = old != text
        if changed:
            path.write_text(text, encoding="utf-8", newline="\n")
        print(("已写入 " if changed else "无变化 ") + f"[{label}] {path}")
    print(json.dumps(catalog["stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
