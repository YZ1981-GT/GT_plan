"""合并企业树三码推导（spec consol-tree-three-code-autobuild 任务 5.4）。

纯函数 ``derive_group_tree`` / ``derive_parent_links`` 直接喂 ``ProjectRecord``：
- 属性 P1（记录顺序无关）/ P2（单体恰一次、合并项目恰一个合并节点、node_key 唯一）/
  P3（合并节点恰一个合并差额 + 一个母公司子节点）/ P4（有分公司的企业节点恰一个母分差额 + 一个本部）/
  P5（派生链接与顺序无关、幂等）/ P6（同一合并企业的子树从哪一级根构建都相同）—— hypothesis，max_examples=5；
- 示例：多级合并、提升与「经 X 间接持有」、并存模式、母公司未建单体、年度隔离、上级=本企业、
  断环、脱挂、按控制方挂靠、关系缺省、口径冲突、分公司再有分公司、分公司的子公司；
- 真 SQLite：``build_tree`` 装载同年度记录（排除已删与其他年度、旧项目年度兜底）。
"""

from __future__ import annotations

import random
import uuid

import hypothesis.strategies as st
import pytest
import pytest_asyncio
from hypothesis import given, settings
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.consol_group_tree import (
    KIND_AGGREGATE,
    KIND_DATA,
    KIND_ELIM,
    MODE_BRANCH,
    MODE_MIXED,
    MODE_NONE,
    MODE_SUBSIDIARY,
    ROLE_BRANCH,
    ROLE_BRANCH_ELIM,
    ROLE_CONSOL,
    ROLE_CONSOL_ELIM,
    ROLE_HQ,
    ROLE_PARENT,
    ROLE_SUBSIDIARY,
    ProjectRecord,
    derive_group_tree,
    derive_parent_links,
)
from app.services.consol_tree_service import (
    TreeNode,
    find_node,
    find_node_by_key,
    iter_nodes,
    to_dict,
)

Y = 2025


def _id(tag: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"ctree-test/{tag}")


def rec(
    code: str, name: str, scope: str = "standalone", *, parent: str | None = None,
    relation: str | None = None, ultimate: str | None = None, year: int | None = Y,
    link: uuid.UUID | None = None,
) -> ProjectRecord:
    return ProjectRecord(
        id=_id(f"{code}/{scope}/{year}"), company_code=code, client_name=name, report_scope=scope,
        audit_year=year, parent_company_code=parent, ultimate_company_code=ultimate,
        relation_to_parent=relation, parent_project_id=link,
    )


def consol(code: str, name: str, **kw) -> ProjectRecord:
    return rec(code, name, "consolidated", **kw)


def tree_of(records: list[ProjectRecord], root: ProjectRecord) -> TreeNode:
    result = derive_group_tree(records, root, Y)
    assert result.root is not None
    return result.root


def shape(node: TreeNode) -> tuple:
    return (
        node.node_key, node.kind, node.project_id, node.host_project_id,
        tuple(shape(c) for c in node.children),
    )


def child_keys(node: TreeNode) -> list[str]:
    return [c.node_key for c in node.children]


def diag_codes(records, root) -> set[str]:
    return {d.code for d in derive_group_tree(records, root, Y).diagnostics}


# ─────────────────────────────── 示例 ───────────────────────────────


