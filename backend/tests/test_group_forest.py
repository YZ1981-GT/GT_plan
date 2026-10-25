"""集团架构森林（spec consol-tree-three-code-autobuild 任务 9.2 / 9.3，需求 8）。

纯函数 ``build_forest``（``GET /api/projects/tree`` 与批量导入预览共用）：
- 需求 8.1 企业实体：同代码同年度的合并与单户项目合为一个节点，两个项目都在 ``projects`` 里，不因同代码丢项目；
- 需求 8.2 年度统一解析：只填了审计年度（期末日为空）的项目按年度归组；缺年度属性的轻量对象不报错；
- 未传年度 ⇒ 按（控制方, 年度）分树，不同年度绝不同树；年度无法解析的项目自成一组；
- 上级=本企业 ⇒ 顶层企业不建自环；与合并树同源的脱挂 / 断环；按控制方挂靠不要求控制方有合并项目；
- 报表类型筛选：被筛掉的中间企业由保留下级接替并记 ``via``，不把下级误标脱挂；
- 可见性过滤后上级确有项目 ⇒ 标「上级不可见」而不是脱挂；
- 属性（hypothesis max_examples=5）：输入顺序无关；每个项目恰出现一次；同一企业只有一个节点。
"""

from __future__ import annotations

import random
import uuid
from datetime import date
from types import SimpleNamespace

import hypothesis.strategies as st
from hypothesis import given, settings

from app.services.group_forest import build_forest

Y = 2025


def _pid(tag: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"ctree-forest/{tag}")


def proj(code, client, scope="standalone", *, parent=None, ultimate=None, relation=None,
         year=Y, period_end=None, tag=None, **extra):
    """轻量项目（批量预览同款 SimpleNamespace）；``year`` 写物化年度列，``period_end`` 只写期末日。"""
    return SimpleNamespace(
        id=_pid(tag or f"{code}/{scope}/{year}/{period_end}"),
        company_code=code, client_name=client, report_scope=scope,
        parent_company_code=parent, ultimate_company_code=ultimate, relation_to_parent=relation,
        audit_year=year, audit_period_end=period_end, status="execution", consol_level=1, **extra,
    )


def walk(nodes):
    for n in nodes:
        yield n
        yield from walk(n["children"])


def all_nodes(forest):
    for t in forest["trees"]:
        yield from walk(t["children"])
    yield from walk(forest["independents"])


def node(forest, code):
    found = [n for n in all_nodes(forest) if n["companyCode"] == code]
    assert len(found) == 1, f"{code} 出现 {len(found)} 次"
    return found[0]


def child_codes(n):
    return [c["companyCode"] for c in n["children"]]


def project_ids(forest):
    return sorted(p["id"] for n in all_nodes(forest) for p in n["projects"])


# ─────────────────────────────── 需求 8.1：企业实体 ───────────────────────────────


class TestEntityNodes:
    def test_consolidated_and_standalone_merge_into_one_node(self):
        """同代码同年度的合并与单户项目 ⇒ 一个企业节点，两个项目都在（旧实现后者覆盖前者、丢一个项目）。"""
        g_c = proj("G", "某集团", "consolidated", ultimate="G")
        g_s = proj("G", "某集团", ultimate="G")
        a = proj("A", "甲公司", parent="G", ultimate="G", relation="subsidiary")
        forest = build_forest([g_s, a, g_c])

        [tree] = forest["trees"]
        assert (tree["ultimateCode"], tree["ultimateName"], tree["year"]) == ("G", "某集团", Y)
        assert tree["rootProjectId"] == str(g_c.id), "根项目取合并项目（点树头进合并页）"
        root = node(forest, "G")
        assert root["id"] == str(g_c.id)
        assert root["consolidatedProjectId"] == str(g_c.id)
        assert root["standaloneProjectId"] == str(g_s.id)
        assert [(p["id"], p["reportScope"]) for p in root["projects"]] == [
            (str(g_c.id), "consolidated"), (str(g_s.id), "standalone"),
        ]
        assert child_codes(root) == ["A"]
        sub = node(forest, "A")
        assert sub["relation"] == "subsidiary" and sub["year"] == Y
        assert sub["consolidatedProjectId"] is None and sub["standaloneProjectId"] == str(a.id)

    def test_duplicate_same_scope_projects_are_listed_and_flagged(self):
        """同代码同年度同口径两个项目（数据异常）⇒ 仍一个节点，两个都列出并标重复，不丢项目。"""
        s1 = proj("S", "乙公司", tag="s1")
        s2 = proj("S", "乙公司", tag="s2")
        forest = build_forest([s1, s2])
        n = node(forest, "S")
        assert sorted(p["id"] for p in n["projects"]) == sorted([str(s1.id), str(s2.id)])
        assert sum(p["duplicate"] for p in n["projects"]) == 1
        assert "duplicate_project" in n["flags"]

    def test_relation_and_branch_are_labelled(self):
        g = proj("G", "某集团", "consolidated", ultimate="G")
        b = proj("B", "某集团上海分公司", parent="G", ultimate="G", relation="branch")
        forest = build_forest([g, b])
        assert node(forest, "B")["relation"] == "branch"
        assert node(forest, "G")["relation"] is None


