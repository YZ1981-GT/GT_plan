# -*- coding: utf-8 -*-
r"""Task 65 真实 PostgreSQL 守卫：opaque lane 真的能消费、projection bundle 真的被拒、
application identity 真的不折叠。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 65
点名 Property：**50 / 64 / 69**
点名 AC：2.11 · 3.9 · 5.5 · 6.19 · 12.6 · 12.10

═══ 这一半证的是「真的落库了 + 真的拒得住 + identity 真的不折叠」 ═══

离线那半（`test_task65_opaque_authority_bundle.py`）证判据存在且形状正确，但纯 AST /
签名判据**可能守着一段死代码**。本文件在真库上证明：

* 五条 lane 经**生产那份** `OpaqueEntryGate.resolve_approved_bundle` 各自解析到一个
  approved authority-model definition + approved bundle，三个 typed slot 全是 registry
  版本化 typed null marker 且 digest 与 registry 逐项等值（AC 6.19 / Property 50）；
* 两个 authority model 的 bundle digest **不同** —— 这是 Property 64 「相同 incoming 在
  不同 bundle / authority model 下必须产生不同 key」在 opaque 通道上真实存在差异化输入
  的前提，不是假设；
* Task 76 发布的 `projection_contract` bundle（三 slot 全 approved `definition`）经 gate
  **必被拒**且错误码是 `opaque_bundle_slot_not_typed_null_marker` —— 两条通道的 slot
  规则相反，混用即 AC 2.3 失守；
* frozen `(bundle_id, sha256)` 不符 / bundle 不存在 / authority child 与 lane 登记不符
  三种越权各自 fail closed 且**各有自己的 error_code**；
* `compute_application_key` 在**真实** digest 上满足：同一 incoming + 同一 frozen base +
  同 room/generation 时，只换 `definition_bundle_sha256` 或只换
  `authority_model_definition_sha256` ⇒ key 必变；两个 digest 为空 / 全零 ⇒ `IdentityError`。

═══ 采集与隔离 ═══

本文件**只读**（`select` + 纯函数），不建 scratch schema、不写任何行 —— 它读的是
`fix_task65_provision_opaque_authority_bundles.py --apply` 已经发布的真实行。因此它对
库的前置要求是「已 provision」；未 provision 时
`test_all_lanes_are_consumable_after_provision` 会红并指出该跑哪条命令，这正是
AC 6.19 「先发布后消费」的可观测形态，不是环境问题。

全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（Task 21~29 实测：第二个起 `NoneType has no attribute send`）。
采集阶段异常一律**记录不穿透**：穿透会把整个 module 变成 collection ERROR，而 `-rf`
只列 FAILED 不列 ERROR ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。
`test_no_phase_crashed_during_collection` 是这个决定的另一半。

用法（仓库根）::

    .\.venv\Scripts\python.exe -m pytest \
        backend/tests/workpaper_sync/test_task65_opaque_authority_bundle_pg.py -q
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import sqlalchemy as sa  # noqa: E402

from app.services.workpaper_sync import opaque_entry_gate as OG  # noqa: E402
from app.services.workpaper_sync.definitions import TYPED_NULL_MARKERS  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    IdentityError,
    compute_application_key,
)

ALL_ZERO = "0" * 64


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""


def _err(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-8:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


def _row_stub(bundle: Any, authority: Any) -> dict[str, SimpleNamespace]:
    """把两行 ORM row 拷成纯属性对象，按 `bundle` / `authority` 具名返回。

    `OpaqueEntryGate._build` 只读属性、不做任何 ORM 操作，所以 stub 是**等价**输入；
    这样做是为了让快照在 session 关闭后仍可用（detached ORM 对象的懒加载会炸）。

    🔴 具名 dict 而不是 tuple：首版返 tuple，于是取用侧写成 `rows[0].id` 时拿到的是
    tuple 而不是 bundle ⇒ `AttributeError` 被 phase 的 `except` 记成「gate 拒绝了」，
    四条越权判据全部变成假绿的近亲（错误码字段里装着 `AttributeError`）。
    """
    return {
        "bundle": SimpleNamespace(
            id=bundle.id,
            state=bundle.state,
            authority_model_definition_id=bundle.authority_model_definition_id,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            canonical_payload_sha256=bundle.canonical_payload_sha256,
            template_slot_type=bundle.template_slot_type,
            template_slot_ref=bundle.template_slot_ref,
            template_slot_digest=bundle.template_slot_digest,
            instrumentation_slot_type=bundle.instrumentation_slot_type,
            instrumentation_slot_ref=bundle.instrumentation_slot_ref,
            instrumentation_slot_digest=bundle.instrumentation_slot_digest,
            contract_slot_type=bundle.contract_slot_type,
            contract_slot_ref=bundle.contract_slot_ref,
            contract_slot_digest=bundle.contract_slot_digest,
        ),
        "authority": SimpleNamespace(
            id=authority.id,
            kind=authority.kind,
            state=authority.state,
            sha256=authority.sha256,
            authority_model_type=authority.authority_model_type,
        ),
    }


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.workpaper_sync_models import (
        WorkpaperSyncDefinitionArtifact,
        WorkpaperSyncDefinitionBundle,
    )

    snap: dict[str, Any] = {"errors": {}, "lanes": {}, "rows": {}}
    if not settings.DATABASE_URL.startswith("postgresql"):
        snap["errors"]["engine"] = (
            "本文件读 V151 的真实表，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}"
        )
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as session:
            gate = OG.OpaqueEntryGate(session=session)
            # ── phase 1：逐 lane 跑生产 gate ────────────────────────────────
            for lane_id in OG.lane_ids():
                try:
                    resolved = await gate.resolve_approved_bundle(lane_id=lane_id)
                except Exception as exc:  # noqa: BLE001 - 如实记录
                    snap["lanes"][lane_id] = {
                        "consumable": False,
                        "error_code": getattr(exc, "error_code", type(exc).__name__),
                        "error": str(exc).splitlines()[0],
                    }
                    continue
                snap["lanes"][lane_id] = {
                    "consumable": True,
                    "authority_model": resolved.authority_model.value,
                    "bundle_id": str(resolved.bundle_id),
                    "bundle_sha256": resolved.bundle_sha256,
                    "authority_definition_id": str(resolved.authority_model_definition_id),
                    "authority_sha256": resolved.authority_model_definition_sha256,
                    "slot_inventory": [list(x) for x in resolved.typed_slot_inventory],
                }

            # ── phase 2：把三类 bundle row 拷成 stub（两个 opaque + 一个 projection）──
            try:
                rows = (
                    await session.execute(
                        sa.select(
                            WorkpaperSyncDefinitionBundle, WorkpaperSyncDefinitionArtifact
                        ).join(
                            WorkpaperSyncDefinitionArtifact,
                            WorkpaperSyncDefinitionArtifact.id
                            == WorkpaperSyncDefinitionBundle.authority_model_definition_id,
                        )
                    )
                ).all()
                for bundle, authority in rows:
                    key = str(authority.authority_model_type)
                    snap["rows"].setdefault(key, []).append(_row_stub(bundle, authority))
            except Exception as exc:  # noqa: BLE001
                snap["errors"]["rows"] = _err(exc)

            # ── phase 3：projection bundle 经 opaque gate 必被拒 ─────────────
            projection_rows = snap["rows"].get(AuthorityModel.projection_contract.value) or []
            projection = projection_rows[0]["bundle"] if projection_rows else None
            if projection is None:
                snap["errors"]["projection_absent"] = (
                    "库里没有 `projection_contract` bundle —— 本判据需要一个三 slot 全 "
                    "approved definition 的真实 bundle 作反例；请先运行 Task 76 的 "
                    "`fix_task76_provision_projection_definitions.py --apply`"
                )
            else:
                try:
                    await gate.resolve_approved_bundle(
                        lane_id="custom_cells",
                        frozen_bundle_id=projection.id,
                        frozen_bundle_sha256=projection.canonical_payload_sha256,
                    )
                    snap["projection_rejected"] = None  # 没抛 ⇒ 判据失守
                except Exception as exc:  # noqa: BLE001
                    snap["projection_rejected"] = getattr(
                        exc, "error_code", type(exc).__name__
                    )

            # ── phase 4：frozen 越权三形态 ──────────────────────────────────
            opaque_rows = snap["rows"].get(
                AuthorityModel.custom_authoritative_ooxml.value
            ) or []
            custom_bundle = opaque_rows[0]["bundle"] if opaque_rows else None
            if custom_bundle is None:
                snap["errors"]["custom_bundle_absent"] = (
                    "库里没有 `custom_authoritative_ooxml` bundle —— 请先运行 "
                    f"{OG.PROVISION_HOST_SCRIPT} --apply"
                )
            else:
                try:
                    await gate.resolve_approved_bundle(
                        lane_id="custom_cells",
                        frozen_bundle_id=custom_bundle.id,
                        frozen_bundle_sha256="c" * 64,
                    )
                    snap["frozen_digest_mismatch"] = None
                except Exception as exc:  # noqa: BLE001
                    snap["frozen_digest_mismatch"] = getattr(
                        exc, "error_code", type(exc).__name__
                    )
                try:
                    await gate.resolve_approved_bundle(
                        lane_id="custom_cells", frozen_bundle_id=uuid.UUID(int=0)
                    )
                    snap["frozen_bundle_absent"] = None
                except Exception as exc:  # noqa: BLE001
                    snap["frozen_bundle_absent"] = getattr(
                        exc, "error_code", type(exc).__name__
                    )
    except Exception as exc:  # noqa: BLE001 - 采集级失败也记录不穿透
        snap["errors"]["collect"] = _err(exc)
    finally:
        await engine.dispose()
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


# ═══════════════════════════════════════════════════════════════════════════
# §0 采集自检
# ═══════════════════════════════════════════════════════════════════════════


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集阶段一个异常都不许被吞成「无数据」。

    与「记录不穿透」是同一决定的两半：穿透会让整个 module 变 collection ERROR（`-rf`
    看不到），不记录则会让后续断言在空数据上恒真。
    """
    assert not snap["errors"], f"采集阶段异常: {snap['errors']}"


