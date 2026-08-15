"""变异检验：`_mutation_kit` 共享件的自身守卫是否真的承重（自举）。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Task 10 · Requirements 6.5 · Property 20

## 为什么这个脚本本身很重要

共享件的价值全部押在「它强制的那些约束真的强制得住」上。如果 `find_anchor` 的唯一性
断言被误删而没人发现，那么所有依赖它的变异脚本都会静默退化成「找到第一处就改」——
一个横跨全平台的假绿入口。

本脚本**用共享件自己**跑对共享件的变异（自举）：它同时也是共享件的第一个真实调用方，
若共享件的 API 表达不出这套用法，说明设计不足。

用法::

    python backend/scripts/diagnose/mutate_mutation_kit_guards.py --list
    python backend/scripts/diagnose/mutate_mutation_kit_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_mutation_kit_guards.py --run all
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

KIT = "backend/scripts/_mutation_kit"

#: 覆盖面分母 —— 本 spec 为共享件与治理机制创建的守卫文件全集。
#:
#: 新增守卫文件时必须同时加一条变异，否则报告末尾会显示 [GAP] 欠账。
GUARD_FILES: dict[str, str] = {
    "test_mutation_kit_capabilities.py": "Task 10 新建（共享件七项能力）",
    "test_mutation_kit_scripts_tracked.py": "Task 4 新建（变异脚本入库）",
    "test_mutation_kit_exemptions.py": "Task 4 新建（豁免表与失效检测）",
}

BE_ARGS = [
    "backend/tests/test_mutation_kit_capabilities.py",
    "backend/tests/test_mutation_kit_scripts_tracked.py",
    "backend/tests/test_mutation_kit_exemptions.py",
    "-q",
    "--tb=no",
    "-rf",
    "-p",
    "no:randomly",
]

#: 冻结基线（2026-08-15 亲测）。改这个数必须同时说明来源。
#: 62 -> 63：M02 判 GREEN 后补 test_find_anchor_rejects_multiline_anchor。
#: 63 -> 65：Task 11 迁移时暴露「子集运行恒非零退出」缺陷，补两条退出码守卫。
#: 65 -> 77：Task 12 为迁移吸收 scope 相对定位与多目标 wants 两项能力，补 12 条守卫。
BASELINE_BE_PASSED = 77

MUTATIONS: list[Mutation] = [
    Mutation(
        id="M01", side="be", path=f"{KIT}/anchor.py", kind="replace",
        anchor="    if len(hits) != 1:",
        new="    if False:",
        want="test_anchor_multiple_hits_is_rejected",
        why="删掉锚点唯一性断言 ⇒ 所有下游变异脚本静默退化成「改第一处」，"
            "同名多处时改错行而判定照常给 RED（横跨全平台的假绿入口）。"
            "不能改成 `if len(hits) < 1`：那样零命中仍会抛，只有多命中这一支失效，"
            "打红的测试集合会不同。",
    ),
    Mutation(
        id="M02", side="be", path=f"{KIT}/anchor.py", kind="replace",
        anchor='    if "\\n" in anchor or "\\r" in anchor:',
        new="    if False:",
        want="test_find_anchor_rejects_multiline_anchor",
        why="删掉**定位期**的换行检查（声明期 spec.validate_mutation 还有一道，两层独立）。"
            "🔴 本条首轮判定 GREEN，抓出了一个真实的守卫缺口：当时只有 "
            "test_multiline_anchor_rejected_at_declaration 覆盖声明期，定位期这一层"
            "无任何测试 ⇒ 删掉它没有测试会红。补 test_find_anchor_rejects_multiline_anchor "
            "后转 RED。绕过 run_cli 直接调 find_anchor 的调用方走的正是这一层。",
    ),
    Mutation(
        id="M03", side="be", path=f"{KIT}/anchor.py", kind="replace",
        anchor="    hits = [i for i, ln in enumerate(lines) if strip_eol(ln) == anchor]",
        new="    hits = [i for i, ln in enumerate(lines) if anchor.strip() in ln]",
        want="test_anchor_substring_does_not_count_as_hit",
        why="把整行相等改成 strip 后子串包含 —— 这正是本 spec Wave 1 实测的假阳性形态"
            "（6 空格锚点把 4 空格的另一行也算进来，HITS=2 误报为锚点漂移）。",
    ),
    Mutation(
        id="M04", side="be", path=f"{KIT}/spec.py", kind="replace",
        anchor='        if "\\n" in m.anchor or "\\r" in m.anchor:',
        new="        if False:",
        want="test_multiline_anchor_rejected_at_declaration",
        why="删掉声明期的换行拒绝。这是本 spec 作者自己在 Wave 2 踩过的坑"
            "（design.md 明文写了仍写出多行锚点），删了就退回「靠文档约束」。",
    ),
    Mutation(
        id="M05", side="be", path=f"{KIT}/spec.py", kind="replace",
        anchor='            errs.append("replace 的 new 与 anchor 相同 = 无效变异（改动不落盘）")',
        new="            pass",
        want="test_noop_mutation_also_rejected_at_declaration",
        why="删掉「new == anchor」的无效变异拒绝 ⇒ 声明期放行，只剩运行时 md5 兜底；"
            "两层里少一层就意味着绕过 run_cli 的调用方失去保护。",
    ),
    Mutation(
        id="M06", side="be", path=f"{KIT}/apply.py", kind="replace",
        anchor="        if md5_bytes(target.read_bytes()) != md5_bytes(before):",
        new="        if False:",
        want="test_restore_failure_is_raised_not_swallowed",
        why="删掉还原后的 md5 逐字核验 ⇒ 「写回成功」被当成「内容相同」。"
            "本 spec Wave 1 实测过 write_text 把 LF 写成 CRLF 导致内容对而 md5 不符，"
            "没有这道核验就会把污染留给后续变异（全变 WRONG-TEST）。",
    ),
    Mutation(
        id="M07", side="be", path=f"{KIT}/apply.py", kind="replace",
        anchor='            raise AnchorMiss("变异后 md5 未变 —— 改动未落盘（无效变异）")',
        new="            pass",
        want="test_noop_mutation_reported_as_anchor_miss",
        why="删掉「变异后 md5 未变」的无效变异检测 ⇒ 没落盘的变异会去跑测试，"
            "结果必然 GREEN，把脚本缺陷误报成守卫缺陷。",
    ),
    Mutation(
        id="M08", side="be", path=f"{KIT}/coverage.py", kind="replace",
        anchor="        if not guard_files:",
        new="        if False:",
        want="test_empty_denominator_is_rejected",
        why="允许空分母 ⇒ 「守卫都被反证过」这个结论恒成立，覆盖面机制变成装饰。"
            "e-cycle 脚本正是靠分母抓出 7 个从未被打红的守卫文件。",
    ),
    Mutation(
        id="M09", side="be", path=f"{KIT}/coverage.py", kind="replace",
        anchor='            lines.append(f"  [GAP] {f}  （{self.guard_files[f]}）—— 全绿但未经反证，需补一条变异")',
        new="            pass",
        want="test_tally_reports_uncovered_guard_file",
        why="报告不再列出未被打红的守卫文件 ⇒ 欠账不可见。注意 is_complete 仍会返回 "
            "False（退出码仍非零），故本条验的是**可诊断性**而非通过性 —— "
            "「知道有缺口」和「知道缺口是哪个文件」是两件事。",
    ),
    Mutation(
        id="M10", side="be", path=f"{KIT}/coverage.py", kind="replace",
        anchor="        if not full_run:",
        new="        if True:",
        want="test_tally_reports_uncovered_guard_file",
        why="让全量运行也走「子集运行不做覆盖面结论」分支 ⇒ 覆盖面永远不给结论。"
            "这是「机制在但被绕过」的形态，比删掉更隐蔽。",
    ),
    Mutation(
        id="M11", side="be", path=f"{KIT}/cli.py", kind="replace",
        anchor="            if m.scope_check is not None and not m.scope_check(mutated_bytes):",
        new="            if False:",
        want="test_scope_check_failure_is_anchor_miss_not_green",
        why="删掉作用域自证 ⇒ 锚点落在被测判据作用域之外时判 GREEN（守卫缺陷）"
            "而非 ANCHOR-MISS（脚本缺陷）。本 spec Wave 1 实测过这个误判：变异改的是"
            "豁免表顶部 _schema.reason 文档说明，而校验只覆盖 exemptions[] 内的项。",
    ),
    Mutation(
        id="M12", side="be", path=f"{KIT}/cli.py", kind="replace",
        anchor="        if hit_files:",
        new="        if True:",
        want="test_list_fails_when_want_cannot_be_located",
        why="让 --list 的「want 定位不到」永远走成功分支 ⇒ 退回 g7 spec 记录的那个形态："
            "只打印的 --list 在 CI 里恒绿，等于没挂。"
            "🔴 不能改成把 `problems.append(` 那行替换掉：那处是多行调用，"
            "单行替换会留下孤立的字符串与右括号 ⇒ 语法错 ⇒ 整批测试挂掉，"
            "判定退化成 WRONG-TEST/ERROR 而非精确命中（首轮 --list 已拦住那个写法）。",
    ),
    Mutation(
        id="M13", side="be", path=f"{KIT}/cli.py", kind="replace",
        anchor="        print(f\"[FATAL] --check-anchors 必须只读，但以下文件被改动：{changed}\")",
        new="        print(f\"[FATAL] check-anchors wrote files: {changed}\")",
        want="test_check_anchors_is_read_only",
        why="🔴 本条验的是**判据不按输出文案判定**：只改提示文案、不动 `return 2`，"
            "故 test_check_anchors_is_read_only 仍应通过 ⇒ 判定应为 GREEN。"
            "它是 negative control，但**不放进 MUTATIONS**（会让「全 RED」判据失效、"
            "并使 CI 里的 --run 恒非零）；其等价保障已由 verdict 的四态单元测试"
            "（test_verdict_green_when_nothing_added 等）覆盖。留声明在此备查。",
        tags=("negative-control", "not-in-suite"),
    ),
]


# ─── 治理机制侧变异（豁免表数据）──────────────────────────────────────────────
#
# 🔴 为什么必须有这一组：首轮 12 条变异**全 RED**，但覆盖面 tally 报出
# test_mutation_kit_exemptions.py 与 test_mutation_kit_scripts_tracked.py 两个 [GAP]
# —— 它们从未被任何变异打红。原因是 Wave 1 做这两个守卫的变异时用的是临时脚本，
# 跑完即删、没有固化。这正是分母要抓的形态：「变异全 RED」按清单计数，
# 「守卫都被反证过」按文件计数，两者不是一回事。


def _exemption_field_is(field: str, value: str, index: int = 0):
    """构造作用域自证：变异后 ``exemptions[index][field]`` 必须等于 ``value``。

    🔴 这是 Wave 1 缺的那个能力。当时一条变异的锚点命中了豁免表顶部
    ``_schema.reason``（一段**文档说明**）而被测校验只覆盖 ``exemptions[]`` 内的项，
    四态判定式「新增失败集合是否为空」把这个脚本缺陷误报成 GREEN（守卫缺陷）。
    """

    def probe(data: bytes) -> bool:
        try:
            parsed = json.loads(data.decode("utf-8"))
            return str(parsed["exemptions"][index].get(field)) == value
        except Exception:  # noqa: BLE001 - 解析不了就是没落在预期结构里
            return False

    return probe


EXEMPTIONS = "backend/data/mutation_kit_exemptions.json"

MUTATIONS += [
    Mutation(
        id="M14", side="be", path=EXEMPTIONS, kind="replace",
        anchor='      "spec": "k-cycle-extraction-formula-and-disclosure-closure",',
        new='      "spec": "e-cycle-extraction-formula-and-disclosure-completion",',
        want="test_no_stale_exemption_after_spec_archived",
        why="把豁免项的 spec 换成一个**已归档**的 spec 名 ⇒ 失效检测必须报出该豁免应撤销。"
            "不改成不存在的假名字：假名字与「已归档」在 active 集合判定上等价，"
            "但用真实已归档 spec 更贴近该机制要防的场景（豁免变成永久后门）。",
        scope_check=_exemption_field_is(
            "spec", "e-cycle-extraction-formula-and-disclosure-completion"
        ),
    ),
    Mutation(
        id="M15", side="be", path=EXEMPTIONS, kind="replace",
        anchor='      "script": "backend/scripts/diagnose/mutate_k_cycle_guards.py",',
        new='      "script": "backend/scripts/diagnose/mutate_never_existed.py",',
        want="test_every_mutation_script_is_tracked_or_exempt",
        why="把豁免项指向另一个路径 ⇒ 真正未入库的 mutate_k_cycle_guards.py 失去豁免，"
            "tracked 守卫必须抓到它；同时 test_exempt_scripts_actually_exist 也应红"
            "（豁免表出现僵尸项）。一条变异同时反证两个判据。",
        scope_check=_exemption_field_is(
            "script", "backend/scripts/diagnose/mutate_never_existed.py"
        ),
    ),
    Mutation(
        id="M16", side="be", path=EXEMPTIONS, kind="replace",
        anchor='      "registered_at": "2026-08-15",',
        new='      "registered_at": "2026/08/15",',
        line=26,
        want="test_every_entry_has_valid_fields",
        why="把登记日期改成非 ISO 格式 ⇒ 字段校验必须报出。锚点在文件里命中 5 次"
            "（含 _schema 里的示例），故用 line 消歧到 exemptions[0]，"
            "并配 scope_check 双重确认改动落在被测结构内 —— "
            "Wave 1 正是因为锚点落到 _schema 文档说明上而把脚本缺陷误报成 GREEN。",
        scope_check=_exemption_field_is("registered_at", "2026/08/15"),
    ),
    # ── Task 12 为迁移吸收的两项新能力（相对定位 / 多目标 want）───────────────
    Mutation(
        id="M17", side="be", path=f"{KIT}/anchor.py", kind="replace",
        anchor="    if scope:",
        new="    if False:",
        want="test_scope_relative_locate_resolves_ambiguous_anchor",
        wants=(
            "test_scope_survives_line_shift_while_absolute_line_would_not",
            "test_scope_must_be_unique",
        ),
        why="删掉 scope 相对定位分支 ⇒ 退回「只能用绝对行号消歧」。绝对行号一改文件就失效"
            "（Wave 3 的 M12 写 line=155 而那行早已是别的内容），而 scope+offset 只要"
            "scope 行还唯一就有效 —— 这条能力是迁移 mutate_trim_decision_guards 时吸收的。"
            "本条用多目标 wants 声明，正好也在验第二项新能力。",
    ),
    Mutation(
        id="M18", side="be", path=f"{KIT}/verdict.py", kind="replace",
        anchor="    patterns = [p for p in ((want,) + tuple(wants)) if p]",
        new="    patterns = [p for p in (want,) if p]",
        want="test_verdict_supports_multi_target_wants",
        wants=("test_verdict_multi_target_union_with_single_want",),
        why="让 matched 丢掉 wants 只看 want ⇒ 多目标退化成单目标。迁移 trim_decision"
            "（expect_red: tuple）与 note_conversion（expect_tests: list）都依赖多目标，"
            "退化后它们的判定会从 RED 变 WRONG-TEST（命中不到被挑掉的那些模式）。",
    ),
]

#: 实际投入运行的变异集合（排除 negative control）。
MUTATIONS = [m for m in MUTATIONS if "not-in-suite" not in m.tags]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="_mutation_kit 共享件自身守卫的变异检验（自举）",
            backend_args=BE_ARGS,
            baseline_backend_passed=BASELINE_BE_PASSED,
            guard_roots=("backend/tests",),
        )
    )
