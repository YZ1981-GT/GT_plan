"""Task 67 structural pre-reconcile 守卫的变异检验。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 67

被检验的守卫：``backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py``

## 为什么每条变异都不是无效变异

structural pre-reconcile 型产物最贵的四类缺陷：

1. **空集恒真** —— 正文点名的一长串链路校验里 10 张表实测 0 行。把 `passed` 的来源从
   「schema 侧结构判据」偷偷换成「没有违反行」，报告会全绿而什么都没度量
   （M04~M09）。
2. **重生成没有真的重生成** —— source digest 的取值来源被掺进业务字段、或重生成路径被
   短路，报告里的「逐 entry source digest」就只是磁盘 manifest 的副本（M01~M03）。
3. **只报告变成偷偷修** —— 本任务要读一长串库表，只读性必须逐条可判；写入目标一旦从
   报告自己挪到 manifest / overlay，本任务就越界了（M24~M26）。
4. **六类计数被短路 / 单口径掩盖事实** —— 未裁决 / 假双向 / 未验收 / unreachable /
   evidence stale / planned-delete 各有独立派生分支；父入口双口径一旦合成一个，
   那条既 unreachable 又是 parent 重复入口的 entry 会从报告里消失（M13~M18）。

另有行级检测器（M10~M12）、结构错误归类（M19~M21）、入向义务与 BP（M22~M23、M27~M29）、
报告自身完整性（M30~M32）。

## 四态判定

RED（打红且正是预期那条）/ GREEN（守卫缺陷，必修）/ ANCHOR-MISS（脚本缺陷：锚点未命中
或命中 >1）/ WRONG-TEST（打红了但不是预期项）。只看退出码会把后三态误判成 RED。

## 用法（仓库根；PATH 上的 `python` 可能指向坏掉的解释器）

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task67_structural_pre_reconcile_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task67_structural_pre_reconcile_guards.py --run M01,M02
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task67_structural_pre_reconcile_guards.py --check-anchors

🔴 **禁后台执行**（孤儿 python + 前台同时变异 ⇒ RestoreFailed）；**绝不 `--restore`**。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CENSUS_LOCK = "backend/scripts/_census_lock.py"
GEN = "backend/scripts/gen/generate_task67_structural_pre_reconcile.py"

#: 🔴 kit 按**短 nodeid**（basename::类::方法）匹配新增失败集合 —— 带
#: `backend/tests/...` 前缀会让「实际打红的正是预期那条」被误判 WRONG-TEST。
_T = "test_task67_structural_pre_reconcile.py"

_SELF = f"{_T}::TestGuardSelfChecks"
_ONLY = f"{_T}::TestGeneratorOnlyReports"
_LOCK = f"{_T}::TestFiveWayLock"
_FACET = f"{_T}::TestPerEntryFacets"
_CHAIN = f"{_T}::TestChainChecksAreMeasured"
_COUNT = f"{_T}::TestCountersAndStructuralErrors"
_BP = f"{_T}::TestInboundObligationsAndBlockingPreconditions"
_IDEM = f"{_T}::TestGeneratorIsIdempotentAndCheckIsStrict"

#: 公共锚点：几乎每条落在生成器上的变异都会让现算报告与磁盘不同。
_BYTE_LOCK = f"{_IDEM}::test_check_matches_the_file_on_disk"


MUTATIONS: list[Mutation] = [
    # ═══ 一、重生成没有真的重生成 ═════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=GEN, kind="replace",
        anchor='    patched["approved_source_digest"] = current',
        new='    patched["approved_source_digest"] = approved',
        want=f"{_LOCK}::test_source_regeneration_reports_the_real_drift",
        wants=(
            f"{_LOCK}::test_entry_set_survives_the_rebuild",
            _BYTE_LOCK,
        ),
        why="内存补丁不再对齐当前源码 ⇒ `build_manifest()` 的 approved digest 复核门拒绝 ⇒ "
            "`rebuilt=None`、`rebuild_error` 非空。正文要求「从**最终源码**重新生成 mounts 与 "
            "source-backed manifest」，重生成失败时逐 entry 的 source digest 只剩磁盘副本，"
            "整份报告的 manifest 侧全部降级 —— 这条必须被守卫看见，而不是静静地报一个 error 字段",
    ),
    Mutation(
        id="M02", side="be", path=GEN, kind="replace",
        anchor='            "mounts": entry.get("mounts"),',
        new='            "mounts": entry.get("mounts"), "capability": entry.get("capability"),',
        want=f"{_SELF}::test_entry_source_digest_ignores_reviewed_business_fields",
        wants=(_BYTE_LOCK,),
        why="source digest 掺进 reviewed 业务字段（capability）。后果不是「多算一点」而是"
            "**改一句裁决就让全部 evidence 变 stale**：Task 70 每次刷新完，任何人调一次 "
            "overlay 的 capability 就把刚验收的 186 条 evidence 全部打成过期，AC 14.16 的"
            "失效轴从「源码变了」退化成「谁都能触发」",
    ),
    Mutation(
        id="M03", side="be", path=GEN, kind="replace",
        anchor='            "profile_source": entry.get("profile_source"),',
        new='            "profile_source": None,',
        want=f"{_SELF}::test_source_digest_tracks_every_source_side_facet",
        wants=(_BYTE_LOCK,),
        why="source digest 不再含 profile_source ⇒ 宿主换文件、readonly 绑定改法、"
            "inbound 引用数变化都不会让 digest 变。`mounts` 仍在兜底，所以「有 entry 变了」"
            "这条粗判据照样绿 —— 必须逐格断言每个源码侧事实都进了 digest，"
            "否则 AC 14.16 的失效轴会静静地少一条",
    ),

    # ═══ 二、空集恒真（本任务最核心的一族）════════════════════════════════
    Mutation(
        id="M04", side="be", path=GEN, kind="replace",
        anchor='        if not evaluated:',
        new='        if False:',
        want=f"{_SELF}::test_chain_check_evaluate_fails_closed_without_schema_requirements",
        wants=(_BYTE_LOCK,),
        why="允许一条链路检查**没有任何 schema 要求**。0 行的表上「逐行成立」恒真，"
            "schema 要求是这些检查唯一的约束力来源；允许为空等于允许把正文点名的十几条"
            "校验写成空壳还全绿（假绿第⑥源）",
    ),
    Mutation(
        id="M05", side="be", path=GEN, kind="replace",
        anchor='        if not db.readable:',
        new='        if False:',
        want=f"{_SELF}::test_db_unreadable_never_reads_as_passed",
        wants=(_BYTE_LOCK,),
        scope="    def evaluate(self, db: DbSnapshot, row_violations: Sequence[Any] = ()) -> dict[str, Any]:",
        offset=1,
        why="🔴 fail-open：库读不到时不再降级，而是继续走 schema 分支 —— 而 `DbSnapshot` "
            "此时是空的 ⇒ 所有 requirement 的 definition 都是 None ⇒ `satisfied=False`。"
            "看似安全，但 `row_denominator` 会变成 0 并带上「通过只来自 schema 侧」的说明，"
            "把「库连不上」伪装成「供给还没到」。本 spec 记录 fail-open 是最贵的一类缺陷",
    ),
    Mutation(
        id="M06", side="be", path=GEN, kind="replace",
        anchor='            fragment for fragment in self.must_contain if fragment not in (definition or "")',
        new='            fragment for fragment in () if fragment not in (definition or "")',
        want=f"{_SELF}::test_schema_requirement_detects_a_missing_fragment_not_just_presence",
        wants=(_BYTE_LOCK,),
        why="判据从「索引/CHECK 的定义里必须出现这几列」退化成「同名对象存在即可」。"
            "forcesave 五元键少一列 `initiated_by_participant_id` 时索引依然叫 "
            "`uq_wpfr_idempotency`，跨 participant 复用同一 Idempotency-Key 就不再 409 —— "
            "教训 16 的原样复现（改名/减列都能绕过只查存在的名单判据）",
    ),
    Mutation(
        id="M07", side="be", path=GEN, kind="replace",
        anchor='            "satisfied": definition is not None and not missing_fragments,',
        new='            "satisfied": True,',
        want=f"{_CHAIN}::test_counterfactual_arms_flip_the_check",
        wants=(
            f"{_SELF}::test_schema_requirement_detects_a_missing_fragment_not_just_presence",
            f"{_SELF}::test_db_unreadable_never_reads_as_passed",
            _BYTE_LOCK,
        ),
        why="把 schema 判据改成恒真。这是「判据是重言式」的教科书形态：所有检查照样全绿、"
            "报告照样自称把住了 UNIQUE/CHECK/trigger，而实际上抹掉哪条约束都无所谓。"
            "反事实多臂实验（逐臂在内存里删掉一条约束）就是为抓这条而存在",
    ),
    Mutation(
        id="M08", side="be", path=GEN, kind="replace",
        anchor="                if row_denominator",
        new="                if True",
        want=f"{_CHAIN}::test_empty_row_denominators_are_declared_never_silently_passed",
        wants=(_BYTE_LOCK,),
        why="0 行时不再解释「通过只来自 schema 侧」。少了这句，Tasks 68/69/70 的读者会把 "
            "10 条空分母检查读成「已在真实数据上验过」，而它们一行都没验过 —— "
            "正文明令如实报告，这句说明就是「如实」的载体",
    ),
    Mutation(
        id="M09", side="be", path=GEN, kind="replace",
        anchor='            "verified_on_rows": bool(row_denominator) and not row_violations,',
        new='            "verified_on_rows": True,',
        want=f"{_CHAIN}::test_empty_row_denominators_are_declared_never_silently_passed",
        wants=(_BYTE_LOCK,),
        why="0 行也声称「在行上验过」。`verified_on_rows` 是本报告区分「schema 把住了」与"
            "「真数据上验过」的唯一字段，恒真之后 Task 70 无法知道哪些链路还完全没被真实"
            "数据碰过",
    ),

    # ═══ 三、行级检测器退化 ═══════════════════════════════════════════════
    Mutation(
        id="M10", side="be", path=GEN, kind="replace",
        anchor='        if row["sha256"] != expected:',
        new='        if False:',
        want=f"{_CHAIN}::test_marker_violations_really_detect_a_tampered_digest",
        wants=(_BYTE_LOCK,),
        why="typed null marker 的 digest 不再与 `definitions.marker_digest()` 现算比对。"
            "AC 6.19 / Property 50 要求 optional child 只能用 registry 里的版本化 marker；"
            "不比 digest 就等于「marker_id 长得像就行」，被就地改过的 marker 照样通过",
    ),
    Mutation(
        id="M11", side="be", path=GEN, kind="replace",
        anchor='            if bundle[f"{slot}_slot_type"] != "definition":',
        new='            if False:',
        want=f"{_CHAIN}::test_projection_child_violations_detect_a_marker_substitution",
        wants=(_BYTE_LOCK,),
        why="projection_contract bundle 用 typed null marker 顶替必需 child 不再被抓到。"
            "这是正文点名的「projection contract approved child」那条 —— 顶替之后 "
            "projection 侧的 contract 实际不存在，而 bundle 仍是 approved",
    ),
    Mutation(
        id="M12", side="be", path=GEN, kind="replace",
        anchor='    "marker_violations": marker_violations,',
        new='    "marker_violations_unused": marker_violations,',
        want=f"{_CHAIN}::test_row_level_violation_functions_are_all_wired",
        why="声明的 `row_violation_fn` 与函数表脱钩 ⇒ 声明成了死字符串。additive 注入即"
            "死代码（假绿第①源）：检查表里写着「逐 marker 现算」，实际一次都不跑",
    ),

    # ═══ 四、父入口双口径与六类计数 ═══════════════════════════════════════
    Mutation(
        id="M13", side="be", path=GEN, kind="replace",
        anchor='            "counted_in_denominator": independent,',
        new='            "counted_in_denominator": True,',
        want=f"{_COUNT}::test_build_entry_rows_derives_the_denominator_flag_from_independence",
        wants=(
            f"{_FACET}::test_parent_duplicates_are_never_in_the_primary_denominator",
            f"{_FACET}::test_the_dual_denominator_hides_nothing",
            f"{_COUNT}::test_counters_recompute_from_the_recorded_entries",
            _BYTE_LOCK,
        ),
        why="正文逐字：「父入口不重复计数」。把 44 条 parent 重复入口算进主分母后，"
            "未验收从 142 虚增到 186、planned-delete 从 142 虚增到 186 —— "
            "同一份底稿的同一个入口被算两遍",
    ),
    Mutation(
        id="M14", side="be", path=GEN, kind="replace",
        anchor='    over_all = {kind: count(kind, scope=all_rows) for kind in REPORTED_COUNTER_KINDS}',
        new='    over_all = dict(reported)',
        want=f"{_COUNT}::test_build_counters_keeps_parent_duplicates_out_of_the_primary_denominator",
        wants=(
            f"{_FACET}::test_the_dual_denominator_hides_nothing",
            f"{_COUNT}::test_counters_recompute_from_the_recorded_entries",
            _BYTE_LOCK,
        ),
        why="🔴 副口径塌成主口径。实测 `xlsx/gt-g6-other-bond-ecl` 既是 "
            "`capability=unreachable` 又是 parent 重复入口 ⇒ 主口径下 `unreachable=0`。"
            "只报主口径会让这条**真实存在**的 unreachable entry 从报告里彻底消失，"
            "而正文明令如实报告 unreachable",
    ),
    Mutation(
        id="M15", side="be", path=GEN, kind="replace",
        anchor='        "unaccepted": not accepted,',
        new='        "unaccepted": False,',
        want=f"{_COUNT}::test_classify_entry_pins_each_verdict_to_its_own_fact",
        wants=(
            f"{_COUNT}::test_each_of_the_six_counters_is_asserted_separately",
            _BYTE_LOCK,
        ),
        why="「未验收」恒假。当前 published representation / test run 全为 0 行 ⇒ 186 条"
            "entry 一条都没验收；报 0 就是把「什么都没验」说成「全验完了」，"
            "正好是正文禁止的那种数字好看",
    ),
    Mutation(
        id="M16", side="be", path=GEN, kind="replace",
        anchor='        "evidence_stale": has_evidence and bool(row["source_digest"]["changed"]),',
        new='        "evidence_stale": bool(row["source_digest"]["changed"]),',
        want=f"{_COUNT}::test_stale_requires_evidence_to_exist_first",
        wants=(
            f"{_COUNT}::test_each_of_the_six_counters_is_asserted_separately",
            f"{_COUNT}::test_counters_recompute_from_the_recorded_entries",
            _BYTE_LOCK,
        ),
        why="🔴 stale 不再要求「先有 evidence」。`working_paper_sync_test_run` 实测 0 行，"
            "没有任何 run 可以「过期」；去掉 `has_evidence` 后报告会报出一个非零 stale 数，"
            "读者会以为「有 evidence 但过期了、重跑一下就好」，而真相是**根本没有 evidence**"
            "（未验收）。正文把这两类分开点名正是为了不混",
    ),
    Mutation(
        id="M17", side="be", path=GEN, kind="replace",
        anchor='        "planned_delete": planned_delete,',
        new='        "planned_delete": False,',
        want=f"{_COUNT}::test_classify_entry_pins_each_verdict_to_its_own_fact",
        wants=(
            f"{_COUNT}::test_each_of_the_six_counters_is_asserted_separately",
            _BYTE_LOCK,
        ),
        why="planned-delete 恒假 ⇒ Task 66 的 215 项清册在本报告里等于没被消费。"
            "正文要求本任务如实报告 planned-delete 计数并与 deletion plan 双向核对",
    ),
    Mutation(
        id="M18", side="be", path=GEN, kind="replace",
        anchor='                if measurable_stale',
        new='                if True',
        want=f"{_COUNT}::test_the_empty_stale_denominator_note_appears_only_when_it_is_empty",
        wants=(
            f"{_COUNT}::test_stale_is_reported_and_never_required_to_be_zero",
            _BYTE_LOCK,
        ),
        why="空分母不再解释。`evidence_stale=0` 单独看与「已刷新」不可区分；"
            "正文逐字「允许报告 stale，不要求 stale 清零」，那句解释是本报告里承载这条"
            "语义的唯一位置",
    ),

    # ═══ 五、结构错误归类 ═════════════════════════════════════════════════
    Mutation(
        id="M19", side="be", path=GEN, kind="replace",
        anchor="    if not regeneration.digests_agree:",
        new="    if False:",
        scope='    errors: list[dict[str, Any]] = []',
        offset=2,
        want=f"{_COUNT}::test_structural_errors_fire_on_a_synthetic_drift_and_stay_silent_without_one",
        wants=(
            f"{_COUNT}::test_the_source_digest_drift_is_reported_as_a_structural_error",
            _BYTE_LOCK,
        ),
        why="source digest 漂移不再进 structural_errors。正文逐字：「profile 降级、"
            "计划外 legacy/unreachable 或 digest/owner/rollback 缺失**立即报结构错误**」。"
            "漂移意味着磁盘 manifest 已不是最终源码的 manifest —— 这是本轮最重要的一条"
            "结构结论，被吞掉之后 Tasks 68/69/70 会拿过期 manifest 当真源",
    ),
    Mutation(
        id="M20", side="be", path=GEN, kind="replace",
        anchor='            if not str(owner.get("deletion_owner_task") or "").strip():',
        new='            if False:',
        want=f"{_COUNT}::test_missing_binding_detector_catches_each_of_the_four",
        wants=(_BYTE_LOCK,),
        why="「owner 缺失」这一条分支被短路。当前清册没有缺失项，所以**只断言「现在没有"
            "违反」的判据对这条毫无信息量**（假绿第②源）；守卫必须逐条造合成缺失项喂回"
            "检测器。owner 缺失意味着 Task 72 删除时找不到负责人",
    ),
    Mutation(
        id="M21", side="be", path=GEN, kind="replace",
        anchor='                "kind": "source_digest_drifted_from_reviewed_overlay",',
        new='                "kind": "profile_downgraded",',
        want=f"{_COUNT}::test_structural_errors_fire_on_a_synthetic_drift_and_stay_silent_without_one",
        wants=(
            f"{_COUNT}::test_the_source_digest_drift_is_reported_as_a_structural_error",
            _BYTE_LOCK,
        ),
        why="漂移被归成另一类结构错误。封闭词表里两个 kind 都合法 ⇒ 词表判据不会红；"
            "但 Tasks 68/69 按 kind 消费，归错类等于把「manifest 过期」这条报给了"
            "「profile 降级」的处理方",
    ),

    # ═══ 六、入向义务与只读性 ═════════════════════════════════════════════
    Mutation(
        id="M22", side="be", path=GEN, kind="replace",
        anchor='    "backend/app/services/workpaper_sync/opaque_entry_gate.py",',
        new='    "backend/data/workpaper_sync_a16_a17_word_chain_adjudication.json",',
        want=f"{_BP}::test_inbound_scan_recomputes_and_contains_the_real_targets",
        wants=(_BYTE_LOCK,),
        why="从生成期反向门里移走 `opaque_entry_gate.py` —— 而它正是唯一带 "
            "`adjudication_owner_task=\"67\"` 结构化归属的生产模块（`ENTRY_ID_NAMESPACE_"
            "SPLIT_NOTE`）。守卫把五条路径**写死**而不是迭代这个常量，正是教训 16："
            "迭代常量的判据在常量被删空时照样绿",
    ),
    Mutation(
        id="M23", side="be", path=GEN, kind="replace",
        anchor='                    "structured_ownership": any(',
        new='                    "structured_ownership": False and any(',
        want=f"{_BP}::test_inbound_scan_recomputes_and_contains_the_real_targets",
        wants=(_BYTE_LOCK,),
        why="所有入向义务都降级成「散文提及」。区分「机器可读的归属登记」与「文档里提了"
            "一句 Task 67」是本报告的价值所在 —— 全都算散文之后，`ENTRY_ID_NAMESPACE_"
            "SPLIT_NOTE` 这类真正等着 Task 67 裁决的登记就淹没在几十处提及里",
    ),
    Mutation(
        id="M24", side="be", path=GEN, kind="replace",
        anchor="    _SQL_TRIGGERS,",
        new="    # _SQL_TRIGGERS 从只读声明清单里被拿掉（变异）",
        want=f"{_ONLY}::test_the_declared_readonly_sql_list_contains_the_real_targets",
        wants=(_BYTE_LOCK,),
        why="只读 SQL 声明清单里去掉 trigger 查询。清单是「本任务只 SELECT」这条承诺的"
            "可核查载体；漏一条就等于有一条 SQL 没被任何判据看过 —— 而 trigger 定义正是"
            "10 条空分母检查的主要结构依据",
    ),
    Mutation(
        id="M25", side="be", path=GEN, kind="replace",
        anchor="    async with engine.connect() as conn:  # 只 connect，不 begin ⇒ 没有写事务",
        new="    async with engine.begin() as conn:  # 变异：打开写事务",
        want=f"{_ONLY}::test_no_destructive_or_write_calls",
        wants=(_BYTE_LOCK,),
        why="🔴 `connect()` 换成 `begin()` ⇒ 打开写事务。本任务对生产库的唯一承诺就是"
            "只读；开了写事务之后，任何一处误写都会真的提交。memory 明写「PG 只读，"
            "禁经本任务写库」",
    ),
    Mutation(
        id="M26", side="be", path=GEN, kind="replace",
        anchor='    os.replace(tmp, OUTPUT_PATH)',
        new='    os.replace(tmp, MANIFEST_PATH)',
        want=f"{_ONLY}::test_write_text_only_targets_the_report",
        wants=(
            f"{_ONLY}::test_the_disk_manifest_is_not_rewritten",
            _BYTE_LOCK,
        ),
        why="🔴 写入目标从报告挪到 **entry manifest**。正文只授权报告；覆盖 manifest 等于"
            "本任务替复核方签了「mount diff 已复核」，还会把并发会话在用的文件换掉",

    ),

    # ═══ 七、BP 与报告自身完整性 ══════════════════════════════════════════
    Mutation(
        id="M27", side="be", path=GEN, kind="replace",
        anchor='BP_ID_RE = re.compile(r"BP-67-\\d+")',
        new='BP_ID_RE = re.compile(r"BP-\\d+")',
        want=f"{_SELF}::test_bp_id_regex_is_task_scoped_and_rejects_the_global_form",
        wants=(_BYTE_LOCK,),
        why="BP 编号退回全局形态。全局 `BP-NN` 已被 Tasks 60/61/63/64 **重复占用**（同号"
            "不同义，Task 64 到 BP-22、Task 63 也有 BP-18~BP-20），接回去只会制造第三份"
            "冲突。task-scoped 前缀是这套编号唯一的去歧义手段",
    ),
    Mutation(
        id="M28", side="be", path=GEN, kind="replace",
        anchor='                "task67_disposition": "reported_not_cleared",',
        new='                "task67_disposition": "cleared",',
        want=f"{_BP}::test_blocking_preconditions_are_built_from_their_inputs_not_from_constants",
        wants=(
            f"{_BP}::test_bp_67_5_reports_bp_66_1_without_clearing_it",
            _BYTE_LOCK,
        ),
        why="🔴 BP-66-1（替代面 19/22 对生产宿主不可达）的 owner 字段写的就是 67。"
            "把处置改成 `cleared` = 在没有改任何前端宿主的情况下宣称解除 —— "
            "下游 Task 72 会以为统一 bridge 已经接线，Stage B 删掉 legacy 后没有可用路径",
    ),
    Mutation(
        id="M29", side="be", path=GEN, kind="replace",
        anchor='                    1 for r in db.definition_bundles if r["state"] == "approved"',
        new="                    1 for r in db.definition_bundles if False  # Task 61 旧数：恒 0",
        want=f"{_BP}::test_blocking_preconditions_are_built_from_their_inputs_not_from_constants",
        wants=(
            f"{_BP}::test_bp_67_4_recomputes_the_bundle_supply_instead_of_citing_task61",
            _BYTE_LOCK,
        ),
        why="🔴 BP 引用 Task 61 的**旧数**（当时实测 approved bundle=1）而不是现算。"
            "本轮实测已增长到 3（Task 65 新发布了两条 opaque authority bundle）。"
            "「引用上游旧数」是本 spec 反复踩的坑：结论会在供给变化后静静地过期",
    ),
    Mutation(
        id="M30", side="be", path=GEN, kind="replace",
        anchor='        strip_census({key: value for key, value in report.items() if key != "report_digest"})',
        new='        strip_census({"task": report["task"]})',
        want=f"{_IDEM}::test_report_digest_covers_everything_except_itself",
        wants=(_BYTE_LOCK,),
        why="`report_digest` 只覆盖一个字段 ⇒ 报告可以被任意手改而 digest 不变。"
            "本报告是 Tasks 68/69/70 的输入，能被手改而守卫不红，整份结构结论就没有"
            "约束力（与 Task 66 清册同型的问题）",
    ),
    Mutation(
        id="M31", side="be", path=GEN, kind="replace",
        anchor='    return sorted(set(axes))',
        new='    return []',
        want=f"{_FACET}::test_evidence_rerun_axes_are_derived_live_not_just_recorded",
        wants=(
            f"{_FACET}::test_evidence_rerun_axes_use_the_production_stale_vocabulary",
            _BYTE_LOCK,
        ),
        why="逐 entry 的 evidence 重跑集合恒空。正文明确要求「按 source/manifest/profile/"
            "definition/bundle/candidate 变化逐 entry 生成 evidence 重跑集合」，"
            "而 Task 70 正是靠这份集合决定刷新哪些轴；空集会让它以为无需重跑",
    ),
    Mutation(
        id="M32", side="be", path=GEN, kind="replace",
        anchor='                "has_landing": entry_id in plan_items_by_entry,',
        new='                "has_landing": True,',
        want=f"{_COUNT}::test_build_entry_rows_derives_the_denominator_flag_from_independence",
        wants=(
            f"{_LOCK}::test_deletion_plan_landing_is_two_way",
            _BYTE_LOCK,
        ),
        why="deletion plan 落点恒真 ⇒ 双向核对的一侧失效。正文要求与 Task 66 deletion plan "
            "**双向**核对、且「计划外 legacy/unreachable 立即报结构错误」；"
            "恒真之后任何计划外的 legacy entry 都会被当成已有落点",
    ),

    # ═══ 八、普查免疫（BP-72-8 的修复：普查派生量不进冻结基线，但仍现算断言语义）═══
    Mutation(
        id="M33", side="be", path=CENSUS_LOCK, kind="replace",
        anchor="            if child in projected:",
        new="            if False:  # mutated: 不再对入向普查做投影",
        want=f"{_IDEM}::test_check_matches_the_file_on_disk",
        wants=(
            f"{_BP}::test_inbound_scan_recomputes_and_contains_the_real_targets",
            f"{_IDEM}::test_report_digest_covers_everything_except_itself",
        ),
        why="🔴 `strip_census` 不再投影 `inbound_obligations` ⇒ 整块进锁，回到 BP-72-8："
            "任何新落盘且正文提到本任务的产物都让逐字节锁打红。这条变异必须让「投影后仍相等」"
            "与「新增尾巴不改 digest」两条判据同时红",
    ),
    Mutation(
        id="M34", side="be", path=GEN, kind="replace",
        anchor='CENSUS_KEYS: tuple[str, ...] = ("inbound_obligations", "census_contract.measured")',
        new='CENSUS_KEYS: tuple[str, ...] = ("inbound_obligations", "census_contract.measured", "counters")',
        want=f"{_IDEM}::test_check_matches_the_file_on_disk",
        wants=(f"{_IDEM}::test_report_digest_covers_everything_except_itself",),
        why="把**非普查**字段（六类计数）也剔进 census ⇒ 剔多了。正文要求「不得削弱真正的 "
            "stale 轴」：counters 一旦不进锁，未验收/未裁决/stale 被改成任意数字都不会红",
    ),
    Mutation(
        id="M35", side="be", path=CENSUS_LOCK, kind="replace",
        anchor='        "all_hold": all(checks.values()),',
        new='        "all_hold": True,  # mutated: 普查语义断言恒真',
        want=f"{_BP}::test_inbound_scan_recomputes_and_contains_the_real_targets",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="把普查语义断言改成恒真 —— 「剔除 ≠ 不管」退化成「不看了」。投影只锁那 5 条真实"
            "目标，语义断言是唯一还在看「普查器是不是真的在普查」的东西",
    ),
    Mutation(
        id="M36", side="be", path=GEN, kind="replace",
        anchor='        "scan_reaches_beyond_the_required_targets": bool(paths - set(REQUIRED_INBOUND_TARGETS)),',
        new='        "scan_reaches_beyond_the_required_targets": True,  # mutated: 恒真',
        want=f"{_BP}::test_inbound_scan_recomputes_and_contains_the_real_targets",
        wants=(f"{_IDEM}::test_check_matches_the_file_on_disk",),
        why="🔴 最隐蔽的一条：普查器被「修」成只返回那 5 条写死目标时，投影比对**照样绿**"
            "（投影本来就只留那 5 条）。`scan_reaches_beyond_the_required_targets` 是唯一能"
            "抓到它的判据；恒真之后「普查器退化成硬编码名单」就没人管了",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files={
                "be": "backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py",
            },
            repo=REPO,
            description="Task 67 structural pre-reconcile 守卫变异检验",
            backend_args=["backend/tests/workpaper_sync/test_task67_structural_pre_reconcile.py"],
            allow_dirty_baseline=True,
        )
    )