# ═══════════════════════════════════════════════════════════════════════════
# §1 五条 lane 真的能消费
# ═══════════════════════════════════════════════════════════════════════════


def test_all_lanes_are_consumable_after_provision(snap: dict[str, Any]) -> None:
    """AC 6.19 的正面：provision 之后每条 lane 都能经生产 gate 解析到 approved bundle。

    🔴 本条红 + 错误码 `opaque_authority_bundle_not_provisioned` ⇒ **不是环境问题**，
    而是「先发布后消费」在起作用：请先运行
    `.\\.venv\\Scripts\\python.exe backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py --apply`。
    """
    blocked = {
        lane_id: item
        for lane_id, item in snap["lanes"].items()
        if not item.get("consumable")
    }
    assert not blocked, (
        f"以下 lane 无法消费: {blocked}\n"
        f"若错误码是 `opaque_authority_bundle_not_provisioned`，请先运行："
        f"\n  .\\.venv\\Scripts\\python.exe {OG.PROVISION_HOST_SCRIPT} --apply"
    )
    assert set(snap["lanes"]) == set(OG.lane_ids())


def test_every_lane_bundle_has_three_registry_markers(snap: dict[str, Any]) -> None:
    """OG-4 真库侧：三 slot 全 registry marker 且 digest 与 registry 逐项等值。"""
    expected = {
        slot.value: (
            TYPED_NULL_MARKERS[f"{slot.value}:none:v1"].slot_type,
            TYPED_NULL_MARKERS[f"{slot.value}:none:v1"].slot_digest,
        )
        for slot in BundleSlot
    }
    for lane_id, item in snap["lanes"].items():
        inventory = {row[0]: (row[1], row[2]) for row in item["slot_inventory"]}
        assert inventory == expected, (
            f"lane {lane_id} 的 typed slot inventory 与 marker registry 不符：\n"
            f"  实得 {inventory}\n  registry {expected}"
        )


