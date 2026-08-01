"""Wave 6 / Task 7.2 —— 契约守卫（Property 12：复用范式不新造 + 口径统一 + 只读兼容）.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/  (Requirements 7.3, 4.1 / Property 12)

以**源码静态检查**冻结三条不可回退的架构契约（get_diagnostics/Vite 查不出的架构漂移，
靠此守卫拦截）：

  * **G1 复用范式不新造**（Property 12 / R7.3）：Tier B `prefill.py` 只经
    `get_active_filter` 读 `tb_balance`（`TbBalance`），**不新造第 3 套四表库读取**——
    禁止裸 `is_deleted` 过滤、禁止直接 import 其它四表 ORM（TrialBalance/TbLedger/
    TbAuxBalance）自建查询绕开 K/M/N 既有 `_build_adjudication_prefill` 范式。
  * **G2 评估器口径统一**（R4.1）：`wp_formula_eval_service` 的 `_resolve_tb`/
    `_resolve_sum_tb` 必经 `get_active_filter`，**不得**裸 `is_deleted`（消除面板求值值
    与 Tier B 预填值漂移）。
  * **G3 四表库只读守卫兼容**（Property 12）：Tier A 保存端仍拒绝把不受支持四表库函数
    （AUX/PREV/序时账）当可编辑公式（`find_unsupported_formula_functions` 存在且检出），
    即「读四表库写底稿允许、把四表库当 auto_calc 可编辑目标仍拒」。

纯文本/AST 静态检查，不触库、不依赖 conftest DB fixture。
"""
from __future__ import annotations

import ast
from pathlib import Path

# backend/tests/d_cycle_extraction/test_contract_guards.py → parents[2] = backend
_BACKEND = Path(__file__).resolve().parents[2]
_PREFILL = _BACKEND / "app" / "services" / "d_cycle_extraction" / "prefill.py"
_EVAL = _BACKEND / "app" / "services" / "wp_formula_eval_service.py"
# P0-1/P0-2 增量（本 spec）契约守卫涉及的模块
_WP_FORMULA_ROUTER = _BACKEND / "app" / "routers" / "wp_formula.py"
_D6_RENDER = (
    _BACKEND / "app" / "routers" / "wp_render_strategies" / "_d6_contract_assets.py"
)

# 其它三张四表库 ORM 名（Tier B 只应经 TbBalance；出现这些=新造第 3 套读取）
_OTHER_FOUR_TABLE_ORMS = ("TrialBalance", "TbLedger", "TbAuxBalance")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _string_literals(tree: ast.AST) -> list[str]:
    """收集模块内所有字符串字面量（用于检出裸 'is_deleted' 属性访问不便时的兜底）。"""
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append(node.value)
    return out


def _attribute_names(tree: ast.AST) -> set[str]:
    """收集所有 `x.attr` 的 attr 名（检出 `.is_deleted` 属性访问）。"""
    return {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }


