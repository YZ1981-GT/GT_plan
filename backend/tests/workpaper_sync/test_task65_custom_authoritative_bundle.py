r"""Task 65 custom 侧守卫：xlsx 本体是唯一权威载荷、JSON projection writer 一次都不调、
五类非法空值各自 fail closed 并指出首个非法 slot、两条通道双向不可混用。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 65
点名 Property：**50 / 64 / 69**
点名 AC：2.11 · 3.9 · 5.5 · 6.19 · 12.6 · 12.10

═══ 与 `test_task65_opaque_authority_bundle.py` 的分工（刻意不重叠）═══

那一半证的是 **lane 登记表**这一侧：登记表 ↔ 源码 `opaque_entry_id(...)` ↔
`commit_bytes(lane_id=...)` 三向锁死、消费门结构上没有发布能力、`provision` 只有一个宿主。
本文件证的是**custom 这条 lane 自己的内容语义**，三组判据一一对应 Task 65 正文三条：

* **正文①「custom 继续以 xlsx artifact 为唯一业务权威 …… 不调用标准 JSON projection
  writer」** → §1 端点把**从 substrate 读回的 xlsx 字节**交给 `commit_bytes`（不是 `grid`、
  不是 `parsed_data`、不是归一化后的 `updates`），端点自己不推进任何版本计数器、不 commit；
  §2 服务层 `_assert_authority_shape` 在 custom 通道上**结构性**拒绝「只交 projection」
  与「携带 per-entry contract」两种转向，两条拒绝各有自己的原因文案且互不命中；
  另证 custom 走的 commit 步骤集**含** `representation`，而 html-only projection 那条
  步骤集**不含** —— 「进入统一 content version / representation」不是一句承诺。
* **正文②「typed null marker 只能用 registry 版本化的，slot omission / SQL·JSON NULL /
  空串 / 全零 hash 一律拒绝」** → §3 五类各一条判据，**各自一个异常类型**且五者
  互不命中；`slot` 字段按 `BundleSlot` 声明序给出首个非法 slot；配对照组。
* **正文③「application key 仍冻结 bundle/authority-model digest」** → §5 两个 digest
  **各自**都能单独改变 key（分开断言，删任一个都不会被另一个顶住），且 key 的入参里
  根本没有 status/request id/sequence；`canonicalize_authorized` 在类型层要求
  `AuthorizedOperationRef` ⇒ 拿着一个旧终态 operation id 无法绕过当前授权/write fence。

§4 是两条通道的**双向**归属：projection bundle 喂进 custom 通道必须拒，custom authority
喂进 projection 通道必须拒，且两条拒绝的 error_code 不同（共用时短路任一条都会被另一条
遮蔽 —— 本 spec 已三次实测到该形态）。

═══ 判据形态说明 ═══

* AST 判据一律**逐段下钻到函数节点**再看，不做全文件 grep：同一个文件里的另一个端点
  （`refresh_custom_projection_endpoint`）合法地调用了 `db.commit()`，全文件 grep 会把它
  算到 `update_custom_cells` 头上。
* 每条「不调用 X」判据都配一条**分母非空**断言（X 真的存在于生产 API 上）；否则改名之后
  交集恒空，判据变成重言式。

用法（仓库根）::

    .\.venv\Scripts\python.exe -m pytest \
        backend/tests/workpaper_sync/test_task65_custom_authoritative_bundle.py -q
"""
from __future__ import annotations

import ast
import inspect
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))

from app.services.workpaper_sync import content_mutation as CM  # noqa: E402
from app.services.workpaper_sync import opaque_entry_gate as OG  # noqa: E402
from app.services.workpaper_sync import projection_provisioning as PP  # noqa: E402
from app.services.workpaper_sync import request_application as RA  # noqa: E402
from app.services.workpaper_sync import writer_migration as WM  # noqa: E402
from app.services.workpaper_sync.definitions import (  # noqa: E402
    TYPED_NULL_MARKERS,
    marker_slot_spec,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotAllZeroDigestError,
    BundleSlotEmptyFieldError,
    BundleSlotNullFieldError,
    BundleSlotOmissionError,
    BundleSlotSpec,
    compute_application_key,
    validate_bundle_slot,
    validate_bundle_slots,
)

CELLS_PATH = BACKEND / "app" / "routers" / "custom_workpaper_cells.py"
CM_PATH = BACKEND / "app" / "services" / "workpaper_sync" / "content_mutation.py"

