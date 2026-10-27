"""acnr_targets 解析编排、拒绝分类与唯一读取函数（acnr-foundation-defect-closure T14，design §2.3，需求 1.2 / 1.3）。

- AST：``acnr_target_values`` 与 ``wp_cell_target`` 不读 ``parsed_data``、不调 ``extract_custom_cells``；前者取值只经
  ``read_entry_cell``，后者只经共享读取函数 ``resolve_wp_cell``；resolver 只产出 L1_cell / L1_sheet / L3 / V1（R2-N10）。
- 分类：真实目录 + 真实 ``AddressingService``（不 mock 解析）每种拒绝码一例 ⇒ 422 ``ACNR_TARGETS_REJECTED``，issues
  逐项给原文 / 码 / 中文原因 / 候选；运行时条目与解析不可用用替身给出结果字段。全部拒绝路径 spy
  ``resolve_wp_cell`` 与 ``read_entry_cell`` 调用 0 次。
- R2-F9：解析桩每项睡 6 秒 ⇒ 整批在 ``ACNR_BATCH_DEADLINE_S`` 加余量内返回 503，取数 0 次；首个不可用即停。
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.acnr import resolver as resolver_mod
from app.services.acnr import wp_cell_target
from app.services.acnr.catalog import get_catalog
from app.services.acnr.limits import ACNR_BATCH_DEADLINE_S
from app.services.acnr.resolver import ResolveResult
from app.services.custom_query import acnr_target_values
from app.services.custom_query.acnr_target_values import classify_target, resolve_acnr_targets
from app.services.custom_query.addressing_service import AddressingService, ResolvedTarget

_READERS = ("resolve_wp_cell", "read_entry_cell")


def _names(module) -> set[str]:
    tree = ast.parse(inspect.getsource(module))
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}


def _called(module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Call):
            fn = node.func
            out.add(fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else "")
    return out


def _string_subscripts(module) -> set[str]:
    return {n.slice.value for n in ast.walk(ast.parse(inspect.getsource(module)))
            if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str)}


@pytest.mark.parametrize("module", [acnr_target_values, wp_cell_target])
def test_value_path_never_touches_parsed_data(module):
    names = _names(module)
    assert "parsed_data" not in names and "extract_custom_cells" not in names
    assert not {"parsed_data", "html_data", "cells"} & _string_subscripts(module)


def test_value_path_reads_only_through_shared_reader():
    assert "read_entry_cell" in _called(acnr_target_values)
    assert "resolve_wp_cell" not in _names(acnr_target_values)  # 直调会绕过 sheet 键与绑定规则
    assert "resolve_wp_cell" in _called(wp_cell_target)


def test_resolver_layers_are_closed_set():
    """R2-N10：resolver 的 source_layer 字面量只有四种（overlay 命中也走 L1_cell 构建函数，不出现 "L2"）。"""
    tree = ast.parse(Path(resolver_mod.__file__).read_text(encoding="utf-8"))
    layers = {kw.value.value for n in ast.walk(tree) if isinstance(n, ast.Call) for kw in n.keywords
              if kw.arg == "source_layer" and isinstance(kw.value, ast.Constant)}
    assert layers == {"L1_cell", "L1_sheet", "L3", "V1", None}


# ── 分类：真实解析 ────────────────────────────────────────────────────────────

@pytest.fixture
def spies(monkeypatch):
    calls = {name: 0 for name in _READERS}

    def _spy(name):
        async def _fn(*_a, **_k):
            calls[name] += 1
            raise AssertionError(f"拒绝路径不得取数：{name}")
        return _fn

    monkeypatch.setattr(wp_cell_target, "resolve_wp_cell", _spy("resolve_wp_cell"))
    monkeypatch.setattr(acnr_target_values, "read_entry_cell", _spy("read_entry_cell"))
    return calls


def _deprecated_cell() -> str:
    return sorted(a for a, c in get_catalog().cells_by_addr_id.items() if c.get("deprecated"))[0]


_REAL_CASES = [
    ("adj:aje", "external_namespace"),
    ("TB('1001','审定数')", "unsupported_domain"),
    ("E1/E1-14", "sheet_level"),
    ("<deprecated>", "deprecated"),
    ("WP('F2','底稿目录','B20')", "ambiguous"),
    ("ZZZ/不存在/A1", "unresolvable"),
]


async def _reject(targets, addressing=None):
    with pytest.raises(HTTPException) as info:
        await resolve_acnr_targets(targets, project_id=None, db=None, addressing=addressing)
    return info.value


@pytest.mark.parametrize("raw, code", _REAL_CASES, ids=[c for _, c in _REAL_CASES])
async def test_each_rejection_code_is_422_and_reads_nothing(spies, raw, code):
    raw = _deprecated_cell() if raw == "<deprecated>" else raw
    exc = await _reject(["E1/E1-14/C10", raw])
    assert exc.status_code == 422
    detail = exc.detail
    assert detail["error_code"] == "ACNR_TARGETS_REJECTED"
    assert detail["message"] == "所选单元格中有 1 项无法取值，未执行查询"
    (issue,) = detail["issues"]
    assert (issue["ref"], issue["error_code"]) == (raw, code)
    assert any("\u4e00" <= ch <= "\u9fff" for ch in issue["message"]), issue  # 中文原因
    assert set(issue) == {"ref", "error_code", "message", "candidates", "required_context"}
    assert spies == {name: 0 for name in _READERS}


async def test_deprecated_issue_offers_replacement_not_followed(spies):
    raw = _deprecated_cell()
    cell = get_catalog().cells_by_addr_id[raw]
    (issue,) = (await _reject([raw])).detail["issues"]
    assert issue["candidates"] == [cell["replaced_by"]] and "停用" in issue["message"]


async def test_ambiguous_issue_carries_candidates_and_context(spies):
    (issue,) = (await _reject(["WP('F2','底稿目录','B20')"])).detail["issues"]
    assert issue["required_context"] == ["sheet_code"]
    assert 1 < len(issue["candidates"]) <= 5 and all("/" in c for c in issue["candidates"])


async def test_every_bad_item_listed_in_order(spies):
    raws = ["ZZZ/不存在/A1", "E1/E1-14/C10", "E1/E1-14", "adj:aje"]
    issues = (await _reject(raws)).detail["issues"]
    assert [(i["ref"], i["error_code"]) for i in issues] == [
        ("ZZZ/不存在/A1", "unresolvable"), ("E1/E1-14", "sheet_level"), ("adj:aje", "external_namespace")]


async def test_all_l1_cells_accepted_in_order_with_duplicates():
    raws = ["E1/E1-14/C10", "WP('E1','货币资金分析表E1-14','C10')", "E1/E1-14/C10", "cell:E1-14!C10"]
    got = await resolve_acnr_targets(raws, project_id=None, db=None)
    assert [t.raw for t in got] == raws
    assert [t.addr_id for t in got] == ["E1/E1-14/C10"] * 4
    assert all(classify_target(t) is None and t.result.source_layer == "L1_cell" for t in got)


# ── 替身给结果字段：运行时条目、解析不可用、超时 ───────────────────────────────

class _Stub(AddressingService):
    def __init__(self, plan):
        self.plan = plan
        self.calls: list[str] = []

    async def resolve_target(self, raw, *, project_id=None, db=None, timeout_s=5.0):
        self.calls.append(raw)
        step = self.plan(raw)
        if isinstance(step, (int, float)):
            await asyncio.sleep(step)
            return ResolvedTarget(raw=raw, found=True, addr_id="E1/E1-14/C10", entry_type="cell",
                                  result=ResolveResult(found=True, addr_id="E1/E1-14/C10", entry_type="cell",
                                                       source_layer="L1_cell"))
        return step


def _runtime(raw):
    res = ResolveResult(found=True, addr_id=f"rt:{raw}", entry_type="runtime_cell", source_layer="L3")
    return ResolvedTarget(raw=raw, found=True, addr_id=res.addr_id, entry_type="runtime_cell", result=res)


def _unavailable(raw):
    return ResolvedTarget(raw=raw, found=False, error="resolve_unavailable")


async def test_runtime_entry_rejected(spies):
    (issue,) = (await _reject(["x"], addressing=_Stub(_runtime))).detail["issues"]
    assert issue["error_code"] == "runtime_entry" and "运行时" in issue["message"]


async def test_first_unavailable_stops_and_is_503(spies):
    stub = _Stub(lambda raw: _unavailable(raw) if raw == "b" else 0)
    exc = await _reject(["a", "b", "c", "d"], addressing=stub)
    assert exc.status_code == 503 and exc.detail["error_code"] == "RESOLVE_UNAVAILABLE"
    assert exc.detail["message"] == "地址解析服务暂不可用，未执行查询，请稍后重试"
    assert [i["ref"] for i in exc.detail["issues"]] == ["b"]
    assert stub.calls == ["a", "b"]  # 不把剩下的跑完
    assert spies == {name: 0 for name in _READERS}


async def test_unavailable_outranks_rejections(spies):
    """先有不合格项、后有不可用 ⇒ 仍是 503（服务不可用更需明示）。"""
    stub = _Stub(lambda raw: _runtime(raw) if raw == "a" else _unavailable(raw))
    assert (await _reject(["a", "b"], addressing=stub)).status_code == 503


async def test_whole_batch_deadline_is_503(spies):
    """R2-F9：每项睡 6 秒，整批在时限加余量内结束并返回 503，取数 0 次。"""
    stub = _Stub(lambda raw: 6)
    t0 = time.monotonic()
    exc = await _reject(["a", "b", "c"], addressing=stub)
    elapsed = time.monotonic() - t0
    assert exc.status_code == 503 and exc.detail["error_code"] == "RESOLVE_UNAVAILABLE"
    assert elapsed <= ACNR_BATCH_DEADLINE_S + 1.5, elapsed
    assert stub.calls == ["a", "b"] and exc.detail["issues"][0]["ref"] == "b"
    assert spies == {name: 0 for name in _READERS}


async def test_empty_targets_resolve_nothing():
    stub = _Stub(lambda raw: 0)
    assert await resolve_acnr_targets([], project_id=None, db=None, addressing=stub) == []
    assert stub.calls == []
