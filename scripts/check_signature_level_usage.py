"""静态检查：确保 backend/app/ 下不存在 signature_level 字符串比较的控制流残留。

排除 extension_models.py 中的字段定义行。
若发现 signature_level == 或 signature_level != 用法则 exit 1。
"""

import re
import sys
from pathlib import Path

PATTERN = re.compile(r"signature_level\s*(?:==|!=)")
EXCLUDE_FILE = "extension_models.py"
SEARCH_ROOT = Path(__file__).resolve().parent.parent / "backend" / "app"


def main() -> int:
    violations: list[str] = []

    for py_file in SEARCH_ROOT.rglob("*.py"):
        if py_file.name == EXCLUDE_FILE:
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(content.splitlines(), start=1):
            if PATTERN.search(line):
                rel_path = py_file.relative_to(SEARCH_ROOT.parent.parent)
                violations.append(f"  {rel_path}:{lineno}: {line.strip()}")

    if violations:
        print("ERROR: signature_level 字符串比较残留：")
        for v in violations:
            print(v)
        return 1

    print("OK: 未发现 signature_level 字符串比较控制流残留。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
