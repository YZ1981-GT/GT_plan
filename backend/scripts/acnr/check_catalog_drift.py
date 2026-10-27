"""ACNR Catalog Drift Check — CI 守卫（薄壳，design §5.3）。

与 `generate_catalog.py --check` 同一入口：以已提交版本号重算并结构化比对目录、报告、schema、当前版本快照，
漂移退出 2 并逐条点名 `addr_id: 字段`；对已提交产物跑发布门禁，违规退出 1；一致退出 0。

Requirements: 18.3；本 spec 需求 4.8（D4）
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.acnr.generate_catalog import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["--check"]))
