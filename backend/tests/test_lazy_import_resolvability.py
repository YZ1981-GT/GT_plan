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
import subprocess
from pathlib import Path

import pytest

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
    # ── F 循环：flag 仍 False 且模块不存在的条目（2026-10-07 现算精简）────
    # 🔴 f3_01_adjudication / f3_04_interest / f4_01_adjudication / f4_09_supplier_financing
    #    flag 已翻 True 但模块仍不存在 ⇒ 移入 _KNOWN_UNRESOLVED_BASELINE。
    # 🔴 其余 9 条 flag 已翻 True 且模块已存在 ⇒ 直接删除（非 zombie）。
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
# - static_sheet_payload_for_adjudication ×3：✅ 已实现（2026-10-07），已从基线删除。
_KNOWN_UNRESOLVED_BASELINE: frozenset[tuple[str, str, str]] = frozenset({
    ("app/routers/adjustments.py", "app.models.audit_platform_models", "ChecklistResponse"),
    ("app/routers/import_templates.py", "app.services.cell_formula_evaluator", "save_formula_batch"),
    ("app/routers/wp_template.py", "app.services.wp_parsed_data_service", "populate_parsed_data"),
    ("app/services/contract_analysis_service.py", "app.models.audit_platform_models", "TbAccount"),
    ("app/services/contract_analysis_service.py", "app.models.audit_platform_models", "TbAdjustment"),
    ("app/services/m8_general_risk_reserve_service.py", "app.models.audit_platform_models", "ChecklistResponse"),
    ("app/services/s_estimate_import_export_service.py", "app.models.audit_platform_models", "ChecklistResponse"),
    # ── F 循环：flag=True 但模块不存在（从 _FLAG_GATED_PLACEHOLDERS 移入，2026-10-07）
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_01_adjudication"),
    ("app/services/workpaper_sync/phase5_f4_accounts_payable.py", "app.services.workpaper_sync", "phase5_f4_09_supplier_financing"),
})

# ---------------------------------------------------------------------------
# 分类三：**检出相关** —— 工作树上可解析、纯 HEAD 检出上不可解析
# ---------------------------------------------------------------------------
# spec: d1-sync-row-table-engine-and-d1-coverage · X5-g（2026-09-28 接 CI 时建立）
#
# ═══ 为什么需要第三类 ═══
#
# 本守卫此前**从未在 CI 里跑过**（两个 workflow 引用它 0 次），只在开发者工作树上跑。
# 接进 CI 时在 `git worktree add --detach HEAD` 的干净检出上实测，报「新增 7 处」：
#
#   app/routers/tb_sync.py                     : EventPayload / EventType
#   app/services/independence_signing_service.py: ProjectAssignment
#   app/services/workpaper_sync/phase5_d3_expansion.py: phase5_d3_04_analysis /
#       _05_long_term / _06_related_party / _07_voucher_check
#
# 这 7 条在工作树上**全部可解析**：前 3 条的符号定义在 `audit_platform_models.py` 的
# **未提交**改动里；后 4 条的目标子模块文件本身**未入库**（`??` 状态）。
# 也就是：**import 侧已提交、定义侧没提交** —— 别 lane 的入库节奏问题。
#
# ⇒ 它们在两种检出上的表现**恰好相反**：
#      工作树 → 可解析 ⇒ 若放进 `_ALLOWED_UNRESOLVED` 会被「禁僵尸」判为已修好；
#      HEAD   → 不可解析 ⇒ 不放进去 CI 就红。
#    单张清单表达不了，必须单独成类并**豁免僵尸检查**。
#
# ═══ 豁免不是永久的（两条反向断言把它钉住）═══
#
#   1. `test_checkout_dependent_entries_are_really_unresolved_on_head`
#      —— 每条在 **HEAD 版**代码里必须**真的**取不到那个 name（按 `git show` 静态判定，
#         不依赖当前检出）。定义侧一入库，本条立刻要求移除登记。
#   2. `test_checkout_dependent_sources_are_committed`
#      —— import 侧文件必须**已提交**。若 import 侧自己都没入库，这条 import 在 HEAD 上
#         根本不存在，登记毫无意义（纯噪音）。
#
# 🔴 与「分类二（待修工单）」的区别是决定性的：分类二在**任何**检出上都是真缺陷
#    （运行时必抛 ImportError）；分类三只是检出不完整的投影，代码本身没问题。
#    混在一起会让「修好了没」这个问题失去答案。
_CHECKOUT_DEPENDENT_UNRESOLVED: frozenset[tuple[str, str, str]] = frozenset({
    # 归属 lane：tb_sync / 事件契约（符号定义在 audit_platform_models.py 未提交改动里）
    ("app/routers/tb_sync.py", "app.models.audit_platform_models", "EventPayload"),
    ("app/routers/tb_sync.py", "app.models.audit_platform_models", "EventType"),
    # 归属 lane：独立性签字（同上）
    (
        "app/services/independence_signing_service.py",
        "app.models.audit_platform_models",
        "ProjectAssignment",
    ),
    # 🔴 d3 的 4 条已入库（2026-10-07 现算），已删除。
})

# 守卫允许的全集 = 未实现占位 ∪ 待修工单 ∪ 检出相关
_ALLOWED_UNRESOLVED = (
    _FLAG_GATED_PLACEHOLDERS | _KNOWN_UNRESOLVED_BASELINE | _CHECKOUT_DEPENDENT_UNRESOLVED
)


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


def _is_tracked(repo_rel: str) -> bool:
    """该路径是否已纳入版本控制（仓库根相对路径，posix 分隔）。"""
    return subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", repo_rel],
        cwd=str(_BACKEND.parent), capture_output=True,
    ).returncode == 0


