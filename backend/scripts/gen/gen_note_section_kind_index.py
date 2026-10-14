"""从四版本 Word 附注模板生成章节类型索引 ``backend/data/note_section_kind_index.json``。

用法（仓库根执行）：
    python backend/scripts/gen/gen_note_section_kind_index.py          # 写入（内容未变则不改文件）
    python backend/scripts/gen/gen_note_section_kind_index.py --check  # 只比对，漂移 exit 2 并点名

Word 模板更新后必须重跑本脚本；守卫 ``test_note_section_kind`` 会校验索引与 Word 同步。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.services.note_section_kind import KIND_INDEX_PATH, build_kind_index_from_word  # noqa: E402


def render() -> str:
    return json.dumps(build_kind_index_from_word(), ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成附注章节类型索引（Word 权威）")
    parser.add_argument("--check", action="store_true", help="只比对，不写文件；漂移时 exit 2")
    args = parser.parse_args()
    expected = render()
    current = KIND_INDEX_PATH.read_text(encoding="utf-8") if KIND_INDEX_PATH.exists() else ""
    if args.check:
        if current != expected:
            print(f"[DRIFT] {KIND_INDEX_PATH.name} 与 Word 模板不同步，请重跑生成脚本")
            return 2
        print(f"[OK] {KIND_INDEX_PATH.name} 与 Word 模板同步")
        return 0
    if current == expected:
        print(f"(无变化) {KIND_INDEX_PATH.name}")
        return 0
    KIND_INDEX_PATH.write_text(expected, encoding="utf-8")
    print(f"[written] {KIND_INDEX_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
