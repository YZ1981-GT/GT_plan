"""audit-check-review-gate-hardening Task 2.5 — summary 契约与权限测试

`GET /api/projects/{pid}/audit-checks/summary`（`get_audit_checks_summary`）的
**契约稳定性** 与 **权限门控** 两维度，与 Task 2.3 的行为测试
（`test_audit_check_summary_endpoint.py`）互补，不重复具体行为断言。

契约（Req1.4 / 5.3）：
- 顶层结构恒为 `{"summary": {...}, "workpapers": [...]}`。
- `summary` 字段集合恒定且类型正确（total/decided/passed/failed/uncovered 为 int，
  pass_rate 为 float|None，blocking_open 为 int）。
- 每个 workpaper 项字段集合恒定齐全（wp_id/wp_code/wp_name/audit_cycle/checks/
  checked_at/updated_at/stale/never_checked）。
- 用多种底稿组合（新字段 / 空列表 / legacy 退回 / parsed_data 为 None / 混合判定）
  断言字段集合**恒定不缺失** —— 契约测试重点是「字段齐全不缺失」。

权限（Req10.1 / P12）：
- summary 端点依赖为**项目只读级** `require_project_access("readonly")`，
  经 inspect 端点依赖的闭包捕获值验证（真实反映权限级别，非源码字符串匹配即可，
  两路并用防伪造通过）。
- 端点为 GET，无写副作用（不改 `parsed_data` / 不 flush / 不 commit / 不 add /
  不 delete）—— 静态检查端点源码 + 行为检查 mock db 的 flush/commit/add 未被调用。
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.deps import require_project_access
from app.routers.audit_check import get_audit_checks_summary, router


# ═══════════════════════════════════════════════════════════════════
# 契约字段常量（单一真源；design §3/§4 + ProjectCheckSummary）
# ═══════════════════════════════════════════════════════════════════

TOP_LEVEL_KEYS = {"summary", "workpapers"}

SUMMARY_KEYS = {
    "total", "decided", "passed", "failed",
    "uncovered", "pass_rate", "blocking_open",
}

WORKPAPER_KEYS = {
    "wp_id", "wp_code", "wp_name", "audit_cycle", "checks",
    "checked_at", "updated_at", "stale", "never_checked",
}

# summary 中恒为 int 的计数字段（pass_rate 单独为 float|None）
SUMMARY_INT_KEYS = {
    "total", "decided", "passed", "failed", "uncovered", "blocking_open",
}


# ═══════════════════════════════════════════════════════════════════
# mock db（对齐 summary 端点 select 列顺序，只读）
# ═══════════════════════════════════════════════════════════════════

def _make_db(rows: list[tuple]):
    """mock AsyncSession；`db.execute(...)` 的 .all() 返回给定 rows。

    每 row 为 6-tuple：(wp_id, parsed_data, updated_at, wp_code, wp_name, audit_cycle)。
    flush/commit/add/delete 保持默认 mock（供「未被调用」断言）。
    """
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute.return_value = result
    return db


async def _call(rows):
    db = _make_db(rows)
    res = await get_audit_checks_summary(project_id=uuid4(), db=db, current_user=None)
    return res, db


def _now():
    return datetime.now(timezone.utc)


def _audit_check(passed, severity="info"):
    return {
        "code": f"C-{uuid4().hex[:6]}",
        "source": "cycle_recon",
        "wp_code": "E1",
        "severity": severity,
        "check_type": "reconciliation",
        "passed": passed,
        "message": "",
        "produced_at": _now().isoformat(),
    }


def _wp_row(*, parsed_data, wp_code="E1", wp_name="货币资金", cycle="E", updated=None):
    return (uuid4(), parsed_data, updated or _now(), wp_code, wp_name, cycle)


# 覆盖多种底稿组合（契约字段集合应恒定不缺失）
def _varied_rows():
    return [
        # 1. 空 parsed_data（未检查底稿）
        _wp_row(parsed_data={}, wp_code="D2", wp_name="应收账款", cycle="D"),
        # 2. parsed_data 为 None
        _wp_row(parsed_data=None, wp_code="K9", wp_name="管理费用", cycle="K"),
        # 3. audit_checks 空列表（新字段分支）
        _wp_row(parsed_data={"audit_checks": [], "audit_checks_at": _now().isoformat()},
                wp_code="M1", wp_name="实收资本", cycle="M"),
        # 4. audit_checks 混合判定（passed True/False/None + blocking）
        _wp_row(parsed_data={
            "audit_checks": [
                _audit_check(True),
                _audit_check(False, severity="blocking"),
                _audit_check(None),
            ],
            "audit_checks_at": _now().isoformat(),
        }, wp_code="N2", wp_name="应交税费", cycle="N"),
        # 5. legacy fine_checks 退回（无 audit_checks）
        _wp_row(parsed_data={
            "fine_checks": [{"code": "E1-CHK-01", "type": "balance",
                             "severity": "blocking", "passed": True, "message": ""}],
            "fine_extracted_at": (_now() - timedelta(hours=1)).isoformat(),
        }, wp_code="E1", wp_name="货币资金", cycle="E"),
    ]


# ═══════════════════════════════════════════════════════════════════
# 契约：顶层结构（Req1.4 / 5.3）
# ═══════════════════════════════════════════════════════════════════

class TestTopLevelContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_constant(self):
        """顶层结构恒为 {"summary":{...}, "workpapers":[...]}（非空项目）。"""
        result, _ = await _call(_varied_rows())
        assert set(result.keys()) == TOP_LEVEL_KEYS
        assert isinstance(result["summary"], dict)
        assert isinstance(result["workpapers"], list)

    @pytest.mark.asyncio
    async def test_top_level_keys_constant_empty_project(self):
        """空项目（无底稿）顶层结构不变，workpapers 为空列表。"""
        result, _ = await _call([])
        assert set(result.keys()) == TOP_LEVEL_KEYS
        assert result["workpapers"] == []
        # 空项目 summary 仍字段齐全
        assert set(result["summary"].keys()) == SUMMARY_KEYS


# ═══════════════════════════════════════════════════════════════════
# 契约：summary 字段集合 + 类型（Req5.3）
# ═══════════════════════════════════════════════════════════════════

class TestSummaryContract:
    @pytest.mark.asyncio
    async def test_summary_field_set_constant(self):
        """summary 字段集合恒定齐全，跨多种底稿组合不变。"""
        result, _ = await _call(_varied_rows())
        assert set(result["summary"].keys()) == SUMMARY_KEYS

    @pytest.mark.asyncio
    async def test_summary_count_fields_are_int(self):
        """计数字段恒为 int（total/decided/passed/failed/uncovered/blocking_open）。"""
        result, _ = await _call(_varied_rows())
        s = result["summary"]
        for k in SUMMARY_INT_KEYS:
            assert isinstance(s[k], int), f"{k} 应为 int，实际 {type(s[k])}"

    @pytest.mark.asyncio
    async def test_pass_rate_type_float_when_decided(self):
        """有已判定项时 pass_rate 为 float（非 bool，且分母不含 null）。"""
        result, _ = await _call(_varied_rows())
        pr = result["summary"]["pass_rate"]
        assert isinstance(pr, float)
        assert not isinstance(pr, bool)
        assert 0.0 <= pr <= 1.0

    @pytest.mark.asyncio
    async def test_pass_rate_none_when_no_decided(self):
        """无已判定项（全未检查/全 uncovered）时 pass_rate 为 None，字段仍在。"""
        rows = [
            _wp_row(parsed_data={}, wp_code="D2", cycle="D"),
            _wp_row(parsed_data={
                "audit_checks": [_audit_check(None)],
                "audit_checks_at": _now().isoformat(),
            }, wp_code="E1", cycle="E"),
        ]
        result, _ = await _call(rows)
        assert "pass_rate" in result["summary"]
        assert result["summary"]["pass_rate"] is None


# ═══════════════════════════════════════════════════════════════════
# 契约：workpaper 项字段集合恒定（跨组合不缺失）
# ═══════════════════════════════════════════════════════════════════

class TestWorkpaperEntryContract:
    @pytest.mark.asyncio
    async def test_every_workpaper_entry_field_set_constant(self):
        """每个 workpaper 项字段集合恒等于 WORKPAPER_KEYS，无论 parsed_data 形态。"""
        result, _ = await _call(_varied_rows())
        assert len(result["workpapers"]) == 5
        for wp in result["workpapers"]:
            assert set(wp.keys()) == WORKPAPER_KEYS, (
                f"{wp.get('wp_code')} 字段集合不符：{set(wp.keys()) ^ WORKPAPER_KEYS}"
            )

    @pytest.mark.asyncio
    async def test_workpaper_field_types(self):
        """workpaper 项字段类型契约：checks 为 list、stale/never_checked 为 bool、
        checked_at/updated_at 为 str|None。"""
        result, _ = await _call(_varied_rows())
        for wp in result["workpapers"]:
            assert isinstance(wp["checks"], list)
            assert isinstance(wp["stale"], bool)
            assert isinstance(wp["never_checked"], bool)
            assert wp["checked_at"] is None or isinstance(wp["checked_at"], str)
            assert wp["updated_at"] is None or isinstance(wp["updated_at"], str)
            assert isinstance(wp["wp_id"], str)

    @pytest.mark.asyncio
    async def test_checks_items_carry_source(self):
        """契约稳定：每个 check 项（含 legacy 退回）都带非空 source（P9 前端渲染依赖）。"""
        result, _ = await _call(_varied_rows())
        for wp in result["workpapers"]:
            for chk in wp["checks"]:
                assert chk.get("source"), f"{wp['wp_code']} 的 check 缺 source"


# ═══════════════════════════════════════════════════════════════════
# 权限：项目只读级 require_project_access("readonly")（Req10.1 / P12）
# ═══════════════════════════════════════════════════════════════════

class TestPermissionGate:
    def test_summary_uses_require_project_access(self):
        """current_user 依赖为 require_project_access 工厂产出（有 .dependency）。"""
        sig = inspect.signature(get_audit_checks_summary)
        assert "current_user" in sig.parameters
        dep = sig.parameters["current_user"].default
        assert dep is not None, "current_user 应有 Depends 默认值"
        assert hasattr(dep, "dependency"), "应为 Depends(...)"

    def test_summary_permission_level_is_readonly(self):
        """真实验证权限级别为 readonly：inspect 依赖闭包捕获的 min_permission。

        `require_project_access(min_permission)` 内部 `dependency` 闭包捕获 `min_permission`，
        经 `__closure__` 读取真实捕获值（"readonly"），不放宽为 edit/review/无鉴权，
        非仅源码字符串匹配 —— 真实反映权限门控。
        """
        sig = inspect.signature(get_audit_checks_summary)
        dep = sig.parameters["current_user"].default
        inner = dep.dependency  # require_project_access 返回的 dependency 闭包
        freevars = inner.__code__.co_freevars
        assert "min_permission" in freevars, (
            "依赖应为 require_project_access 闭包（捕获 min_permission）"
        )
        idx = freevars.index("min_permission")
        captured = inner.__closure__[idx].cell_contents
        assert captured == "readonly", (
            f"summary 权限级别应为 readonly（最低只读级），实际捕获 {captured!r}"
        )

    def test_readonly_is_lowest_level_not_bypassed(self):
        """交叉验证：readonly 是最低只读级（PERMISSION_HIERARCHY 最小非零），
        且端点确实绑定了鉴权依赖（非无鉴权放宽）。"""
        from app.deps import PERMISSION_HIERARCHY

        assert PERMISSION_HIERARCHY["readonly"] == min(PERMISSION_HIERARCHY.values())
        # 与源码级断言并用，防伪造通过
        src = inspect.getsource(get_audit_checks_summary)
        assert 'require_project_access("readonly")' in src
        # 不得放宽为更高权限或去鉴权
        assert 'require_project_access("edit")' not in src
        assert 'require_project_access("review")' not in src

    def test_summary_route_is_get(self):
        """summary 路由方法为 GET（只读语义），路径正确。"""
        route = next(
            r for r in router.routes
            if getattr(r, "path", "") == "/api/projects/{project_id}/audit-checks/summary"
        )
        assert route.methods == {"GET"}


# ═══════════════════════════════════════════════════════════════════
# 只读无写副作用（不改 parsed_data / 不 flush / 不 commit）
# ═══════════════════════════════════════════════════════════════════

class TestNoWriteSideEffects:
    @pytest.mark.asyncio
    async def test_no_flush_commit_add_delete_called(self):
        """行为：summary 调用后 mock db 的 flush/commit/add/delete 均未被调用。"""
        _, db = await _call(_varied_rows())
        db.flush.assert_not_called()
        db.commit.assert_not_called()
        db.add.assert_not_called()
        db.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_only_execute_select_no_mutation(self):
        """行为：只经 db.execute 读取（1 次批量查询），无其它写方法调用。"""
        _, db = await _call(_varied_rows())
        assert db.execute.await_count == 1

    def test_source_has_no_mutation_calls(self):
        """静态：端点源码不含写副作用（flush/commit/add/delete）与重算/上报调用。

        summary 是只读端点（design §3），不得调 recompute/report/改 parsed_data。
        """
        src = inspect.getsource(get_audit_checks_summary)
        for banned in (".flush(", ".commit(", ".add(", ".delete(",
                       "recompute", "report", "signoff"):
            assert banned not in src, f"summary 端点不应出现写副作用/收口动作：{banned}"