# ─────────────────────────────── 需求 8.2：年度 ───────────────────────────────


class TestYears:
    def test_audit_year_only_projects_are_found_by_year(self):
        """F11：真库项目只填审计年度、期末日为空 —— 旧实现只看期末日 ⇒ 按年度查得 0 棵树。"""
        g = proj("G", "某集团", "consolidated", ultimate="G")
        a = proj("A", "甲公司", parent="G", ultimate="G", relation="subsidiary")
        forest = build_forest([g, a], year=Y)
        assert [t["ultimateCode"] for t in forest["trees"]] == ["G"]
        assert child_codes(node(forest, "G")) == ["A"]

    def test_period_end_and_name_suffix_fallbacks(self):
        """年度列为空时按期末日、再按项目名后缀解析（平台统一 5 级解析）。"""
        g = proj("G", "某集团", "consolidated", ultimate="G", year=None, period_end=date(Y, 12, 31))
        a = proj("A", "甲公司", parent="G", ultimate="G", relation="subsidiary", year=None, name=f"甲公司_{Y}")
        forest = build_forest([g, a], year=Y)
        assert child_codes(node(forest, "G")) == ["A"]

    def test_lightweight_objects_without_year_attributes(self):
        """批量预览行没有 audit_year / wizard_state / name 属性 ⇒ 不报错，年度按空处理。"""
        bare = SimpleNamespace(id=_pid("bare"), company_code="X", client_name="某企业")
        forest = build_forest([bare])
        n = node(forest, "X")
        assert n["year"] is None and n["isIndependent"] is True

    def test_years_never_share_a_tree(self):
        """未传年度 ⇒ 每个（控制方, 年度）一棵树：2024 的子公司不会挂到 2025 的母公司下。"""
        g25 = proj("G", "某集团", "consolidated", ultimate="G", year=2025)
        g24 = proj("G", "某集团", "consolidated", ultimate="G", year=2024)
        a24 = proj("A", "甲公司", parent="G", ultimate="G", relation="subsidiary", year=2024)
        forest = build_forest([g24, a24, g25])
        assert [(t["ultimateCode"], t["year"]) for t in forest["trees"]] == [("G", 2025), ("G", 2024)]
        assert len({t["key"] for t in forest["trees"]}) == 2
        t25, t24 = forest["trees"]
        assert [c["companyCode"] for c in walk(t25["children"])] == ["G"]
        assert [c["companyCode"] for c in walk(t24["children"])] == ["G", "A"]
        only_2024 = build_forest([g24, a24, g25], year=2024)
        assert [(t["ultimateCode"], t["year"]) for t in only_2024["trees"]] == [("G", 2024)]

    def test_unresolved_year_projects_form_their_own_group(self):
        """年度无法解析的项目不与有年度的项目混建（它们之间仍按三码成树）。"""
        g = proj("G", "某集团", "consolidated", ultimate="G")
        a = proj("A", "甲公司", parent="G", ultimate="G", relation="subsidiary", year=None)
        forest = build_forest([g, a])
        years = sorted((t["year"] is None, t["ultimateCode"]) for t in forest["trees"])
        assert years == [(False, "G"), (True, "G")]
        assert node(forest, "A")["year"] is None


# ─────────────────────────────── 结构：与合并树同源的边 ───────────────────────────────


