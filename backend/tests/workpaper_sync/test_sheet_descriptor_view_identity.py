"""`EditorLaunchDescriptor` 的视图身份（target sheet / document scope）冻结守卫。

spec: `onlyoffice-sheet-open-via-published-artifact` task 2.4 / Requirement 3.3 / 3.4 / 8.2

═══ 这个文件补的是什么缺陷 ═══

task 2.4 首版只把 `target_sheet` / `document_scope` 加了字段、加了 `__post_init__` 的封闭域
校验，**没有任何判据看「route 解析出来的值真的走到 descriptor」**。实测磁盘变异 5/5 存活：

* M1 `target_sheet=self._frozen_target_sheet(request)` → `None`：全绿；
* M2 `document_scope=str(request.document_scope)` → `"single_sheet"`：全绿；
* M3 整册视图带 target 的拒绝 → `if False and target:`：全绿；
* M4 `DOCUMENT_SCOPES` 加第三个值：全绿；
* M6 store 路径丢 scope：全绿。

根因是那个阶段的判据全是**字段存在性**判据（`set(as_dict()) >= REQUIRED_FIELDS`、
`target_sheet=None` 也能构造成功）。字段存在 ≠ 值正确 —— 与「接线判据必须落在副作用上」
是同一条纪律。

═══ 判据分层 ═══

1. **构造期**：`assert_descriptor_mountable` 的封闭域真的拒绝非法组合（M3 / M4）；
2. **归一化**：`_frozen_target_sheet` 的 whole/single 分支各自产出正确形态（M1 / M2）；
3. **路由装配**：`materialize` / `materialize-from-store` 把 route 解析值传进
   `MaterializeRequest`，store 路径再传进 `store_materialize.materialize_from_store`（M5 / M6）。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import Any

import pytest

from app.services.workpaper_sync import descriptor_view_identity as VI
from app.services.workpaper_sync import materialize_coordinator as MC
from app.services.workpaper_sync.definitions import AuthorityModel

_BACKEND = Path(__file__).resolve().parents[2]
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"
_STORE_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "store_materialize.py"


def _digest(tag: str) -> str:
    import hashlib

    return hashlib.sha256(tag.encode()).hexdigest()


def _descriptor(**over: Any) -> MC.EditorLaunchDescriptor:
    """一个**合法** descriptor（与 `test_task25` 的 helper 同形）。"""
    base = dict(
        operation_id=uuid.uuid4(),
        room_id=uuid.uuid4(),
        participant_id=uuid.uuid4(),
        doc_key="wpsync-view-g1",
        generation=1,
        server_applied_revision=1,
        client_confirmed_base_revision=None,
        content_version_id=uuid.uuid4(),
        representation_id=uuid.uuid4(),
        representation_generation=1,
        artifact_sha256=_digest("artifact"),
        write_fence_epoch=1,
        authority_model=AuthorityModel.projection_contract.value,
        authority_model_definition_sha256=_digest("authority"),
        definition_bundle_id=uuid.uuid4(),
        definition_bundle_sha256=_digest("bundle"),
        definition_bundle_slots={
            "template": {"type": "definition", "sha256": _digest("tpl")},
            "instrumentation": {"type": "definition", "sha256": _digest("instr")},
            "contract": {"type": "definition", "sha256": _digest("contract")},
        },
        document_type="xlsx",
        target_sheet=None,
        document_scope="single_sheet",
        mode="edit",
        onlyoffice_config={"document": {"key": "wpsync-view-g1"}},
    )
    base.update(over)
    return MC.EditorLaunchDescriptor(**base)  # type: ignore[arg-type]


def _request(**over: Any) -> MC.MaterializeRequest:
    from app.services.workpaper_sync.endpoint_payloads import scope_only_projection
    from app.services.workpaper_sync.entry_profile import Capability

    base = dict(
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="xlsx/gt-d4-operating-revenue",
        sheet_key="d4-26-managed",
        user_id=uuid.uuid4(),
        pending_mutation_token=None,
        idempotency_key="view-identity-key",
        expected_revision=1,
        capability=Capability.bidirectional,
        projection=scope_only_projection(),
        document_type="xlsx",
    )
    base.update(over)
    return MC.MaterializeRequest(**base)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 构造期封闭域（M3 / M4）
# ═══════════════════════════════════════════════════════════════════════════


def test_whole_workbook_with_target_sheet_is_refused() -> None:
    """整册视图带定位 = 把其它 sheet 悄悄藏起来（Requirement 3.4 明禁）。"""
    with pytest.raises(MC.DescriptorFieldMissingError, match="whole_workbook"):
        _descriptor(document_scope="whole_workbook", target_sheet="境外销售收入检查D4-26")


def test_unknown_document_scope_is_refused() -> None:
    """封闭域只有两个值：第三个值是「隐藏 sheet 改写 artifact」的后门。"""
    with pytest.raises(MC.DescriptorFieldMissingError, match="document_scope"):
        _descriptor(document_scope="legacy")


def test_document_scopes_enum_is_exactly_two_values() -> None:
    """分母守卫：枚举被悄悄加宽时打红（M4 就是这条）。"""
    assert set(MC.DOCUMENT_SCOPES) == {"single_sheet", "whole_workbook"}


def test_single_sheet_with_padded_target_is_refused() -> None:
    """首尾空白不做归一化：真实 sheet 名可能含空格，半 strip 的输入必须拒。"""
    with pytest.raises(MC.DescriptorFieldMissingError, match="首尾空白"):
        _descriptor(target_sheet=" 境外销售收入检查D4-26")


def test_single_sheet_with_empty_string_target_is_refused() -> None:
    """空串是「既想定位又没定位到」的歧义形态 —— 显式不定位必须是 `None`。"""
    with pytest.raises(MC.DescriptorFieldMissingError, match="single_sheet"):
        _descriptor(target_sheet="")


def test_valid_single_sheet_and_whole_workbook_both_construct() -> None:
    """正向对照：两种合法形态都必须能构造（否则上面的拒绝判据可以靠「全拒」通过）。"""
    assert _descriptor(target_sheet="境外销售收入检查D4-26").target_sheet == (
        "境外销售收入检查D4-26"
    )
    whole = _descriptor(document_scope="whole_workbook", target_sheet=None)
    assert whole.document_scope == "whole_workbook"


def test_view_identity_is_in_the_descriptor_response() -> None:
    """Requirement 8.2：descriptor 响应必须能回溯 target sheet 与 mapping scope。"""
    body = _descriptor(target_sheet="境外销售收入检查D4-26").as_dict()
    assert body["target_sheet"] == "境外销售收入检查D4-26"
    assert body["document_scope"] == "single_sheet"
    for field in ("target_sheet", "document_scope"):
        assert field in MC.DESCRIPTOR_REQUIRED_FIELDS, (
            f"{field} 不在必填清单里 —— 前端无法据此判断视图语义"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 归一化（M1 / M2）
# ═══════════════════════════════════════════════════════════════════════════


def test_frozen_target_sheet_keeps_single_sheet_value() -> None:
    """M1：single_sheet 的 target 必须原样保留，不能被归一成 None。"""
    request = _request(target_sheet="境外销售收入检查D4-26", document_scope="single_sheet")
    got = VI.normalize_target_sheet(
        document_scope=str(request.document_scope), target_sheet=request.target_sheet
    )
    assert got == "境外销售收入检查D4-26"


def test_frozen_target_sheet_drops_target_for_whole_workbook() -> None:
    """反方向：整册视图即便请求带了 target，也必须归一到 None。"""
    request = _request(target_sheet="境外销售收入检查D4-26", document_scope="whole_workbook")
    got = VI.normalize_target_sheet(
        document_scope=str(request.document_scope), target_sheet=request.target_sheet
    )
    assert got is None


def test_frozen_target_sheet_normalizes_blank_to_none() -> None:
    """`"  "` 与「没解析到」是同一件事，统一成显式的 `None`。"""
    blank = _request(target_sheet="   ")
    assert VI.normalize_target_sheet(
        document_scope=str(blank.document_scope), target_sheet=blank.target_sheet
    ) is None
    none = _request(target_sheet=None)
    assert VI.normalize_target_sheet(
        document_scope=str(none.document_scope), target_sheet=none.target_sheet
    ) is None


def test_request_defaults_are_single_sheet_without_target() -> None:
    """`MaterializeRequest` 的默认值必须是最保守的那一档。

    🔴 默认值就是安全性：默认成 `whole_workbook` 会让所有未声明的入口打开整册。
    """
    request = _request()
    assert request.document_scope == "single_sheet"
    assert request.target_sheet is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. 路由装配（M5 / M6）—— AST 判据，落在「传了这个值」上
# ═══════════════════════════════════════════════════════════════════════════


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name!r}")


def _call_with_kwargs(fn: ast.AST, callee: str) -> list[dict[str, str]]:
    """`fn` 体内每个 `callee(...)` 调用的关键字实参源码（按 arg 名索引）。"""
    out: list[dict[str, str]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.id if isinstance(func, ast.Name)
            else func.attr if isinstance(func, ast.Attribute)
            else ""
        )
        if name != callee:
            continue
        out.append({kw.arg: ast.unparse(kw.value) for kw in node.keywords if kw.arg})
    return out


def test_materialize_route_forwards_view_identity_into_the_request() -> None:
    """M5 的正向形态：route 必须把 `target_sheet` / `document_scope` 传进请求构造。

    🔴 判据看的是**实参表达式**，不是「源码里出现过这两个名字」：把
    `document_scope=document_scope` 改成 `document_scope="single_sheet"` 之后名字仍在
    函数里（别处用到），presence 判据会全绿而整册视图永久失效。
    """
    fn = _func(_tree(_ROUTER_PY), "_materialize_request")
    params = {a.arg for a in fn.args.kwonlyargs} | {a.arg for a in fn.args.args}
    assert {"target_sheet", "document_scope"} <= params, (
        f"_materialize_request 没有接收视图身份参数：{sorted(params)}"
    )
    builds = _call_with_kwargs(fn, "MaterializeRequest")
    assert len(builds) == 1, f"MaterializeRequest 构造点 {len(builds)} 个 —— 应恰好 1 个"
    kwargs = builds[0]
    assert kwargs.get("target_sheet") == "target_sheet", kwargs
    assert kwargs.get("document_scope") == "document_scope", kwargs


def test_materialize_route_derives_scope_from_a_server_side_fact() -> None:
    """`document_scope` 必须由服务端从 `payload["whole_workbook"]` 判定，不得读客户端任意值。

    M5 的变异形态是把整个三元表达式换成 `"single_sheet"` 字面量 —— 上面那条查的是
    `_materialize_request` 的内部，这条查 `materialize` 端点里的实际赋值。
    """
    fn = _func(_tree(_ROUTER_PY), "materialize")
    assigns = {
        target.id: ast.unparse(node.value)
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "document_scope"
    }
    assert "document_scope" in assigns, "materialize 端点没有计算 document_scope"
    expr = assigns["document_scope"]
    assert "whole_workbook" in expr, f"document_scope 的取值表达式不含整册判定：{expr}"
    assert "payload" in expr, f"document_scope 不是从请求载荷判定：{expr}"


def test_store_route_forwards_view_identity_into_the_service() -> None:
    """M6：`/materialize-from-store` 也必须把视图身份传进 service。"""
    fn = _func(_tree(_ROUTER_PY), "materialize_from_store")
    calls = _call_with_kwargs(fn, "materialize_from_store")
    assert len(calls) == 1, f"materialize_from_store 调用点 {len(calls)} 个"
    kwargs = calls[0]
    # `target_sheet or None`：空串（契约没声明该 sheet_key）必须归一成显式不定位。
    assert kwargs.get("target_sheet") == "target_sheet or None", kwargs
    assert kwargs.get("document_scope") == "document_scope", kwargs


def test_store_service_forwards_view_identity_into_every_materialize_request() -> None:
    """service 内部两处 `MaterializeRequest` 构造（指纹快速路径 + 正常路径）都要带上。

    🔴 只有一处带的话，指纹命中的那次会产出 `target_sheet=None` 的 descriptor —— 表现为
    「第二次打开停在首 sheet」，而单测只看第一次。
    """
    fn = _func(_tree(_STORE_PY), "materialize_from_store")
    params = {a.arg for a in fn.args.kwonlyargs} | {a.arg for a in fn.args.args}
    assert {"target_sheet", "document_scope"} <= params, (
        f"store service 没有接收视图身份：{sorted(params)}"
    )
    # `base` dict 是两处构造的共同来源；断言它带着这两个键。
    base_assigns = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "base" for t in node.targets)
    ]
    assert len(base_assigns) == 1, f"`base = dict(...)` 出现 {len(base_assigns)} 次"
    base_src = ast.unparse(base_assigns[0].value)
    assert "target_sheet=target_sheet" in base_src, base_src
    assert "document_scope=str(document_scope)" in base_src, base_src
    # 两处构造都必须从 `base` 展开（`**base`），否则它们拿不到视图身份。
    builds = _call_with_kwargs(fn, "MaterializeRequest")
    assert len(builds) == 2, f"MaterializeRequest 构造点 {len(builds)} 个 —— 应恰好 2 个"
    starred = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "MaterializeRequest"
        and any(kw.arg is None for kw in node.keywords)
    ]
    assert len(starred) == 2, (
        f"只有 {len(starred)}/2 处 MaterializeRequest 用 `**base` 展开 —— "
        "未展开的那次会丢掉视图身份"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 阴性对照
# ═══════════════════════════════════════════════════════════════════════════


def test_negative_control_scope_guard_allows_the_legal_pair() -> None:
    """阴性对照：合法组合必须**不**被上面的封闭域判据拒。

    没有这条，`assert_descriptor_mountable` 里写成「无条件 raise」也能让 6 条拒绝用例全绿。
    """
    for scope, target in (("single_sheet", None), ("single_sheet", "Sheet1"),
                          ("whole_workbook", None)):
        descriptor = _descriptor(document_scope=scope, target_sheet=target)
        assert descriptor.document_scope == scope
        assert descriptor.target_sheet == target


# ═══════════════════════════════════════════════════════════════════════════
# 5. coordinator 内部的 descriptor 构造点（M1 / M2 / M7）
#
# 🔴 为什么必须单独查构造点：上面「归一化」那组是**直接调** `_frozen_target_sheet`，
#    它证明函数本身正确，但证明不了 descriptor 构造时**用了**它。实测把构造处的
#    `target_sheet=self._frozen_target_sheet(request)` 换成 `target_sheet=None` 后
#    全绿 —— 那正是「测了被调函数一层，测不到调用方传没传参」这个经典形态。
# ═══════════════════════════════════════════════════════════════════════════


def _coordinator_tree() -> ast.Module:
    return _tree(Path(MC.__file__))


#: descriptor 的**真实**构造点所在函数。
#:
#: 🔴 曾经按名字假设它在 `materialize()` 里 —— 实测那是错的（`materialize` 只调
#: `_open_room_and_descriptor`，构造发生后者内部）。按名字假设的判据会找 0 个构造点而红，
#: 那次红是判据自己报错、不是源码错。首次接触的接口先跑一次 AST 探针确认，成本 3 秒。
_DESCRIPTOR_BUILDER = "_open_room_and_descriptor"


def _descriptor_call_kwargs() -> dict[str, str]:
    """`_open_room_and_descriptor()` 内 `EditorLaunchDescriptor(...)` 的关键字实参源码。"""
    fn = _func(_coordinator_tree(), _DESCRIPTOR_BUILDER)
    builds = _call_with_kwargs(fn, "EditorLaunchDescriptor")
    assert len(builds) == 1, f"EditorLaunchDescriptor 构造点 {len(builds)} 个 —— 应恰好 1 个"
    return builds[0]


def test_descriptor_is_built_from_the_request_view_identity() -> None:
    """M1 + M2 的正面判据：构造 descriptor 时必须**传**这两个字段的实际值。

    判据看实参表达式，不看「名字在函数里出现过」——`target_sheet=None` 让名字彻底消失，
    但即便有人写成 `target_sheet=getattr(request, "target_sheet", None)`（名字仍在、
    语义已变），下一条的表达式断言也会收紧。
    """
    kwargs = _descriptor_call_kwargs()
    assert "target_sheet" in kwargs, f"descriptor 构造缺 target_sheet：{sorted(kwargs)}"
    assert "document_scope" in kwargs, f"descriptor 构造缺 document_scope：{sorted(kwargs)}"
    assert "request" in kwargs["target_sheet"], (
        f"target_sheet 不是从请求取的：{kwargs['target_sheet']!r}"
    )
    assert "request" in kwargs["document_scope"], (
        f"document_scope 不是从请求取的：{kwargs['document_scope']!r}"
    )


def test_descriptor_target_sheet_goes_through_the_normalizer() -> None:
    """target_sheet 必须经 `_frozen_target_sheet` 归一（M7 的等价形态之一）。

    直接写 `request.target_sheet` 会漏掉「整册视图归一到 None」与「空串归一到 None」
    两条 —— descriptor 的封闭域校验随即拒绝，把一次正常的整册打开变成 500。
    """
    kwargs = _descriptor_call_kwargs()
    assert "normalize_target_sheet" in kwargs["target_sheet"], (
        f"target_sheet 未走归一化：{kwargs['target_sheet']!r}"
    )


def test_request_view_identity_reaches_every_descriptor_field_it_should() -> None:
    """闭包检查：`MaterializeRequest` 的视图身份字段名与 descriptor 字段名逐值一致。

    两边任一改名而另一侧不改，上面两条按名匹配的判据就静默失效（找不到就红，但换成
    `getattr` 写法就不红）。这条按**数据类字段**比对，给改名留一条明确的红灯。
    """
    import dataclasses

    request_fields = {f.name for f in dataclasses.fields(MC.MaterializeRequest)}
    descriptor_fields = {f.name for f in dataclasses.fields(MC.EditorLaunchDescriptor)}
    for name in ("target_sheet", "document_scope"):
        assert name in request_fields, f"MaterializeRequest 缺 {name}"
        assert name in descriptor_fields, f"EditorLaunchDescriptor 缺 {name}"


def test_materialize_route_passes_the_resolved_target_to_the_request_builder() -> None:
    """M7：`materialize()` 必须把**解析后**的 target 传进 `_materialize_request`。

    🔴 这条与 `test_materialize_route_forwards_view_identity_into_the_request` 查的不是
    同一件事：后者查 `_materialize_request` 内部往 `MaterializeRequest` 塞了什么，本条查
    `materialize()` 端点有没有把 `resolve_launch_target_sheet` 的**结果**交进去。实测把
    `target_sheet=target_sheet or None` 换成 `target_sheet=None` 后，前者全绿 —— 因为
    `_materialize_request` 仍忠实地转发它收到的（`None`）值。这就是「测了被调方，
    测不到调用方」的第二层。
    """
    fn = _func(_tree(_ROUTER_PY), "materialize")
    calls = _call_with_kwargs(fn, "_materialize_request")
    assert len(calls) == 1, f"_materialize_request 调用点 {len(calls)} 个 —— 应恰好 1 个"
    kwargs = calls[0]
    assert "target_sheet" in kwargs, f"未传 target_sheet：{sorted(kwargs)}"
    assert "target_sheet" in kwargs["target_sheet"], (
        f"传的不是解析结果：{kwargs['target_sheet']!r}"
    )
    assert kwargs.get("document_scope") == "document_scope", kwargs


def test_materialize_route_resolves_the_target_from_the_contract() -> None:
    """目标 sheet 必须由 `resolve_launch_target_sheet(contract, sheet_key)` 解析。

    不许从 `payload` 直接读客户端给的 sheet 名：那等于让客户端决定定位到哪张表。
    """
    fn = _func(_tree(_ROUTER_PY), "materialize")
    calls = _call_with_kwargs(fn, "resolve_launch_target_sheet")
    assert len(calls) == 1, f"resolve_launch_target_sheet 调用点 {len(calls)} 个"
    assert "sheet_key" in calls[0], f"未按 sheet_key 解析：{calls[0]}"
    assert "contract" in calls[0], f"未按契约解析：{calls[0]}"


def test_store_route_derives_scope_from_a_server_side_fact() -> None:
    """M5b：`/materialize-from-store` 的 `document_scope` 也必须由服务端判定。

    🔴 与 `test_materialize_route_derives_scope_from_a_server_side_fact` 是**两条**判据：
    M5a（`materialize`）与 M5b（`materialize-from-store`）是两处独立赋值，实测只查
    `materialize` 时把 store 那处改成 `"single_sheet"` 字面量全绿 —— 表现为「store 型
    entry 的整册视图永久失效」，而 store 型 entry（D2 大 JSON 那批）恰恰是最需要整册的。

    判据看**赋值表达式**而不是「名字出现过」：store 端点的 `document_scope` 变量只在
    两处出现（赋值 + 传参），字面量赋值后名字仍在传参处。
    """
    fn = _func(_tree(_ROUTER_PY), "materialize_from_store")
    assigns = {
        target.id: ast.unparse(node.value)
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "document_scope"
    }
    assert "document_scope" in assigns, "materialize_from_store 端点没有计算 document_scope"
    expr = assigns["document_scope"]
    assert "whole_workbook" in expr, f"store 端点的 document_scope 不含整册判定：{expr}"
    assert "payload" in expr, f"store 端点的 document_scope 不是从请求载荷判定：{expr}"
