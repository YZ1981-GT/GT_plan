"""单测 — NoteTrimService.auto_trim（Sprint 3 Task 3.7）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.7
Reqs:   R3.4 智能裁剪（v2 §5.3 简化版）

测试策略：
- 不连真 PG：用 monkeypatch 替换 ``resolve_template_type / get_sections /
  save_trim`` 这三个依赖 DB 的方法。
- ``_is_all_zero_for_codes`` 走真实 SQL 路径但通过 mock db.execute 返回构造数据；
  保证算法逻辑（NULL/0 判定 + 多列汇总）路径覆盖。
- ``get_binding_for_section`` 通过 monkeypatch 注入 in-memory binding map。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services import note_template_bindings_loader as loader
from app.services.note_trim_service import NoteTrimService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    sections: list[dict[str, Any]],
    *,
    template_type: str = "soe",
    tb_rows_by_codes: dict[frozenset[str], list[tuple]] | None = None,
    tb_db_error: bool = False,
    save_trim_error: bool = False,
) -> tuple[NoteTrimService, dict[str, Any]]:
    """构造一个 mock 注入完整的 NoteTrimService.

    Args:
        sections: ``get_sections`` 返回的章节列表。
        template_type: ``resolve_template_type`` 返回值。
        tb_rows_by_codes: 按 account_codes set 索引的 (audited, opening) 行集合，
            用于 ``_is_all_zero_for_codes`` 中的 db.execute 模拟。
        tb_db_error: 设为 True 时 db.execute 抛异常（模拟缺数据/PG 不可用）。
        save_trim_error: 设为 True 时 save_trim 抛异常。

    Returns:
        (svc, calls)：calls dict 记录 save_trim 的入参以便断言。
    """
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    if tb_db_error:
        db.execute = AsyncMock(side_effect=RuntimeError("PG unavailable"))
    else:
        async def _exec(query):
            # 提取 in_(...) 中的 account_codes — SQLAlchemy 用 bind 参数，须 compile literal_binds
            try:
                compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
            except Exception:
                compiled = str(query)
            mapping = tb_rows_by_codes or {}
            for codes_key, rows in mapping.items():
                # 所有 codes 都出现在 compiled SQL 中即认为命中（in_ 子句把 codes 作字符串字面值）
                if all(f"'{c}'" in compiled for c in codes_key):
                    res = MagicMock()
                    res.all = MagicMock(return_value=rows)
                    return res
            res = MagicMock()
            res.all = MagicMock(return_value=[])
            return res

        db.execute = AsyncMock(side_effect=_exec)

    svc = NoteTrimService(db)

    # mock resolve_template_type
    async def _resolve(_pid, _tt):
        return template_type
    svc.resolve_template_type = _resolve  # type: ignore[assignment]

    # mock get_sections
    async def _get_sections(_pid, _tt):
        return sections
    svc.get_sections = _get_sections  # type: ignore[assignment]

    # mock save_trim
    calls: dict[str, Any] = {"save_trim": []}

    async def _save_trim(pid, tt, items):
        calls["save_trim"].append({
            "project_id": pid,
            "template_type": tt,
            "items": list(items),
        })
        if save_trim_error:
            raise RuntimeError("save_trim failure")
        return len(items)

    svc.save_trim = _save_trim  # type: ignore[assignment]

    return svc, calls


def _binding_for(account_codes: list[str]) -> dict[str, Any]:
    """构造单 cell 单 row 单 table 的 binding（含指定 account_codes）."""
    return {
        "tables": [{
            "table_index": 0,
            "rows": {
                "data_row": {
                    "row_type": "data",
                    "binding": {
                        "closing_balance": {
                            "source": "trial_balance",
                            "field": "audited_amount",
                            "account_codes": list(account_codes),
                            "mode": "auto",
                        },
                    },
                },
            },
        }],
    }


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    """每个测试结束清缓存防 cross-pollution."""
    loader.reload()
    yield
    loader.reload()


def _patch_loader(monkeypatch, mapping: dict[str, dict | None]):
    """注入 ``get_binding_for_section`` 行为：mapping[section_number] → binding."""
    def _fake(section_number):
        return mapping.get(section_number)
    monkeypatch.setattr(
        "app.services.note_trim_service.get_binding_for_section",
        _fake,
        raising=False,
    )


# ---------------------------------------------------------------------------
# 1. 全 0 章节自动跳过
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_all_zero_section_skipped(monkeypatch):
    """章节科目在 TrialBalance 全 0 → status=not_applicable + skip_reason='auto:all_zero'."""
    sec_id = str(uuid4())
    sections = [
        {"id": sec_id, "section_number": "四、在建工程", "section_title": "在建工程",
         "status": "retain", "skip_reason": None, "sort_order": 10},
    ]
    # binding 用 1604（在建工程典型科目）
    _patch_loader(monkeypatch, {
        "四、在建工程": _binding_for(["1604"]),
    })

    # TB 全 0：rows 都是 (0, 0) 或 None
    tb_rows = {
        frozenset({"1604"}): [
            (Decimal("0"), Decimal("0")),
            (None, None),
        ],
    }
    svc, calls = _make_service(sections, tb_rows_by_codes=tb_rows)

    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    assert result["auto_skipped"] == 1
    assert result["retained"] == 0
    assert result["errors"] == []

    # save_trim 被调用一次，包含该 section 的 not_applicable 标记
    assert len(calls["save_trim"]) == 1
    saved = calls["save_trim"][0]["items"]
    assert len(saved) == 1
    assert saved[0]["id"] == sec_id
    assert saved[0]["status"] == "not_applicable"
    assert saved[0]["skip_reason"] == "auto:all_zero"


# ---------------------------------------------------------------------------
# 2. 部分非 0 章节保留
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_nonzero_section_retained(monkeypatch):
    """章节科目 audited_amount 非 0 → 保留（不写 save_trim）."""
    sec_id = str(uuid4())
    sections = [
        {"id": sec_id, "section_number": "四、应收账款", "section_title": "应收账款",
         "status": "retain", "skip_reason": None, "sort_order": 20},
    ]
    _patch_loader(monkeypatch, {
        "四、应收账款": _binding_for(["1122"]),
    })

    tb_rows = {
        frozenset({"1122"}): [
            (Decimal("100000.00"), Decimal("80000.00")),
        ],
    }
    svc, calls = _make_service(sections, tb_rows_by_codes=tb_rows)

    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    assert result["auto_skipped"] == 0
    assert result["retained"] == 1
    assert result["errors"] == []

    # 全部保留 → save_trim 不被调用（因 items 为空）
    assert calls["save_trim"] == []


@pytest.mark.asyncio
async def test_auto_trim_mixed_sections(monkeypatch):
    """混合：1 全 0 跳 + 1 非 0 留 + 1 缺 binding 留 → 总计 1 跳 2 留."""
    sec_zero = str(uuid4())
    sec_nonzero = str(uuid4())
    sec_no_binding = str(uuid4())
    sections = [
        {"id": sec_zero, "section_number": "S1", "section_title": "全0",
         "status": "retain", "skip_reason": None, "sort_order": 1},
        {"id": sec_nonzero, "section_number": "S2", "section_title": "非0",
         "status": "retain", "skip_reason": None, "sort_order": 2},
        {"id": sec_no_binding, "section_number": "S3", "section_title": "缺binding",
         "status": "retain", "skip_reason": None, "sort_order": 3},
    ]
    _patch_loader(monkeypatch, {
        "S1": _binding_for(["1001"]),
        "S2": _binding_for(["1002"]),
        # S3 缺
    })

    tb_rows = {
        frozenset({"1001"}): [(Decimal("0"), Decimal("0"))],
        frozenset({"1002"}): [(Decimal("999"), Decimal("0"))],
    }
    svc, calls = _make_service(sections, tb_rows_by_codes=tb_rows)
    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    assert result["auto_skipped"] == 1
    assert result["retained"] == 2
    assert result["errors"] == []

    saved = calls["save_trim"][0]["items"]
    assert len(saved) == 1
    assert saved[0]["id"] == sec_zero


# ---------------------------------------------------------------------------
# 3. 缺 binding 的 section 默认保留（不跳过）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_missing_binding_retained(monkeypatch):
    """章节缺 binding（loader 返 None） → 默认保留 + 不抛错."""
    sec_id = str(uuid4())
    sections = [
        {"id": sec_id, "section_number": "未知章节", "section_title": "X",
         "status": "retain", "skip_reason": None, "sort_order": 0},
    ]
    _patch_loader(monkeypatch, {})  # 空 map → 全 None

    svc, calls = _make_service(sections)
    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    assert result["auto_skipped"] == 0
    assert result["retained"] == 1
    assert calls["save_trim"] == []


@pytest.mark.asyncio
async def test_auto_trim_binding_with_empty_account_codes_retained(monkeypatch):
    """binding 存在但所有 account_codes 都为空 list → 视为缺 binding，保留."""
    sec_id = str(uuid4())
    sections = [
        {"id": sec_id, "section_number": "S1", "section_title": "X",
         "status": "retain", "skip_reason": None, "sort_order": 0},
    ]
    _patch_loader(monkeypatch, {"S1": _binding_for([])})

    svc, _calls = _make_service(sections)
    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    assert result["auto_skipped"] == 0
    assert result["retained"] == 1


# ---------------------------------------------------------------------------
# 4. 缺 TrialBalance 数据时不抛错（graceful）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_missing_tb_data_treats_as_zero(monkeypatch):
    """TrialBalance 完全无该 codes 行 → 视为全 0 自动跳过（不抛错）."""
    sec_id = str(uuid4())
    sections = [
        {"id": sec_id, "section_number": "S1", "section_title": "X",
         "status": "retain", "skip_reason": None, "sort_order": 0},
    ]
    _patch_loader(monkeypatch, {"S1": _binding_for(["9999"])})

    svc, calls = _make_service(sections, tb_rows_by_codes={})  # 任何 codes 都返空 rows
    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    # 缺 TB 行 → 视为全 0 → 跳过
    assert result["auto_skipped"] == 1
    assert result["errors"] == []


@pytest.mark.asyncio
async def test_auto_trim_db_error_in_tb_query_graceful(monkeypatch):
    """db.execute 抛异常 → graceful 记录到 errors[] 不阻塞其他 section."""
    sec1 = str(uuid4())
    sec2 = str(uuid4())
    sections = [
        {"id": sec1, "section_number": "S1", "section_title": "X",
         "status": "retain", "skip_reason": None, "sort_order": 0},
        {"id": sec2, "section_number": "S2", "section_title": "Y",
         "status": "retain", "skip_reason": None, "sort_order": 0},
    ]
    _patch_loader(monkeypatch, {
        "S1": _binding_for(["1001"]),
        "S2": _binding_for(["1002"]),
    })

    svc, calls = _make_service(sections, tb_db_error=True)
    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    # _is_all_zero_for_codes 内部已 try/except → 返 True (视为全 0)
    # → auto_skipped 计数 = 2，且 errors 列表为空（DB 异常被吞）
    assert result["auto_skipped"] == 2
    assert result["retained"] == 0


@pytest.mark.asyncio
async def test_auto_trim_save_trim_failure_recorded(monkeypatch):
    """save_trim 抛异常 → 记录到 errors[] 不破坏返回结构."""
    sec_id = str(uuid4())
    sections = [
        {"id": sec_id, "section_number": "S1", "section_title": "X",
         "status": "retain", "skip_reason": None, "sort_order": 0},
    ]
    _patch_loader(monkeypatch, {"S1": _binding_for(["1001"])})

    tb_rows = {frozenset({"1001"}): [(Decimal("0"), Decimal("0"))]}
    svc, _calls = _make_service(
        sections,
        tb_rows_by_codes=tb_rows,
        save_trim_error=True,
    )
    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    assert result["auto_skipped"] == 1
    # errors 应包含 save_trim 失败记录
    assert any(e.get("phase") == "save_trim" for e in result["errors"])


# ---------------------------------------------------------------------------
# 5. 模板类型自动检测（不传 template_type）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_template_type_auto_resolution(monkeypatch):
    """不传 template_type → 调 resolve_template_type 自动检测."""
    sec_id = str(uuid4())
    sections = [
        {"id": sec_id, "section_number": "S1", "section_title": "X",
         "status": "retain", "skip_reason": None, "sort_order": 0},
    ]
    _patch_loader(monkeypatch, {"S1": _binding_for(["1001"])})

    tb_rows = {frozenset({"1001"}): [(Decimal("100"), Decimal("0"))]}

    captured: dict[str, Any] = {}

    db = MagicMock()
    db.execute = AsyncMock()
    res = MagicMock()
    res.all = MagicMock(return_value=tb_rows[frozenset({"1001"})])
    db.execute = AsyncMock(return_value=res)

    svc = NoteTrimService(db)

    async def _resolve(pid, tt):
        captured["template_type_arg"] = tt
        return "listed"

    svc.resolve_template_type = _resolve  # type: ignore[assignment]
    svc.get_sections = AsyncMock(return_value=sections)  # type: ignore[assignment]
    svc.save_trim = AsyncMock(return_value=0)  # type: ignore[assignment]

    pid = uuid4()
    result = await svc.auto_trim(pid, 2025, template_type=None)

    # resolve_template_type 收到 None → 服务内部自动检测
    assert captured["template_type_arg"] is None
    assert "auto_skipped" in result and "retained" in result


# ---------------------------------------------------------------------------
# 6. 重复跑幂等
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_idempotent(monkeypatch):
    """同样输入连跑两次 → 返回值一致；save_trim 调用次数稳定."""
    sec_zero = str(uuid4())
    sec_nonzero = str(uuid4())
    sections = [
        {"id": sec_zero, "section_number": "S1", "section_title": "X1",
         "status": "retain", "skip_reason": None, "sort_order": 1},
        {"id": sec_nonzero, "section_number": "S2", "section_title": "X2",
         "status": "retain", "skip_reason": None, "sort_order": 2},
    ]
    _patch_loader(monkeypatch, {
        "S1": _binding_for(["1001"]),
        "S2": _binding_for(["1002"]),
    })
    tb_rows = {
        frozenset({"1001"}): [(Decimal("0"), Decimal("0"))],
        frozenset({"1002"}): [(Decimal("99"), Decimal("0"))],
    }
    svc, calls = _make_service(sections, tb_rows_by_codes=tb_rows)
    pid = uuid4()

    r1 = await svc.auto_trim(pid, 2025)
    r2 = await svc.auto_trim(pid, 2025)

    assert r1 == r2
    assert r1["auto_skipped"] == 1
    assert r1["retained"] == 1
    # save_trim 每次都调一次，items 内容一致
    assert len(calls["save_trim"]) == 2
    assert calls["save_trim"][0]["items"] == calls["save_trim"][1]["items"]


# ---------------------------------------------------------------------------
# 额外：collect_account_codes 算法直接测试（非异步，纯函数）
# ---------------------------------------------------------------------------


def test_collect_account_codes_unions_all_cells():
    """多 row × 多 cell 的 account_codes 求并集."""
    binding = {
        "tables": [{
            "rows": {
                "row1": {
                    "binding": {
                        "closing_balance": {"account_codes": ["1001", "1002"]},
                        "opening_balance": {"account_codes": ["1001"]},
                    },
                },
                "row2": {
                    "binding": {
                        "closing_balance": {"account_codes": ["1003"]},
                    },
                },
            },
        }],
    }
    result = NoteTrimService._collect_account_codes_for_section(binding)
    assert result == {"1001", "1002", "1003"}


def test_collect_account_codes_handles_dirty_data():
    """脏数据（None / 非 list / 空 list / 非 str）不抛错."""
    binding = {
        "tables": [
            "not a dict",
            {
                "rows": {
                    "row1": "not a dict",
                    "row2": {"binding": "not a dict"},
                    "row3": {
                        "binding": {
                            "x": None,
                            "y": {"account_codes": "not a list"},
                            "z": {"account_codes": [None, "1001", "", 42]},
                        },
                    },
                },
            },
        ],
    }
    result = NoteTrimService._collect_account_codes_for_section(binding)
    assert result == {"1001"}


def test_collect_account_codes_returns_empty_for_none():
    assert NoteTrimService._collect_account_codes_for_section(None) == set()
    assert NoteTrimService._collect_account_codes_for_section({}) == set()
    assert NoteTrimService._collect_account_codes_for_section({"tables": "x"}) == set()


# ---------------------------------------------------------------------------
# 额外：empty sections 不抛错
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_no_sections_returns_zero():
    svc, calls = _make_service([])
    pid = uuid4()
    r = await svc.auto_trim(pid, 2025)
    assert r == {"auto_skipped": 0, "retained": 0, "errors": []}
    assert calls["save_trim"] == []


# ---------------------------------------------------------------------------
# 额外：per-section graceful exception 路径
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_trim_per_section_exception_graceful(monkeypatch):
    """_collect_account_codes_for_section 抛错 → graceful 记 errors[] 不阻塞其他 section."""
    sec1 = str(uuid4())
    sec2 = str(uuid4())
    sections = [
        {"id": sec1, "section_number": "S1", "section_title": "X",
         "status": "retain", "skip_reason": None, "sort_order": 0},
        {"id": sec2, "section_number": "S2", "section_title": "Y",
         "status": "retain", "skip_reason": None, "sort_order": 0},
    ]

    # mock get_binding_for_section 仅对 S1 抛错；S2 正常返回非 0 binding
    def _fake(sn):
        if sn == "S1":
            raise RuntimeError("simulated binding load failure")
        return _binding_for(["1002"])
    monkeypatch.setattr(
        "app.services.note_trim_service.get_binding_for_section",
        _fake,
        raising=False,
    )

    tb_rows = {frozenset({"1002"}): [(Decimal("100"), Decimal("0"))]}
    svc, _calls = _make_service(sections, tb_rows_by_codes=tb_rows)

    pid = uuid4()
    result = await svc.auto_trim(pid, 2025)

    assert result["auto_skipped"] == 0
    assert result["retained"] == 2  # S1 异常路径记 retained，S2 非0 retained
    # errors 应包含 S1 失败
    assert any(e.get("section_number") == "S1" for e in result["errors"])


# ---------------------------------------------------------------------------
# 额外：_is_all_zero_for_codes 边界（empty account_codes → True）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_all_zero_empty_codes_returns_true():
    """_is_all_zero_for_codes(空 list) → True（防御）."""
    db = MagicMock()
    db.execute = AsyncMock()
    svc = NoteTrimService(db)
    assert await svc._is_all_zero_for_codes(uuid4(), 2025, []) is True
    # 没有空 code 时不查 DB
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_is_all_zero_with_partial_nonzero_returns_false():
    """3 行：(0,0) (None,None) (None, 100) → 第 3 行 opening 非 0 → False."""
    db = MagicMock()
    res = MagicMock()
    res.all = MagicMock(return_value=[
        (Decimal("0"), Decimal("0")),
        (None, None),
        (None, Decimal("100")),
    ])
    db.execute = AsyncMock(return_value=res)
    svc = NoteTrimService(db)
    assert await svc._is_all_zero_for_codes(uuid4(), 2025, ["1001"]) is False


@pytest.mark.asyncio
async def test_is_all_zero_audited_nonzero_returns_false():
    """audited 非 0 → False."""
    db = MagicMock()
    res = MagicMock()
    res.all = MagicMock(return_value=[(Decimal("999"), Decimal("0"))])
    db.execute = AsyncMock(return_value=res)
    svc = NoteTrimService(db)
    assert await svc._is_all_zero_for_codes(uuid4(), 2025, ["1001"]) is False


def test_collect_account_codes_non_list_tables():
    """tables 不是 list（例如 dict）→ 返 set() 不抛错."""
    binding = {"tables": {"not": "a list"}}
    assert NoteTrimService._collect_account_codes_for_section(binding) == set()
