# -*- coding: utf-8 -*-
"""D4-13/14/15/16 T4「发现→人工认定链」前端守卫变异检验（四态）。

spec: d4-inspection-writeback-formula-io · Task T6
对前端 inspection 组件源文件做**临时**变异（改完立即恢复），每次重跑
d4InspectionWriteback.spec.ts 的 T4 段，观察对应守卫是否打红。

证明 T4 守卫（A13 推送必须人工触发 / 按 diff 过滤而非 reason 非空）真在承重，
不是「字符串存在」式假绿。

3 锚点：
  M1 D4-16 把 A13 推送塞进 debounceSave 自动回调 → 「必须人工触发」守卫必红
  M2 D4-16 过滤条件从 diff!==0 改成 portsReason 非空 → 「reason 非空不构成异常」守卫必红
  M3 D4-15 过滤条件从 isConsistent===false 改成恒 true（推全部）→ 守卫必红

四态：RED（打红且命中预期测试）/ GREEN（守卫缺陷，改坏仍绿）/
      ANCHOR-MISS（锚点未命中源码）/ WRONG-TEST（红了但不是预期项）。

用法（从 backend 目录）：
  python scripts/diagnose/mutate_d4_inspection_t4_guards.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Windows 控制台默认 GBK，本脚本报告含中文 → 强制 stdout/stderr 走 UTF-8（防 print 崩溃）。
try:  # pragma: no cover
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
_REPO = _BACKEND.parent
_FE = _REPO / "audit-platform" / "frontend"
_INSPECT = _FE / "src" / "components" / "workpaper" / "d4" / "inspection"
_SPEC = "src/components/workpaper/__tests__/d4InspectionWriteback.spec.ts"


def _run_test(name_filter: str) -> tuple[bool, str]:
    """跑 vitest 指定用例（-t 名称过滤），返回 (passed, tail)。"""
    proc = subprocess.run(
        ["npx", "vitest", "run", _SPEC, "-t", name_filter],
        cwd=str(_FE), capture_output=True, text=True, shell=True,
        encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0
    tail = [ln for ln in out.strip().splitlines() if ln.strip()][-4:] if out else []
    return passed, " | ".join(tail)


MUTATIONS = [
    {
        "id": "M1_push_in_debounce_auto",
        "file": _INSPECT / "D4TabExport.vue",
        "test": "pushToA13 只在按钮处理函数里调用",
        # 在 debounceSave 回调里注入自动推送（模拟绕过人工确认的自动发布）
        "old": "debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)",
        "new": "debounceTimer = setTimeout(() => { debounceTimer = null; flushSave(); handlePushToA13() }, 2000)",
        "count": 1,
    },
    {
        "id": "M2_filter_by_reason_not_diff",
        "file": _INSPECT / "D4TabExport.vue",
        "test": "portsReason/taxReason 只作描述不构成异常",
        "old": ".filter(r => r.portsDiff !== 0 || r.taxDiff !== 0)",
        "new": ".filter(r => r.portsReason || r.taxReason)",
        "count": 1,
    },
    {
        "id": "M3_d4_15_push_all",
        "file": _INSPECT / "D4TabCompleteness.vue",
        "test": "只推 isConsistent === false",
        "old": ".filter(i => i.isConsistent === false)",
        "new": ".filter(i => true)",
        "count": 1,
    },
]


def main() -> int:
    # 基线：未变异时对应守卫必须全绿
    for mut in MUTATIONS:
        ok, tail = _run_test(mut["test"])
        if not ok:
            print(json.dumps({"baseline": "FAIL", "test": mut["test"], "tail": tail}, ensure_ascii=False))
            return 1

    verdicts = []
    green = 0
    for mut in MUTATIONS:
        target: Path = mut["file"]
        original = target.read_text(encoding="utf-8")
        hit = original.count(mut["old"])
        if hit != mut["count"]:
            verdicts.append({"id": mut["id"], "actual": "ANCHOR-MISS",
                             "detail": f"锚点命中 {hit} 次，期望 {mut['count']}"})
            continue
        mutated = original.replace(mut["old"], mut["new"], mut["count"])
        try:
            target.write_text(mutated, encoding="utf-8")
            passed, tail = _run_test(mut["test"])
        finally:
            target.write_text(original, encoding="utf-8")  # 立即恢复
        actual = "GREEN" if passed else "RED"
        if passed:
            green += 1
        verdicts.append({"id": mut["id"], "test": mut["test"], "actual": actual, "tail": tail})

    report = {
        "verdicts": verdicts,
        "green_count": green,
        "pass": green == 0 and all(v["actual"] == "RED" for v in verdicts),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
