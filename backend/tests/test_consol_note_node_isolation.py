"""任务 1.5：合并附注节点隔离与 legacy 兼容 —— 真 ORM / 真 SQLite 行集成测试。

spec: consol-node-key-isolation-and-shared-context（需求 1.1~1.6；设计 §二~§三、P1~P4）。

被测的是任务 1.3/1.4 落地的真实生产函数（禁用 mock 替换被测函数本身）：
  - ``consol_note_formula_service._note_data_record``        节点行 loader（含根 legacy 回退）
  - ``consol_note_formula_service._note_data_record_exact``  写入目标行（不回退 legacy）
  - ``consol_note_formula_service._copy_note_data_record``   根首次写入复制 legacy
  - ``routers.consol_note_sections._save_note_record / _load_note_record``  端点 upsert / 装载
企业树身份用 ``consol_tree_service.build_tree`` 真实构建（``group`` 夹具的 G⊃A⊃A1, G⊃B）。

覆盖场景（任务 1.5 清单）：
  双节点隔离 / 非法节点 / 项目·年度·章节范围过滤 / 根 GET 回退 NULL /
  非根不回退 / 复制后 legacy 行不变 / 无键旧调用只查 NULL。

证据纪律：断言写的是「设计要求的正确行为」。任务 2.1 已把根判定从 ``node_key.endswith(':consol')``
字符串后缀改为经企业树验证树根 consol 节点（``_is_tree_root_consol``，设计 §三.4 / ADR-CNSC-001），
``A:consol``（role=consol 但**不是**树根）不再错误回退 legacy —— 原 task 1.5 以 xfail(strict) 钉住的
缺陷现由 ``test_nonroot_consol_node_does_not_fall_back_to_legacy`` 真实通过。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa

import tests.conftest  # noqa: F401  注册全部模型 + SQLite 方言补丁
from app.models.consol_note_data_models import ConsolNoteData
from app.routers.consol_note_sections import (
    _load_note_record,
    _save_note_record,
)
from app.services.consol_note_formula_service import (
    _copy_note_data_record,
    _note_data_record,
    _note_data_record_exact,
)
from app.services.consol_tree_service import build_tree, find_node_by_key

# 复用 test_consol_push 的真集团夹具（真 SQLite 内存库 + 真 ORM 行）。
from tests.test_consol_push import (  # noqa: F401
    Y,
    db,
    factory,
    group,
)

SID = "note_5_1"  # 任一章节 id；本测聚焦归属元组隔离，模板内容无关


def _utc():
    return datetime.now(timezone.utc)


async def _add(db, *, project_id, year, section_id, node_key, data, is_stale=False):
    rec = ConsolNoteData(
        project_id=project_id, year=year, section_id=section_id, node_key=node_key,
        data=data, is_stale=is_stale, updated_at=_utc(),
    )
    db.add(rec)
    await db.flush()
    return rec


@pytest_asyncio.fixture
async def tree(db, group):
    """真实构建 G 集团企业树；返回 (root, keys)。"""
    root = await build_tree(db, group["G"].id)
    assert root is not None and root.node_key == "G:consol", "根节点应为 G:consol"
    return root


# ─────────────────────────── 双节点隔离（P1） ───────────────────────────


class TestNodeIsolation:
    @pytest.mark.asyncio
    async def test_two_nodes_do_not_overwrite_each_other(self, db, group):
        """P1：两个 node_key 对同 project/year/section 的写互不覆盖，各读各的。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key="G:parent", data={"v": "parent"})
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key="B:subsidiary", data={"v": "subB"})
        await db.commit()

        a = await _note_data_record_exact(db, pid, Y, SID, node_key="G:parent")
        b = await _note_data_record_exact(db, pid, Y, SID, node_key="B:subsidiary")
        assert a is not None and a.data == {"v": "parent"}
        assert b is not None and b.data == {"v": "subB"}
        # 两行物理独立
        assert a.id != b.id

    @pytest.mark.asyncio
    async def test_exact_loader_never_reads_other_node(self, db, group):
        """精确 loader 对某节点查询，绝不返回其它节点行（即使该节点无行）。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key="A:parent", data={"v": "A"})
        await db.commit()
        # B:subsidiary 没有行 —— 不得串到 A:parent 行
        assert await _note_data_record_exact(db, pid, Y, SID, node_key="B:subsidiary") is None


# ─────────────────── 项目 / 年度 / 章节范围过滤（P2） ───────────────────


class TestScopeFiltering:
    @pytest.mark.asyncio
    async def test_project_year_section_are_filtered(self, db, group):
        """同 node_key 下，跨项目 / 跨年度 / 跨章节的行互不命中。"""
        pid = group["G"].id
        other_pid = group["A"].id
        nk = "G:parent"
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=nk, data={"hit": "target"})
        await _add(db, project_id=other_pid, year=Y, section_id=SID, node_key=nk, data={"hit": "other_project"})
        await _add(db, project_id=pid, year=Y - 1, section_id=SID, node_key=nk, data={"hit": "other_year"})
        await _add(db, project_id=pid, year=Y, section_id="other_sec", node_key=nk, data={"hit": "other_section"})
        await db.commit()

        rec = await _note_data_record_exact(db, pid, Y, SID, node_key=nk)
        assert rec is not None and rec.data == {"hit": "target"}, "只命中同项目+年度+章节+节点的行"


# ───────────────────── 非法节点（P2，经树精确校验） ─────────────────────


class TestIllegalNode:
    @pytest.mark.asyncio
    async def test_illegal_key_not_in_tree(self, db, group, tree):
        """非法 node_key 不在当前树 ⇒ find_node_by_key 返回 None（上层据此拒绝）。"""
        assert find_node_by_key(tree, "ZZ:consol") is None
        assert find_node_by_key(tree, "G:fake_role") is None
        assert find_node_by_key(tree, "") is None
        # 合法键确实在树里
        assert find_node_by_key(tree, "G:consol") is not None
        assert find_node_by_key(tree, "B:subsidiary") is not None

    @pytest.mark.asyncio
    async def test_illegal_key_has_no_row_and_no_fallback(self, db, group):
        """非法键既无专属行、也不得回退到 legacy NULL 行。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        # 伪造一个 role 不是 consol 的键 ⇒ 不满足根回退条件 ⇒ 不读 legacy
        rec = await _note_data_record(db, pid, Y, SID, node_key="ZZ:parent")
        assert rec is None, "非法 / 非根节点不得回退到 legacy NULL 行"


