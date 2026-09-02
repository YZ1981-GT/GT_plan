# -*- coding: utf-8 -*-
"""Task 37 守卫的变异检验（Excel identity-aware extractor 与共用 verifier）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 37
Properties: P23 / P24 / P27 / P29 / P60 / P66

═══ 为什么必须做 ═══

「写完守卫没打红 = 守卫有缺陷，不是代码没问题」。本 spec 已三次实测到「共享错误码让较早
分支永久不可达 ⇒ 该分支守卫永久 GREEN」，因此本脚本刻意为**每一条身份/保护/预算判据**
各准备一条变异，逐条要求 RED。

═══ 已踩过的坑（本脚本按它们写死） ═══

* `want` 必须是**短 nodeid**（`file.py::Class::test`，不带目录前缀）—— 带路径前缀会让
  整轮记成 WRONG-TEST；
* pytest 参数传 `-rfE`（不是 `-rf`），否则 error 态的用例名收不进失败集合；
* 锚点不得含 `\n` —— 工作树是 CRLF，跨行锚点必 ANCHOR-MISS；
* `_mutation_kit.span` 会把绿色控制项映射成 RED，读数时别误判。

用法::

    py -3 backend/scripts/diagnose/mutate_task37_excel_extract_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task37_excel_extract_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task37_excel_extract_guards.py --run all --out tmp.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts
from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

EXTRACT = "backend/app/services/workpaper_sync/excel_extract.py"
BASE = "backend/app/services/workpaper_sync/adapters/base.py"
MERGE = "backend/app/services/workpaper_sync/merge.py"
T37 = "test_task37_excel_extract.py"
T14 = "test_task14_merge_conflicts.py"

MUTATIONS: list[Mutation] = [
    # ── Property 66：identity 载体保留与锚点 ──────────────────────────
    Mutation(
        id="M01", side="be", path=EXTRACT, kind="replace",
        anchor="        inventory.resolved_sheet_by is not None",
        new="        False",
        want=f"{T37}::TestProperty66IdentityRetention"
             "::test_forbidden_anchor_path_has_its_own_error_type",
        why="关掉「被证伪锚点」判据后，`resolved_sheet_by='sheet_id'` 会被放行 —— "
            "Task 5 已证伪 sheet_id（OO 每次保存重编号），放行等于按错的 sheet 反读",
        tags=("p66",),
    ),
    Mutation(
        id="M02", side="be", path=EXTRACT, kind="replace",
        anchor="    if dynamic_tables and inventory.resolved_sheet_by is None:",
        new="    if False:",
        want=f"{T37}::TestProperty66IdentityRetention::test_uuid_column_wiped_blocks_engine",
        why="删掉「整列 UUID 被删 ⇒ 载体缺失」这条后，None 会掉进锚点判据被报成"
            "「锚点用错」—— 错误原因指错地方，且真正的锚点误用分支变得不可分辨",
        tags=("p66", "ordering"),
    ),
    Mutation(
        id="M03", side="be", path=EXTRACT, kind="replace",
        anchor="    lost_rows = sorted(set(expected.row_uuids.values()) - observed.identities)",
        new="    lost_rows = []",
        want=f"{T37}::TestProperty66IdentityRetention"
             "::test_lost_row_identity_is_retention_failure_not_silent_pass",
        why="丢一个 row UUID 不再打红 ⇒ 该行数据静默少读，Property 66 的核心承诺失效",
        tags=("p66",),
    ),
    Mutation(
        id="M04", side="be", path=EXTRACT, kind="replace",
        anchor="    if expected_span != observed_span:",
        new="    if expected.table_ref != observed.table_ref:",
        want=f"{T37}::TestProperty66IdentityRetention::test_row_insert_is_not_retention_failure",
        why="把「列跨度相等」换成「Table ref 逐字相等」后，OO 合法插行会被报成载体漂移 —— "
            "反向自检：判据过严时调用方只能整体关掉这道门",
        tags=("p66", "reverse"),
    ),
    Mutation(
        id="M05", side="be", path=EXTRACT, kind="replace",
        anchor="    if not region.contains_column(binding.uuid_column):",
        new="    if False:",
        want=f"{T37}::TestEngineEntryGates::test_uuid_column_outside_table_span_fails_closed",
        why="UUID 列落在 Table 列跨度外仍放行 ⇒ 插删行时 identity 与数据行错位",
        tags=("p66",),
    ),
    # ── Property 23：动态行身份不使用下标 ────────────────────────────
    Mutation(
        id="M06", side="be", path=EXTRACT, kind="replace",
        anchor="        if disposition is EmptyRowIdentityDisposition.assign_new_id:",
        new="        if True:",
        want=f"{T37}::TestAnomalyClassesAreDistinctAndReachable"
             "::test_empty_identity_on_reject_table_becomes_schema_anomaly",
        why="无条件给空 UUID 分配新 ID ⇒ 契约声明 delete_policy=reject 的表也被静默改结构，"
            "Requirement 6.15 的三分类退化成一类",
        tags=("p23",),
    ),
    Mutation(
        id="M07", side="be", path=EXTRACT, kind="replace",
        anchor="    if not table.has_dynamic_rows:",
        new="    if False:",
        want=f"{T37}::TestProperty23RowIdentityIsNotPositional"
             "::test_empty_identity_classification_is_contract_driven",
        why="静态表不再判 reject ⇒ `classify_empty_row_identity` 的三个取值缩到两个，"
            "其中一条永久不可达",
        tags=("p23",),
    ),
    Mutation(
        id="M08", side="be", path=EXTRACT, kind="replace",
        anchor="        if candidate not in blocked:",
        new="        if True:",
        want=f"{T37}::TestProperty23RowIdentityIsNotPositional"
             "::test_minted_identity_never_collides_with_tombstones",
        why="不再避让已占用/已 tombstone 的 ID ⇒ 新行会复用已删除 UUID，"
            "原行数据串到新行（Requirement 6.15 明令禁止）",
        tags=("p23",),
    ),
    Mutation(
        id="M09", side="be", path=EXTRACT, kind="replace",
        anchor="    reused = tuple(sorted(set(identity_by_row.values()) & tombstone_set))",
        new="    reused = ()",
        want=f"{T37}::TestAnomalyClassesAreDistinctAndReachable"
             "::test_tombstoned_identity_reuse_has_its_own_kind",
        why="tombstone 复现不再登记 ⇒ 已删除 UUID 重新出现被当正常行合并",
        tags=("p23", "anomaly"),
    ),
    # ── 五类异常各自可达、各有专属 kind ──────────────────────────────
    Mutation(
        id="M10", side="be", path=EXTRACT, kind="replace",
        anchor="    for identity in scan.duplicate_identities:",
        new="    for identity in ():",
        want=f"{T37}::TestAnomalyClassesAreDistinctAndReachable"
             "::test_duplicate_identity_with_same_values_is_identity_anomaly_only",
        why="复制行产生的重复 UUID 不再形成结构冲突 ⇒ 两行争同一个身份被静默合并",
        tags=("anomaly",),
    ),
    Mutation(
        id="M11", side="be", path=EXTRACT, kind="replace",
        anchor="        if len(distinct) > 1:",
        new="        if False:",
        want=f"{T37}::TestAnomalyClassesAreDistinctAndReachable"
             "::test_duplicate_identity_with_divergent_values_adds_multi_location",
        why="同 stable key 多位置异值不再报 ⇒ 第一个位置静默胜出，另一处审计师录入丢失",
        tags=("anomaly",),
    ),
    Mutation(
        id="M12", side="be", path=EXTRACT, kind="replace",
        anchor="            normalize_value(raw, spec.value_type)",
        new="            pass",
        want=f"{T37}::TestAnomalyClassesAreDistinctAndReachable"
             "::test_type_normalization_failure_keeps_raw_value",
        why="不再尝试规范化 ⇒ 类型转换失败静默通过，坏值直接进 projection 而没有裁决记录",
        tags=("anomaly",),
    ),
    # ── Property 24：受保护字段 ──────────────────────────────────────
    Mutation(
        id="M13", side="be", path=EXTRACT, kind="replace",
        anchor="    if baseline_formulas is not None:",
        new="    if False:",
        want=f"{T37}::TestProperty24ProtectedFieldConflicts"
             "::test_formula_text_only_tamper_is_invisible_to_value_merge_and_must_be_补齐",
        why="关掉公式层比对 ⇒ 「把 =G7-D7 改写成 =G7-D7+1」在缓存值相同时完全不可见，"
            "Property 24 要求的 protected 冲突永不出现",
        tags=("p24",),
    ),
    Mutation(
        id="M14", side="be", path=EXTRACT, kind="replace",
        anchor="                kind=FormulaTamperKind.formula_text_changed,",
        new="                kind=FormulaTamperKind.literal_value_changed,",
        want=f"{T37}::TestProperty24ProtectedFieldConflicts"
             "::test_four_tamper_kinds_are_each_reachable_and_distinct",
        why="把「公式文本被改写」归成「字面量被改」⇒ 四类 tamper 缩成三类，"
            "诊断指向错误的成因",
        tags=("p24",),
    ),
    Mutation(
        id="M15", side="be", path=EXTRACT, kind="replace",
        # `if missing:` 在文件里出现 3 次 ⇒ 用 scope 相对定位（绝对行号一改文件就失效，
        # 本轮实测过一次：加了 10 行注释之后 M15/M33 的 line 全指错）。
        anchor="    if missing:",
        scope="def assert_protected_tamper_fully_reported(",
        offset=21,
        new="    if False:",
        want=f"{T37}::TestProperty24ProtectedFieldConflicts"
             "::test_formula_text_only_tamper_is_invisible_to_value_merge_and_must_be_补齐",
        why="`assert_protected_tamper_fully_reported` 不再打红 ⇒ extract 侧发现了篡改而"
            "merge 侧没有 protected 冲突时静默通过（跨层判据失效）",
        tags=("p24",),
    ),
    Mutation(
        id="M16", side="be", path=EXTRACT, kind="replace",
        anchor="        if key in seen:",
        new="        if False:",
        want=f"{T37}::TestProperty24ProtectedFieldConflicts"
             "::test_no_double_reporting_when_value_layer_already_conflicted",
        why="值层已生成 protected 冲突时仍重复补齐 ⇒ 撞破 ConflictSet 的 "
            "UNIQUE(stable_field_key,row_key,oo_location)",
        tags=("p24",),
    ),
    Mutation(
        id="M17", side="be", path=EXTRACT, kind="replace",
        anchor="        data_only=True,",
        new="        data_only=False,",
        want=f"{T37}::TestBaselineExtract"
             "::test_protected_field_value_is_computed_not_formula_text",
        why="把公式文本当 projection 值 ⇒ 每个公式字段都变成 type_normalization_failure "
            "schema 冲突，protected 冲突（Property 24）永久不可达",
        tags=("p24",),
    ),
    # ── Property 29：反读等值 ────────────────────────────────────────
    Mutation(
        id="M18", side="be", path=EXTRACT, kind="replace",
        anchor="        if _is_editable(key, contract)",
        new="        if True",
        want=f"{T37}::TestProperty29RoundtripEquivalence"
             "::test_roundtrip_compares_only_editable_fields",
        why="把公式/auto-source 混进等值比较 ⇒ verifier 在真实数据上恒不通过，"
            "调用方只能整体关掉它",
        tags=("p29",),
    ),
    Mutation(
        id="M19", side="be", path=EXTRACT, kind="replace",
        # 🔴 不能把 `if left.value_type is not right.value_type:` 整行换成 `return True`：
        #    紧随其后的 `return False` 会变成过深缩进 ⇒ IndentationError ⇒ 整轮 collection
        #    error，判定记成 WRONG-TEST 而不是 RED（实测踩过）。改成短路掉真正的比较，
        #    语法保持合法。
        anchor="        return normalize_value(left.value, left.value_type) == normalize_value(",
        new="        return True or normalize_value(",
        want=f"{T37}::TestProperty29RoundtripEquivalence::test_single_cell_drift_is_located",
        why="类型化相等恒真 ⇒ 反读等值判据空转，写错的格照样发布（AC 8.11 失守）",
        tags=("p29",),
    ),
    Mutation(
        id="M20", side="be", path=EXTRACT, kind="replace",
        anchor="        if not self.equivalent and not (self.first_difference or \"\").strip():",
        # `RoundtripReport` 与 `UnmanagedRegionReport` 的同款判据同名同形 ⇒ 用 scope 相对
        # 定位（`scope` 行唯一），比绝对行号稳：文件一改绝对行号就失效。
        scope="class RoundtripReport:",
        offset=10,
        new="        if False:",
        want=f"{T37}::TestProperty29RoundtripEquivalence"
             "::test_report_cannot_claim_inequivalence_without_location",
        why="允许「不等值但不说哪里不等」⇒ Requirement 6.10 要求的「指出首个漂移位置」失效",
        tags=("p29",),
    ),
    # ── Property 60：预算 ────────────────────────────────────────────
    Mutation(
        id="M21", side="be", path=EXTRACT, kind="replace",
        anchor="        self._limits.assert_table_rows(self._rows[table_key], table_key=table_key)",
        new="        pass",
        want=f"{T37}::TestProperty60BudgetsFailVisible::test_row_budget_is_wired_into_extract",
        why="行预算不再判 ⇒ 100000 行的表读到 OOM 而不是 fail visible（Requirement 14.11）",
        tags=("p60",),
    ),
    Mutation(
        id="M22", side="be", path=EXTRACT, kind="replace",
        anchor="        self._limits.assert_projection_fields(self._field_count)",
        new="        pass",
        want=f"{T37}::TestProperty60BudgetsFailVisible::test_field_budget_is_wired_into_extract",
        why="field 预算不再判 ⇒ 单 projection 超 200000 字段时无界增长",
        tags=("p60",),
    ),
    Mutation(
        id="M23", side="be", path=EXTRACT, kind="replace",
        anchor="    return max(1, limits.peak_memory_budget_bytes // limits.chunk_bytes)",
        new="    return 64",
        want=f"{T37}::TestProperty60BudgetsFailVisible"
             "::test_rows_per_chunk_is_derived_from_limits_not_hardcoded",
        why="块大小写死 ⇒ 预算与分块脱钩，调小内存预算后分块仍是老样子（第二真源）",
        tags=("p60",),
    ),
    Mutation(
        id="M24", side="be", path=EXTRACT, kind="replace",
        anchor="            sidecar_path.unlink(missing_ok=True)  # type: ignore[union-attr]",
        new="            pass",
        want=f"{T37}::TestProperty60BudgetsFailVisible"
             "::test_budget_abort_leaves_no_truncated_sidecar",
        why="越界中止后留下半成品 sidecar ⇒ 下游把被截断的 gzip 当完整 projection 读"
            "（Requirement 14.11 的「不得截断」）",
        tags=("p60",),
    ),
    # ── 流式 sidecar ────────────────────────────────────────────────
    Mutation(
        id="M25", side="be", path=EXTRACT, kind="replace",
        anchor="            filename=\"\", fileobj=self._raw, mode=\"wb\", mtime=0, compresslevel=9",
        new="            fileobj=self._raw, mode=\"wb\"",
        want=f"{T37}::TestStreamingSidecarAndChunking::test_sidecar_bytes_are_reproducible",
        why="gzip 头写进 mtime 与 FNAME ⇒ 同一 projection 两次导出字节不同，evidence digest 漂移",
        tags=("sidecar",),
    ),
    # ── 未管理区域 ──────────────────────────────────────────────────
    Mutation(
        id="M26", side="be", path=EXTRACT, kind="replace",
        anchor="            if ref and ref not in managed:",
        new="            if ref:",
        want=f"{T37}::TestUnmanagedRegionVerifier::test_managed_cell_change_is_allowed",
        why="把受管格算进未管理区域 ⇒ materialize 每次都被自己的写入打红，"
            "调用方只能整体关掉这道门",
        tags=("unmanaged", "reverse"),
    ),
    Mutation(
        id="M27", side="be", path=EXTRACT, kind="replace",
        anchor="            if limit_count is not None and seen >= limit_count:",
        new="            if False:",
        want=f"{T37}::TestUnmanagedRegionVerifier"
             "::test_appending_shared_strings_is_allowed_but_editing_existing_is_not",
        why="不再只比前 N 个 `<si>` ⇒ 合法追加新字符串被判成未管理区域异动（假红）",
        tags=("unmanaged", "reverse"),
    ),
    Mutation(
        id="M28", side="be", path=EXTRACT, kind="replace",
        anchor="        if base.aspects[aspect] != target.aspects[aspect]:",
        new="        if False:",
        want=f"{T37}::TestUnmanagedRegionVerifier::test_protected_part_change_is_caught",
        why="未管理区域比对恒等价 ⇒ drawing/chart/pivot 被改也照常发布（Requirement 6.17 失守）",
        tags=("unmanaged",),
    ),
    # ── commit 前置门 ───────────────────────────────────────────────
    Mutation(
        id="M29", side="be", path=EXTRACT, kind="replace",
        anchor="        if not self.roundtrip.equivalent:",
        new="        if False:",
        want=f"{T37}::TestVerifyBeforeCommitGate"
             "::test_roundtrip_failure_blocks_commit_with_its_own_error",
        why="反读不等值仍允许交 commit ⇒ AC 8.11 的「不得推进任何指针」失守",
        tags=("commit",),
    ),
    Mutation(
        id="M30", side="be", path=EXTRACT, kind="replace",
        anchor="        if not self.formulas.intact:",
        new="        if False:",
        want=f"{T37}::TestVerifyBeforeCommitGate"
             "::test_formula_drift_blocks_commit_with_its_own_error",
        why="公式区域被改仍允许交 commit ⇒ AC 6.6 的「公式结果不得被覆盖」失守",
        tags=("commit",),
    ),
    Mutation(
        id="M31", side="be", path=EXTRACT, kind="replace",
        anchor="        self.unmanaged.assert_equivalent()",
        new="        pass",
        want=f"{T37}::TestVerifyBeforeCommitGate"
             "::test_unmanaged_drift_blocks_commit_with_its_own_error",
        why="未管理区域异动仍允许交 commit ⇒ Word-only/Excel 未管理内容被静默改写",
        tags=("commit",),
    ),
    Mutation(
        id="M32", side="be", path=EXTRACT, kind="replace",
        anchor="        if not self.roundtrip.compared_keys and not self.extracted.projection.values:",
        new="        if False:",
        want=f"{T37}::TestVerifyBeforeCommitGate::test_empty_projection_is_not_a_pass",
        why="零次比对判「全过」⇒ identity 定位静默落空或写入没落盘时照样发布（空转恒真）",
        tags=("commit",),
    ),
    Mutation(
        id="M33", side="be", path=EXTRACT, kind="replace",
        anchor="    if not findings:",
        scope="def verify_formula_regions(",
        offset=15,
        new="    if True:",
        want=f"{T37}::TestVerifyBeforeCommitGate"
             "::test_formula_drift_blocks_commit_with_its_own_error",
        why="`verify_formula_regions` 恒返回 intact=True ⇒ 公式篡改结论被吞掉",
        tags=("commit",),
    ),
    # ── engine 入口门 ───────────────────────────────────────────────
    Mutation(
        id="M34", side="be", path=EXTRACT, kind="replace",
        anchor="    if definitions.bundle is None:",
        new="    if False:",
        want=f"{T37}::TestEngineEntryGates"
             "::test_handmade_definitions_without_bundle_are_rejected",
        why="放行手工拼装的 FrozenEntryDefinitions ⇒ bundle/contract/authority 三向锁死全部落空",
        tags=("gate",),
    ),
    Mutation(
        id="M35", side="be", path=EXTRACT, kind="replace",
        # `_ = (` 会让后面的关键字实参落进元组 ⇒ SyntaxError；`dict(` 保持语法合法。
        anchor="    assert_contract_identity_frozen(",
        new="    _ = dict(",
        want=f"{T37}::TestEngineEntryGates::test_contract_digest_drift_is_rejected",
        why="不再比对 contract canonical digest 与 bundle slot ⇒ 可按当前 alias 顶替历史契约"
            "（Property 28 失守）",
        tags=("gate",),
    ),
    Mutation(
        id="M36", side="be", path=EXTRACT, kind="replace",
        # 直接把 `raise` 换掉会让后面的消息串与 `)` 悬空 ⇒ SyntaxError；改成让绑定「凭空
        # 出现」，走的正是被禁止的那条路：按契约声明列猜。
        anchor="    bound = binding.dynamic_column_columns.get(table.table_key)",
        new="    bound = {spec.column_key: cell.column}",
        want=f"{T37}::TestEngineEntryGates"
             "::test_dynamic_columns_without_measured_binding_fail_closed",
        why="动态列缺实测绑定时按声明列猜 ⇒ 某单位的金额被读到另一家名下（Requirement 6.4）",
        tags=("gate",),
    ),
    # ── 结构性自证 ──────────────────────────────────────────────────
    Mutation(
        id="M37", side="be", path=EXTRACT, kind="replace",
        anchor="    loaded = tuple(name for name in FORBIDDEN_DOWNSTREAM_MODULES if name in sys.modules)",
        new="    loaded = ()",
        want=f"{T37}::TestStructuralSelfChecks"
             "::test_materializer_dependency_guard_can_actually_fail",
        why="「extractor 不得反向依赖 materializer」判据恒返回空 ⇒ 清单写错模块名时无人发现",
        tags=("selfcheck",),
    ),
    Mutation(
        id="M38", side="be", path=BASE, kind="replace",
        anchor="        if state is not ArtifactState.staged:",
        new="        if False:",
        want=f"{T37}::TestStagedResultSubstrateRole::test_other_combinations_are_rejected",
        why="`staged_result` 角色放行 published/durable ⇒ 它变成读任意 artifact 的旁路，"
            "substrate 准入矩阵被开了个洞",
        tags=("gate",),
    ),
    Mutation(
        id="M39", side="be", path=MERGE, kind="replace",
        anchor='        "expected_consumer_module": "app/services/workpaper_sync/excel_extract.py",',
        new='        "expected_consumer_module": "app/services/workpaper_sync/not_there.py",',
        want=f"{T14}::TestTask14ScopeBoundary::test_retired_deferral_records_who_wired_it",
        why="退役登记指向不存在的模块 ⇒ 「谁在哪个任务接线」的记录与事实脱钩；"
            "Task 14 的双向等值判据必须抓住它",
        tags=("registry",),
    ),
]

GUARD_FILES = {
    T37: "Task 37 新建（extractor + 三个共用 verifier）",
    T14: "Task 14（merge 域消费方退役登记的双向等值判据）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 37 Excel extractor / verifier 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task37_excel_extract.py",
                "backend/tests/workpaper_sync/test_task14_merge_conflicts.py",
                "-q",
                "--tb=no",
                "-rfE",
            ],
            baseline_backend_passed=None,
        )
    )
