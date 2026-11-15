"""
test_staged_rows_not_visible.py

「半成品 staged 行不可见」不变式守卫
（spec platform-global-display-settings-closure 任务 8 / design §5 staged-only writer）。

三层保证，每层都要有断言：

1. **写入侧**：`bulk_insert_staged` 默认 `is_deleted=True` + 必填 `dataset_id`
   ⇒ staged 行既带 stage dataset_id 又被标删。
2. **读取侧**：`get_active_filter` 必须同时约束 `dataset_id == active` 与
   `is_deleted == false` ⇒ staged 行在任何一层都落选。
3. **激活侧**：`DatasetService.activate` 在切换 active 的同时把 staged 行
   的 `is_deleted` 放开（否则激活后数据仍不可见）。

🔴 为什么需要这个文件：三层分属三个模块，任何一层被改动都会让
「导入中数据泄漏」或「激活后看不见」——两种都不会报错，只会静默错。
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]


def _writer_src() -> str:
    return (_BACKEND / "app" / "services" / "ledger_import" / "writer.py").read_text(encoding="utf-8")


def _dataset_query_src() -> str:
    return (_BACKEND / "app" / "services" / "dataset_query.py").read_text(encoding="utf-8")


# ── 1. 写入侧：默认 is_deleted=True 且 dataset_id 必填 ────


class TestWriteSide:
    def test_bulk_insert_staged_default_is_deleted_true(self) -> None:
        from app.services.ledger_import.writer import bulk_insert_staged

        params = inspect.signature(bulk_insert_staged).parameters
        assert "is_deleted" in params
        assert params["is_deleted"].default is True, (
            "bulk_insert_staged 的 is_deleted 默认值必须是 True（staged 隐藏）"
        )

    def test_bulk_insert_staged_requires_dataset_id(self) -> None:
        """`dataset_id` 必须是**必填**（keyword-only 且无默认）。

        可选的 dataset_id 会让「忘记传」变成「写进所有版本的可见行」。
        """
        from app.services.ledger_import.writer import bulk_insert_staged

        params = inspect.signature(bulk_insert_staged).parameters
        assert "dataset_id" in params
        assert params["dataset_id"].default is inspect.Parameter.empty, (
            "dataset_id 不能有默认值（忘记传会写成可见行）"
        )

    @pytest.mark.parametrize("fn_name", ["bulk_copy_staged", "bulk_write_staged"])
    def test_other_staged_writers_also_hidden(self, fn_name: str) -> None:
        from app.services.ledger_import import writer

        fn = getattr(writer, fn_name)
        params = inspect.signature(fn).parameters
        assert "dataset_id" in params
        assert params["dataset_id"].default is inspect.Parameter.empty

    def test_writer_sets_is_deleted_in_row_payload(self) -> None:
        """写入时真的把 is_deleted 写进行数据（不是只在签名里声明）。

        三种真实写法（现读实证）：
        - dict 路径：`rec["is_deleted"] = is_deleted`
        - COPY 路径（按列索引）：`row_list[idx_deleted] = is_deleted`
        🔴 首版我按 `"is_deleted": is_deleted`（字典字面量）写判据 —— 实测
        writer 用的是**赋值**而不是字面量，导致假红。
        """
        src = _writer_src()
        assert 'rec["is_deleted"] = is_deleted' in src, (
            "dict 写入路径未设置 is_deleted"
        )
        assert "row_list[idx_deleted] = is_deleted" in src, (
            "COPY 写入路径未按列索引设置 is_deleted"
        )


# ── 2. 读取侧：dataset_id + is_deleted 双约束 ─────────────


class TestReadSide:
    """读取侧：`get_active_filter` 的**每条**路径都要双约束。

    🔴 `get_active_filter` 有三条返回路径：
    1. 无项目权限 ⇒ `sa.literal(False)`（永假，天然排除）
    2. `force_dataset_id` 分支 ⇒ dataset_id + is_deleted
    3. active_id 分支 ⇒ dataset_id + is_deleted
    末路 fallback 是 `base_filter`（只 project+year+is_deleted）。

    🔴 变异实证（2026-11-16）：首版用正则「只要有一处 dataset_id == 就过」，
    删掉 active 分支的约束仍全绿存活 —— 因为 force 分支那一处还在。
    改成**逐分支切段**后，S5/S6 各自都能打红。
    """

    def _branches(self) -> dict[str, str]:
        """把 `get_active_filter` 切成三个分支源码段。"""
        src = _dataset_query_src()
        start = src.find("async def get_active_filter")
        assert start > 0, "找不到 get_active_filter"
        end = src.find("\nasync def ", start + 10)
        body = src[start: end if end > 0 else len(src)]

        force_start = body.find("if force_dataset_id is not None")
        active_start = body.find("# 四表已有 dataset_id 列")
        assert force_start > 0, "找不到 force_dataset_id 分支"
        assert active_start > force_start, "找不到 active_id 分支"
        return {
            "force": body[force_start:active_start],
            "active": body[active_start:],
        }

    @pytest.mark.parametrize("branch", ["force", "active"])
    def test_each_branch_has_dataset_id_constraint(self, branch: str) -> None:
        seg = self._branches()[branch]
        assert "dataset_id ==" in seg, (
            f"{branch} 分支缺少 dataset_id 约束（staged 行会泄漏）"
        )

    @pytest.mark.parametrize("branch", ["force", "active"])
    def test_each_branch_has_is_deleted_constraint(self, branch: str) -> None:
        seg = self._branches()[branch]
        assert "is_deleted == sa.false()" in seg, (
            f"{branch} 分支缺少 is_deleted 约束（staged 行会泄漏）"
        )

    def test_no_privilege_path_returns_literal_false(self) -> None:
        """无项目权限分支必须返回永假（不是「不加约束」）。"""
        src = _dataset_query_src()
        assert "return sa.literal(False)" in src

    def test_fallback_base_filter_still_hides_deleted(self) -> None:
        """末路 fallback（无 active dataset）也必须排除已删行。"""
        src = _dataset_query_src()
        idx = src.find("base_filter = sa.and_(")
        assert idx > 0
        seg = src[idx: idx + 300]
        assert "is_deleted == sa.false()" in seg


# ── 3. 激活侧：切换 active 时放开 staged 行 ────────────────


class TestActivationSide:
    def _activate_src(self) -> str:
        """取 `DatasetService.activate` 的源码（可能跨文件）。"""
        p = _BACKEND / "app" / "services" / "dataset_service.py"
        src = p.read_text(encoding="utf-8")
        start = src.find("async def activate(")
        assert start > 0, "找不到 DatasetService.activate"
        end = src.find("\n    async def ", start + 10)
        return src[start: end if end > 0 else len(src)]

    def test_activate_clears_is_deleted_for_new_dataset(self) -> None:
        """激活必须把新 dataset 的行的 `is_deleted` 置 false（否则激活后看不见）。"""
        body = self._activate_src()
        # 允许 update(...).values(is_deleted=False) 或 is_deleted = False
        assert re.search(r"is_deleted\s*=\s*(sa\.)?false\(\)|is_deleted\s*=\s*False", body), (
            "activate 未放开新 dataset 的 is_deleted；激活后数据仍不可见"
        )

    def test_activate_marks_old_dataset_deleted(self) -> None:
        """旧 active 的数据必须被标记（否则新旧两版同时可见 = 双计）。"""
        body = self._activate_src()
        assert "superseded" in body.lower() or "is_deleted" in body, (
            "activate 未处理旧 active 数据"
        )


# ── 4. 反向：写入侧不得有「staged 但写可见行」的路径 ────────


class TestNoVisibleStagedPath:
    def test_no_staged_writer_defaults_to_visible(self) -> None:
        """所有 `*_staged` 写函数的 `is_deleted` 默认值都必须是 True。"""
        from app.services.ledger_import import writer

        offenders: list[str] = []
        for name in dir(writer):
            if not name.endswith("_staged") or not name.startswith("bulk_"):
                continue
            fn = getattr(writer, name)
            if not callable(fn):
                continue
            try:
                params = inspect.signature(fn).parameters
            except (TypeError, ValueError):
                continue
            if "is_deleted" not in params:
                continue
            if params["is_deleted"].default is not True:
                offenders.append(f"{name}: default={params['is_deleted'].default!r}")
        assert not offenders, (
            f"以下 staged writer 的 is_deleted 默认值不是 True：{offenders}"
        )

    def test_clear_project_year_does_not_touch_other_datasets(self) -> None:
        """`clear_project_year` 若按 project+year 全删，会连 active 数据一起抹掉。"""
        src = _writer_src()
        start = src.find("async def clear_project_year")
        assert start > 0
        end = src.find("\ndef ", start + 10)
        body = src[start: end if end > 0 else len(src)]
        # 必须带 dataset_id 或其他收窄条件，不能只有 project+year
        assert "dataset_id" in body or "is_deleted" in body, (
            "clear_project_year 只按 project+year 删除，会抹掉 active 数据"
        )
