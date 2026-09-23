"""一次性：从 pytest 输出里抠 outcome 的 error_detail / stages（用完即删）。"""
import re
import sys
from pathlib import Path

t = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
for key in ("error_code", "error_stage", "error_detail", "stages"):
    for m in re.finditer(re.escape(key) + r"'?: (.{0,900})", t):
        print("###", key, "->", m.group(1).replace("\\n", "\n"))
        print()
        break
