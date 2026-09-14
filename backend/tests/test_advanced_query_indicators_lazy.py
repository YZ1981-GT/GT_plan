"""指标树懒加载守卫（R12）。

Feature: advanced-query-hardening-wiring-closure

**存在理由（浏览器实测）**：`GET /api/custom-query/indicators` 单次返回 9 大类完整树，
实测约 **578,057 字符 / 3,089 节点 / 2,766 叶子**，慢请求监控记录 **3,391ms**；
其中绝大部分来自底稿树（全部 wp_code × 全部 sheet）与附注树（全部章节）。

判据要求（R12.5）：首屏收敛必须由**可执行判据度量**而非目视 —— 故本文件直接比较
骨架与全量的节点数/序列化体积，并断言收敛比达到明确阈值。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.routers.custom_query as router_module
from app.routers.custom_query import (
    LAZY_INDICATOR_BRANCHES,
    _INDICATORS_SCHEMA_VERSION,
)

#: 骨架相对全量的节点数上限（骨架必须显著小于全量）
SKELETON_NODE_RATIO_MAX = 0.25

USER = SimpleNamespace(id="u1", role=SimpleNamespace(value="admin"))


def _count_nodes(nodes) -> int:
    total = 0
    for node in nodes or []:
        total += 1
        total += _count_nodes(node.get("children"))
    return total


def _payload_size(nodes) -> int:
    return len(json.dumps(nodes, ensure_ascii=False))


@pytest.fixture
def stub_trees(monkeypatch):
    """把三个重量级建树函数换成可控替身，使判据与真实数据量无关。"""
    # 替身规模与「节点密度」都贴近真实观测值：真实全量约 578,057 字符 / 3,089 节点
    # ≈ 187 字符/节点。若替身节点过于轻薄，骨架里轻量大类的固定成本（每个叶子都带
    # columns）会把体积收敛比抬高，判据就失去意义 —— 那时该修替身而不是放宽阈值。
    _LEAF_COLUMNS = [
        "row_code",
        "row_name",
        "current_period_amount",
        "prior_period_amount",
        "account_code",
        "account_name",
    ]
    disclosure = [
        {
            "key": f"disclosure_note:section-{i}",
            "label": f"附注章节 {i} —— 合并财务报表项目注释",
            "columns": list(_LEAF_COLUMNS),
        }
        for i in range(40)
    ]
    workpaper = [
        {
            "key": f"cycle_{c}",
            "label": f"循环{c}",
            "children": [
                {
                    "key": f"workpaper:{c}{i}",
                    "label": f"{c}{i} 审定表",
                    "children": [
                        {
                            "key": f"workpaper:{c}{i}|sheet-{j}",
                            "label": f"{c}{i} 工作表 {j}",
                            "columns": list(_LEAF_COLUMNS),
                            "ancestorKeys": [f"cycle_{c}", f"workpaper:{c}{i}"],
                        }
                        for j in range(3)
                    ],
                }
                for i in range(10)
            ],
        }
        for c in ("A", "B", "C")
    ]

    async def _disclosure(template_type):
        return [dict(x) for x in disclosure]

    async def _workpaper(db, project_id):
        return [dict(x) for x in workpaper]

    async def _consol(db, project_id):
        return None

    async def _template_type(db, project_id):
        return "soe"

    monkeypatch.setattr(router_module, "_build_disclosure_tree", _disclosure)
    monkeypatch.setattr(router_module, "_build_workpaper_tree", _workpaper)
    monkeypatch.setattr(router_module, "_build_consol_units_tree", _consol)
    monkeypatch.setattr(router_module, "_resolve_project_template_type", _template_type)
    return SimpleNamespace(disclosure=disclosure, workpaper=workpaper)


async def _indicators(**kwargs):
    params = {
        "project_id": None,
        "depth": None,
        "branch": None,
        "response": None,
        "db": object(),
        "current_user": USER,
    }
    params.update(kwargs)
    return await router_module.get_indicators(**params)


class TestIndicatorsSkeleton:
    @pytest.mark.asyncio
    async def test_depth1_skeleton_is_significantly_smaller(self, stub_trees):
        """R12.1 / R12.5：骨架节点数与体积都必须显著小于全量。"""
        full = await _indicators()
        skeleton = await _indicators(depth=1)

        full_nodes = _count_nodes(full)
        skel_nodes = _count_nodes(skeleton)
        assert skel_nodes < full_nodes * SKELETON_NODE_RATIO_MAX, (
            f"骨架 {skel_nodes} 节点 / 全量 {full_nodes} 节点，收敛比不足"
        )
        assert _payload_size(skeleton) < _payload_size(full) * SKELETON_NODE_RATIO_MAX

    @pytest.mark.asyncio
    async def test_skeleton_keeps_all_top_level_categories(self, stub_trees):
        """骨架不能丢大类 —— 用户要能看到全部入口，只是子节点按需加载。"""
        full = await _indicators()
        skeleton = await _indicators(depth=1)
        assert [n["key"] for n in skeleton] == [n["key"] for n in full]

    @pytest.mark.asyncio
    async def test_lazy_branches_marked_and_emptied(self, stub_trees):
        """重分支在骨架中 children 为空且标 lazy=True。"""
        skeleton = {n["key"]: n for n in await _indicators(depth=1)}
        for key in LAZY_INDICATOR_BRANCHES:
            assert key in skeleton, f"骨架缺大类 {key}"
            assert skeleton[key]["children"] == []
            assert skeleton[key]["lazy"] is True

    @pytest.mark.asyncio
    async def test_light_categories_stay_inline_in_skeleton(self, stub_trees):
        """轻量大类（试算/调整/工时等）仍内联 —— 为它们再发一次请求不值得。"""
        skeleton = {n["key"]: n for n in await _indicators(depth=1)}
        for key in ("trial_balance", "adjustment", "worksheet", "workhours"):
            assert skeleton[key]["children"], f"{key} 不应被懒加载"

    @pytest.mark.asyncio
    async def test_full_tree_marks_lazy_false(self, stub_trees):
        """全量模式下 lazy=False，前端据此决定是否注册 load 回调。"""
        full = {n["key"]: n for n in await _indicators()}
        for key in LAZY_INDICATOR_BRANCHES:
            assert full[key]["lazy"] is False
            assert full[key]["children"], f"全量模式 {key} 应内联子节点"

    @pytest.mark.asyncio
    async def test_omitting_depth_keeps_backward_compatible_full_tree(self, stub_trees):
        """不传 depth 时行为与改造前一致（懒加载是 opt-in）。"""
        full = await _indicators()
        disclosure = next(n for n in full if n["key"] == "disclosure")
        assert len(disclosure["children"]) == 40


class TestIndicatorsBranch:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("branch,expected", [("disclosure", 40), ("workpaper", 3)])
    async def test_branch_returns_only_that_subtree(self, stub_trees, branch, expected):
        """R12.2：展开某分支只加载该分支子节点。"""
        children = await _indicators(branch=branch)
        assert isinstance(children, list)
        assert len(children) == expected

    @pytest.mark.asyncio
    async def test_branch_payload_smaller_than_full_tree(self, stub_trees):
        """单分支响应必须小于全量树，否则懒加载没有意义。"""
        full = await _indicators()
        branch = await _indicators(branch="workpaper")
        assert _payload_size(branch) < _payload_size(full)

    @pytest.mark.asyncio
    async def test_unknown_branch_returns_400_not_empty(self, stub_trees):
        """未知分支 400 而非空数组 —— 静默空会让「参数写错」看起来像「没有数据」。"""
        with pytest.raises(HTTPException) as exc:
            await _indicators(branch="not_a_branch")
        assert exc.value.status_code == 400
        assert exc.value.detail["error_code"] == "UNKNOWN_INDICATOR_BRANCH"
        assert exc.value.detail["allowed"] == list(LAZY_INDICATOR_BRANCHES)

    @pytest.mark.asyncio
    async def test_branch_request_still_requires_ownership(self, monkeypatch, stub_trees):
        """分支加载不得绕过归属校验（R1.2 对新参数同样成立）。"""
        from app.services.custom_query.ownership_guard import ownership_guard

        called: list[str] = []

        async def _guard(*, user, project_id, db):
            called.append(str(project_id))
            raise HTTPException(
                status_code=403, detail={"error_code": "FORBIDDEN_PROJECT"}
            )

        monkeypatch.setattr(ownership_guard, "assert_target_accessible", _guard)
        with pytest.raises(HTTPException) as exc:
            await _indicators(project_id="p-forbidden", branch="workpaper")
        assert exc.value.status_code == 403
        assert called == ["p-forbidden"]


class TestDirectCallCompatibility:
    """端点被直调（不经 FastAPI 依赖注入）时新参数不得误判。

    🔴 锁死一个实际踩到的坑：未传的 `Query(default=None)` 参数在直调时保留的是
    **`Query` 实例**而非 None，`if branch:` 会恒为真 —— 表现为「不传 branch 却报
    UNKNOWN_INDICATOR_BRANCH」，把既有契约测试打红。故须按真实类型判断。
    """

    @pytest.mark.asyncio
    async def test_query_object_defaults_treated_as_absent(self, stub_trees):
        """模拟直调：显式传入 Query 实例默认值，应等价于「未提供」。"""
        from fastapi import Query as FastApiQuery

        tree = await router_module.get_indicators(
            project_id=None,
            depth=FastApiQuery(default=None, ge=1, le=9),
            branch=FastApiQuery(default=None),
            response=None,
            db=object(),
            current_user=USER,
        )
        # 未提供 branch → 返回完整大类列表而非分支子节点
        assert isinstance(tree, list)
        keys = [n["key"] for n in tree]
        assert "workpaper" in keys and "disclosure" in keys
        # 未提供 depth → 全量（非骨架）
        disclosure = next(n for n in tree if n["key"] == "disclosure")
        assert disclosure["children"], "未提供 depth 时不应返回骨架"

    @pytest.mark.asyncio
    async def test_omitted_kwargs_signature_still_works(self, stub_trees):
        """既有调用方只传 4 个关键字参数时仍可用（向后兼容）。"""
        tree = await router_module.get_indicators(
            project_id=None, response=None, db=object(), current_user=USER
        )
        assert isinstance(tree, list) and tree


class TestIndicatorsSchemaVersion:
    def test_schema_version_bumped_for_lazy_fields(self):
        """R12.3：新增 lazy 字段必须升 schema 版本，否则前端旧缓存不失效。"""
        assert _INDICATORS_SCHEMA_VERSION >= 10

    @pytest.mark.asyncio
    async def test_version_header_emitted(self, stub_trees):
        from fastapi import Response

        class _Registry:
            async def get_max_version(self, db):
                return 0

        import app.routers.custom_query as rm

        original = rm.wp_template_registry_service
        rm.wp_template_registry_service = _Registry()
        try:
            resp = Response()
            await _indicators(depth=1, response=resp)
            assert resp.headers["X-Indicators-Schema-Version"] == str(
                _INDICATORS_SCHEMA_VERSION
            )
        finally:
            rm.wp_template_registry_service = original