class TestStructure:
    def test_self_parent_is_top_level(self):
        """上级=本企业（需求 1.5）⇒ 顶层企业，不建自环、不标脱挂。"""
        g = proj("G", "某集团", "consolidated", parent="G", ultimate="G")
        forest = build_forest([g])
        [tree] = forest["trees"]
        [root] = tree["children"]
        assert root["companyCode"] == "G" and root["children"] == []
        assert not root["isDetached"] and root["flags"] == []

    def test_attach_by_controller_without_consolidated_project(self):
        """没有上级的企业按控制方挂到控制方企业下 —— 控制方只有单户项目也挂（森林看架构，不看合并范围）。"""
        g = proj("G", "某集团", ultimate="G")
        x = proj("X", "丙公司", ultimate="G")
        forest = build_forest([g, x])
        assert child_codes(node(forest, "G")) == ["X"]
        assert forest["independents"] == []

    def test_detached_goes_under_controller_and_is_flagged(self):
        g = proj("G", "某集团", "consolidated", ultimate="G")
        d = proj("D", "丁公司", parent="NOPE", ultimate="G", relation="subsidiary")
        forest = build_forest([g, d])
        n = node(forest, "D")
        assert n["isDetached"] and "detached" in n["flags"]
        assert child_codes(node(forest, "G")) == ["D"]

    def test_cycle_is_broken_deterministically(self):
        g = proj("G", "某集团", "consolidated", ultimate="G")
        a = proj("A", "甲公司", parent="B", ultimate="G", relation="subsidiary")
        b = proj("B", "乙公司", parent="A", ultimate="G", relation="subsidiary")
        forest = build_forest([g, a, b])
        breaker = node(forest, "A")  # 环内代码最小者断开上级边
        assert breaker["isCycleBreak"] and "cycle_break" in breaker["flags"]
        assert child_codes(node(forest, "G")) == ["A"] and child_codes(breaker) == ["B"]

    def test_controller_without_project_groups_top_level_entities(self):
        """控制方本年度没有项目：同一控制方的顶层企业合成一棵无根树，树名取填写的控制方名称。"""
        a = proj("A", "甲公司", ultimate="U", ultimate_company_name="某控股集团")
        b = proj("B", "乙公司", ultimate="U", ultimate_company_name="某控股集团")
        forest = build_forest([a, b])
        [tree] = forest["trees"]
        assert (tree["ultimateCode"], tree["ultimateName"], tree["rootProjectId"]) == ("U", "某控股集团", None)
        # 同级按（名称, 代码）排序，与合并树一致（「乙」码位小于「甲」）
        assert [c["companyCode"] for c in tree["children"]] == ["B", "A"]

    def test_independent_and_missing_code(self):
        solo = proj("S", "独立企业")
        blank = proj("", "无代码企业", tag="blank")
        forest = build_forest([solo, blank])
        assert forest["trees"] == []
        by_name = {n["companyName"]: n for n in forest["independents"]}
        assert by_name["独立企业"]["isIndependent"] and not by_name["独立企业"]["hasNoCompanyCode"]
        assert by_name["无代码企业"]["hasNoCompanyCode"]


# ─────────────────────────────── 报表类型筛选 / 可见性标记 ───────────────────────────────