#: custom lane 的 lane_id。取自登记表而不是字面量：登记表是 authority model 的真源。
CUSTOM_LANE = "custom_cells"

#: 标准结构化 JSON projection 的**持久化**面。custom 通道一次都不许碰（AC 2.11 / 12.6）。
JSON_PROJECTION_PERSIST = ("commit_projection", "stage_html_projection", "commit_html_projection")

ALL_ZERO = "0" * 64


def _digest(seed: str) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _src(path: Path) -> str:
    """读磁盘真相（`inspect.getsource` 会给出 import 期缓存的陈旧版本）。"""
    return path.read_text(encoding="utf-8")


def _func_node(path: Path, qualname: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """按 `Class.method` / `func` 逐段下钻到定义节点。"""
    node: ast.AST = ast.parse(_src(path), filename=str(path))
    for part in qualname.split("."):
        found = None
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and child.name == part
            ):
                found = child
                break
        if found is None:
            raise AssertionError(f"AST 里找不到 {qualname!r}（卡在 {part!r}）")
        node = found
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)), f"{qualname} 不是函数"
    return node


def _called_names(node: ast.AST) -> set[str]:
    """节点内被调用的**方法/函数名**集合（`a.b.c(...)` 取 `c`）。"""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            fn = child.func
            if isinstance(fn, ast.Attribute):
                names.add(fn.attr)
            elif isinstance(fn, ast.Name):
                names.add(fn.id)
    return names


def _kwargs_of(node: ast.AST, callee: str) -> dict[str, ast.AST]:
    """节点内对 `callee` 的**唯一**一次调用的关键字实参映射。"""
    hits = [
        c
        for c in ast.walk(node)
        if isinstance(c, ast.Call)
        and (
            (isinstance(c.func, ast.Attribute) and c.func.attr == callee)
            or (isinstance(c.func, ast.Name) and c.func.id == callee)
        )
    ]
    assert len(hits) == 1, f"期望恰好一次 {callee}(...) 调用，实得 {len(hits)} 次"
    return {kw.arg: kw.value for kw in hits[0].keywords if kw.arg}


# ═══════════════════════════════════════════════════════════════════════════
# §1 custom 端点：xlsx 本体是唯一权威载荷
# ═══════════════════════════════════════════════════════════════════════════


def test_custom_endpoint_commits_the_substrate_bytes_not_a_projection() -> None:
    """`payload=` 必须是「从 `ctx.wp.file_path` 读回的字节」那个名字。

    这是 AC 2.11 的可 falsify 形态：端点手里同时有 `grid`（重投影结果）、`normalized`
    （归一化后的单元格补丁）与 xlsx 本体三份数据，只有第三份是权威。判据做成**数据流**
    而不是「源码里出现 read_bytes」：后者在 `payload=grid` 的情况下照样绿。
    """
    fn = _func_node(CELLS_PATH, "update_custom_cells")

    # 1) 找到唯一一次 `....read_bytes()` 的赋值目标
    bound: list[str] = []
    for child in ast.walk(fn):
        if not isinstance(child, ast.Assign):
            continue
        val = child.value
        if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute):
            if val.func.attr == "read_bytes":
                assert len(child.targets) == 1 and isinstance(child.targets[0], ast.Name)
                bound.append(child.targets[0].id)
    assert len(bound) == 1, f"期望恰好一次 read_bytes() 赋值，实得 {bound}"

    # 2) `commit_bytes(payload=...)` 必须就是那个名字
    payload = _kwargs_of(fn, "commit_bytes")["payload"]
    assert isinstance(payload, ast.Name), f"payload 不是简单名字绑定: {ast.dump(payload)[:120]}"
    assert payload.id == bound[0], (
        f"commit_bytes(payload={payload.id!r}) 不是从 substrate 读回的 {bound[0]!r} —— "
        "custom 的权威是 xlsx 本体，投影（grid / parsed_data）不得冒充权威载荷（AC 2.11）"
    )