def test_lane_authority_model_matches_registration(snap: dict[str, Any]) -> None:
    """lane 登记的 authority model 与真库解析结果双向锁死。"""
    for lane in OG.OPAQUE_AUTHORITY_LANES:
        got = snap["lanes"][lane.lane_id]["authority_model"]
        assert got == lane.authority_model.value, (
            f"lane {lane.lane_id} 登记 {lane.authority_model.value}，真库解析出 {got}"
        )


def test_bundle_digest_differs_across_authority_models(snap: dict[str, Any]) -> None:
    """Property 64 的前提：两个 authority model 的 bundle digest 必须不同。

    若两者相同，「相同 incoming 在不同 authority model 下产生不同 application key」这条
    就没有差异化输入可用 —— 判据会变成一句无法证伪的话。
    """
    by_model = {
        item["authority_model"]: item["bundle_sha256"] for item in snap["lanes"].values()
    }
    assert len(by_model) >= 2, f"登记表只覆盖了 {sorted(by_model)} 一个 authority model"
    assert len(set(by_model.values())) == len(by_model), (
        f"不同 authority model 的 bundle digest 撞了: {by_model}"
    )
    authority_digests = {
        item["authority_model"]: item["authority_sha256"] for item in snap["lanes"].values()
    }
    assert len(set(authority_digests.values())) == len(authority_digests), (
        f"不同 authority model 的 authority definition digest 撞了: {authority_digests}"
    )


