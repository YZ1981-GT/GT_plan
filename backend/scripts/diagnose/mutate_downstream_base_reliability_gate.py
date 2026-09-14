# -*- coding: utf-8 -*-
"""跨 Wave 假绿拦截守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure（整改清单项 4）
被检守卫: ``backend/tests/workpaper_sync/test_downstream_base_reliability_gate.py``

## 四态

===============  ==========================  ==============================
判定             含义                        归因
===============  ==========================  ==============================
``RED``          **预期那条**判据打红        守卫有效
``GREEN``        无新增失败                  **守卫缺陷**
``WRONG-TEST``   打红了但不是预期项          锚点错行 / 污染残留
``ANCHOR-MISS``  锚点非唯一命中 / 未落盘     **本脚本缺陷**
===============  ==========================  ==============================

判定与还原（`finally` + 逐字核验 + 残留扫描）全部走共享件 ``_mutation_kit``；本脚本另加
一层 **sha256** 前后比对（共享件内部用 md5），覆盖 memory 记的「判成败查数据不看 exit
code」——`--run` 被 `^C` 中断时退出码不可信，但哈希不会骗人。

## 🔴 为什么变异打在**守卫自己的判据**上，而不是打在被判的事实上

本守卫判的三样东西全部**不可变异**：

- ``tasks.md``（勾选态与依赖图）、``check_workpaper_writer_revision_gate.py``（门）、
  ``workpaper_sync_*_cycle_manifest_slice.json``（slice）—— 都有并发会话在改，
  临时改写 + 还原会与对方的在途写入互相覆盖；
- ``workpaper_sync_entry_manifest.json`` 是 source-backed 生成物，手改它等于伪造事实。

所以变异落在**判据本体**：把每条谓词按「最像的那种放宽形态」改一下，看反向自检是否打红。
这检的正是最要紧的一件事 —— **判据被放宽时有没有人拦**（守卫的危险从来不是「一直红」，
而是某个谓词被悄悄放宽而变绿）。M08 就是复刻本轮实际发生过的缺陷：初版漏了 SR-5/SR-6 的
``capability`` 前提，把四处**诚实的** pilot 未闭环记录误报成「宣称 base 可靠」。

## 用法

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_downstream_base_reliability_gate.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_downstream_base_reliability_gate.py --check-anchors
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_downstream_base_reliability_gate.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/downstream-base-reliability-gate/mutation_report.json
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_downstream_base_reliability_gate.py --verify-restore

## 并发注意

共享件的残留扫描是**全仓库**范围，并发会话正在变异别的文件时（实测撞到
``workpaper_sync_migration_paradigm.json.mutbak`` 与
``check_task44_oo94_excel_pilot_gate.py.mutbak``）本脚本会 `[ABORT]`。
**不要代它 `--restore`** —— 那会把对方在途的变异态写回去。等它自己散掉再跑。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend" / "scripts"))

from _mutation_kit import Mutation, run_cli  # noqa: E402

GUARD = "backend/tests/workpaper_sync/test_downstream_base_reliability_gate.py"

#: 覆盖面分母：本次整改的守卫文件 → 归属说明。空分母会让覆盖统计恒成功。
GUARD_FILES = {
    "test_downstream_base_reliability_gate.py": (
        "整改清单项 4：门未过时下游不得宣称 base 可靠 —— "
        "类别 A（依赖序）/ B（门禁序）/ C（证据结构）三类判据 + 反向自检"
    ),
}

BE_ARGS = [GUARD, "-q", "--tb=no", "-rf", "-p", "no:randomly"]

MUTATIONS: list[Mutation] = [
    # ═══════════════ 派生面：依赖图闭包与下游集合 ═══════════════
    Mutation(
        id="M01",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="        stack.extend(str(n) for n in deps.get(node, []))",
        new="        pass",
        want="test_reverse_selfcheck_closure_is_transitive",
        why="闭包不再传递 —— 真实图里 Task 27 是经 26 才够到门的（27 的直接依赖是 "
        "14/15/26），只看直接依赖会把 Wave 2 一半的下游漏掉，判据随之少报",
    ),
    Mutation(
        id="M02",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="            if waves[task] > gate_wave and gate_task in dependency_closure(deps, task)",
        new="            if waves[task] > gate_wave",
        want="test_the_downstream_set_is_derived_not_enumerated",
        why="把「下游」退化成「wave 更大」= 手写名单的等价形态：Tasks 21–24 就在门之后的 "
        "wave 里却不依赖门，会被误报；这类误报最后总是靠放宽判据消掉",
    ),
    Mutation(
        id="M03",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="    return sorted(name for name, holders in gates.items() if gate_task in map(str, holders))",
        new="    return []",
        want="test_reverse_selfcheck_a_blocked_door_with_a_verified_claim_is_stopped",
        why="本门不再认领任何闸 ⇒ 类别 B 恒绿。`gates` 块是「任何 adapter pilot 不得宣称」"
        "那半句的唯一真源，认领集合空掉后越门执行永远查不出来",
    ),
    # ═══════════════ 门的状态：本门未过怎么判 ═══════════════
    Mutation(
        id="M04",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="    return any(issues.values())",
        new='    return any(issues.get("missing_required_domain", []))',
        want="test_a_relocated_criterion_still_blocks_the_door",
        why="**本轮最要防的 fail-open**：只按归属 Task 20 的准则判门。实测归属 Task 20 的"
        "六条全为 0（912 归 74、4 归 71），这样一改整个守卫立刻恒绿，而门自己仍 exit 1",
    ),
    Mutation(
        id="M05",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="    if waves[owner] > waves[claimant]:",
        new="    if False:",
        want="test_reverse_selfcheck_an_owner_in_the_same_wave_is_not_scheduled_after",
        why="「归属方排在更晚的 wave」这一支被摘掉 ⇒ 类别 A 只剩「归属方反过来依赖宣称方」"
        "一支，而当前 200 条违规全部来自 wave 序（Task 74/71 在 Wave 7）⇒ 恒绿",
    ),
    Mutation(
        id="M06",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="            if owner == gate_task:",
        new="            if False:",
        want="test_reverse_selfcheck_the_gate_owner_debt_is_also_a_claim_blocker",
        why="摘掉「归属就是本门」那一支 ⇒ Task 20 自有准则一旦非零反而没人拦。"
        "「已移交的不该让门背锅」不等于「门自己的也不用管」",
    ),
    # ═══════════════ 证据结构：类别 C 的两条边界 ═══════════════
    Mutation(
        id="M07",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="                    and state != cannot_verify_state",
        new='                    and state == "VERIFIED"',
        want="test_reverse_selfcheck_the_evidence_predicate_is_fail_closed_on_unknown_states",
        why="把「≠ 不可验证」换成「== VERIFIED」—— 换个词（CLOSED / PASSED / 已闭环）"
        "就能绕过。这是白名单式判据的典型 fail-open 形态",
    ),
    Mutation(
        id="M08",
        side="be",
        path=GUARD,
        kind="replace",
        anchor="            if declared and bidirectional_token not in declared.values():",
        new="            if True:",
        want="test_reverse_selfcheck_an_identity_field_on_an_entry_is_a_claim",
        why="复刻**本轮实际发生过的缺陷**：漏掉 SR-5/SR-6 的 capability 前提后，"
        "task40/42/43 三份 pilot 执行记录（有 entry_id + adapter_id、无 capability、"
        "明写 capability_enabled=false）被误报成宣称 —— 判据越出规则自己的作用域",
    ),
    Mutation(
        id="M09",
        side="be",
        path=GUARD,
        kind="replace",
        anchor='            found.extend(iter_entry_nodes(value, f"{path}/{key}"))',
        new="            pass",
        want="test_the_evidence_scan_has_a_real_denominator",
        why="entry 递归只剩数组分支 ⇒ 嵌在 dict 下的 entry（slice 的 "
        "`independent_entries` 之外还有 `parent_duplicate_summary` 等）扫不到，"
        "类别 C 的分母静默缩小。分母判据必须能拦住这种缩水",
    ),
    Mutation(
        id="M10",
        side="be",
        path=GUARD,
        kind="replace",
        anchor='_CLAIM_MARKERS = frozenset({"x"})',
        new='_CLAIM_MARKERS = frozenset({"x", " ", "~", "-"})',
        want="test_reverse_selfcheck_an_unchecked_downstream_task_is_not_a_claim",
        why="把未勾选/进行中/阻塞态也算成「宣称完成」⇒ 判据变成「有欠账就打红所有下游」"
        "的恒红装饰，复核者只会去删这条守卫。恒红与恒绿一样是失效",
    ),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _targets() -> list[Path]:
    return sorted({(REPO / m.path) for m in MUTATIONS})


def main(argv: list[str] | None = None) -> int:
    """跑共享件 CLI，并在其外层加一道 sha256 逐字还原核验。"""
    args = list(sys.argv[1:] if argv is None else argv)
    before = {p: _sha256(p) for p in _targets() if p.exists()}

    if "--verify-restore" in args:
        # 只报当前哈希，供中断后人工比对（共享件的 --restore 负责实际还原）
        for path, digest in before.items():
            print(f"[SHA256] {path.relative_to(REPO).as_posix()} {digest}")
        return 0

    rc = run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        description="跨 Wave 假绿拦截守卫（门未过时下游不得宣称 base 可靠）变异检验",
        backend_args=BE_ARGS,
        baseline_backend_passed=15,
        argv=args,
    )

    print("\n── sha256 逐字还原核验 ──")
    drift = []
    for path, digest in before.items():
        now = _sha256(path)
        mark = "OK " if now == digest else "!! "
        print(f"  {mark}{path.relative_to(REPO).as_posix()}")
        print(f"      before {digest}")
        print(f"      after  {now}")
        if now != digest:
            drift.append(path)
    if drift:
        print(f"[FATAL] {len(drift)} 个目标文件未逐字还原 —— 立即 --restore 并复核工作树")
        return 8
    print("  全部目标文件 sha256 与变异前逐字一致")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
