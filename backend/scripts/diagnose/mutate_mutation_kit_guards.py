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
ADOPTION = "backend/tests/test_mutation_kit_adoption.py"
EXEMPT_GUARD = "backend/tests/test_mutation_kit_exemptions.py"

#: 覆盖面分母 —— 本 spec 为共享件与治理机制创建的守卫文件全集。
#:
#: 新增守卫文件时必须同时加一条变异，否则报告末尾会显示 [GAP] 欠账。
GUARD_FILES: dict[str, str] = {
    "test_mutation_kit_capabilities.py": "Task 10 新建（共享件七项能力）",
    "test_mutation_kit_scripts_tracked.py": "Task 4 新建（变异脚本入库）",
    "test_mutation_kit_exemptions.py": "Task 4 新建（豁免表与失效检测）",
    "test_mutation_kit_adoption.py": "Task 14 新建（采纳守卫：存量冻结名单）",
}

BE_ARGS = [
    "backend/tests/test_mutation_kit_capabilities.py",
    "backend/tests/test_mutation_kit_scripts_tracked.py",
    "backend/tests/test_mutation_kit_exemptions.py",
    "backend/tests/test_mutation_kit_adoption.py",
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
#: 77 -> 92：Task 14 两件事叠加 —— ① 新建采纳守卫 test_mutation_kit_adoption.py（13 例）
#: 并纳入分母；② 修 test_mutation_kit_exemptions.py 的两条既存红（失效检测命中 k/i-cycle
#: 归档 + test_active_spec_scan_is_not_empty 把 `len(active)>=3` 当基线而 active 只剩 2 个）。
#: 故 77(其中 2 条红) → 79 全绿 → +13 = 92。**首版误写 90**（拿旧的 77 直接加 13，
#: 漏算那 2 条由红转绿的），实测 91 passed + 1 failed = 92 时才发现。
BASELINE_BE_PASSED = 92

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


def _inject_entry(
    *,
    script: str = "backend/scripts/diagnose/mutate_wp_export_resolver_guards.py",
    spec: str = "e1-variant-recalc-and-mutation-denominator-closure",
    reason: str = "变异注入项，跑完即还原",
    registered_at: str = "2026-08-16",
) -> str:
    """构造一条**注入用**豁免项的多行 JSON 文本（供 ``kind="insert"`` 用）。

    🔴 为什么三条治理侧变异都改成注入而不是替换现有条目（2026-08-16）：
    豁免项会随 spec 归档被逐条撤销，最终 ``exemptions`` 归零 —— 任何锚在
    「某条具体豁免」上的变异都会在那一刻失效。M14/M15/M16 各失效过两次
    （先锚 k-cycle 条目 → 撤销后改 scope 定位 exemptions[0] → 该项也被撤销）。
    注入式变异只依赖 ``"exemptions": [`` 这个**结构锚**，与表内有几项无关。

    默认 ``script`` 用一个**真实存在**的脚本路径，使「路径存在性」不会成为
    意外的红因 —— 只有显式传入不存在的路径时（M15）才触发该判据。
    """
    return (
        "    {\n"
        f'      "script": "{script}",\n'
        f'      "spec": "{spec}",\n'
        f'      "reason": "{reason}",\n'
        f'      "registered_at": "{registered_at}",\n'
        '      "revoke_when": "本项由变异脚本注入，跑完即还原，不应出现在任何提交里"\n'
        "    }"
    )


EXEMPTIONS = "backend/data/mutation_kit_exemptions.json"

MUTATIONS += [
    Mutation(
        id="M14", side="be", path=EXEMPTIONS, kind="insert",
        anchor='  "exemptions": [',
        new=_inject_entry(
            spec="e-cycle-extraction-formula-and-disclosure-completion",
            reason="变异注入项：spec 已归档，失效检测必须报出本项应撤销",
        ),
        want="test_no_stale_exemption_after_spec_archived",
        why="注入一条 spec 指向**已归档** spec 的豁免 ⇒ 失效检测必须报出它应撤销。"
            "不用不存在的假名字：假名字与「已归档」在 active 集合判定上等价，"
            "但用真实已归档 spec 更贴近该机制要防的场景（豁免变成永久后门）。"
            "🔴 **形态已从 replace 现有条目改为 insert 构造条目**（2026-08-16 第二次改）："
            "第一版锚在 `_revoked_log` 那条（撤销后失效），第二版改 scope 相对定位到 "
            "exemptions[0]，而本日 `workpaper-import-export-lifecycle-closure` 归档后"
            "该项也被撤销、exemptions 成了**空数组**，锚点第三次失效。"
            "两次失效同一根因：**变异判据依赖『豁免表里恰好有条目』这个环境值** —— "
            "与守卫侧 test_active_spec_scan 两度假红（先 `>=3` 后 `assert active`）是同一形态。"
            "改成注入后判据只依赖 `\"exemptions\": [` 这个**结构锚**，"
            "豁免项增删归零都不再影响它。",
        scope_check=_exemption_field_is(
            "spec", "e-cycle-extraction-formula-and-disclosure-completion"
        ),
    ),
    Mutation(
        id="M15", side="be", path=EXEMPTIONS, kind="insert",
        anchor='  "exemptions": [',
        new=_inject_entry(
            script="backend/scripts/diagnose/mutate_never_existed.py",
            reason="变异注入项：script 指向不存在的脚本（僵尸豁免项）",
        ),
        want="test_exempt_scripts_actually_exist",
        wants=("test_every_entry_script_path_exists",),
        why="注入一条指向**不存在脚本**的豁免 ⇒ 僵尸项判据必须报出。"
            "一条变异同时反证两个文件里的两条判据（tracked 守卫的 "
            "test_exempt_scripts_actually_exist + 豁免表守卫的 "
            "test_every_entry_script_path_exists），故用 wants 多目标声明。"
            "🔴 **判据目标已从 tracked 主判据换成僵尸项判据**（2026-08-16）："
            "原设计靠「移走某个未入库脚本的豁免」让 "
            "test_every_mutation_script_is_tracked_or_exempt 变红，但全平台变异脚本"
            "**已全部入库**（豁免表因此归零）⇒ 任何豁免增删都无法再让 tracked 主判据变红，"
            "原形态会退化成 GREEN 而假报守卫缺陷。僵尸项判据同在 tracked 守卫文件内，"
            "覆盖面分母不会因此出现 [GAP]。",
        scope_check=_exemption_field_is(
            "script", "backend/scripts/diagnose/mutate_never_existed.py"
        ),
    ),
    Mutation(
        id="M16", side="be", path=EXEMPTIONS, kind="insert",
        anchor='  "exemptions": [',
        new=_inject_entry(
            registered_at="2026/08/15",
            reason="变异注入项：registered_at 非 ISO 格式，字段校验必须报出",
        ),
        want="test_every_entry_has_valid_fields",
        why="注入一条 registered_at 为非 ISO 格式的豁免 ⇒ 字段校验必须报出。"
            "配 scope_check 确认改动落在 `exemptions[]` 结构内 —— "
            "Wave 1 正是因为锚点落到 `_schema` 文档说明上而把脚本缺陷误报成 GREEN。"
            "🔴 **消歧方式三度演进**（2026-08-16 第二次改）：line=26 绝对行号 → "
            "scope+offset 相对定位 exemptions[0] → 现在的结构锚 + 注入。"
            "前两版都锚在「某条真实豁免」上，而豁免会被撤销：`_revoked_log` 补留档时"
            "绝对行号漂移（--list 报「期望 registered_at，实为 revoked_at」），"
            "exemptions 归零时 scope 相对定位又整条失效。"
            "注入式只依赖结构锚，且**天然消歧** —— 无需 line/scope，"
            "因为 `\"exemptions\": [` 全文唯一。",
        scope_check=_exemption_field_is("registered_at", "2026/08/15"),
    ),
    Mutation(
        id="M23", side="be", path=EXEMPT_GUARD, kind="replace",
        anchor='        if p.is_dir() and not p.name.startswith("_")',
        new="        if p.is_dir()",
        want="test_active_spec_scan_mechanism_is_healthy",
        why="删掉 `_` 前缀排除 ⇒ 归档区 `_archive` 被当成一个 active spec。"
            "🔴 本条补的是一个**从未被反证过的判据**：`test_active_spec_scan_*` 两度假红"
            "（第一版 `len(active) >= 3`、第二版 `assert active`），两次都是「把当时的"
            "环境值当基线」；2026-08-16 全部 spec 归档后 active 真的归零，第二版当场打红。"
            "第三版改用与规模无关的结构判据（根目录可枚举 + `_archive` 存在 + "
            "`_archive` 不得出现在结果里），而**新判据必须自己被反证过才算数** —— "
            "否则它可能是一条恒真的空话（这正是假绿第②源）。本条变异证明它有区分能力："
            "排除逻辑一坏即红，而 active 为 0 时仍绿。",
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
    # ── Task 14 的采纳守卫（存量冻结名单形态）——────────────────────────────────
    #
    # 🔴 为什么这一组必须固化在这里、不能用临时脚本跑一次：Wave 3 的覆盖面 tally 曾
    # 报出两个 [GAP]（test_mutation_kit_exemptions / test_mutation_kit_scripts_tracked
    # 从未被任何变异打红），原因正是 Wave 1 给它们做变异时用的是临时脚本、跑完即删。
    # 采纳守卫是本 spec 收敛后的核心机制，它的四条不变量都要有常驻反证。
    Mutation(
        id="M19", side="be", path=ADOPTION, kind="replace",
        anchor='    "backend/scripts/check/mutate_task13_wiring_guards.py":',
        new='    "backend/scripts/check/mutate__never_existed_probe__.py":',
        want="test_new_scripts_must_use_the_shared_kit",
        why="把一个真实存量脚本从冻结名单里「挪走」（键改成不存在的路径）⇒ 它变成"
            "「名单外且未采纳」，主判据必须报出它。这条验的是采纳守卫的**正向能力** —— "
            "名单不是把所有脚本都放过的万能白名单，漏登记就会被抓。"
            "不能直接 delete 该行：值在下一行，删键会留下孤立字符串 ⇒ 语法错误，"
            "判定退化成 collect error（WRONG-TEST）而非精确命中。",
    ),
    Mutation(
        id="M20", side="be", path=ADOPTION, kind="replace",
        anchor="_FROZEN_SIZE = 19",
        new="_FROZEN_SIZE = 18",
        want="test_frozen_list_only_shrinks",
        why="下调冻结上限模拟「名单增长了一条」⇒ only-shrinks 判据必红。这条守的是"
            "R8.2 的第二条不变量：新脚本不得把自己加进名单来逃避约束，否则名单退化成"
            "免责声明（e-cycle 的 M20 变异针对的正是同一形态）。"
            "🔴 之所以改上限而不是真加一条名单项：真加一条需要同时给出一个不存在的脚本"
            "路径，会连带打红 zombie/路径形态那几条判据 ⇒ 判定不再精确对应本条不变量。",
    ),
    Mutation(
        id="M21", side="be", path=ADOPTION, kind="insert",
        anchor='        "删除完成则本条成为可清理的僵尸项（只 INFO），若被恢复则按存量处理不打红",',
        new='    "backend/scripts/check/mutate_task13_wiring_guards.py": "短",',
        want="test_every_frozen_entry_has_a_real_reason",
        why="在名单末尾插入一条**重复键**的空话理由（Python dict 字面量后者覆盖前者）"
            "⇒ task13 的理由变成「短」，理由质量闸必红。这条守的是「豁免必须说明为什么"
            "不迁」——空话让名单退化成免责声明。"
            "🔴 用重复键而不是新键：新键会让条目数 +1 从而连带打红 only-shrinks，"
            "判定就分不清是哪条不变量在承重了（重复键下 len 不变，只有理由闸红）。"
            "实证价值：本闸上线时立刻抓到作者自己写的两条「同上」（15 字）。",
    ),
    Mutation(
        id="M22", side="be", path=ADOPTION, kind="replace",
        anchor="        elif isinstance(node, ast.Import):",
        new="        elif KIT_PACKAGE in src:  # mut: 退化成字符串匹配",
        want="test_reverse_selfcheck_comment_mention_is_not_adoption",
        why="把 AST 判据的第二个分支换成字符串匹配 ⇒ 「docstring 里提一句 _mutation_kit」"
            "会被判成已采纳（memory 假绿第②源：grep 式守卫只查字符串存在）。"
            "🔴 本条同时验证了一次判据重构的必要性：初版的这条自检是**自包含**的"
            "（内联源码串自己 ast.walk 一遍），改坏 imports_kit_src 打不红它 —— "
            "证明的是「AST 语义如此」而非「本文件的实现如此」。抽成纯函数后才咬得住。"
            "不能整体删掉 ImportFrom 分支：那样真实 import 也认不出，会连带打红形态自检"
            "⇒ 判定不精确对应「退化为字符串匹配」这一形态。",
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