def test_custom_endpoint_reads_the_substrate_it_declares() -> None:
    """读回的路径与 `substrate_path=` 必须是同一个来源，否则「权威」指向另一个文件。"""
    fn = _func_node(CELLS_PATH, "update_custom_cells")
    kwargs = _kwargs_of(fn, "commit_bytes")
    substrate = ast.unparse(kwargs["substrate_path"])
    read_calls = [
        ast.unparse(c.func.value)
        for c in ast.walk(fn)
        if isinstance(c, ast.Call)
        and isinstance(c.func, ast.Attribute)
        and c.func.attr == "read_bytes"
    ]
    assert read_calls, "端点没有从 substrate 读回权威字节"
    assert substrate in read_calls or any(substrate == r for r in read_calls), (
        f"substrate_path={substrate!r} 与实际读回的 {read_calls!r} 不是同一来源 —— "
        "提交的字节与声明的权威文件必须是同一个"
    )


def test_custom_endpoint_declares_lane_and_xlsx_document_type() -> None:
    """lane_id 与 document_type 都是字面量且与登记表一致（authority model 由 lane 单向决定）。"""
    kwargs = _kwargs_of(_func_node(CELLS_PATH, "update_custom_cells"), "commit_bytes")
    lane = kwargs["lane_id"]
    assert isinstance(lane, ast.Constant) and lane.value == CUSTOM_LANE, (
        f"lane_id 不是字面量 {CUSTOM_LANE!r}: {ast.dump(lane)[:120]}"
    )
    doc = kwargs["document_type"]
    assert isinstance(doc, ast.Constant) and doc.value == "xlsx"
    assert OG.authority_model_for_lane(CUSTOM_LANE) is AuthorityModel.custom_authoritative_ooxml, (
        "custom lane 的 authority model 必须是 `custom_authoritative_ooxml`（AC 6.19）"
    )


def test_custom_endpoint_never_calls_the_json_projection_writer() -> None:
    """custom 端点一次都不调标准 JSON projection 的持久化面（AC 2.11 / 3.9 / 12.6）。"""
    called = _called_names(_func_node(CELLS_PATH, "update_custom_cells"))
    # 🔴 分母非空：那三个名字必须真的存在于生产 API 上。少了这条断言，一旦上游改名，
    #    交集恒空 ⇒ 判据变成重言式（本 spec 记录的假绿第②源的近亲）。
    surface = set(dir(WM.AuthoritativeContentWriter)) | set(dir(CM.ContentMutationService))
    missing = [n for n in JSON_PROJECTION_PERSIST if n not in surface]
    assert not missing, f"分母失真：{missing} 已不在生产 API 上，判据需重写"
    leaked = sorted(set(JSON_PROJECTION_PERSIST) & called)
    assert not leaked, (
        f"custom 端点调用了标准 JSON projection 持久化面 {leaked} —— "
        "custom 的权威是 xlsx 本体，不得转为 JSON 三方 projection（AC 12.6）"
    )


def test_custom_endpoint_has_no_self_commit_and_no_version_counter() -> None:
    """端点自己不 commit、不推进任何版本字段 —— 唯一提交出口是 `commit_bytes`。

    同文件的 `refresh_custom_projection_endpoint` 合法地 `await db.commit()`（它只重投影，
    不碰权威），所以判据必须**限定在函数节点内**，不能全文件 grep。
    """
    fn = _func_node(CELLS_PATH, "update_custom_cells")
    assert "commit" not in _called_names(fn) - {"commit_bytes"}, (
        "update_custom_cells 自己调了 commit() —— 提交出口只能是 ContentMutationService"
    )
    assigned = {
        ast.unparse(t)
        for node in ast.walk(fn)
        if isinstance(node, (ast.Assign, ast.AugAssign))
        for t in (node.targets if isinstance(node, ast.Assign) else [node.target])
    }
    counters = sorted(a for a in assigned if "file_version" in a or "content_revision" in a)
    assert not counters, (
        f"端点自己推进了版本计数器 {counters} —— 版本只能由统一提交入口推进（AC 2.2）"
    )
    # 对照：该函数确实还有别的赋值（否则上面的空集是因为 AST 取空，不是因为判据成立）
    assert assigned, "AST 取不到任何赋值目标 ⇒ 判据分母为空，需重写定位方式"


# ═══════════════════════════════════════════════════════════════════════════
# §2 服务层：custom 通道结构性拒绝转向 JSON projection
# ═══════════════════════════════════════════════════════════════════════════


def _plan_stub(*, model: AuthorityModel, contract: object | None) -> SimpleNamespace:
    """`_assert_authority_shape` 只读四个属性，且完全不用 `self`。

    用鸭子类型 stub 而不是造一个真 `ContentCommitPlan`，是为了让判据聚焦在**分支**上；
    紧随其后的 `test_the_stub_shape_matches_the_real_plan` 锁死 stub 不许与真 dataclass
    漂移（否则 stub 会变成「测了一个不存在的形状」）。
    """
    return SimpleNamespace(
        is_projection_based=model is AuthorityModel.projection_contract,
        authority_model=model,
        contract=contract,
        entry_id="opaque-D2-1",
    )


