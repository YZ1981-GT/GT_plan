# -*- coding: utf-8 -*-
"""Task 38 守卫的变异检验（Excel identity-aware materializer / rematerializer / adapter）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38
Properties: P9 / P22 / P23 / P24 / P29 / P65 / P66 / P67

═══ 为什么必须做 ═══

「写完守卫没打红 = 守卫有缺陷，不是代码没问题」。本 spec 已三次实测「共享错误码让较早分支
永久不可达 ⇒ 该分支守卫永久 GREEN」，因此本脚本为**每一条写入侧判据**各准备一条变异，逐条
要求 RED。

═══ 已踩过的坑（本脚本按它们写死）═══

* `want` 必须是**短 nodeid**（`file.py::Class::test`，不带目录前缀）—— 带路径前缀会让整轮
  记成 WRONG-TEST；
* pytest 参数传 `-rfE`（不是 `-rf`），否则 error 态的用例名收不进失败集合；
* 锚点不得含 `\n` —— 工作树是 CRLF，跨行锚点必 ANCHOR-MISS；
* **替换体必须保持语法合法**：条件语句一律 `if False and <原式>:` / `if False:`（缩进块本身
  仍合法），表达式用 `return True or <原式>` / `_ = dict(` 这类短路式。整行替换让后续行悬空
  会变成 collection error（Task 37 首轮三条 WRONG-TEST 全是这个形态）；
* 同形态锚点用 `scope` + `offset` 相对定位，不用绝对 `line`；
* `_mutation_kit` 会把 `expect_green` 的对照项在汇总里映射成 RED，读数时别误判。

用法::

    py -3 backend/scripts/diagnose/mutate_task38_excel_materialize_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task38_excel_materialize_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task38_excel_materialize_guards.py --run all
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

MAT = "backend/app/services/workpaper_sync/excel_materialize.py"
REMAT = "backend/app/services/workpaper_sync/excel_rematerialize.py"
ADAPTER = "backend/app/services/workpaper_sync/adapters/excel.py"
EXTRACT = "backend/app/services/workpaper_sync/excel_extract.py"
MERGE = "backend/app/services/workpaper_sync/merge.py"
REGISTRY = "backend/app/services/workpaper_sync/adapters/registry.py"

T38 = "test_task38_excel_materialize.py"
T38PG = "test_task38_excel_materialize_pg.py"
T13 = "test_task13_contract_registry.py"
T14 = "test_task14_merge_conflicts.py"

MUTATIONS: list[Mutation] = [
    # ── Property 9：临时校验与原子发布 ────────────────────────────────
    Mutation(
        id="M01", side="be", path=MAT, kind="replace",
        anchor='    tmp = output.with_name(output.name + ".materializing")',
        new="    tmp = output",
        want=f"{T38}::TestProperty9AtomicPublish"
             "::test_failed_write_does_not_touch_a_preexisting_output",
        why="临时文件与目标路径合一（= 直接写目标路径）⇒ 失败时 `finally` 的清理把已存在的 "
            "output 删掉，读侧看到「文件凭空消失」。成功路径上两者字节相同、无法分辨，"
            "只有失败路径能 falsify —— 判据因此落在失败后的盘上事实",
        tags=("p9",),
    ),
    Mutation(
        id="M02", side="be", path=MAT, kind="replace",
        anchor="        if tmp.exists():",
        new="        if False and tmp.exists():",
        want=f"{T38}::TestProperty9AtomicPublish::test_publish_stage_failure_leaves_no_temp_file",
        why="失败后不清理 `*.materializing` ⇒ 临时文件残留，下一次 materialize 可能读到半成品。"
            "注入点必须是原子改名而不是 zip 重打包：后者失败时临时文件还没落盘，清理分支不可达",
        tags=("p9",),
    ),
    Mutation(
        id="M03", side="be", path=MAT, kind="replace",
        anchor="    assert_output_outside_template_library(output)",
        new="    _ = output",
        want=f"{T38}::TestProperty9AtomicPublish"
             "::test_output_inside_template_library_is_refused_before_any_read",
        why="不再校验输出路径 ⇒ 运行时可以写回 `backend/wp_templates/`，"
            "把唯一权威源污染掉（Requirement 9.9）",
        tags=("p9", "template"),
    ),
    Mutation(
        id="M04", side="be", path=MAT, kind="replace",
        anchor="    if TEMPLATE_LIBRARY_MARKER in resolved.parts:",
        new='    if str(output).startswith("/nonexistent-prefix"):',
        want=f"{T38}::TestProperty9AtomicPublish"
             "::test_output_inside_template_library_is_refused_before_any_read",
        why="判据从「解析后的路径分量」退化成字符串前缀比较 ⇒ `..` 拼出来的模板库路径查不出来",
        tags=("p9", "template"),
    ),
    # ── Property 22：动态列 key 与 label 解耦 ─────────────────────────
    Mutation(
        id="M05", side="be", path=MAT, kind="replace",
        anchor="            bad_keys = sorted(key for key in bound if not pattern.fullmatch(key))",
        new="            bad_keys = []",
        want=f"{T38}::TestProperty22DynamicColumnKeys::test_label_shaped_key_is_refused",
        why="不再校验动态列键形态 ⇒ `公司甲_1` 这类带 label 的键被接受，"
            "改公司名就会让列 identity 漂移（Requirement 6.4 明令禁止）",
        tags=("p22",),
    ),
    Mutation(
        id="M06", side="be", path=MAT, kind="replace",
        anchor="            collided = {c: k for c, k in by_column.items() if len(k) > 1}",
        new="            collided = {}",
        want=f"{T38}::TestProperty22DynamicColumnKeys"
             "::test_two_slots_bound_to_one_column_is_refused",
        why="两个 `{slot}_{seq}` 落进同一列不再报错 ⇒ 后写的静默覆盖先写的，"
            "审计上表现为「一家单位的数据凭空消失」",
        tags=("p22",),
    ),
    Mutation(
        id="M07", side="be", path=MAT, kind="replace",
        anchor="            if not bound:",
        new="            if False:",
        want=f"{T38}::TestProperty22DynamicColumnKeys::test_missing_measured_binding_is_refused",
        why="缺实测绑定不再 fail closed ⇒ 写入侧退回按声明列右移猜，"
            "某单位的金额被写到另一家名下",
        tags=("p22",),
    ),
    Mutation(
        id="M08", side="be", path=MAT, kind="replace",
        anchor='    escaped = escaped.replace(re.escape("{slot}"), r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*?")',
        new='    escaped = escaped.replace(re.escape("{slot}"), r".+")',
        want=f"{T38}::TestProperty22DynamicColumnKeys::test_label_shaped_key_is_refused",
        why="把 `{slot}` 放宽成任意字符 ⇒ 中文 label 键也能通过，Property 22 的判据空转",
        tags=("p22",),
    ),
    Mutation(
        id="M09", side="be", path=MAT, kind="replace",
        anchor="    if not region.contains_column(column):",
        new="    if False:",
        want=f"{T38}::TestProperty22DynamicColumnKeys"
             "::test_binding_outside_the_table_span_is_refused_by_both_layers",
        why="动态列绑定落在 Table 列跨度之外仍放行 ⇒ 写到受管区域之外，"
            "反读拿不回来（写入侧那条判据是 `plan_managed_writes` 入口的唯一防线）",
        tags=("p22",),
    ),
    # ── Property 23：动态行身份不使用下标 ────────────────────────────
    Mutation(
        id="M10", side="be", path=MAT, kind="replace",
        anchor="    physical = dict(scan.row_identity_by_row)",
        new="    physical = {region.first_row + i: k for i, k in enumerate(projection.row_keys.get(dynamic_table.table_key, ()))}",
        want=f"{T38}::TestProperty23RowIdentityIsNotPositional"
             "::test_reversed_row_order_lands_on_the_same_physical_rows",
        wants=(
            f"{T38}::TestProperty23RowIdentityIsNotPositional"
            "::test_writes_target_the_row_that_carries_the_identity",
        ),
        why="identity→物理行的映射不再来自 Task 37 的实测扫描，而是**按 projection 里的位置**"
            "重建 ⇒ 行序被打乱时值整批串行。这正是 Requirement 6.5 禁止的「用数组下标作持久化"
            "身份」（与 M11 是两条独立路径：一个改映射来源、一个改取行方式）",
        tags=("p23",),
    ),
    Mutation(
        id="M11", side="be", path=MAT, kind="replace",
        anchor="        row = row_of_identity[identity]",
        new="        row = region.first_row + wanted.index(identity)",
        want=f"{T38}::TestProperty23RowIdentityIsNotPositional"
             "::test_reversed_row_order_lands_on_the_same_physical_rows",
        why="把目标行号从「identity 的物理行」换成「在 projection 里的下标」—— "
            "Requirement 6.5 明令禁止用数组下标作持久化身份",
        tags=("p23",),
    ),
    Mutation(
        id="M12", side="be", path=MAT, kind="replace",
        anchor="        if minted not in set(wanted):",
        new="        if False:",
        want=f"{T38}::TestProperty23RowIdentityIsNotPositional"
             "::test_minted_identity_must_reach_the_projection_first",
        why="OO 新增行的 minted 身份不再要求先经三方 merge 进 projection ⇒ "
            "写入侧自行决定要不要保留一行（Requirement 6.15）",
        tags=("p23",),
    ),
    Mutation(
        id="M13", side="be", path=MAT, kind="replace",
        anchor="    for row, minted in sorted(scan.minted_by_row.items()):",
        new="    for row, minted in []:",
        want=f"{T38}::TestProperty23RowIdentityIsNotPositional"
             "::test_minted_identity_is_written_into_the_hidden_uuid_column",
        why="minted 身份根本不写进隐藏 UUID 列 ⇒ 下一次 extract 又把它当新行，"
            "每次保存都 mint 一个新 ID（identity 永不稳定）",
        tags=("p23", "p66"),
    ),
    Mutation(
        id="M14", side="be", path=MAT, kind="replace",
        anchor="    if orphan:",
        new="    if False:",
        want=f"{T38}::TestProperty9AtomicPublish::test_plan_stage_failure_publishes_nothing",
        why="merged projection 里有 substrate 上不存在的行身份时不再 fail closed ⇒ "
            "那些行的值被静默丢弃（结构性插行未实现却假装成功）",
        tags=("p23", "p9"),
    ),
    # ── Property 24：受保护字段 ──────────────────────────────────────
    Mutation(
        id="M15", side="be", path=REMAT, kind="replace",
        anchor="        intended_formulas=baseline_formulas,",
        new="        intended_formulas=None,",
        want=f"{T38}::TestProperty24ProtectedFieldsStayProtected"
             "::test_reported_tamper_proceeds_and_keeps_the_template_formula",
        why="🔴 本任务首轮实测的真实缺陷：intended 公式取 incoming 而不是 base representation ⇒ "
            "被 OO 改写的 `<f>` 逐字进 staged result，而 verifier 是「篡改比篡改」恒通过"
            "（AC 6.6 失守）",
        tags=("p24",),
    ),
    Mutation(
        id="M16", side="be", path=MAT, kind="replace",
        anchor="            if intended and _formula_body(intended) != _formula_body(observed):",
        new="            if False:",
        want=f"{T38}::TestProperty24ProtectedFieldsStayProtected"
             "::test_reported_tamper_proceeds_and_keeps_the_template_formula",
        why="不再还原被改写的公式文本 ⇒ 同上，受保护格的 `<f>` 被 OO 侧决定",
        tags=("p24",),
    ),
    Mutation(
        id="M17", side="be", path=MAT, kind="replace",
        anchor="    return text[1:] if text.startswith(\"=\") else text",
        new="    return text",
        want=f"{T38}::TestGuardSelfCheck::test_formula_equals_prefix_conversion_is_needed",
        why="不换算 openpyxl 的 `=` 前缀 ⇒ 写出 `<f>=G7-D7</f>`，Excel 打开后是 `==G7-D7`"
            "（首轮实测踩过）",
        tags=("p24",),
    ),
    Mutation(
        id="M18", side="be", path=REMAT, kind="replace",
        anchor="    assert_protected_tamper_fully_reported(",
        new="    _ = dict(",
        want=f"{T38}::TestProperty24ProtectedFieldsStayProtected"
             "::test_unreported_tamper_blocks_rematerialize_before_any_byte_is_written",
        why="受保护格篡改的跨层闭合被关掉 ⇒ merge 漏报 protected 冲突时照常发布，"
            "审计师看不到任何冲突（Property 24）",
        tags=("p24",),
    ),
    Mutation(
        id="M19", side="be", path=MAT, kind="replace",
        anchor="            if view is not None and view.has_formula:",
        new="            if False:",
        want=f"{T38}::TestProperty24ProtectedFieldsStayProtected"
             "::test_auto_source_on_a_formula_cell_is_refused",
        why="auto_source 落在公式格上不再报错 ⇒ 写字面量毁掉模板公式（AC 6.6 / 3.5）。"
            "首轮 want 指向失败形态清册那条 ⇒ GREEN：清册里 `ProtectedRegionWriteError` 是用"
            "「契约说 formula 但模板没公式」触发的，两条判据共用一个 error_code，靠前的这条"
            "缺专属 oracle（正是本 spec 反复强调的形态）",
        tags=("p24",),
    ),
    Mutation(
        id="M20", side="be", path=MAT, kind="replace",
        anchor='        elif view is not None and view.shared_ref and ":" in (view.shared_ref or ""):',
        new="        elif False:",
        want=f"{T38}::TestFailureKindsAreReachableAndMutuallyDistinct"
             "::test_every_registered_failure_kind_is_really_reachable",
        why="覆盖共享公式主格不再被拒 ⇒ H8 被写成字面量后 H9..H25 全组失效（写坏 18 行公式）",
        tags=("p24",),
    ),
    Mutation(
        id="M21", side="be", path=MAT, kind="replace",
        anchor="    attrs = re.sub(r'\\s+t=\"[^\"]*\"', \"\", view.attrs)",
        new="    attrs = view.attrs",
        want=f"{T38}::TestProperty24ProtectedFieldsStayProtected"
             "::test_stale_text_marker_is_dropped_from_a_numeric_formula_cell",
        why="公式格写缓存值时保留原来的 `t=\"str\"` 之类过期文本标记 ⇒ Excel 把数字当字符串"
            "（求和恒为 0）。首轮 GREEN 的原因是 K11 的 H 列本来就没有 `t=`，该分支在真实模板"
            "上不可达 —— 现在 fixture 专门补一个过期标记让它可达",
        tags=("p24", "p29"),
    ),
    # ── Property 29：roundtrip ───────────────────────────────────────
    Mutation(
        id="M22", side="be", path=MAT, kind="replace",
        anchor="        body = body + rendered",
        new="        body = body",
        want=f"{T38}::TestProperty24ProtectedFieldsStayProtected"
             "::test_formula_cell_without_a_cached_value_gets_one",
        why="公式格没有 `<v>` 时不补缓存值 ⇒ 反读拿不到值，Task 15 的全字段等值门挡掉发布。"
            "首轮 GREEN 的原因是 K11 的公式格都带 `<v>0</v>`，且删掉 `<v>` 后 extract 也读不到"
            "该字段 ⇒ 值必须来自另一侧的 projection（正是 OO 尚未重算的生产形态）",
        tags=("p29",),
    ),
    Mutation(
        id="M23", side="be", path=MAT, kind="replace",
        anchor="        return normalize_value(field.value, spec.value_type)",
        new="        return field.value",
        want=f"{T38}::TestFailureKindsAreReachableAndMutuallyDistinct"
             "::test_every_registered_failure_kind_is_really_reachable",
        why="写入侧不再复用 merge 的规范化口径 ⇒ 「merge 认为等值、反读认为不等值」的"
            "无法解释的发布失败（也让「值无法规范化」这条失败形态不可达）",
        tags=("p29",),
    ),
    Mutation(
        id="M24", side="be", path=MAT, kind="replace",
        anchor='    style_attr = f\' s="{style}"\' if style else ""',
        new='    style_attr = ""',
        want=f"{T38}::TestBaselineMaterialize::test_style_and_unmanaged_cells_survive_the_write",
        why="写入时丢掉原样式 `s=` ⇒ 金额格变成默认格式（AC 3.5 要求样式保留）。首轮 GREEN 的"
            "原因是 fixture 里受管格根本没有 `s=`（Task 37 的 `patch_cells` 写格不带样式）⇒ "
            "判据恒真；现在 fixture 给 C7/J7 补了模板原样式",
        tags=("p29", "style"),
    ),
    Mutation(
        id="M25", side="be", path=MAT, kind="replace",
        anchor="    entries[plan.sheet_part] = _patch_sheet_xml(xml, plan.writes).encode(\"utf-8\")",
        new="    entries[plan.sheet_part] = _patch_sheet_xml(xml, plan.field_writes).encode(\"utf-8\")",
        want=f"{T38}::TestProperty23RowIdentityIsNotPositional"
             "::test_minted_identity_is_written_into_the_hidden_uuid_column",
        why="只写字段、丢掉 identity 列写入 ⇒ minted UUID 不落盘（与 M13 是两条独立路径："
            "一个在计划期、一个在写盘期）",
        tags=("p29", "p66"),
    ),
    # ── Property 65：substrate 准入与顺序 ────────────────────────────
    Mutation(
        id="M26", side="be", path=MAT, kind="replace",
        anchor="    assert_substrate_usable(",
        new="    _ = dict(",
        want=f"{T38}::TestProperty65SubstrateAdmissionAndProjectionIdentity"
             "::test_quarantined_is_refused_before_the_output_path_check",
        why="engine 入口不再判 substrate 准入 ⇒ quarantined 的报错退到 Task 37 的 extract 里，"
            "而输出路径判据会先抛 ⇒ 诊断指向完全错的地方。首轮 want 指「quarantined 被拒」⇒ "
            "GREEN：extract 内部也会拒，只是更晚。用「同时违反两条禁令、看抛哪一条」定序",
        tags=("p65", "ordering"),
    ),
    Mutation(
        id="M27", side="be", path=MAT, kind="delete",
        anchor="    assert_engine_entry_definitions(definitions)",
        want=f"{T38}::TestProperty65SubstrateAdmissionAndProjectionIdentity"
             "::test_unapproved_bundle_is_refused_before_the_output_path_check",
        why="删掉 materializer 自己的 frozen 身份门 ⇒ 未 approved bundle 的报错退到 extract 里，"
            "输出路径判据会先抛。首轮用 `move` 做顺序变异：`block_open` 就是锚点行本身 ⇒ 两个"
            "块解析到同一行、`apply_mutation` 判「两个锚点落在同一块内」⇒ ANCHOR-MISS。"
            "改用 delete + 「同时违反两条禁令」的定序 oracle",
        tags=("p65", "ordering"),
    ),
    Mutation(
        id="M28", side="be", path=REMAT, kind="replace",
        anchor="        if self.mode is ExcelRematerializeMode.representation_upgrade:",
        new="        if False:",
        want=f"{T38}::TestProperty67UpgradeCandidateFirst"
             "::test_candidate_is_produced_and_is_not_committable",
        why="representation upgrade 的产物可以当业务 commit 交出去 ⇒ 纯表示升级制造伪业务 "
            "revision（Property 67 / AC 6.18）",
        tags=("p65", "p67"),
    ),
    Mutation(
        id="M29", side="be", path=REMAT, kind="replace",
        anchor="        self.verification.assert_publishable()",
        new="        _ = self.verification.passed",
        want=f"{T38}::TestProperty9AtomicPublish::test_verification_stage_failure_blocks_commit",
        why="commit 前置门只读一个布尔而不抛 ⇒ 反读不等值的 staged result 也能交 "
            "`ContentMutationService`（AC 8.11）",
        tags=("p65",),
    ),
    Mutation(
        id="M30", side="be", path=REMAT, kind="replace",
        anchor="        artifact_state=incoming_state,",
        new="        artifact_state=ArtifactState.durable,",
        want=f"{T38}::TestProperty65SubstrateAdmissionAndProjectionIdentity"
             "::test_quarantined_is_refused_before_the_tamper_closure_check",
        why="把调用方给的 incoming 状态硬写成 durable ⇒ quarantined incoming 在 OO→HTML 的**第一"
            "道**门（带 baseline 的 incoming extract）不再被拒，于是篡改闭合检查先抛 —— 诊断"
            "从「安全隔离」变成「冲突漏报」（AC 8.10：本协议不提供 quarantined→durable 的边）。"
            "两轮 GREEN 的教训：两道门互为兜底时，只有能分辨「谁先抛」的 oracle 才可 falsify",
        tags=("p65",),
    ),
    # ── Property 66：identity 保留与 runtime binding 读侧 ────────────
    Mutation(
        id="M31", side="be", path=EXTRACT, kind="replace",
        anchor="    if part is None:",
        new="    if False:",
        want=f"{T38}::TestProperty66IdentityRetainedAfterWrite"
             "::test_runtime_binding_reader_fails_closed_instead_of_returning_empty",
        why="隐藏 metadata sheet 定位不到时不再 fail closed ⇒ 后续 `.get(...)` 抛 "
            "AttributeError 或读空，真因（sheet 定位失败）被埋掉",
        tags=("p66",),
    ),
    Mutation(
        id="M32", side="be", path=EXTRACT, kind="replace",
        anchor="    if not pairs:",
        new="    if False:",
        want=f"{T38}::TestProperty66IdentityRetainedAfterWrite"
             "::test_runtime_binding_reader_rejects_an_empty_metadata_sheet",
        why="一对 key/value 都读不到时返回空 dict（fail-open）⇒ 「载体形态与写侧不符」被当成"
            "「这份文件没有冻结任何绑定」，正是首轮踩到的形态。首轮 want 指向「sheet 定位失败」"
            "那条 oracle ⇒ GREEN：两条分支不同，各需自己的 oracle",
        tags=("p66",),
    ),
    Mutation(
        id="M33", side="be", path=MAT, kind="replace",
        anchor="    if str(observed) != str(frozen).strip():",
        new="    if False:",
        want=f"{T38}::TestProperty66IdentityRetainedAfterWrite"
             "::test_footer_anchor_cross_checks_two_independent_carriers",
        why="footer 的「可见 marker 行号」与「冻结 GT_FOOTER_ROW」不再交叉验证 ⇒ footer 下移后"
            "跟着 marker 写，而 extract 仍按契约 static_row 反读（静默错值）",
        tags=("p66",),
    ),
    Mutation(
        id="M34", side="be", path=MAT, kind="replace",
        anchor="    staged_inventory = _staged_identity_inventory(",
        new="    staged_inventory = substrate_view.identity_inventory or _staged_identity_inventory(",
        want=f"{T38}::TestProperty23RowIdentityIsNotPositional"
             "::test_minted_identity_is_written_into_the_hidden_uuid_column",
        why="staged 清册从「反读产物实测」退化成「沿用 substrate 的清册」（自证式推导）⇒ "
            "UUID 根本没写进去时它照样给出正确答案。这正是本任务刻意避开的形态",
        tags=("p66",),
    ),
    # ── Property 67：upgrade candidate ──────────────────────────────
    Mutation(
        id="M35", side="be", path=REMAT, kind="replace",
        anchor="    if CANDIDATE_NAMESPACE not in candidate_output.resolve().parts:",
        new="    if False:",
        want=f"{T38}::TestProperty67UpgradeCandidateFirst"
             "::test_candidate_must_land_in_the_candidate_namespace",
        why="candidate 不再要求落 candidate 命名空间 ⇒ 一个手滑的 relative_path 就能让它被 "
            "resolver 当 current 读到（AC 6.18）",
        tags=("p67",),
    ),
    Mutation(
        id="M36", side="be", path=REMAT, kind="replace",
        anchor="    if before_digest != after_digest:",
        new="    if False:",
        want=f"{T38}::TestProperty67UpgradeCandidateFirst"
             "::test_a_business_value_change_during_upgrade_is_detected",
        why="纯表示升级不再校验业务 projection 是否变化 ⇒ 「趁升级顺手改业务值」不再可见"
            "（AC 6.18 / Property 67）",
        tags=("p67",),
    ),
    Mutation(
        id="M37", side="be", path=REMAT, kind="replace",
        anchor="    revision_delta: int = 0",
        new="    revision_delta: int = 1",
        want=f"{T38PG}::TestEngineSideDoesNotTouchRevision"
             "::test_upgrade_reports_zero_revision_delta",
        why="纯表示升级声明非零 revision 增量 ⇒ 与 AC 6.18「业务 projection 未变则 "
            "content_revision 保持不变」直接冲突（真库守卫同时钉住实际 DB 值）",
        tags=("p67", "pg"),
    ),
    Mutation(
        id="M38", side="be", path=REMAT, kind="replace",
        anchor="    before, _ = derive_baseline_from_representation(",
        new="    before, _ = (Projection(contract_id=definitions.contract.contract_id, semantic_version=definitions.contract.semantic_version, document_type=definitions.contract.document_type, values={}, row_keys={}), None) or derive_baseline_from_representation(",
        want=f"{T38PG}::TestFinalizeIsAdditiveOnly"
             "::test_the_published_generation_carries_task38_identity",
        why="升级要写的 projection 变成空的 ⇒ 一个受管格都不写，candidate 与 current 的业务"
            "内容不再等值，而 `before/after` 两侧都为空使 digest 判据空转",
        tags=("p67", "pg"),
    ),
    # ── 写入策略门 ──────────────────────────────────────────────────
    Mutation(
        id="M39", side="be", path=MAT, kind="replace",
        anchor="    if capability is None or not capability.openpyxl_safe:",
        new="    if False:",
        want=f"{T38}::TestWriteStrategyGate::test_capability_absent_refuses_openpyxl",
        why="缺 capability 时不再拒 ⇒ 任意模板都可能走 openpyxl 全量重写，"
            "drawing/chart/pivot 被丢掉",
        tags=("strategy",),
    ),
    Mutation(
        id="M40", side="be", path=MAT, kind="replace",
        anchor="    present = facts.protected_aspects_present",
        new="    present = ()",
        want=f"{T38}::TestWriteStrategyGate"
             "::test_protected_parts_refuse_openpyxl_even_with_capability",
        why="不再实测受保护部件 ⇒ capability 说「安全」就照办，而实测这个模板含 drawing",
        tags=("strategy",),
    ),
    Mutation(
        id="M41", side="be", path=MAT, kind="replace",
        anchor="    blocked = sorted(set(CAPABILITY_REQUIRED_PROBE_ASPECTS) & set(uncovered))",
        new="    blocked = []",
        want=f"{T38}::TestWriteStrategyGate::test_uncovered_probe_aspect_refuses_openpyxl",
        why="探针 not_covered 不再拦 ⇒ 「未取证」被当成「已证明安全」（Requirement 6.16）",
        tags=("strategy",),
    ),
    Mutation(
        id="M42", side="be", path=MAT, kind="replace",
        anchor="        missing = sorted(",
        new="        missing = [] if True else sorted(",
        want=f"{T38}::TestWriteStrategyGate"
             "::test_capability_not_declaring_coverage_refuses_openpyxl",
        why="capability 未声明覆盖关键部件时不再拒 ⇒ 声明与取证脱钩。首轮写成 `[] or sorted(...)` "
            "⇒ **无效变异**（`[]` 是假值，`or` 直接取右支，语义完全不变）⇒ GREEN 是脚本缺陷"
            "而不是守卫缺陷；短路式必须真的短路",
        tags=("strategy",),
    ),
    Mutation(
        id="M43", side="be", path=MAT, kind="replace",
        anchor="    if not decision.openpyxl_allowed:",
        new="    if False:",
        want=f"{T38}::TestWriteStrategyGate::test_openpyxl_path_is_fail_closed_at_its_own_entry",
        why="`apply_plan_openpyxl` 不再 fail closed ⇒ 「只有放行时才可调用」退回成 docstring "
            "约定，新调用点漏判就全量重写一个含 drawing 的工作簿",
        tags=("strategy",),
    ),
    # ── 失败形态互不折叠 ────────────────────────────────────────────
    Mutation(
        id="M44", side="be", path=MAT, kind="replace",
        anchor='    error_code = "excel_materialize_shared_formula_master_write"',
        new='    error_code = "excel_materialize_protected_region_violation"',
        want=f"{T38}::TestFailureKindsAreReachableAndMutuallyDistinct"
             "::test_registry_matches_the_concrete_exception_classes",
        why="两个异常类共用同一个 error_code ⇒ 「契约说受保护却被改」与「契约说 editable 但那是"
            "公式源」在诊断上不可分辨，靠前的分支永久不可达（本 spec 已三次实测的假绿形态）",
        tags=("kinds",),
    ),
    Mutation(
        id="M45", side="be", path=MAT, kind="replace",
        anchor='    "excel_materialize_footer_formula_range_stale": (',
        new='    "excel_materialize_not_a_real_kind": (',
        want=f"{T38}::TestFailureKindsAreReachableAndMutuallyDistinct"
             "::test_registry_matches_the_concrete_exception_classes",
        wants=(
            f"{T38}::TestFailureKindsAreReachableAndMutuallyDistinct"
            "::test_every_registered_failure_kind_is_really_reachable",
        ),
        why="把登记清单里的一个 key 改成不存在的 kind ⇒ 清单与异常类双向等值不成立"
            "（基数不变但集合不等 ⇒ 两条判据都打红）。首轮用 `delete` 删 key 行 ⇒ 值行悬空成 "
            "SyntaxError ⇒ collection error ⇒ WRONG-TEST（本 spec 已实测过的替换体语法陷阱）",
        tags=("kinds",),
    ),
    # ── 登记裁决（跨任务共享表，归因型判据）────────────────────────
    Mutation(
        id="M46", side="be", path=MERGE, kind="replace",
        anchor='        "expected_consumer_module": "app/services/workpaper_sync/excel_materialize.py",',
        new='        "expected_consumer_module": "app/services/workpaper_sync/not_there.py",',
        want=f"{T14}::TestTask14ScopeBoundary::test_retired_deferral_records_who_wired_it",
        wants=(
            f"{T14}::TestTask14ScopeBoundary"
            "::test_merge_domain_consumers_match_the_retirement_registry_exactly",
            f"{T38}::TestTask38ScopeBoundary::test_merge_domain_retirement_is_registered_for_task38",
        ),
        why="Task 38 的退役登记指向不存在的模块 ⇒ 「谁在哪个任务接线」的记录与事实脱钩；"
            "Task 14 的双向等值判据与本任务的归因型判据都必须抓住它",
        tags=("registry",),
    ),
    Mutation(
        id="M47", side="be", path=MERGE, kind="replace",
        anchor='        "capability": "normalize_value / ValueNormalizationError（Excel 写入侧落盘值规范化）",',
        new='        "capability": "merge_projections / 写入侧",',
        want=f"{T38}::TestTask38ScopeBoundary::test_merge_domain_retirement_is_registered_for_task38",
        why="capability 写成 `merge_projections` ⇒ Task 14 的分域判据会要求本模块命中 merge 本体"
            "的接线语义，而它实际消费的只是 `normalize_value`；登记不准就无法核对欠账",
        tags=("registry",),
    ),
    Mutation(
        id="M48", side="be", path=REGISTRY, kind="replace",
        anchor='        "adapter_module": "app/services/workpaper_sync/adapters/excel.py",',
        new='        "adapter_module": "app/services/workpaper_sync/adapters/nope.py",',
        want=f"{T13}::TestTask13ScopeBoundary"
             "::test_engine_adapters_match_the_delivery_registry_exactly",
        wants=(f"{T38}::TestTask38ScopeBoundary::test_engine_delivery_is_registered_for_task38",),
        why="engine 交付登记指向不存在的 adapter 模块 ⇒ 「adapters/ 里的模块集合与登记双向等值」"
            "立刻不成立（少掉的意味着登记过期、多出来的意味着有人绕过载体 gate）",
        tags=("registry",),
    ),
    Mutation(
        id="M49", side="be", path=REGISTRY, kind="replace",
        anchor='            "app/services/workpaper_sync/excel_materialize.py",',
        new='            "app/services/workpaper_sync/excel_nowhere.py",',
        want=f"{T13}::TestTask13ScopeBoundary"
             "::test_engine_adapters_match_the_delivery_registry_exactly",
        wants=(f"{T38}::TestTask38ScopeBoundary::test_engine_delivery_is_registered_for_task38",),
        why="登记的 engine 模块不存在 ⇒ adapter 是空壳，protocol 方法没有真实实现可转手"
            "（假绿第①源）",
        tags=("registry",),
    ),
    Mutation(
        id="M50", side="be", path=REGISTRY, kind="replace",
        anchor='            "app/services/workpaper_sync/adapters/word.py",',
        new='            "app/services/workpaper_sync/adapters/base.py",',
        want=f"{T13}::TestTask13ScopeBoundary"
             "::test_engine_adapters_match_the_delivery_registry_exactly",
        why="把 Word engine 的 `forbidden_paths` 指到一个**已存在**的文件 ⇒ 「未过 pilot 门不得"
            "落地 adapter」这条判据当场打红。反向证明：该判据不是空转，它真的在查文件存在性",
        tags=("registry", "reverse"),
    ),
    # ── adapter 接线 ───────────────────────────────────────────────
    Mutation(
        id="M51", side="be", path=ADAPTER, kind="replace",
        anchor="        if contract.canonical_sha256 != frozen.canonical_sha256:",
        new="        if False:",
        want=f"{T38}::TestExcelAdapterWiring"
             "::test_cross_entry_contract_is_refused_at_every_protocol_entry",
        why="不再比对传入 contract 与冻结 contract 的 digest ⇒ 把 A entry 的 adapter 复用到 B "
            "entry 会按 A 的 identity binding 去写 B 的文件，受管格全部错位而零报错",
        tags=("adapter",),
    ),
    Mutation(
        id="M52", side="be", path=ADAPTER, kind="replace",
        anchor='    if direction == "oo_to_html" and baseline_representation is None:',
        new="    if False:",
        want=f"{T38}::TestExcelAdapterWiring"
             "::test_oo_to_html_requires_the_frozen_base_representation",
        why="OO→HTML 缺 base representation 也放行 ⇒ Property 24 的 baseline 来源没了，"
            "受保护格篡改在生产上完全不可见",
        tags=("adapter",),
    ),
    Mutation(
        id="M53", side="be", path=ADAPTER, kind="replace",
        anchor="        if STAGING_NAMESPACE in resolved.parts:",
        new="        if False:",
        want=f"{T38}::TestExcelAdapterWiring"
             "::test_adapter_extract_classifies_the_substrate_shape_by_path",
        why="staged result 不再被识别 ⇒ `ContentMutationService` 反读自己刚写的产物时会被当成 "
            "published/incoming，substrate 准入矩阵判错",
        tags=("adapter",),
    ),
    Mutation(
        id="M54", side="be", path=ADAPTER, kind="replace",
        anchor="    if direction not in shapes:",
        new="    if False:",
        want=f"{T38}::TestExcelAdapterWiring::test_direction_is_a_closed_vocabulary",
        why="direction 从封闭词表退化成自由文本 ⇒ substrate 形态由调用方随手拼的字符串决定"
            "（AC 8.10）",
        tags=("adapter",),
    ),
    Mutation(
        id="M55", side="be", path=ADAPTER, kind="replace",
        anchor='        if self.definitions.contract.document_type != "xlsx":',
        new="        if False:",
        want=f"{T38}::TestExcelAdapterWiring::test_adapter_only_accepts_xlsx",
        why="Excel adapter 不再拒 docx 契约 ⇒ Word 底稿会被 Excel engine 按 Table/UUID 列去解析，"
            "而 Word engine 的载体门（F2-22/F2-23 pilot）根本还没过",
        tags=("adapter",),
    ),
    Mutation(
        id="M56", side="be", path=ADAPTER, kind="replace",
        anchor="        assert_no_mutation_surface(self, label=\"ExcelSyncAdapter\")",
        new="        _ = self",
        want=f"{T38}::TestExcelAdapterWiring"
             "::test_adapter_construction_rejects_a_field_with_a_write_surface",
        why="adapter 构造时不再实测「零写入面」⇒ 传进来的字段可以带 session/outbox，"
            "engine 就有了第二个 commit 边界（Property 61）。首轮 want 指向源码文本判据 ⇒ "
            "GREEN：删调用不会让「源码里没有 session」这句话变假 —— 判据必须落在行为上",
        tags=("adapter",),
    ),
]

GUARD_FILES = {
    T38: "Task 38 新建（materializer / rematerializer / adapter 守卫）",
    T38PG: "Task 38 新建（真库：纯表示升级不推进 content revision）",
    T13: "Task 13（engine adapter 交付登记的双向等值判据）",
    T14: "Task 14（merge 域消费方退役登记的双向等值判据）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 38 Excel materializer / rematerializer 守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task38_excel_materialize.py",
                "backend/tests/workpaper_sync/test_task38_excel_materialize_pg.py",
                "backend/tests/workpaper_sync/test_task13_contract_registry.py",
                "backend/tests/workpaper_sync/test_task14_merge_conflicts.py",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=None,
        )
    )
