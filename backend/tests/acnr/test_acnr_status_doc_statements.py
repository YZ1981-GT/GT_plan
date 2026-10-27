r"""T32 守卫（登记制）：架构提案「现状（2026-10-26）」节的每个陈述单元逐字登记并绑定复算判据。

段四复审第 2 轮 F4-02 残留（二）：`test_acnr_architecture_status_doc.py` 的数字绑定、完成态措辞、计划中符号
三条判据都是「拦已知坏写法」的黑名单，把审计 A1 的原假内容换个措辞写回现状节（复审变异 R2-D5 / R2-D6 /
R2-D7：发布后规模 1225 / 449 / 0、前端「统一从目录取显示名」、V2「节点身份已经规范化」）它们全绿。
本守卫改为白名单：现状节里任何新增或改写的陈述，在这里登记复算判据之前都打红。

1. 结构封闭：现状节每个非空行只能是——节标题、`_SUBSECTIONS` 登记的子节标题（顺序固定）、三张登记表格
   （表头逐字固定）的行、正文行。未登记的标题、其他子节里出现表格、表头或分隔行不符都红。
2. 陈述单元：
   - 正文行（去掉 `>` 引用与列表前缀）按「。」「；」「;」切句（「」、（）、() 与反引号内不切），每句一个单元；
     表格行须以竖线收尾（最后一个竖线之后的文字不进任何单元，不收尾即红）；
   - 事实表每行的「事实」单元格、组件表每行的「组件」单元格、计划表每行的「事项」单元格各一个单元。
   不单独成为单元的：事实表「值」列（由 test_fact_table_values_recomputed_from_artifacts 对产物现算）；
   事实表「复算键」、组件表「类型 / 模块 / 符号 / 测试」、计划表「任务」三类列随本行单元逐字登记（`Stmt.cols`）；
   节末结束行。「…」引文与版本格式字面量（`^\d{14}$`、`%Y%m%d%H%M%S`）随所在句逐字登记。复审规则允许
   「计划中（未落地）」子节、「…」引文与版本格式字面量不登记；本守卫更严：计划表「事项」也逐字登记（自动绑定
   「任务仍未勾选」），引文与版本格式字面量不单独成单元、随所在句整句登记，改动它们同样要改登记表。
3. 每个单元必须逐字出现在 `_STATEMENTS[所在子节]` 里并绑定复算判据（AST / 产物现算 / tasks.md 状态；勘误子节的
   引文另核对它确实逐字出现在节外原文的所述位置）。未登记即红，判据为假即红，登记表里节内已不存在的条目
   （失效条目）即红，同一子节重复出现也红。正文单元须至少有一个显式判据；组件行自动绑定「模块定义所列符号、
   测试文件有 test_ 函数」（后端，AST）或「模块与测试文件存在」（前端；前端描述另由 acnrArchitectureStatusDoc.spec.ts
   用 TS 编译器 API 核对），计划行自动绑定「任务列的任务仍未勾选」，事实行自动绑定「复算键是守卫认识的键」。

改现状节的做法：先改文档，再在 `_STATEMENTS` 里登记新句子并写出能证伪它的判据，删掉不再出现的旧条目。
切分与判据库在 `_status_doc_checks.py`。变异证明见 tmp_acnr_foundation/out/段四_修复记录.md。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

import pytest

from app.services.acnr import catalog_integrity as ci
from tests.acnr._status_doc_checks import (
    _DESIGN, _FE_GUARD_REL, _GEN_REL, _LINKAGE_REL, _RESOLVER_REL, _STALE_REL, _STATUS_GUARD_REL, _SUBSECTIONS,
    _TABLE_HEADERS, _THIS_REL, _V2_REL, H_ERRATA, H_INTRO, H_PARALLEL, H_VERSION, NON_WP_TO_V1, PLANNED_ROWS_OPEN,
    RESOLVER_DOC_OK,
    SCHEMA_FOLLOWS_CONTRACT, SPEC_TASKS, V1_BYPASS, Check, Unit,
    _component_tests_present, _exact_identity_is_pure, _exact_identity_only_release_imports,
    _generator_assigns_utc_timestamp, _orphan_verdicts_released, _parsed, _resolve_instance_binds_wp_code,
    _schema_file_is_generated, _sentences, _stale_impact_route, _task_ids, _units_and_structure_problems,
    _versions_are_timestamps, absent, calls, claim, defines, design_quote, exists, fact_eq, fact_ne, has_tests,
    in_planned, not_calls, not_imports, outside_unchanged, quote_at, task_done, task_open, task_open_at,
)
from tests.acnr.test_acnr_architecture_status_doc import (
    _REPO, H_COMPONENTS, H_FACTS, H_PLANNED, _cells, _claim_legacy_forwarding, _claim_stale_authz,
    _claim_version_format, _facts, _read, _strip_code, _task_states, _test_function_count,
)


# ─── 登记表：子节 → 陈述原文 → 判据 ──────────────────────────────────────────


@dataclass(frozen=True)
class Stmt:
    kind: str
    checks: tuple[Check, ...] = ()
    cols: tuple[str, ...] = ()


def P(*checks: Check) -> Stmt:
    return Stmt("prose", checks)


def F(key: str) -> Stmt:
    return Stmt("fact", (), (f"`{key}`",))


def CB(module: str, symbols: tuple[str, ...], test: str, *checks: Check) -> Stmt:
    return Stmt("component", checks, ("后端", f"`{module}`", "、".join(f"`{s}`" for s in symbols), f"`{test}`"))


def CF(module: str, symbol: str, test: str, *checks: Check) -> Stmt:
    return Stmt("component", checks, ("前端", f"`{module}`", f"`{symbol}`", f"`{test}`"))


def L(tasks: str) -> Stmt:
    return Stmt("planned", (), (tasks,))


_A = "backend/app/services/acnr/"
_T = "backend/tests/acnr/"
_BUILD_REL = _A + "catalog_build.py"
_NAMES_REL = _A + "catalog_names.py"
_STATEMENTS: dict[str, dict[str, Stmt]] = {
    H_INTRO: {
        "本节由实施 spec `acnr-foundation-defect-closure`（D12）补入，**只写当前 HEAD 可验证的事实**": P(
            SPEC_TASKS, claim("design.md 有「## 15. D12」节", lambda: any(
                ln.startswith("## 15. D12") for ln in _read(_DESIGN).split("\n"))),
            has_tests(_THIS_REL, "test_every_statement_unit_is_registered", "test_registered_criteria_hold")),
        "守卫 `backend/tests/acnr/test_acnr_architecture_status_doc.py` 逐项复算：「已落地」事实表的每个值从真实产物（`global_catalog.json`、`catalog_report.json`、快照、生成器源码）现算，组件表用 AST 确认模块、符号与测试存在，「计划中（未落地）」的任务号必须在 tasks.md 里仍未勾选": P(
            has_tests(_STATUS_GUARD_REL, "test_fact_table_values_recomputed_from_artifacts",
                      "test_component_rows_exist_by_ast", "test_planned_rows_reference_unchecked_tasks"),
            claim("事实表复算键覆盖目录 / 报告 / 快照 / 生成器源码四类产物", lambda: all(
                any(k.startswith(p) for k in _facts()) for p in ("catalog.", "report.", "snapshots.", "generator.")))),
        "节内每句正文与事实表「事实」、组件表「组件」、计划表「事项」三列的每个单元格都在守卫 `backend/tests/acnr/test_acnr_status_doc_statements.py` 里逐字登记并绑定复算判据（前端组件的描述另由 `audit-platform/frontend/src/services/acnr/tests/acnrArchitectureStatusDoc.spec.ts` 用 TS 编译器 API 核对），未登记、判据不成立或登记失效都打红": P(
            has_tests(_THIS_REL, "test_every_statement_unit_is_registered", "test_registered_criteria_hold",
                      "test_registry_has_no_stale_entries"), exists(_FE_GUARD_REL)),
        "本文其余段落为架构提案原文，未改一字，其中对「当前状态」的陈述以本节为准（见末尾「过时陈述勘误」）": P(
            outside_unchanged()),
        "修订（2026-10-27，段四审计 F4-01）：本节初版（提交 `96fba2c49`）把尚未实施的内容写成了现状（发布后目录规模、生成器结构化比对、版本锁持久化、跨模块单元格取值、显示名统一、「已完成 P0/P1/P2」等），已按上述口径重写": P(
            task_open_at("96fba2c49", "T05", "T07", "T14", "T17", "T29", "T30"),
            claim("tasks.md 的 33 个任务并未全部勾选（「已完成 P0/P1/P2」不成立）",
                  lambda: len(_task_states()) == 33 and not all(_task_states().values())),
            claim("现状节结构封闭（三张表与固定子节）", lambda: not _parsed()[1])),
        "未落地内容全部移到「计划中（未落地）」并标任务号": P(PLANNED_ROWS_OPEN),
    },
    H_FACTS: {
        "说明：现行 schema 由 `catalog_contract.build_schema()` 生成并改为跟随真实契约（purpose 改受控模式、functional_type 换成目录里实际出现的取值、`registry_version` 改为时间戳格式、`item_id` 允许数组，均有设计依据），所以上表的 schema 错误数（`catalog.schema_errors` 为 0）是 schema 修正的结果，不是目录本身被修正：审计报告记的报错数是 `b5fc200e0` 时的旧 schema 对同一份目录的校验结果": P(
            *SCHEMA_FOLLOWS_CONTRACT, fact_eq("catalog.schema_errors", "0")),
        "孤儿 cell 已按判定记录停用（`catalog.orphan_cells` 为 0），原孤儿 cell 仍在目录里、作为停用条目保留，父 sheet 由判定记录补登（`catalog.deprecated_entries` 为 44）": P(
            fact_eq("catalog.orphan_cells", "0"), fact_eq("catalog.deprecated_entries", "44"),
            claim("sheet_verdicts 里 kind=orphan 的 cell 全部仍在目录、已停用、父 sheet 已补登", _orphan_verdicts_released)),
        "生成器写出前跑 catalog_release 门禁（`generator.runs_release_gates` 为 是），加载期 release 互校已在生产目录生效（`report.has_release` 为 是）": P(
            fact_eq("generator.runs_release_gates", "是"), calls(_GEN_REL, "run_write", "_build_candidate"),
            calls(_BUILD_REL, "build_release", "run_release_gates"), fact_eq("report.has_release", "是"),
            claim("过渡期旧报告登记已删除（LEGACY_REPORT_WITHOUT_RELEASE 为 None）", lambda: ci.LEGACY_REPORT_WITHOUT_RELEASE is None),
            has_tests(_T + "test_catalog_index_fail_closed.py", "test_production_report_release_or_registered_legacy")),
        "本子节表格以外的数字都写明复算键，守卫逐个比对现算值": P(
            has_tests(_STATUS_GUARD_REL, "test_landed_numbers_bound_to_fact_keys")),
        "目录版本号": F("catalog.registry_version"),
        "目录 sheet 条目数": F("catalog.sheets"),
        "目录 cell 条目数": F("catalog.cells"),
        "父 sheet 在目录内的 cell": F("catalog.cells_with_parent"),
        "孤儿 cell（父 sheet 不在目录）": F("catalog.orphan_cells"),
        "孤儿 cell 所属 sheet 编码": F("catalog.orphan_parent_sheet_codes"),
        "停用（deprecated）条目数": F("catalog.deprecated_entries"),
        "条目所属域": F("catalog.domains"),
        "父级编码覆盖的循环": F("catalog.parent_cycles"),
        "cell 自带 formula_ref 能解析回本身的条目": F("catalog.formula_ref_roundtrip_ok"),
        "按现行契约 `catalog_contract.build_schema()` 校验目录的错误数": F("catalog.schema_errors"),
        "报告是否带 release 段": F("report.has_release"),
        "历史快照份数": F("snapshots.count"),
        "仍在仓库的分片文件": F("shards.files"),
        "生成器命令行参数": F("generator.cli_flags"),
        "生成器写出前是否跑发布门禁": F("generator.runs_release_gates"),
        "生产代码中导入发布门禁模块的文件数": F("catalog_release.production_importers"),
    },
    H_COMPONENTS: {
        "门禁清单：已经在跑的守卫见上表「测试」列": P(
            claim("组件表每行的「测试」文件都存在（后端测试文件有 test_ 函数，AST）", _component_tests_present)),
        "随本 spec 后续任务加入的门禁见下表——往返与保存校验（T10）、V2 对账（T22）、消费方绕过棘轮（T24）、显示名单一来源（T29、T30）": P(
            task_open("T10", "T22", "T24", "T29", "T30"),
            in_planned("T10", "T22", "T24", "T29", "T30")),
        "L1 目录加载与内存索引": CB(
            _A + "catalog.py", ("CatalogIndex", "get_catalog", "list_sheets", "list_cells"),
            _T + "test_catalog_index_fail_closed.py"),
        "加载期完整性：重复 addr_id fail-closed、LF 内容哈希口径、报告 release 段互校（缺 release 段即拒绝）": CB(
            _A + "catalog_integrity.py", ("duplicate_addr_id_problems", "content_sha256", "check_release_report"),
            _T + "test_catalog_index_fail_closed.py",
            has_tests(_T + "test_catalog_index_fail_closed.py", "test_duplicate_sheet_addr_id_fail_closed",
                      "test_content_sha256_is_lf_normalized",
                      "test_cross_check_no_release_segment_rejected_after_legacy_removed"),
            claim("旧格式报告的过渡期登记已删除（LEGACY_REPORT_WITHOUT_RELEASE 为 None）",
                  lambda: ci.LEGACY_REPORT_WITHOUT_RELEASE is None),
            fact_eq("report.has_release", "是")),
        "底稿域 canonical resolver（非底稿域委托 V1）": CB(
            _A + "resolver.py", ("full_resolve", "resolve_instance"), _T + "test_full_resolve.py",
            RESOLVER_DOC_OK, NON_WP_TO_V1),
        "L2 项目 overlay": CB(
            _A + "overlay.py", ("get_project_overlay", "ProjectOverlay"), _T + "test_overlay.py",
            calls(_RESOLVER_REL, "full_resolve", "get_project_overlay")),
        "L3 运行时条目": CB(
            _A + "runtime.py", ("get_runtime_entries",), _T + "test_runtime.py",
            calls(_RESOLVER_REL, "full_resolve", "get_runtime_entries")),
        "唯一精确身份判定（纯函数；尚未接入运行时解析）": CB(
            _A + "exact_identity.py", ("sheet_of", "cell_of", "name_owner"), _T + "test_exact_identity.py",
            claim("exact_identity 只导入标准库与本包 reasons / catalog_contract / catalog、不做文件或数据库读写（AST）",
                  _exact_identity_is_pure),
            claim("生产代码里导入 exact_identity 的恰为 catalog_release 与 catalog_names（运行时解析未接入，AST）",
                  _exact_identity_only_release_imports)),
        "目录契约单一来源，schema 由它生成": CB(
            _A + "catalog_contract.py", ("build_schema", "REGISTRY_VERSION_PATTERN", "FUNCTIONAL_TYPES"),
            _T + "test_catalog_schema_single_source.py",
            claim("schema 文件与 catalog_contract.schema_json() 逐字相同（LF）", _schema_file_is_generated)),
        "发布门禁模块（生成器写出与 `--check` 都调用）": CB(
            _A + "catalog_release.py", ("run_release_gates", "GateViolation"), _T + "test_catalog_release_gates.py",
            calls(_BUILD_REL, "build_release", "run_release_gates"), calls(_GEN_REL, "run_check", "run_release_gates"),
            fact_eq("catalog_release.production_importers", "2"),
            has_tests(_T + "test_catalog_release_gates.py", "test_real_catalog_release_gates_blocking_zero")),
        "孤儿与历史移除判定记录的 loader（发布候选构建读取）": CB(
            _A + "loaders/from_sheet_verdicts.py", ("load_sheet_verdicts",), _T + "test_sheet_verdicts.py",
            calls(_BUILD_REL, "build_release", "load_sheet_verdicts")),
        "平台底稿索引名 loader（名称规则模块调用）": CB(
            _A + "loaders/from_wp_account_mapping.py", ("load_wp_account_mapping_aliases",), _T + "test_name_system.py",
            calls(_NAMES_REL, "merge_platform_names", "load_wp_account_mapping_aliases")),
        "生成器名称规则：平台底稿名并入别名并逐条往返、同父一名多码记禁止别名、cell 写法按名称归属选模板名或编码": CB(
            _NAMES_REL, ("merge_platform_names", "apply_cell_names", "apply_cell_verdicts"), _T + "test_name_system.py",
            calls(_BUILD_REL, "build_release", "merge_platform_names", "apply_cell_names", "apply_cell_verdicts"),
            has_tests(_T + "test_name_system.py", "test_generator_name_rules_roundtrip_all_non_orphan_cells",
                      "test_generator_writes_forbidden_alias_policy_nine_groups")),
        "发布候选构建：叠加判定记录与名称规则、上一批次别名沿用、输入指纹与报告 release 段": CB(
            _BUILD_REL, ("build_release", "locate_previous", "inputs_fingerprint"), _T + "test_generator_release_flow.py",
            has_tests(_T + "test_generator_release_flow.py", "test_release_section_is_consistent_with_artifacts")),
        "目录报告四组分组（blocking / acknowledged / deprecated / info，count 恒等于条目数）与标签源别名逐条处置（未处置即阻断）": CB(
            _A + "catalog_report_buckets.py", ("build_buckets", "bucket_problems"), _T + "test_catalog_report_buckets.py",
            calls(_BUILD_REL, "build_release", "build_buckets"), calls(_NAMES_REL, "apply_alias_policy", "sheet_of"),
            claim("已提交报告四组 count == len(items) 且 blocking 为 0", lambda: (lambda r: not __import__(
                "app.services.acnr.catalog_report_buckets", fromlist=["bucket_problems"]).bucket_problems(r)
                and r["blocking"]["count"] == 0)(json.loads(_read(_REPO / "backend/data/acnr/catalog_report.json")))),
            has_tests(_T + "test_catalog_report_buckets.py", "test_every_key_and_conflict_disposed_per_design",
                      "test_forbidden_conflict_disposition_removed_blocked", "test_ack_expired_blocked")),
        "目录生成器（唯一写出方：门禁通过才写、内容不变不写、`--check` 结构化比对）": CB(
            _GEN_REL, ("generate_catalog", "run_write", "run_check", "main"), _T + "test_generator_release_flow.py",
            claim("生成器命令行有 --check（AST）", lambda: "--check" in _facts()["generator.cli_flags"].split("、")),
            has_tests(_T + "test_generator_release_flow.py", "test_second_write_is_idempotent",
                      "test_gate_violation_writes_nothing_and_names_addr_id", "test_alias_added_only_in_catalog_is_drift"),
            has_tests(_T + "test_only_generator_writes_catalog.py", "test_only_generator_writes_catalog"),
            claim("目录写出方现算恰为生成器（AST 污点分析）", lambda: __import__(
                "tests.acnr.test_only_generator_writes_catalog", fromlist=["catalog_writers"]
            ).catalog_writers() == {"scripts/acnr/generate_catalog.py"})),
        "写 stale 端点项目鉴权（`/api/linkage-bus/impact` 等）": CB(
            _LINKAGE_REL, ("stale_impact", "stale_impact_by_addr"), _T + "test_stale_write_endpoint_authz.py",
            claim("stale_impact / stale_impact_by_addr 调用项目级鉴权（AST）", _claim_stale_authz),
            claim("stale_impact 的路由是 POST /api/linkage-bus/impact（AST）", _stale_impact_route)),
        "前端 ACNR SDK，按项目订阅失效": CF(
            "audit-platform/frontend/src/services/acnr/useAcnr.ts", "useAcnr",
            "audit-platform/frontend/src/services/acnr/tests/useAcnr_project_subscription.spec.ts",
            task_done("T28"), exists(_FE_GUARD_REL)),
        "前端当前项目上下文": CF(
            "audit-platform/frontend/src/composables/useCurrentProjectId.ts", "useCurrentProjectId",
            "audit-platform/frontend/src/composables/__tests__/useCurrentProjectId.spec.ts", exists(_FE_GUARD_REL)),
    },
    H_PLANNED: {
        "exact_identity 接入全部使用者、删除 catalog 子串启发式、停用条目行为、保存校验与往返": L("T10"),
        "高级查询 acnr_targets 跨模块单元格取值、acnr_results 结果块、422 / 503 / YEAR_REQUIRED、前端结果区与下钻": L("T11、T12、T13、T14、T15、T16"),
        "版本锁持久化（迁移、lock_project_registry、effective_catalog）与按库引用的快照清理": L("T17、T18、T19"),
        "异步追溯拿到规范 addr_id": L("T20"),
        "V2 依赖图节点经 v2_canonical 规范化、stale 身份内核、双读对账产物、CCR 不可解析源处置": L("T21、T22"),
        "消费方台账与绕过棘轮、四个 ACNR CI 作业转绿": L("T24"),
        "版本锁 / acnr_targets / 拒绝计入 ACNR 指标": L("T26"),
        "统一显示名（后端 display.py 写入目录、前端改读 display_label）、歧义候选与外部命名空间中文提示": L("T29、T30、T31"),
        "INDEX 登记与提交边界核对": L("T33"),
    },
    H_VERSION: {
        "`registry_version` 为 **14 位 UTC 时间戳**（`%Y%m%d%H%M%S`，形态 `^\\d{14}$`，与 `catalog_contract.REGISTRY_VERSION_PATTERN` 一致；当前值见上表），由生成器在写出时赋值": P(
            claim("契约版本模式为 ^\\d{14}$ 且目录版本号符合", _claim_version_format),
            claim("generate_catalog 用 datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') 赋版本号（AST）",
                  _generator_assigns_utc_timestamp)),
        "不再使用 `YYYY.N.N`（本文下方示例中的 `2026.07.10` 已过时，见末尾勘误）": P(
            claim("目录与全部快照的版本号都是 14 位时间戳", _versions_are_timestamps),
            quote_at('registry_version: "2026.07.10"', "### 5.2 SheetCatalogEntry（L1 主条目）")),
    },
    H_PARALLEL: {
        "**ACNR（L1 + L2 + L3）**：底稿域（wp）由 `acnr/resolver.py` 解析": P(
            defines(_RESOLVER_REL, "full_resolve"),
            calls(_RESOLVER_REL, "full_resolve", "get_catalog", "get_project_overlay", "get_runtime_entries")),
        "L1 目录只覆盖底稿域（见上表 `catalog.domains`）": P(fact_eq("catalog.domains", "wp")),
        "**V1**（`services/address_registry`，动态寻址）：试算表 / 报表 / 附注 / 辅助余额等非底稿域的解析者，ACNR 对这些域委托 V1": P(
            exists("backend/app/services/address_registry.py"), NON_WP_TO_V1),
        "定位是「canonical resolver + legacy 委托」，不是全平台唯一入口": P(RESOLVER_DOC_OK),
        "平台里仍有直接调用 V1 或自行推导 sheet 身份的绕过点（基线待 T24 冻结）": P(V1_BYPASS, task_open("T24")),
        "**V2**（`routers/address_registry_v2.py` 与 stale 传播引擎）：依赖图与 stale 标记": P(
            exists(_V2_REL), defines(_STALE_REL, "StalePropagationEngine")),
        "节点身份仍由旧正则从路径猜编码，规范化见上表 T21": P(
            task_open("T21"), in_planned("T21"), absent(_A + "v2_canonical.py"),
            not_imports(_V2_REL, "exact_identity"), not_imports(_STALE_REL, "exact_identity")),
        "写 stale 的端点已加项目鉴权（见组件表）": P(
            claim("stale_impact / stale_impact_by_addr 调用项目级鉴权（AST）", _claim_stale_authz)),
        "**legacy 导航门面**（`wp_index_resolve` 等）：已转发 ACNR，`resolve_instance` 按 `wp_index.wp_code` 绑定项目已有底稿": P(
            claim("wp_index_resolve 导入并调用 acnr.resolver.full_resolve（AST）", _claim_legacy_forwarding),
            claim("resolve_instance 按 WpIndex.wp_code 查项目底稿（AST）", _resolve_instance_binds_wp_code)),
    },
    H_ERRATA: {
        "「文档体系地图」表「实施 spec」行的「❌ **尚未创建**（G8 阻塞项）」：实施 spec `acnr-foundation-defect-closure` 已创建，进度以其 tasks.md 为准": P(
            quote_at("❌ **尚未创建**（G8 阻塞项）", "### 文档体系地图", "**实施 spec**"), SPEC_TASKS),
        "上方「计划中（未落地）」所列任务均未完成": P(PLANNED_ROWS_OPEN),
        "「5.2 SheetCatalogEntry」「5.3 CellCatalogEntry」两节示例里的 `registry_version: \"2026.07.10\"`：版本号已改为 14 位 UTC 时间戳，`YYYY.N.N` 形态作废": P(
            quote_at('registry_version: "2026.07.10"', "### 5.2 SheetCatalogEntry（L1 主条目）"),
            quote_at('registry_version: "2026.07.10"', "### 5.3 CellCatalogEntry（L1 坐标子条目）"),
            claim("契约版本模式为 ^\\d{14}$ 且目录版本号符合", _claim_version_format)),
        "「执行摘要」表「M0（先落地）」行的「D 循环 catalog JSON 进库」等按 D 循环分期的陈述：L1 目录现已按 classification 骨架覆盖上表 `catalog.parent_cycles` 所列各循环（仍只覆盖底稿域）": P(
            quote_at("D 循环 catalog JSON 进库", "### 执行摘要（决策人 + 落地）", "**M0（先落地）**"),
            claim("目录父级编码覆盖多于一个循环", lambda: len(_facts()["catalog.parent_cycles"].split("、")) > 1),
            fact_eq("catalog.domains", "wp")),
        "「执行摘要」表「L1 首期」行的「经同一 `resolve` 出口」、「15.3 文档问题与矛盾」表 D-D10 行的「五域统一 resolve 出口」，以及 resolver 模块旧注释「四大消费库的唯一解析入口」（design §15.2 第 2 条）：应称「canonical resolver + legacy 委托」——底稿域由 ACNR 解析，其他域委托 V1，平台里仍有直接调用 V1 的绕过点（见上一子节）": P(
            quote_at("经同一 `resolve` 出口", "### 执行摘要（决策人 + 落地）", "**L1 首期**"),
            quote_at("五域统一 resolve 出口", "### 15.3 文档问题与矛盾（须修或迁入 spec 时解决）", "D-D10"),
            design_quote("四大消费库的唯一解析入口", "### 15.2"), RESOLVER_DOC_OK, NON_WP_TO_V1, V1_BYPASS),
        "resolver 模块注释已据此更正": P(RESOLVER_DOC_OK),
    },
}


# ─── 判定 ────────────────────────────────────────────────────────────────────


def _auto_checks(u: Unit) -> tuple[Check, ...]:
    """表格行自动绑定的判据（登记表里不必重复写）。"""
    if u.kind == "fact":
        key = _strip_code(u.cols[0])
        return (claim(f"复算键 {key} 是守卫认识的键", lambda: key in _facts()),)
    if u.kind == "planned":
        ids = tuple(_task_ids(u.cols[0]))
        return (claim("任务列至少有一个任务号", lambda: bool(ids)), task_open(*ids))
    if u.kind == "component":
        kind, module, symbols, test = (u.cols + ("", "", "", ""))[:4]
        module, test = _strip_code(module), _strip_code(test)
        if kind == "后端":
            syms = tuple(s for s in (_strip_code(x) for x in re.split(r"[、,，]", symbols)) if s)
            return (defines(module, *syms), claim(f"{test} 有 test_ 函数（AST）",
                                                  lambda: (_REPO / test).is_file() and _test_function_count(_REPO / test) > 0))
        return (exists(module), exists(test))
    return ()


def _registration_problems(units: list[Unit] | tuple[Unit, ...]) -> list[str]:
    """未登记 / 种类或其余列不符 / 同一子节重复（不含失效条目）。"""
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for u in units:
        if (u.subsection, u.text) in seen:
            problems.append(f"同一子节重复出现的陈述：[{u.subsection}] {u.text[:60]}")
            continue
        seen.add((u.subsection, u.text))
        stmt = _STATEMENTS.get(u.subsection, {}).get(u.text)
        if stmt is None:
            problems.append(f"未登记的陈述（先在 _STATEMENTS 登记复算判据）：[{u.subsection}] <{u.kind}> {u.text}")
        elif stmt.kind != u.kind or stmt.cols != u.cols:
            problems.append(f"登记的种类或其余列与文档不符：[{u.subsection}] {u.text[:40]}…"
                            f" 登记 {stmt.kind} {stmt.cols}，文档 {u.kind} {u.cols}")
    return problems


def _stale_entries(units: list[Unit] | tuple[Unit, ...]) -> list[str]:
    present = {(u.subsection, u.text) for u in units}
    return [f"[{sub}] {text[:70]}" for sub, entries in _STATEMENTS.items() for text in entries
            if (sub, text) not in present]


def _criteria_problems(units: list[Unit] | tuple[Unit, ...]) -> list[str]:
    problems: list[str] = []
    for u in units:
        stmt = _STATEMENTS.get(u.subsection, {}).get(u.text)
        if stmt is None:
            continue
        for label, fn in _auto_checks(u) + stmt.checks:
            try:
                ok = bool(fn())
            except Exception as exc:  # 判据出错按不成立处理（fail-closed），并写明原因
                ok, label = False, f"{label}（判据异常 {type(exc).__name__}: {exc}）"
            if not ok:
                problems.append(f"[{u.subsection}] {u.text[:50]}…：判据不成立——{label}")
    return problems


def test_status_section_structure_is_closed():
    units, problems = _parsed()
    assert len(units) >= 60, f"陈述单元过少（防空转）：{len(units)}"
    assert not problems, "现状节结构与登记不符：\n" + "\n".join(problems)


def test_every_statement_unit_is_registered():
    problems = _registration_problems(_parsed()[0])
    assert not problems, "现状节有未登记或与登记不符的陈述：\n" + "\n".join(problems)


def test_registry_has_no_stale_entries():
    stale = _stale_entries(_parsed()[0])
    assert not stale, "登记表里有节内已不存在的陈述（失效条目，须删除）：\n" + "\n".join(stale)


def test_registered_criteria_hold():
    problems = _criteria_problems(_parsed()[0])
    assert not problems, "现状节陈述的复算判据不成立：\n" + "\n".join(problems)


def test_every_registered_prose_has_explicit_criterion():
    empty = [f"[{sub}] {text[:60]}" for sub, entries in _STATEMENTS.items() for text, s in entries.items()
             if s.kind == "prose" and not s.checks]
    unknown = [f"[{sub}] {text[:60]}" for sub, entries in _STATEMENTS.items() for text, s in entries.items()
               if s.kind not in ("prose", "fact", "component", "planned") or sub not in (H_INTRO, *_SUBSECTIONS)]
    assert not empty and not unknown, f"正文陈述没有显式判据：{empty}；种类或子节不认识：{unknown}"


# ─── 判据自检（内存副本，不碰磁盘） ─────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("甲。乙；丙", ["甲", "乙", "丙"]),
    ("丙（丁；戊）「己。」`庚。`辛。", ["丙（丁；戊）「己。」`庚。`辛"]),
    ("**粗体**：一句; 二句", ["**粗体**：一句", "二句"]),
])
def test_sentence_splitter_self_check(text, expected):
    assert _sentences(text) == expected


def _synthetic_section() -> list[str]:
    """由登记表生成的「干净」现状节（每个登记单元恰出现一次；事实值用占位）。自检只依赖登记表，不依赖文档当前措辞。"""
    def prose(sub: str) -> list[str]:
        return [f"- {t}。" for t, s in _STATEMENTS.get(sub, {}).items() if s.kind == "prose"]
    lines = ["## 现状（2026-10-26）", ""] + prose(H_INTRO)
    for sub in _SUBSECTIONS:
        lines += ["", sub, ""]
        if sub in _TABLE_HEADERS:
            header = _TABLE_HEADERS[sub]
            lines += ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
            for t, s in _STATEMENTS.get(sub, {}).items():
                if s.kind != "prose":
                    lines.append("| " + " | ".join((t, "`x`", *s.cols) if s.kind == "fact" else (t, *s.cols)) + " |")
            lines.append("")
        lines += prose(sub)
    return lines


def _row_index(sec: list[str], kind_col: str) -> int:
    """合成节里第一条「第二列 = kind_col」的表格数据行（kind_col 为 后端 / 前端 时即组件行）。"""
    return next(i for i, ln in enumerate(sec) if ln.startswith("| ") and len(_cells(ln)) > 1 and _cells(ln)[1] == kind_col)


def _first_row_after(sec: list[str], heading: str) -> int:
    return next(i for i in range(sec.index(heading) + 3, len(sec)) if sec[i].startswith("| "))


def _set_cell(sec: list[str], i: int, col: int, value: str) -> list[str]:
    cells = _cells(sec[i])
    cells[col] = value
    return sec[:i] + ["| " + " | ".join(cells) + " |"] + sec[i + 1:]


def _insert_before(sec: list[str], heading: str, new: list[str]) -> list[str]:
    i = sec.index(heading)
    return sec[:i] + new + sec[i:]


def _insert_after(sec: list[str], heading: str, new: list[str]) -> list[str]:
    i = sec.index(heading)
    return sec[:i + 1] + new + sec[i + 1:]


def _replace_first_prose(sec: list[str], heading: str, new: str) -> list[str]:
    i = next(j for j in range(sec.index(heading) + 1, len(sec)) if sec[j].startswith("- "))
    return sec[:i] + [new] + sec[i + 1:]


_SELF_CHECK = {
    "R2-D5 并行关系子节加一句未登记的发布后规模": lambda s: _insert_before(
        s, H_ERRATA, ["- L1 目录规模：sheet 1225、有效 cell 449、孤儿 cell 0。", ""]),
    "R2-D6 组件描述追加统一显示名": lambda s: _set_cell(
        s, _row_index(s, "前端"), 0, _cells(s[_row_index(s, "前端")])[0] + "，统一从目录取显示名"),
    "R2-D7 改写一句已登记正文": lambda s: _replace_first_prose(s, H_PARALLEL, "- 节点身份已经由 exact_identity 规范化为 addr_id。"),
    "新增未登记子节": lambda s: _insert_before(s, H_VERSION, ["### 已完成", "", "- 版本锁已持久化。", ""]),
    "非表格子节加表格": lambda s: _insert_after(s, H_ERRATA, ["", "| 事项 | 状态 |", "|---|---|", "| 版本锁 | 已落地 |"]),
    "组件行改测试列": lambda s: _set_cell(s, _row_index(s, "后端"), 4, "`backend/tests/acnr/__init__.py`"),
    "事实行改复算键": lambda s: _set_cell(s, _first_row_after(s, H_FACTS), 2, "`catalog.cells_with_parent_x`"),
    "计划行改任务列": lambda s: _set_cell(s, _first_row_after(s, H_PLANNED), 1, "T02"),
    "表格行收尾竖线之后加文字": lambda s: s[:_row_index(s, "前端")] + [
        s[_row_index(s, "前端")] + " 统一从目录取显示名"] + s[_row_index(s, "前端") + 1:],
}


def test_registration_self_check_clean_synthetic():
    """对照组：由登记表生成的节没有任何问题（同时证明每个登记键都是切句器认的单个单元）。"""
    units, structure = _units_and_structure_problems(_synthetic_section())
    assert not structure and not _registration_problems(units) and not _stale_entries(units)
    assert len(units) == sum(len(v) for v in _STATEMENTS.values())


@pytest.mark.parametrize("desc", sorted(_SELF_CHECK))
def test_registration_self_check(desc):
    units, structure = _units_and_structure_problems(_SELF_CHECK[desc](_synthetic_section()))
    assert structure or _registration_problems(units) or _stale_entries(units), f"{desc}：登记制守卫应报出问题"
