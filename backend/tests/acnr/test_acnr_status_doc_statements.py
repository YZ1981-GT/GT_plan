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
    _component_tests_present, _exact_identity_is_pure, _exact_identity_only_release_imports, _production_importers_of,
    _full_resolve_step1_uses_exact_identity,
    _generator_assigns_utc_timestamp, _orphan_verdicts_released, _parsed, _resolve_instance_binds_wp_code,
    _schema_file_is_generated, _sentences, _stale_impact_route, _task_ids, _units_and_structure_problems,
    _versions_are_timestamps, absent, calls, claim, defines, design_quote, exists, fact_eq, fact_ne, gc_runtime_rows, has_tests,
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


def CF(module: str, symbol: str | tuple[str, ...], test: str, *checks: Check) -> Stmt:
    names = (symbol,) if isinstance(symbol, str) else symbol
    return Stmt("component", checks, ("前端", f"`{module}`", "、".join(f"`{s}`" for s in names), f"`{test}`"))


def L(tasks: str) -> Stmt:
    return Stmt("planned", (), (tasks,))


_A = "backend/app/services/acnr/"
_T = "backend/tests/acnr/"
_BUILD_REL = _A + "catalog_build.py"
_NAMES_REL = _A + "catalog_names.py"
_CQ = "backend/app/services/custom_query/"


def _query_models_are_strict() -> bool:
    """QueryDSL（builder_dsl）与业务视图 QueryRequest（routers/custom_query）的基类是 StrictRequestModel，
    acnr_targets 的注解是 AcnrTargetList（AST，T14）。"""
    import ast as _ast

    def _ok(rel: str, cls_name: str) -> bool:
        tree = _ast.parse(_read(_REPO / rel))
        cls = next((n for n in tree.body if isinstance(n, _ast.ClassDef) and n.name == cls_name), None)
        if cls is None or [getattr(b, "id", None) for b in cls.bases] != ["StrictRequestModel"]:
            return False
        return any(isinstance(n, _ast.AnnAssign) and getattr(n.target, "id", None) == "acnr_targets"
                   and getattr(n.annotation, "id", None) == "AcnrTargetList" for n in cls.body)

    return _ok(_CQ + "builder_dsl.py", "QueryDSL") and _ok("backend/app/routers/custom_query.py", "QueryRequest")


_QB_REL = "backend/app/routers/query_builder.py"
_ORCH_REL = _CQ + "cross_sheet_trace_orchestrator.py"
_V2C_REL = _A + "v2_canonical.py"
_CCR_SRC_REL = _A + "ccr_sources.py"
_CCR_CHK_REL = "backend/scripts/acnr/check_ccr_resolve.py"
_RECON_REL = "backend/scripts/acnr/reconcile_v2_canonical.py"
_RECON_OUT = "backend/data/acnr/v2_canonical_reconcile.json"


def _ci_job_runs(job: str, command: str) -> bool:
    """governance-checks.yml 的 ``job`` 有一步恰好运行 ``command``，且该作业不 continue-on-error（YAML 解析，T22）。"""
    import yaml

    jobs = yaml.safe_load(_read(_REPO / ".github" / "workflows" / "governance-checks.yml")).get("jobs") or {}
    body = jobs.get(job) or {}
    return not body.get("continue-on-error") and any(
        (s or {}).get("run") == command for s in body.get("steps") or [])


_BYPASS_REL = "backend/scripts/check/acnr_bypass_scan.py"


def _coverage_is_thin_shell() -> bool:
    """check_acnr_consumer_coverage.py 只从 acnr_bypass_scan 导入 main，自身不定义函数 / 类（AST，T24）。"""
    import ast as _ast

    tree = _ast.parse(_read(_REPO / "backend/scripts/check/check_acnr_consumer_coverage.py"))
    imports = [(n.module, [a.name for a in n.names]) for n in _ast.walk(tree) if isinstance(n, _ast.ImportFrom)]
    defs = [n for n in _ast.walk(tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef))]
    return ("acnr_bypass_scan", ["main"]) in imports and not defs


def _ccr_checker_has_no_private_matching() -> bool:
    """CCR 检查器不再定义私有表名匹配（无 _find_sheet / OfflineCatalog / _resolve_3arg / _resolve_2arg，AST）。"""
    import ast as _ast

    names = {n.name for n in _ast.walk(_ast.parse(_read(_REPO / _CCR_CHK_REL)))
             if isinstance(n, (_ast.FunctionDef, _ast.ClassDef))}
    return not names & {"_find_sheet", "OfflineCatalog", "_resolve_3arg", "_resolve_2arg"}


