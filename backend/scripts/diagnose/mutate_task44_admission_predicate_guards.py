"""变异检验：把 Task 44 准入判据的两条缺陷逐条改回去，确认守卫必红。

四态：RED（打红）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点未命中或命中多处）。
每次变异后校验源文件干净还原。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]  # backend/scripts/diagnose/ -> 仓库根
_CHECK_DIR = ROOT / "backend" / "scripts" / "check"
GATE = _CHECK_DIR / "check_task44_oo94_excel_pilot_gate.py"
#: 请求路径探针的真实实现（宿主只留薄转发，判据真源在这里）。
PROBE = _CHECK_DIR / "_task44_request_path_probe.py"
SPEC = "backend/tests/workpaper_sync/test_task44_admission_predicate.py"

#: `(说明, 目标文件, 原文, 变异文)`
MUTATIONS: list[tuple[str, Path, str, str]] = [
    (
        "M01 准入退回用「无 session 的 registry 快照」（缺陷 ①）",
        GATE,
        "            and self.adapter_registered_on_request_path is True\n",
        "            and self.adapter_registered\n",
    ),
    (
        "M02 拒绝不变量方向反转（缺陷 ②）",
        GATE,
        "        return self.attach_without_representation == ()",
        "        return bool(self.attach_without_representation)",
    ),
    (
        "M03 请求路径探针改成只读 registry 快照（不调 register_from_manifest）",
        PROBE,
        "                outcome = await reg.register_from_manifest(session=session)\n"
        "                return tuple(sorted(outcome.registered_adapter_ids))",
        "                return tuple(sorted(r.adapter_id for r in reg.registrations()))",
    ),
    (
        "M04 真库不可达时记成「没注册」而不是 unverifiable",
        PROBE,
        '        return None, f"真库不可达或注册路径抛错：{type(exc).__name__}: {exc}"[:300]',
        '        return (), f"真库不可达或注册路径抛错：{type(exc).__name__}: {exc}"[:300]',
    ),
    (
        "M05 探针丢掉 NullPool（回到共享池 ⇒ 假 ERROR 态）",
        PROBE,
        "        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)",
        "        engine = create_async_engine(settings.DATABASE_URL)",
    ),
    (
        "M06 信号不再把请求路径结果填进去（additive 死代码）",
        GATE,
        "        request_path_registered_adapter_ids=request_ids,\n",
        "",
    ),
    (
        "M07 自检退回 `real != substituted`（预设真实态为 False）",
        GATE,
        "        flipped = substituted.admitted is True and starved.admitted is False",
        "        flipped = real.admitted != substituted.admitted",
    ),
    (
        "M08 删掉伴生模块的委派（宿主薄转发失去真源）",
        GATE,
        "    from _task44_request_path_probe import probe_request_path_registration\n\n"
        "    return probe_request_path_registration()",
        "    return None, '未实现'",
    ),
]


def run_spec() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SPEC, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    return proc.returncode == 0


print("=== 基线 ===")
if not run_spec():
    print("❌ 基线不绿")
    sys.exit(1)
print("  baseline PASS")

verdicts: dict[str, str] = {}
for name, target, old, new in MUTATIONS:
    original = target.read_text(encoding="utf-8")
    hits = original.count(old)
    if hits != 1:
        verdicts[name] = f"ANCHOR-MISS({hits})"
        print(f"  {verdicts[name]:20s} {name}")
        continue
    try:
        target.write_text(original.replace(old, new), encoding="utf-8")
        verdicts[name] = "GREEN(缺陷!)" if run_spec() else "RED"
    finally:
        target.write_text(original, encoding="utf-8")
        assert target.read_text(encoding="utf-8") == original, f"{target.name} 未干净还原"
    print(f"  {verdicts[name]:20s} {name}")

print()
reds = sum(1 for v in verdicts.values() if v == "RED")
print(f"RED={reds} / {len(MUTATIONS)}")
bad = {k: v for k, v in verdicts.items() if v != "RED"}
if bad:
    for k, v in bad.items():
        print(f"  {v}  {k}")
    sys.exit(1)
print("✅ 全部 RED")
