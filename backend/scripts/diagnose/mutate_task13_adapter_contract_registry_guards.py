# -*- coding: utf-8 -*-
"""Task 13 变异检验：通用 adapter protocol / canonical contract+bundle schema /
fail-closed registry 的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 13
Requirements: 1.4, 6.1, 6.2, 6.3, 6.10, 6.14, 6.20, 9.8, 12.1
Properties: P3 / P20 / P21 / P28

═══ 变异改的是**生产代码**，不是守卫 ═══

落点六处：

* `workpaper_sync/contracts.py` —— 关掉 col 占位/source_ref/JSON Pointer/行身份/
  动态列/footer/formula mask/删除策略/审核态/probe gate/结构漂移各条判据，
  以及「委托 payload 级校验」与「跨语言 canonical 门」两处接线
* `workpaper_sync/adapters/base.py` —— 关掉副作用面守卫、substrate 三条准入、
  projection 键匹配、frozen identity 一致性、未管理区域报告
* `workpaper_sync/adapters/registry.py` —— 关掉 RG-1/3/7/10/11/13/18 各条，
  并把 `declares_bidirectional` 改成 descriptor 派生（复现结构性死代码）
* `workpaper_sync/entry_profile.py` —— 关掉 profile 缺失/capability/descriptor/room
  四类交叉判据
* `workpaper_sync/canonical_interop.py` —— 关掉 XL-1/2/3/5
* `scripts/check/check_workpaper_sync_closure.py` —— 断掉 registry 报告的**唯一生产
  消费方**接线（检验「新增能力是否真被消费」）
* 前端 `canonicalJson.ts` —— 换回默认 `sort()`、关掉负零判据（跨语言等价的 TS 侧）

判定四态：打红=RED（守卫有效）；不红=GREEN（守卫缺陷）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。**GREEN 一律当守卫缺陷逐条归因，不降标。**

═══ 否定式承诺只能靠注入证明 ═══

M40~M43 是**注入**而不是短路：

* 「registry 不得按 alias 重组历史 bundle」—— 源码里本来没有 alias 语句，没有可短路
  的对象，只能注入一个 alias 历史解析方法；
* 「本任务不发布 representation / 不 finalize candidate」—— 同理，注入一次真实调用；
* 「不引入 Excel/Word engine」—— 注入 `import openpyxl`。

这三条对应 Task 12 的 M51 经验：否定式承诺若不做注入检验，守卫可能只是恒真的空转。

═══ 本任务实测到的判据设计教训（已固化进守卫）═══

1. **「名单里写着」不等于「正在调用」**：`base.py` 的
   `FORBIDDEN_SIDE_EFFECT_ATTRS` 恰恰把 `finalize_candidate` / `set_entry_pointer`
   写成禁用名单字符串。按词出现判会把「明令禁止」误判成「正在调用」⇒ 首轮实测假红。
   判据改成「name 后跟 `(`」，并加一条反向自检。
2. **TS 源码必须先剥注释**：`canonicalJson.ts` 的模块注释里正解释「不能用
   `Array.prototype.sort()`」，直接扫全文必假红。剥注释器自带双向自检
   （注释确被剥、代码未被误剥、字符串里的 `//` 不被当注释）。
3. **禁用正则做函数体截取**：`(?:(?:\\s{4}.*)?\\n)+?` 这类「可选组套在重复里」的写法
   灾难性回溯，实测让整个 pytest 跑挂到 5 分钟超时。改行级 + 缩进判定。
4. **float 与「域外整数」是两条不同判据**：`header_rows=2.0` 被更早的跨语言门
   （XL-6 禁 float）拦下，异常类型也不同。合并断言会让其中一条永不被测到。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task13_adapter_contract_registry_guards.py --list
    python backend/scripts/diagnose/mutate_task13_adapter_contract_registry_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task13_adapter_contract_registry_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task13-adapter-contract-registry/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

CONTRACTS = "backend/app/services/workpaper_sync/contracts.py"
BASE = "backend/app/services/workpaper_sync/adapters/base.py"
REGISTRY = "backend/app/services/workpaper_sync/adapters/registry.py"
PROFILE = "backend/app/services/workpaper_sync/entry_profile.py"
INTEROP = "backend/app/services/workpaper_sync/canonical_interop.py"
CLOSURE = "backend/scripts/check/check_workpaper_sync_closure.py"
TS = "audit-platform/frontend/src/components/workpaper/sync/canonicalJson.ts"

#: 覆盖面分母：Task 13 新建的两个守卫文件（后端 + 前端跨语言）。
GUARD_FILES = {
    "test_task13_contract_registry.py":
        "Task 13 新建：contract 强校验（P20/P21）、bundle typed slots 与漂移（P28）、"
        "fail-closed registry 与伪双向（P3）、adapter protocol 面、跨语言 canonical、"
        "任务边界与反向自检",
    "canonicalJson.spec.ts":
        "Task 13 新建：canonical bytes 跨 Python/TypeScript 逐字节一致"
        "（两侧读同一份 golden fixture）",
}

U = "test_task13_contract_registry"

MUTATIONS: list[Mutation] = [
    # ══ 一、Property 20：generated col 占位 ═════════════════════════════
    Mutation(
        id="M01", side="be", path=CONTRACTS, kind="replace",
        anchor='_GENERATED_COLUMN_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"^col_[a-z]+$")',
        new='_GENERATED_COLUMN_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"^__never__$")',
        want=f"{U}.py::TestProperty20GeneratedColumnPlaceholder::test_col_placeholder_in_stable_key_rejected",
        wants=(
            f"{U}.py::TestProperty20GeneratedColumnPlaceholder::test_col_placeholder_rejected_even_with_full_source_ref",
            f"{U}.py::TestProperty20GeneratedColumnPlaceholder::test_col_placeholder_in_column_key_rejected",
        ),
        why="让 `col_[a-z]+` 形态不再匹配 ⇒ generated YAML 的无语义列占位可直接注册"
            "生产写格契约（Requirement 6.1 / Property 20 的核心反例）",
    ),
    Mutation(
        id="M02", side="be", path=CONTRACTS, kind="replace",
        anchor="    if not isinstance(value, str) or not value.strip():",
        scope="def assert_source_ref(value: Any, *, location: str) -> str:",
        offset=2,
        new="    if False:",
        want=f"{U}.py::TestProperty20GeneratedColumnPlaceholder::test_missing_source_ref_is_an_independent_judgement",
        wants=(
            f"{U}.py::TestProperty21ContractFieldCompleteness::test_each_missing_facet_is_rejected",
            f"{U}.py::TestProperty20GeneratedColumnPlaceholder::test_dynamic_columns_source_ref_required",
        ),
        why="关掉 `source_ref` 必填 ⇒ 无来源自造字段可进生产契约。与 M01 必须是两条"
            "独立判据：合成一条后删掉 col 检查仍会被 source_ref 挡住 ⇒ 变异 GREEN",
    ),
    Mutation(
        id="M03", side="be", path=CONTRACTS, kind="replace",
        anchor="    if review_status is not ContractReviewStatus.reviewed:",
        new="    if False:",
        want=f"{U}.py::TestProperty20GeneratedColumnPlaceholder::test_candidate_contract_cannot_register",
        wants=(
            f"{U}.py::TestProperty20GeneratedColumnPlaceholder::test_shipped_example_candidate_is_rejected_by_the_real_parser",
        ),
        why="让 generator 产的候选骨架直接可注册 ⇒ 「人工审核后的 per-entry contract "
            "发布后才能组 approved bundle」失效",
    ),

    # ══ 二、Property 21：contract 字段完整 ══════════════════════════════
    Mutation(
        id="M04", side="be", path=CONTRACTS, kind="replace",
        anchor="    if _BAD_TILDE_RE.search(pointer):",
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_json_pointer_tilde_escape_is_its_own_judgement",
        why="关掉 RFC 6901 的 `~0`/`~1` 转义判据 ⇒ 非法 pointer 进契约，"
            "运行时定位到不存在的路径",
    ),
    Mutation(
        id="M05", side="be", path=CONTRACTS, kind="replace",
        anchor="    if row_scoped and occurrences != 1:",
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_row_scoped_pointer_needs_exactly_one_row_placeholder",
        why="关掉「行域字段 pointer 必须含恰好一个 {row_uuid}」⇒ 行字段未绑定行身份，"
            "删除/重排后数据串行（Requirement 6.5）",
    ),
    Mutation(
        id="M06", side="be", path=CONTRACTS, kind="replace",
        anchor="    if not row_scoped and occurrences != 0:",
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_non_row_field_must_not_carry_row_placeholder",
        why="关掉「非行域字段不得含 {row_uuid}」—— 与 M05 是两个方向，"
            "只测一条时删另一条不会红",
    ),
    Mutation(
        id="M07", side="be", path=CONTRACTS, kind="replace",
        anchor="    if not key.isascii():",
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_non_ascii_identity_is_rejected",
        why="允许中文 label 作 stable key ⇒ identity 依赖展示文本，改标题即漂移"
            "（Requirement 6.14 明令禁止）",
    ),
    Mutation(
        id="M08", side="be", path=CONTRACTS, kind="replace",
        anchor='        if row_from == "row_identity":',
        new='        if row_from == "row_identity" or True:',
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_row_scoped_cell_must_not_hardcode_row_number",
        wants=(
            f"{U}.py::TestProperty21ContractFieldCompleteness::test_static_field_must_not_claim_row_identity",
            f"{U}.py::TestProperty21ContractFieldCompleteness::test_each_missing_facet_is_rejected",
        ),
        why="让任何 `row_from` 都被当成 row_identity ⇒ 写死行号与缺失 cell 都被静默接受",
    ),
    Mutation(
        id="M09", side="be", path=CONTRACTS, kind="replace",
        anchor="        if not isinstance(cell_raw, Mapping):",
        new="        if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_each_missing_facet_is_rejected",
        wants=(
            f"{U}.py::TestProperty21ContractFieldCompleteness::test_every_mode_field_still_needs_cell",
        ),
        why="关掉「xlsx 受管字段必须声明 cell（OO 位置）」⇒ Property 21 的六个语义面"
            "少一面仍能注册",
    ),
    Mutation(
        id="M10", side="be", path=CONTRACTS, kind="replace",
        anchor="    if len(set(all_keys)) != len(all_keys):",
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_duplicate_stable_keys_rejected_within_and_across_tables",
        why="允许 stable_field_key 跨 sheet/table 重复 ⇒ 同一 key 指向两个格，"
            "三方 merge 的键索引失去唯一性",
    ),
    Mutation(
        id="M11", side="be", path=CONTRACTS, kind="replace",
        anchor="    if not isinstance(header_rows, int) or isinstance(header_rows, bool) or not 1 <= header_rows <= 3:",
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_header_rows_domain",
        why="关掉两级表头的 header_rows 域判据（Requirement 6.3）⇒ 0/4/布尔值都能进契约",
    ),

    # ══ 三、Requirement 6.3~6.9 结构判据 ════════════════════════════════
    Mutation(
        id="M12", side="be", path=CONTRACTS, kind="replace",
        anchor="    if isinstance(kind_raw, str) and kind_raw in FORBIDDEN_ROW_IDENTITY_KINDS:",
        new="    if False:",
        want=f"{U}.py::TestContractStructuralRules::test_positional_row_identity_rejected",
        why="让 `index`/`ordinal`/`position` 等位置身份可作 row identity ⇒ 删行再新增后"
            "旧身份被复用、数据串到新行（Requirement 6.5 / Property 23）",
    ),
    Mutation(
        id="M13", side="be", path=CONTRACTS, kind="replace",
        anchor="    if identity != DYNAMIC_COLUMN_IDENTITY_TEMPLATE:",
        new="    if False:",
        want=f"{U}.py::TestContractStructuralRules::test_dynamic_column_identity_must_be_exact_template",
        why="允许任意动态列 identity 模板 ⇒ 可改 label 被当 identity、列数被写死"
            "（Requirement 6.4 / 平台 H7 范式）",
    ),
    Mutation(
        id="M14", side="be", path=CONTRACTS, kind="replace",
        anchor='    for forbidden in ("row", "row_index", "row_number"):',
        new="    for forbidden in ():",
        want=f"{U}.py::TestContractStructuralRules::test_footer_anchor_must_not_hardcode_row",
        why="允许 footer_anchor 写死行号 ⇒ 行新增后 footer 下移，公式范围写错位置",
    ),
    Mutation(
        id="M15", side="be", path=CONTRACTS, kind="replace",
        anchor="        if not column_in_ranges(spec.cell.column, formula_mask):",
        new="        if False:",
        want=f"{U}.py::TestContractStructuralRules::test_formula_field_must_be_covered_by_formula_mask",
        why="让 formula 字段的列不必落在 formula_mask 内 ⇒ 受保护单元格未登记只读，"
            "OO 侧修改会覆盖公式结果（Requirement 6.6）",
    ),
    Mutation(
        id="M16", side="be", path=CONTRACTS, kind="replace",
        anchor="    if row_identity is not None and delete_policy is None:",
        new="    if False:",
        want=f"{U}.py::TestContractStructuralRules::test_dynamic_rows_require_delete_policy_and_vice_versa",
        why="动态行表可以不声明 delete_policy ⇒ 删除语义留给运行时猜测"
            "（Requirement 6.9 / 6.15）",
    ),
    Mutation(
        id="M17", side="be", path=CONTRACTS, kind="replace",
        anchor='        if raw.get("sdt_tag") is not None:',
        new="        if False:",
        want=f"{U}.py::TestContractStructuralRules::test_document_type_crossover_is_rejected_four_ways",
        why="关掉 xlsx 契约里的 Word `sdt_tag` 拒绝 ⇒ 文档类型串用，"
            "Excel adapter 会拿到只有 Word 才有的载体声明",
    ),
    Mutation(
        id="M18", side="be", path=CONTRACTS, kind="replace",
        anchor="        if row_scoped and ROW_UUID_PLACEHOLDER not in sdt_tag:",
        new="        if False:",
        want=f"{U}.py::TestContractStructuralRules::test_row_scoped_docx_field_tag_must_carry_row_uuid",
        why="行域 Word 字段的 tag 可以不带 {row_uuid} ⇒ 行身份无处承载。"
            "row 级 SDT 在 OO 9.4 实测被剥掉，这是唯一可用的行身份载体",
    ),
    Mutation(
        id="M19", side="be", path=CONTRACTS, kind="replace",
        anchor="    if adapter_id is not None and contract_id != adapter_id:",
        new="    if False:",
        want=f"{U}.py::TestContractStructuralRules::test_contract_id_must_match_adapter_id",
        why="契约身份与 adapter 身份不再双向锁死 ⇒ 一个 adapter 可挂任意契约文件",
    ),
    Mutation(
        id="M20", side="be", path=CONTRACTS, kind="replace",
        anchor="    if relative_path.startswith((\"/\", \"\\\\\")) or \"..\" in Path(relative_path).parts:",
        new="    if False:",
        want=f"{U}.py::TestContractStructuralRules::test_template_path_traversal_rejected",
        why="契约里的模板相对路径可绝对、可含 `..` ⇒ 目录穿越进模板库之外",
    ),

    # ══ 四、probe gate 与 extract 载体（Requirement 6.16 / 6.20）════════
    Mutation(
        id="M21", side="be", path=CONTRACTS, kind="replace",
        anchor="        if carrier in self.blocked_carriers:",
        new="        if False:",
        want=f"{U}.py::TestCarrierProbeGate::test_failed_word_row_sdt_carrier_is_rejected",
        why="放行 probe blocklist 里的载体 ⇒ 真实 OO 9.4 上 failed 的 `row_sdt` 可进"
            "生产契约，engine 会建在一个会被 OO 剥掉的载体上",
    ),
    Mutation(
        id="M22", side="be", path=CONTRACTS, kind="replace",
        anchor="        if anchor in self.blocked_anchors:",
        new="        if False:",
        want=f"{U}.py::TestCarrierProbeGate::test_failed_excel_anchors_are_rejected",
        why="放行 blocklist 里的结构锚点 ⇒ `sheet_id` / `sheet_display_name`"
            "（OO 9.4 实测 failed）被当 sheet 定位依据",
    ),
    Mutation(
        id="M23", side="be", path=CONTRACTS, kind="replace",
        anchor="        if carrier not in self.verdicts:",
        new="        if False:",
        want=f"{U}.py::TestCarrierProbeGate::test_unregistered_carrier_is_rejected",
        why="未在 probe 契约登记的载体也放行 ⇒ gate 形同不存在（与 M21 是两条："
            "「登记过但 failed」与「根本没登记」）",
    ),
    Mutation(
        id="M24", side="be", path=CONTRACTS, kind="replace",
        anchor="        if native_anchors_present:",
        new="        if True:",
        want=f"{U}.py::TestCarrierProbeGate::test_extract_fails_closed_without_any_carrier",
        why="两级载体都不存在时不再 fail closed，而是谎报「有原生锚点」⇒ extract 会降级到"
            "中文标题/位置猜测（Requirement 6.20 明令禁止）",
    ),

    # ══ 五、Property 28：漂移 fail closed ═══════════════════════════════
    Mutation(
        id="M25", side="be", path=CONTRACTS, kind="replace",
        anchor="        if expected != actual:",
        new="        if False:",
        want=f"{U}.py::TestProperty28DefinitionDriftFailsClosed::test_structure_drift_reports_first_position",
        why="关掉逐项结构比对 ⇒ 契约声明与实测结构漂移后仍按旧坐标写格"
            "（Requirement 6.10 要求指出首个漂移 sheet/field/cell）",
    ),
    Mutation(
        id="M26", side="be", path=CONTRACTS, kind="replace",
        anchor="        if not template.is_definition or template.slot_digest != self.template_definition_sha256:",
        new="        if False:",
        want=f"{U}.py::TestProperty28DefinitionDriftFailsClosed::test_contract_bundle_slot_digests_are_locked_both_ways",
        wants=(
            f"{U}.py::TestProperty28DefinitionDriftFailsClosed::test_marker_in_template_slot_is_drift_for_projection_contract",
        ),
        why="契约声明的 template digest 不再与 frozen bundle 的 typed slot 比对 ⇒ "
            "definition 漂移后历史 identity 与当前契约悄悄错配",
    ),
    Mutation(
        id="M27", side="be", path=CONTRACTS, kind="replace",
        anchor="        if template is None or instrumentation is None:",
        new="        if False:",
        want=f"{U}.py::TestProperty28DefinitionDriftFailsClosed::test_missing_slot_prevents_comparison",
        why="bundle 缺 typed slot 时不再拒绝，而是往下走到 KeyError/None 比较 ⇒ "
            "slot omission 的诊断消失",
    ),
    Mutation(
        id="M28", side="be", path=CONTRACTS, kind="replace",
        anchor="    validate_contract_payload(payload)",
        new="    pass",
        want=f"{U}.py::TestPublishDagAndReferenceDirection::test_contract_payload_must_not_embed_self_identity",
        wants=(
            f"{U}.py::TestPublishDagAndReferenceDirection::test_contract_payload_must_not_forward_reference_bundle",
            f"{U}.py::TestPublishDagAndReferenceDirection::test_parse_contract_delegates_payload_level_rules",
            f"{U}.py::TestPublishDagAndReferenceDirection::test_self_identity_is_rejected_even_when_nested",
        ),
        why="断掉「字段级校验器委托 payload 级判据」的接线 ⇒ 自引用 artifact UUID/hash、"
            "反向 bundle 引用全部放行（Requirement 6.2 / 6.14）",
    ),
    Mutation(
        id="M29", side="be", path=CONTRACTS, kind="replace",
        anchor="    assert_cross_language_safe(payload)",
        new="    pass",
        want=f"{U}.py::TestCrossLanguageCanonicalizer::test_contract_payload_goes_through_the_cross_language_gate",
        wants=(
            f"{U}.py::TestProperty21ContractFieldCompleteness::test_float_header_rows_is_rejected_earlier_by_cross_language_gate",
        ),
        why="断掉跨语言 canonical 门 ⇒ float/NaN/孤立代理项/超安全整数进 contract payload，"
            "Python 与 TypeScript 算出不同 SHA（AC 6.2「同一 semantic payload 同一 SHA」失效）",
    ),

    # ══ 六、canonical_interop：XL 反例 ═══════════════════════════════════
    Mutation(
        id="M30", side="be", path=INTEROP, kind="replace",
        anchor="        if math.isnan(value) or math.isinf(value):",
        new="        if False:",
        want=f"{U}.py::TestCrossLanguageCanonicalizer::test_reject_kind_messages_carry_distinct_xl_classes",
        wants=(
            f"{U}.py::TestCrossLanguageCanonicalizer::test_every_registered_reject_kind_is_rejected",
        ),
        why="关掉 XL-1（NaN/Infinity）⇒ 该分类的可区分文案消失，JS 侧会静默输出 `null`",
    ),
    Mutation(
        id="M31", side="be", path=INTEROP, kind="replace",
        anchor="        if value == 0.0 and math.copysign(1.0, value) < 0:",
        new="        if False:",
        want=f"{U}.py::TestCrossLanguageCanonicalizer::test_reject_kind_messages_carry_distinct_xl_classes",
        why="关掉 XL-2（负零）⇒ 与 XL-6 的通用禁 float 合并，「负零」这条可区分诊断丢失。"
            "三条 float 子判据必须各有文案，否则删前两条不改变行为",
    ),
    Mutation(
        id="M32", side="be", path=INTEROP, kind="replace",
        anchor="    if abs(value) > MAX_SAFE_INTEGER:",
        new="    if False:",
        want=f"{U}.py::TestCrossLanguageCanonicalizer::test_boundary_integers_are_allowed",
        wants=(
            f"{U}.py::TestCrossLanguageCanonicalizer::test_every_registered_reject_kind_is_rejected",
            f"{U}.py::TestCrossLanguageCanonicalizer::test_reject_kind_messages_carry_distinct_xl_classes",
        ),
        why="关掉 XL-3 ⇒ 超出 `Number.MAX_SAFE_INTEGER` 的整数进 payload，TS 侧丢精度",
    ),
    Mutation(
        id="M33", side="be", path=INTEROP, kind="replace",
        anchor="            if not isinstance(key, str):",
        new="            if False:",
        want=f"{U}.py::TestCrossLanguageCanonicalizer::test_every_registered_reject_kind_is_rejected",
        wants=(
            f"{U}.py::TestCrossLanguageCanonicalizer::test_reject_kind_messages_carry_distinct_xl_classes",
        ),
        why="关掉 XL-5（非字符串对象键）⇒ Python 会强转成字符串而 TS 侧无此形态，"
            "两侧语义不可对齐",
    ),

    # ══ 七、adapter protocol 面 ═════════════════════════════════════════
    Mutation(
        id="M34", side="be", path=BASE, kind="replace",
        anchor="        if hits:",
        new="        if False:",
        want=f"{U}.py::TestAdapterProtocolSurface::test_context_rejects_any_mutation_surface",
        why="关掉副作用面守卫 ⇒ adapter 上下文可以携带 session/repository/outbox，"
            "adapter 能自己 commit、递增 revision、改 pointer（design §Adapter protocol 第 1 条）",
    ),
    Mutation(
        id="M35", side="be", path=BASE, kind="replace",
        anchor="    if state is ArtifactState.quarantined:",
        new="    if False:",
        want=f"{U}.py::TestAdapterProtocolSurface::test_quarantined_substrate_is_rejected",
        why="quarantined incoming 可进 adapter ⇒ 被隔离的可疑 OOXML 进入 extract/merge/"
            "retry/rematerialize",
    ),
    Mutation(
        id="M36", side="be", path=BASE, kind="replace",
        anchor="    if kind is ArtifactKind.upgrade_candidate or state is ArtifactState.candidate:",
        new="    if False:",
        want=f"{U}.py::TestAdapterProtocolSurface::test_upgrade_candidate_substrate_is_rejected",
        why="representation upgrade candidate 可作 substrate ⇒ 未经 approved contract/bundle "
            "的 candidate 被 resolver/room/evidence 消费（Requirement 6.18）",
    ),
    Mutation(
        id="M37", side="be", path=BASE, kind="replace",
        anchor="        if state is not ArtifactState.durable:",
        new="        if False:",
        want=f"{U}.py::TestAdapterProtocolSurface::test_incoming_substrate_must_be_durable",
        why="incoming 未 durable 就能被 extract ⇒ 下载/封存还没完成就算 application key",
    ),
    Mutation(
        id="M38", side="be", path=BASE, kind="replace",
        anchor="        if len(expected) != len(actual):",
        new="        if False:",
        want=f"{U}.py::TestAdapterProtocolSurface::test_projection_key_matching_is_not_prefix_only",
        wants=(
            f"{U}.py::TestGuardSelfCheck::test_prefix_only_projection_matching_would_accept_wrong_key",
        ),
        why="projection 键匹配退化成「段数不限」⇒ 同前缀的错误键被放行，"
            "D2 那类大表会串数据",
    ),
    Mutation(
        id="M39", side="be", path=BASE, kind="replace",
        anchor="        if contract_slot.slot_digest != self.contract.canonical_sha256:",
        new="        if False:",
        want=f"{U}.py::TestAdapterProtocolSurface::test_frozen_identity_consistency",
        why="adapter 执行时不再校验 contract digest == frozen bundle 的 contract slot ⇒ "
            "历史 operation 可以拿当前契约跑旧 bundle（Property 28）",
    ),

    # ══ 八、否定式承诺（注入而非短路）════════════════════════════════════
    Mutation(
        id="M40", side="be", path=REGISTRY, kind="insert",
        anchor="    def resolve_for_entry(self, entry_id: str) -> AdapterRegistration:",
        new="        from app.services.workpaper_sync.definitions import DefinitionAliasRegistry\n"
            "        self.aliases = DefinitionAliasRegistry()\n"
            "        _ = self.aliases.resolve_for_publish(entry_id)\n",
        want=f"{U}.py::TestProperty28DefinitionDriftFailsClosed::test_registry_exposes_no_alias_based_history_lookup",
        why="🔴 **注入**：给 registry 加一条按 alias 解析的路径。「不得按 alias 重组历史 "
            "bundle」是否定式承诺 —— 源码里本来没有可短路的语句，只能注入反例来证明"
            "判据可 falsify（同 Task 12 的 M51）",
    ),
    Mutation(
        id="M41", side="be", path=REGISTRY, kind="insert",
        anchor="def build_production_registry() -> WorkpaperSyncAdapterRegistry:",
        new="    _service = object()\n"
            "    if False:\n"
            "        finalize_candidate(_service)\n",
        want=f"{U}.py::TestTask13ScopeBoundary::test_no_representation_publish_or_candidate_finalize",
        why="🔴 **注入**：在 Task 13 模块里注入一次 `finalize_candidate(...)` 调用。"
            "「本任务不 finalize upgrade candidate、不发布 representation」是否定式承诺，"
            "必须靠注入证明判据不是恒真空转",
    ),
    Mutation(
        id="M42", side="be", path=BASE, kind="insert",
        anchor="import uuid",
        new="import openpyxl  # noqa: F401\n",
        want=f"{U}.py::TestTask13ScopeBoundary::test_no_excel_or_word_engine_dependency",
        why="🔴 **注入**：给 protocol 层加载体库依赖。「本 Wave 不引入 Excel/Word engine」"
            "同样是否定式承诺，短路无从下手",
    ),
    Mutation(
        id="M43", side="be", path=CLOSURE, kind="replace",
        anchor="        issues = evaluate_closure(manifest, baseline, build_registry_facts(manifest))",
        new="        issues = evaluate_closure(manifest, baseline)",
        want=f"{U}.py::TestRegistryReportHasAProductionConsumer::test_closure_gate_consumes_the_registry_report",
        why="断掉 registry 报告的**唯一生产消费方** ⇒ 整个 fail-closed registry 退化成"
            "additive 死代码（假绿第①源）。这条正是「新增能力是否真被消费」的判据",
    ),

    # ══ 九、registry fail-closed 清册 ═══════════════════════════════════
    Mutation(
        id="M44", side="be", path=REGISTRY, kind="replace",
        anchor="    if not_callable:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg1_adapter_shape",
        why="关掉「protocol 五个方法必须可调用」⇒ 把方法全写成 None 的桩也能注册"
            "（RG-1；`runtime_checkable` Protocol 只查属性存在性）",
    ),
    Mutation(
        id="M45", side="be", path=REGISTRY, kind="replace",
        anchor="        if not self.wp_codes:",
        new="        if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg2_empty_matcher",
        why="允许空 matcher ⇒ 永远解析不到的死注册被当成「已迁移」（RG-2）",
    ),
    Mutation(
        id="M46", side="be", path=REGISTRY, kind="replace",
        anchor="            shared = registration.matcher.overlaps(existing.matcher)",
        new="            shared = ()",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg3_matcher_overlap",
        why="关掉 matcher 重叠检测 ⇒ 解析结果取决于注册顺序，同一 wp/sheet 可能命中"
            "两个 adapter（RG-3）",
    ),
    Mutation(
        id="M47", side="be", path=REGISTRY, kind="replace",
        anchor="    if bundle.state is not DefinitionState.approved:",
        new="    if False:",
        want=f"{U}.py::TestProperty3BidirectionalRequiresAdapter::test_missing_bundle_approval_forbids_bidirectional_claim",
        why="candidate 态 bundle 可被 registry/room 使用 ⇒ 未批准的 definition 组合"
            "进入生产（Property 3 / 28）",
    ),
    Mutation(
        id="M48", side="be", path=REGISTRY, kind="replace",
        anchor="        if contract is None:",
        new="        if False:",
        want=f"{U}.py::TestProperty3BidirectionalRequiresAdapter::test_missing_contract_forbids_projection_bundle",
        why="`projection_contract` 缺 approved per-entry contract 也能注册 ⇒ 「缺 contract 的 "
            "entry 不得进入 bidirectional 验收」失效（Requirement 12.1 / Property 3）",
    ),
    Mutation(
        id="M49", side="be", path=REGISTRY, kind="replace",
        anchor="    if slot.slot_digest != contract.canonical_sha256:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg10_contract_digest_must_equal_bundle_slot_digest",
        why="关掉 RG-10（注册 ↔ frozen bundle 漂移）。与 RG-11 必须分开：合成一条后删掉"
            "任一分支都会被另一条遮蔽 ⇒ 变异 GREEN",
    ),
    Mutation(
        id="M50", side="be", path=REGISTRY, kind="replace",
        anchor="            assert_contract_file_current(contract=registration.contract, entry_id=entry_id)",
        new="            pass",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg11_on_disk_contract_drift_is_a_separate_judgement",
        wants=(
            f"{U}.py::TestRegistryFailClosedRules::test_rg11_missing_contract_file_is_stale",
        ),
        why="关掉 RG-11（注册 ↔ 磁盘真源漂移）⇒ 磁盘契约被改过、adapter 还挂旧 digest 的"
            "stale 形态不再被发现",
    ),
    Mutation(
        id="M51", side="be", path=REGISTRY, kind="replace",
        anchor='        if not entry.get("independent_entry"):',
        scope='                "中 —— 源码挂载点已变但 adapter 未同步（RG-12）"',
        offset=2,
        new="        if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg13_parent_duplicate_and_unreachable_entries_rejected",
        why="父组件重复入口可单独注册 adapter ⇒ 43 个重复入口被重复计成「已迁移」"
            "（Requirement 1.6 / 12.4）",
    ),
    Mutation(
        id="M52", side="be", path=REGISTRY, kind="replace",
        anchor="        if registration.declares_bidirectional and capability is not Capability.bidirectional:",
        new="        if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg18_fake_bidirectional_both_directions",
        why="single entry 可注册 declared_capability=bidirectional 的 adapter ⇒ "
            "「仅能打开 OO」伪装成双向同步（Requirement 1.4 / Property 3 的原始缺陷）",
    ),
    Mutation(
        id="M53", side="be", path=REGISTRY, kind="replace",
        anchor="        return self.declared_capability is Capability.bidirectional",
        new="        return self.descriptor.mode is DescriptorMode.bidirectional",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg18_declared_capability_is_independent_of_descriptor_mode",
        why="把 `declares_bidirectional` 改成 descriptor 派生 ⇒ 因 RG-16 已要求 "
            "`descriptor.mode == manifest capability`，RG-18 变成结构性不可达的死代码"
            "（假绿第①源，本任务实测过的形态）",
    ),
    Mutation(
        id="M54", side="be", path=REGISTRY, kind="replace",
        anchor="    if len(distinct) != 1:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg6_document_type_must_agree_across_four_sources",
        why="adapter/contract/matcher/manifest 的 document_type 不再四方一致 ⇒ "
            "需要 docx 时拿到 xlsx 也放行（Requirement 9.5）",
    ),
    Mutation(
        id="M55", side="be", path=REGISTRY, kind="replace",
        anchor="        entry = self._entries.get(entry_id)",
        scope='                "中 —— 源码挂载点已变但 adapter 未同步（RG-12）"',
        offset=-5,
        new='        entry = self._entries.get(entry_id) or {"independent_entry": True, '
            '"capability": "single_html", "document_type": "xlsx"}',
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg12_entry_not_in_manifest_is_stale",
        why="给未登记 entry 静默补一份默认裁决（典型 fail-open）⇒ adapter 可指向 manifest 里"
            "不存在的 entry，源码挂载点已删/改名而 adapter 未同步不再被判 stale（RG-12）",
    ),

    # ══ 十、entry profile 交叉判据 ══════════════════════════════════════
    Mutation(
        id="M56", side="be", path=PROFILE, kind="replace",
        anchor="    if missing:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg14_profile_fields_are_mandatory",
        wants=(
            f"{U}.py::TestRegistryReportHasAProductionConsumer::test_report_invariant_holds_on_the_real_manifest",
            f"{U}.py::TestRegistryReportHasAProductionConsumer::test_entries_missing_profile_cannot_register",
        ),
        why="manifest 缺 source-backed profile 三字段也能注册 adapter ⇒ 「要么有完整合法 "
            "profile，要么不可能注册」这条不变式失效（Requirement 1.2 的欠账被隐藏）",
    ),
    Mutation(
        id="M57", side="be", path=PROFILE, kind="replace",
        anchor="    if profile.editability not in allowed_editability:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg15_profile_must_agree_with_capability",
        why="profile 的 editability 可与 capability 矛盾 ⇒ readonly 宿主被裁决成 "
            "bidirectional（required scenarios 随之被降级）",
    ),
    Mutation(
        id="M58", side="be", path=PROFILE, kind="replace",
        anchor="    if descriptor.mode.value != capability.value:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg16_descriptor_mode_must_agree_with_capability",
        why="服务端 descriptor 可以对前端谎报模式 ⇒ 前端显示「可双向回写」而后端只有单向"
            "（Requirement 1.4 / 1.5）",
    ),
    Mutation(
        id="M59", side="be", path=PROFILE, kind="replace",
        anchor="    if descriptor.exposes_mode_switch and capability is not Capability.bidirectional:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg16_mode_switch_only_for_bidirectional",
        why="非双向入口可暴露模式切换按钮 ⇒ 显示不可兑现的切换（Requirement 1.5）",
    ),
    Mutation(
        id="M60", side="be", path=PROFILE, kind="replace",
        anchor="    if room.doc_key_includes_mtime:",
        new="    if False:",
        want=f"{U}.py::TestRegistryFailClosedRules::test_rg17_room_facts_must_agree_and_dockey_must_drop_mtime",
        why="doc_key 仍含文件 mtime 的 room 也能注册 ⇒ 一次 sheet 可见性写盘就轮转 doc_key、"
            "打断进行中的协同会话（Property 6；当前生产 `_generate_doc_key` 正是这个形态）",
    ),

    # ══ 十一、closure gate 的登记与阻断总数 ═════════════════════════════
    Mutation(
        id="M61", side="be", path=CLOSURE, kind="replace",
        anchor="    for key in REGISTRY_ISSUE_KEYS:",
        new="    for key in ():",
        want=f"{U}.py::TestRegistryReportHasAProductionConsumer::test_registry_facts_participate_in_the_blocking_total",
        wants=(
            f"{U}.py::TestRegistryReportHasAProductionConsumer::test_closure_gate_consumes_the_registry_report",
        ),
        why="registry 事实不再进 issue map ⇒ 即使算出来了也不计入阻断总数（Requirement 1.8"
            "「只许下降」失去判据）",
    ),
    Mutation(
        id="M62", side="be", path=CLOSURE, kind="replace",
        anchor="    if unknown:",
        new="    if False:",
        want=f"{U}.py::TestRegistryReportHasAProductionConsumer::test_unregistered_registry_fact_is_rejected",
        why="新增 registry 事实无需登记 ⇒ 会静默不计入阻断总数（下一个人加事实时不会有人提醒）",
    ),

    # ══ 十一之二、JSON Pointer 形态的其余分支 ════════════════════════════
    Mutation(
        id="M65", side="be", path=CONTRACTS, kind="replace",
        anchor='    if not pointer.startswith("/"):',
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_json_pointer_must_be_rfc6901",
        why="关掉「pointer 必须以 `/` 开头」⇒ 相对路径形态进契约，运行时定位落到根对象",
    ),
    Mutation(
        id="M66", side="be", path=CONTRACTS, kind="replace",
        anchor='    if any(token == "" for token in tokens):',
        new="    if False:",
        want=f"{U}.py::TestProperty21ContractFieldCompleteness::test_json_pointer_must_be_rfc6901",
        why="关掉空 token 判据 ⇒ `/rows//closingAmount` 这类 pointer 进契约，"
            "RFC 6901 下它指向键名为空串的成员（与作者意图不符）",
    ),

    # ══ 十二、前端跨语言 canonicalizer ══════════════════════════════════
    Mutation(
        id="M63", side="fe", path=TS, kind="replace",
        anchor="    const keys = Object.keys(value as Record<string, unknown>).sort(compareByCodePoint)",
        new="    const keys = Object.keys(value as Record<string, unknown>).sort()",
        want="canonical 输出把 Ｚ 排在 𝐀 之前",
        wants=(
            "golden 用例 astral_key_order",
            "TS canonicalizer 与后端逐字节一致",
        ),
        why="TS 侧换回默认 `sort()`（UTF-16 code unit 序）⇒ 星平面键的顺序与 Python 的 "
            "code point 序相反，两侧 canonical bytes 分叉（AC 6.2「同一 semantic payload "
            "同一 SHA」失效）",
    ),
    Mutation(
        id="M64", side="fe", path=TS, kind="replace",
        anchor="  if (Object.is(value, -0)) {",
        new="  if (false) {",
        # want 必须同时是**源码里的静态标题**（`--list` 静态定位用）与**运行期
        # fullName 的子串**（判定用）。参数化标题 `拒绝 %s` 只满足前者，故主目标取静态标题。
        want="每条反例的文案带自己的 XL 分类标记",
        wants=("拒绝 negative_zero", "不同 XL 分类的文案互不相同"),
        why="TS 侧关掉 XL-2（负零）⇒ `-0` 在 JS 序列化成 `0`、Python 为 `-0.0`，"
            "两侧 digest 不同。fixture 声明的反例种类必须两侧都真拒",
    ),
]

if __name__ == "__main__":
    frontend = REPO / "audit-platform" / "frontend"
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task13_contract_registry.py",
            "-q", "--tb=no", "-rf", "-p", "no:cacheprovider",
        ],
        frontend_filters=["src/components/workpaper/sync/__tests__/canonicalJson.spec.ts"],
        frontend_dir=frontend,
        vitest_json=REPO / "tmp_task13_vitest.json",
        # 冻结基线来源：2026-08-25 Task 13 收口实测（仓库根、`.venv` 解释器）
        #   backend  test_task13_contract_registry.py   237 passed
        #   frontend canonicalJson.spec.ts               42 passed
        baseline_backend_passed=237,
        baseline_frontend_passed=42,
    ))