def _imported_names(tree: ast.AST) -> set[str]:
    """收集 import / from-import 引入的名字。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
    return names


# ---------------------------------------------------------------------------
# G1: Tier B prefill 复用范式不新造第 3 套四表库读取
# ---------------------------------------------------------------------------


def test_g1_prefill_uses_active_filter_not_naked_is_deleted():
    """prefill.py 必用 get_active_filter，禁止裸 `.is_deleted` 过滤（Property 12 / R7.3）。"""
    src = _read(_PREFILL)
    tree = ast.parse(src)
    imported = _imported_names(tree)
    assert "get_active_filter" in imported, (
        "prefill.py 必须 import get_active_filter（复用 K/M/N 数据集版本口径）"
    )
    # 源码中必确实调用 get_active_filter
    assert "get_active_filter(" in src
    # 禁止裸 is_deleted 过滤（既不出现属性访问也不出现字面量列名）
    assert "is_deleted" not in _attribute_names(tree), (
        "prefill.py 禁止裸 `.is_deleted` 过滤（须经 get_active_filter，避免读 superseded/staged）"
    )
    assert "is_deleted" not in _string_literals(tree)


def test_g1_prefill_reads_only_tbbalance_no_third_reader():
    """prefill.py 只经 TbBalance 读四表库，不 import 其它三张四表 ORM 自建查询（Property 12）。"""
    tree = ast.parse(_read(_PREFILL))
    imported = _imported_names(tree)
    assert "TbBalance" in imported, "Tier B 预填应经 tb_balance（TbBalance）"
    for orm in _OTHER_FOUR_TABLE_ORMS:
        assert orm not in imported, (
            f"prefill.py 不得 import {orm} 自建第 3 套四表库读取（违反收敛铁律 / Property 12）；"
            "复杂归集（序时账/辅助余额）归 Tier B render 既有链路或前端一键取数，非本模块"
        )


def test_g1_prefill_no_direct_sqlmodel_session_bypass():
    """prefill.py 只用传入 ctx.db，不自建 engine/sessionmaker 绕过（收敛）。"""
    src = _read(_PREFILL)
    for banned in ("create_async_engine", "async_sessionmaker", "sessionmaker("):
        assert banned not in src, f"prefill.py 不得自建 {banned}（须用 ctx.db）"


# ---------------------------------------------------------------------------
# G2: 评估器口径统一（active_filter，不裸 is_deleted）
# ---------------------------------------------------------------------------


def test_g2_evaluator_tb_resolvers_use_active_filter():
    """_resolve_tb / _resolve_sum_tb 必经 get_active_filter，不裸 is_deleted（R4.1）。"""
    src = _read(_EVAL)
    tree = ast.parse(src)
    imported = _imported_names(tree)
    assert "get_active_filter" in imported
    # 两个 resolver 函数体：从 AST 节点检查（排除注释/文档串里对 is_deleted 的说明性提及）
    func_nodes: dict[str, ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name in (
            "_resolve_tb",
            "_resolve_sum_tb",
        ):
            func_nodes[node.name] = node
    assert set(func_nodes) == {"_resolve_tb", "_resolve_sum_tb"}, (
        "评估器应含 _resolve_tb 与 _resolve_sum_tb"
    )
    for name, node in func_nodes.items():
        # 函数体内确实调用 get_active_filter（AST Call → func 为 Name/Attribute 'get_active_filter'）
        calls = {
            (c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", ""))
            for c in ast.walk(node)
            if isinstance(c, ast.Call)
        }
        assert "get_active_filter" in calls, (
            f"{name} 必经 get_active_filter（与 Tier B 同口径，消除漂移 / R4.1）"
        )
        # 真实代码里不得有 `.is_deleted` 属性访问或列名字面量（注释/文档串不算，AST 不含注释）
        assert "is_deleted" not in _attribute_names(node), (
            f"{name} 不得裸 `.is_deleted` 属性过滤（须经 get_active_filter）"
        )
        assert "is_deleted" not in _string_literals(node), (
            f"{name} 不得裸 is_deleted 列名字面量（须经 get_active_filter）"
        )


# ---------------------------------------------------------------------------
# G3: 四表库只读守卫兼容（不支持函数不得当 auto_calc 可编辑目标）
# ---------------------------------------------------------------------------


def test_g3_unsupported_function_detector_present_and_effective():
    """find_unsupported_formula_functions 存在且检出 AUX/PREV/序时账（Property 12 / R4.2）。"""
    from app.services.wp_formula_eval_service import (
        find_unsupported_formula_functions,
    )

    # 受支持（Tier A 简单总额）→ 空
    assert find_unsupported_formula_functions("TB('1402','期末余额')") == []
    assert find_unsupported_formula_functions("SUM_TB('1122','审定数')") == []
    # 不受支持（复杂归集归 Tier B，不得当可编辑公式）→ 检出
    assert find_unsupported_formula_functions("AUX('1122','客户A','期末余额')")
    assert find_unsupported_formula_functions("PREV('1402','期末余额')")


# ---------------------------------------------------------------------------
# G4/G5: preset 运行时守卫（P1-5 —— 防预设文件锚点拼错静默丢弃 / 表达式漂移）
# ---------------------------------------------------------------------------
#
# `resolve_effective` 对未知锚点仅 logger.warning 后丢弃（不落库、不报错）→ 预设文件
# 锚点拼错会静默失效，CI 不失败。此守卫在**源数据层**冻结：每条 preset 锚点必 ∈
# anchor registry、表达式必只用受支持函数（TB/SUM_TB/WP），任一违反即 CI 失败。

import json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from app.services.d_cycle_extraction.anchor_registry import is_known_anchor  # noqa: E402
from app.services.d_cycle_extraction.presets import _PRESETS_PATH  # noqa: E402
from app.services.wp_formula_eval_service import (  # noqa: E402
    find_unsupported_formula_functions,
)


def _iter_preset_entries():
    """遍历 d_cycle_extraction_presets.json 全部 (wp_code, entry)（跳过 _meta 元数据键）。"""
    raw = json.loads(_Path(_PRESETS_PATH).read_text(encoding="utf-8"))
    for wp_code, entries in raw.items():
        if wp_code.startswith("_"):
            continue
        assert isinstance(entries, list), f"{wp_code} 预设应为列表"
        for entry in entries:
            yield wp_code, entry


def test_g4_every_preset_anchor_is_known():
    """每条 preset 锚点必 ∈ is_known_anchor(wp_code, anchor)（防拼错静默丢弃 / P1-5）。"""
    checked = 0
    for wp_code, entry in _iter_preset_entries():
        anchor = str(entry.get("anchor") or "").strip()
        assert anchor, f"{wp_code} 预设条目缺 anchor：{entry}"
        assert is_known_anchor(wp_code, anchor), (
            f"preset 锚点未登记（会被 resolve_effective 静默丢弃）：wp_code={wp_code} "
            f"anchor={anchor}；须 ∈ d_cycle_anchor_registry.json 或修正拼写"
        )
        checked += 1
    assert checked > 0, "预设库为空？应至少覆盖 D1-D7 的 Tier A 标量"


def test_g5_every_preset_expression_uses_supported_functions_only():
    """每条 preset 表达式必只用受支持函数（TB/SUM_TB/WP），无 AUX/PREV/序时账（P1-5）。"""
    for wp_code, entry in _iter_preset_entries():
        expr = str(entry.get("expression") or "").strip()
        assert expr, f"{wp_code} 预设条目缺 expression：{entry}"
        unsupported = find_unsupported_formula_functions(expr)
        assert not unsupported, (
            f"preset 表达式含不受支持函数（Tier A 可编辑公式仅 TB/SUM_TB/WP）："
            f"wp_code={wp_code} expr={expr} 命中={unsupported}"
        )


# ---------------------------------------------------------------------------
# G6/G7/G8: P0-1/P0-2 增量契约守卫脚手架（本 spec：d-cycle-tier-a-writeback-detail-seed）
# ---------------------------------------------------------------------------
#
# 🔴 Wave 0 脚手架任务（Task 1.2）：**先建骨架**，随后各波落地后转绿——
#   * G6 ← Wave 1（Task 2.1）：保存跳过 parsed_data + 不做 DB 写回 + 返回 evaluated_value。
#   * G8 ← Wave 2（Task 3.1）GET value + Wave 3/4（Task 4.1/4.2）render seed 同经 get_active_filter。
#   * G7 ← Wave 5（Task 5.1）明细归集复用既有函数不新造第 3 套四表库读取。
#
# 🟢 P0-1/P0-2 业务逻辑（Wave1/2/3/5）已全部落地，G6/G7/G8a/G8b 全部转绿（已移除 xfail），
# 断言精确表达**最终契约**（design 决策1/决策4 + Property 1/9/13/4）。


def _func_node(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """从模块 AST 取指定名的（异步）函数定义节点。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _call_names(node: ast.AST) -> set[str]:
    """收集某 AST 子树内所有被调用的可调用名（Name.id 或 Attribute.attr）。"""
    out: set[str] = set()
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            fn = c.func
            out.add(fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", ""))
    return out


def _has_if_testing_call(func: ast.AST, callee_name: str) -> bool:
    """func 内是否存在以 `callee_name(...)` 为（部分）条件的 `if`（路由守卫）。"""
    for node in ast.walk(func):
        if isinstance(node, ast.If):
            for c in ast.walk(node.test):
                if isinstance(c, ast.Call):
                    fn = c.func
                    name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
                    if name == callee_name:
                        return True
    return False


# ---------------------------------------------------------------------------
# G6: D-cycle 锚点 auto_calc 保存跳过 parsed_data + 不做 DB 写回 + 返回 evaluated_value
# ---------------------------------------------------------------------------


def test_g6_dcycle_anchor_save_skips_parsed_data_and_no_db_writeback():
    """G6（决策1 / Property 1, 2, 13）：`save_formula` auto_calc 分支按 `is_known_anchor` 路由——

      * D-cycle 锚点（target_cell ∈ known_anchors(wp_code)）+ 主开关开 → **跳过**
        `write_cell_to_parsed_data`（parsed_data 该 cell 不被写，因专属组件读 checklist_responses）；
      * **不新增**任何 checklist_responses/DB 写回路径（决策1：保存不写库，render transient
        seed 是"编辑即生效"的权威）；
      * 仍在响应返回 `evaluated_value`（供前端即时本地显示）；
      * 普通网格 cell（∉ known_anchors）沿用 `write_cell_to_parsed_data`（Property 2 零回归）。

    Wave 1（Task 2.1）已落地：`save_formula` 经 `is_known_anchor` 路由 D-cycle 锚点，对锚点
    跳过 `write_cell_to_parsed_data`、不做 checklist_responses/DB 写回、仍返回 evaluated_value
    → 本守卫已转绿（移除 xfail）。G7/G8 仍 xfail（其对应 Wave 5 / Wave 2·3 未落地）。
    """
    src = _read(_WP_FORMULA_ROUTER)
    tree = ast.parse(src)
    save = _func_node(tree, "save_formula")
    assert save is not None, "wp_formula.py 应含 save_formula"

    # (a) 保存路径 import 并调用 is_known_anchor 以路由 D-cycle 锚点 vs 网格 cell
    assert "is_known_anchor" in _imported_names(tree), (
        "wp_formula.py 须 import is_known_anchor（路由 D-cycle 锚点保存行为）"
    )
    assert "is_known_anchor" in _call_names(save), (
        "save_formula 须调用 is_known_anchor 判别 D-cycle 锚点 vs 普通网格 cell"
    )

    # (b) write_cell_to_parsed_data 被 is_known_anchor 守卫（D-cycle 锚点跳过写 parsed_data，
    #     非锚点才写）——不再无条件调用
    assert "write_cell_to_parsed_data" in _call_names(save), (
        "save_formula 仍应对普通网格 cell 调 write_cell_to_parsed_data（零回归分支保留）"
    )
    assert _has_if_testing_call(save, "is_known_anchor"), (
        "write_cell_to_parsed_data 须被 `if is_known_anchor(...)` 守卫（D-cycle 锚点跳过 parsed_data 写入）"
    )

    # (c) 决策1：保存不做 checklist_responses/DB 写回（不得新增写库路径）
    dumped = ast.dump(save)
    for banned in ("ChecklistResponse", "checklist_responses", "write_checklist_anchor"):
        assert banned not in dumped, (
            f"save_formula 不得新增 {banned} 写回（决策1：保存不写库，render transient seed 才是权威）"
        )

    # (d) 仍返回 evaluated_value 供前端即时显示
    assert "evaluated_value" in dumped, "save_formula 须在响应返回 evaluated_value（前端即时显示）"


# ---------------------------------------------------------------------------
# G7: 明细归集复用既有函数不新造第 3 套四表库读取（P0-2 / Property 9）
# ---------------------------------------------------------------------------


def test_g7_detail_seed_reuses_existing_aggregation_no_third_reader():
    """G7（决策4 / Property 9 / R4.3, R4.4）：P0-2 明细表维度归集 render 自动 seed（试点 D6-2）
    **复用既有后端归集函数/resolver**，产出 `detail_prefill` 的模块**不得**直接 import 其它三张
    四表库 ORM（TrialBalance/TbLedger/TbAuxBalance）自建第 3 套读取——四表库读取归既有可复用
    聚合函数（必要时先从 HTTP handler 抽出的纯函数），render seed 只按名调用它。

    Wave 5（Task 5.1）已落地：D6 render 的 `_seed_d6_detail_prefill` 调既有可复用归集
    `aggregate_d6_detail_rows`（tb_aux_balance 1141 客户/合同维度，`detail_aggregation.py`
    用原端点逐字节相同的 `sa.text` SQL，不 import 四表库 ORM），transient seed `detail_prefill`。
    产出方 `_d6_contract_assets.py` 只按名调用归集函数、不 import 四表 ORM → 本守卫转绿（移除 xfail）。
    """
    # detail_prefill 可能落地于 render 策略、resolver 或新抽取的纯聚合模块——跨候选定位其产出方
    candidates = [
        _D6_RENDER,
        _BACKEND / "app" / "services" / "auto_data_resolvers" / "_d6_contract_assets.py",
        _BACKEND / "app" / "services" / "d_cycle_extraction" / "detail_prefill.py",
    ]
    producers = [p for p in candidates if p.exists() and "detail_prefill" in _read(p)]
    assert producers, (
        "P0-2 明细自动 seed 未落地：无模块产出 detail_prefill（Wave 5 / Task 5.1）"
    )
    for path in producers:
        imported = _imported_names(ast.parse(_read(path)))
        for orm in _OTHER_FOUR_TABLE_ORMS:  # TrialBalance / TbLedger / TbAuxBalance
            assert orm not in imported, (
                f"{path.name} 明细 seed 不得直接 import {orm} 自建第 3 套四表库读取"
                "（须复用既有归集 resolver/纯函数，按名调用 / Property 9 / R4.3, R4.4）"
            )


# ---------------------------------------------------------------------------
# G8: GET value 求值 · render seed 均同经 get_active_filter（Property 4）
# ---------------------------------------------------------------------------
#
# G8 拆两半（Task 3.1 只满足 GET-value 半，render seed 半留 Wave 3）：
#   * G8a（本 Wave / Task 3.1）：GET value 求值经共享评估器 → 转绿（un-xfail）。
#   * G8b（Wave 3 / Task 4.1）：render seed 求值经共享评估器 → 仍 xfail，待 Wave 3 转绿。


def test_g8a_get_value_evaluates_via_get_active_filter():
    """G8a（Property 4 / R2.1, R7.2）：GET Tier A value 求值经共享评估器
    `evaluate_wp_formula_expression`（其 `_resolve_tb`/`_resolve_sum_tb` 经 `get_active_filter`，
    已由 G2 锁定）→ 与 Tier B 预填同数据集版本口径，消除面板求值值漂移。

    `_build_extraction_block` 逐条 Tier A 求值填 `value` 委托给助手 `_evaluate_tier_a_value`
    （单条 fail-open）；故契约为：`_build_extraction_block` 调用 `_evaluate_tier_a_value`，
    且 `_evaluate_tier_a_value` 经 `evaluate_wp_formula_expression` 求值。

    Wave 2（Task 3.1）已落地 → 本守卫转绿（un-xfail）。
    """
    tree = ast.parse(_read(_WP_FORMULA_ROUTER))
    block = _func_node(tree, "_build_extraction_block")
    assert block is not None, "wp_formula.py 应含 _build_extraction_block"
    # _build_extraction_block 逐条 Tier A 求值（委托助手，避免 N+1 内联/便于 fail-open）
    assert "_evaluate_tier_a_value" in _call_names(block), (
        "_build_extraction_block 须对每条 Tier A binding 求值填 value"
        "（委托 _evaluate_tier_a_value / R2.1）"
    )
    evaluator = _func_node(tree, "_evaluate_tier_a_value")
    assert evaluator is not None, (
        "wp_formula.py 应含 _evaluate_tier_a_value（Tier A GET 求值助手）"
    )
    assert "evaluate_wp_formula_expression" in _call_names(evaluator), (
        "_evaluate_tier_a_value 须经 evaluate_wp_formula_expression 求值"
        "（其内部走 get_active_filter，G2 已锁口径，与 Tier B/保存同数据集版本 / Property 4）"
    )


def test_g8b_render_seed_evaluates_via_get_active_filter():
    """G8b（Property 4 / R1.5, R3.1）：render seed 求值经共享评估器 `evaluate_wp_formula_expression`
    → 与 GET value/保存同经 get_active_filter，消除 render 漂移。

      * render seed：D6 render 用 `resolve_effective` 取有效 Tier A 公式 + `evaluate_wp_formula_expression`
        transient seed TB 核对行。

    Wave 3（Task 4.1）已落地：D6 render 的 `_seed_tier_a_reconciliation` 用 `resolve_effective`
    取有效 Tier A 公式 + `evaluate_wp_formula_expression`（经 get_active_filter）求值 transient seed
    → 本守卫转绿（移除 xfail）。
    """
    # render seed：D6 render 须用 resolve_effective 取有效 Tier A 公式 + 同一评估器求值
    d6_src = _read(_D6_RENDER)
    assert "resolve_effective" in d6_src, (
        "D6 render 须用 resolve_effective 取有效 Tier A 公式（读时收敛，主机制 / R3.1）"
    )
    assert "evaluate_wp_formula_expression" in d6_src, (
        "D6 render 须经 evaluate_wp_formula_expression 求值 transient seed"
        "（与 GET value/保存同经 get_active_filter / Property 4）"
    )
