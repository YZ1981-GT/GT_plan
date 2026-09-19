# -*- coding: utf-8 -*-
"""Task 36 守卫变异检验：Excel per-entry contract/bundle loader 与 candidate finalize gate。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 36
Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.20
Properties: P20 / P21 / P22 / P23 / P28 / P66 / P67

用法（从仓库根跑）::

    py -3 backend/scripts/diagnose/mutate_task36_excel_entry_gate_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task36_excel_entry_gate_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task36_excel_entry_gate_guards.py --run all

═══ 为什么每条变异都改**条件行**而不是 `raise` 行 ═══

`raise X(` 在本模块里全是多行语句（文案含中文与格式化），整行替换首行会破坏续行语法 ⇒
文件级 collect ERROR ⇒ 判定从 RED 退化成 WRONG-TEST（且失败 diff 会异常短）。所以一律
把**判据的条件**短路成 `if False:`（语法始终合法），或删掉一整行独立调用。

═══ 判据设计的一个直接结果 ═══

M10~M13 四条针对动态列 identity 的四个分支，正是首轮实测抓到的缺陷的回归锚：改造前
「label 被嵌入 key」这条分支排在形态门之后，于是**永久不可达**（任何含 label 的 key 都
先被形态门拒），它的变异恒 GREEN。现在四个分支的触发条件互不重叠，四条都能各自打红。
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO / "backend") not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_REPO / "backend"))
sys.path.insert(0, str(_REPO / "backend" / "scripts"))

from _mutation_kit.cli import run_cli  # noqa: E402
from _mutation_kit.spec import Mutation  # noqa: E402

GATE = "backend/app/services/workpaper_sync/excel_entry_gate.py"

#: 🔴 `want` 必须用 `_mutation_kit.runner.short_nodeid` 的形态（`文件名::类::方法`），
#: **不带**目录前缀：runner 收失败名时已把路径截成文件名，带前缀的 want 在
#: `verdict.matched` 里既不子串命中也不前缀命中 ⇒ 全部判 WRONG-TEST。
#: 首轮实测 44/44 全 WRONG-TEST 就是这个原因（每次都恰好只有预期那一条测试失败）。
T = "test_task36_excel_entry_gate.py::"

#: 覆盖面分母：本次变异应当打红的守卫文件。
GUARD_FILES = {
    "test_task36_excel_entry_gate.py": "Task 36 loader/gate 守卫（纯域，无库）",
}

_FALSE_8 = "        if False:  # MUT"
_FALSE_4 = "    if False:  # MUT"
_FALSE_12 = "            if False:  # MUT"


MUTATIONS: list[Mutation] = [
    # ── FS-1 ~ FS-5：六类 frozen slot 分类 ───────────────────────────────
    Mutation(
        id="M01", side="be", path=GATE, kind="replace",
        anchor="        if column not in raw:",
        new=_FALSE_8,
        want=f"{T}TestFrozenSlotClassification::test_fs1_slot_omission_names_the_missing_column",
        why="短路 slot omission（FS-1）。键缺失后 FS-2 直接 `raw[column]` 抛 KeyError，"
            "`FrozenSlotOmittedError` 这条专属 error_code 消失 —— 「slot omission 必须 "
            "fail closed 且有自己的 code」失守。",
    ),
    Mutation(
        id="M02", side="be", path=GATE, kind="replace",
        anchor="        if raw[column] is None:",
        new=_FALSE_8,
        want=f"{T}TestFrozenSlotClassification::test_fs2_null_is_separate_from_blank",
        why="短路 NULL（FS-2）。`str(None)` 非空白 ⇒ 落到 models 的合并判据抛 "
            "BundleIntegrityError，NULL 与空串两条禁令合流。",
    ),
    Mutation(
        id="M03", side="be", path=GATE, kind="replace",
        anchor="        if not str(raw[column]).strip():",
        new=_FALSE_8,
        want=f"{T}TestFrozenSlotClassification::test_fs2_null_is_separate_from_blank",
        why="短路空串/纯空白（FS-3）。空串会被 models 的合并判据接走，专属 code 消失。",
    ),
    Mutation(
        id="M04", side="be", path=GATE, kind="replace",
        anchor="    if str(raw[digest_col]).strip() == ALL_ZERO_DIGEST:",
        new=_FALSE_4,
        want=f"{T}TestFrozenSlotClassification::test_fs4_all_zero_digest_is_its_own_cause",
        why="短路全零 digest（FS-4）。`is_digest` 也拒全零，但抛的是合并类型 ⇒ 「忘了算 "
            "hash 就填 0」这个伪身份成因在诊断里不可分辨。",
    ),
    Mutation(
        id="M05", side="be", path=GATE, kind="replace",
        anchor="        if marker is None:",
        new=_FALSE_8,
        want=f"{T}TestFrozenSlotClassification::test_fs5_illegal_marker",
        why="短路「marker 未在 registry 登记」（FS-5）。未登记 marker 会一路走到 "
            "`marker.slot` 的 AttributeError，而不是可诊断的 fail-closed。",
    ),
    Mutation(
        id="M06", side="be", path=GATE, kind="replace",
        anchor="        if spec.slot_ref != marker.slot_ref or spec.slot_digest != marker.slot_digest:",
        new=_FALSE_8,
        want=f"{T}TestFrozenSlotClassification::test_marker_digest_tampering_is_rejected",
        why="短路 marker ref/digest 与 registry 的一致性。篡改后的 marker digest 仍是合法 "
            "hex，models 侧不会拒 ⇒ 伪 marker 可进 canonical bytes。",
    ),
    Mutation(
        id="M07", side="be", path=GATE, kind="delete",
        anchor="    validate_bundle_slot(spec)",
        want=f"{T}TestFrozenSlotClassification::test_form_predicates_stay_delegated_to_models",
        why="删掉对 models 单一真源的委派。分类通过后就不再校验 digest 形态与 "
            "`definition:<uuid>` ref 形态 —— 「不复制判据」的另一面是「必须真的调它」。",
    ),
    # ── `_GT_SYNC` 业务枚举排除 ──────────────────────────────────────────
    Mutation(
        id="M08", side="be", path=GATE, kind="replace",
        anchor="        if is_platform_metadata_sheet(name):",
        new=_FALSE_8,
        want=f"{T}TestMetadataSheetExclusion::test_business_enumeration_leak_names_the_first_offender",
        wants=(
            f"{T}TestMetadataSheetExclusion::test_business_enumeration_leak_names_the_first_offender",
            f"{T}TestLoader::test_metadata_sheet_in_business_enumeration_fails_closed",
        ),
        why="短路运行态业务 sheet 枚举的 `_GT_SYNC` 泄漏检查（Requirement 6.17 后半句）。"
            "审计师会在下拉/报表里看到一张自己无法解释的隐藏表。",
    ),
    Mutation(
        id="M09", side="be", path=GATE, kind="replace",
        anchor="            if is_platform_metadata_sheet(value):",
        new=_FALSE_12,
        want=f"{T}TestMetadataSheetExclusion::test_contract_may_not_declare_the_metadata_sheet",
        why="短路「契约不得把隐藏 metadata sheet 声明成业务表」。它与 M08 是两条判据："
            "运行态已排除时，一份把 `_GT_SYNC` 写进 sheets[] 的契约会悄悄通过。",
    ),
    # ── 动态列 identity 与 label 解耦（Property 22，四个互不重叠分支）────
    Mutation(
        id="M10", side="be", path=GATE, kind="replace",
        anchor="        if not key.isascii():",
        new=_FALSE_8,
        want=f"{T}TestDynamicColumnIdentity::test_label_derived_key_is_rejected",
        why="短路「实测 key 含非 ASCII」。中文 label 直接当列身份时诊断退化成形态错，"
            "「identity 不得依赖中文 label」这条不可分辨。",
    ),
    Mutation(
        id="M11", side="be", path=GATE, kind="replace",
        anchor="        if pattern.match(key) is None:",
        new=_FALSE_8,
        want=f"{T}TestDynamicColumnIdentity::test_ascii_but_label_shaped_key_is_rejected",
        why="短路由模板派生的键形态门。ASCII 英文简称当键时诊断被「与派生键不等」遮蔽。",
    ),
    Mutation(
        id="M12", side="be", path=GATE, kind="replace",
        anchor="    if len(set(observed_keys)) != len(observed_keys):",
        new=_FALSE_4,
        want=f"{T}TestDynamicColumnIdentity::test_duplicate_observed_keys_are_their_own_cause",
        why="短路「实测 key 撞键」。两家同名公司共用一个键（H7 实测过的缺陷）会被"
            "「与派生键不等」接走，撞键这条独立成因消失。",
    ),
    Mutation(
        id="M13", side="be", path=GATE, kind="replace",
        anchor="        if key != want:",
        new=_FALSE_8,
        want=f"{T}TestDynamicColumnIdentity::test_reordered_or_renumbered_keys_are_rejected",
        why="短路「与 label 无关的派生键逐项相等」。按 label 排序后重新编号就无人拦，"
            "改名/重排会静默换掉列身份。",
    ),
    Mutation(
        id="M14", side="be", path=GATE, kind="replace",
        anchor="            if table.table_key not in observed_dynamic_columns:",
        new=_FALSE_12,
        want=f"{T}TestDynamicColumnIdentity::test_declared_dynamic_table_without_observed_columns_fails_closed",
        why="短路「声明了 dynamic_columns 就必须给实测列」。没给即跳过时，G7/H1 这类"
            "横向动态列最多的 entry 恰好完全不被检查。",
    ),
    Mutation(
        id="M15", side="be", path=GATE, kind="replace",
        anchor="    unknown = sorted(set(observed_dynamic_columns) - set(resolved))",
        new="    unknown = []  # MUT",
        want=f"{T}TestDynamicColumnIdentity::test_observed_columns_for_undeclared_table_fail_closed",
        why="短路「实测输入必须与契约声明一一对应」。多喂一张未声明动态列的表不再报错，"
            "调用方以为检查过了其实没有。",
    ),
    # ── identity inventory（Requirement 6.15 / 6.16）────────────────────
    Mutation(
        id="M16", side="be", path=GATE, kind="replace",
        anchor="    if not inventory.excluded_from_business_enumeration:",
        new=_FALSE_4,
        want=f"{T}TestIdentityInventory::test_each_missing_carrier_fails_closed",
        why="短路 identity 反读侧的「隐藏表已被业务枚举排除」。与 M08/M09 是第三层"
            "（实测反读），三层缺任一层都留绕过路径。",
    ),
    Mutation(
        id="M17", side="be", path=GATE, kind="replace",
        anchor='    if inventory.resolved_sheet_by != "table_sheet":',
        new=_FALSE_4,
        want=f"{T}TestIdentityInventory::test_forbidden_sheet_anchors_are_rejected",
        why="短路「sheet 只能由 excel_table_sheet_association 解析」。Task 5 实测 "
            "`sheet_id` 与 sheet 展示名在 OO 9.4 上 failed，放开即回到被证伪的锚点。",
    ),
    Mutation(
        id="M18", side="be", path=GATE, kind="replace",
        anchor="    if inventory.empty_row_uuids:",
        new=_FALSE_4,
        want=f"{T}TestIdentityInventory::test_first_empty_row_uuid_is_named",
        why="短路空 row UUID 的分类处置（Requirement 6.15）。OO 里新增的空 identity 行会"
            "被按位置猜行身份。",
    ),
    Mutation(
        id="M19", side="be", path=GATE, kind="replace",
        anchor="    if inventory.duplicate_row_uuids:",
        new=_FALSE_4,
        want=f"{T}TestIdentityInventory::test_first_duplicate_row_uuid_is_named",
        why="短路重复 row UUID 的分类处置。复制行产生的重复 UUID 会让两行数据串到一起。",
    ),
    Mutation(
        id="M20", side="be", path=GATE, kind="replace",
        anchor="    if dynamic_tables and not inventory.row_uuids:",
        new=_FALSE_4,
        want=f"{T}TestIdentityInventory::test_dynamic_row_table_without_any_identity_names_the_first_table",
        why="短路「契约声明动态行却零 row identity ⇒ 拒绝」（Property 23）。identity 列被"
            "用户删掉后 extract 只能按位置猜。",
    ),
    # ── adapter build ───────────────────────────────────────────────────
    Mutation(
        id="M21", side="be", path=GATE, kind="replace",
        anchor="    if not is_digest(build.adapter_build_digest):",
        new=_FALSE_4,
        want=f"{T}TestAdapterBuild::test_each_mismatch_fails_closed",
        why="短路 adapter build digest 合法性。全零 build digest 会被写进 representation，"
            "adapter 身份成为伪身份。",
    ),
    Mutation(
        id="M22", side="be", path=GATE, kind="replace",
        anchor="    if build.adapter_id != contract.contract_id:",
        new=_FALSE_4,
        want=f"{T}TestAdapterBuild::test_each_mismatch_fails_closed",
        why="短路「adapter 身份与 contract 身份双向锁死」。Task 36 明令禁止复用另一个 "
            "entry 的 contract，这是那条禁令在 adapter 侧的落点。",
    ),
    Mutation(
        id="M23", side="be", path=GATE, kind="replace",
        anchor="    if bundle.authority_model is not AuthorityModel.projection_contract:",
        new=_FALSE_4,
        want=f"{T}TestAdapterBuild::test_non_projection_authority_model_is_rejected",
        why="短路「标准 Excel entry 必须是 projection_contract」。custom/opaque bundle 会"
            "被本门当标准 entry 放行，绕过 Task 65 的专属协议。",
    ),
    # ── candidate 证据（roundtrip / visible equivalence / probe gate）───
    Mutation(
        id="M24", side="be", path=GATE, kind="replace",
        anchor="    if observed != expected_sha256:",
        new=_FALSE_4,
        want=f"{T}TestCandidateEvidence::test_digest_mismatch_blocks_borrowed_evidence",
        why="短路 evidence digest 与 candidate 登记值的比对。拿另一个 entry 的 evidence "
            "顶替即可 finalize —— Task 36 明令禁止的形态。",
    ),
    Mutation(
        id="M25", side="be", path=GATE, kind="replace",
        anchor='    if str(payload.get("entry_id")) != entry_id:',
        new=_FALSE_4,
        want=f"{T}TestCandidateEvidence::test_other_entry_evidence_is_rejected",
        why="短路 evidence 的 entry 归属。它与 M24 是两条：digest 对得上但 entry 写错时"
            "（同一份报告被两个 entry 引用）只有本条能拦。",
    ),
    Mutation(
        id="M26", side="be", path=GATE, kind="replace",
        anchor='    if equivalence.get("equivalent") is not True:',
        new=_FALSE_4,
        want=f"{T}TestCandidateEvidence::test_failed_visible_equivalence_is_rejected",
        why="短路可见等价性结论。instrumentation 破坏了公式/样式/merge 的 candidate 也能"
            "发布成 published representation（Requirement 6.17）。",
    ),
    Mutation(
        id="M27", side="be", path=GATE, kind="replace",
        anchor='    if equivalence.get("metadata_sheet_excluded_from_business") is not True:',
        new=_FALSE_4,
        want=f"{T}TestCandidateEvidence::test_metadata_sheet_not_excluded_is_rejected",
        why="短路证据里的「隐藏表已排除」。它与 `equivalent` 是两条独立结论，合并后"
            "前者被后者遮蔽。",
    ),
    Mutation(
        id="M28", side="be", path=GATE, kind="replace",
        anchor='        if not str(probe_gate.get(key) or "").strip():',
        new=_FALSE_8,
        want=f"{T}TestCandidateEvidence::test_probe_gate_identity_is_required",
        why="短路 probe gate 身份（载体契约 digest + OO build）。未过真实 OnlyOffice 9.4 "
            "探针的载体可以进 engine（Requirement 6.16 / Property 66）。",
    ),
    Mutation(
        id="M29", side="be", path=GATE, kind="replace",
        anchor="    missing = [key for key in REQUIRED_EQUIVALENCE_KEYS if key not in payload]",
        new="    missing = []  # MUT",
        want=f"{T}TestCandidateEvidence::test_missing_required_key_is_named",
        why="短路证据必需键清册。缺 identity_inventory / probe_gate 的半份报告也能过门，"
            "后续解析拿到空对象。",
    ),
    # ── frozen FK/digest（Property 28）──────────────────────────────────
    Mutation(
        id="M30", side="be", path=GATE, kind="replace",
        anchor="        if row_digest != frozen_bundle_sha256.strip():",
        new=_FALSE_8,
        want=f"{T}TestLoader::test_frozen_digest_mismatch_fails_closed",
        why="短路 frozen digest 与 bundle row 的一致性。调用方冻结的身份不再被校验，"
            "等于「按当前那个 bundle 顶替」—— Requirement 6.2 禁止的 alias 行为。",
    ),
    Mutation(
        id="M31", side="be", path=GATE, kind="replace",
        anchor="        if not is_digest(frozen_bundle_sha256):",
        new=_FALSE_8,
        want=f"{T}TestLoader::test_blank_frozen_digest_is_not_treated_as_wildcard",
        why="短路「frozen digest 必须显式且合法」。空串/全零会落到 M30 的比对上抛同一"
            "类型 —— 守卫因此断言本条专属文案，否则两条合流后本条恒 GREEN。",
    ),
    # ── FS-6：per-entry contract child ──────────────────────────────────
    Mutation(
        id="M32", side="be", path=GATE, kind="replace",
        anchor="        if not slot.is_definition:",
        new=_FALSE_8,
        want=f"{T}TestLoader::test_marker_cannot_impersonate_the_per_entry_contract",
        why="短路「marker 不得冒充 per-entry contract」（FS-6 / Requirement 6.19）。"
            "typed null marker 的 ref 会被当 `definition:<uuid>` 解析。",
    ),
    Mutation(
        id="M33", side="be", path=GATE, kind="replace",
        anchor="        if child is None:",
        new=_FALSE_8,
        want=f"{T}TestLoader::test_fs6_contract_child_states",
        why="短路「contract child 必须存在」。指向不存在 definition 的 bundle 会一路走到"
            " AttributeError 而不是 fail closed。",
    ),
    Mutation(
        id="M34", side="be", path=GATE, kind="replace",
        anchor="        if child.kind != DefinitionKind.contract.value:",
        new=_FALSE_8,
        want=f"{T}TestLoader::test_fs6_contract_child_states",
        why="短路 contract child 的 kind。instrumentation definition 会被当 per-entry "
            "contract 用。",
    ),
    Mutation(
        id="M35", side="be", path=GATE, kind="replace",
        anchor="        if child.state != DefinitionState.approved.value:",
        new=_FALSE_8,
        want=f"{T}TestLoader::test_fs6_contract_child_states",
        why="短路「只有人工审核后 approved 的契约可 finalize」。generator 产的 candidate "
            "契约会被放行 —— Task 36 的核心禁令。",
    ),
    # ── 复用既有判据（删一行即绕开一整条判据）──────────────────────────
    Mutation(
        id="M36", side="be", path=GATE, kind="delete",
        anchor="        assert_bundle_usable(bundle, entry_id=entry_id)",
        want=f"{T}TestLoader::test_unapproved_bundle_snapshot_propagates",
        wants=(
            f"{T}TestLoader::test_unapproved_bundle_snapshot_propagates",
            f"{T}TestLoader::test_loader_reuses_the_existing_predicates",
        ),
        why="删掉 Task 13 的 RG-7。非 approved / slot 不全的 bundle 快照可直接进 finalize。",
    ),
    Mutation(
        id="M37", side="be", path=GATE, kind="delete",
        anchor="        assert_contract_identity_frozen(contract=contract, bundle=bundle, entry_id=entry_id)",
        want=f"{T}TestLoader::test_contract_drift_from_frozen_slot_is_stale_adapter",
        wants=(
            f"{T}TestLoader::test_contract_drift_from_frozen_slot_is_stale_adapter",
            f"{T}TestLoader::test_template_definition_drift_fails_closed",
            f"{T}TestLoader::test_loader_reuses_the_existing_predicates",
        ),
        why="删掉 Task 13 的 RG-10（含 template/instrumentation 漂移）。磁盘契约被改过而 "
            "bundle 未重发布时仍会 finalize —— Property 28 失守。",
    ),
    Mutation(
        id="M38", side="be", path=GATE, kind="delete",
        anchor="        assert_no_structure_drift(contract, observed_structure)",
        want=f"{T}TestLoader::test_structure_drift_names_the_first_offender",
        wants=(
            f"{T}TestLoader::test_structure_drift_names_the_first_offender",
            f"{T}TestLoader::test_loader_reuses_the_existing_predicates",
        ),
        why="删掉结构漂移定位（Requirement 6.10）。契约声明与实测结构不一致时继续按旧坐标"
            "写格，且不再指出首个漂移 sheet/table/field。",
    ),
    # ── finalize gate（Property 67）─────────────────────────────────────
    Mutation(
        id="M39", side="be", path=GATE, kind="replace",
        anchor="        if candidate.entry_id != entry_id:",
        new=_FALSE_8,
        want=f"{T}TestFinalizeGate::test_candidate_from_another_entry_is_rejected",
        why="短路 candidate 的 entry 归属。用另一个 entry 的 candidate 就能 finalize 本 "
            "entry —— Task 36 明令禁止复用别人的 candidate。",
    ),
    Mutation(
        id="M40", side="be", path=GATE, kind="replace",
        anchor="        if str(staged_candidate.entry_id) != entry_id:",
        new=_FALSE_8,
        want=f"{T}TestFinalizeGate::test_staged_candidate_scope_mismatch_is_rejected",
        why="短路 staged candidate 的 entry 归属。它与 M39 是两侧（DB 行 vs 磁盘产物），"
            "两者都要锁。",
    ),
    Mutation(
        id="M41", side="be", path=GATE, kind="replace",
        anchor="        if frozen_bundle_id is None:",
        new=_FALSE_8,
        want=f"{T}TestFinalizeGate::test_candidate_without_approved_bundle_is_rejected",
        why="短路「candidate 必须已有 approved bundle」。Task 17 产出的空 bundle candidate "
            "会带着 `None` 一路走下去，诊断指向别处。",
    ),
    Mutation(
        id="M42", side="be", path=GATE, kind="replace",
        anchor="        if evidence.instrumented_sha256 != staged_candidate.sha256:",
        new=_FALSE_8,
        want=f"{T}TestFinalizeGate::test_evidence_bytes_must_describe_the_artifact_being_published",
        why="短路「反读等值证据必须描述将要发布的那份字节」。证据与 artifact 脱钩后，"
            "roundtrip 通过的是另一份文件。",
    ),
    Mutation(
        id="M43", side="be", path=GATE, kind="replace",
        anchor="        if self._coordinator is None:",
        new=_FALSE_8,
        want=f"{T}TestFinalizeGate::test_missing_coordinator_fails_visible",
        why="短路「未装配 Task 25 唯一出口时 fail visible」。退化成 AttributeError 而不是"
            "带 error_code 的域异常（Requirement 5.12）。",
    ),
    Mutation(
        id="M44", side="be", path=GATE, kind="replace",
        anchor="        if outcome.definition_bundle_id != frozen_bundle_id:",
        new=_FALSE_8,
        want=f"{T}TestFinalizeGate::test_result_bundle_must_equal_the_frozen_one",
        why="短路 finalize 结果与 frozen bundle 的后置核验。出口若绑错 bundle，"
            "representation 的身份与 candidate 冻结的不一致且无人报警。",
    ),
]


if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=_REPO,
            description="Task 36 Excel per-entry contract/bundle loader 与 finalize gate 变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task36_excel_entry_gate.py",
                "-q",
                "-rfE",
                "-p",
                "no:cacheprovider",
            ],
            baseline_backend_passed=103,
        )
    )
