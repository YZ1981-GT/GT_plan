#!/usr/bin/env python
"""落盘 G-HANDOFF-CONSUMER evidence（Task 16）。

evidence 由 ``build_ghandoff_consumer_evidence_payload()`` 单源构造，写到
``backend/data/guidance/contracts/ghandoff/evidence/ghandoff_consumer_evidence.json``，
供 custom spec X11 消费。module sha256 会随实现变化——evidence 是当前实现的
指纹，不是手写常量。

用法：
    python backend/scripts/fix/emit_ghandoff_consumer_evidence.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]  # backend/scripts/fix -> backend
ROOT = BACKEND.parent  # repo root
sys.path.insert(0, str(BACKEND))

from app.services.guidance_handoff_consumer_service import (  # noqa: E402
    build_ghandoff_consumer_evidence_payload,
)


def main() -> int:
    payload = build_ghandoff_consumer_evidence_payload()
    out_dir = ROOT / "backend" / "data" / "guidance" / "contracts" / "ghandoff" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "ghandoff_consumer_evidence.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] wrote {out_path.relative_to(ROOT)} (module sha256={payload['sourceDigests']['module'][:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
