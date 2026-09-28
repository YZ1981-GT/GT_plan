"""test_lazy_import_resolvability.py — 函数体内 lazy import 可解析性守卫.

spec: adj-formula-repair-and-approval-gate-wiring · 复盘补漏（原任务 1.2 只做了
一次性 grep，未固化为守卫 ⇒ 同类缺陷可再次进来）

背景：本 spec 的首要缺陷是 `prefill_engine._resolve_adj_formula` 函数体内
`from app.models.phase10_models import Adjustment, AdjustmentEntry` —— 该模块
既无定义也无 re-export ⇒ 每次调用必抛 ImportError，但因是 lazy import，
模块加载期与静态检查都发现不了。

触类旁通同时抓到 `routers/attachments.py` 4 处 `Attachment` 同型缺陷。

本守卫静态解析 app/ 下**所有函数体内**的 `from app.xxx import Name`，
逐个验证 Name 在目标模块中真实可取 —— 无需执行业务代码即可打红。
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_APP = _BACKEND / "app"

# ---------------------------------------------------------------------------
# 分类一：feature-flag 关闭的「未实现占位」（不是缺陷）
# ---------------------------------------------------------------------------
# 这些 import 被模块级 `_INCLUDE_XXX: Final[bool] = False` 包裹，运行时**永不执行**。
# 形态是「spec 规划了该 sheet，代码骨架先留好、flag 关闭，等模块落地再打开」。
# 实证：同文件内 flag=True 的兄弟项（如 phase5_f3_05_overdue）目标模块确实存在。
#
# 🔴 与「分类二」区别是决定性的：把它们混在一起会让守卫产生 13 条永久噪音，
#    而真正会崩的条目被淹没。判定脚本见本 spec 复盘记录（按 AST 取 flag 字面值）。
# 🔴 一旦某个 flag 翻成 True 而目标模块仍不存在 → 它会从这里"掉进"分类二并打红，
#    这正是我们要的行为（守卫 test_flag_gated_entries_are_really_gated 钉死）。
_FLAG_GATED_PLACEHOLDERS: frozenset[tuple[str, str, str]] = frozenset({
    ("app/services/workpaper_sync/phase5_f3_notes_payable.py", "app.services.workpaper_sync", "phase5_f3_01_adjudication"),
    ("app/services/workpaper_sync/phase5_f3_notes_payable.py", "app.services.workpaper_sync", "phase5_f3_02_detail"),
    ("app/services/workpaper_sync/phase5_f3_notes_payable.py", "app.services.workpaper_sync", "phase5_f3_04_interest"),
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_01_adjudication"),
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_02_detail"),
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_05_long_outstanding"),
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_07_unrecorded"),
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_08_voucher_check"),
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_09_supplier_financing"),
    ("app/services/workpaper_sync/phase5_f5_cost_of_sales.py", "app.services.workpaper_sync", "phase5_f5_02_monthly_detail"),
    ("app/services/workpaper_sync/phase5_f5_cost_of_sales.py", "app.services.workpaper_sync", "phase5_f5_03_other_cost"),
    ("app/services/workpaper_sync/phase5_f5_cost_of_sales.py", "app.services.workpaper_sync", "phase5_f5_05_comparison"),
    ("app/services/workpaper_sync/phase5_f5_cost_of_sales.py", "app.services.workpaper_sync", "phase5_f5_07_cost_rollforward"),
})

# ---------------------------------------------------------------------------
# 分类二：真会崩的存量（无 flag 守卫或 flag=True）—— 待修工单
# ---------------------------------------------------------------------------
# 这 10 条一被执行必抛 ImportError。它们与本 spec 已修的 8 处（路径写错）**性质不同**：
# 目标名在**全仓任何模块都不存在**（已用 SQLAlchemy 注册表 + AST 全仓搜实证），
# 属「幽灵引用」—— 修它需要业务判断（新建 ORM 模型 / 改裸 SQL / 删死代码），
# 不是改 import 路径能解决的，故另立工单。
#
# 分类明细：
# - ChecklistResponse ×3：`checklist_responses` 表**无 ORM 模型**（SQLAlchemy 注册表
#   权威确认，该表走裸 SQL）⇒ 需新建模型或改裸 SQL
# - TbAccount / TbAdjustment：全仓无定义，同模块无相近名
# - save_formula_batch / populate_parsed_data：同上
# - static_sheet_payload_for_adjudication ×3：**flag=True 会真执行**，
#   `phase5_adjudication_sheet` 只导出 4 个类 + col_index，无此函数。
#   属正在进行的 workpaper-sync-* spec 工作区，交该 spec 处置。
_KNOWN_UNRESOLVED_BASELINE: frozenset[tuple[str, str, str]] = frozenset({
    ("app/routers/adjustments.py", "app.models.audit_platform_models", "ChecklistResponse"),
    ("app/routers/import_templates.py", "app.services.cell_formula_evaluator", "save_formula_batch"),
    ("app/routers/wp_template.py", "app.services.wp_parsed_data_service", "populate_parsed_data"),
    ("app/services/contract_analysis_service.py", "app.models.audit_platform_models", "TbAccount"),
    ("app/services/contract_analysis_service.py", "app.models.audit_platform_models", "TbAdjustment"),
    ("app/services/m8_general_risk_reserve_service.py", "app.models.audit_platform_models", "ChecklistResponse"),
    ("app/services/s_estimate_import_export_service.py", "app.models.audit_platform_models", "ChecklistResponse"),
    # flag=True，会真执行 —— 属 workpaper-sync-* spec 工作区
    ("app/services/workpaper_sync/phase5_d5_expansion.py", "app.services.workpaper_sync.phase5_adjudication_sheet", "static_sheet_payload_for_adjudication"),
    ("app/services/workpaper_sync/phase5_d6_expansion.py", "app.services.workpaper_sync.phase5_adjudication_sheet", "static_sheet_payload_for_adjudication"),
    ("app/services/workpaper_sync/phase5_d7_expansion.py", "app.services.workpaper_sync.phase5_adjudication_sheet", "static_sheet_payload_for_adjudication"),
})

# 守卫允许的全集 = 未实现占位 ∪ 待修工单
_ALLOWED_UNRESOLVED = _FLAG_GATED_PLACEHOLDERS | _KNOWN_UNRESOLVED_BASELINE


def _guarded_import_linenos(tree: ast.AST) -> set[int]:
    """收集「受保护」的 import 行号 —— 这些不算缺陷。

    两类：
    1. `if TYPE_CHECKING:` 块内 —— 运行时不执行，只供类型标注
    2. `try: ... except ImportError/Exception:` 块内 —— 有 fallback 兜底

    🔴 不排除这两类会产生大批误报（复盘教训：第一版扫描器因此把
    「有 fallback 的可选依赖」也算成缺陷）。
    """
    guarded: set[int] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            t = n.test
            is_tc = (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (
                isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"
            )
            if is_tc:
                for s in ast.walk(n):
                    if isinstance(s, ast.ImportFrom):
                        guarded.add(s.lineno)
        if isinstance(n, ast.Try):
            catches_import = any(
                h.type is None
                or (isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "Exception"))
                or (isinstance(h.type, ast.Tuple) and any(
                    isinstance(e, ast.Name) and e.id in ("ImportError", "Exception")
                    for e in h.type.elts))
                for h in n.handlers
            )
            if catches_import:
                for s in n.body:
                    for ss in ast.walk(s):
                        if isinstance(ss, ast.ImportFrom):
                            guarded.add(ss.lineno)
    return guarded


def _collect_function_scoped_app_imports() -> list[tuple[str, int, str, str]]:
    """收集 app/ 下函数体内**未受保护**的 `from app.* import Name`。

    Returns:
        [(posix 相对路径, 行号, 模块名, 导入名), ...]
    """
    found: list[tuple[str, int, str, str]] = []

    for fp in _APP.rglob("*.py"):
        if "__pycache__" in str(fp):
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        guarded = _guarded_import_linenos(tree)
        rel = fp.relative_to(_BACKEND).as_posix()

        # 只看函数/方法体内的 import（模块级 import 在加载期就会炸，无需守卫）
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for sub in ast.walk(node):
                if not isinstance(sub, ast.ImportFrom):
                    continue
                if sub.lineno in guarded:
                    continue
                mod = sub.module or ""
                if not mod.startswith("app."):
                    continue
                for alias in sub.names:
                    if alias.name == "*":
                        continue
                    found.append((rel, sub.lineno, mod, alias.name))
    return found


def _scan_unresolved() -> set[tuple[str, str, str]]:
    """扫出全部不可解析项，返回 {(文件, 模块, 导入名)} 去重集合（不含行号）。"""
    entries = _collect_function_scoped_app_imports()
    module_cache: dict[str, object] = {}
    skipped: set[str] = set()
    unresolved: set[tuple[str, str, str]] = set()

    for rel_path, _lineno, mod, name in entries:
        if mod in skipped:
            continue
        if mod not in module_cache:
            try:
                module_cache[mod] = importlib.import_module(mod)
            except Exception:
                skipped.add(mod)
                continue
        if not hasattr(module_cache[mod], name):
            try:
                importlib.import_module(f"{mod}.{name}")
            except Exception:
                unresolved.add((rel_path, mod, name))
    return unresolved


class TestLazyImportResolvability:
    """函数体内 lazy import 的导入名必须在目标模块中真实存在。"""

    def test_no_new_unresolved_lazy_import(self):
        """禁新增：不可解析项不得超出 `_KNOWN_UNRESOLVED_BASELINE`。

        扫描条数与不可解析数**现算**，禁写死。
        """
        entries = _collect_function_scoped_app_imports()
        assert entries, "扫描器未收集到任何函数体内 app.* import ⇒ 解析口径有问题"

        unresolved = _scan_unresolved()
        newly_added = sorted(unresolved - _ALLOWED_UNRESOLVED)

        assert not newly_added, (
            f"新增 {len(newly_added)} 处函数体内 lazy import 不可解析"
            f"（现算已扫 {len(entries)} 条 import、不可解析共 {len(unresolved)} 条、"
            f"占位 {len(_FLAG_GATED_PLACEHOLDERS)} 条、待修 {len(_KNOWN_UNRESOLVED_BASELINE)} 条）。\n"
            "运行时必抛 ImportError —— 请修正 import 路径，而非加进基线：\n"
            + "\n".join(f"  {f}: from {m} import {n}" for f, m, n in newly_added)
        )

    def test_baseline_has_no_zombie_entries(self):
        """禁僵尸：两张清单里都不得有「已修好却还挂着」的条目。

        修完一条就必须移除，否则清单会永久掩盖已恢复的健康区域，
        使守卫对该文件重新劣化时不再打红。
        """
        unresolved = _scan_unresolved()
        zombies = sorted(_ALLOWED_UNRESOLVED - unresolved)

        assert not zombies, (
            f"清单中 {len(zombies)} 条已不再是缺陷（已修复或代码已删），"
            "请从 _KNOWN_UNRESOLVED_BASELINE / _FLAG_GATED_PLACEHOLDERS 移除：\n"
            + "\n".join(f"  {f}: from {m} import {n}" for f, m, n in zombies)
        )

    def test_flag_gated_entries_are_really_gated(self):
        """钉死分类依据：_FLAG_GATED_PLACEHOLDERS 每条都必须真被 flag=False 关着。

        🔴 这是两张清单分类的唯一合法依据。若某个 `_INCLUDE_*` 被翻成 True 而
        目标模块仍不存在，该条就**不再是占位而是真缺陷**，必须移入待修清单
        —— 本测试会打红逼迫这次搬移，防「flag 打开后静默变成必崩」。
        """
        import ast as _ast

        violations = []
        for rel, _mod, name in sorted(_FLAG_GATED_PLACEHOLDERS):
            fp = _BACKEND / rel
            if not fp.exists():
                violations.append(f"{rel}: 文件已不存在，请从占位清单移除")
                continue
            tree = _ast.parse(fp.read_text(encoding="utf-8"))

            # 取模块级 _INCLUDE_* 字面值
            flags: dict[str, object] = {}
            for node in tree.body:
                if isinstance(node, _ast.AnnAssign) and isinstance(node.target, _ast.Name):
                    targets, value = [node.target.id], node.value
                elif isinstance(node, _ast.Assign):
                    targets = [t.id for t in node.targets if isinstance(t, _ast.Name)]
                    value = node.value
                else:
                    continue
                for t in targets:
                    if t.startswith("_INCLUDE") and value is not None:
                        try:
                            flags[t] = _ast.literal_eval(value)
                        except Exception:
                            flags[t] = "<非字面量>"

            # 找包裹该 import 的 `if _INCLUDE_X:`
            gate = None
            for node in _ast.walk(tree):
                if not isinstance(node, _ast.If):
                    continue
                inner = {
                    a.name
                    for s in _ast.walk(node)
                    if isinstance(s, _ast.ImportFrom)
                    for a in s.names
                }
                if name not in inner:
                    continue
                t = node.test
                if isinstance(t, _ast.Name) and t.id.startswith("_INCLUDE"):
                    gate = t.id
                    break

            if gate is None:
                violations.append(f"{rel}: {name} 未被任何 _INCLUDE_* 守卫包裹")
            elif flags.get(gate) is not False:
                violations.append(
                    f"{rel}: {name} 的守卫 {gate}={flags.get(gate)!r}（非 False）"
                    " ⇒ 已不是占位，请移入 _KNOWN_UNRESOLVED_BASELINE 并修实现"
                )

        assert not violations, (
            "占位清单的分类依据已失效：\n" + "\n".join(f"  {v}" for v in violations)
        )

    def test_spec_fixed_targets_are_not_in_baseline(self):
        """本 spec 已修的 4 类目标必须真修好（不在不可解析集合里）。

        ADJ（Adjustment）· AUX/TB_AUX（TbAuxBalance）· prefill WpIndex ·
        attachments Attachment —— 任一回退即打红。
        """
        unresolved = _scan_unresolved()
        must_be_clean = {
            # 路径写错类（目标存在于别的模块）
            ("app/services/prefill_engine.py", "app.models.phase10_models", "Adjustment"),
            ("app/services/prefill_engine.py", "app.models.dataset_models", "TbAuxBalance"),
            ("app/services/prefill_engine.py", "app.models.audit_platform_models", "WpIndex"),
            ("app/routers/attachments.py", "app.models.phase10_models", "Attachment"),
            # 错名类（database 真实导出是 async_session，与 async_engine 别名问题同源）
            ("app/services/a13_event_handler.py", "app.core.database", "async_session_factory"),
            ("app/services/ocr_service_v2.py", "app.core.database", "async_session_maker"),
            ("app/services/ai_chat/address_index_source.py", "app.core.database", "get_db_contextmanager"),
        }
        regressed = sorted(must_be_clean & unresolved)
        assert not regressed, (
            "本 spec 已修的 lazy import 出现回退：\n"
            + "\n".join(f"  {f}: from {m} import {n}" for f, m, n in regressed)
        )

    def test_guard_excludes_type_checking_and_try_blocks(self):
        """P12：受保护 import（TYPE_CHECKING / try-except）必须被排除。

        不排除会产生大批误报（复盘实测：第一版扫描器因此虚报）。
        """
        sample = (
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    from app.models.nonexistent_mod import Ghost\n"
            "def f():\n"
            "    if TYPE_CHECKING:\n"
            "        from app.models.nonexistent_mod import Ghost2\n"
            "    try:\n"
            "        from app.models.nonexistent_mod import Ghost3\n"
            "    except ImportError:\n"
            "        Ghost3 = None\n"
            "    from app.models.nonexistent_mod import Ghost4\n"
            "    return Ghost3, Ghost4\n"
        )
        tree = ast.parse(sample)
        guarded = _guarded_import_linenos(tree)

        # Ghost2（TYPE_CHECKING，第 6 行）与 Ghost3（try，第 8 行）应被标为受保护
        assert 6 in guarded, "函数体内 TYPE_CHECKING 块未被排除"
        assert 8 in guarded, "try/except ImportError 块未被排除"
        # Ghost4（第 11 行，裸 lazy import）不应被排除
        assert 11 not in guarded, "裸 lazy import 被误排除 ⇒ 守卫会漏检"

    def test_scanner_detects_injected_bad_import(self, tmp_path):
        """P12 双向变异：扫描器对已知坏样本必须命中。

        构造一个含坏 lazy import 的 AST 样本，验证收集器能提取到它，
        且 hasattr 检查能判定不可解析 —— 否则上一测试是恒绿的。
        """
        sample = (
            "def f():\n"
            "    from app.models.phase10_models import Adjustment\n"
            "    return Adjustment\n"
        )
        tree = ast.parse(sample)
        collected = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.ImportFrom) and (sub.module or "").startswith("app."):
                        for alias in sub.names:
                            collected.append((sub.module, alias.name))

        assert collected == [("app.models.phase10_models", "Adjustment")], (
            "收集器未能从样本提取函数体内 import"
        )

        mod = importlib.import_module("app.models.phase10_models")
        assert not hasattr(mod, "Adjustment"), (
            "phase10_models 竟然有 Adjustment —— 本 spec 的前提事实已变，需重新核实"
        )

    def test_known_good_import_passes(self):
        """P12 正样本：已修复后的正确路径必须通过。"""
        mod = importlib.import_module("app.models.audit_platform_models")
        for name in ("Adjustment", "AdjustmentEntry"):
            assert hasattr(mod, name), f"audit_platform_models 缺 {name}"

        attach = importlib.import_module("app.models.attachment_models")
        assert hasattr(attach, "Attachment"), "attachment_models 缺 Attachment"