def _imported_names(rel: str, module_tail: str) -> list[str]:
    """``rel`` 里 ``from …{module_tail} import …`` 导入的名字（排序，AST）。"""
    import ast as _ast

    return sorted(a.name for n in _ast.walk(_ast.parse(_read(_REPO / rel)))
                  if isinstance(n, _ast.ImportFrom) and (n.module or "").endswith(module_tail) for a in n.names)


def _acnr_targets_importers_ok() -> bool:
    """生产代码里导入 acnr_target_values 的恰为业务视图编排器与构建器路由（T15 接线，AST）。"""
    return sorted(_production_importers_of("acnr_target_values")) == [_QB_REL, _CQ + "query_orchestrator.py"]


def _fn_node(rel: str, name: str):
    import ast as _ast

    return next(n for n in _ast.walk(_ast.parse(_read(_REPO / rel)))
                if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == name)


def _first_call_line(node, name: str) -> int | None:
    import ast as _ast

    lines = [c.lineno for c in _ast.walk(node) if isinstance(c, _ast.Call)
             and (c.func.id if isinstance(c.func, _ast.Name) else getattr(c.func, "attr", "")) == name]
    return min(lines) if lines else None


def _builder_endpoints_scope_before_targets() -> bool:
    """构建器三端点：项目守卫（_builder_scope）的调用行先于 plan_builder_targets（取值只在守卫放行之后）。"""
    for fn in ("preview_query", "execute_query", "export_excel"):
        node = _fn_node(_QB_REL, fn)
        scope, plan = _first_call_line(node, "_builder_scope"), _first_call_line(node, "plan_builder_targets")
        if scope is None or plan is None or not scope < plan:
            return False
    return True


def _orchestrator_reads_values_after_cache() -> bool:
    """编排器 execute 里 read_acnr_target_values 在 get_or_compute 之后；QueryResult.to_payload 不含 acnr_results。"""
    import ast as _ast

    rel = _CQ + "query_orchestrator.py"
    node = _fn_node(rel, "execute")
    cache, read = _first_call_line(node, "get_or_compute"), _first_call_line(node, "read_acnr_target_values")
    to_payload = _fn_node(rel, "to_payload")
    keys = {k.value for n in _ast.walk(to_payload) if isinstance(n, _ast.Dict)
            for k in n.keys if isinstance(k, _ast.Constant)}
    return cache is not None and read is not None and cache < read and "acnr_results" not in keys


def _template_configs_are_checked() -> bool:
    """模板创建 / 更新请求模型的 config 注解里用的是 TemplateConfig（保存时校验 acnr_targets，AST）。"""
    import ast as _ast

    tree = _ast.parse(_read(_REPO / "backend/app/routers/custom_query.py"))
    found = {}
    for cls in (n for n in tree.body if isinstance(n, _ast.ClassDef)):
        for n in cls.body:
            if isinstance(n, _ast.AnnAssign) and getattr(n.target, "id", None) == "config":
                found[cls.name] = {x.id for x in _ast.walk(n.annotation) if isinstance(x, _ast.Name)}
    return all("TemplateConfig" in found.get(c, set()) for c in ("TemplateCreateRequest", "TemplateUpdateRequest"))


def _locate_gate_ok() -> bool:
    """底稿短链定位端点：路由 GET /api/acnr/workpapers/{wp_id}/locate，函数体调用 assert_project_permission(…, "readonly")（AST）。"""
    import ast as _ast

    rel = "backend/app/routers/acnr.py"
    node = _fn_node(rel, "acnr_locate_workpaper")
    routes = [d for d in node.decorator_list if isinstance(d, _ast.Call) and getattr(d.func, "attr", "") == "get"
              and d.args and getattr(d.args[0], "value", None) == "/workpapers/{wp_id}/locate"]
    calls = [c for c in _ast.walk(node) if isinstance(c, _ast.Call)
             and getattr(c.func, "id", getattr(c.func, "attr", None)) == "assert_project_permission"
             and any(getattr(a, "value", None) == "readonly" for a in c.args)]
    return bool(routes) and bool(calls)