def _shape(plan: object, mutation: object, adapter: object = None) -> None:
    CM.ContentMutationService._assert_authority_shape(None, plan, mutation, adapter)  # type: ignore[arg-type]


def test_the_stub_shape_matches_the_real_plan() -> None:
    """stub 用到的属性名必须都在真 `ContentCommitPlan` / `BusinessMutation` 上。"""
    plan_names = set(CM.ContentCommitPlan.__dataclass_fields__) | {
        n for n in dir(CM.ContentCommitPlan) if not n.startswith("_")
    }
    for name in ("is_projection_based", "authority_model", "contract", "entry_id"):
        assert name in plan_names, f"ContentCommitPlan 已无 {name!r}，stub 漂移"
    for name in ("projection", "authoritative_payload"):
        assert name in CM.BusinessMutation.__dataclass_fields__, f"BusinessMutation 已无 {name!r}"


def test_custom_channel_refuses_a_projection_only_mutation() -> None:
    """custom 通道只交 projection、不交权威字节 ⇒ 拒，且原因文案指向 AC 2.11。"""
    with pytest.raises(CM.AuthorityModelMismatchError) as got:
        _shape(
            _plan_stub(model=AuthorityModel.custom_authoritative_ooxml, contract=None),
            SimpleNamespace(projection=object(), authoritative_payload=None),
        )
    assert "authoritative_payload" in str(got.value)
    assert "JSON projection writer" in str(got.value)


def test_custom_channel_refuses_a_per_entry_contract() -> None:
    """custom bundle 携带 per-entry contract ⇒ 拒（contract slot 必须是 typed null marker）。"""
    with pytest.raises(CM.AuthorityModelMismatchError) as got:
        _shape(
            _plan_stub(
                model=AuthorityModel.custom_authoritative_ooxml, contract=SimpleNamespace()
            ),
            SimpleNamespace(projection=None, authoritative_payload=b"PK\x03\x04"),
        )
    assert "per-entry contract" in str(got.value)
    assert "typed null marker" in str(got.value)


def test_the_two_custom_channel_reasons_do_not_overlap() -> None:
    """两条拒绝的原因文案**互不命中** —— 共用类型时这是唯一能分辨它们的判据。

    只断言异常类型时，把「缺 authoritative_payload」那条短路掉之后「携带 contract」那条
    会抛出同一个 `AuthorityModelMismatchError` 顶上来，变异检验判 GREEN。
    """
    def reason(payload: bytes | None, contract: object | None) -> str:
        with pytest.raises(CM.AuthorityModelMismatchError) as got:
            _shape(
                _plan_stub(model=AuthorityModel.custom_authoritative_ooxml, contract=contract),
                SimpleNamespace(projection=None, authoritative_payload=payload),
            )
        return str(got.value)

    missing_payload = reason(None, None)
    carries_contract = reason(b"PK\x03\x04", SimpleNamespace())
    assert "per-entry contract" not in missing_payload
    assert "authoritative_payload" not in carries_contract


def test_projection_channel_refuses_authoritative_bytes() -> None:
    """反方向：projection 通道只交权威字节 ⇒ 拒（两条通道各自的内容形态不可互换）。"""
    with pytest.raises(CM.AuthorityModelMismatchError) as got:
        _shape(
            _plan_stub(model=AuthorityModel.projection_contract, contract=None),
            SimpleNamespace(projection=None, authoritative_payload=b"PK\x03\x04"),
        )
    assert "projection_contract" in str(got.value)


def test_only_the_content_commit_lane_writes_a_representation() -> None:
    """custom 走的步骤集含 `representation`，html-only projection 那条不含（AC 12.6）。

    「custom 进入统一 content version / representation」在这里变成两个**可枚举集合**的
    差集，而不是一句注释。两个集合都断言非空（防空集恒等价）。
    """
    content = set(CM.CONTENT_COMMIT_STEPS)
    html_only = set(CM.HTML_ONLY_COMMIT_STEPS)
    assert content and html_only, "步骤集为空 ⇒ 判据分母为空"
    assert "representation" in content, "统一提交步骤里没有 representation"
    assert "representation" not in html_only, (
        "html-only projection 步骤集出现 representation ⇒ 两条 lane 的必需步骤不再互斥，"
        "custom 可以借 html-only 那条跳过 representation"
    )
    assert "content_version" in content and "content_version" in html_only
    # custom 端点确实走的是 content commit 那条（`commit_bytes` → `commit`），不是 html-only
    writer_src = inspect.getsource(WM.AuthoritativeContentWriter.commit_bytes)
    assert "self._mutation.commit(" in writer_src
    assert "commit_html_projection" not in writer_src


