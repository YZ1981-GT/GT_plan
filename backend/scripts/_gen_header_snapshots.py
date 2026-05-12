"""一次性脚本：生成 9 家样本 header 快照 JSON（Sprint 10 Task 10.31）。

用后可删除。运行：
  cd backend; python scripts/_gen_header_snapshots.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本可以作为 __main__ 直接跑
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ledger_import.detector import detect_file_from_path  # noqa: E402
from app.services.ledger_import.identifier import identify  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "数据"
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "header_snapshots.json"

SAMPLES = [
    ("YG36 四川物流", "YG36-重庆医药集团四川物流有限公司2025.xlsx"),
    ("YG4001 宜宾大药房", "YG4001-30重庆医药集团宜宾医药有限公司新健康大药房临港店-余额表+序时账.xlsx"),
    ("和平药房-余额", "和平药房/科目余额表-重庆和平药房连锁有限责任公司2025.xlsx"),
    ("和平物流", "和平物流25加工账-药品批发.xlsx"),
    ("安徽骨科", "余额表+序时账-安徽-骨科.xlsx"),
]


def main() -> int:
    snapshot: dict = {}
    missing: list[str] = []
    for name, rel in SAMPLES:
        p = DATA_DIR / rel
        if not p.exists():
            missing.append(f"{name}: {rel}")
            continue
        fd = detect_file_from_path(str(p), p.name)
        snapshot[name] = {
            "file": rel,
            "sheets": [],
        }
        for s in fd.sheets:
            idf = identify(s)
            snapshot[name]["sheets"].append({
                "sheet_name": s.sheet_name,
                "data_start_row": s.data_start_row,
                "header_cells_first_8": (s.detection_evidence.get("header_cells") or [])[:8],
                "table_type": idf.table_type,
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {len(snapshot)} samples to {OUT}")
    if missing:
        print("Missing files (快照仅含可用样本):")
        for m in missing:
            print(f"  - {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
