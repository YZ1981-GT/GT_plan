# -*- coding: utf-8 -*-
"""Task 17 变异检验：Excel instrumentation 载体门 / 发布 DAG / 可见等价 / candidate
非当前性的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 17
Requirements: 2.1, 2.3, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.19, 9.1, 9.8, 9.9,
9.10, 14.16
Properties: **P28**（definition 漂移 fail closed）/ **P66**（只用真实 OO 探针通过的载体）/
            **P67**（先 candidate、approved bundle 后 finalize）/ **P71**（evidence stale）

═══ 变异改的是**生产代码**，不是守卫 ═══

落点五处：

* `workpaper_sync/excel_instrumentation.py` —— 载体/锚点门短路、Tier A/B stale 比对
  短路、payload 反向引用注入、locator 换成被证伪的锚点、authority_root 换成参考副本、
  Table `headerRowCount` 置 1、UUID 列不隐藏、`_GT_SYNC` 改成可见、预写 runtime
  binding、等价判定短路、重复注入闸门短路、行区间漂移不 fail closed、反读退回被证伪的
  sheet 定位路径、采集异常降级、禁用方法集合缩水、门面不包裹、四条非当前性断言逐条短路、
  candidate state 直接写 ready、伪造 target contract、`_snapshot` 测不到真 pointer
* `excel_metadata_sheet_policy.py` —— 排除名单越界收进离线导入的 `_meta_`、过滤时重排序
* `xlsx_read_adapter.py` —— calamine 分支退回 `list(...)`（不排除隐藏 metadata sheet）
* `xlsx_to_univer.py` —— Univer 快照分支退回逐 `wb.sheetnames`

判定四态：打红=RED（守卫有效）；不红=GREEN（**守卫缺陷**）；红了但不是预期项=WRONG-TEST；
锚点未命中/命中多处=ANCHOR-MISS（脚本缺陷）。GREEN 一律当守卫缺陷逐条归因，不降标。

═══ 本任务实测到的两个守卫缺口（已补齐，不是「事后解释」）═══

首轮设计变异清单时发现两条生产判据**没有任何守卫**，改成 `pass` 全绿：

1. `ExcelIdentityCarrierGate.assert_carrier_allowed` 的 raise（Property 66 的
   「任一载体缺失即阻断 engine gate」）。原因是既有守卫只改逐条 `probe_verdict`，
   被 `_assert_gate_matches_verdicts` 的集合相等判据拦在 `load()` 里 ⇒ 这条门永远
   走不到。补 `test_a_consistently_retracted_carrier_blocks_the_engine_gate`：把
   verdict 与 gate 清单**一致地**改成「该载体已被证伪」，于是 `load()` 合法通过、
   allowed 集合真的少一个。→ M05
2. `assert_evidence_fresh` 的 **digest 漂移**分支。既有守卫只走「文件不存在」，
   把 digest 比对删掉不会变红。补 `test_tier_b_digest_drift_makes_the_gate_stale`。
   → M09

这两条正是「变异检验不是给已有守卫盖章，而是找缺口」的实例。

═══ 无效变异的三个陷阱（本清单刻意避开）═══

1. **删掉只在坏输入上生效的防御 = 行为不变**。例如把
   `validate_instrumentation_payload(payload)` 删掉：正常 payload 本来就合法，
   删了也全绿，而这不是守卫缺陷。→ 改成**注入坏输入**（M11 往 payload 插一个
   `definition_bundle_sha256` 反向引用），让那条调用真正被逼着报错。
2. **契约里全 passed 的枚举做「去掉过滤器」变异是空操作**。四个 carrier 全 `passed`，
   所以 `passed_carriers` 的推导式去掉 `== "passed"` 后集合不变 ⇒ 无效变异。
   anchors 侧两个是 `failed`，去掉过滤器集合真的变 ⇒ 只对 anchors 做（M03）。
3. **`list_sheet_names` 有 calamine / openpyxl 两条分支**。本机 `python_calamine`
   已安装 ⇒ 生产实际走 calamine 那条；只改 openpyxl 兜底分支会全绿（假 GREEN）。
   故 M26 落在 calamine 分支上。

用法（仓库根）::

    python backend/scripts/diagnose/mutate_task17_excel_instrumentation_guards.py --list
    python backend/scripts/diagnose/mutate_task17_excel_instrumentation_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_task17_excel_instrumentation_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/\\
evidence/task17-excel-instrumentation/mutation_report.json

单批跑（避免单次调用超时）::

    ... --run M01,M02,...  --out <批次报告路径>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

EI = "backend/app/services/workpaper_sync/excel_instrumentation.py"
POLICY = "backend/app/services/excel_metadata_sheet_policy.py"
ADAPTER = "backend/app/services/xlsx_read_adapter.py"
UNIVER = "backend/app/services/xlsx_to_univer.py"

D = "test_task17_excel_instrumentation.py"
P = "test_task17_excel_instrumentation_pg.py"

GUARD_FILES = {
    D: "Task 17 纯域守卫（载体门 / payload / 真实模板注入等价 / 反读 / 业务排除 / candidate 断言）",
    P: "Task 17 真实 PostgreSQL 守卫（pointer/revision/representation 零变化、candidate 不可解析）",
}


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # A. 载体裁决门与 stale 门（Property 66 / 71 · Requirement 6.16 / 14.16）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=EI, kind="replace",
        anchor="        if declared_carriers != passed_carriers:",
        new="        if False:  # MUT: 不再交叉核对 gate 清单与逐条 probe_verdict",
        want=f"{D}::TestCarrierGateIsFailClosed::"
             "test_each_carrier_verdict_downgrade_is_independently_fail_closed",
        why="契约的 `gate_for_downstream_tasks.allowed_carriers` 与逐 carrier "
            "`probe_verdict` 不再互锁 ⇒ 只改一侧即可悄悄放行未过真实 OO 探针的载体。"
            "这正是 Task 5 契约 loader_rule 明文禁止的降级路径",
    ),
    Mutation(
        id="M02", side="be", path=EI, kind="replace",
        anchor="        if not declared_forbidden:",
        new="        if False:  # MUT: 允许 forbidden_anchors 为空集",
        want=f"{D}::TestCarrierGateIsFailClosed::test_emptying_forbidden_anchors_is_fail_closed",
        why="空集判据是三条集合相等判据之外**唯一**能拦住「两侧一起改成没有禁用锚点」"
            "的门。Task 5 已证伪 sheet_id 与 sheet 展示名，forbidden 恒非空",
    ),
    Mutation(
        id="M03", side="be", path=EI, kind="replace",
        anchor='            name for name, a in anchors.items() if a.get("probe_verdict") == "passed"',
        new="            name for name, a in anchors.items()",
        want=f"{D}::TestCarrierGateIsFailClosed::"
             "test_allowed_sets_are_reverse_computed_from_probe_verdicts",
        why="allowed_anchors 不再由逐条裁决反算 ⇒ 被证伪的 sheet_id / sheet_display_name "
            "混进 passed 集合。carriers 侧四个全 passed，去掉过滤器是空操作（无效变异），"
            "所以只能在 anchors 侧做这条检验",
    ),
    Mutation(
        id="M04", side="be", path=EI, kind="replace",
        anchor="        if anchor in self.forbidden_anchors:",
        new="        if False:  # MUT: 被证伪的锚点不再有专属异常类型",
        want=f"{D}::TestCarrierGateIsFailClosed::test_disproved_anchor_gets_its_own_exception_type",
        why="短路 forbidden 分支后 allowed 分支会顶上来抛通用 `CarrierGateError` ⇒ 行为"
            "看似仍拒绝，但拒绝理由不再指出「已被实证证伪」。异常类型分家就是为了让这条"
            "短路可被 falsify（Task 12/13/14/15 连续踩过共用类型的坑）",
    ),
    Mutation(
        id="M05", side="be", path=EI, kind="replace",
        anchor="        if carrier not in self.allowed_carriers:",
        new="        if False:  # MUT: 未过探针的载体也放行",
        want=f"{D}::TestCarrierGateIsFailClosed::"
             "test_a_consistently_retracted_carrier_blocks_the_engine_gate",
        why="Property 66 的后半句「任一缺失阻断 engine gate」的**唯一**落点。首轮变异"
            "实测这条改成 pass 后全绿（既有守卫都被 load() 的集合相等判据拦在前面），"
            "因此补了一条一致撤回载体的场景",
    ),
    Mutation(
        id="M06", side="be", path=EI, kind="replace",
        anchor='            if observed != item["sha256"]:',
        scope="                path = contract_file", offset=6,
        new="            if False:  # MUT: Tier A 文件 digest 漂移不再判 stale",
        want=f"{D}::TestProbeEvidenceStaleness::test_contract_byte_drift_makes_the_gate_stale",
        why="契约本体/`excel_structure_fingerprint` 变了仍按旧裁决 instrumentation ⇒ "
            "Property 71 的第 1、3 项 invalidate_on 失效",
    ),
    Mutation(
        id="M07", side="be", path=EI, kind="replace",
        anchor='            if observed != item["sha256"]:',
        scope="                    f\"探针覆盖的权威模板缺失: {item['template_id']} → {path}\"",
        offset=3,
        new="            if False:  # MUT: 权威模板 digest 漂移不再判 stale",
        want=f"{D}::TestProbeEvidenceStaleness::test_probed_template_drift_makes_the_gate_stale",
        why="探针取证用的那两份权威模板换了内容，载体裁决与等价基线本应整体失效；"
            "短路后会拿旧实证去 instrumentation 一份结构已变的模板",
    ),
    Mutation(
        id="M08", side="be", path=EI, kind="replace",
        anchor="            if not path.is_file():",
        scope='        for item in baseline["tier_b_evidence"]["files"]:', offset=2,
        new="            if True is False:  # MUT: evidence 缺文件降级成跳过",
        want=f"{D}::TestProbeEvidenceStaleness::test_missing_evidence_file_is_stale_not_skipped",
        why="evidence 不在了却继续放行 = 把「实证没了」伪装成「无需检查」。"
            "缺文件必须判 stale 而不是 skip（Requirement 14.16）",
    ),
    Mutation(
        id="M09", side="be", path=EI, kind="replace",
        anchor='            if got != item["sha256"]:',
        new="            if False:  # MUT: Tier B evidence 内容漂移不再判 stale",
        want=f"{D}::TestProbeEvidenceStaleness::test_tier_b_digest_drift_makes_the_gate_stale",
        why="probe 脚本 / operation_matrix / instrumentation_report 内容变了仍算新鲜 ⇒ "
            "旧 test run 不会 stale。首轮变异实测这条改成 pass 后全绿（既有守卫只走"
            "「文件不存在」那条分支），因此补了内容漂移场景",
    ),
    Mutation(
        id="M10", side="be", path=EI, kind="replace",
        anchor="        except PathBoundaryError as exc:",
        new="        except FileNotFoundError as exc:  # MUT: 越界不再翻成本模块异常",
        want=f"{D}::TestInstrumentationPayload::test_template_outside_authority_root_is_rejected",
        why="`PathBoundaryError` 不是 `InstrumentationError` 子类（实测 mro 已确认）⇒ "
            "参考副本路径与 `..` 逃逸会抛一个调用方 fail-closed 分支接不住的类型，"
            "Requirement 9.1 的拒绝语义断在半路",
    ),

    # ═══════════════════════════════════════════════════════════════════
    # B. canonical payload 与发布 DAG（Property 28 · Requirement 6.14 / 9.1）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M11", side="be", path=EI, kind="insert",
        anchor='        "identity_anchors": list(identity_anchors),',
        new='        "definition_bundle_sha256": template_definition_sha256,'
            "  # MUT: 反向引用",
        want=f"{D}::TestInstrumentationPayload::test_payload_passes_task12_validator",
        why="instrumentation payload 里出现 bundle digest = 发布 DAG 反向引用（Task 13 "
            "明文禁止）。刻意用**注入坏输入**而不是删掉 `validate_instrumentation_payload` "
            "调用：删调用在合法 payload 上行为不变，是无效变异",
    ),
    Mutation(
        id="M12", side="be", path=EI, kind="replace",
        anchor='                    "anchor": "defined_name_ref",',
        scope='                "locator": {', offset=1,
        new='                    "anchor": "sheet_display_name",  # MUT: 被证伪的锚点',
        want=f"{D}::TestInstrumentationPayload::test_no_locator_uses_a_disproved_anchor",
        wants=(
            f"{D}::TestInstrumentationPayload::"
            "test_payload_carries_no_sheet_id_or_display_name_as_identity",
        ),
        why="受管 sheet 的 locator 改用 sheet 展示名 ⇒ 用户改名后 identity 直接失联"
            "（Task 5 实测改名场景）。判据必须是**结构式**逐 locator 检查，"
            "全文 grep 会被 payload 里那份给下游 loader 的黑名单字段误伤",
    ),
    Mutation(
        id="M13", side="be", path=EI, kind="replace",
        anchor='        "authority_root": "backend/wp_templates",',
        new='        "authority_root": "基础数据/致同通用审计程序及底稿模板（2025年修订）",'
            "  # MUT",
        want=f"{D}::TestInstrumentationPayload::test_template_payload_pins_the_authority_root",
        why="template definition 声明的权威源换成**已落后的参考副本** ⇒ 下游按参考副本"
            "复现 instrumentation，与运行时真模板不一致（Requirement 9.1）",
    ),
    Mutation(
        id="M14", side="be", path=EI, kind="delete",
        anchor='    "GT_DEFINITION_BUNDLE_SHA256",',
        want=f"{D}::TestInstrumentationPayload::test_payload_declares_runtime_binding_as_finalize_only",
        why="runtime binding 键集少一个 ⇒ instrumentation 阶段可以合法预写 bundle digest，"
            "candidate 看起来已绑定 bundle。design 要求五个 digest 全部只在 finalize 写入",
    ),
    Mutation(
        id="M15", side="be", path=EI, kind="replace",
        anchor='            "user_deleted_identity_column": "reject",',
        new='            "user_deleted_identity_column": "allocate_new_id",  # MUT',
        want=f"{D}::TestInstrumentationPayload::"
             "test_row_uuid_disposition_matches_contract_classification",
        why="用户删掉 identity 列后改成「静默分配新 ID」= 按位置猜行身份，与 Task 5 契约"
            "`requirement_6_15_classification` 裁决的「拒绝」相反（Requirement 6.15）",
    ),

    # ═══════════════════════════════════════════════════════════════════
    # C. 真实注入与可见等价（Requirement 6.13 / 6.17）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M16", side="be", path=EI, kind="replace",
        anchor='        f\'ref="{ref}" headerRowCount="0" totalsRowShown="0">\'',
        new='        f\'ref="{ref}" headerRowCount="1" totalsRowShown="0">\'  # MUT',
        want=f"{D}::TestIdentityReadback::test_table_header_row_count_is_zero",
        why="`headerRowCount=1` 会把业务两级合并表头的第一行当成 Table 表头行 ⇒ 受管行"
            "区域整体错位一行，且 Excel 可能改写该行样式（可见结构被动）",
    ),
    Mutation(
        id="M17", side="be", path=EI, kind="replace",
        anchor='    col = f\'<col min="{col_no}" max="{col_no}" width="9" hidden="1" customWidth="1"/>\'',
        new='    col = f\'<col min="{col_no}" max="{col_no}" width="9" hidden="0" customWidth="1"/>\''
            "  # MUT",
        want=f"{D}::TestIdentityReadback::test_row_uuids_are_pregenerated_literals",
        wants=(f"{D}::TestVisibleEquivalenceOnRealTemplates::test_no_collection_errors",),
        why="UUID 列不再隐藏 ⇒ 审计师会在底稿里看到一列 `GTROW-K11-0007` 之类的内部标识，"
            "Requirement 6.13 的「不改变可见业务内容」被破坏",
    ),
    Mutation(
        id="M18", side="be", path=EI, kind="replace",
        anchor='        f\'state="hidden" r:id="{_GT_SYNC_REL_ID}"/>\',',
        new='        f\'state="visible" r:id="{_GT_SYNC_REL_ID}"/>\',  # MUT',
        want=f"{D}::TestVisibleEquivalenceOnRealTemplates::"
             "test_metadata_sheet_is_hidden_and_out_of_business_enumeration",
        wants=(f"{D}::TestVisibleEquivalenceOnRealTemplates::test_no_collection_errors",),
        why="`_GT_SYNC` 变成可见 sheet ⇒ OO 标签栏与全部业务枚举都会多出一张审计师无法"
            "解释的表，可见 sheet 集合也不再等价（Requirement 6.17）",
    ),
    Mutation(
        id="M19", side="be", path=EI, kind="insert",
        anchor='        ("GT_ROW_UUID_COLUMN", spec.uuid_col),',
        new='        ("GT_DEFINITION_BUNDLE_SHA256", "0" * 64),  # MUT: 预写 runtime binding',
        want=f"{D}::TestIdentityReadback::test_gt_sync_has_no_runtime_binding_key",
        wants=(f"{D}::TestVisibleEquivalenceOnRealTemplates::test_no_collection_errors",),
        why="instrumentation 阶段就往 `_GT_SYNC` 写 bundle digest ⇒ contract / bundle / "
            "authority model 此刻根本不存在，写占位值会让 candidate 看起来已绑定 bundle。"
            "这条同时检验 `assert_no_runtime_binding` 的**调用点**是活的",
    ),
    Mutation(
        id="M20", side="be", path=EI, kind="replace",
        anchor='    if not report["equivalent"]:',
        new="    if False:  # MUT: 不等价也放行",
        want=f"{D}::TestVisibleEquivalenceOnRealTemplates::test_equivalence_is_falsifiable",
        why="可见等价判定短路 ⇒ 破坏业务单元格的 instrumentation 照样进 candidate。"
            "Requirement 6.17 的六个 aspect 比对全部作废",
    ),
    Mutation(
        id="M21", side="be", path=EI, kind="replace",
        anchor="    if _GT_SYNC_SHEET_PART in entries or _GT_TABLE_PART in entries:",
        new="    if False:  # MUT: 允许重复注入",
        want=f"{D}::TestVisibleEquivalenceOnRealTemplates::"
             "test_reinstrumenting_an_instrumented_artifact_is_rejected",
        why="已 instrumented 的 artifact 再注入一次 ⇒ 两套 defined name / 两个 Table / "
            "两列 UUID，行身份出现二义，下游 extract 无法判定哪套是权威",
    ),
    Mutation(
        id="M22", side="be", path=EI, kind="replace",
        anchor="        if not opened:",
        new="        if False:  # MUT: 行不存在不再 fail closed",
        want=f"{D}::TestVisibleEquivalenceOnRealTemplates::"
             "test_managed_row_range_outside_the_sheet_fails_closed",
        why="声明的受管行区间超出模板实际结构时不再报出「找不到第 N 行」，而是在 None 上"
            "崩成 AttributeError ⇒ 调用方的 fail-closed 分支接不住（Requirement 6.10 "
            "要求结构漂移在写入前失败并指出位置）",
    ),

    # ═══════════════════════════════════════════════════════════════════
    # D. identity 反读（Requirement 6.14 / 6.15 / 6.20）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M23", side="be", path=EI, kind="insert",
        anchor="            uuid_column_letter=spec.uuid_col,",
        new="            uuid_sheet_name=spec.managed_sheet,  # MUT: 退回被证伪的定位路径",
        want=f"{D}::TestIdentityReadback::test_sheet_resolution_only_uses_the_probed_anchor",
        why="反读一旦传 `uuid_sheet_name`，`sheet_resolution_candidates` 里就多出 "
            "`sheet_name` 这条被 Task 5 证伪的路径（OO 允许用户改名）。判据是**结构**："
            "生产反读结构上不可能退化到它，而不是「记得别传」",
    ),
    Mutation(
        id="M24", side="be", path=EI, kind="replace",
        anchor='    if col["resolved_sheet_by"] is None:',
        new="    if False:  # MUT: 删列不再归类成 Requirement 6.15 的「拒绝」",
        want=f"{D}::TestRequirement615Dispositions::"
             "test_deleted_identity_column_is_detectable_and_fails_closed",
        why="「用户删掉整列 UUID」会掉进下一条锚点分支，被报成 ForbiddenAnchorError"
            "（锚点用错）⇒ 错误原因指错地方，真正的锚点误用分支变得不可分辨。"
            "这检验的是**判据顺序**：语义分类在前、锚点校验在后",
    ),
    Mutation(
        id="M25", side="be", path=EI, kind="replace",
        anchor="    except FingerprintError as exc:  # 采集失败绝不降级成「无 identity」",
        new="    except ZeroDivisionError as exc:  # MUT: 采集异常不再翻成反读失败",
        want=f"{D}::TestIdentityReadback::test_readback_rejects_dangling_table_part",
        why="`identity_inventory` 采集失败时异常穿透 ⇒ 调用方按「未知异常」处理，而不是"
            "「identity 反读失败」。fail-open 的镜像形态：结构损坏被读成别的原因",
    ),

    # ═══════════════════════════════════════════════════════════════════
    # E. 业务 sheet 排除（Requirement 6.17 后半句）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M26", side="be", path=ADAPTER, kind="replace",
        anchor="            return exclude_metadata_sheets(CalamineWorkbook.from_path(str(fp)).sheet_names)",
        new="            return list(CalamineWorkbook.from_path(str(fp)).sheet_names)  # MUT",
        want=f"{D}::TestBusinessSheetExclusion::"
             "test_production_sheet_enumerator_excludes_metadata_sheet",
        why="`list_sheet_names` 是模板 diff / 程序表抽取 / 审定表抽取 / 细则引擎 / 通用"
            "处理器 / 裁决导出六处业务枚举的共同入口。落在 **calamine** 分支上是因为本机"
            "`python_calamine` 已安装、生产实际走它；只改 openpyxl 兜底分支会假 GREEN",
    ),
    Mutation(
        id="M27", side="be", path=UNIVER, kind="replace",
        anchor="    for idx, ws_name in enumerate(exclude_metadata_sheets(wb.sheetnames)):",
        new="    for idx, ws_name in enumerate(wb.sheetnames):  # MUT",
        want=f"{D}::TestBusinessSheetExclusion::test_univer_snapshot_excludes_metadata_sheet",
        why="Univer 快照逐 sheet 转换时不再排除 ⇒ 编辑器标签栏多出 `_GT_SYNC`。"
            "OO 自己不显示隐藏 sheet，但平台自建的 Univer 快照会",
    ),
    Mutation(
        id="M28", side="be", path=POLICY, kind="replace",
        anchor="PLATFORM_METADATA_SHEETS: frozenset[str] = frozenset({GT_SYNC_SHEET_NAME})",
        new='PLATFORM_METADATA_SHEETS: frozenset[str] = frozenset({GT_SYNC_SHEET_NAME, "_meta_"})'
            "  # MUT",
        want=f"{D}::TestBusinessSheetExclusion::test_offline_import_meta_sheet_is_not_swept_up",
        wants=(f"{D}::TestBusinessSheetExclusion::test_policy_reuses_the_single_source_sheet_name",),
        why="排除名单**越界**收进离线导入自有的 `_meta_` ⇒ `wp_offline_import_service` / "
            "`note_offline_import_service` 的「枚举不到 `_meta_` 就拒绝导入」前置全线失效。"
            "范围判据必须双向可 falsify：只测「`_GT_SYNC` 被排除」的话顺手扩张不会被发现",
    ),
    Mutation(
        id="M29", side="be", path=POLICY, kind="replace",
        anchor="    return [str(n) for n in names if not is_platform_metadata_sheet(n)]",
        new="    return sorted(str(n) for n in names if not is_platform_metadata_sheet(n))  # MUT",
        want=f"{D}::TestBusinessSheetExclusion::test_exclusion_preserves_order",
        why="过滤时重排序 ⇒ 多处业务代码按「第一个 sheet」取默认表"
            "（`read_sheet_values(sheet_name=None)`），静默换表且不报错",
    ),

    # ═══════════════════════════════════════════════════════════════════
    # F. candidate 非当前性（Property 67 · Requirement 6.18 / 9.10）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M30", side="be", path=EI, kind="replace",
        anchor='        {"create_representation", "set_entry_pointer", "finalize_candidate"}',
        new='        {"set_entry_pointer", "finalize_candidate"}  # MUT: 漏掉发布 representation',
        want=f"{D}::TestCandidateOnlyRepository::"
             "test_forbidden_set_covers_representation_pointer_finalize_and_revision",
        wants=(f"{P}::TestCandidateArtifactIsIsolated::"
               "test_forbidden_methods_are_unreachable_on_a_real_repository",),
        why="`create_representation` 从禁用面漏出 ⇒ 本任务可以直接发布 published "
            "representation，Property 67 的「先 candidate」承诺失去可执行判据",
    ),
    Mutation(
        id="M31", side="be", path=EI, kind="replace",
        anchor="    ) | frozenset(REVISION_DOMAIN_WRITE_METHODS)",
        new="    )  # MUT: 不再并入 Task 15 的 revision 写入面",
        want=f"{D}::TestCandidateOnlyRepository::"
             "test_forbidden_set_covers_representation_pointer_finalize_and_revision",
        wants=(f"{P}::TestCandidateArtifactIsIsolated::"
               "test_forbidden_methods_are_unreachable_on_a_real_repository",),
        why="revision 域三件套不再被禁 ⇒ 纯 instrumentation 可以递增 content revision"
            "（Requirement 2.1 明文禁止）。取并集而不是手抄清单，正是为了让 Task 15 那边"
            "新增 writer 时这里不会漏；短路它即回到手抄语义",
    ),
    Mutation(
        id="M32", side="be", path=EI, kind="replace",
        anchor="        if name in CANDIDATE_FORBIDDEN_METHODS:",
        new="        if False:  # MUT: 门面不再拦任何方法",
        want=f"{D}::TestCandidateOnlyRepository::test_each_forbidden_method_is_unreachable",
        wants=(f"{P}::TestCandidateArtifactIsIsolated::"
               "test_forbidden_methods_are_unreachable_on_a_real_repository",),
        why="门面退化成纯透传 ⇒ 「不得发布 representation / 切 pointer / finalize / 推进 "
            "revision」四条否定式承诺同时失去判据。禁令做成门面而不是「本模块没写那段代码」"
            "的全部意义就在这里",
    ),
    Mutation(
        id="M33", side="be", path=EI, kind="replace",
        anchor="            if isinstance(repository, CandidateOnlyRepository)",
        new="            if True  # MUT: 裸 repository 不再被无条件包裹",
        want=f"{D}::TestCandidateOnlyRepository::test_upgrader_wraps_a_bare_repository_unconditionally",
        why="调用方传裸 repository 时 upgrader 直接拿到全部写入面 ⇒ 门面形同虚设，"
            "而单测若只用已包装的门面则完全看不出来",
    ),
    Mutation(
        id="M34", side="be", path=EI, kind="replace",
        anchor="    if not outcome.revision_unchanged:",
        new="    if False:  # MUT: 不再断言 revision 未变",
        want=f"{D}::TestCandidateNonCurrencyAssertions::test_revision_advance_only",
        why="四条非当前性断言逐条短路，用来证明每个合取项都有只违反它自己的场景"
            "（Task 15 复盘第 2 条）。这条对应 Requirement 2.1 的 content revision",
    ),
    Mutation(
        id="M35", side="be", path=EI, kind="replace",
        anchor="    if not outcome.pointer_unchanged:",
        new="    if False:  # MUT: 不再断言 entry pointer 未动",
        want=f"{D}::TestCandidateNonCurrencyAssertions::test_pointer_move_only",
        why="candidate 阶段切了 entry pointer 也不报 ⇒ candidate 直接变成 current，"
            "Property 67 的「不得暴露为 current」失去判据",
    ),
    Mutation(
        id="M36", side="be", path=EI, kind="replace",
        anchor="    if not outcome.no_representation_created:",
        new="    if False:  # MUT: 不再断言 representation 行数未增",
        want=f"{D}::TestCandidateNonCurrencyAssertions::test_representation_created_only",
        why="新增了 representation 行也算通过 ⇒ 越过 `template → instrumentation → "
            "contract → bundle → representation` 的最后一段",
    ),
    Mutation(
        id="M37", side="be", path=EI, kind="replace",
        anchor="    if outcome.state not in (CandidateState.staged, CandidateState.awaiting_contract):",
        new="    if outcome.state not in tuple(CandidateState):  # MUT: 任何状态都算合法",
        want=f"{D}::TestCandidateNonCurrencyAssertions::test_forbidden_state_only",
        why="`ready` / `finalized` 也被当成本阶段合法状态 ⇒ 缺 approved bundle 与 "
            "compatibility 校验的 candidate 会显得可 finalize（Requirement 6.18）",
    ),
    Mutation(
        id="M38", side="be", path=EI, kind="replace",
        anchor="    if outcome.target_contract_definition_id is not None:",
        new="    if False:  # MUT: 允许带上 target contract",
        want=f"{D}::TestCandidateNonCurrencyAssertions::test_forged_contract_target_only",
        why="candidate 带上 per-entry contract target ⇒ 本任务伪造了只能由 Task 36 与 "
            "Tasks 40–57 人工审核发布的 approved child",
    ),
    Mutation(
        id="M39", side="be", path=EI, kind="replace",
        anchor="    if outcome.target_definition_bundle_id is not None:",
        new="    if False:  # MUT: 允许带上 target bundle",
        want=f"{D}::TestCandidateNonCurrencyAssertions::test_forged_bundle_target_only",
        why="candidate 带上 definition bundle target ⇒ 伪造 approved bundle，"
            "`RepresentationService.finalize_candidate()` 的前置校验被绕开",
    ),

    # ═══════════════════════════════════════════════════════════════════
    # G. 真库落库形态（Property 67 · 真实 PostgreSQL）
    # ═══════════════════════════════════════════════════════════════════
    Mutation(
        id="M40", side="be", path=EI, kind="replace",
        anchor="            state=CandidateState.awaiting_contract,",
        new="            state=CandidateState.ready,  # MUT: 直接写成 ready",
        want=f"{P}::TestAwaitingContractIsTerminalForThisTask::"
             "test_candidate_state_is_awaiting_contract",
        wants=(f"{P}::TestHarness::test_no_harness_errors",),
        why="缺 approved contract/bundle 却把 candidate 写成 `ready` ⇒ 下游会认为 "
            "compatibility 已通过、可直接 finalize。`awaiting_contract` 是本任务的终态",
    ),
    Mutation(
        id="M41", side="be", path=EI, kind="replace",
        anchor="            target_contract_definition_id=None,",
        scope="            #    直到 Task 36 与 Tasks 40–57 把 approved child 补齐。", offset=1,
        new="            target_contract_definition_id=template_definition.definition_id,  # MUT",
        want=f"{P}::TestHarness::test_no_harness_errors",
        wants=(f"{P}::TestAwaitingContractIsTerminalForThisTask::"
               "test_contract_and_bundle_targets_are_null_not_forged",),
        why="往 candidate 行真写一个 target contract（拿 template definition 冒充）⇒ "
            "落库形态上就伪造了 approved child。判据落在**数据库里的那一行**，"
            "不是 outcome 自报值",
    ),
    Mutation(
        id="M42", side="be", path=EI, kind="replace",
        anchor='                    "WHERE wp_id = :wp AND entry_id = :e"',
        scope='                    "SELECT current_representation_id FROM working_paper_sync_entry_state "',
        offset=1,
        new='                    "WHERE wp_id = :wp AND entry_id = :e || \'-none\'"  # MUT',
        want=f"{P}::TestCandidateChangesNothingCurrent::test_outcome_matches_the_database",
        why="pointer 快照恒查不到行 ⇒ before/after 都是 None、`pointer_unchanged` 恒真，"
            "「我没动 pointer」变成空集恒真。这检验的是 `_snapshot` 真的量到了那一行"
            "（假绿第③源：把空值当基线锁死）",
    ),
]


if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task17_excel_instrumentation.py",
            "backend/tests/workpaper_sync/test_task17_excel_instrumentation_pg.py",
            "-q", "--tb=no", "-rfE", "-p", "no:cacheprovider", "-p", "no:randomly",
        ],
        # 冻结基线来源：Task 17 收口实测（仓库根执行，2026-08-26）
        #   test_task17_excel_instrumentation.py       98 passed
        #     （93 条原有 + 一致撤回载体 4 条参数化 + Tier B digest 漂移 1 条）
        #   test_task17_excel_instrumentation_pg.py    34 passed
        baseline_backend_passed=132,
    ))