# ──────────────── 根回退 / 非根不回退（P3；需求 1.3、1.4） ────────────────


class TestRootLegacyFallback:
    @pytest.mark.asyncio
    async def test_root_consol_falls_back_to_legacy_null_row(self, db, group):
        """P3：树根 consol 节点无专属行时，GET 回退到同项目/年度/章节的 NULL 行。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        rec = await _note_data_record(db, pid, Y, SID, node_key="G:consol")
        assert rec is not None and rec.data == {"v": "legacy"}, "根 consol 节点可回退 legacy"
        assert rec.node_key is None, "回退命中的是 legacy NULL 行本身"

    @pytest.mark.asyncio
    async def test_root_prefers_own_node_row_over_legacy(self, db, group):
        """根节点有专属行时优先读专属行，不回退 legacy。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key="G:consol", data={"v": "own"})
        await db.commit()
        rec = await _note_data_record(db, pid, Y, SID, node_key="G:consol")
        assert rec is not None and rec.data == {"v": "own"}

    @pytest.mark.asyncio
    async def test_data_node_does_not_fall_back(self, db, group):
        """非根数据节点（parent / subsidiary）无专属行时不得回退 legacy。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        assert await _note_data_record(db, pid, Y, SID, node_key="G:parent") is None
        assert await _note_data_record(db, pid, Y, SID, node_key="B:subsidiary") is None

    @pytest.mark.asyncio
    async def test_exact_writer_target_never_fallback(self, db, group):
        """写入目标 loader（_exact）对根节点也不回退 legacy —— 写必须落专属行。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        assert await _note_data_record_exact(db, pid, Y, SID, node_key="G:consol") is None, \
            "根节点首次写入前，写目标行应不存在（不能把 legacy 当成写目标）"

    @pytest.mark.asyncio
    async def test_nonroot_consol_node_does_not_fall_back_to_legacy(self, db, group, tree):
        """ADR-CNSC-001：根身份经企业树验证（树根 + role=consol），不仅凭 ':consol' 后缀。

        ``A:consol`` role=consol 但**不是**树根（是 G 的子合并节点）。``_note_data_record`` 现经企业树
        判根（``_is_tree_root_consol``）：A:consol 非树根 ⇒ 不回退 legacy。
        （任务 2.1 根因修复后，原 task 1.5 的 xfail(strict) 守卫转为真实通过。）
        """
        pid = group["G"].id
        # 现读确认 A:consol 存在于树、role 为 consol，但不是根
        a_consol = find_node_by_key(tree, "A:consol")
        assert a_consol is not None and a_consol.role == "consol"
        assert tree.node_key == "G:consol" and tree.node_key != "A:consol"
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()
        rec = await _note_data_record(db, pid, Y, SID, node_key="A:consol")
        # 设计要求：非树根节点不得回退 legacy
        assert rec is None, "非树根的 consol 子节点不应回退到 legacy NULL 行（ADR-CNSC-001）"


# ──────────── 复制后 legacy 不变（P3）；无键只查 NULL（P4） ────────────