def _short_link_route_ok() -> bool:
    """前端底稿域路由表登记了短链 workpapers/:wpId → WorkpaperShortLink.vue（TS 源码里的路由对象）。"""
    src = _read(_REPO / "audit-platform/frontend/src/router/domains/workpapers.ts")
    return ("path: 'workpapers/:wpId'" in src and "name: 'WorkpaperShortLink'" in src
            and "@/views/WorkpaperShortLink.vue" in src)


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
        "消费方绕过棘轮与台账（后端绕过点：从 V1 地址服务导入寻址符号、加载 V2 身份文件或读 CCR 后自行拼 sheet 身份，按语法树现算、注释与文档字符串不计；与冻结基线逐条比对，新增或失效都阻断；消费方台账逐项登记状态与迁移目标，文件与符号须真实存在、状态为 migrated 的条目不得在基线里；前端两类绕过点由 `audit-platform/frontend/src/acnrBypassRatchet.spec.ts` 读同一基线核对；CI 作业 acnr-consumer-coverage 经薄壳运行它）": CB(
            _BYPASS_REL, ("run", "scan_backend", "ledger_problems", "main"), _T + "test_acnr_bypass_ratchet.py",
            calls(_BYPASS_REL, "run", "scan_backend", "ledger_problems"),
            exists("audit-platform/frontend/src/acnrBypassRatchet.spec.ts"), exists("backend/data/acnr/bypass_baseline.json"),
            claim("check_acnr_consumer_coverage.py 只导入 acnr_bypass_scan.main、不定义函数（AST）", _coverage_is_thin_shell),
            claim("CI 作业 acnr-consumer-coverage 运行 check_acnr_consumer_coverage.py --strict 且不 continue-on-error（YAML）",
                  lambda: _ci_job_runs("acnr-consumer-coverage",
                                       "python backend/scripts/check/check_acnr_consumer_coverage.py --strict")),
            has_tests(_T + "test_acnr_bypass_ratchet.py", "test_real_repo_strict_green_and_counts_recomputed",
                      "test_injected_v1_import_is_new_bypass", "test_comment_or_docstring_mention_is_not_a_bypass",
                      "test_removed_baseline_call_is_stale_entry",
                      "test_ledger_nonexistent_symbol_file_and_migrated_in_baseline")),
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
        "唯一精确身份判定（纯函数；目录写法解析、`full_resolve` 首步、发布门禁、生成器名称规则、单元格取值接线、跨 sheet 追溯编排器、V2 依赖图节点规范身份与 CCR 端点规范身份调用它）": CB(
            _A + "exact_identity.py", ("sheet_of", "cell_of", "name_owner"), _T + "test_exact_identity.py",
            claim("exact_identity 只导入标准库与本包 reasons / catalog_contract / catalog、不做文件或数据库读写（AST）",
                  _exact_identity_is_pure),
            claim("生产代码里导入 exact_identity 的恰为 catalog、catalog_names、catalog_release、ccr_sources、"
                  "v2_canonical、wp_cell_target 与跨 sheet 追溯编排器（AST）", _exact_identity_only_release_imports),
            calls(_ORCH_REL, "_identity", "cell_of"),
            calls(_V2C_REL, "canonical_node", "sheet_of", "cell_of"),
            claim("full_resolve 第 1 步经 step1_identity → catalog 结构化判定 → sheet_of，catalog 无子串启发式（AST）",
                  _full_resolve_step1_uses_exact_identity),
            calls(_A + "wp_cell_target.py", "sheet_key_for", "sheet_of"),
            calls(_A + "wp_cell_target.py", "read_formula_cell", "sheet_of"),
            calls(_CCR_SRC_REL, "_end", "sheet_of", "cell_of")),
        "底稿单元格共享读取函数（与 formula-hub 共用契约，非 ok 带中文原因与原因码、取不到不以零值代替；生产代码只有单元格取值接线导入它）": CB(
            "backend/app/services/wp_cell_reader.py", ("resolve_wp_cell", "WpCellRead"),
            "backend/tests/test_wp_cell_reader_contract.py",
            has_tests("backend/tests/test_wp_cell_reader.py", "test_every_non_ok_construction_sets_reason_code"),
            has_tests("backend/tests/test_wp_cell_reader_contract.py", "test_missing_reasons",
                      "test_database_error_propagates"),
            claim("生产代码里导入 wp_cell_reader 的恰为 acnr/wp_cell_target（AST）",
                  lambda: _production_importers_of("wp_cell_reader") == [_A + "wp_cell_target.py"])),
        "单元格取值接线（锁定项目按锁定目录判名但锁定来源暂为进程内登记、sheet 级底稿优先、借名与多义不读；导入它的生产模块是底稿公式三参 WP 的 A1 第三参（WPExecutor）、高级查询取值编排与跨 sheet 追溯编排器（追溯只用它按锁定状态取目录））": CB(
            _A + "wp_cell_target.py", ("read_entry_cell", "read_formula_cell", "effective_catalog", "sheet_key_for"),
            _T + "test_wp_cell_target.py",
            calls(_A + "wp_cell_target.py", "read_entry_cell", "resolve_wp_cell", "bind_wp_code", "sheet_key_for"),
            calls(_A + "wp_cell_target.py", "effective_catalog", "load_versioned_catalog"),
            calls(_A + "wp_cell_target.py", "_locked_version", "get_project_registry_version"),
            not_imports(_A + "wp_cell_target.py", "project_registry_lock"), task_open("T17", "T18"),
            has_tests(_T + "test_wp_cell_target.py", "test_locked_project_judges_identity_by_locked_catalog",
                      "test_sheet_level_paper_preferred_over_parent", "test_borrowed_and_ambiguous_names_block"),
            claim("生产代码里导入 wp_cell_target 的恰为 formula_engine、custom_query/acnr_target_values 与"
                  "跨 sheet 追溯编排器（AST）", lambda: sorted(_production_importers_of("wp_cell_target")) == [
                      "backend/app/services/custom_query/acnr_target_values.py", _ORCH_REL,
                      "backend/app/services/formula_engine.py"]),
            claim("跨 sheet 追溯编排器只从 wp_cell_target 导入 effective_catalog（AST）",
                  lambda: _imported_names(_ORCH_REL, "wp_cell_target") == ["effective_catalog"]),
            calls("backend/app/services/formula_engine.py", "read_sheet_cell", "effective_catalog", "read_formula_cell"),
            claim("生产代码里导入 acnr_target_values 的恰为编排器与构建器路由（AST）", _acnr_targets_importers_ok)),
        "高级查询 acnr_targets 解析与取值编排（逐项分类、任一不合格即整体拒绝并逐项给中文原因、首个解析不可用即返回服务不可用、整批时限；取值只经单元格取值接线；后端已接到业务视图 execute、模板执行与构建器预览 / 执行 / 导出，构建器先过与业务视图同一项目守卫，带单元格缺项目或年度补不出即拒绝，取值不进查询缓存）": CB(
            _CQ + "acnr_target_values.py",
            ("resolve_acnr_targets", "read_acnr_target_values", "classify_target", "plan_builder_targets",
             "complete_year"),
            _T + "test_acnr_targets_query_e2e.py",
            calls(_CQ + "acnr_target_values.py", "resolve_acnr_targets", "resolve_target", "classify_target"),
            calls(_CQ + "acnr_target_values.py", "read_acnr_target_values", "effective_catalog", "read_entry_cell"),
            calls(_CQ + "acnr_target_values.py", "plan_builder_targets", "complete_year", "resolve_acnr_targets"),
            not_calls(_CQ + "acnr_target_values.py", "resolve_wp_cell", "extract_custom_cells"),
            claim("生产代码里导入 acnr_target_values 的恰为编排器与构建器路由（AST）", _acnr_targets_importers_ok),
            calls(_CQ + "query_orchestrator.py", "_resolve_targets", "resolve_acnr_targets", "complete_year"),
            calls(_CQ + "query_orchestrator.py", "execute", "get_or_compute", "read_acnr_target_values"),
            claim("编排器在缓存读取（get_or_compute）之后才取单元格值、取值块不写进缓存 payload（AST）",
                  _orchestrator_reads_values_after_cache),
            claim("构建器预览 / 执行 / 导出三端点都先调 _builder_scope、再调 plan_builder_targets（AST 语句顺序）",
                  _builder_endpoints_scope_before_targets),
            calls(_QB_REL, "preview_query", "preview"), calls(_QB_REL, "export_excel", "acnr_sheet"),
            calls(_QB_REL, "execute_query", "with_acnr_results", "results"),
            has_tests(_T + "test_acnr_targets_single_reader.py", "test_each_rejection_code_is_422_and_reads_nothing",
                      "test_first_unavailable_stops_and_is_503", "test_whole_batch_deadline_is_503"),
            has_tests(_T + "test_acnr_target_values.py", "test_two_sheets_same_a1_each_read_their_own",
                      "test_missing_paper_is_wp_missing_not_zero"),
            has_tests(_T + "test_acnr_targets_three_way_pg.py", "test_formula_targets_and_stored_values_are_equal"),
            has_tests(_T + "test_acnr_targets_query_e2e.py", "test_three_entries_return_the_same_block",
                      "test_builder_year_is_filled_from_project_and_required_when_unknown",
                      "test_permission_matrix_is_the_same_for_both_entries",
                      "test_preview_resolves_without_reading_and_export_appends_sheet",
                      "test_requests_without_targets_are_unchanged", "test_values_are_read_fresh_even_on_cache_hit")),
        "高级查询顶层请求模型严格化（构建器与业务视图请求含未声明字段即拒收并点名该字段；acnr_targets 条数与单项长度校验；查询模板保存时同样校验 acnr_targets，执行时模板配置不合格即拒绝并点名非法项、不再报服务器错误）": CB(
            _CQ + "strict_model.py", ("StrictRequestModel", "AcnrTargetList", "TemplateConfig", "template_config_rejected"),
            "backend/tests/test_query_dsl_rejects_unknown_fields.py",
            claim("QueryDSL 与业务视图 QueryRequest 都继承 StrictRequestModel、acnr_targets 声明为 AcnrTargetList（AST）",
                  _query_models_are_strict),
            claim("模板创建 / 更新请求的 config 注解为 TemplateConfig（AST）", _template_configs_are_checked),
            calls("backend/app/routers/custom_query.py", "execute_template", "template_config_rejected"),
            has_tests(_T + "test_acnr_targets_query_e2e.py", "test_template_with_illegal_targets_is_422_not_500"),
            has_tests("backend/tests/test_query_dsl_rejects_unknown_fields.py",
                      "test_unknown_key_rejected_with_chinese_message", "test_builder_endpoints_reject_unknown_key",
                      "test_business_execute_rejects_unknown_key")),
        "跨 sheet 追溯节点规范身份（`/api/custom-query/cross-sheet-trace` 的每个节点按「父底稿 + sheet 名或编码 + A1」经唯一精确身份判定取规范 addr_id：sheet 已识别且 A1 合法即解析成功并标明是否为目录登记格，sheet 不识别、多义、命中禁止别名或 A1 非法给中文原因；同步追溯的生产构造都不经同步桥接取身份）": CB(
            _ORCH_REL, ("CrossSheetTraceOrchestrator", "TracedRefNode"), _T + "test_cross_sheet_trace_async_e2e.py",
            calls(_ORCH_REL, "_identity", "cell_of"), calls(_ORCH_REL, "trace", "effective_catalog", "_instance_route"),
            calls(_ORCH_REL, "_instance_route", "resolve_instance"), not_imports(_ORCH_REL, "addressing_service"),
            calls("backend/app/routers/custom_query.py", "cross_sheet_trace", "trace"),
            has_tests(_T + "test_cross_sheet_trace_async_e2e.py", "test_registered_unregistered_and_outside_nodes",
                      "test_unresolvable_root_has_chinese_reason"),
            has_tests(_T + "test_cross_sheet_identity_paths.py",
                      "test_every_production_construction_passes_resolve_identity_false",
                      "test_sync_bridge_only_referenced_inside_guarded_helper")),
        "V2 依赖图节点规范身份与 stale 起点身份（V2 `/resolve`、`/anchors`、`/stale-impact`、`/dependencies` 的节点与边端点追加 addr_id、sheet_addr_id、unresolved_code、unresolved_reason，经唯一精确身份判定取得，addr_id 与中文原因恰有其一，addr_id 为目录登记格时另带目录的统一显示名 display_label；`/resolve` 的包含匹配只作候选；stale 写入口与图中底稿键共用同一身份函数，身份算不出不写 stale 并返回原因）": CB(
            _V2C_REL, ("canonical_node", "canonical_uri", "canonical_addr", "annotate"),
            _T + "test_v2_canonical_reconcile.py",
            calls(_V2C_REL, "canonical_node", "sheet_of", "cell_of", "_catalog_display_label"),
            has_tests(_T + "test_display_contract.py", "test_v2_node_outputs_catalog_display_label"),
            calls(_V2_REL, "resolve_address", "annotate"), calls(_V2_REL, "list_anchors", "annotate"),
            calls(_V2_REL, "stale_impact", "annotate", "canonical_node", "non_workpaper_node"),
            calls(_V2_REL, "get_dependencies", "_end_identity", "canonical_node"),
            calls(_V2_REL, "_end_identity", "annotate", "non_workpaper_node"),
            calls(_STALE_REL, "_identity_of", "canonical_uri", "canonical_addr"),
            calls(_STALE_REL, "_ensure_identity_index", "_identity_of"),
            calls(_STALE_REL, "_start_keys", "_identity_of", "_ensure_identity_index"),
            calls(_STALE_REL, "on_change", "_start_keys", "_unresolved_response"),
            calls(_STALE_REL, "preview_impact", "_start_keys", "_unresolved_response"),
            not_imports(_STALE_REL, "linkage_graph_builder"),
            not_calls(_STALE_REL, "_normalize_wp_uri_to_addr_id"),
            has_tests(_T + "test_v2_canonical_reconcile.py",
                      "test_canonical_node_classes_have_exactly_one_and_chinese_reason",
                      "test_every_graph_wp_key_classified_with_reason", "test_anchors_nodes",
                      "test_endpoint_addr_ids_round_trip_non_vacuous", "test_stale_impact_and_dependencies_nodes",
                      "test_resolve_contains_is_candidate_not_matched", "test_collision_sample_starts_only_from_itself",
                      "test_real_collision_groups_start_only_from_same_sheet",
                      "test_multi_writing_same_identity_merged",
                      "test_contains_only_input_not_written_and_returns_reason",
                      "test_editor_save_inputs_new_rule_covers_old_correct_hits",
                      "test_write_path_does_not_use_regex_normalizer")),
        "CCR 端点规范身份与 CI 检查（`cross_wp_references.json` 的源与底稿目标经唯一精确身份判定取身份，检查器无私有匹配、只依赖标准库；不可解析的源须在豁免清单逐条登记，清单外或已失效的豁免即阻断；生成器按新目录把不可解析源写进报告问题清单，供豁免门禁核实；解析到停用条目的引用单列）": CB(
            _CCR_SRC_REL, ("source_end", "target_ends", "unresolved_source_ids", "is_deprecated"),
            _T + "test_ccr_resolve.py",
            calls(_CCR_SRC_REL, "_end", "sheet_of", "cell_of"),
            calls(_CCR_SRC_REL, "unresolved_source_ids", "source_end"),
            calls(_CCR_CHK_REL, "run", "source_end", "target_ends", "is_deprecated", "acknowledged_ccr_ids"),
            calls(_BUILD_REL, "_ccr_unresolved", "unresolved_source_ids"),
            calls(_BUILD_REL, "build_release", "_ccr_unresolved"),
            claim("CCR 检查器不定义私有表名匹配（AST）", _ccr_checker_has_no_private_matching),
            claim("CI 作业 acnr-ccr-resolve-blocking 运行 check_ccr_resolve.py --blocking 且不 continue-on-error（YAML）",
                  lambda: _ci_job_runs("acnr-ccr-resolve-blocking",
                                       "python backend/scripts/acnr/check_ccr_resolve.py --blocking")),
            has_tests(_T + "test_ccr_resolve.py", "test_blocking_green_and_counts_recomputed",
                      "test_acks_equal_unresolved_and_generator_report",
                      "test_each_ack_has_owner_expiry_reason_and_recomputed_evidence",
                      "test_rewriting_b60_to_workload_board_is_rejected", "test_stale_ack_and_outside_list_are_reported",
                      "test_blocking_fails_on_stale_ack_alone",
                      "test_deprecated_group_counts", "test_scripts_run_without_site_packages")),
        "V2 静态数据双读对账产物（L2 语义锚点、resolved refs、L3 依赖、CCR 四个文件的每个节点与边端点，经 V2 读端点同一身份函数按来源文件 × 分类计数，每类附中文原因与样本，不含时间戳；`--check` 比对，CI 运行）": CB(
            _RECON_REL, ("build", "main"), _T + "test_ccr_resolve.py",
            calls(_RECON_REL, "build", "canonical_node", "non_workpaper_node"), exists(_RECON_OUT),
            claim("CI 作业 acnr-v2-canonical-reconcile 运行 reconcile_v2_canonical.py --check 且不 continue-on-error（YAML）",
                  lambda: _ci_job_runs("acnr-v2-canonical-reconcile",
                                       "python backend/scripts/acnr/reconcile_v2_canonical.py --check")),
            has_tests(_T + "test_ccr_resolve.py", "test_reconcile_check_passes",
                      "test_reconcile_counts_self_consistent_and_reasons_chinese",
                      "test_reconcile_diff_names_changed_bucket")),
        "`full_resolve` 首步身份推导与停用字段（多义 / 禁止别名返回中文原因、所需上下文与候选；停用条目带替代地址）": CB(
            _A + "resolve_identity.py", ("step1_identity", "deprecation_fields"), _T + "test_catalog_roundtrip_real.py",
            calls(_RESOLVER_REL, "full_resolve", "step1_identity"),
            calls(_RESOLVER_REL, "_build_cell_resolve_result", "deprecation_fields"),
            has_tests(_T + "test_catalog_roundtrip_real.py", "test_step1_ambiguous_name_returns_reason_and_candidates",
                      "test_step1_forbidden_alias_returns_reason_and_candidates",
                      "test_every_live_cell_round_trips_through_full_resolve"),
            has_tests(_T + "test_catalog_release_integrity.py", "test_deprecated_cells_resolve_with_resolvable_replacement",
                      "test_entries_hide_deprecated_sheets_by_default")),
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
        "统一显示名（发布候选构建按同一规则写进目录：sheet 的 display_label 为「编码 名称」，名称取平台底稿名、其次手工维护的 sheet 显示名、再次去尾编码的模板名，名称等于编码时只显示编码，加科目简称前缀，同父级重名按编码自然序加序号（编码等于所属底稿编码的那张不参与序号），停用条目加「（已停用）」；cell 的 cell_label 为「A1 语义标签」、display_label 为「sheet 显示名 › cell_label」；`/api/acnr/resolve` 的命中与候选、acnr_targets、V2 节点输出同一字段，L3 运行时条目与非底稿域委托结果用同一函数现算）": CB(
            _A + "display.py", ("compose_sheet_labels", "cell_labels", "apply_display_labels"), _T + "test_display_contract.py",
            calls(_BUILD_REL, "build_release", "apply_display_labels", "load_name_sources"),
            calls(_RESOLVER_REL, "_build_runtime_resolve_result", "computed_display_label"),
            calls(_RESOLVER_REL, "_delegate_v1", "computed_display_label"), calls(_A + "resolve_identity.py", "computed_display_label", "cell_labels"),
            calls(_CQ + "acnr_target_values.py", "_display_label", "cell_labels"),
            has_tests(_T + "test_display_contract.py", "test_display_py_recomputes_every_published_label", "test_published_catalog_equals_fixture",
                      "test_resolve_endpoints_output_catalog_display_label", "test_acnr_targets_preview_outputs_catalog_display_label",
                      "test_candidates_use_catalog_display_label", "test_synthetic_groups", "test_rule_b_pairs_drop_redundant_sequence_numbers")),
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
        "ACNR 计数指标（`/api/acnr/metrics` 的 counters 段，键恒在：版本锁命中、锁定快照缺失、带项目而无会话无法核对版本锁，在 `full_resolve` 与单元格取值接线取目录处计数，锁定来源暂为进程内登记；acnr_targets 逐项拒绝按拒绝码计；停用条目引用被保存；stale 写入口起点身份算不出按原因码计；带原因码的两项遇未登记的码记 other）": CB(
            _A + "metrics.py", ("AcnrMetricsCollector", "get_acnr_metrics", "VERSION_LOCK_COUNTERS"), _T + "test_acnr_metrics.py",
            calls(_RESOLVER_REL, "full_resolve", "record_version_lock"), calls(_A + "wp_cell_target.py", "effective_catalog", "record_version_lock"),
            calls(_CQ + "acnr_target_values.py", "resolve_acnr_targets", "record_acnr_target_rejected"),
            calls(_A + "formula_validation.py", "_record_deprecated_ref_saved", "record_deprecated_ref_saved"),
            calls(_STALE_REL, "on_change", "record_stale_start_unresolved"),
            has_tests(_T + "test_acnr_metrics.py", "test_fresh_counters_have_all_keys_zero", "test_rejected_targets_counted_per_error_code",
                      "test_labelled_counters_bound_unknown_codes_to_other", "test_metrics_endpoint_returns_counters")),
        **gc_runtime_rows(CB),  # 运行时快照清理一行（RV13.1-01），登记在判据库：本文件已到 800 行上限
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
        "高级查询单元格取值的请求构造与拒绝提示（业务视图与构建器的请求体由同一模块构造：有项目且有单元格目标才发送单元格目标；构建器的项目与年度在限定当前项目或带单元格目标时发送、年度未知不发；拒绝、无权、解析不可用转成中文提示）": CF(
            "audit-platform/frontend/src/components/custom-query/queryPayloads.ts", ("buildBusinessPayload", "buildBuilderPayload", "queryErrorText"),
            "audit-platform/frontend/src/components/custom-query/__tests__/queryPayloads.contract.spec.ts", exists(_FE_GUARD_REL),
            exists("audit-platform/frontend/src/components/custom-query/AcnrTargetResults.vue"),
            has_tests(_T + "test_query_request_fields_fixture.py", "test_fixture_holds_for_backend_models")),
        "底稿短链定位端点（ACNR 跳转路由 `/workpapers/{wp_id}` 按底稿 id 查所属项目，先按所属项目做只读鉴权再区分回收站；不存在或传的是底稿索引 id 即未找到，回收站给中文原因）": CB(
            "backend/app/routers/acnr.py", ("acnr_locate_workpaper",), _T + "test_workpaper_locate_endpoint.py",
            claim("定位端点路由与只读项目鉴权（AST）", _locate_gate_ok),
            has_tests(_T + "test_workpaper_locate_endpoint.py", "test_non_member_is_403_without_project_id",
                      "test_wp_index_id_is_not_a_workpaper_id", "test_recycle_bin_is_410_with_chinese_reason")),
        "底稿短链页（`/workpapers/:wpId` 定位后替换到底稿编辑器、保留 sheet / cell；失败显示中文原因不跳转）与后端跳转路由形态契约": CF(
            "audit-platform/frontend/src/views/composables/workpaperShortLink.ts", ("resolveShortLink", "shortLinkQuery"),
            "audit-platform/frontend/src/views/__tests__/WorkpaperShortLink.spec.ts",
            claim("底稿域路由表登记短链 workpapers/:wpId", _short_link_route_ok),
            exists("audit-platform/frontend/src/router/__tests__/backendRouteShapes.contract.spec.ts"),
            has_tests(_T + "test_frontend_route_shapes_fixture.py", "test_fixture_matches_backend_sources")),
        "前端显示名只读目录（选址器、高级查询选字段、公式管理与公式编辑三棵树，公式选址器、地址库搜索、已选字段、取值结果区与索引 chip 都读目录的 display_label / cell_label，前端只按编码排序、父节点标题加科目简称；停用 cell 由同一谓词过滤）": CF("audit-platform/frontend/src/services/acnr/sheetDisplayName.ts", ("sortSheetsForGroup", "groupHeaderLabel", "wpCodeNaturalCompare"),
            "audit-platform/frontend/src/acnrDisplaySingleSource.spec.ts", exists(_FE_GUARD_REL), exists("audit-platform/frontend/src/services/acnr/cellListing.ts")),
    },
    H_PLANNED: {
        "版本锁持久化（迁移、lock_project_registry、effective_catalog 改读落库的锁）与按库引用的快照清理": L("T17、T18、T19"),
        "歧义候选与外部命名空间中文提示": L("T31"),
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
        "平台里仍有直接调用 V1 或自行推导 sheet 身份的绕过点，已冻结为基线（见组件表「消费方绕过棘轮与台账」）": P(
            V1_BYPASS, exists("backend/data/acnr/bypass_baseline.json"),
            has_tests(_T + "test_acnr_bypass_ratchet.py", "test_real_repo_strict_green_and_counts_recomputed")),
        "**V2**（`routers/address_registry_v2.py` 与 stale 传播引擎）：依赖图与 stale 标记": P(
            exists(_V2_REL), defines(_STALE_REL, "StalePropagationEngine")),
        "读端点的节点与 stale 写入口经 `acnr/v2_canonical.py` 取规范身份，四个静态文件的双读对账产物与 CCR 端点身份检查见组件表": P(
            exists(_V2C_REL), calls(_V2_REL, "resolve_address", "annotate"),
            calls(_V2_REL, "get_dependencies", "_end_identity", "canonical_node"),
            calls(_STALE_REL, "_start_keys", "_identity_of"),
            calls(_STALE_REL, "_identity_of", "canonical_uri", "canonical_addr"),
            not_imports(_STALE_REL, "linkage_graph_builder"),
            exists(_RECON_REL), exists(_RECON_OUT), exists(_CCR_SRC_REL),
            calls(_RECON_REL, "build", "canonical_node", "non_workpaper_node")),
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
