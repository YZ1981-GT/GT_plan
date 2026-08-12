"""批量导出可见集过滤的粒度守卫 —— Wave 6 Task 24

spec: workpaper-import-export-lifecycle-closure（R7.6）

## 守的是什么

`make_bulk_visible_filter` 必须按**整稿**（`wp_id`）判可见性，
**不得**传 `requested_sheet_key`。

## 为什么（2026-08-12 浏览器/HTTP 实测抓到的真缺陷）

批量导出的粒度是整份底稿文件（一个 `wp_id` → 一个 xlsx 进 ZIP），不是页面级
sheet 资源。原实现把 `sheet_code` 传给 `try_gate_wp` 的 `requested_sheet_key`，
额外触发 `SheetBindingCatalog` 的 sheet 成员校验 —— 而该 catalog 的候选集来自
``ProcedureRowTask.sheet_key``，实测**只覆盖 19 / 2802 个 wp_index（0.7%）**。

后果是「四层守卫全绿但产物是空壳」这一类里最严重的一个：

* 99.3% 的底稿被判 `DenialReason.sheet_unmapped` → `visible_filter` 返回 False
* 不可见项按设计**不泄露存在性** ⇒ 连 `manifest.skipped` 都不进
* 用户拿到的 ZIP 只有报表/附注/试算表，**一份底稿都没有，且无任何提示**
* 三个真实项目实测：1025 份 → 0、1017 份 → 0、340 份 → 0

修后同一项目 D 循环：ZIP 底稿条目 0 → **7**，`manifest.files` 0 → 7（各带 sha256），
`skipped` 0 → 74（如实登记）。

## 判据落在「不传 sheet_key」这个行为上

不查字符串，而是**真调闭包**并用一个 spy 记下 `try_gate_wp` 收到的参数 ——
这样即使有人换写法（改成 `requested_sheet_key=None if ... else x`）也拦得住。
"""

from __future__ import annotations

import inspect
import re
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_MODULE = _REPO / "backend" / "app" / "services" / "wp_visibility" / "entry_integration.py"


def test_module_exists() -> None:
    assert _MODULE.is_file(), f"缺少 {_MODULE}"


@pytest.mark.asyncio
async def test_bulk_filter_does_not_pass_sheet_key(monkeypatch) -> None:  # noqa: ANN001
    """🔴 行为判据：闭包调用 `try_gate_wp` 时不得带 `requested_sheet_key`。

    用 spy 替换 `try_gate_wp`，真调一次闭包，检查它实际传了什么。
    比 grep 源码可靠 —— 换成三元表达式、变量中转都逃不掉。
    """
    from app.services.wp_visibility import entry_integration as ei

    captured: dict[str, object] = {}

    async def _spy(db, current_user, **kwargs):  # noqa: ANN001, ANN003, ARG001
        captured.update(kwargs)
        return object()  # 非 None ⇒ 可见

    monkeypatch.setattr(ei, "try_gate_wp", _spy)

    vis = ei.make_bulk_visible_filter(db=None, current_user=object())
    ok = await vis(str(uuid.uuid4()), "D1-1")

    assert ok is True, "spy 返回非 None 时闭包应判可见"
    assert "requested_sheet_key" not in captured or captured["requested_sheet_key"] is None, (
        "批量可见集过滤传了 requested_sheet_key ⇒ 会触发 sheet 成员校验，"
        "而候选集只覆盖 0.7% 的 wp_index ⇒ 99.3% 底稿被静默剔除，ZIP 里没有底稿。\n"
        f"实际传参: {sorted(captured)}"
    )
    assert captured.get("wp_id") is not None, "必须按 wp_id 判整稿可见性"


