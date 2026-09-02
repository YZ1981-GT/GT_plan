# -*- coding: utf-8 -*-
"""变异检验：`workpaper_sync_migration_paradigm.json` 四个新键的判据是否真的承重。

spec: .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/
Requirements: 1.3, 1.4, 1.5, 12.1, 12.8, 12.9

═══ 这一轮的「生产代码」是数据 ═══

`paradigm_registry` / `definition_producer_paradigm` / `adjudication_criteria` /
`slice_schema` 四个键上一轮补出来时**零消费方**（死数据）。本轮补的判据是
`backend/tests/workpaper_sync/test_migration_paradigm_contract.py`，所以变异落在
**数据侧**（那个 JSON），守卫保持不动 —— 与「变异改生产、不改守卫」是同一条规矩。

═══ 一个专属的假绿形态：判据从被变异的源头推导期望值 ═══

`slice_schema` 的反例是**从 schema 现读**参数化出来的：把 `required_entry` 里某个字段
删掉，它自己的反例也随之消失 ⇒ 「抽字段」这个动作反而没有任何测试变红。M03 就是这条
的证据 —— 它必须由**地板判据**（`FROZEN_REQUIRED_FLOOR`，独立于 schema 的硬编码下限）
打红，而不是由参数化反例打红。

═══ 四态 ═══

RED=守卫有效 · GREEN=守卫缺陷或无效变异（须逐条归因）· WRONG-TEST=红了但不是预期项
（污染残留 / 锚点落在错误位置）· ANCHOR-MISS=脚本缺陷（锚点未唯一命中 / 未落盘 /
CRLF 下的跨行锚点）。退出码不作判据。

═══ 还原核验 ═══

`_mutation_kit` 在 `finally` 里按 **md5** 逐字还原核验；本脚本在 `run_cli` 前后再做一层
**sha256** 全量核验（`--run` 结束后逐文件比对），两个摘要都不符才算还原失败。

用法（仓库根，注意本仓库 PATH 上的 `python` 指向坏掉的 venv）::

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_migration_paradigm_contract.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_migration_paradigm_contract.py --check-anchors
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_migration_paradigm_contract.py --run all --out tmp_paradigm_mutation.json
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

PARADIGM = "backend/data/workpaper_sync_migration_paradigm.json"
GUARD = "test_migration_paradigm_contract.py"

#: 覆盖面分母 —— 本轮新建的守卫文件全集。
GUARD_FILES = {
    GUARD: (
        "本轮新建：四个新顶层键的判据（步骤拓扑 / AC 原文逐字 / slice_schema 两侧断言 / "
        "旧 paradigm 字节冻结 / AP-1 循环论证检测 + 四键互锁 + 反向自检）"
    ),
}

BE_ARGS = [
    f"backend/tests/workpaper_sync/{GUARD}",
    "-q",
    "--tb=no",
    # 🔴 `-rfE` 而不是 `-rf`：变异改的是**参数化与 fixture 的数据源**，一旦某条变异让
    # 模块导入期的 `_negative_cases()` / `_single_onlyoffice_params()` 抛异常，pytest 记
    # 的是 ERROR 而不是 FAILED，`-rf` 的 short summary 一条都不列 ⇒ 明明打红了却被判 GREEN。
    "-rfE",
    "-p",
    "no:randomly",
]

MUTATIONS: list[Mutation] = [
    # ═══ 一、definition_producer_paradigm 的步骤拓扑 ═════════════════════════
    Mutation(
        id="M01", side="be", path=PARADIGM, kind="replace",
        anchor='        "blocks": [12]',
        new='        "blocks": [1]',
        want="test_blocks_edges_are_forward_only",
        wants=("test_the_step_graph_is_acyclic",),
        why="把 step 11（enforce_honest_mode_visibility）的前向边改成指回 step 1 ⇒ 制造回边"
            "与 1→11→1 的环。`ordering_rule` 只是一句话，判据必须是现算的图：边方向由 "
            "find_edge_violations 判，环由独立的 DFS 判（两条判据都得红）",
    ),
    Mutation(
        id="M08", side="be", path=PARADIGM, kind="delete",
        anchor='        "read_authoritative_template_and_freeze_digest": 2,',
        want="test_the_gap_the_registry_names_is_fully_covered",
        why="删掉「读权威模板并冻结 digest」这件活的归属映射 ⇒ step 2 不再被任何 activity "
            "覆盖。这正是旧 /paradigm 漏掉九件活的形态：某类活没有归属步骤，而计数关系"
            "（activities >= does_not_cover）单独看不出来 —— 必须同时断言 step 2~11 全覆盖",
    ),
    # ═══ 二、AC 原文逐字（唯一真源 = requirements.md 磁盘内容）═══════════════
    Mutation(
        id="M02", side="be", path=PARADIGM, kind="replace",
        anchor='        "text": "无 HTML 对端的纯 OO entry SHALL 标为 `single_onlyoffice`；不得为满足数字伪造字段映射或修改模板制造对端。"',
        new='        "text": "无 HTML 对端的纯 OO entry SHALL 标成 `single_onlyoffice`；不得为满足数字伪造字段映射或修改模板制造对端。"',
        want="test_ac_text_is_verbatim_from_requirements_md",
        why="AC 12.8 原文「标为」改一字成「标成」。`quotation_rule` 承诺的是**逐字**，"
            "判据必须现读 requirements.md 按 `12.8. ` 前缀定位后 `==` 比对 —— 若退化成 "
            "`in`/关键词命中，改一字（甚至截尾）都不会红（见守卫里的两条反向自检）",
    ),
    # ═══ 三、slice_schema 抽字段（专属假绿：反例从被变异源推导）═════════════
    Mutation(
        id="M03", side="be", path=PARADIGM, kind="delete",
        anchor='      "template_ref",',
        want="test_required_field_groups_never_shrink",
        why="从 `required_entry` 删掉 `template_ref`。🔴 它**不会**被参数化反例打红 —— 反例"
            "是从 schema 现读构造的，字段删了它自己的反例也消失。必须由地板判据"
            "（FROZEN_REQUIRED_FLOOR，独立于 schema 的硬编码下限）承重。这条是本脚本"
            "存在的核心理由：证明「schema 缩水」有独立证人",
    ),
    Mutation(
        id="M07", side="be", path=PARADIGM, kind="replace",
        anchor='        "observable_consequences"',
        new='        "observable_consequences_renamed"',
        want="test_one_of_groups_never_shrink",
        wants=("test_the_reference_instance_passes",),
        why="把 one-of 组里的 `observable_consequences` 改名 ⇒ ①地板判据发现该组消失；"
            "②事实范式 slice 的 BP-4（只有 observable_consequences、没有 consequence）"
            "当场通不过正例校验。one-of 组本身就是本轮修的内部矛盾（初版把 consequence "
            "列成必填而 BP-4 没有它），改名后两侧都必须红",
    ),
    Mutation(
        id="M09", side="be", path=PARADIGM, kind="replace",
        anchor='        "html_counterpart_verdict",',
        new='        "html_counterpart_verdict_renamed",',
        want="test_verdict_field_names_agree_across_three_declarations",
        wants=("test_task48_additions_never_shrink",),
        why="`effective_from_task_48.required_entry` 的字段名改一处（8 空格缩进那份，不是 "
            "AP-1 / verdicts / step 3 里的 10~12 空格那几份）⇒ 「schema 加严的字段」与"
            "「检测器要求的字段」"
            "漂移成两批。同一件事声明三遍（step 3 must_contain / AP-1 required_remedy_fields "
            "/ schema 追加项）时，漂移的那一份就变成死数据，且没人知道哪份是真的",
    ),
    # ═══ 四、旧 `paradigm` 字节冻结 ══════════════════════════════════════════
    Mutation(
        id="M04", side="be", path=PARADIGM, kind="replace",
        anchor='        "name": "identify_legacy",',
        new='        "name": "identify_legacy_v2",',
        want="test_raw_block_bytes_are_frozen",
        wants=(
            "test_canonical_digest_is_frozen",
            "test_the_seven_frozen_step_names_are_intact",
        ),
        why="改 Task 45 冻结的七步之一。`immutability` 声明双向 digest 锁，判据必须现算"
            "字节 + canonical 两个摘要与硬编码常量比对。这一步名还被 "
            "test_task46_d_cycle_migration.py 依赖（它断言恰 7 步且名字固定）—— 字节冻结"
            "不承重时，改动会静默传播到别的 spec 的守卫上",
    ),
    # ═══ 五、AP-1 循环论证检测器 ═════════════════════════════════════════════
    Mutation(
        id="M05", side="be", path=PARADIGM, kind="replace",
        anchor='              "entry_id": "xlsx/gt-e1-monetary-fund",',
        new='              "entry_id": "xlsx/gt-e1-monetary-fund-unregistered",',
        want="test_violations_are_a_subset_of_the_registered_debt",
        wants=(
            "test_the_registered_debt_has_no_zombie_entries",
            "test_single_onlyoffice_entry_states_its_html_counterpart",
        ),
        why="把 E1（当前**唯一**仍在违规的欠账）从 known_debt_inventory 里「摘掉」⇒ 一条仍然"
            "违规的 single_onlyoffice 裁决变成未登记违规。三条判据必须同时响：①subset 规则"
            "（清单外新违规立刻打红，无 xfail 保护）②僵尸项 ③E1 自己的逐 entry 判据失去 "
            "xfail 标记后成为硬失败。这就是 Tasks 48–57 继续走老路时的形态。"
            "🔴 初版锚在 D1 上，但 2026-08-30 并发的 D 循环回填已把 7 条 D 改成带 "
            "`html_counterpart_verdict: exists` 的待裁决态（不再是 single_onlyoffice）⇒ "
            "摘掉 D1 的登记不会触发 subset 规则（它已不在违规集合里）",
    ),
    Mutation(
        id="M10", side="be", path=PARADIGM, kind="replace",
        anchor='              "entry_id": "xlsx/gt-d1-notes-receivable",',
        new='              "entry_id": "xlsx/gt-d1-notes-receivable-typo",',
        want="test_the_registered_debt_has_no_zombie_entries",
        why="把一条**已兑现**的欠账登记改成不存在的 entry_id ⇒ 清单腐化（僵尸项）。"
            "与 M05 是两个不同判据：M05 考「清单外新违规」，本条考「清单内容与现实脱节」"
            "—— 僵尸项会让 xfail 标记挂空，届时 strict xfail 的 XPASS 反向锁就静默失效",
    ),
    Mutation(
        id="M06", side="be", path=PARADIGM, kind="replace",
        anchor='        "forbidden_verdict_for_single_onlyoffice": "exists",',
        new='        "forbidden_verdict_for_single_onlyoffice": "none",',
        want="test_an_exists_verdict_forbids_single_onlyoffice",
        wants=("test_a_resolved_none_verdict_with_source_refs_is_clean",),
        why="把「有 HTML 对端就不许裁 single_onlyoffice」这条禁令的取值翻过来 ⇒ AC 12.8 的"
            "唯一合法判据失守。真实数据里目前没有 verdict=exists 的 entry，这条分支只能靠"
            "合成输入激活 —— 没有它，`forbidden_verdict_for_single_onlyoffice` 就是死声明。"
            "同时合规样例（verdict=none）会被误报，证明检测器两个方向都被这条声明驱动",
    ),
    # ═══ 六、SR-3 蕴含式的右支（待裁决态）—— G1 收口后新增 ═══════════════════
    #
    # 背景：AC 1.3 的 `capability_enum` 只有四个终态，而迁移中的 entry 会被 AC 12.8 / 12.9 /
    # 1.7 / 12.1 同时排除掉四个 ⇒ D/F 两份 slice 采用 `capability: null` + 三个 pending 字段的
    # 诚实待裁决态。收口做法是把 SR-3 改成蕴含式（枚举内 **或** null+三字段齐备），**不**扩
    # 枚举。下面五条逐支验证「右支不是后门」：缺字段、语义被放宽、计数器指错、被误设成全局
    # 必填、语义 kind 不认识时是否 fail closed。
    Mutation(
        id="M11", side="be", path=PARADIGM, kind="delete",
        anchor='      "capability_verdict_stage",',
        want="test_required_field_groups_never_shrink",
        wants=("test_pending_verdict_fields_are_conditional_not_global",),
        why="从 `required_pending_verdict_fields` 删掉 `capability_verdict_stage`。🔴 与 M03 同型"
            "的专属假绿：该字段的参数化反例（`pending:missing:capability_verdict_stage`）是从"
            " schema 现读构造的，字段删了它自己的反例也消失 ⇒ 「待裁决态可以不写阶段」这个"
            "放宽反而没有任何反例变红。必须由地板判据（FROZEN_REQUIRED_FLOOR 的同名组）+ "
            "「required 列表与 semantics 必须同一批字段」两条独立判据承重",
    ),
    Mutation(
        id="M12", side="be", path=PARADIGM, kind="replace",
        anchor='      "capability_target": "member_of_capability_enum",',
        new='      "capability_target": "non_empty_string",',
        want="test_the_pending_verdict_contract_never_loosens",
        wants=("pending:capability_target",),
        why="把 `capability_target` 的语义 kind 从「必须落在 capability_enum 内」放宽成「非空"
            "字符串」。🔴 这是**值**层面的放宽：键一个没少，`FROZEN_REQUIRED_FLOOR` 那种只锁"
            "键名的地板一条都不会红，而 `capability_target: \"dual\"`（自造能力态当目标）当场"
            "放行 —— 「不知道往哪走」就冒充成了待裁决。两个证人：冻结语义表 + 那条「target 不在"
            "枚举内」的参数化反例（放宽后它不再报违规）",
    ),
    Mutation(
        id="M13", side="be", path=PARADIGM, kind="replace",
        anchor='    "pending_verdict_counter": "unadjudicated",',
        new='    "pending_verdict_counter": "stale_evidence",',
        want="test_the_pending_verdict_contract_never_loosens",
        why="把 SR-9 的计数器从 `unadjudicated` 改指到 `stale_evidence`。两个计数器都在 "
            "`required_slice_counters` 里、都存在 ⇒ 校验器照样跑得通，但「待裁决条目数」从此"
            "与 `unadjudicated` 脱钩：slice 可以记 7 条 null 同时报 unadjudicated=0（正是"
            "「归零冒充进度」）。这条证明计数器名是被冻结的**值**，不是随便写的注释",
    ),
    Mutation(
        id="M14", side="be", path=PARADIGM, kind="insert",
        anchor='      "template_ref",',
        new='      "capability_verdict_stage",',
        want="test_pending_verdict_fields_are_conditional_not_global",
        wants=("test_the_reference_instance_passes", "test_every_scanned_slice_passes_the_schema"),
        why="把待裁决字段塞进无条件必填的 `required_entry`。这不是「更严」而是**另一种假绿**："
            "终态已定的 entry（E slice 那条 single_onlyoffice、四个 pilot 的 bidirectional）"
            "会被逼着为一个不存在的「待裁决」编造 stage —— `conditional_sections.why_not_global`"
            "写的同一条「additive 注入即死代码」。三个证人：有条件必填判据 + 参照实例正例 + "
            "scan_glob 全量正例（E slice 没有该字段，当场打红）",
    ),
    Mutation(
        id="M15", side="be", path=PARADIGM, kind="replace",
        anchor='      "capability_target_blocked_by": "non_empty_list"',
        new='      "capability_target_blocked_by": "list_or_whatever"',
        want="test_the_pending_verdict_contract_never_loosens",
        wants=("test_a_complete_pending_verdict_state_passes",),
        why="把 `capability_target_blocked_by` 的语义 kind 改成校验器不认识的词。判据要求校验器"
            "**fail closed**（未知/缺失语义 ⇒ 报违规，而不是跳过该字段）：若它 fail open，"
            "「加个字段不加语义」或「把语义写错一个字」就能让阻断项为空数组的待裁决态悄悄通过。"
            "两个证人：冻结语义表 + 右支正例（齐备的待裁决态在 fail closed 下会被这条无效声明"
            "打红，证明校验器真的读了语义而不是硬编码字段名）",
    ),
    Mutation(
        id="M16", side="be", path=PARADIGM, kind="replace",
        anchor='        "rule": "每个 entry 的 capability 落在 adjudication_criteria.capability_enum 内（AC 1.3），**或** capability 为 null 且 slice_schema.required_pending_verdict_fields 三字段按 pending_verdict_field_semantics 全部齐备（capability_verdict_stage 非空串 · capability_target 落在 capability_enum 内 · capability_target_blocked_by 非空数组）",',
        new='        "rule": "每个 entry 的 capability 落在 adjudication_criteria.capability_enum 内（AC 1.3），或为 null 时按另有约定处理",',
        want="test_the_sr3_rule_text_names_its_machine_declaration",
        why="把 SR-3 的规则文本退化成「为 null 时按另有约定处理」—— 机器声明"
            "（required_pending_verdict_fields / pending_verdict_field_semantics）一个字节没动，"
            "校验器行为完全不变，所以**没有任何行为判据会红**。但读规则的人从此不知道右支到底"
            "要求什么，散文与机器版漂移成两份真源。这条证明「同一件事声明两遍必须互锁」"
            "（与 M09 的三处 verdict 字段名同型）",
    ),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    """跑 CLI，并在前后各做一次 sha256 全量核验（kit 内部用的是 md5）。"""
    targets = sorted({REPO / m.path for m in MUTATIONS})
    before = {p: _sha256(p) for p in targets}
    rc = run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        description="migration paradigm 四新键判据变异检验",
        backend_args=BE_ARGS,
        # 实测 `pytest <守卫文件> -q --tb=no -rfE -p no:randomly` = 184 passed, 1 xfailed。
        #
        # 183 passed / 8 xfailed → 184 / 1：首轮实测时 D×7 + E×1 全是 `single_onlyoffice`
        # 且无对端结论，8 条逐 entry 判据全 xfail。2026-08-30 01:17 并发的 D 循环回填
        # 完成 step 3 调查，7 条 D 改成 `html_counterpart_verdict: exists` + `capability: null`
        # ⇒ 不再进 AP-1 的 single_onlyoffice 分母，其参数化条目消失（不是 XPASS）。
        # 同时守卫的分母判据从「len(单 OO 参数) >= 8」（会随欠账兑现而假红 = 把错值当基线）
        # 改成「slice 文件数 + entry 总数」，净 +1 passed。
        #
        # 184 → 197（2026-08-31 G1 收口）：SR-3 改成蕴含式后守卫净增 13 条 —— 7 条右支反例
        # （3 个「缺 pending 字段」从 schema 现读 + target 不在枚举内 + blocked_by 空数组 +
        # stage 空白串 + SR-9 计数说谎）、1 条右支正例（齐备待裁决态必须通过）、3 条
        # `scan_glob` 全量正例参数项（D/E/F 三份 slice）、2 条地板判据（语义 kind 与计数器名
        # 的**值**冻结 + 待裁决字段必须是有条件必填而非全局必填）+ 1 条散文互锁（SR-3 的
        # rule 文本必须点名它的机器声明，M16 的证人）。实测
        # `pytest <守卫文件> -q --tb=no -rfE -p no:randomly` = 198 passed, 1 xfailed。
        baseline_backend_passed=198,
    )
    print("\n── 还原核验（sha256）──")
    bad = []
    for path in targets:
        now = _sha256(path)
        rel = path.relative_to(REPO).as_posix()
        mark = "OK " if now == before[path] else "!! "
        print(f"  {mark}{rel}\n      before {before[path]}\n      after  {now}")
        if now != before[path]:
            bad.append(rel)
    if bad:
        print(f"[FATAL] 以下文件未逐字节还原：{bad}")
        return 5
    print("  全部目标文件 sha256 与变异前一致")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
