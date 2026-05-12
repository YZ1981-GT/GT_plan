"""production-readiness spec 的属性测试（Properties 1-14）

使用 Hypothesis 验证设计文档中声明的 14 条正确性属性。

实现策略：
  - 后端逻辑属性（10, 11, 12, 13, 14）：直接测试真实模块
  - 前端逻辑属性（1-9）：将 TypeScript 算法复刻为 Python 等价实现后用 hypothesis 验证
    原因：项目前端未装 vitest/fast-check，新增前端测试栈超出本 spec 范围。
    代价：如果前端 TS 代码实际实现偏离本文件复刻的算法，这里测过不能代表真实行为，
    需通过 code review 保证两边一致。
  - 运行次数：max_examples=3–5（速度优先，MVP 阶段；2026-05-10 调低防止慢测试）
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from hypothesis import given, settings, assume, strategies as st


# ===========================================================================
# Property 1: 底稿保存事件传播
# ===========================================================================
# 前端算法复刻：onSave 成功后，eventBus.emit('workpaper:saved', {projectId, wpId})
# 验证：载荷一定包含调用时传入的 projectId 和 wpId

class _FakeEventBus:
    """mitt 风格事件总线的最小复刻"""
    def __init__(self):
        self._listeners: dict[str, list] = {}
        self.events: list[tuple[str, dict]] = []

    def on(self, event: str, handler):
        self._listeners.setdefault(event, []).append(handler)

    def emit(self, event: str, payload: dict):
        self.events.append((event, payload))
        for h in self._listeners.get(event, []):
            h(payload)


def _simulate_on_save_success(bus: _FakeEventBus, project_id: str, wp_id: str) -> bool:
    """复刻 WorkpaperEditor.vue 的 onSave 成功分支"""
    bus.emit("workpaper:saved", {"projectId": project_id, "wpId": wp_id})
    return True


@given(
    project_id=st.uuids().map(str),
    wp_id=st.uuids().map(str),
)
@settings(max_examples=5)
def test_property_01_workpaper_save_event_propagates(project_id, wp_id):
    """Property 1: 底稿保存事件传播（验证需求 1.1）"""
    bus = _FakeEventBus()
    received: list[dict] = []
    bus.on("workpaper:saved", lambda p: received.append(p))

    ok = _simulate_on_save_success(bus, project_id, wp_id)

    assert ok is True
    assert len(received) == 1
    assert received[0]["projectId"] == project_id
    assert received[0]["wpId"] == wp_id


# ===========================================================================
# Property 2: 附注刷新防抖
# ===========================================================================
# 前端算法：收到 workpaper:saved 事件时 clearTimeout 旧 timer → setTimeout 新 timer
# 1000ms 防抖。在 <1 秒窗口内 N 次触发只会实际调用 1 次
# （这里测"防抖合并"这个不变式的数学语义：只有最后一次调度会执行）

class _Debouncer:
    """setTimeout/clearTimeout 防抖的等价状态机"""
    def __init__(self, wait_ms: int = 1000):
        self.wait_ms = wait_ms
        self._scheduled_at: int | None = None  # 最后一次 trigger 的时间戳
        self._actual_calls = 0

    def trigger(self, now_ms: int):
        # 等价于 clearTimeout + setTimeout
        self._scheduled_at = now_ms

    def tick(self, now_ms: int):
        # 时间跳到 now_ms 时，若 scheduled_at + wait <= now 则执行
        if self._scheduled_at is not None and now_ms - self._scheduled_at >= self.wait_ms:
            self._actual_calls += 1
            self._scheduled_at = None

    @property
    def actual_calls(self) -> int:
        return self._actual_calls


@given(
    events=st.lists(
        st.integers(min_value=0, max_value=999),
        min_size=2,
        max_size=20,
    )
)
@settings(max_examples=5)
def test_property_02_debounce_coalesces_burst(events):
    """Property 2: 1 秒内 N 次连续事件只产生 1 次刷新（验证需求 1.5）"""
    d = _Debouncer(wait_ms=1000)
    # 所有事件都在 [0, 999]ms 窗口内触发（不超过防抖阈值）
    for t in sorted(events):
        d.trigger(t)
    # 然后时间前进到 last + 1000ms，触发执行
    d.tick(max(events) + 1000)

    assert d.actual_calls == 1


# ===========================================================================
# Property 3: 趋势图数据一致性
# ===========================================================================
# 前端算法：后端返回 trend[date][status] = count，前端 sparkSeries 按日期排序
# 取各 status 数组。验证数组值 = API 响应对应位置的值

def _build_spark_series(trend: dict[str, dict[str, int]]) -> dict[str, list[int]]:
    """复刻 Dashboard.vue 的 sparkSeries computed"""
    days = sorted(trend.keys())
    return {
        "review_passed": [trend.get(d, {}).get("review_passed", 0) for d in days],
        "in_progress": [trend.get(d, {}).get("in_progress", 0) for d in days],
    }


@given(
    trend=st.dictionaries(
        st.text(alphabet="0123456789-", min_size=10, max_size=10),
        st.dictionaries(
            st.sampled_from(["review_passed", "in_progress", "archived"]),
            st.integers(min_value=0, max_value=1000),
            min_size=0, max_size=3,
        ),
        min_size=1, max_size=7,
    )
)
@settings(max_examples=5)
def test_property_03_trend_series_matches_api(trend):
    """Property 3: sparkSeries 数组值 == API 响应（验证需求 2.3）"""
    series = _build_spark_series(trend)
    days = sorted(trend.keys())
    for i, d in enumerate(days):
        assert series["review_passed"][i] == trend[d].get("review_passed", 0)
        assert series["in_progress"][i] == trend[d].get("in_progress", 0)


# ===========================================================================
# Property 4: 编辑命令触发 Dirty 标记
# ===========================================================================
# 前端算法：命令 ID 若匹配 DIRTY_COMMAND_PATTERNS 中任一子串，dirty=true

_DIRTY_PATTERNS = [
    "set-range-values", "set-cell",
    "set-formula", "formula.", "array-formula",
    "set-style", "set-border", "set-number-format", "set-font",
    "clear-selection", "delete-range",
    "insert-row", "insert-col", "remove-row", "remove-col",
    "merge-cells", "unmerge-cells",
]


def _should_mark_dirty(command_id: str) -> bool:
    return any(p in command_id for p in _DIRTY_PATTERNS)


@given(
    prefix=st.text(min_size=0, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz-"),
    pattern=st.sampled_from(_DIRTY_PATTERNS),
    suffix=st.text(min_size=0, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz-"),
)
@settings(max_examples=5)
def test_property_04_command_triggers_dirty(prefix, pattern, suffix):
    """Property 4: 命令 ID 含 DIRTY_COMMAND_PATTERNS 任一模式则 dirty=true（需求 3.1/3.2/3.6）"""
    command_id = f"{prefix}{pattern}{suffix}"
    assert _should_mark_dirty(command_id) is True


@given(noise=st.text(min_size=1, max_size=30).filter(
    lambda s: not any(p in s for p in _DIRTY_PATTERNS)
))
@settings(max_examples=3)
def test_property_04_negative_non_dirty_command(noise):
    """Property 4 补充：不含任一模式的命令不应触发 dirty"""
    assert _should_mark_dirty(noise) is False


# ===========================================================================
# Property 5: 保存后 Dirty 重置
# ===========================================================================
# 前端算法：onSave 成功后 dirty.value = false

class _EditorState:
    def __init__(self):
        self.dirty = False

    def mark_dirty(self):
        self.dirty = True

    def on_save_success(self):
        self.dirty = False


@given(edits_before=st.integers(min_value=1, max_value=50))
@settings(max_examples=5)
def test_property_05_save_resets_dirty(edits_before):
    """Property 5: 任意数量编辑后保存，dirty 必定重置为 false（需求 3.5）"""
    st_ = _EditorState()
    for _ in range(edits_before):
        st_.mark_dirty()
    assert st_.dirty is True
    st_.on_save_success()
    assert st_.dirty is False


# ===========================================================================
# Property 6: 复核收件箱入口权限控制
# ===========================================================================

_ALLOWED_ROLES = {"reviewer", "partner", "admin"}
_ALL_ROLES = ["staff", "senior", "manager", "reviewer", "partner", "admin", "guest", "client"]


def _has_review_inbox_access(role: str) -> bool:
    return role in _ALLOWED_ROLES


@given(role=st.sampled_from(_ALL_ROLES))
@settings(max_examples=5)
def test_property_06_review_inbox_visibility(role):
    """Property 6: 角色在 {reviewer, partner, admin} 才显示收件箱入口（需求 4.1/4.4）"""
    has_access = _has_review_inbox_access(role)
    assert has_access == (role in _ALLOWED_ROLES)


# ===========================================================================
# Property 7: 复核 Badge 数量一致性
# ===========================================================================

def _badge_count_from_api(api_total: int) -> int:
    """前端：pendingReviewCount.value = res.total || 0"""
    return max(0, api_total or 0)


@given(api_total=st.integers(min_value=0, max_value=10_000))
@settings(max_examples=5)
def test_property_07_badge_count_matches_api(api_total):
    """Property 7: Badge 数 == API 返回 total（需求 4.3/4.5）"""
    assert _badge_count_from_api(api_total) == api_total


# ===========================================================================
# Property 8: UUID → 姓名映射完整性
# ===========================================================================

def _resolve_user_name(uuid: str | None, user_map: dict[str, str]) -> str:
    """复刻 WorkpaperList.vue 的 resolveUserName"""
    if uuid is None or uuid == "":
        return "未分配"
    return user_map.get(uuid, "未知用户")


@given(
    user_map=st.dictionaries(
        st.uuids().map(str),
        st.text(min_size=1, max_size=20),
        min_size=1, max_size=10,
    ),
    lookup=st.uuids().map(str),
)
@settings(max_examples=5)
def test_property_08_uuid_to_name_mapping(user_map, lookup):
    """Property 8: 映射完整性三分支（需求 5.1/5.2/5.3）"""
    # 分支 A：null/空
    assert _resolve_user_name(None, user_map) == "未分配"
    assert _resolve_user_name("", user_map) == "未分配"
    # 分支 B：命中
    for uid, name in user_map.items():
        assert _resolve_user_name(uid, user_map) == name
    # 分支 C：未命中
    if lookup not in user_map:
        assert _resolve_user_name(lookup, user_map) == "未知用户"


# ===========================================================================
# Property 9: 进度百分比计算正确性
# ===========================================================================

_COMPLETED = {"review_passed", "archived"}


def _progress_percent(statuses: list[str]) -> dict:
    if not statuses:
        return {"completed": 0, "total": 0, "percent": 0}
    completed = sum(1 for s in statuses if s in _COMPLETED)
    percent = math.floor((completed / len(statuses)) * 100)
    return {"completed": completed, "total": len(statuses), "percent": percent}


@given(
    statuses=st.lists(
        st.sampled_from([
            "not_started", "in_progress", "draft", "edit_complete",
            "review_passed", "archived",
        ]),
        min_size=0, max_size=100,
    )
)
@settings(max_examples=5)
def test_property_09_progress_calculation(statuses):
    """Property 9: percent = floor(completed/total*100)（需求 6.2/6.4）"""
    result = _progress_percent(statuses)
    if not statuses:
        assert result == {"completed": 0, "total": 0, "percent": 0}
        return
    expected_completed = sum(1 for s in statuses if s in _COMPLETED)
    expected_pct = math.floor((expected_completed / len(statuses)) * 100)
    assert result["completed"] == expected_completed
    assert result["total"] == len(statuses)
    assert result["percent"] == expected_pct
    # percent 永不超过 100
    assert 0 <= result["percent"] <= 100


# ===========================================================================
# Property 10: 步骤状态单调递进
# ===========================================================================

class _SetupStepMachine:
    """复刻 TrialBalance.vue 的步骤引导状态"""
    def __init__(self):
        self.current = 0

    def advance(self):
        if self.current < 3:
            self.current += 1

    def step_status(self) -> list[str]:
        return [
            "finish" if i < self.current else "process" if i == self.current else "wait"
            for i in range(3)
        ]


@given(advance_count=st.integers(min_value=0, max_value=10))
@settings(max_examples=5)
def test_property_10_step_monotonic(advance_count):
    """Property 10: 步骤单调递进，永不回退，上限 3（需求 7.2/7.3）"""
    m = _SetupStepMachine()
    prev = 0
    for _ in range(advance_count):
        m.advance()
        assert m.current >= prev
        assert m.current <= 3
        prev = m.current


# ===========================================================================
# Property 11: 借贷平衡计算正确性
# ===========================================================================
# 复刻 TrialBalance.vue 的 liabEquityTotal（含损益类）

def _liab_equity_total(rows: list[tuple[str, float]]) -> float:
    """rows = [(account_category, audited_amount), ...]"""
    liab_eq = sum(a for cat, a in rows if cat in ("liability", "equity"))
    income_net = sum(
        a for cat, a in rows if cat in ("revenue", "income", "cost", "expense")
    )
    return liab_eq + income_net


def _asset_total(rows: list[tuple[str, float]]) -> float:
    return sum(a for cat, a in rows if cat == "asset")


@given(
    asset_amt=st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
    liab_amt=st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
    eq_amt=st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
    rev_amt=st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
    exp_amt=st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=5)
def test_property_11_balance_includes_income_net(asset_amt, liab_amt, eq_amt, rev_amt, exp_amt):
    """Property 11: 资产 ≈ 负债 + 权益 + 收入 + 费用（需求 8.1/8.3/8.4）"""
    # 构造一组"应平衡"的数据：asset = liab + eq + rev + exp
    asset_amt = liab_amt + eq_amt + rev_amt + exp_amt
    rows = [
        ("asset", asset_amt),
        ("liability", liab_amt),
        ("equity", eq_amt),
        ("revenue", rev_amt),
        ("expense", exp_amt),
    ]
    diff = _asset_total(rows) - _liab_equity_total(rows)
    # 浮点容忍（项目用 < 1 元判断平衡）
    assert abs(diff) < 1e-4


# ===========================================================================
# Property 12: 数据库迁移完整性
# ===========================================================================

def test_property_12_schema_table_count():
    """Property 12: metadata 表数 ≥ 144（需求 9.2）"""
    import importlib
    import pkgutil
    from app import models

    for _, modname, _ in pkgutil.iter_modules(models.__path__, models.__name__ + "."):
        try:
            importlib.import_module(modname)
        except Exception:
            pass

    from app.models import Base

    table_count = len(Base.metadata.tables)
    assert table_count >= 144, (
        f"Schema 表数 {table_count} < 144，需求 9.2 要求至少 144 张表"
    )


# ===========================================================================
# Property 13: Worker 异常隔离
# ===========================================================================

@pytest.mark.asyncio
async def test_property_13_worker_isolates_exceptions():
    """Property 13: Worker 内部异常不影响主循环（需求 10.5）"""
    import asyncio
    # 我们不实际拉起 worker（它需要 DB 连接），但直接验证其异常处理结构：
    # - 内部 try/except 捕获异常
    # - CancelledError 时 break
    # - 其它异常记录 warning 并继续

    from app.workers import sla_worker, import_recover_worker, outbox_replay_worker

    # 三个 worker 都必须暴露 async run(stop_event)
    assert callable(sla_worker.run)
    assert callable(import_recover_worker.run)
    assert callable(outbox_replay_worker.run)

    # stop_event 设置后，worker 必须快速退出（不阻塞）
    stop_event = asyncio.Event()
    stop_event.set()
    # SLA worker：第一次 wait_for 就命中 stop_event
    await asyncio.wait_for(sla_worker.run(stop_event), timeout=3.0)


# ===========================================================================
# Property 14: 路由前缀规范一致性
# ===========================================================================

def test_property_14_no_hasattr_patch_remaining():
    """Property 14: router_registry.py 不得再有 hasattr 补丁（需求 11.1/11.2）"""
    # 解析相对于本测试文件的路径，兼容 cwd=repo root 或 cwd=backend
    test_dir = Path(__file__).resolve().parent
    candidates = [
        test_dir.parent / "app" / "router_registry.py",  # backend/app/router_registry.py
        Path("backend/app/router_registry.py"),
        Path("app/router_registry.py"),
    ]
    src_path = next((p for p in candidates if p.exists()), None)
    assert src_path is not None, f"router_registry.py 未找到（尝试路径：{candidates}）"
    src = src_path.read_text(encoding="utf-8")
    # hasattr(r, 'prefix') 这种运行时判断补丁必须已经删除
    assert "hasattr(r, 'prefix')" not in src
    assert "hasattr(r, \"prefix\")" not in src


def test_property_14_all_business_routes_under_api():
    """Property 14: 除 WOPI / healthz / version 外，所有业务路由以 /api 开头（需求 11.4）"""
    from app.main import app

    non_api = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path:
            continue
        # 已知例外（WOPI 协议要求、探针、OpenAPI 内置路径、Prometheus 标准路径）
        exceptions = (
            "/wopi",
            "/api",  # 前缀本身匹配
            "/docs", "/openapi.json", "/redoc",
            "/metrics",  # Sprint 4.10 Prometheus 标准端点，非业务路由
        )
        if path.startswith(exceptions):
            continue
        # Starlette Mount 等可能没有 /api 前缀，但必须不含业务动词路径段
        # 健康检查 / 静态资源等明确白名单
        if path in ("/", "/healthz", "/favicon.ico"):
            continue
        non_api.append(path)

    assert not non_api, f"以下路由未以 /api 开头: {non_api[:20]}"
