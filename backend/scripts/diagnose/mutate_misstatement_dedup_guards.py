# -*- coding: utf-8 -*-
"""V164 / B3 未更正错报 durable 幂等守卫变异检验（四态）。

对 misstatement_service.py 的 create_misstatement 幂等逻辑做临时变异（改完立即恢复），
每次重跑 test_misstatement_source_identity_dedup.py，观察守卫是否打红。

3 锚点：
  M1 pre-check 恒不命中（existing 强制 None）→ dedup 失效 → test_same_source_identity_* 必红
  M2 命中既有记录后不返回、继续插入（删 return resp 分支的 return）→ 必红
  M3 identity 传空给 row（source_identity=None）→ 库里无 identity → 跨调用不去重 → 必红

四态：RED（预期打红）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点未命中/命中≠预期次数）/ WRONG-TEST。
用法（从 backend 目录）：python scripts/diagnose/mutate_misstatement_dedup_guards.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
_TARGET = _BACKEND / "app" / "services" / "misstatement_service.py"
_TESTFILE = "tests/test_misstatement_source_identity_dedup.py"


def _run(node: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", f"{_TESTFILE}::{node}", "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(_BACKEND), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-2:]
    return proc.returncode == 0, " | ".join(tail)


MUTATIONS = [
    {
        "id": "M1_precheck_never_hits",
        "node": "test_same_source_identity_dedups_across_calls",
        # 用 create_misstatement 独有上下文锚定（create_from_rejected_aje 也有同名局部变量）
        "old": "            existing = (await self.db.execute(existing_q)).scalar_one_or_none()\n            if existing is not None:\n                resp = self._to_response(existing)",
        "new": "            existing = None  # MUTATION\n            if existing is not None:\n                resp = self._to_response(existing)",
        "count": 1,
    },
    {
        "id": "M2_hit_but_not_return",
        "node": "test_same_source_identity_dedups_across_calls",
        # 命中既有后应 return；把 resp.deduplicated=True 后的 return 去掉 → 继续插入
        "old": "                resp.deduplicated = True\n                return resp\n\n        row = UnadjustedMisstatement(",
        "new": "                resp.deduplicated = True\n                # MUTATION: return removed\n\n        row = UnadjustedMisstatement(",
        "count": 1,
    },
    {
        "id": "M3_identity_not_persisted",
        "node": "test_same_source_identity_dedups_across_calls",
        "old": "            source_identity=source_identity,\n            created_by=created_by,",
        "new": "            source_identity=None,  # MUTATION\n            created_by=created_by,",
        "count": 1,
    },
]


def main() -> int:
    original = _TARGET.read_text(encoding="utf-8")
    for mut in MUTATIONS:
        ok, tail = _run(mut["node"])
        if not ok:
            print(json.dumps({"baseline": "FAIL", "node": mut["node"], "tail": tail}, ensure_ascii=False))
            return 1
    verdicts = []
    green = 0
    for mut in MUTATIONS:
        hit = original.count(mut["old"])
        if hit != mut["count"]:
            verdicts.append({"id": mut["id"], "actual": "ANCHOR-MISS", "detail": f"命中 {hit} 期望 {mut['count']}"})
            continue
        mutated = original.replace(mut["old"], mut["new"], mut["count"])
        try:
            _TARGET.write_text(mutated, encoding="utf-8")
            passed, tail = _run(mut["node"])
        finally:
            _TARGET.write_text(original, encoding="utf-8")
        actual = "GREEN" if passed else "RED"
        if passed:
            green += 1
        verdicts.append({"id": mut["id"], "node": mut["node"], "actual": actual, "tail": tail})
    restored = _TARGET.read_text(encoding="utf-8") == original
    report = {"verdicts": verdicts, "green_count": green, "restored_ok": restored,
              "pass": green == 0 and all(v["actual"] == "RED" for v in verdicts) and restored}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
