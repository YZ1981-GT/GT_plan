"""RV12.0-01 守卫：目录外命中的 display_label 必须等于目录同一函数的现算结果。

背景：L1 条目的 display_label 由生成器写进目录；而 L3 运行时条目与非底稿域委托 V1
的结果不在目录里，由 `resolve_identity.computed_display_label` 调 `display.cell_labels`
现算。此前只有「登记制守卫的语法树判据」盯着这件事（断言函数被调用），没有行为用例
——把 L3 的语义标签换成 None 之类的改动不会打红。本文件按**独立现算**逐例比对。

判据：
1. L3 单命中：display_label == display.cell_labels(wp_code, {坐标, 语义})[1]
2. L3 多命中：每个候选的 display_label 同上
3. 非底稿域委托 V1：display_label == display.cell_labels("源/路径", {列, None})[1]
4. 语义标签与分隔符真的参与：换掉语义标签，结果随之变（否则 RV12-X6 那类变异不打红）

变异（RV12-X6 / RV12-X7）：把 `_build_runtime_resolve_result` 的语义标签传成 None、
或把 display_label 置空 → 第 1、2、4 组用例红。
"""
from __future__ import annotations

import pytest

from app.services.acnr import display
from app.services.acnr.resolver import full_resolve
from app.services.acnr.runtime import RuntimeCellEntry, _l3_store


def expected_label(head: str, cell_address: str | None, semantic_label: str | None) -> str:
    """独立现算：直接调目录用的那个函数，不经被测路径。"""
    return display.cell_labels(
        head, {"cell_address": cell_address, "semantic_label": semantic_label}
    )[1]


def _entry(project_id: str, cell: str, semantic: str, *, wp_code: str = "CUST-01",
           wp_id: str = "wp-rv12") -> RuntimeCellEntry:
    return RuntimeCellEntry(
        addr_id=f"runtime/{project_id}/{wp_id}/{wp_code}/{cell}",
        uri=f"wp://{wp_code}/{cell}",
        formula_ref=f"WP('{wp_code}','{cell}')",
        project_id=project_id,
        wp_id=wp_id,
        cell_address=cell,
        semantic_label=semantic,
        wp_code=wp_code,
    )


@pytest.fixture
def l3_project():
    """造一个只属本用例的 L3 命名空间，用完清掉。"""
    project_id = "proj-rv12-display"
    _l3_store.pop(project_id, None)
    yield project_id
    _l3_store.pop(project_id, None)


# ─── 1. L3 单命中 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_hit_display_label_matches_catalog_function(l3_project: str) -> None:
    entry = _entry(l3_project, "B7", "自定义格")
    _l3_store[l3_project] = {entry.addr_id: entry}

    result = await full_resolve(addr_id=entry.addr_id, project_id=l3_project)

    assert result.found is True
    assert result.source_layer == "L3"
    assert result.display_label == expected_label("CUST-01", "B7", "自定义格")
    # 现算值形态自证：分隔符与两段都在，避免「两边都算成空」的恒真比较
    assert result.display_label == f"CUST-01{display.CELL_SEPARATOR}B7 自定义格"


@pytest.mark.asyncio
async def test_runtime_hit_semantic_label_participates(l3_project: str) -> None:
    """语义标签真的进显示名：换语义标签，显示名随之变。"""
    first = _entry(l3_project, "B7", "自定义格")
    _l3_store[l3_project] = {first.addr_id: first}
    label_a = (await full_resolve(addr_id=first.addr_id, project_id=l3_project)).display_label

    second = _entry(l3_project, "B7", "期末余额")
    _l3_store[l3_project] = {second.addr_id: second}
    label_b = (await full_resolve(addr_id=second.addr_id, project_id=l3_project)).display_label

    assert label_a != label_b
    assert label_a == expected_label("CUST-01", "B7", "自定义格")
    assert label_b == expected_label("CUST-01", "B7", "期末余额")


@pytest.mark.asyncio
async def test_runtime_hit_without_semantic_label(l3_project: str) -> None:
    """没有语义标签时只剩坐标，仍与目录函数一致。"""
    entry = _entry(l3_project, "C10", "")
    _l3_store[l3_project] = {entry.addr_id: entry}

    result = await full_resolve(addr_id=entry.addr_id, project_id=l3_project)

    assert result.found is True
    assert result.display_label == expected_label("CUST-01", "C10", "")
    assert result.display_label == f"CUST-01{display.CELL_SEPARATOR}C10"


# ─── 2. L3 多命中：候选项的显示名 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_ambiguous_candidates_carry_computed_labels(l3_project: str) -> None:
    """同一自定义格命中多个运行时条目时，每个候选的显示名都按目录函数现算。"""
    a = _entry(l3_project, "B7", "甲公司", wp_id="wp-a")
    b = _entry(l3_project, "B7", "乙公司", wp_id="wp-b")
    _l3_store[l3_project] = {a.addr_id: a, b.addr_id: b}

    result = await full_resolve(formula_ref="WP('CUST-01','B7')", project_id=l3_project)

    assert result.found is False
    assert result.error == "ambiguous"
    assert result.source_layer == "L3"
    # T31：多命中也要给可解释字段
    assert result.reason and result.next_step and result.required_context

    got = {c["addr_id"]: c["display_label"] for c in (result.candidates or [])}
    assert set(got) == {a.addr_id, b.addr_id}
    assert got[a.addr_id] == expected_label("CUST-01", "B7", "甲公司")
    assert got[b.addr_id] == expected_label("CUST-01", "B7", "乙公司")
    assert got[a.addr_id] != got[b.addr_id]


# ─── 3. 非底稿域委托 V1 ────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "uri,head,cell",
    [
        ("tb://1001#期末余额", "1001", "期末余额"),
        ("note://五、3", "五、3", ""),
    ],
)
async def test_v1_delegate_display_label_matches_catalog_function(
    uri: str, head: str, cell: str
) -> None:
    """非底稿域的显示名由同一函数现算。

    不带项目上下文时 found=False（`project_context_required`：存在性要按项目数据判，
    design §2.2），但显示名在 `_delegate_v1` 里已经算好并原样返回 —— 本用例盯的就是
    这个字段，不是存在性。
    """
    result = await full_resolve(uri=uri)

    assert result.source_layer == "V1"
    assert result.error == "project_context_required"
    assert result.display_label == expected_label(head, cell, None)
    assert result.display_label, "非底稿域也要有显示名"


@pytest.mark.asyncio
async def test_v1_delegate_label_contains_separator_when_cell_present() -> None:
    """带列的非底稿域：显示名是「源 › 列」，分隔符与两段都在。"""
    result = await full_resolve(uri="tb://1001#期末余额")
    assert result.display_label == f"1001{display.CELL_SEPARATOR}期末余额"


@pytest.mark.asyncio
async def test_v1_delegate_label_has_no_dangling_separator() -> None:
    """没有列时只显示源，不留「五、3 › 」这种后面空无一物的分隔符（T31 现算发现）。"""
    result = await full_resolve(uri="note://五、3")
    assert result.display_label == "五、3"
    assert not result.display_label.endswith(display.CELL_SEPARATOR.rstrip())
    assert display.CELL_SEPARATOR not in result.display_label
