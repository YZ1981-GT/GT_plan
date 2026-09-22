# -*- coding: utf-8 -*-
"""post-durable 失败的**真因**必须能被前端读到。

2026-09-22 真栈实测的可用性缺陷：在 OnlyOffice 里往「本月金额」这类 ``amount`` 列填了
一段文本，回写走到 rematerialize 失败，错误码 ``excel_materialize_editable_write_failed``
**只进了后端日志**：

* `working_paper_sync_operation.error_code` = NULL
  （`apply_durable_incoming` 在 durable 之后刻意不抛，AC 5.7/5.8，失败只表现为
   `result.result`，落库落在 application 事件流）
* `GET .../operations/{id}` 因此回 `error_code: null`
* 界面只剩一句「同步失败」—— 用户看不出「这一列要数字」

本文件锁三条：
1. 读侧投影真的从 application 事件流取到码与阶段；
2. 中文措辞来自**后端单源词表**，未登记的码不编措辞（返回 None，让 UI 显示码本身）；
3. 没有失败事件时三项都是 None（不得把「没失败」投影成空字符串之类的假信号）。
"""
from __future__ import annotations

import inspect

import pytest

from app.routers import wp_sync_router as router_mod
from app.services.workpaper_sync.excel_materialize import FAILURE_KINDS
from app.services.workpaper_sync.failure_wording import (
    describe_sync_failure_code,
    iter_registered_failure_codes,
)


# ═══ 1. 措辞单源 ═══


def test_every_registered_code_resolves_to_its_registry_text() -> None:
    codes = iter_registered_failure_codes()
    assert codes, "失败码词表为空 —— 判据会恒真（假绿）"
    for code in codes:
        text = describe_sync_failure_code(code)
        assert text, f"{code} 查不到中文说明"
        assert text.strip() == text and len(text) > 4


def test_wording_is_not_a_second_copy_but_the_engine_registry_itself() -> None:
    """措辞必须来自引擎模块的词表；抄一份必然漂移。"""
    for code, expected in FAILURE_KINDS.items():
        assert describe_sync_failure_code(code) == expected, (
            f"{code} 的说明与 excel_materialize.FAILURE_KINDS 不一致 —— "
            "出现了第二份措辞副本，后续必然漂移"
        )


@pytest.mark.parametrize("unknown", ["", "   ", "nope_not_registered", "excel_materialize_"])
def test_unregistered_codes_are_not_given_invented_wording(unknown: str) -> None:
    assert describe_sync_failure_code(unknown) is None, (
        "给未登记的码编了措辞 —— 那会把「没人维护的码」伪装成「已知原因」"
    )


# ═══ 2. 读侧投影的接线 ═══


def test_operation_endpoint_projects_the_application_failure_facts() -> None:
    source = inspect.getsource(router_mod.get_operation)
    assert "_application_failure_facts" in source, (
        "operation 端点没有投影 application 侧失败真因 —— 前端只能拿到 null"
    )

    helper = inspect.getsource(router_mod._application_failure_facts)
    assert "WorkpaperContentApplicationEvent" in helper, (
        "真因不在 application 行上而在**事件流**里（error_code 列），必须读事件表"
    )
    assert "sequence_no" in helper and "desc()" in helper, (
        "必须取**最后一条**带 error_code 的事件；取首条会拿到早期无关失败"
    )
    assert "error_code.isnot(None)" in helper, (
        "必须只挑带 error_code 的事件；否则会取到一条正常 state_changed 而投影出 None"
    )
    assert "describe_sync_failure_code" in helper, "中文措辞必须走后端单源词表"


def test_projection_is_read_only() -> None:
    """投影只读：不得在查询端点里写状态（那会让 GET 有副作用）。"""
    helper = inspect.getsource(router_mod._application_failure_facts)
    for forbidden in ("session.add", "flush", "commit", "update(", "delete("):
        assert forbidden not in helper, (
            f"读侧投影里出现 {forbidden!r} —— GET 端点不得改状态"
        )


def test_projection_keys_are_exactly_the_three_declared_fields() -> None:
    """键集合固定：多一个少一个都会让前端 DTO 与后端漂移。"""
    default_block = inspect.getsource(router_mod.get_operation)
    for key in (
        "application_error_code",
        "application_error_stage",
        "application_error_message",
    ):
        assert f'"{key}": None' in default_block, (
            f"{key} 没有在 app_facts 的默认值里声明 —— pre-correlation shell 阶段"
            "会整键缺失，前端读到 undefined 而不是 null"
        )
