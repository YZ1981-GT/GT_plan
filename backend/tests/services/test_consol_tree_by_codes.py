"""group-tree-architecture Task 1.1 — build_tree_by_codes 纯逻辑单元测试

验证 build_group_trees_from_projects（build_tree_by_codes 的纯函数核心）：
- 空列表 → 空森林
- 单集团简单层级 → 正确父子关系
- 脱挂节点（parent 指向不存在）→ isDetached
- 独立节点（company_code 空 / ultimate 空）→ independents
- 循环引用 → 打断 + isCycleBreak
- 年度过滤

不依赖 DB（build_tree_by_codes 的 DB 查询部分在端点集成测试覆盖）。

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.consol_tree_service import build_group_trees_from_projects


def _proj(
    company_code,
    *,
    ultimate=None,
    parent=None,
    name=None,
    period_end=None,
    report_scope=None,
    status="created",
):
    """构造 Project-like 对象（build_group_trees_from_projects 仅访问属性）。"""
    return SimpleNamespace(
        id=uuid4(),
        company_code=company_code,
        client_name=name or (company_code or "无名"),
        parent_company_code=parent,
        ultimate_company_code=ultimate,
        consol_level=1,
        audit_period_end=period_end,
        report_scope=report_scope,
        status=status,
    )


def _find_node(nodes, company_code):
    """在 to_dict_v2 节点列表中递归查找 companyCode 匹配的节点。"""
    for n in nodes:
        if n["companyCode"] == company_code:
            return n
        found = _find_node(n["children"], company_code)
        if found:
            return found
    return None


def test_empty_list_returns_empty_forest():
    result = build_group_trees_from_projects([])
    assert result["trees"] == []
    assert result["independents"] == []


def test_single_group_simple_hierarchy():
    """ROOT(ultimate) → SUB1 → SUB2 正确嵌套。"""
    projects = [
        _proj("ROOT0000000000000A", ultimate="ROOT0000000000000A", name="集团母公司"),
        _proj("SUB10000000000000A", ultimate="ROOT0000000000000A", parent="ROOT0000000000000A", name="子公司1"),
        _proj("SUB20000000000000A", ultimate="ROOT0000000000000A", parent="SUB10000000000000A", name="子公司2"),
    ]
    result = build_group_trees_from_projects(projects)

    assert len(result["trees"]) == 1
    tree = result["trees"][0]
    assert tree["ultimateCode"] == "ROOT0000000000000A"
    assert tree["ultimateName"] == "集团母公司"

    # 根节点是唯一顶层 children
    assert len(tree["children"]) == 1
    root = tree["children"][0]
    assert root["companyCode"] == "ROOT0000000000000A"

    # SUB1 挂根下
    sub1 = _find_node([root], "SUB10000000000000A")
    assert sub1 is not None
    # SUB2 挂 SUB1 下
    sub2 = _find_node(sub1["children"], "SUB20000000000000A")
    assert sub2 is not None


def test_detached_node_when_parent_missing():
    """parent 指向组内不存在的企业 → isDetached 挂 ultimate 根下。"""
    projects = [
        _proj("ROOT0000000000000A", ultimate="ROOT0000000000000A", name="母公司"),
        _proj("ORPHAN000000000A", ultimate="ROOT0000000000000A", parent="NONEXIST00000000A", name="孤儿"),
    ]
    result = build_group_trees_from_projects(projects)

    root = result["trees"][0]["children"][0]
    orphan = _find_node([root], "ORPHAN000000000A")
    assert orphan is not None
    assert orphan["isDetached"] is True
    # 应是根的直接子节点
    assert any(c["companyCode"] == "ORPHAN000000000A" for c in root["children"])


def test_independent_when_ultimate_empty():
    """ultimate_company_code 为空 → 独立分组，不进 trees。"""
    projects = [
        _proj("SOLO0000000000000A", ultimate=None, name="独立企业"),
    ]
    result = build_group_trees_from_projects(projects)

    assert result["trees"] == []
    assert len(result["independents"]) == 1
    node = result["independents"][0]
    assert node["companyCode"] == "SOLO0000000000000A"
    assert node["isIndependent"] is True


def test_independent_when_company_code_empty():
    """company_code 为空 → 排除出树，进独立分组 hasNoCompanyCode。"""
    projects = [
        _proj("", ultimate="ROOT0000000000000A", name="无代码企业"),
    ]
    result = build_group_trees_from_projects(projects)

    assert result["trees"] == []
    assert len(result["independents"]) == 1
    node = result["independents"][0]
    assert node["hasNoCompanyCode"] is True
    assert node["isIndependent"] is True


def test_cycle_detection_breaks_and_marks():
    """A→B→C→A 循环 → 终止 + 至少一个 isCycleBreak。"""
    projects = [
        _proj("ROOT0000000000000A", ultimate="ROOT0000000000000A", name="根"),
        _proj("AAAA0000000000000A", ultimate="ROOT0000000000000A", parent="CCCC0000000000000A", name="A"),
        _proj("BBBB0000000000000A", ultimate="ROOT0000000000000A", parent="AAAA0000000000000A", name="B"),
        _proj("CCCC0000000000000A", ultimate="ROOT0000000000000A", parent="BBBB0000000000000A", name="C"),
    ]
    # 不应挂起；应正常返回
    result = build_group_trees_from_projects(projects)

    root = result["trees"][0]["children"][0]
    cycle_nodes = []
    for code in ("AAAA0000000000000A", "BBBB0000000000000A", "CCCC0000000000000A"):
        n = _find_node([root], code)
        if n is not None and n["isCycleBreak"]:
            cycle_nodes.append(code)
    assert len(cycle_nodes) >= 1


def test_year_filtering_isolation():
    """指定年份只含该年份项目。"""
    projects = [
        _proj("AAAA0000000000000A", ultimate="AAAA0000000000000A", name="2024企业", period_end=date(2024, 12, 31)),
        _proj("BBBB0000000000000A", ultimate="BBBB0000000000000A", name="2025企业", period_end=date(2025, 12, 31)),
    ]
    result_2025 = build_group_trees_from_projects(projects, year=2025)

    assert len(result_2025["trees"]) == 1
    assert result_2025["trees"][0]["ultimateCode"] == "BBBB0000000000000A"


def test_ultimate_grouping_invariant():
    """不同 ultimate → 不同树，互不混入。"""
    projects = [
        _proj("G1ROOT00000000000A", ultimate="G1ROOT00000000000A", name="集团1根"),
        _proj("G1SUB000000000000A", ultimate="G1ROOT00000000000A", parent="G1ROOT00000000000A", name="集团1子"),
        _proj("G2ROOT00000000000A", ultimate="G2ROOT00000000000A", name="集团2根"),
    ]
    result = build_group_trees_from_projects(projects)

    assert len(result["trees"]) == 2
    by_code = {t["ultimateCode"]: t for t in result["trees"]}
    g1 = by_code["G1ROOT00000000000A"]
    g2 = by_code["G2ROOT00000000000A"]
    # 集团2 不含集团1的子公司
    assert _find_node(g2["children"], "G1SUB000000000000A") is None
    assert _find_node(g1["children"], "G1SUB000000000000A") is not None


def test_node_data_preserved():
    """节点保留 companyName/status/reportScope。"""
    projects = [
        _proj("ROOT0000000000000A", ultimate="ROOT0000000000000A", name="某集团", report_scope="consolidated", status="execution"),
    ]
    result = build_group_trees_from_projects(projects)
    root = result["trees"][0]["children"][0]
    assert root["companyName"] == "某集团"
    assert root["reportScope"] == "consolidated"
    assert root["status"] == "execution"


# ===========================================================================
# Property-Based Tests (hypothesis) — Tasks 1.4–1.10
#
# build_group_trees_from_projects 是纯同步函数（无 DB、无 async），
# 故 PBT 无 fixture / HealthCheck 顾虑。统一 max_examples=5（项目铁律）。
# ===========================================================================


def _collect_tree_codes(trees):
    """收集所有 GroupTree 中所有节点的 companyCode（含根+后代）。"""
    codes = []

    def _walk(nodes):
        for n in nodes:
            codes.append(n["companyCode"])
            _walk(n["children"])

    for t in trees:
        _walk(t["children"])
    return codes


def _code(idx: int) -> str:
    """把序号映射为 18 位定长唯一代码（保证组内 company_code 唯一）。"""
    base = f"C{idx:04d}"
    return (base + "0" * 18)[:18]


# Feature: group-tree-architecture, Property 1: All valid projects appear in tree
# Validates: Requirements 1.1
@settings(max_examples=5)
@given(n=st.integers(min_value=1, max_value=6))
def test_property1_all_valid_projects_appear_exactly_once(n):
    """任意非空 company_code + 非空 ultimate 项目必出现在对应 GroupTree 中恰好一次。"""
    ultimate = _code(0)
    projects = [_proj(ultimate, ultimate=ultimate, name="根")]
    expected_codes = {ultimate}
    for i in range(1, n + 1):
        code = _code(i)
        projects.append(_proj(code, ultimate=ultimate, parent=ultimate, name=f"子{i}"))
        expected_codes.add(code)

    result = build_group_trees_from_projects(projects)
    all_codes = _collect_tree_codes(result["trees"])

    for code in expected_codes:
        assert all_codes.count(code) == 1, f"{code} 出现 {all_codes.count(code)} 次"
    assert len(all_codes) == len(expected_codes)


# Feature: group-tree-architecture, Property 2: Ultimate grouping invariant
# Validates: Requirements 1.2
@settings(max_examples=5)
@given(
    n_ultimates=st.integers(min_value=1, max_value=3),
    n_subs=st.integers(min_value=1, max_value=4),
)
def test_property2_ultimate_grouping_invariant(n_ultimates, n_subs):
    """同一 ultimate 的项目必在同一 GroupTree，不出现在其他树。"""
    projects = []
    code_to_ultimate = {}
    idx = 0
    for u in range(n_ultimates):
        ult = _code(idx)
        idx += 1
        projects.append(_proj(ult, ultimate=ult, name=f"集团{u}根"))
        code_to_ultimate[ult] = ult
        for _ in range(n_subs):
            sub = _code(idx)
            idx += 1
            projects.append(_proj(sub, ultimate=ult, parent=ult, name=f"集团{u}子"))
            code_to_ultimate[sub] = ult

    result = build_group_trees_from_projects(projects)

    for tree in result["trees"]:
        ult = tree["ultimateCode"]
        for code in _collect_tree_codes([tree]):
            assert code_to_ultimate[code] == ult, (
                f"{code}（属 {code_to_ultimate[code]}）错误出现在树 {ult} 中"
            )

    tree_ults = [t["ultimateCode"] for t in result["trees"]]
    assert len(tree_ults) == len(set(tree_ults))
    assert set(tree_ults) == set(code_to_ultimate.values())


# Feature: group-tree-architecture, Property 3: Parent-child relationship correctness
# Validates: Requirements 1.3
@settings(max_examples=5)
@given(depth=st.integers(min_value=1, max_value=5))
def test_property3_parent_child_relationship_correctness(depth):
    """parent_company_code 匹配 Q.company_code 且无循环 → P 是 Q 后代。"""
    ultimate = _code(0)
    projects = [_proj(ultimate, ultimate=ultimate, name="根")]
    chain = [ultimate]
    for i in range(1, depth + 1):
        code = _code(i)
        projects.append(_proj(code, ultimate=ultimate, parent=chain[-1], name=f"层{i}"))
        chain.append(code)

    result = build_group_trees_from_projects(projects)
    root = result["trees"][0]["children"][0]

    for i in range(1, depth + 1):
        parent_code = chain[i - 1]
        child_code = chain[i]
        parent_node = _find_node([root], parent_code)
        assert parent_node is not None
        assert _find_node(parent_node["children"], child_code) is not None, (
            f"{child_code} 不是 {parent_code} 的后代"
        )


# Feature: group-tree-architecture, Property 4: Year filtering isolation
# Validates: Requirements 1.4, 1.5
@settings(max_examples=5)
@given(
    target_year=st.integers(min_value=2020, max_value=2026),
    other_year_offset=st.integers(min_value=1, max_value=4),
)
def test_property4_year_filtering_isolation(target_year, other_year_offset):
    """指定年份构建的树只含该年份项目。"""
    other_year = target_year - other_year_offset
    target_code = _code(0)
    other_code = _code(1)
    projects = [
        _proj(target_code, ultimate=target_code, name="目标年", period_end=date(target_year, 12, 31)),
        _proj(other_code, ultimate=other_code, name="其它年", period_end=date(other_year, 12, 31)),
    ]

    result = build_group_trees_from_projects(projects, year=target_year)
    all_codes = _collect_tree_codes(result["trees"]) + [
        n["companyCode"] for n in result["independents"]
    ]

    assert target_code in all_codes
    assert other_code not in all_codes


# Feature: group-tree-architecture, Property 5: Invalid field routing to independent group
# Validates: Requirements 2.2, 2.4
@settings(max_examples=5)
@given(empty_company=st.booleans(), empty_ultimate=st.booleans())
def test_property5_invalid_field_routing_to_independent(empty_company, empty_ultimate):
    """company_code 空或 ultimate 空 → 进 independents，不在 groupTrees 中。"""
    company_code = "" if empty_company else _code(1)
    ultimate = "" if empty_ultimate else _code(0)

    valid_code = _code(9)
    projects = [
        _proj(valid_code, ultimate=valid_code, name="有效"),
        _proj(company_code, ultimate=ultimate or None, name="待检"),
    ]

    result = build_group_trees_from_projects(projects)
    tree_codes = _collect_tree_codes(result["trees"])
    independent_codes = [n["companyCode"] for n in result["independents"]]

    if empty_company or empty_ultimate:
        assert company_code in independent_codes
        assert company_code not in tree_codes
    else:
        # 两者都非空 → 有效项目，进树不进 independents
        assert company_code in tree_codes
        assert company_code not in independent_codes


# Feature: group-tree-architecture, Property 6: Detached node handling
# Validates: Requirements 2.1
@settings(max_examples=5)
@given(n_detached=st.integers(min_value=1, max_value=4))
def test_property6_detached_node_handling(n_detached):
    """parent 指向不存在企业 → isDetached=true 且为 ultimate 根直接子节点。"""
    ultimate = _code(0)
    projects = [_proj(ultimate, ultimate=ultimate, name="根")]
    detached_codes = []
    for i in range(1, n_detached + 1):
        code = _code(i)
        missing_parent = _code(900 + i)  # 保证组内不存在
        projects.append(_proj(code, ultimate=ultimate, parent=missing_parent, name=f"脱挂{i}"))
        detached_codes.append(code)

    result = build_group_trees_from_projects(projects)
    root = result["trees"][0]["children"][0]
    root_child_codes = {c["companyCode"] for c in root["children"]}

    for code in detached_codes:
        node = _find_node([root], code)
        assert node is not None
        assert node["isDetached"] is True, f"{code} 应标记 isDetached"
        assert code in root_child_codes, f"{code} 应为根直接子节点"


# Feature: group-tree-architecture, Property 7: Cycle detection terminates and marks
# Validates: Requirements 2.3
@settings(max_examples=5, deadline=None)
@given(cycle_len=st.integers(min_value=2, max_value=4))
def test_property7_cycle_detection_terminates_and_marks(cycle_len):
    """循环引用 → 函数终止（不挂起）+ 至少一个 isCycleBreak=true。"""
    ultimate = _code(0)
    projects = [_proj(ultimate, ultimate=ultimate, name="根")]
    # 构造闭环：c0.parent=c{last}, c1.parent=c0, ..., c{last}.parent=c{last-1}
    cycle_codes = [_code(i) for i in range(1, cycle_len + 1)]
    for i, code in enumerate(cycle_codes):
        parent = cycle_codes[i - 1] if i > 0 else cycle_codes[-1]
        projects.append(_proj(code, ultimate=ultimate, parent=parent, name=f"环{i}"))

    # 不应挂起；正常返回
    result = build_group_trees_from_projects(projects)
    root = result["trees"][0]["children"][0]

    cycle_break_count = 0
    for code in cycle_codes:
        n = _find_node([root], code)
        if n is not None and n["isCycleBreak"]:
            cycle_break_count += 1
    assert cycle_break_count >= 1, "环中应至少有一个节点被标记 isCycleBreak"