def _head_bytes(repo_rel: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{repo_rel}"],
        cwd=str(_BACKEND.parent), capture_output=True,
    )
    return None if proc.returncode != 0 else proc.stdout


def _resolvable_on_head(mod: str, name: str) -> bool | None:
    """在 **HEAD 版**代码里 `from {mod} import {name}` 能不能取到。

    静态判定，不 import、不依赖当前检出 —— 这样工作树与 CI 得到同一个结论
    （分类三的条目在两种检出上表现相反，只有脱离当前检出才能给出稳定判据）。

    Returns:
        True  取得到；False 取不到；None 无法判定（HEAD 里连 mod 都没有）。
    """
    mod_path = mod.replace(".", "/")
    # ① name 是子模块：`backend/<mod>/<name>.py`
    if _head_bytes(f"backend/{mod_path}/{name}.py") is not None:
        return True
    # ② name 是包：`backend/<mod>/<name>/__init__.py`
    if _head_bytes(f"backend/{mod_path}/{name}/__init__.py") is not None:
        return True
    # ③ name 是符号：在 HEAD 版 `<mod>.py` 或 `<mod>/__init__.py` 的顶层能找到定义/导入
    for candidate in (f"backend/{mod_path}.py", f"backend/{mod_path}/__init__.py"):
        raw = _head_bytes(candidate)
        if raw is None:
            continue
        try:
            tree = ast.parse(raw.decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            return None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == name:
                    return True
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == name:
                        return True
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == name:
                    return True
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if (alias.asname or alias.name.split(".")[0]) == name:
                        return True
        return False
    return None


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

        🔴 两处豁免（2026-09-28 接 CI 时补，都配了独立的反向断言，见下文）：

        * `_CHECKOUT_DEPENDENT_UNRESOLVED` —— 它在工作树上**本来就**可解析，
          按本条判据必然被算成僵尸。它的有效性由
          `test_checkout_dependent_entries_are_really_unresolved_on_head` 守（按 HEAD
          版代码静态判定），不由本条守。
        * **源文件不在当前检出** —— 扫不到的 import 当然不在 `unresolved` 里，但那不叫
          「修好了」。实测：`phase5_d{5,6,7}_expansion.py` 在纯 HEAD 检出上不存在
          （`??` 未入库），旧口径于是报 3 条僵尸、要求删掉 3 条**仍然有效**的工单。
          与 Gate 5 的 `absent_known_gaps`、Gate 6 的 `BASIS_FROM_UNCOMMITTED` 同型。
        """
        unresolved = _scan_unresolved()
        candidates = _ALLOWED_UNRESOLVED - unresolved - _CHECKOUT_DEPENDENT_UNRESOLVED

        zombies: list[tuple[str, str, str]] = []
        absent_source: list[tuple[str, str, str]] = []
        for item in sorted(candidates):
            if (_BACKEND / item[0]).exists():
                zombies.append(item)
            else:
                absent_source.append(item)

        assert not zombies, (
            f"清单中 {len(zombies)} 条已不再是缺陷（已修复或代码已删），"
            "请从 _KNOWN_UNRESOLVED_BASELINE / _FLAG_GATED_PLACEHOLDERS 移除：\n"
            + "\n".join(f"  {f}: from {m} import {n}" for f, m, n in zombies)
            + (
                "\n（另有 %d 条源文件不在本检出，已按「不完整检出」豁免，不计入僵尸）"
                % len(absent_source)
                if absent_source
                else ""
            )
        )

    def test_checkout_dependent_entries_are_really_unresolved_on_head(self):
        """分类三的有效前提：每条在 **HEAD 版**代码里真的取不到那个 name。

        🔴 按 `git show HEAD:<path>` 静态判定，**不依赖当前检出** —— 这样工作树与 CI
        得到同一个结论。定义侧一入库，本条立刻要求移除登记，豁免不会变成永久遮羞布。
        """
        if not _CHECKOUT_DEPENDENT_UNRESOLVED:
            pytest.skip("分类三为空 —— 无需校验")
        stale: list[tuple[str, str, str, str]] = []
        for rel_path, mod, name in sorted(_CHECKOUT_DEPENDENT_UNRESOLVED):
            verdict = _resolvable_on_head(mod, name)
            if verdict is True:
                stale.append((rel_path, mod, name, "HEAD 版已能取到"))
        assert not stale, (
            f"分类三有 {len(stale)} 条在 HEAD 版代码里已经可解析 —— 定义侧已入库，"
            "请从 _CHECKOUT_DEPENDENT_UNRESOLVED 移除（棘轮只许变短）：\n"
            + "\n".join(f"  {f}: from {m} import {n} —— {why}" for f, m, n, why in stale)
        )

    def test_checkout_dependent_sources_are_committed(self):
        """分类三的 import 侧文件必须**已提交**。

        若 import 侧自己都没入库，这条 import 在 HEAD 上根本不存在，登记纯噪音。
        """
        if not _CHECKOUT_DEPENDENT_UNRESOLVED:
            pytest.skip("分类三为空 —— 无需校验")
        uncommitted = [
            rel for rel, _m, _n in sorted(_CHECKOUT_DEPENDENT_UNRESOLVED)
            if not _is_tracked(f"backend/{rel}")
        ]
        assert not uncommitted, (
            "分类三里这些 import 侧文件未纳入版本控制 ⇒ HEAD 上不存在该 import，"
            f"登记无意义，请移除：\n" + "\n".join(f"  {r}" for r in sorted(set(uncommitted)))
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
