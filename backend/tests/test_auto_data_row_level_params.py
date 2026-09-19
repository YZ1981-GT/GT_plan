# -*- coding: utf-8 -*-
"""通用 auto-data 端点的**行级参数透传**判据。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Task 7 收口

🔴 补这组判据的原因（复盘实证）：`resolve_auto_data_source` 早就支持 `**kwargs`，但
`GET /api/projects/{pid}/auto-data/{source}` 原来一个都不传 ⇒ 任何**按行取数**的
resolver 经 HTTP 恒拿不到参数。D4 IPO 四表的 resolver 都要 `customer_name`
（或 `person_name`）才能查，缺参时按「宁缺勿造」返回全 None ——
于是「表间提取」在 UI 上永远空白，而当时**没有任何测试覆盖这个端点**。

判据落在「query 参数真的变成了 resolver 的 kwargs」上，而不是「函数存在」。
"""
from __future__ import annotations

import inspect

import pytest

from app.routers import auto_data


# ═══════════════════════════════════════════════════════════════════════════
# 1. 保留名不得被当作行级参数透传（否则 resolver 收到重复参数 TypeError）
# ═══════════════════════════════════════════════════════════════════════════


def test_reserved_keys_cover_path_and_fixed_params() -> None:
    """`project_id` / `source` / `year` 必须在保留名里。

    它们已由路径/签名显式传给 `resolve_auto_data_source`，再透传一遍会
    `got multiple values for argument`。
    """
    assert {"project_id", "source", "year"} <= set(auto_data._RESERVED_QUERY_KEYS)


class _FakeQueryParams:
    """最小 `request.query_params` 替身（只需 `.items()`）。"""

    def __init__(self, pairs: dict[str, str]) -> None:
        self._pairs = pairs

    def items(self):  # noqa: ANN201 - 仿 starlette QueryParams
        return self._pairs.items()


class _FakeRequest:
    def __init__(self, pairs: dict[str, str]) -> None:
        self.query_params = _FakeQueryParams(pairs)


def test_row_level_kwargs_keeps_extra_params_and_drops_reserved() -> None:
    """非保留参数按原名保留；保留参数被剔除。"""
    req = _FakeRequest(
        {
            "year": "2025",  # 保留 → 剔除
            "project_id": "x",  # 保留 → 剔除
            "source": "y",  # 保留 → 剔除
            "customer_name": "某某公司",  # 行级 → 保留
            "person_name": "陈某",  # 行级 → 保留
        }
    )
    got = auto_data._row_level_kwargs(req)  # type: ignore[arg-type]
    assert got == {"customer_name": "某某公司", "person_name": "陈某"}


def test_row_level_kwargs_empty_when_only_reserved() -> None:
    """只带保留参数时返回空 dict —— 既有调用方行为零变化（纯加法的判据）。"""
    req = _FakeRequest({"year": "2025"})
    assert auto_data._row_level_kwargs(req) == {}  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 端点真的把 kwargs 交给了调度器（不是算出来却没传）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_endpoint_forwards_row_level_kwargs_to_resolver(monkeypatch) -> None:
    """`customer_name` 必须出现在 `resolve_auto_data_source` 的调用 kwargs 里。

    这是整条链路的**唯一**关键接缝：算出 kwargs 却忘了传进去，UI 表现与从前一模一样
    （永远空白），而「函数存在」类判据全绿。
    """
    seen: dict[str, object] = {}

    async def _spy(db, project_id, year, source, **kwargs):  # noqa: ANN001
        seen["project_id"] = project_id
        seen["year"] = year
        seen["source"] = source
        seen["kwargs"] = kwargs
        return {"summary": "ok", "sales_amount": 1.0}

    monkeypatch.setattr(auto_data, "resolve_auto_data_source", _spy)

    req = _FakeRequest({"year": "2025", "customer_name": "甲公司"})
    out = await auto_data.get_auto_data(
        project_id="11111111-1111-1111-1111-111111111111",  # type: ignore[arg-type]
        source="d4_25_dealer_sales",
        request=req,  # type: ignore[arg-type]
        year=2025,
        db=None,  # type: ignore[arg-type]
    )

    assert out == {"summary": "ok", "sales_amount": 1.0}
    assert seen["source"] == "d4_25_dealer_sales"
    assert seen["year"] == 2025
    assert seen["kwargs"] == {"customer_name": "甲公司"}, (
        "行级参数没进 resolver —— 表间提取会恒返回空"
    )


@pytest.mark.asyncio
async def test_unregistered_source_still_reports_error_shape(monkeypatch) -> None:
    """未注册数据源仍返回 `_error` 形态（透传改动不得吃掉这条既有契约）。"""

    async def _none(db, project_id, year, source, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr(auto_data, "resolve_auto_data_source", _none)
    out = await auto_data.get_auto_data(
        project_id="11111111-1111-1111-1111-111111111111",  # type: ignore[arg-type]
        source="__nope__",
        request=_FakeRequest({"year": "2025"}),  # type: ignore[arg-type]
        year=2025,
        db=None,  # type: ignore[arg-type]
    )
    assert out["_error"] is True
    assert "__nope__" in out["summary"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. 四个 IPO resolver 的返回键 = 前端 resolverField 声明（跨语言字段契约，后端侧）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("resolver_name", "expected_fields"),
    [
        ("d4_25_dealer_sales", {"sales_amount", "ar_balance"}),
        ("d4_26_overseas_sales", {"sales_amount"}),
        ("d4_27_related_party_sales", {"annual_sales"}),
        ("d4_28_customer_balances", {"sales_amount", "ar_balance", "contract_liab_balance"}),
    ],
)
def test_ipo_resolver_returns_declared_fields(resolver_name: str, expected_fields: set[str]) -> None:
    """resolver 源码里必须出现前端声明的返回键（改名/拼错即红）。

    前端 `IPO_FORMULA_PRESETS[].resolverField` 按这些键取值；键改了前端就取不到，
    而前端那侧的守卫只扫后端源码文本 —— 两侧各有一半，这里补后端侧。
    """
    from app.services.auto_data_resolvers import _REGISTRY

    fn = _REGISTRY.get(resolver_name)
    assert fn is not None, f"{resolver_name} 未注册"
    src = inspect.getsource(fn)
    missing = {f for f in expected_fields if f'"{f}"' not in src and f"'{f}'" not in src}
    assert not missing, f"{resolver_name} 返回体缺键 {missing}（前端 resolverField 会取不到值）"


def test_selfcheck_nonexistent_field_is_detected() -> None:
    """反向自检：编造的键必须判缺（否则上一条是假绿）。"""
    from app.services.auto_data_resolvers import _REGISTRY

    src = inspect.getsource(_REGISTRY["d4_25_dealer_sales"])
    assert '"sales_amount"' in src
    assert '"__definitely_not_a_field__"' not in src
