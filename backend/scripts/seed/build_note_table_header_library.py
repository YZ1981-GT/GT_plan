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
    LIBRARY_PATH,
    build_catalog,
    check_catalog,
    render_catalog,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成附注表格标题行库目录")
    parser.add_argument("--check", action="store_true", help="只比对入库目录，有漂移 exit 2")
    args = parser.parse_args(argv)
    if args.check:
        diff = check_catalog()
        if diff:
            print(f"[DRIFT] {LIBRARY_PATH.name} 与当前词表 / 种子生成结果不一致（重跑本脚本后审 diff 再提交）：")
            for line in diff:
                print("  " + line)
            return 2
        print(f"[OK] {LIBRARY_PATH.name} 与生成结果一致")
        return 0
    catalog = build_catalog()
    text = render_catalog(catalog)
    old = LIBRARY_PATH.read_text(encoding="utf-8") if LIBRARY_PATH.exists() else None
    if old != text:
        LIBRARY_PATH.write_text(text, encoding="utf-8", newline="\n")
    print(("已写入 " if old != text else "无变化 ") + str(LIBRARY_PATH))
    print(json.dumps(catalog["stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
