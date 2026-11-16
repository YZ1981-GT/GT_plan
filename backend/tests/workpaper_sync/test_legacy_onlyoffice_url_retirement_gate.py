"""旧式 OnlyOffice URL 停止签发门（spec 任务 2.8 第 ① 步）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`

## 这个门要防什么

`/sheets/{sheet}/onlyoffice-config` 是**旧式**链路入口：它签发
`wopi/contents` + `/onlyoffice-callback` 两个 URL，而那三个端点各自解析一次目标文件
⇒ writer gate 的 `multi_resolver` 把三行全部点名。只要这条路径还在生产上签发 URL，
「优先级链单一来源」就做不到 —— 删了调用方它还会被新代码调回来。

## 判据为什么用 `readiness.runtime.ready`

「这个 entry 能不能走 room 协议」已经有唯一答案（`evaluate_entry_readiness`），
前端「在线编辑不可用」的提示、`GET /sync/entries/{id}/readiness` 都读它。
本文件**不重造**那套判定，只验证「门读的确实是它」。

## 三条臂（缺任一条这类门就会退化成恒绿 / 恒红）

1. **拒绝态**：room 供给就绪 ⇒ 409 + `legacy_onlyoffice_url_retired` + 可操作文案
2. **fail-open 态**：供给不就绪 ⇒ 照旧签发（**否则一批 entry 直接打不开**）
3. **判据缺失态**：readiness 算不出来（entry 不在 manifest 等）⇒ 也照旧签发

臂 2 / 3 是本文件的核心：只测「该拒的拒了」会让判据在「一律 409」的实现下依旧全绿，
而那正是比 `multi_resolver` 更重的事故。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

#: 本文件在 `backend/tests/workpaper_sync/` 下 ⇒ parents[2] 就是 `backend/`。
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ROOT = BACKEND_ROOT.parent
ROUTER_PATH = BACKEND_ROOT / "app/routers/wp_onlyoffice_router.py"
#: 门的**实现**在伴生模块（行数门要求从宿主抽出）。宿主只留一行 import 别名。
GATE_PATH = BACKEND_ROOT / "app/routers/_wp_onlyoffice_legacy_url_gate.py"


def _load_router_module() -> Any:
    """按文件路径加载 router（不经过包 import，避免拉整个 app 的启动副作用）。"""
    if "legacy_oo_gate_router_probe" in sys.modules:
        return sys.modules["legacy_oo_gate_router_probe"]
    spec = importlib.util.spec_from_file_location("legacy_oo_gate_router_probe", ROUTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["legacy_oo_gate_router_probe"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def router_module() -> Any:
    return _load_router_module()


def _readiness(*, ready: bool, entry_id: str = "xlsx-sheet/D4-1/__whole__") -> SimpleNamespace:
    """最小 readiness 替身 —— 只带门真正读取的三个字段。"""
    return SimpleNamespace(
        runtime=SimpleNamespace(ready=ready),
        effective_entry_id=entry_id,
        allowed_modes=("html", "onlyoffice") if ready else ("html",),
    )


def _gate(
    router_module: Any,
    readiness_obj: Any | None,
    *,
    raises: Exception | None = None,
    binding_status: str = "no_binding",
):
    """在 readiness 打桩下调用门，返回它抛的异常（没抛则 None）。

    🔴 2.6 起门分两层：binding 状态机优先，binding 无结论才走 readiness。本文件测的是
    **readiness 那一层**，所以默认把 binding 层打桩成 `no_binding`；binding 层的三条臂
    在 `test_sheet_legacy_gate_binding_states.py`。
    """
    target = (
        "app.services.workpaper_sync.entry_readiness.evaluate_entry_readiness"
    )
    binding_target = (
        "app.routers._wp_onlyoffice_legacy_url_gate._binding_verdict"
    )

    async def fake_evaluate(**_kwargs: Any) -> Any:
        if raises is not None:
            raise raises
        return readiness_obj

    def fake_binding(**_kwargs: Any):
        if binding_status == "unresolved":
            return "unresolved", None
        return "no_binding", None

    import asyncio

    async def run() -> None:
        await router_module._refuse_legacy_url_when_room_ready(
            AsyncMock(),
            wp_id="wp",
            project_id="proj",
            entry_id="e",
            source_wp_code="D4",
            sheet_name="境外销售收入检查D4-26",
            whole_workbook=False,
        )

    with patch(target, new=fake_evaluate), patch(binding_target, new=fake_binding):
        try:
            asyncio.run(run())
        except HTTPException as exc:
            return exc
    return None


# ════════════════════════════════════════════════════════════════════════════
# 臂 1：供给就绪 ⇒ 拒绝（且码与文案可操作）
# ════════════════════════════════════════════════════════════════════════════


def test_ready_entry_is_refused_with_an_actionable_code(router_module: Any) -> None:
    exc = _gate(router_module, _readiness(ready=True))
    assert exc is not None, "room 供给已就绪，旧式签发竟被放行 —— 门形同不存在"
    assert exc.status_code == 409, (
        f"拒绝码应是 409（当前状态不允许、状态变了就能做），实得 {exc.status_code}"
    )
    detail = exc.detail
    assert isinstance(detail, dict), f"detail 必须是结构化 dict，实得 {type(detail)}"
    assert detail["error_code"] == "legacy_onlyoffice_url_retired"
    message = str(detail["message"])
    assert message, "错误文案不能为空 —— 界面要显示它而不是空白"
    assert "统一在线编辑协议" in message or "协同编辑" in message, (
        f"文案必须告诉用户下一步做什么（走协同编辑入口），实得：{message!r}"
    )
    assert detail["allowed_modes"] == ["html", "onlyoffice"], (
        "必须把该 entry 真实可用模式带出去，前端据此展示切换入口"
    )


def test_refusal_names_the_effective_entry_not_the_requested_one(router_module: Any) -> None:
    """回执里的 entry_id 必须是 effective entry —— 前端要拿它去调 materialize。

    请求的 entry 与 effective 不一致（alias）时，用请求值会让前端去 materialize
    一个不存在的 entry，表现为「点了没反应」而不是可归因的错误。
    """
    exc = _gate(router_module, _readiness(ready=True, entry_id="xlsx/gt-d4-operating-revenue"))
    assert exc is not None
    assert exc.detail["entry_id"] == "xlsx/gt-d4-operating-revenue"


# ════════════════════════════════════════════════════════════════════════════
# 臂 2：供给不就绪 ⇒ 照旧签发（核心反面臂）
# ════════════════════════════════════════════════════════════════════════════


def test_not_ready_entry_still_gets_the_legacy_url(router_module: Any) -> None:
    """room 供给未就绪时必须放行。

    🔴 这条是「门不是对任何输入都拒绝」的**唯一**证据。删掉它之后，
    把实现改成「无条件 raise 409」也能让臂 1 全绿 —— 而那会让一批 entry
    彻底打不开在线编辑（Requirement 12.8：不得做假切换 / 不得让入口失效）。
    """
    exc = _gate(router_module, _readiness(ready=False))
    assert exc is None, (
        "room 供给未就绪却被拒绝 —— 该 entry 将同时失去旧式与 room 两条路，"
        f"等于在线编辑彻底打不开（实得 {exc.detail if exc else ''}）"
    )


# ════════════════════════════════════════════════════════════════════════════
# 臂 3：判据算不出来 ⇒ 也照旧签发（fail-open 的方向必须是这一侧）
# ════════════════════════════════════════════════════════════════════════════


def test_readiness_failure_falls_open_to_the_legacy_url(router_module: Any) -> None:
    """readiness 抛异常（entry 不在 manifest / adapter 未注册）时必须放行。

    这些 entry 本来就进不了 room（没 representation 就没法 materialize），
    拒绝它们 = 两条路都没有。fail-open 到旧路径是**有意**的选择，不是遗漏。
    """
    exc = _gate(router_module, None, raises=RuntimeError("entry 不在 current manifest"))
    assert exc is None, "readiness 算不出来时拒绝签发 —— 那批 entry 将彻底打不开底稿"


# ════════════════════════════════════════════════════════════════════════════
# 门读的确实是唯一判据（不另造一套资格判定）
# ════════════════════════════════════════════════════════════════════════════


def test_gate_delegates_to_the_single_readiness_source() -> None:
    """门必须调 `evaluate_entry_readiness`，不得自己重新判资格。

    源码形态判据，但它判的是**接线**不是措辞：自己重写一套资格判定时，
    新增一条资格条件会让这里静默放行（本 spec 反复付过这个代价）。
    """
    # 门实现在伴生模块；宿主只留别名 import（`test_host_re_exports_the_gate` 钉住它）。
    source = GATE_PATH.read_text(encoding="utf-8")
    body = source
    assert "evaluate_entry_readiness" in body, (
        "门没调 evaluate_entry_readiness —— 它必须复用唯一判据，不得另造资格判定"
    )
    assert "runtime.ready" in body, "门没读 runtime.ready"
    # 反面：门里不得**重写**一套 readiness 资格判定。
    #
    # 🔴 2.6 起 `load_entry_manifest` 从禁止改成允许：binding 层要按 manifest 校验
    #    entry 是否真实存在（Requirement 1.1 的显式真源）。真正要禁的是「自己判
    #    capability / intent policy」—— 那才是会让两处口径分叉的第二套资格判定。
    for forbidden in ("INTENT_POLICY", "capability_of", "Capability("):
        assert forbidden not in body, (
            f"门里出现了 {forbidden} —— 那是第二套资格判定，会让两处口径分叉"
        )


def test_host_re_exports_the_gate_under_the_original_name() -> None:
    """宿主必须用**原名**再导出，否则调用点静默失配（抽模块最容易踩的坑）。

    判据用 AST 认 `from app.routers._wp_onlyoffice_legacy_url_gate import (… as …)`，
    不靠子串：别名写错时字符串仍然在，但调用会 NameError。
    """
    import ast

    tree = ast.parse(ROUTER_PATH.read_text(encoding="utf-8"))
    aliases = {
        (alias.asname or alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").endswith("_wp_onlyoffice_legacy_url_gate")
        for alias in node.names
    }
    assert "_refuse_legacy_url_when_room_ready" in aliases, (
        "宿主没有以原名再导出闸门函数 —— 调用点会 NameError"
        f"（现有别名：{sorted(aliases)}）"
    )


def test_flag_defaults_to_issuing_legacy_urls() -> None:
    """开关默认值必须是 `True`（沿用旧行为）。

    默认 `False` 会让所有未跟进的前端调用方立刻 409 —— 那不是「停止签发」，
    那是发布事故，且没有 drain 窗口。
    """
    from app.core.config import Settings

    field = Settings.model_fields["ONLYOFFICE_LEGACY_URL_ISSUE"]
    assert field.default is True, (
        f"ONLYOFFICE_LEGACY_URL_ISSUE 默认值应为 True（零回归），实得 {field.default!r}"
    )


def test_router_consults_the_flag_before_signing() -> None:
    """config 端点必须在签发前**真的读**这个开关，否则开关是死配置。

    🔴 判据必须走 AST，不能子串匹配。实测教训（M8 变异存活）：原判据是
    `"settings.ONLYOFFICE_LEGACY_URL_ISSUE" in source`，而变异把整段条件改成
    `if False:` 之后，**那个字符串仍然留在同一行**（`if False and settings.…`）⇒
    判据照绿，而门已经永不执行。这正是㉖「判断代码是否真做了 X 一律用 AST」的现场。
    """
    import ast

    source = ROUTER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # ① 存在一处 `settings.ONLYOFFICE_LEGACY_URL_ISSUE` 的**属性读取**（不是字符串里提一句）
    reads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "ONLYOFFICE_LEGACY_URL_ISSUE"
        and isinstance(node.value, ast.Name)
        and node.value.id == "settings"
    ]
    assert reads, (
        "router 里没有真实读取 settings.ONLYOFFICE_LEGACY_URL_ISSUE 的属性访问 —— "
        "开关是死配置（写了字符串不算）"
    )

    # ② 每处读取都必须处在一个 `if` 的条件里，且该条件**不含恒假常量**
    #    （`if False and settings.X:` 会被 AST 看成含该属性，但门永不执行）
    read_ids = {id(node) for node in reads}
    effective = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        in_this_condition = {
            id(sub) for sub in ast.walk(node.test)
        } & read_ids
        if not in_this_condition:
            continue
        has_always_false = any(
            isinstance(sub, ast.Constant) and sub.value is False
            for sub in ast.walk(node.test)
        )
        if not has_always_false:
            effective = True
            break
    assert effective, (
        "settings.ONLYOFFICE_LEGACY_URL_ISSUE 没有出现在任何**有效**的 if 条件里 —— "
        "读了却不判、或被 `and False` 短路，门等于不存在"
    )

    # ③ 顺序：门必须在 URL 拼接之前（否则已经签发了才判）
    gate_at = source.index("await _refuse_legacy_url_when_room_ready")
    url_at = source.index(
        'f"{base_url}/api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents"'
    )
    assert gate_at < url_at, (
        "门在 URL 拼接之后才执行 —— 那时 URL 已经签出来了，门等于没拦"
    )


def test_ast_flag_predicate_rejects_a_short_circuited_flag() -> None:
    """上一条谓词的双向自检：`if False and settings.X:` 必须判否。

    这是 M8 变异存活后补的：门写了、字符串也在，但条件恒假 ⇒ 永不执行。
    只测「源码里出现过这个字符串」的判据对这类改动完全失明。
    """
    import ast

    def flag_is_effective(src: str) -> bool:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            for sub in ast.walk(node.test):
                if (
                    isinstance(sub, ast.Attribute)
                    and sub.attr == "ONLYOFFICE_LEGACY_URL_ISSUE"
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == "settings"
                ):
                    # 条件里出现恒假常量 ⇒ 整条 if 永不成立
                    has_false = any(
                        isinstance(c, ast.Constant) and c.value is False
                        for c in ast.walk(node.test)
                    )
                    if not has_false:
                        return True
        return False

    good = "if not settings.ONLYOFFICE_LEGACY_URL_ISSUE:\n    pass\n"
    assert flag_is_effective(good), "正常读开关的写法竟判否"
    shorted = "if False and settings.ONLYOFFICE_LEGACY_URL_ISSUE:\n    pass\n"
    assert not flag_is_effective(shorted), (
        "`if False and settings.…` 竟判为有效 —— 那正是 M8 变异存活的形态"
    )
    only_string = 'x = "settings.ONLYOFFICE_LEGACY_URL_ISSUE"\n'
    assert not flag_is_effective(only_string), "只在字符串里提一句竟判为有效"
