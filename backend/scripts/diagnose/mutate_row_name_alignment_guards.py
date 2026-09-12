# -*- coding: utf-8 -*-
"""行名对齐守卫变异检验（四态）。

spec: formula-row-name-alignment-confirmation · Task 13
覆盖锚点（每条必须打红对应守卫）：
  M1 删掉映射查询调用     —— classify 不再读 saved_mapping（当作无映射）→ user_confirmed/ stale 守卫必红
  M2 作用域键漏 wp_code   —— load_active_mappings 的 where 去掉 wp_code → 跨底稿串（存储层守卫必红）
  M3 作用域键漏 year      —— 同上去掉 year
  M4 ambiguous 当 auto    —— classify 归一后多命中判成 auto_matched → Property 1 守卫必红

四态：RED（打红且正是预期测试）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点未命中/命中≠1）/
      WRONG-TEST（打红但非预期项）。GREEN/WRONG/ANCHOR 均视为失败。

用法（仓库根）：
  python backend/scripts/diagnose/mutate_row_name_alignment_guards.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_ALIGN = _REPO / "backend" / "app" / "services" / "four_table" / "row_name_alignment.py"
_STORE = _REPO / "backend" / "app" / "services" / "row_name_mapping_service.py"

_TEST_ALIGN = "backend/tests/four_table/test_row_name_alignment.py"
_TEST_STORE = "backend/tests/four_table/test_row_name_mapping_service.py"


@dataclass
class Mutation:
    mid: str
    target: Path
    old: str
    new: str
    # 预期打红的测试节点（-k 表达式）与文件
    test_file: str
    expect_k: str


MUTATIONS: list[Mutation] = [
    # M1: classify 忽略 saved_mapping（当作从不复用）→ user_confirmed / stale 守卫必红
    Mutation(
        mid="M1_ignore_saved_mapping",
        target=_ALIGN,
        old="    if saved_mapping is not None and saved_mapping.targets:",
        new="    if False and saved_mapping is not None and saved_mapping.targets:",
        test_file=_TEST_ALIGN,
        expect_k="saved_mapping_valid or saved_mapping_stale",
    ),
    # M2: load_active_mappings 漏 wp_code 作用域键 → 跨底稿串（存储守卫必红）
    Mutation(
        mid="M2_scope_missing_wp_code",
        target=_STORE,
        old="                WorkpaperRowNameMapping.wp_code == scope.wp_code,\n                WorkpaperRowNameMapping.sheet_code == scope.sheet_code,\n                WorkpaperRowNameMapping.is_active.is_(True),\n            )\n        )\n        rows = (await self.db.execute(stmt)).scalars().all()",
        new="                WorkpaperRowNameMapping.sheet_code == scope.sheet_code,\n                WorkpaperRowNameMapping.is_active.is_(True),\n            )\n        )\n        rows = (await self.db.execute(stmt)).scalars().all()",
        test_file=_TEST_STORE,
        expect_k="scope_isolation_wp_code",
    ),
    # M3: _load_active_rows 漏 year → 版本冲突检测/覆盖逻辑读错基线（存储守卫必红）
    Mutation(
        mid="M3_scope_missing_year",
        target=_STORE,
        old="        stmt = sa.select(WorkpaperRowNameMapping).where(\n            WorkpaperRowNameMapping.project_id == scope.project_id,\n            WorkpaperRowNameMapping.year == scope.year,\n            WorkpaperRowNameMapping.wp_code == scope.wp_code,\n            WorkpaperRowNameMapping.sheet_code == scope.sheet_code,\n            WorkpaperRowNameMapping.is_active.is_(True),\n        )\n        return list((await self.db.execute(stmt)).scalars().all())",
        new="        stmt = sa.select(WorkpaperRowNameMapping).where(\n            WorkpaperRowNameMapping.project_id == scope.project_id,\n            WorkpaperRowNameMapping.wp_code == scope.wp_code,\n            WorkpaperRowNameMapping.sheet_code == scope.sheet_code,\n            WorkpaperRowNameMapping.is_active.is_(True),\n        )\n        return list((await self.db.execute(stmt)).scalars().all())",
        test_file=_TEST_STORE,
        expect_k="confirm_baseline_isolated_by_year",
    ),
    # M4: classify 归一后多命中判成 auto_matched（丢掉 ambiguous 保护）→ Property 1 守卫必红
    Mutation(
        mid="M4_ambiguous_as_auto",
        target=_ALIGN,
        old="    if len(exact) > 1:\n        # 归一后多命中 → 必须人工确认\n        return ClassifyResult(\n            state=MatchState.AMBIGUOUS,\n            matched_targets=tuple(c.target for c in exact),\n        )",
        new="    if len(exact) > 1:\n        # MUTATED: 错误地当精确命中\n        return ClassifyResult(\n            state=MatchState.AUTO_MATCHED,\n            matched_targets=tuple(c.target for c in exact),\n        )",
        test_file=_TEST_ALIGN,
        expect_k="normalized_multi_hit",
    ),
]


def _run_pytest(test_file: str, expr: str) -> tuple[bool, str]:
    """跑指定测试节点。返回 (passed, tail)。passed=True 表示全过。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-k", expr, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0
    tail = "\n".join(out.strip().splitlines()[-6:])
    return passed, tail


def _verify_baseline() -> list[str]:
    fails = []
    for tf in (_TEST_ALIGN, _TEST_STORE):
        ok, tail = _run_pytest(tf, "")
        if not ok:
            fails.append(f"{tf}: {tail}")
    return fails


def main() -> int:
    # 基线：未变异时守卫必须全绿
    baseline_fails = _verify_baseline()
    if baseline_fails:
        print(json.dumps({"baseline": "FAIL", "detail": baseline_fails}, ensure_ascii=False, indent=2))
        return 1

    verdicts = []
    for m in MUTATIONS:
        src = m.target.read_text(encoding="utf-8")
        count = src.count(m.old)
        if count != 1:
            verdicts.append({"id": m.mid, "actual": "ANCHOR-MISS",
                             "detail": f"anchor count={count} (need 1)"})
            continue
        mutated = src.replace(m.old, m.new, 1)
        try:
            m.target.write_text(mutated, encoding="utf-8")
            # 目标测试节点：变异后应当 FAIL（打红）
            passed, tail = _run_pytest(m.test_file, m.expect_k)
        finally:
            m.target.write_text(src, encoding="utf-8")  # 字节复原

        if passed:
            actual = "GREEN"  # 变异后仍全过 = 守卫缺陷
            detail = "guard still green after mutation — defective"
        else:
            # 确认失败项确实命中预期测试（-k 已限定，非全表 fail）
            actual = "RED" if "failed" in tail.lower() or "error" in tail.lower() else "WRONG-TEST"
            detail = tail
        verdicts.append({"id": m.mid, "expect_k": m.expect_k, "actual": actual, "detail": detail})

    ok = all(v["actual"] == "RED" for v in verdicts)
    report = {
        "spec": "formula-row-name-alignment-confirmation",
        "task": 13,
        "baseline": "PASS",
        "verdicts": verdicts,
        "pass": ok,
    }
    out_path = (
        _REPO / ".kiro" / "specs" / "formula-row-name-alignment-confirmation"
        / "evidence" / "T13-mutation-verdict.json"
    )
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
