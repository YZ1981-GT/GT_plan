# -*- coding: utf-8 -*-
"""外部知识源 office 文档增量转 markdown。

用法（仓库根）: .venv/Scripts/python.exe .claude/kb/kb_convert.py [--force]
把 EXTERNAL_DIRS 下的 docx/xlsx/pdf 转为 md 存入 knowledge/external/<目录名>/，
保留相对路径结构；按 (源mtime) 增量跳过，--force 全量重转。zip 及 node_modules 跳过。
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from markitdown import MarkItDown
except ImportError:
    print("错误: .venv 未安装 markitdown（pip install markitdown）", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
OUT_BASE = ROOT / "knowledge" / "external"

# 外部知识源根目录（按需追加，须与 kb_search.py 的 EXTERNAL_DIRS 保持一致）
EXTERNAL_DIRS = [
    r"C:\Users\baiji\Desktop\文件\税务平台",
]

CONVERT_SUFFIXES = {".docx", ".xlsx", ".pdf"}
EXCLUDE_PARTS = {"node_modules", "dist", ".git", ".workbuddy", "build", ".venv"}

# xlsx 多 sheet 输出可能极大，超出则截断（字符）
MAX_OUTPUT_CHARS = 200_000


def convert(force: bool = False) -> int:
    md = MarkItDown()
    ok = skip = fail = 0
    for base in EXTERNAL_DIRS:
        base = Path(base)
        if not base.is_dir():
            print(f"跳过（目录不存在）: {base}")
            continue
        out_dir = OUT_BASE / base.name
        for f in sorted(base.rglob("*")):
            if f.suffix.lower() not in CONVERT_SUFFIXES:
                continue
            if any(part in EXCLUDE_PARTS for part in f.parts):
                continue
            if f.name.startswith("~$"):  # Office 打开时的临时锁文件
                continue
            rel = f.relative_to(base)
            out_file = out_dir / (str(rel) + ".md")
            if not force and out_file.exists() and out_file.stat().st_mtime >= f.stat().st_mtime:
                skip += 1
                continue
            out_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                result = md.convert(str(f))
                text = result.text_content or ""
                if len(text) > MAX_OUTPUT_CHARS:
                    text = text[:MAX_OUTPUT_CHARS] + "\n\n…（超长截断）"
                out_file.write_text(
                    f"---\nsource: {f.resolve()}\n---\n\n{text}", encoding="utf-8"
                )
                ok += 1
                print(f"OK   {rel}")
            except Exception as e:  # 单文件失败不中断批量
                fail += 1
                print(f"FAIL {rel}: {type(e).__name__}: {e}", file=sys.stderr)
    print(f"\n完成: 转换 {ok}，跳过 {skip}，失败 {fail}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(convert(force="--force" in sys.argv))