def test_custom_commit_passes_no_adapter_and_no_contract() -> None:
    """`commit_bytes` 在装配层写死 `adapter=None` / `contract=None`。

    这两条让「custom 转 JSON 三方 projection」在**装配层不可表达**：没有 adapter 就没有
    materialize/extract，没有 contract 就没有 per-entry projection 契约。两条**分开**
    断言 —— 合成一条时删掉其中一个会被另一个顶住。
    """
    fn = _func_node(
        BACKEND / "app" / "services" / "workpaper_sync" / "writer_migration.py",
        "AuthoritativeContentWriter.commit_bytes",
    )
    plan_kwargs = _kwargs_of(fn, "ContentCommitPlan")
    assert isinstance(plan_kwargs["contract"], ast.Constant)
    assert plan_kwargs["contract"].value is None, "commit_bytes 透传了 contract"
    commit_kwargs = _kwargs_of(fn, "commit")
    assert isinstance(commit_kwargs["adapter"], ast.Constant)
    assert commit_kwargs["adapter"].value is None, "commit_bytes 传了 adapter"
    role = ast.unparse(plan_kwargs["substrate_role"])
    assert role.endswith("published_representation"), (
        f"substrate_role={role} —— custom 的 substrate 必须发布成 published representation"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §3 五类非法空值：各自一个类型 + 首个非法 slot
# ═══════════════════════════════════════════════════════════════════════════


def _marker(slot: BundleSlot) -> BundleSlotSpec:
    return marker_slot_spec(slot)


def _custom_slots() -> dict[BundleSlot, BundleSlotSpec]:
    """一份**合法**的 custom bundle slot map（三 slot 全 registry 版本化 marker）。"""
    return {slot: _marker(slot) for slot in BundleSlot}


def _validate(slots: dict[BundleSlot, BundleSlotSpec]) -> None:
    validate_bundle_slots(
        authority_model=AuthorityModel.custom_authoritative_ooxml,
        authority_model_definition_sha256=_digest("authority-custom"),
        slots=slots,
    )


def test_control_group_a_valid_custom_bundle_is_accepted() -> None:
    """对照组：合法输入必须通过。没有它，「什么都拒」也算通过。"""
    _validate(_custom_slots())
    OG.assert_slots_are_typed_null_markers(_custom_slots(), where="control")


def test_class1_slot_omission_is_rejected_with_its_own_type() -> None:
    slots = _custom_slots()
    del slots[BundleSlot.instrumentation]
    with pytest.raises(BundleSlotOmissionError) as got:
        _validate(slots)
    assert got.value.first_illegal_slot == BundleSlot.instrumentation.value
    assert got.value.error_code == "bundle_slot_omission"


def test_class2_sql_or_json_null_is_rejected_with_its_own_type() -> None:
    """SQL NULL / JSON NULL 都到 Python 里就是 `None`（列没写 / JSON 少键 / 显式 null）。"""
    for field, spec in (
        ("type", BundleSlotSpec(BundleSlot.template, None, "marker:x", _digest("d"))),  # type: ignore[arg-type]
        ("ref", BundleSlotSpec(BundleSlot.template, "template:none:v1", None, _digest("d"))),  # type: ignore[arg-type]
        ("digest", BundleSlotSpec(BundleSlot.template, "template:none:v1", "marker:x", None)),  # type: ignore[arg-type]
    ):
        with pytest.raises(BundleSlotNullFieldError) as got:
            validate_bundle_slot(spec)
        assert "SQL/JSON NULL" in str(got.value), field
        assert got.value.first_illegal_slot == BundleSlot.template.value
        assert got.value.error_code == "bundle_slot_null_field"


def test_class3_empty_string_is_rejected_with_its_own_type() -> None:
    for spec in (
        BundleSlotSpec(BundleSlot.contract, "", "marker:x", _digest("d")),
        BundleSlotSpec(BundleSlot.contract, "contract:none:v1", "   ", _digest("d")),
        BundleSlotSpec(BundleSlot.contract, "contract:none:v1", "marker:x", ""),
    ):
        with pytest.raises(BundleSlotEmptyFieldError) as got:
            validate_bundle_slot(spec)
        assert "空串" in str(got.value)
        assert got.value.first_illegal_slot == BundleSlot.contract.value
        assert got.value.error_code == "bundle_slot_empty_field"


def test_class4_all_zero_hash_is_rejected_with_its_own_type() -> None:
    """全零 hash 在 `char(64)` 与 hex 正则层面都合法 —— 必须与「非法 hex」分开。"""
    spec = BundleSlotSpec(
        BundleSlot.template, "template:none:v1", "marker:template:none:v1", ALL_ZERO
    )
    with pytest.raises(BundleSlotAllZeroDigestError) as got:
        validate_bundle_slot(spec)
    assert got.value.error_code == "bundle_slot_all_zero_digest"
    assert got.value.first_illegal_slot == BundleSlot.template.value


def test_class5_unregistered_marker_version_is_rejected_with_its_own_type() -> None:
    """`contract:none:v0` 通得过版本化正则，但**不在 registry 里** ⇒ 必须拒。

    这一格只有 `assert_slots_are_typed_null_markers` 在守：`models` 层的正则是
    `v[0-9]+`，`v0` 合法。分母断言 `v0` 真的不在 registry 里 —— 否则本判据无效。
    """
    forged_type = "contract:none:v0"
    assert forged_type not in TYPED_NULL_MARKERS, "registry 已收 v0，本判据需换一个未登记版本"
    slots = _custom_slots()
    slots[BundleSlot.contract] = BundleSlotSpec(
        BundleSlot.contract, forged_type, f"marker:{forged_type}", _digest(forged_type)
    )
    # models 层放行（正则允许 v0）—— 这正是为什么 registry 判据必须存在
    validate_bundle_slot(slots[BundleSlot.contract])
    with pytest.raises(OG.OpaqueSlotNotTypedNullMarkerError) as got:
        OG.assert_slots_are_typed_null_markers(slots, where="task65")
    assert "marker registry" in str(got.value)
    assert got.value.error_code == "opaque_bundle_slot_not_typed_null_marker"


def test_the_five_classes_are_mutually_exclusive() -> None:
    """五类**互不命中**：每个反例只被自己那一类的类型捕获。

    这是「判据存在」与「判据可锁」的分界：五类共用 `BundleIntegrityError` 时，短路任一类
    都会被另一类顶上来抛同样的类型 ⇒ 定向变异判 GREEN。
    """
    cases: dict[type[BundleIntegrityError], BundleSlotSpec] = {
        BundleSlotNullFieldError: BundleSlotSpec(
            BundleSlot.template, None, "marker:x", _digest("d")  # type: ignore[arg-type]
        ),
        BundleSlotEmptyFieldError: BundleSlotSpec(
            BundleSlot.template, "template:none:v1", "marker:x", ""
        ),
        BundleSlotAllZeroDigestError: BundleSlotSpec(
            BundleSlot.template, "template:none:v1", "marker:template:none:v1", ALL_ZERO
        ),
    }
    assert len(cases) == 3
    for expected, spec in cases.items():
        with pytest.raises(BundleIntegrityError) as got:
            validate_bundle_slot(spec)
        assert type(got.value) is expected, (
            f"{spec!r} 抛了 {type(got.value).__name__}，期望 {expected.__name__} —— "
            "两类被合成一条判据时短路其一会被另一条遮蔽"
        )
    # omission 是 bundle 级（不是单 slot 级），单独验它的类型也唯一
    slots = _custom_slots()
    del slots[BundleSlot.template]
    with pytest.raises(BundleSlotOmissionError):
        _validate(slots)
    codes = {
        BundleSlotOmissionError.error_code,
        BundleSlotNullFieldError.error_code,
        BundleSlotEmptyFieldError.error_code,
        BundleSlotAllZeroDigestError.error_code,
        OG.OpaqueSlotNotTypedNullMarkerError.error_code,
    }
    assert len(codes) == 5, f"五类 error_code 有重复: {sorted(codes)}"


def test_first_illegal_slot_follows_declaration_order() -> None:
    """两个 slot 同时非法时，报出的是 `BundleSlot` **声明序**里靠前的那一个。

    不按 dict 插入序：插入序会让同一份坏 bundle 在不同代码路径报出不同的「首个非法
    slot」，运维照着修会修错那一个。
    """
    order = list(BundleSlot)
    assert order[0] is BundleSlot.template and order[-1] is BundleSlot.contract

    # 反向插入：contract 先入 dict，但 template 才该被报出
    slots: dict[BundleSlot, BundleSlotSpec] = {}
    slots[BundleSlot.contract] = BundleSlotSpec(
        BundleSlot.contract, "contract:none:v1", "marker:contract:none:v1", ALL_ZERO
    )
    slots[BundleSlot.instrumentation] = _marker(BundleSlot.instrumentation)
    slots[BundleSlot.template] = BundleSlotSpec(
        BundleSlot.template, "template:none:v1", "marker:template:none:v1", ALL_ZERO
    )
    with pytest.raises(BundleSlotAllZeroDigestError) as got:
        _validate(slots)
    assert got.value.first_illegal_slot == BundleSlot.template.value, (
        "首个非法 slot 跟着 dict 插入序走了 —— 必须按 BundleSlot 声明序"
    )

    # 两个都缺席时同理
    only_middle = {BundleSlot.instrumentation: _marker(BundleSlot.instrumentation)}
    with pytest.raises(BundleSlotOmissionError) as got2:
        _validate(only_middle)
    assert got2.value.first_illegal_slot == BundleSlot.template.value


# ═══════════════════════════════════════════════════════════════════════════
# §4 两条通道双向不可混用
# ═══════════════════════════════════════════════════════════════════════════


def _definition_slot(slot: BundleSlot) -> BundleSlotSpec:
    return BundleSlotSpec(
        slot, "definition", f"definition:{uuid.uuid4()}", _digest(f"{slot.value}-child")
    )


def test_projection_bundle_is_refused_by_the_custom_channel() -> None:
    """三 slot 全 approved definition 的 projection bundle 喂进 custom 通道 ⇒ 拒。"""
    slots = {slot: _definition_slot(slot) for slot in BundleSlot}
    with pytest.raises(OG.OpaqueSlotNotTypedNullMarkerError) as got:
        OG.assert_slots_are_typed_null_markers(slots, where="task65-reverse")
    assert "definition" in str(got.value)


def test_marker_bundle_is_refused_by_the_projection_channel() -> None:
    """反方向：typed null marker 冒充 per-entry contract ⇒ 拒（AC 2.3）。"""
    with pytest.raises(BundleIntegrityError) as got:
        validate_bundle_slots(
            authority_model=AuthorityModel.projection_contract,
            authority_model_definition_sha256=_digest("authority-projection"),
            slots=_custom_slots(),
        )
    assert "必须全部是" in str(got.value)
    assert got.value.first_illegal_slot == BundleSlot.template.value


def test_custom_authority_is_refused_by_the_projection_provisioner() -> None:
    """custom authority model 喂进 projection 发布判据函数 ⇒ 拒，且是**独立**类型。"""
    assert issubclass(PP.ProjectionAuthorityModelMismatchError, Exception)
    import asyncio

    async def _go() -> None:
        await PP.assert_projection_supply_authentic(
            session=None,
            entry_id="D2-1",
            authority_model=AuthorityModel.custom_authoritative_ooxml,
            authority_model_definition_sha256=_digest("authority-custom"),
            slots=_custom_slots(),
            contract_payload={},
        )

    with pytest.raises(PP.ProjectionAuthorityModelMismatchError):
        asyncio.run(_go())


def test_opaque_provisioner_refuses_the_projection_authority_model() -> None:
    """另一半：`projection_contract` 不在 opaque 封闭集里（封闭集非空 + 不含它）。"""
    assert WM.OPAQUE_AUTHORITY_MODELS, "opaque 封闭集为空 ⇒ 判据分母为空"
    assert AuthorityModel.projection_contract not in WM.OPAQUE_AUTHORITY_MODELS
    assert AuthorityModel.custom_authoritative_ooxml in WM.OPAQUE_AUTHORITY_MODELS


def test_the_two_channel_refusals_have_distinct_error_codes() -> None:
    """两条通道的拒绝**各有自己的 error_code** —— 共用时短路任一条会被另一条遮蔽。"""
    codes = {
        OG.OpaqueSlotNotTypedNullMarkerError.error_code,
        PP.ProjectionAuthorityModelMismatchError.error_code,
        WM.ProjectionAuthorityNotAllowedError.error_code,
        BundleIntegrityError.error_code,
    }
    assert len(codes) == 4, f"通道拒绝的 error_code 有重复: {sorted(codes)}"


# ═══════════════════════════════════════════════════════════════════════════
# §5 application identity 冻结 bundle / authority digest
# ═══════════════════════════════════════════════════════════════════════════


_KEY_BASE = {
    "wp_id": uuid.UUID(int=11),
    "room_id": uuid.UUID(int=22),
    "generation": 3,
    "frozen_client_base_version_id": uuid.UUID(int=33),
    "frozen_client_base_representation_id": uuid.UUID(int=44),
    "incoming_sha256": _digest("incoming"),
    "definition_bundle_sha256": _digest("bundle-custom"),
    "authority_model_definition_sha256": _digest("authority-custom"),
    "adapter_build_digest": _digest("opaque.authoritative.v1"),
}


def test_application_key_has_no_status_or_request_inputs() -> None:
    """key 的入参里没有 callback status / request id / sequence / room last-applied。"""
    params = set(inspect.signature(compute_application_key).parameters)
    forbidden = {
        "callback_status",
        "status",
        "request_id",
        "request_sequence",
        "latest_durable_sequence",
        "room_last_applied",
    }
    assert not (params & forbidden), f"application key 入参含可变量: {sorted(params & forbidden)}"
    for required in ("definition_bundle_sha256", "authority_model_definition_sha256"):
        assert required in params, f"application key 不再冻结 {required}（AC 5.5）"


def test_only_the_bundle_digest_changes_the_key() -> None:
    """**单独**断言 bundle digest 参与 key —— 与下一条分开写，防「删一个被另一个顶住」。"""
    base = compute_application_key(**_KEY_BASE)  # type: ignore[arg-type]
    moved = compute_application_key(
        **{**_KEY_BASE, "definition_bundle_sha256": _digest("bundle-opaque")}  # type: ignore[arg-type]
    )
    assert base != moved, (
        "相同 incoming 在不同 definition bundle 下算出了同一个 application key —— "
        "两次写入会被折叠成一次 application（AC 5.5 明令禁止）"
    )


def test_only_the_authority_model_digest_changes_the_key() -> None:
    base = compute_application_key(**_KEY_BASE)  # type: ignore[arg-type]
    moved = compute_application_key(
        **{**_KEY_BASE, "authority_model_definition_sha256": _digest("authority-opaque")}  # type: ignore[arg-type]
    )
    assert base != moved, (
        "相同 incoming 在不同 authority model 下算出了同一个 key —— custom 与 opaque "
        "两条 lane 的写入被折叠（Property 64）"
    )


def test_identical_frozen_identity_is_stable() -> None:
    """对照组：完全相同的 frozen identity 必须算出同一个 key（否则重试无法幂等）。"""
    assert compute_application_key(**_KEY_BASE) == compute_application_key(**_KEY_BASE)  # type: ignore[arg-type]


def test_old_terminal_state_cannot_skip_authorization() -> None:
    """拿着一个旧终态 operation id 无法直接 canonicalize：类型层要求已授权凭证。

    AC 5.5 末句「复用旧终态不得绕过授权」的结构形态：`canonicalize_authorized` 的入参
    是 `AuthorizedOperationRef`（只能由 `authorize_operation_scope` 产出），不是裸 uuid。
    另一半是「授权阶段只读非敏感 scope index」，由
    `assert_authorization_first_source_shape()` 现场 AST 反查。
    """
    params = inspect.signature(RA.RequestApplicationService.canonicalize_authorized).parameters
    annotations = {
        name: str(p.annotation) for name, p in params.items() if name not in ("self",)
    }
    assert any("AuthorizedOperationRef" in a for a in annotations.values()), (
        f"canonicalize_authorized 的入参不再要求已授权凭证: {annotations}"
    )
    assert not any(
        "uuid" in a.lower() and "Authorized" not in a for a in annotations.values()
    ), f"canonicalize_authorized 接受裸 uuid ⇒ 可绕过授权: {annotations}"
    # 授权阶段的仓储调用集合非空且只含 scope 读取（覆盖计数非空，防空集恒等价）
    calls = RA.assert_authorization_first_source_shape()
    assert calls, "授权阶段一个仓储方法都没调 ⇒ 判据分母为空"
    assert set(calls) <= RA._SCOPE_ONLY_REPO_CALLS