def test_lanes_sharing_one_authority_model_share_one_bundle(snap: dict[str, Any]) -> None:
    """内容寻址的必然结果：同一 authority model 下的 lane 共用一份 bundle。

    opaque bundle 的 canonical payload 只由 authority digest + 三个 marker digest 组成，
    所以同 authority model 的 canonical bytes 逐字节相同；而
    `canonical_payload_sha256` 有 UNIQUE 约束 ⇒ 「一 lane 一 bundle」物理上不可能。
    lane 之间的独立性体现在 entry_id / representation generation / evidence 上。
    """
    for model in {lane.authority_model for lane in OG.OPAQUE_AUTHORITY_LANES}:
        lanes = OG.lanes_for_authority_model(model)
        digests = {snap["lanes"][lane.lane_id]["bundle_sha256"] for lane in lanes}
        assert len(digests) == 1, (
            f"authority model {model.value} 的 {len(lanes)} 条 lane 解析到 "
            f"{len(digests)} 个不同 bundle: {digests} —— 内容寻址下这不可能，"
            "说明 gate 的选择判据引入了 lane 相关的分支"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §2 越权三形态各自 fail closed
# ═══════════════════════════════════════════════════════════════════════════


def test_projection_bundle_is_rejected_by_opaque_gate(snap: dict[str, Any]) -> None:
    """Task 76 的 `projection_contract` bundle 必被 opaque gate 拒。

    🔴 期望错误码是 `opaque_authority_definition_state_invalid` 而**不是**
    `opaque_bundle_slot_not_typed_null_marker`。这是判据顺序的实情，也是它该有的顺序：
    projection bundle 的第一原因是 **authority child 的枚举不对**
    （`projection_contract` ≠ 本 lane 登记的 `custom_authoritative_ooxml`），而不是 slot
    形态不对。`_build` 的 authority 三条判据先跑完，才轮到 slot。

    首版这条写的是 slot 错误码，实测红了 —— 而那次红暴露的是本模块一个真实缺陷：
    slot 判据在 frozen 路径上**从未被真实执行过**（任何 projection bundle 都先被
    authority 判据挡住），也就是 additive 注入即死代码（假绿第①源）。修法不是改判据
    顺序（authority 确实更根本），而是补
    :func:`test_slot_marker_guard_is_reachable_through_the_gate` 证明 slot 判据在 gate
    的真实调用路径上可达且会拒。
    """
    assert snap["projection_rejected"] == "opaque_authority_definition_state_invalid", (
        "opaque gate 对 projection bundle 的第一原因应是 authority child 枚举不符 "
        f"（实得 {snap['projection_rejected']!r}）—— 两条通道的 authority/slot 规则相反，"
        "混用即 AC 2.3 失守"
    )


class _StubSession:
    """按序返回预置 row 的最小 session（只实现 `execute`）。

    用它是为了让 slot 判据在 gate 的**真实调用路径**上被执行到：库里不存在
    「opaque authority + definition slot」这种组合（provision 只发 marker bundle，
    而 V151 的 `wpsync_check_bundle_slots` 只对 `projection_contract` 要求三 slot 全
    definition，对 opaque **不**要求全 marker —— 那正是 gate 这条判据要补的 DB 缺口）。
    """

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.calls = 0

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        value = self._results[self.calls]
        self.calls += 1
        return SimpleNamespace(
            scalar_one_or_none=lambda: value, first=lambda: value, scalars=lambda: value
        )


def test_slot_marker_guard_is_reachable_through_the_gate(snap: dict[str, Any]) -> None:
    """OG-4 的可达性：走完整 `resolve_approved_bundle`，slot 判据必须真的拒。

    构造的是 V151 **拦不住**的那种 bundle：authority child 是合法的
    `custom_authoritative_ooxml`（所以 `_build` 三条 authority 判据全过），但 contract
    slot 是 approved `definition`。这在库里发布得出来 —— gate 是唯一防线。
    """
    opaque = snap["rows"].get(AuthorityModel.custom_authoritative_ooxml.value) or []
    projection = snap["rows"].get(AuthorityModel.projection_contract.value) or []
    assert opaque and projection, "需要两类 bundle 快照各一份"
    good_bundle = opaque[0]["bundle"]
    authority = opaque[0]["authority"]
    donor = projection[0]["bundle"]

    hybrid = SimpleNamespace(
        **{
            **vars(good_bundle),
            "contract_slot_type": donor.contract_slot_type,
            "contract_slot_ref": donor.contract_slot_ref,
            "contract_slot_digest": donor.contract_slot_digest,
        }
    )
    assert hybrid.contract_slot_type == "definition", (
        "供体 bundle 的 contract slot 应是 definition，否则这条判据测的是另一个分支"
    )
    gate = OG.OpaqueEntryGate(session=_StubSession([hybrid, authority]))  # type: ignore[arg-type]
    with pytest.raises(OG.OpaqueSlotNotTypedNullMarkerError) as exc:
        asyncio.run(
            gate.resolve_approved_bundle(
                lane_id="custom_cells",
                frozen_bundle_id=hybrid.id,
                frozen_bundle_sha256=hybrid.canonical_payload_sha256,
            )
        )
    message = str(exc.value)
    assert "definition" in message and "6.19" in message

    # 反向自检：把 contract slot 换回真实 marker，同一条路径必须通过。没有这一半时，
    # 上面那条红可能来自任何环节（stub 顺序错、lane 不对……），而不是 slot 判据。
    ok_gate = OG.OpaqueEntryGate(session=_StubSession([good_bundle, authority]))  # type: ignore[arg-type]
    resolved = asyncio.run(
        ok_gate.resolve_approved_bundle(
            lane_id="custom_cells",
            frozen_bundle_id=good_bundle.id,
            frozen_bundle_sha256=good_bundle.canonical_payload_sha256,
        )
    )
    assert resolved.bundle_id == good_bundle.id


def test_frozen_digest_mismatch_has_its_own_error_code(snap: dict[str, Any]) -> None:
    """frozen `(bundle_id, sha256)` 不符 ⇒ 专属 error_code（禁按当前 alias 顶替）。"""
    assert snap["frozen_digest_mismatch"] == "opaque_bundle_digest_mismatch", (
        f"实得 {snap['frozen_digest_mismatch']!r}"
    )


def test_missing_frozen_bundle_has_its_own_error_code(snap: dict[str, Any]) -> None:
    """frozen bundle 不存在 ⇒ `opaque_authority_bundle_not_provisioned`。

    与上一条分成两个 error_code 是**有意**的：合成一类时删掉 digest 比对会被
    「不存在」分支接住并抛同样的码 ⇒ 只断言类型的守卫判 GREEN。
    """
    assert snap["frozen_bundle_absent"] == "opaque_authority_bundle_not_provisioned", (
        f"实得 {snap['frozen_bundle_absent']!r}"
    )


def test_authority_child_mismatching_lane_is_rejected(snap: dict[str, Any]) -> None:
    """lane 登记的 authority model 与 bundle 的 authority child 不符 ⇒ 专属 error_code。

    判据落在 `_build` 上（纯函数、无 IO），输入是真库两行 row 的等价 stub。构造方式是把
    `custom_cells` 这条 lane 的 authority model 换成 `opaque_single_onlyoffice`，再喂给它
    `custom_authoritative_ooxml` 的真实 bundle —— 这正是「lane 登记漂移后仍能拿到一个
    bundle」的形态，它会让 evidence 的 authority 分桶指向另一条通道。
    """
    rows = snap["rows"].get(AuthorityModel.custom_authoritative_ooxml.value) or []
    assert rows, "缺 custom_authoritative_ooxml bundle 快照"
    bundle = rows[0]["bundle"]
    authority = rows[0]["authority"]
    lane = next(
        lane for lane in OG.OPAQUE_AUTHORITY_LANES if lane.lane_id == "custom_cells"
    )
    drifted = replace(
        lane,
        authority_model=AuthorityModel.opaque_single_onlyoffice,
        has_html_counterpart=False,
    )
    gate = OG.OpaqueEntryGate(session=None)  # type: ignore[arg-type]
    with pytest.raises(OG.OpaqueAuthorityDefinitionStateError) as exc:
        gate._build(drifted, bundle, authority)  # noqa: SLF001 - 纯函数判据
    assert "双向锁死" in str(exc.value)
    # 正例：不漂移时同一输入必须通过（否则上面那条红得没有信息量）
    resolved = gate._build(lane, bundle, authority)  # noqa: SLF001
    assert resolved.authority_model is AuthorityModel.custom_authoritative_ooxml


def test_unapproved_authority_child_is_rejected(snap: dict[str, Any]) -> None:
    """authority child 非 approved / kind 不对 ⇒ 同一异常类型但消息可定位。"""
    rows = snap["rows"].get(AuthorityModel.custom_authoritative_ooxml.value) or []
    assert rows, "缺 custom_authoritative_ooxml bundle 快照"
    bundle = rows[0]["bundle"]
    authority = rows[0]["authority"]
    lane = next(
        lane for lane in OG.OPAQUE_AUTHORITY_LANES if lane.lane_id == "custom_cells"
    )
    gate = OG.OpaqueEntryGate(session=None)  # type: ignore[arg-type]
    base = dict(
        id=authority.id,
        kind=authority.kind,
        state=authority.state,
        sha256=authority.sha256,
        authority_model_type=authority.authority_model_type,
    )
    for field, value, needle in (
        ("kind", "template", "authority_model"),
        ("state", "candidate", "approved"),
    ):
        broken = SimpleNamespace(**{**base, field: value})
        with pytest.raises(OG.OpaqueAuthorityDefinitionStateError) as exc:
            gate._build(lane, bundle, broken)  # noqa: SLF001
        assert needle in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# §3 application identity：same incoming + 不同 bundle/authority ⇒ key 必变
# ═══════════════════════════════════════════════════════════════════════════


def _fixed_identity(snap: dict[str, Any]) -> dict[str, Any]:
    """一组固定的 frozen identity 入参（除 bundle/authority digest 外全部相同）。"""
    custom = snap["lanes"]["custom_cells"]
    return {
        "wp_id": uuid.UUID(int=1),
        "room_id": uuid.UUID(int=2),
        "generation": 1,
        "frozen_client_base_version_id": uuid.UUID(int=3),
        "frozen_client_base_representation_id": uuid.UUID(int=4),
        "incoming_sha256": "a" * 64,
        "definition_bundle_sha256": custom["bundle_sha256"],
        "authority_model_definition_sha256": custom["authority_sha256"],
        "adapter_build_digest": "b" * 64,
    }


def test_same_incoming_different_bundle_yields_different_key(snap: dict[str, Any]) -> None:
    """Property 64 / AC 5.5：只换 bundle digest ⇒ application key 必变。

    用的是真库里两个 authority model 的**真实** bundle digest，不是合成字符串 ——
    合成字符串证明的只是 sha256 的性质，不是「本平台真的有两个不同的 opaque bundle
    身份可用」。
    """
    base = _fixed_identity(snap)
    opaque = next(
        item
        for item in snap["lanes"].values()
        if item["authority_model"] == AuthorityModel.opaque_single_onlyoffice.value
    )
    key_custom = compute_application_key(**base)
    key_other_bundle = compute_application_key(
        **{**base, "definition_bundle_sha256": opaque["bundle_sha256"]}
    )
    assert key_custom != key_other_bundle, (
        "相同 incoming + 相同 frozen base 在**不同 bundle** 下算出了同一个 "
        "application_key —— 两条 lane 的写入会被折叠成一次 application"
    )


def test_same_incoming_different_authority_model_yields_different_key(
    snap: dict[str, Any]
) -> None:
    """只换 authority model digest ⇒ application key 必变。"""
    base = _fixed_identity(snap)
    opaque = next(
        item
        for item in snap["lanes"].values()
        if item["authority_model"] == AuthorityModel.opaque_single_onlyoffice.value
    )
    key_custom = compute_application_key(**base)
    key_other_authority = compute_application_key(
        **{**base, "authority_model_definition_sha256": opaque["authority_sha256"]}
    )
    assert key_custom != key_other_authority, (
        "相同 incoming 在**不同 authority model** 下算出了同一个 application_key —— "
        "custom 与 opaque 的写入会被折叠"
    )


def test_identical_frozen_identity_is_stable(snap: dict[str, Any]) -> None:
    """反向自检：全部入参相同时 key 必须稳定。

    没有这条时，上面两条「key 必变」可以被一个「每次都返回随机值」的实现满足 ——
    那样 status 6 / status 2 / 网络重试也不会命中同一个 application（Property 64 的
    另一半）。
    """
    base = _fixed_identity(snap)
    assert compute_application_key(**base) == compute_application_key(**base)


def test_empty_or_all_zero_digests_are_rejected(snap: dict[str, Any]) -> None:
    """AC 5.5：bundle / authority digest 永远非空 —— 空串与全零 hash 都拒。

    全零单独测：它在 `char(64)` 与 hex 正则层面都合法，是典型的「忘了算 hash 就填 0」
    伪身份。
    """
    base = _fixed_identity(snap)
    for field in ("definition_bundle_sha256", "authority_model_definition_sha256"):
        for bad in ("", ALL_ZERO, "   ", "ABC", "a" * 63):
            with pytest.raises(IdentityError) as exc:
                compute_application_key(**{**base, field: bad})
            assert field in str(exc.value), (
                f"{field}={bad!r} 的拒绝消息里应指名是哪个入参"
            )
