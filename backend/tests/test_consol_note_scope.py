"""任务 2.1：合并附注节点作用域共享解析器 —— 真 ORM / 真 SQLite 集成测试。

spec: consol-node-key-isolation-and-shared-context（需求 1.1、1.2、1.5；设计 §三、ADR-CNSC-001/002）。

被测真实生产函数（禁 mock 替换被测函数本身）：
  - ``consol_note_scope.requested_node_key``   显式 query 优先于 body；空串保留为无效输入
  - ``consol_note_scope.resolve_note_scope``   经当前企业树精确校验，产出 NodeScope / LegacyScope
  - ``consol_note_scope.is_root_consol_node``  经树判根（树根 + role=consol），非仅 ':consol' 后缀
  - ``consol_note_scope.load_scoped_record / exact_scoped_record``  作用域装载（根可回退 / 写不回退）

企业树身份用 ``group`` 夹具真实构建（G⊃A⊃A1, G⊃B；G:consol 为根，A:consol 为子合并节点）。
"""

from __future__ import annotations

import pytest

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.consol_note_data_models import ConsolNoteData
from app.services.consol_note_scope import (
    LegacyScope,
    NodeScope,
    NoteScopeError,
    exact_scoped_record,
    is_root_consol_node,
    load_scoped_record,
    requested_node_key,
    resolve_note_scope,
)
from app.services.consol_tree_service import build_tree, find_node_by_key

# 复用 test_consol_push 的真集团夹具。
from tests.test_consol_push import (  # noqa: F401
    Y,
    db,
    factory,
    group,
)
from tests.test_consol_note_node_isolation import SID, _add, _utc, tree  # noqa: F401


# ─────────────────────────── requested_node_key（§三.1；需求 1.5） ───────────────────────────


class TestRequestedNodeKey:
    def test_query_takes_priority_over_body(self):
        assert requested_node_key("Q:consol", {"node_key": "B:sub"}) == "Q:consol"

    def test_body_used_only_when_query_absent(self):
        assert requested_node_key(None, {"node_key": "B:sub"}) == "B:sub"

    def test_none_when_neither_present(self):
        assert requested_node_key(None, {}) is None
        assert requested_node_key(None, None) is None

    def test_empty_query_string_preserved_as_invalid_input(self):
        """空字符串是显式无效输入 —— 不降级成省略（由 resolve_note_scope 拒绝）。"""
        assert requested_node_key("", {"node_key": "B:sub"}) == ""


# ─────────────────────────── is_root_consol_node（§三.4；ADR-CNSC-001） ───────────────────────────


class TestIsRootConsol:
    @pytest.mark.asyncio
    async def test_tree_root_consol_is_root(self, tree):
        assert is_root_consol_node(tree, "G:consol") is True

    @pytest.mark.asyncio
    async def test_nonroot_consol_child_is_not_root(self, tree):
        """A:consol role=consol 但不是树根 ⇒ 不是根（禁 ':consol' 后缀兜底）。"""
        a = find_node_by_key(tree, "A:consol")
        assert a is not None and a.role == "consol"
        assert is_root_consol_node(tree, "A:consol") is False

    @pytest.mark.asyncio
    async def test_data_node_and_illegal_are_not_root(self, tree):
        assert is_root_consol_node(tree, "B:subsidiary") is False
        assert is_root_consol_node(tree, "ZZ:consol") is False
        assert is_root_consol_node(tree, "") is False
        assert is_root_consol_node(tree, None) is False
        assert is_root_consol_node(None, "G:consol") is False


# ─────────────────────────── resolve_note_scope（§三.1~§三.5；需求 1.1、1.2） ───────────────────────────