@pytest.mark.asyncio
async def test_bulk_filter_rejects_bad_wp_id(monkeypatch) -> None:  # noqa: ANN001
    """wp_id 非法/缺失仍必须拒绝（修 sheet 粒度不等于放宽 wp 维度）。"""
    from app.services.wp_visibility import entry_integration as ei

    called = {"n": 0}

    async def _spy(db, current_user, **kwargs):  # noqa: ANN001, ANN003, ARG001
        called["n"] += 1
        return object()

    monkeypatch.setattr(ei, "try_gate_wp", _spy)
    vis = ei.make_bulk_visible_filter(db=None, current_user=object())

    for bad in (None, "", "not-a-uuid"):
        assert await vis(bad, "D1-1") is False, f"wp_id={bad!r} 应判不可见"
    assert called["n"] == 0, "非法 wp_id 不应触达 gate（省一次 DB 往返且避免误判）"


@pytest.mark.asyncio
async def test_bulk_filter_still_fail_closed(monkeypatch) -> None:  # noqa: ANN001
    """gate 返回 None（不可见）时闭包必须返回 False —— fail-closed 不能被削弱。"""
    from app.services.wp_visibility import entry_integration as ei

    async def _deny(db, current_user, **kwargs):  # noqa: ANN001, ANN003, ARG001
        return None

    monkeypatch.setattr(ei, "try_gate_wp", _deny)
    vis = ei.make_bulk_visible_filter(db=None, current_user=object())
    assert await vis(str(uuid.uuid4()), "D1-1") is False


def test_sheet_key_omission_is_documented() -> None:
    """必须写明为什么不传 sheet_key —— 否则下次有人"顺手补上"就回退了。

    这条不是形式主义：该缺陷的表现是「产物变空壳」而非报错，
    回退后没有任何信号，只能靠注释拦住。
    """
    src = _MODULE.read_text(encoding="utf-8")
    fn_src = src[src.index("def make_bulk_visible_filter") :]
    fn_src = fn_src[: fn_src.index("def make_bulk_preflight")]
    assert "requested_sheet_key" in fn_src, "注释里应提到该参数以说明为何不传"
    assert "ProcedureRowTask" in fn_src, "应写明候选集来源（解释覆盖率为何只有 0.7%）"
    for marker in ("整稿", "0.7%"):
        assert marker in fn_src, f"docstring 缺少关键说明: {marker}"


def test_signature_keeps_sheet_code_param() -> None:
    """形参保留 —— 调用方按位置传 sheet_code，删了会 TypeError。

    同时它对审计溯源有价值（知道剔除的是哪张表），只是不参与判定。
    """
    from app.services.wp_visibility.entry_integration import make_bulk_visible_filter

    closure = make_bulk_visible_filter(db=None, current_user=object())
    params = list(inspect.signature(closure).parameters)
    assert len(params) == 2, f"闭包应接受 (wp_id, sheet_code)，实际 {params}"


def test_export_service_still_passes_sheet_code() -> None:
    """反向：导出服务仍按位置传 sheet_code（契约两端一致）。"""
    svc = (
        _REPO / "backend" / "app" / "services" / "bulk_tab" / "bulk_export_service.py"
    ).read_text(encoding="utf-8")
    assert re.search(r"visible_filter\(\s*_e\.wp_id\s*,\s*_e\.sheet_code\s*\)", svc), (
        "bulk_export_service 未按 (wp_id, sheet_code) 调用 visible_filter"
    )


def test_page_level_gate_unaffected() -> None:
    """本改动只动批量闭包，页面级 gate 仍必须能带 sheet_key。

    sheet 级隔离由页面级入口负责；若有人顺手把 `gate_wp` 的该参数也去掉，
    就把页面级隔离一起放宽了。
    """
    from app.services.wp_visibility.entry_integration import gate_wp, try_gate_wp

    for fn in (gate_wp, try_gate_wp):
        assert "requested_sheet_key" in inspect.signature(fn).parameters, (
            f"{fn.__name__} 丢了 requested_sheet_key ⇒ 页面级 sheet 隔离被放宽"
        )