class TestScopeAndVisibility:
    def test_scope_filter_promotes_descendants_with_via(self):
        """只看合并项目：中间企业 M 只有单户项目 ⇒ 被筛掉，其下级合并企业接到 G 下并记 via=M，而不是标脱挂。"""
        g = proj("G", "某集团", "consolidated", ultimate="G")
        m = proj("M", "中间控股", parent="G", ultimate="G", relation="subsidiary")
        n_c = proj("N", "孙公司", "consolidated", parent="M", ultimate="G", relation="subsidiary")
        s = proj("S", "乙公司", parent="G", ultimate="G", relation="subsidiary")
        forest = build_forest([g, m, n_c, s], scope="consolidated")
        root = node(forest, "G")
        assert child_codes(root) == ["N"]
        grandchild = node(forest, "N")
        assert grandchild["via"] == [{"companyCode": "M", "companyName": "中间控股"}]
        assert not grandchild["isDetached"]
        assert all(n["reportScope"] == "consolidated" for n in all_nodes(forest))

    def test_scope_filter_root_without_matching_project(self):
        """树头企业没有该口径项目 ⇒ 树名仍是它、根项目为空，下级直接挂树上（它就是树头，不再记进 via）。"""
        g = proj("G", "某集团", ultimate="G")
        a = proj("A", "甲公司", "consolidated", parent="G", ultimate="G", relation="subsidiary")
        forest = build_forest([g, a], scope="consolidated")
        [tree] = forest["trees"]
        assert (tree["ultimateCode"], tree["ultimateName"], tree["rootProjectId"]) == ("G", "某集团", None)
        [top] = tree["children"]
        assert top["companyCode"] == "A" and top["via"] == [] and not top["isDetached"]

    def test_scope_filter_keeps_only_matching_projects_of_entity(self):
        g_c = proj("G", "某集团", "consolidated", ultimate="G")
        g_s = proj("G", "某集团", ultimate="G")
        forest = build_forest([g_c, g_s], scope="standalone")
        root = node(forest, "G")
        assert [p["id"] for p in root["projects"]] == [str(g_s.id)]
        assert forest["trees"][0]["rootProjectId"] == str(g_s.id)

    def test_unknown_scope_yields_empty_forest(self):
        assert build_forest([proj("G", "某集团")], scope="xyz") == {"trees": [], "independents": []}

    def test_hidden_parent_is_not_detached(self):
        """可见性过滤后上级不在结果里、但它本年度确有项目 ⇒ 标「上级不可见」，不标脱挂。"""
        a = proj("A", "甲公司", parent="G", ultimate="G", relation="subsidiary")
        forest = build_forest([a], existing_codes={Y: {"G", "A"}})
        n = node(forest, "A")
        assert not n["isDetached"] and "parent_hidden" in n["flags"] and "detached" not in n["flags"]
        truly = build_forest([a], existing_codes={Y: {"A"}})
        assert node(truly, "A")["isDetached"], "上级确实没建项才是脱挂"


# ─────────────────────────────── 属性（hypothesis） ───────────────────────────────


_CODES = ["G", "A", "B", "C", "D"]


@st.composite
def _world(draw):
    items = []
    for i, code in enumerate(_CODES):
        for scope in draw(st.sets(st.sampled_from(["consolidated", "standalone"]), min_size=1, max_size=2)):
            year = draw(st.sampled_from([2024, 2025, None]))
            parent = draw(st.sampled_from([None, code, *_CODES[:i], "NOPE"]))
            items.append(proj(
                code, f"企业{code}", scope, parent=parent,
                ultimate=draw(st.sampled_from([None, "G", "U"])),
                relation=draw(st.sampled_from([None, "subsidiary", "branch"])) if parent else None,
                year=year, tag=f"{code}/{scope}/{year}",
            ))
    return items, draw(st.randoms(use_true_random=False))


@settings(max_examples=5, deadline=None)
@given(_world(), st.sampled_from([None, "consolidated", "standalone"]))
def test_property_order_independent_and_each_project_once(world, scope):
    """任意排列同一输入 ⇒ 森林完全相同；每个（符合筛选的）项目恰出现一次；同一（企业, 年度）只有一个节点。"""
    items, rnd = world
    shuffled = items[:]
    rnd.shuffle(shuffled)
    forest = build_forest(items, scope=scope)
    assert forest == build_forest(shuffled, scope=scope)

    expected = sorted(str(p.id) for p in items if scope is None or p.report_scope == scope)
    assert project_ids(forest) == expected
    keys = [(n["companyCode"], n["year"]) for n in all_nodes(forest)]
    assert len(keys) == len(set(keys))
    for t in forest["trees"]:
        assert {n["year"] for n in walk(t["children"])} == {t["year"]}, "一棵树只含一个年度"


def test_order_independence_smoke():
    """确定性回归：固定一组含冲突、断环、脱挂的输入，多次随机排列结果不变。"""
    items = [
        proj("G", "某集团", "consolidated", ultimate="G"), proj("G", "某集团", ultimate="G"),
        proj("A", "甲公司", parent="B", ultimate="G", relation="subsidiary"),
        proj("B", "乙公司", parent="A", ultimate="G", relation="branch"),
        proj("D", "丁公司", parent="NOPE", ultimate="G"), proj("S", "独立企业"),
    ]
    base = build_forest(items)
    for seed in range(20):
        shuffled = items[:]
        random.Random(seed).shuffle(shuffled)
        assert build_forest(shuffled) == base