class TestExamples:
    def test_three_nodes_with_branch_expansion_and_mixed_mode(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        a = rec("A", "甲公司", parent="G", relation="subsidiary")
        b = rec("B", "某集团上海分公司", parent="G", relation="branch")
        root = tree_of([g_c, g_s, a, b], g_c)

        assert root.node_key == "G:consol" and root.kind == KIND_AGGREGATE
        assert root.display_name == "某集团（合并）"
        assert child_keys(root) == ["G:consol_elim", "G:parent", "A:subsidiary"]
        elim, parent, sub_a = root.children
        assert elim.kind == KIND_ELIM and elim.host_project_id == g_c.id and elim.project_id is None
        assert elim.display_name == "某集团（合并差额）"
        # 母公司有分公司 ⇒ 母公司节点是汇总：母分差额 + 本部 + 分公司
        assert parent.kind == KIND_AGGREGATE and parent.project_id is None
        assert parent.display_name == "某集团（母公司）"
        assert child_keys(parent) == ["G:branch_elim", "G:hq", "B:branch"]
        assert parent.children[0].host_project_id == g_c.id
        assert parent.children[0].display_name == "某集团（母分差额）"
        assert parent.children[1].project_id == g_s.id and parent.children[1].display_name == "某集团（本部）"
        assert parent.children[2].project_id == b.id and parent.children[2].relation == "branch"
        assert sub_a.project_id == a.id and sub_a.relation == "subsidiary" and sub_a.kind == KIND_DATA
        assert root.mode == MODE_MIXED

    def test_role_matrix_has_stable_node_keys_and_elim_hosts(self):
        """实体角色与计算差额角色共存时，节点键和分录承载项目必须可区分。"""
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        branch = rec("B", "某集团上海分公司", parent="G", relation="branch")
        subsidiary = rec("S", "乙公司", parent="G", relation="subsidiary")
        root = tree_of([g_c, g_s, branch, subsidiary], g_c)

        nodes = list(iter_nodes(root))
        assert [node.node_key for node in nodes] == [
            "G:consol", "G:consol_elim", "G:parent", "G:branch_elim", "G:hq",
            "B:branch", "S:subsidiary",
        ]
        assert len({node.node_key for node in nodes}) == len(nodes)
        assert {node.role for node in nodes} == {
            ROLE_CONSOL, ROLE_CONSOL_ELIM, ROLE_PARENT, ROLE_BRANCH_ELIM,
            ROLE_HQ, ROLE_BRANCH, ROLE_SUBSIDIARY,
        }

        consol_elim = find_node_by_key(root, "G:consol_elim")
        branch_elim = find_node_by_key(root, "G:branch_elim")
        assert consol_elim is not None and consol_elim.project_id is None
        assert branch_elim is not None and branch_elim.project_id is None
        assert consol_elim.host_project_id == g_c.id
        assert branch_elim.host_project_id == g_c.id
        assert root.mode == MODE_MIXED

        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        a = rec("A", "甲公司", parent="G", relation="subsidiary")
        root = tree_of([g_c, g_s, a], g_c)
        parent = find_node_by_key(root, "G:parent")
        assert parent.kind == KIND_DATA and parent.project_id == g_s.id and parent.children == []
        assert root.mode == MODE_SUBSIDIARY

    def test_multi_level_consolidation_recurses(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        s_c = consol("S", "乙控股", parent="G", relation="subsidiary")
        s_s = rec("S", "乙控股", parent="G", relation="subsidiary")
        t = rec("T", "丙公司", parent="S", relation="subsidiary")
        root = tree_of([g_c, g_s, s_c, s_s, t], g_c)
        s_node = find_node_by_key(root, "S:consol")
        assert s_node in root.children
        assert child_keys(s_node) == ["S:consol_elim", "S:parent", "T:subsidiary"]
        assert s_node.children[0].host_project_id == s_c.id, "下级合并的差额由下级合并项目承载"
        assert s_node.children[1].project_id == s_s.id

    def test_subsidiary_without_consol_promotes_members_with_via(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        m = rec("M", "中间公司", parent="G", relation="subsidiary")
        n = rec("N", "孙公司", parent="M", relation="subsidiary")
        root = tree_of([g_c, g_s, m, n], g_c)
        assert child_keys(root) == ["G:consol_elim", "G:parent", "M:subsidiary", "N:subsidiary"]
        assert find_node_by_key(root, "N:subsidiary").via == ["M"]
        assert "via" in diag_codes([g_c, g_s, m, n], g_c)

    def test_branch_of_branch_and_subsidiary_of_branch(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        b = rec("B", "上海分公司", parent="G", relation="branch")
        c = rec("C", "上海分公司浦东营业部", parent="B", relation="branch")
        s = rec("S", "丁公司", parent="B", relation="subsidiary")
        root = tree_of([g_c, g_s, b, c, s], g_c)
        b_node = find_node_by_key(root, "B:branch")
        assert b_node.kind == KIND_AGGREGATE and b_node.display_name == "上海分公司（汇总）"
        assert child_keys(b_node) == ["B:branch_elim", "B:hq", "C:branch"]
        assert b_node.children[0].host_project_id == g_c.id, "母分差额由最近的外层合并项目承载"
        # 分公司名下的子公司是集团的合并成员（挂在合并节点下）
        assert "S:subsidiary" in child_keys(root)

    def test_parent_standalone_missing_is_flagged_not_dropped(self):
        g_c = consol("G", "某集团")
        a = rec("A", "甲公司", parent="G", relation="subsidiary")
        result = derive_group_tree([g_c, a], g_c, Y)
        parent = find_node_by_key(result.root, "G:parent")
        assert parent.project_id is None and "standalone_missing" in parent.flags
        assert [d.code for d in result.diagnostics if d.code == "standalone_missing"] == ["standalone_missing"]

    def test_other_year_never_mixed(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        old = rec("A", "甲公司", parent="G", relation="subsidiary", year=2024)
        root = tree_of([g_c, g_s, old], g_c)
        assert "A" not in {n.company_code for n in iter_nodes(root)}

    def test_self_parent_is_top_without_self_edge(self):
        """上级代码 = 本企业（需求 1.5）：只一个实体、不建自环；三码相同就是根。"""
        g_c = consol("G", "某集团", parent="G", ultimate="G")
        g_s = rec("G", "某集团", parent="G", ultimate="G")
        a = rec("A", "甲公司", parent="G", relation="subsidiary", ultimate="G")
        result = derive_group_tree([g_c, g_s, a], g_c, Y)
        keys = [n.node_key for n in iter_nodes(result.root)]
        assert keys == ["G:consol", "G:consol_elim", "G:parent", "A:subsidiary"]
        assert result.root.parent_company_code is None
        assert not {"cycle_break", "detached", "relation_defaulted"} & {d.code for d in result.diagnostics}

    def test_cycle_broken_at_smallest_code_then_attached_by_ultimate(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        x = rec("X", "某甲", parent="Y", relation="subsidiary", ultimate="G")
        yy = rec("Y", "某乙", parent="X", relation="subsidiary", ultimate="G")
        result = derive_group_tree([g_c, g_s, x, yy], g_c, Y)
        x_node = find_node_by_key(result.root, "X:subsidiary")
        assert "cycle_break" in x_node.flags
        assert "Y:subsidiary" in {n.node_key for n in iter_nodes(result.root)}
        assert "cycle_break" in {d.code for d in result.diagnostics}

    def test_detached_attached_only_when_ultimate_is_this_group(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        d1 = rec("D1", "脱挂甲", parent="ZZZ", relation="subsidiary", ultimate="G")
        d2 = rec("D2", "脱挂乙", parent="ZZZ", relation="subsidiary", ultimate="OTHER")
        result = derive_group_tree([g_c, g_s, d1, d2], g_c, Y)
        codes = {n.company_code for n in iter_nodes(result.root)}
        assert "D1" in codes and "D2" not in codes
        assert "detached" in find_node_by_key(result.root, "D1:subsidiary").flags
        assert {d.company_code for d in result.diagnostics if d.code == "detached"} == {"D1"}

    def test_mutual_ultimate_attachment_broken_deterministically(self):
        """两家互为最终控制方且都没有上级（大样本随机探针抓到的 P6 反例）：挂靠会成环，
        断开代码较小者的挂靠 —— 两家各自为根构建时结论一致。"""
        e0_c = consol("E0", "企业零", ultimate="E1")
        e0_s = rec("E0", "企业零", ultimate="E1")
        e1_c = consol("E1", "企业一", parent="E1", ultimate="E0")
        records = [e0_c, e0_s, e1_c]
        from_e0 = derive_group_tree(records, e0_c, Y).root
        from_e1 = derive_group_tree(records, e1_c, Y).root
        assert "E1:consol" in child_keys(from_e0), "E1 按控制方挂到 E0 下"
        assert "E0" not in {n.company_code for n in iter_nodes(from_e1)}, "E0 的挂靠被断开"
        nested = find_node_by_key(from_e0, "E1:consol")
        assert [shape(c) for c in nested.children] == [shape(c) for c in from_e1.children]

    def test_branch_with_own_consol_is_folded_and_flagged(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        b_c = consol("B", "某集团上海分公司", parent="G", relation="branch")
        b_s = rec("B", "某集团上海分公司", parent="G", relation="branch")
        result = derive_group_tree([g_c, g_s, b_c, b_s], g_c, Y)
        assert find_node_by_key(result.root, "B:branch").project_id == b_s.id
        assert find_node_by_key(result.root, "B:consol") is None
        assert "branch_consol_ignored" in {d.code for d in result.diagnostics}

    def test_missing_parent_code_attached_by_ultimate(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        p = rec("P", "未填上级", ultimate="G")
        result = derive_group_tree([g_c, g_s, p], g_c, Y)
        node = find_node_by_key(result.root, "P:subsidiary")
        assert node is not None and "parent_missing" in node.flags

    def test_ultimate_without_consolidated_project_does_not_attach(self):
        """合并树按控制方挂靠要求控制方有合并项目（design §3.3）：控制方 U 只有单户项目 ⇒ X 不挂靠，
        既不进上层合并树，派生链接也为空（否则链接会指向合并项目、而树里却没有 X）。
        集团架构森林不要求（``attach_to_controllers``），那里 X 会显示在 U 下。"""
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        u = rec("U", "中间控股", parent="G", relation="subsidiary")
        x = rec("X", "丙公司", ultimate="U")
        records = [g_c, g_s, u, x]
        tree = tree_of(records, g_c)
        assert "X" not in {n.company_code for n in iter_nodes(tree)}
        assert derive_parent_links(records, Y)[x.id] is None

    def test_relation_defaulted_and_conflict(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        h_c = consol("H", "某控股")
        a_s = rec("A", "甲公司", parent="G", relation="subsidiary")
        a_c = consol("A", "甲公司", parent="H", relation="branch")
        b = rec("B", "乙公司", parent="G")  # 关系未填
        result = derive_group_tree([g_c, g_s, h_c, a_s, a_c, b], g_c, Y)
        codes = {d.code for d in result.diagnostics}
        assert {"relation_conflict", "relation_defaulted"} <= codes
        # 单户优先：A 在 G 下（且 A 有合并项目 ⇒ 三节点）
        assert find_node_by_key(result.root, "A:consol") in result.root.children
        assert "relation_defaulted" in find_node_by_key(result.root, "B:subsidiary").flags

    def test_root_not_consolidated_returns_lone_node(self):
        a = rec("A", "甲公司")
        result = derive_group_tree([a], a, Y)
        assert result.root.children == [] and result.root.project_id == a.id
        assert [d.code for d in result.diagnostics] == ["root_not_consolidated"]

    def test_year_unresolved_returns_lone_node(self):
        g_c = consol("G", "某集团", year=None)
        result = derive_group_tree([g_c], g_c, None)
        assert result.root.children == [] and [d.code for d in result.diagnostics] == ["year_unresolved"]

    @pytest.mark.parametrize(("relations", "mode"), [
        (["subsidiary"], MODE_SUBSIDIARY), (["branch"], MODE_BRANCH),
        (["subsidiary", "branch"], MODE_MIXED), ([], MODE_NONE),
    ])
    def test_mode_by_member_relations(self, relations, mode):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        members = [rec(f"M{i}", f"成员{i}", parent="G", relation=r) for i, r in enumerate(relations)]
        assert tree_of([g_c, g_s, *members], g_c).mode == mode

    def test_find_node_compat_and_to_dict_keys(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        root = tree_of([g_c, g_s], g_c)
        assert find_node(root, "G").node_key == "G:consol", "纯代码取首个节点（合并户）"
        assert find_node(root, "G:parent").project_id == g_s.id
        d = to_dict(root)
        legacy = {"project_id", "company_code", "company_name", "parent_company_code",
                  "ultimate_company_code", "consol_level", "children"}
        assert legacy <= set(d)
        elim = d["children"][0]
        assert elim["project_id"] is None and elim["host_project_id"] == str(g_c.id)
        assert elim["display_name"] == "某集团（合并差额）" and elim["kind"] == "elim"

    def test_links_follow_tree(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        s_c = consol("S", "乙控股", parent="G", relation="subsidiary")
        s_s = rec("S", "乙控股", parent="G", relation="subsidiary")
        m = rec("M", "中间公司", parent="S", relation="subsidiary")
        n = rec("N", "孙公司", parent="M", relation="subsidiary")
        b = rec("B", "分公司", parent="G", relation="branch")
        links = derive_parent_links([g_c, g_s, s_c, s_s, m, n, b], Y)
        assert links[g_s.id] == g_c.id and links[g_c.id] is None
        assert links[s_s.id] == s_c.id and links[s_c.id] == g_c.id
        assert links[m.id] == s_c.id and links[n.id] == s_c.id, "没有合并项目的中间层不截断链接"
        assert links[b.id] == g_c.id

    def test_link_mismatch_reported(self):
        g_c, g_s = consol("G", "某集团"), rec("G", "某集团")
        a = rec("A", "甲公司", parent="G", relation="subsidiary", link=None)
        result = derive_group_tree([g_c, g_s, a], g_c, Y)
        assert {d.company_code for d in result.diagnostics if d.code == "link_mismatch"} == {"A", "G"}


# ─────────────────────────────── 属性测试 ───────────────────────────────


@st.composite
def _groups(draw) -> list[ProjectRecord]:
    """随机集团：E0 必有合并项目（作根）；上级可空/指向任意企业（含自己）；关系三态；控制方可空。"""
    n = draw(st.integers(min_value=2, max_value=7))
    records: list[ProjectRecord] = []
    for i in range(n):
        code = f"E{i}"
        has_consol = True if i == 0 else draw(st.booleans())
        has_standalone = draw(st.booleans()) if has_consol else True
        parent_idx = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=n - 1)))
        relation = draw(st.sampled_from([None, "subsidiary", "branch"]))
        ult_idx = draw(st.one_of(st.none(), st.integers(min_value=0, max_value=n - 1)))
        kw = {
            "parent": f"E{parent_idx}" if parent_idx is not None else None,
            "relation": relation,
            "ultimate": f"E{ult_idx}" if ult_idx is not None else None,
        }
        if has_consol:
            records.append(consol(code, f"企业{i}", **kw))
        if has_standalone:
            records.append(rec(code, f"企业{i}", **kw))
    return records


def _root_of(records: list[ProjectRecord]) -> ProjectRecord:
    return next(r for r in records if r.company_code == "E0" and r.report_scope == "consolidated")


@settings(max_examples=5, deadline=None)
@given(records=_groups(), seed=st.integers(min_value=0, max_value=10_000))
def test_p1_order_independent(records, seed):
    root = _root_of(records)
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)
    a = derive_group_tree(records, root, Y)
    b = derive_group_tree(shuffled, root, Y)
    assert shape(a.root) == shape(b.root)
    assert a.mode == b.mode
    assert [d.to_dict() for d in a.diagnostics] == [d.to_dict() for d in b.diagnostics]


@settings(max_examples=5, deadline=None)
@given(records=_groups())
def test_p2_each_project_once_and_keys_unique(records):
    tree = derive_group_tree(records, _root_of(records), Y).root
    nodes = list(iter_nodes(tree))
    keys = [n.node_key for n in nodes]
    assert len(keys) == len(set(keys)), "node_key 树内唯一"
    in_tree = {n.company_code for n in nodes}
    standalone_ids = [r.id for r in records if r.report_scope == "standalone" and r.company_code in in_tree]
    data_ids = [n.project_id for n in nodes if n.kind == KIND_DATA and n.project_id is not None]
    assert sorted(map(str, data_ids)) == sorted(map(str, standalone_ids)), "树内企业的单体项目恰出现一次"
    consol_ids = [n.project_id for n in nodes if n.role == ROLE_CONSOL]
    assert len(consol_ids) == len(set(consol_ids)), "每个合并项目至多对应一个合并节点"


@settings(max_examples=5, deadline=None)
@given(records=_groups())
def test_p3_p4_structure(records):
    tree = derive_group_tree(records, _root_of(records), Y).root
    for n in iter_nodes(tree):
        roles = [c.role for c in n.children]
        if n.role == ROLE_CONSOL:
            assert roles.count(ROLE_CONSOL_ELIM) == 1 and roles.count(ROLE_PARENT) == 1
            assert roles[:2] == [ROLE_CONSOL_ELIM, ROLE_PARENT], "差额在前、母公司第二"
        elif n.kind == KIND_AGGREGATE:
            assert roles.count(ROLE_BRANCH_ELIM) == 1 and roles.count(ROLE_HQ) == 1
            assert roles[:2] == [ROLE_BRANCH_ELIM, ROLE_HQ]
        if n.kind == KIND_ELIM:
            assert n.children == [] and n.host_project_id is not None and n.project_id is None


@settings(max_examples=5, deadline=None)
@given(records=_groups())
def test_p6_nested_consol_subtree_is_root_independent(records):
    tree = derive_group_tree(records, _root_of(records), Y).root
    by_id = {r.id: r for r in records}
    for n in iter_nodes(tree):
        if n.role != ROLE_CONSOL or n is tree:
            continue
        own = derive_group_tree(records, by_id[n.project_id], Y).root
        assert [shape(c) for c in n.children] == [shape(c) for c in own.children]


@settings(max_examples=5, deadline=None)
@given(records=_groups(), seed=st.integers(min_value=0, max_value=10_000))
def test_p5_links_order_independent(records, seed):
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)
    assert derive_parent_links(records, Y) == derive_parent_links(shuffled, Y)
    assert set(derive_parent_links(records, Y)) == {r.id for r in records}


# ─────────────────────────────── 真 SQLite：build_tree 装载 ───────────────────────────────

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    from app.models.base import Base

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.mark.asyncio
async def test_build_tree_loads_same_year_from_db(db):
    from app.models.base import ProjectStatus
    from app.models.core import Project
    from app.services.consol_tree_service import build_tree

    def p(code, name, scope, **kw):
        return Project(name=f"{name}_{kw.pop('year_name', Y)}", client_name=name, status=ProjectStatus.created,
                       company_code=code, report_scope=scope, **kw)

    g_c = p("G", "某集团", "consolidated", audit_year=Y)
    g_s = p("G", "某集团", "standalone", audit_year=Y)
    a = p("A", "甲公司", "standalone", audit_year=Y, parent_company_code="G", relation_to_parent="subsidiary")
    b = p("B", "某集团上海分公司", "standalone", audit_year=Y, parent_company_code="G", relation_to_parent="branch")
    old = p("C", "上年公司", "standalone", audit_year=2024, parent_company_code="G", relation_to_parent="subsidiary")
    gone = p("D", "已删公司", "standalone", audit_year=Y, parent_company_code="G", is_deleted=True)
    # 物化年度为空的旧项目：按名称后缀 _2025 兜底解析
    legacy = p("E", "旧项目公司", "standalone", audit_year=None, parent_company_code="G",
               relation_to_parent="subsidiary")
    db.add_all([g_c, g_s, a, b, old, gone, legacy])
    await db.commit()

    tree = await build_tree(db, g_c.id)
    codes = {n.company_code for n in iter_nodes(tree)}
    assert codes == {"G", "A", "B", "E"}
    assert tree.mode == MODE_MIXED
    # 差额 → 母公司 → 其余成员按（名称，代码）；名称按字符码位排序（旧 U+65E7 < 甲 U+7532）
    assert [n.node_key for n in tree.children] == ["G:consol_elim", "G:parent", "E:subsidiary", "A:subsidiary"]
    assert isinstance(tree.diagnostics, list) and all(isinstance(d, dict) for d in tree.diagnostics)
    # 库存链接全空 ⇒ 推导结果与库存不一致，提示而不是报错
    assert {d["company_code"] for d in tree.diagnostics if d["code"] == "link_mismatch"} >= {"A", "B"}
    assert await build_tree(db, uuid.uuid4()) is None