class TestResolveScope:
    @pytest.mark.asyncio
    async def test_no_node_key_is_legacy_scope(self, db, group):
        scope = await resolve_note_scope(db, group["G"].id, Y, node_key=None)
        assert isinstance(scope, LegacyScope)
        assert scope.node_key is None
        assert scope.is_root_consol is False
        assert scope.allow_legacy_fallback is False

    @pytest.mark.asyncio
    async def test_root_consol_resolves_as_root_node_scope(self, db, group):
        scope = await resolve_note_scope(db, group["G"].id, Y, node_key="G:consol")
        assert isinstance(scope, NodeScope)
        assert scope.node_key == "G:consol"
        assert scope.is_root_consol is True
        assert scope.allow_legacy_fallback is True
        assert scope.year == Y

    @pytest.mark.asyncio
    async def test_nonroot_consol_child_resolves_without_root(self, db, group):
        """A:consol 在树里但不是根 ⇒ NodeScope 但 is_root_consol=False（不享 legacy 回退）。"""
        scope = await resolve_note_scope(db, group["G"].id, Y, node_key="A:consol")
        assert isinstance(scope, NodeScope)
        assert scope.node_key == "A:consol"
        assert scope.is_root_consol is False
        assert scope.allow_legacy_fallback is False

    @pytest.mark.asyncio
    async def test_data_node_resolves_without_root(self, db, group):
        scope = await resolve_note_scope(db, group["G"].id, Y, node_key="B:subsidiary")
        assert isinstance(scope, NodeScope)
        assert scope.is_root_consol is False

    @pytest.mark.asyncio
    async def test_illegal_key_rejected_400(self, db, group):
        with pytest.raises(NoteScopeError) as exc:
            await resolve_note_scope(db, group["G"].id, Y, node_key="ZZ:consol")
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_empty_string_rejected_400(self, db, group):
        with pytest.raises(NoteScopeError) as exc:
            await resolve_note_scope(db, group["G"].id, Y, node_key="")
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_mismatched_year_rejected_400(self, db, group):
        """显式年度与项目审计年度不一致 ⇒ 400，不跨年读写（§三.2）。"""
        with pytest.raises(NoteScopeError) as exc:
            await resolve_note_scope(db, group["G"].id, Y - 1, node_key="G:consol")
        assert exc.value.status == 400

    @pytest.mark.asyncio
    async def test_non_consol_project_rejected_404(self, db, group):
        """单户项目不是合并项目 ⇒ 404。"""
        with pytest.raises(NoteScopeError) as exc:
            await resolve_note_scope(db, group["B"].id, Y, node_key="B:subsidiary")
        assert exc.value.status == 404

    @pytest.mark.asyncio
    async def test_effective_year_falls_back_to_project_year(self, db, group):
        """year=None 时取项目审计年度。"""
        scope = await resolve_note_scope(db, group["G"].id, None, node_key="G:consol")
        assert isinstance(scope, NodeScope)
        assert scope.year == Y


# ─────────────────────────── 作用域装载（§三.6~§三.7；需求 1.3、1.4） ───────────────────────────


class TestScopedLoaders:
    @pytest.mark.asyncio
    async def test_root_scope_load_falls_back_to_legacy(self, db, group):
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        scope = await resolve_note_scope(db, pid, Y, node_key="G:consol")
        rec = await load_scoped_record(db, scope, SID)
        assert rec is not None and rec.node_key is None and rec.data == {"v": "legacy"}

    @pytest.mark.asyncio
    async def test_nonroot_scope_load_does_not_fall_back(self, db, group):
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        scope = await resolve_note_scope(db, pid, Y, node_key="A:consol")
        assert await load_scoped_record(db, scope, SID) is None, "非树根子合并节点不得回退 legacy"

    @pytest.mark.asyncio
    async def test_exact_scope_never_falls_back(self, db, group):
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        scope = await resolve_note_scope(db, pid, Y, node_key="G:consol")
        assert await exact_scoped_record(db, scope, SID) is None, "写目标行不回退 legacy"

    @pytest.mark.asyncio
    async def test_legacy_scope_reads_null_only(self, db, group):
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key="G:consol", data={"v": "node"})
        await db.commit()
        scope = await resolve_note_scope(db, pid, Y, node_key=None)
        rec = await load_scoped_record(db, scope, SID)
        assert rec is not None and rec.node_key is None and rec.data == {"v": "legacy"}