class TestCopyAndLegacyCompat:
    @pytest.mark.asyncio
    async def test_root_first_write_copies_and_leaves_legacy_untouched(self, db, group):
        """P3：根首次写入从 legacy 复制为节点专属行；legacy 行字段/字节不变。"""
        pid = group["G"].id
        legacy = await _add(
            db, project_id=pid, year=Y, section_id=SID, node_key=None,
            data={"headers": ["项目", "期末"], "rows": [["货币资金", "100"]]}, is_stale=True,
        )
        await db.commit()
        legacy_id = legacy.id
        legacy_data_before = {"headers": ["项目", "期末"], "rows": [["货币资金", "100"]]}
        legacy_stale_before = legacy.is_stale

        copied = await _copy_note_data_record(
            db, legacy, project_id=pid, year=Y, section_id=SID, node_key="G:consol",
        )
        await db.commit()

        # 新建的是独立的节点专属行
        assert copied.id != legacy_id and copied.node_key == "G:consol"
        assert copied.data == legacy_data_before, "复制内容与 legacy 一致"
        assert copied.is_stale == legacy_stale_before

        # 复制是深拷贝：改动节点行不污染 legacy
        copied.data["rows"][0][1] = "999"
        await db.flush()

        # 独立事务复读 legacy，确认未被改动
        legacy_reread = (await db.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.id == legacy_id
        ))).scalar_one()
        assert legacy_reread.data == legacy_data_before, "legacy 行数据必须保持不变"
        assert legacy_reread.node_key is None and legacy_reread.is_stale == legacy_stale_before

    @pytest.mark.asyncio
    async def test_legacy_only_call_reads_null_row_only(self, db, group):
        """P4：无 node_key 的旧调用只访问 NULL 行，不读任何节点专属行。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key="G:consol", data={"v": "node"})
        await db.commit()
        rec = await _note_data_record(db, pid, Y, SID, node_key=None)
        assert rec is not None and rec.data == {"v": "legacy"} and rec.node_key is None
        rec_exact = await _note_data_record_exact(db, pid, Y, SID, node_key=None)
        assert rec_exact is not None and rec_exact.node_key is None


# ─────────── 端点级 upsert / 装载（_save_note_record / _load_note_record） ───────────


class TestRouterSaveLoad:
    @pytest.mark.asyncio
    async def test_save_creates_node_row_without_touching_legacy(self, db, group):
        """根节点 PUT：从 legacy 读到数据后，保存只创建/更新节点专属行，legacy 不变。"""
        pid = group["G"].id
        await _add(db, project_id=pid, year=Y, section_id=SID, node_key=None, data={"v": "legacy"})
        await db.commit()

        await _save_note_record(db, pid, Y, SID, "G:consol", {"v": "node-save"}, _utc())
        await db.commit()

        # legacy 行原样
        legacy = (await db.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.project_id == pid, ConsolNoteData.year == Y,
            ConsolNoteData.section_id == SID, ConsolNoteData.node_key.is_(None),
        ))).scalar_one()
        assert legacy.data == {"v": "legacy"}
        # 节点专属行已建
        node_row = (await db.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.project_id == pid, ConsolNoteData.year == Y,
            ConsolNoteData.section_id == SID, ConsolNoteData.node_key == "G:consol",
        ))).scalar_one()
        assert node_row.data == {"v": "node-save"}

    @pytest.mark.asyncio
    async def test_save_two_nodes_then_each_reread_returns_own(self, db, group):
        """需求 1.6：节点 A、B 先后保存后，各自重读返回各自最后保存的数据。"""
        pid = group["G"].id
        await _save_note_record(db, pid, Y, SID, "G:parent", {"v": "A1"}, _utc())
        await _save_note_record(db, pid, Y, SID, "B:subsidiary", {"v": "B1"}, _utc())
        await db.commit()
        await _save_note_record(db, pid, Y, SID, "G:parent", {"v": "A2"}, _utc())
        await db.commit()

        a = await _load_note_record(db, pid, Y, SID, "G:parent")
        b = await _load_note_record(db, pid, Y, SID, "B:subsidiary")
        assert a is not None and a.data == {"v": "A2"}
        assert b is not None and b.data == {"v": "B1"}

    @pytest.mark.asyncio
    async def test_legacy_null_unique_index_upsert(self, db, group):
        """V177 legacy 部分唯一索引：同 project/year/section 的 NULL 行二次保存更新而非重复插入。"""
        pid = group["G"].id
        await _save_note_record(db, pid, Y, SID, None, {"v": "first"}, _utc())
        await db.commit()
        await _save_note_record(db, pid, Y, SID, None, {"v": "second"}, _utc())
        await db.commit()
        rows = (await db.execute(sa.select(ConsolNoteData).where(
            ConsolNoteData.project_id == pid, ConsolNoteData.year == Y,
            ConsolNoteData.section_id == SID, ConsolNoteData.node_key.is_(None),
        ))).scalars().all()
        assert len(rows) == 1 and rows[0].data == {"v": "second"}
