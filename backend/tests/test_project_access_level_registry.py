"""项目权限级别名必须是登记值 —— 拼错不得静默放行。

Feature: advanced-query-hardening-wiring-closure（收口顺带发现的授权缺陷）

缺陷形态：``require_project_access(min_permission)`` 内部用
``PERMISSION_HIERARCHY.get(min_permission, 0)`` 取所需层级。未登记的级别名静默取到
**0**，于是 ``user_level < 0`` 恒为假 —— **任何项目成员（含 readonly）都能通过**，门禁
形同不存在。全仓实测有 4 个**写**端点因此被降级：

- ``disclosure_notes`` 的 删除章节 / 更新状态 / 恢复章节 三处写了 ``"editor"``
- ``wp_editor_router`` 的 底稿签署状态更新 写了 ``"member"``

两个名字都不在 ``PERMISSION_HIERARCHY``（只有 ``edit`` / ``review`` / ``readonly``）里，
既不报错也无日志。这类缺陷唯一可靠的拦法是**在工厂调用期（模块导入期）硬失败**。

判据分两层：
1. 行为型 —— 传未登记级别必须抛错（fail-closed），而不是返回一个恒放行的依赖；
2. 全仓型 —— 扫所有 ``require_project_access("...")`` 调用点，级别名必须都在登记表里。
   这条防的是「今天修好、明天又写错一个」。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.deps import PERMISSION_HIERARCHY, require_project_access

APP_DIR = Path(__file__).resolve().parents[1] / "app"
CALL_RE = re.compile(r"""require_project_access\(\s*["']([^"']*)["']""")


class TestFailClosedOnUnknownLevel:
    def test_unknown_level_raises_at_factory_time(self):
        """未登记级别必须在工厂调用期抛错，而不是造出一个恒放行的依赖。"""
        for bogus in ("editor", "member", "write", "", "EDIT"):
            with pytest.raises(ValueError) as ei:
                require_project_access(bogus)
            assert "未登记" in str(ei.value) or "合法值" in str(ei.value)

    def test_registered_levels_still_work(self):
        """反向自检：三个登记级别必须都能正常造出依赖，否则上一条会把功能一起锁死。"""
        for level in sorted(PERMISSION_HIERARCHY):
            dep = require_project_access(level)
            assert callable(dep)

    def test_hierarchy_is_strictly_ordered(self):
        """层级值必须严格递增，且 readonly 必须 > 0。

        readonly=0 会让 ``user_level < required_level`` 对任何成员恒为假 —— 与「未登记
        级别取 0」是同一个洞的另一种写法。
        """
        assert PERMISSION_HIERARCHY["readonly"] > 0
        assert (
            PERMISSION_HIERARCHY["readonly"]
            < PERMISSION_HIERARCHY["review"]
            < PERMISSION_HIERARCHY["edit"]
        )


class TestNoUnregisteredLevelInCallSites:
    @staticmethod
    def _call_sites() -> list[tuple[str, int, str]]:
        out: list[tuple[str, int, str]] = []
        for path in sorted(APP_DIR.rglob("*.py")):
            src = path.read_text(encoding="utf-8", errors="ignore")
            for m in CALL_RE.finditer(src):
                line = src[: m.start()].count("\n") + 1
                out.append((path.as_posix(), line, m.group(1)))
        return out

    def test_scanner_finds_call_sites(self):
        """反向自检：扫描器至少要认出大量调用点，否则下一条会假绿。"""
        sites = self._call_sites()
        assert len(sites) > 100, f"只扫到 {len(sites)} 个调用点，扫描器可能失效"

    def test_all_call_sites_use_registered_levels(self):
        bad = [
            f"{p}:{ln} -> {lvl!r}"
            for p, ln, lvl in self._call_sites()
            if lvl not in PERMISSION_HIERARCHY
        ]
        assert not bad, (
            "以下调用点用了未登记的权限级别（会被静默降级为 0 = 任何项目成员放行）：\n"
            + "\n".join("  " + b for b in bad)
        )


class TestMutationEndpointsRequireEdit:
    """曾被降级的写端点必须要求 edit 或走附注编辑门禁。

    判据接受三种形态：直接挂 ``require_project_access("edit")``（底稿签字等一般写端点），
    走附注编辑门禁的路径依赖 ``require_note_edit_access``，或函数体调用
    ``assert_note_edit_access``（其内部以 review 级调用 ``assert_project_permission``，
    见 ``test_unified_note_gate_requires_review_eqcr_matrix_lock``）。
    """

    NOTE_EDIT_GATES = {"assert_note_edit_access", "assert_note_edit_access_for_object", "require_note_edit_access"}

    CASES = (
        ("backend/app/routers/disclosure_notes.py", "delete_section"),
        ("backend/app/routers/disclosure_notes.py", "restore_section"),
        ("backend/app/routers/wp_editor_router.py", "update_sign_status"),
    )

    def test_known_downgraded_endpoints_now_require_edit(self):
        import ast

        repo = APP_DIR.parents[1]
        problems: list[str] = []
        for rel, func in self.CASES:
            src = (repo / rel).read_text(encoding="utf-8")
            tree = ast.parse(src)
            node = next(
                (
                    n
                    for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == func
                ),
                None,
            )
            if node is None:
                problems.append(f"{rel}: 找不到端点函数 {func}（重命名了？判据已失效）")
                continue
            seg = ast.get_source_segment(src, node) or ""
            levels = CALL_RE.findall(seg)
            called = {
                getattr(c.func, "id", None) or getattr(c.func, "attr", None)
                for c in ast.walk(ast.parse(seg.lstrip()))
                if isinstance(c, ast.Call)
            }
            if "edit" not in levels and not (called & self.NOTE_EDIT_GATES):
                problems.append(
                    f"{rel}::{func} 既没有 require_project_access(\"edit\")，"
                    f"也没走附注编辑门禁（实测级别 {levels}）"
                )
        assert not problems, "\n".join(problems)

    def test_unified_note_gate_requires_review_eqcr_matrix_lock(self):
        """附注编辑门禁自身必须包含 review + EQCR + note:edit + consol_lock（需求 6.10）。

        ``assert_note_edit_access`` 在顶层语句中以 review 级调 ``assert_project_permission``，
        调 ``is_project_eqcr``，判定操作矩阵 ``note:edit``，并以 ``consol_lock`` 字面量判合并锁。
        """
        import ast
        import inspect

        from app.services.note_edit_gate import assert_note_edit_access, NOTE_EDIT_MIN_LEVEL

        # 验证门禁级别常量是 review
        assert NOTE_EDIT_MIN_LEVEL == "review", (
            f"NOTE_EDIT_MIN_LEVEL 应为 'review'，实际为 {NOTE_EDIT_MIN_LEVEL!r}"
        )

        src = inspect.getsource(assert_note_edit_access)
        tree = ast.parse(src.lstrip())
        called = {
            getattr(c.func, "id", None) or getattr(c.func, "attr", None)
            for c in ast.walk(tree)
            if isinstance(c, ast.Call)
        }
        assert "assert_project_permission" in called, (
            "assert_note_edit_access 未调用 assert_project_permission"
        )
        assert "is_project_eqcr" in called, (
            "assert_note_edit_access 未调用 EQCR 判定 is_project_eqcr"
        )
        # NOTE_EDIT_MIN_LEVEL 常量被传递给 assert_project_permission（在源码中引用）
        assert "NOTE_EDIT_MIN_LEVEL" in src, (
            "assert_note_edit_access 源码中未引用 NOTE_EDIT_MIN_LEVEL 常量"
        )
        # consol_lock 关键字参数在源码中
        assert "consol_lock" in src, (
            "assert_note_edit_access 源码中未见 consol_lock 关键字"
        )
        # note:edit 操作矩阵权限点
        from app.services.note_edit_gate import NOTE_EDIT_OPERATION
        assert NOTE_EDIT_OPERATION == "note:edit", (
            f"NOTE_EDIT_OPERATION 应为 'note:edit'，实际为 {NOTE_EDIT_OPERATION!r}"
        )
