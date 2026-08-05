"""抽样框数据集绑定守卫（sampling-compliance-closure Wave 1 Task 4）

背景：抽样链路此前全文无 dataset_id，查询走 get_active_filter（当前 active）。
序时账重导后同 seed 同参数复跑得到**不同样本且无提示** → 「seed 可复现」不成立，
CAS 1131 的可复算要求落空。本文件锁定：
  - extract 返回的 dataset_id 恒等于该 (project, year) 真实 active 记录（连库实证）
  - dataset_stale 的三态判定（未知不当已变更）

Validates: Requirements 1.1, 1.4, 1.6, 7.3
Properties: Property 1, Property 2
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa

from app.routers.voucher_sampling import (
    _resolve_sampling_dataset_id,
    compute_dataset_stale,
)

_ROUTER_SRC = (
    Path(__file__).resolve().parent.parent / "app" / "routers" / "voucher_sampling.py"
).read_text(encoding="utf-8")


# ─── Property 2：dataset_stale 三态（纯函数，不连库） ─────────────────────────


class TestComputeDatasetStale:
    def test_record_missing_is_not_stale(self):
        """改造前的既有记录无 dataset_id → 不得报告告警（未知 ≠ 已变更）。

        若判成 stale，全库历史记录会一夜之间全部打红，审计师无法分辨哪条是真变了。
        """
        cur = uuid4()
        assert compute_dataset_stale(None, cur) is False
        assert compute_dataset_stale("", cur) is False

    def test_current_missing_is_not_stale(self):
        """当前无 active 数据集（尚未导入/全部作废）→ 无法判定 ⇒ 不报告。"""
        rec = uuid4()
        assert compute_dataset_stale(rec, None) is False
        assert compute_dataset_stale(rec, "") is False

    def test_equal_is_not_stale(self):
        ds = uuid4()
        assert compute_dataset_stale(ds, ds) is False
        assert compute_dataset_stale(str(ds), ds) is False
        assert compute_dataset_stale(ds, str(ds)) is False

    def test_different_is_stale(self):
        assert compute_dataset_stale(uuid4(), uuid4()) is True

    def test_str_uuid_mixed_forms_compare_by_text(self):
        """UUID 与其字符串形式必须判为相等（history 回显的是 JSON 字符串）。"""
        a = UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
        assert compute_dataset_stale(str(a), a) is False
        assert compute_dataset_stale(a, str(a)) is False

    def test_reverse_selfcheck_naive_impl_would_fail(self):
        """反向自检：朴素实现「记录有版本即 stale」会在"版本相同"时误判为 True。

        本断言证明现实现确实做了相等比较，而非只判非空。
        """
        ds = uuid4()

        def naive(record_id, current_id):  # 故意错误的朴素实现
            return record_id not in (None, "")

        assert naive(ds, ds) is True          # 朴素实现误判
        assert compute_dataset_stale(ds, ds) is False  # 现实现正确


# ─── 源码级：extract / history 已接线 ─────────────────────────────────────────


class TestDatasetBindingWiring:
    def test_extract_returns_dataset_id(self):
        assert '"dataset_id": (' in _ROUTER_SRC
        assert "_resolve_sampling_dataset_id" in _ROUTER_SRC

    def test_history_returns_stale_flag(self):
        assert '"dataset_stale": compute_dataset_stale(' in _ROUTER_SRC

    def test_no_fallback_to_arbitrary_dataset(self):
        """禁兜底：不得用 now()/任意 dataset 填充未识别的抽样框版本。

        绑定到错误版本比不绑定更坏 —— 它让「同 seed 可复算」的判定假绿。
        """
        body = _slice_func(_ROUTER_SRC, "_resolve_sampling_dataset_id")
        assert "datetime.now" not in body
        assert "order_by" not in body  # 不得自己挑"最近一版"

    def test_dataset_resolution_rolls_back_on_failure(self):
        """失败须 rollback 恢复事务，否则后续 trial_balance 查询会在被污染的事务上失败，
        把"版本未识别"放大成"整个抽凭 500"。"""
        body = _slice_func(_ROUTER_SRC, "_resolve_sampling_dataset_id")
        assert "db.rollback()" in body
        assert "return None" in body


def _slice_func(src: str, name: str) -> str:
    """截取 `async def name(` / `def name(` 到下一个顶层定义之间的函数体。

    按行首缩进判定边界（Python 无花括号），避免固定字符窗口溢出到下一个函数。
    """
    lines = src.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(f"async def {name}(") or line.startswith(f"def {name}("):
            start = i
            break
    assert start is not None, f"未找到函数 {name}（正则失效 → 断言会空转）"
    out = [lines[start]]
    for line in lines[start + 1 :]:
        if line and not line[0].isspace() and not line.startswith(")"):
            break
        out.append(line)
    return "\n".join(out)


# ─── Property 1：连库实证 dataset_id 取值 ────────────────────────────────────


@dataclass
class _Snapshot:
    """一次 asyncio.run 内取齐全部连库事实。

    🔴 连接池绑定首个事件循环：一个模块内跑第二次 asyncio.run 会抛
    `AttributeError: 'NoneType' object has no attribute 'send'`，
    若 fixture 里 except→skip 就变成静默假绿。故所有查询合并进一次 run。
    """

    active_pairs: list[tuple[UUID, int, UUID]] = field(default_factory=list)
    resolved: dict[tuple[str, int], UUID | None] = field(default_factory=dict)
    no_dataset_probe: tuple[UUID, int] | None = None
    no_dataset_result: UUID | None = None
    superseded_pairs: list[tuple[UUID, int, UUID]] = field(default_factory=list)
    available: bool = False
    reason: str = ""


def _load_snapshot() -> _Snapshot:
    snap = _Snapshot()

    async def _all() -> None:
        from app.core.database import async_session

        async with async_session() as db:
            rows = (
                await db.execute(
                    sa.text(
                        "SELECT project_id, year, id FROM ledger_datasets "
                        "WHERE status = 'active' ORDER BY year, project_id"
                    )
                )
            ).fetchall()
            snap.active_pairs = [(r[0], int(r[1]), r[2]) for r in rows]

            sup = (
                await db.execute(
                    sa.text(
                        "SELECT project_id, year, id FROM ledger_datasets "
                        "WHERE status = 'superseded' ORDER BY year, project_id"
                    )
                )
            ).fetchall()
            snap.superseded_pairs = [(r[0], int(r[1]), r[2]) for r in sup]

            for project_id, year, _ds in snap.active_pairs:
                snap.resolved[(str(project_id), year)] = (
                    await _resolve_sampling_dataset_id(db, project_id, year)
                )

            # 无数据集的探针：用真实项目 + 一个必然无账套的年度
            if snap.active_pairs:
                probe_pid = snap.active_pairs[0][0]
                snap.no_dataset_probe = (probe_pid, 1990)
                snap.no_dataset_result = await _resolve_sampling_dataset_id(
                    db, probe_pid, 1990
                )
            snap.available = True

    try:
        asyncio.run(_all())
    except Exception as exc:  # noqa: BLE001
        snap.available = False
        snap.reason = f"{type(exc).__name__}: {exc}"
    return snap


_SNAP = _load_snapshot()
_live = pytest.mark.skipif(
    not _SNAP.available, reason=f"数据库不可用（{_SNAP.reason}）"
)


@_live
class TestDatasetIdMatchesActive:
    def test_environment_has_active_datasets(self):
        """前置：环境必须有 active 数据集，否则下面的断言全部空转。"""
        assert len(_SNAP.active_pairs) > 0, "无 active 数据集 → Property 1 无法验证"

    def test_resolved_equals_real_active_id(self):
        """Property 1：解析结果逐个等于 ledger_datasets 中真实 active 记录 id。"""
        assert _SNAP.resolved, "解析结果为空 → 断言空转"
        for project_id, year, ds_id in _SNAP.active_pairs:
            got = _SNAP.resolved[(str(project_id), year)]
            assert got is not None, f"有 active 数据集却解析到 None: {project_id}/{year}"
            assert str(got) == str(ds_id), (
                f"project={project_id} year={year} 解析到 {got}，真实 active 为 {ds_id}"
            )

    def test_no_dataset_year_resolves_to_none(self):
        """无 active 数据集 → None（如实表达"未绑定"，不兜底到别的版本）。"""
        assert _SNAP.no_dataset_probe is not None
        assert _SNAP.no_dataset_result is None

    def test_superseded_dataset_would_be_stale(self):
        """已作废版本对当前 active 判定为 stale —— 这正是"序时账重导后不可复算"的信号。"""
        if not _SNAP.superseded_pairs:
            pytest.skip("环境无 superseded 数据集")
        hits = 0
        for project_id, year, old_id in _SNAP.superseded_pairs:
            cur = _SNAP.resolved.get((str(project_id), year))
            if cur is None:
                continue
            assert compute_dataset_stale(old_id, cur) is True
            hits += 1
        assert hits > 0, "无可比对的 superseded/active 组合 → 断言空转"
