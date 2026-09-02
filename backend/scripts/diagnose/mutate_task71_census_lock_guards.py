# -*- coding: utf-8 -*-
"""任务 71 门 —— census 普查免疫判据的变异检验。

拆分自 `mutate_task71_chaos_guards.py`（原 948 行 > pre-commit 行数门禁 whitelist 基线
878 + 5% = 921）。拆分同时修掉一个**真缺陷**：那 7 条 census 变异被追加时复用了已占用的
变异号（`M57` / `M59` / `M60` 各出现两次）。宿主 `run()` 的 `verdicts` 是按 mid 的字典 ⇒
后者覆盖前者，一条结果被静默吞掉、收尾的「RED n/n」计数失真 —— 那本身就是一条假绿通道。
拆成独立脚本后本文件有自己的编号命名空间（M01~M07），重号消失。

判据本体**原样搬移**（scope / 锚点 / 替换 / why 一字未改），只改两处必须改的：
① 变异号重编；② 其中 5 条的 `want` 从 `TestGuardPlacement::` 改为 `TestCensusLock::` ——
那三条判据已随守卫拆分移入 `backend/tests/workpaper_sync_chaos/test_task71_census_lock.py`。
另 2 条（`upstream_lock_impact` 的现算判定）要打红的判据**仍在宿主守卫里**，因此本组的
pytest target 是**两个**文件，缺一条都会让那 2 条变成 WRONG-TEST。

runner 复用宿主的（`locate` / `classify` / `run` / `check_anchors` / `run_pytest`），不抄第二份 ——
抄一份 runner 意味着两个文件对「四态怎么判」可能分叉，而四态判定正是本 spec 最贵的判据之一。
宿主为此加了两个**向后兼容**的可选参数（`mutations` / `targets`），默认值即原行为。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task71_census_lock_guards.py --list
    python backend/scripts/diagnose/mutate_task71_census_lock_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task71_census_lock_guards.py --run all
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Final

_HOST_PATH = Path(__file__).with_name("mutate_task71_chaos_guards.py")
_spec = importlib.util.spec_from_file_location("_task71_mutation_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

Mutation = _host.Mutation
CENSUS_LOCK_REL = "backend/scripts/_census_lock.py"
GATE_REL = _host.GATE_REL

#: 本组变异要打红的守卫文件。**两个**：5 条落在拆分出来的 census 守卫上，2 条仍落在宿主的
#: chaos 守卫上（`test_upstream_lock_impact_is_measured_and_owned` 没有随拆分移走）。
TARGETS: Final[tuple[str, ...]] = (
    "backend/tests/workpaper_sync_chaos/test_task71_census_lock.py",
    _host.GUARD_TEST,
)

MUTATIONS: Final[tuple[Mutation, ...]] = (
    Mutation(
        "M01",
        GATE_REL,
        "strip_census",
        "            if child in CENSUS_KEYS:",
        "            if False:  # mutated: 不再剔除普查派生量",
        "TestCensusLock::test_census_derived_quantities_are_excluded_from_the_byte_lock",
        "🔴 `strip_census` 不再剔除任何东西 ⇒ 自有辐射面全树计数与**转记的**上游 live 值重新"
        "进锁，回到 BP-71-8：仓库任意位置新增一个 `test_*.py` 都打红本门",
    ),
    Mutation(
        "M02",
        GATE_REL,
        "CENSUS_KEYS",
        '        "upstream_lock_impact.task70_scanned_test_files_live",',
        '        "upstream_lock_impact.task70_scanned_test_files_live_MUTATED",',
        "TestCensusLock::test_census_derived_quantities_are_excluded_from_the_byte_lock",
        "把**转记的上游全树计数**从 census 名单里改名剔走 —— 这正是传递形态的根因字段："
        "上游把普查量冻进锁，本门又把上游的 live 值冻进自己的锁",
    ),
    Mutation(
        "M03",
        GATE_REL,
        "CENSUS_KEYS",
        '        "census_contract.measured",',
        '        "census_contract.measured",\n        "upstream_lock_impact.task70_surface_projection_agrees",',
        "TestCensusLock::test_census_derived_quantities_are_excluded_from_the_byte_lock",
        "把对上游的**判定**也剔进 census ⇒ 剔多了。那三条判定才是本门对上游那把锁的真判据，"
        "不进锁就等于没有判据",
    ),
    Mutation(
        "M04",
        GATE_REL,
        "census_semantics",
        '        "all_hold": all(checks.values()),',
        '        "all_hold": True,  # mutated: 语义断言恒真',
        "TestCensusLock::test_census_semantics_are_asserted_not_merely_skipped",
        "把普查语义断言改成恒真 —— 「剔除 ≠ 不管」退化成「不看了」",
    ),
    Mutation(
        "M05",
        CENSUS_LOCK_REL,
        "coverage_from_members",
        "        str(name): any(str(name) in (why or ()) for why in members.values())",
        "        str(name): True  # mutated: 覆盖布尔恒真",
        "TestCensusLock::test_coverage_boolean_is_derived_not_hardcoded",
        "🔴 逐 pattern 覆盖布尔恒真。注意它**与记录相等**（记录里今天也全是 True），"
        "所以只有「从同一份成员清单重算」这条判据能抓到 —— 等值比对在这里天生不敏感",
    ),
    Mutation(
        "M06",
        GATE_REL,
        "upstream_lock_impact",
        '    projection_agrees = strip({"radiation_surface": live}) == strip({"radiation_surface": disk})',
        "    projection_agrees = True  # mutated: 不再现算上游投影是否一致",
        "TestCensusLock::test_projection_agreement_is_really_computed",
        "本门对上游那把锁的核心判定被写成恒真 ⇒ 上游普查免疫被回退时本门也不会红",
    ),
    Mutation(
        "M07",
        GATE_REL,
        "upstream_lock_impact",
        "    if strip is None or not census_keys:",
        "    if False:  # mutated: 上游没有普查免疫也照样往下走",
        "TestCensusLock::test_upstream_precondition_is_fail_closed",
        "上游的门被回退掉 `CENSUS_KEYS` / `strip_census` 时不再上抛 ⇒ 本门的判据前提悄悄失效"
        "（fail-open：`projection_agrees` 会拿 `None` 比 `None` 得 True）",
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="任务 71 census 普查免疫守卫变异检验")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true")
    mode.add_argument("--run", type=str, help="逗号分隔的变异号，或 all")
    mode.add_argument("--check-anchors", action="store_true")
    args = parser.parse_args(argv)

    if args.list:
        print(f"[任务71census变异] 共 {len(MUTATIONS)} 条")
        for mutation in MUTATIONS:
            print(f"  {mutation.mid}  {mutation.scope:<24} {mutation.why}")
        return 0
    if args.check_anchors:
        return _host.check_anchors(MUTATIONS)
    selected = [part.strip() for part in str(args.run).split(",") if part.strip()]
    return _host.run(selected, MUTATIONS, TARGETS)


if __name__ == "__main__":
    raise SystemExit(main())
