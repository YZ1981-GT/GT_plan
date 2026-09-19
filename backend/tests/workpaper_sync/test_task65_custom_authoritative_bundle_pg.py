r"""Task 65 custom 侧真实 PostgreSQL 守卫：custom 写入路径在**真库**上装配出的
`ContentCommitPlan` 真的以 xlsx 本体为权威、真的不带 adapter/contract、真的把
resolved bundle 的冻结身份带进 application key 的入参。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 65
点名 Property：**50 / 64 / 69**
点名 AC：2.11 · 3.9 · 5.5 · 6.19 · 12.6 · 12.10

═══ 这一半证什么（与另外两个 task65 文件都不重叠）═══

* `test_task65_opaque_authority_bundle_pg.py` 直接调 `OpaqueEntryGate`，证的是**门**在真库
  上拒得住；
* `test_task65_custom_authoritative_bundle.py` 是 AST/签名判据，证的是**形状**对；
* 本文件走**生产装配面** `build_content_mutation_service_writer(session).commit_bytes(...)`，
  证 custom lane 从「端点交出 xlsx 字节」到「统一提交入口收到 plan」这一整段在真库上
  真的跑得通，且 plan 的每一项都是它该有的值。AST 判据可能守着一段永远走不到的代码；
  本文件让那段代码**真的执行一次**。

═══ 为什么在 `ContentMutationService.commit` 上取样，而不是让它真写库 ═══

`commit_bytes` 的函数体只有三步：空载荷拒绝 → `provisioner.resolve(lane_id=...)` →
装配 `ContentCommitPlan` 并交 `commit`。**前两步全部在真库上真实执行**（包含
`OpaqueEntryGate` 的五条判据、两次真实 `select`、`load_bundle_snapshot`）；被替换掉的
只有最后那一次 DB 写。这不是把被测对象 mock 掉 —— 被测对象正是「装配出的 plan 长什么
样」，而取样点就在它的**唯一**出口上。

真写一行 content version 需要一个真的 `working_paper` + project + 落盘 substrate，
且 custom lane 的 room / durable ack 三格尚未接入（`opaque_entry_gate.CUSTOM_LANE_ROOM_DEBT`
登记为 `UNVERIFIABLE`，归 Task 71）。真库实测 `working_paper_content_version` 现为 0 行，
这一事实已登记在 `ENTRY_ID_NAMESPACE_SPLIT_NOTE.measured_migration_cost_at_task65` 里；
本文件不假装那一格已经闭合。

`test_seam_matches_the_production_signature` 锁死取样点不许与生产签名漂移。

═══ 采集与隔离 ═══

全部场景由**一次 `asyncio.run`** 跑完落进快照（module fixture）—— 每个测试各自开 async
会污染共享连接池（第二个起 `NoneType has no attribute send`）。采集阶段异常一律
**记录不穿透**并由 `test_no_phase_crashed_during_collection` 兜底：穿透会把整个 module 变成
collection ERROR，而 `-rf` 只列 FAILED ⇒ 定向变异看不到预期失败项 ⇒ 判 GREEN。

前置：`fix_task65_provision_opaque_authority_bundles.py --apply` 已跑过（AC 6.19 的
「先发布后消费」）。未跑时 `test_custom_lane_assembles_a_plan_on_the_real_db` 会红并指出
该跑哪条命令 —— 那是判据成立的表现，不是环境问题。

用法（仓库根）::

    .\.venv\Scripts\python.exe -m pytest \
        backend/tests/workpaper_sync/test_task65_custom_authoritative_bundle_pg.py -q
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import content_mutation as CM  # noqa: E402
from app.services.workpaper_sync import opaque_entry_gate as OG  # noqa: E402
from app.services.workpaper_sync import writer_migration as WM  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    compute_application_key,
)

CUSTOM_LANE = "custom_cells"

#: 权威载荷：一段**任意但确定**的字节。custom lane 的 `commit_bytes` 不解析它
#: （xlsx 本体原样落盘），所以不需要一个真 workbook；需要的是「交出去的字节与读回的
#: 字节逐字节相同」这件事可被证伪。
AUTHORITATIVE_BYTES = b"PK\x03\x04-task65-custom-authoritative-substrate"


def _err(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-8:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(frames))
    return f"{type(exc).__name__}: {exc} @ {where}"


async def _collect() -> dict[str, Any]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    snap: dict[str, Any] = {"errors": {}, "plans": {}}
    if not settings.DATABASE_URL.startswith("postgresql"):
        snap["errors"]["engine"] = (
            "本文件走生产装配面读 V151 的真实表，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}"
        )
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    tmpdir = tempfile.mkdtemp(prefix="task65_custom_")
    substrate = Path(tmpdir) / "custom.xlsx"
    substrate.write_bytes(AUTHORITATIVE_BYTES)
    try:
        async with Session() as session:
            writer = WM.build_content_mutation_service_writer(session)

            captured: dict[str, Any] = {}

            async def _capture(*, plan: Any, mutation: Any, adapter: Any = None, **rest: Any):
                """取样点：统一提交入口的**唯一**出口。不写库、不返回假 receipt。"""
                captured["plan"] = plan
                captured["mutation"] = mutation
                captured["adapter"] = adapter
                captured["extra"] = dict(rest)
                raise _Sampled()

            writer._mutation.commit = _capture  # type: ignore[method-assign]

            # ── phase 1：真库上跑一次 custom lane 的装配 ─────────────────────
            for lane_id, payload in ((CUSTOM_LANE, AUTHORITATIVE_BYTES),):
                captured.clear()
                try:
                    await writer.commit_bytes(
                        project_id=uuid.uuid4(),
                        wp_id=uuid.uuid4(),
                        entry_id=f"opaque-TASK65-{lane_id}",
                        source=CM.CUSTOM,
                        payload=payload,
                        document_type="xlsx",
                        expected_revision=0,
                        substrate_path=substrate,
                        lane_id=lane_id,
                    )
                    snap["errors"][f"{lane_id}_no_sample"] = (
                        "commit_bytes 没有走到统一提交入口 —— 取样点未被命中"
                    )
                except _Sampled:
                    plan = captured["plan"]
                    mutation = captured["mutation"]
                    snap["plans"][lane_id] = {
                        "authority_model": plan.authority_model.value,
                        "is_projection_based": bool(plan.is_projection_based),
                        "contract_is_none": plan.contract is None,
                        "adapter_is_none": captured["adapter"] is None,
                        "extra_kwargs": sorted(captured["extra"]),
                        "substrate_role": getattr(
                            plan.substrate_role, "value", str(plan.substrate_role)
                        ),
                        "substrate_kind": getattr(
                            plan.substrate_kind, "value", str(plan.substrate_kind)
                        ),
                        "substrate_state": getattr(
                            plan.substrate_state, "value", str(plan.substrate_state)
                        ),
                        "substrate_path": str(plan.substrate_path),
                        "document_type": plan.document_type,
                        "adapter_id": plan.adapter_id,
                        "adapter_build_digest": plan.adapter_build_digest,
                        "projection_is_none": mutation.projection is None,
                        "payload_sha256": hashlib.sha256(
                            mutation.authoritative_payload or b""
                        ).hexdigest(),
                        # 三格未接入的**事实侧**：plan 上这两格必须真的是 None，
                        # 与 `CUSTOM_LANE_ROOM_DEBT` 的登记双向锁死。
                        "room_id": None if plan.room_id is None else str(plan.room_id),
                        "application_id": (
                            None if plan.application_id is None else str(plan.application_id)
                        ),
                        "bundle_id": str(plan.bundle.bundle_id),
                        "bundle_sha256": plan.bundle.bundle_sha256,
                        "bundle_state": getattr(
                            plan.bundle.state, "value", str(plan.bundle.state)
                        ),
                        "authority_definition_sha256": (
                            plan.bundle.authority_model_definition_sha256
                        ),
                        "slot_types": {
                            getattr(k, "value", str(k)): getattr(v, "slot_type", None)
                            for k, v in dict(plan.bundle.slots).items()
                        },
                    }
                except Exception as exc:  # noqa: BLE001 - 如实记录，不 fail-open
                    snap["plans"][lane_id] = {
                        "assembled": False,
                        "error_code": getattr(exc, "error_code", type(exc).__name__),
                        "error": str(exc).splitlines()[0],
                    }

            # ── phase 2：空载荷必须在碰库之前就被拒 ──────────────────────────
            try:
                await writer.commit_bytes(
                    project_id=uuid.uuid4(),
                    wp_id=uuid.uuid4(),
                    entry_id="opaque-TASK65-empty",
                    source=CM.CUSTOM,
                    payload=b"",
                    document_type="xlsx",
                    expected_revision=0,
                    substrate_path=substrate,
                    lane_id=CUSTOM_LANE,
                )
                snap["empty_payload_rejected"] = None
            except _Sampled:
                snap["empty_payload_rejected"] = "REACHED_COMMIT"
            except Exception as exc:  # noqa: BLE001
                snap["empty_payload_rejected"] = type(exc).__name__

            # ── phase 3：未登记 lane 必须 fail closed（authority model 无真源）──
            try:
                await writer.commit_bytes(
                    project_id=uuid.uuid4(),
                    wp_id=uuid.uuid4(),
                    entry_id="opaque-TASK65-unregistered",
                    source=CM.CUSTOM,
                    payload=AUTHORITATIVE_BYTES,
                    document_type="xlsx",
                    expected_revision=0,
                    substrate_path=substrate,
                    lane_id="totally_unregistered_lane",
                )
                snap["unregistered_lane_rejected"] = None
            except _Sampled:
                snap["unregistered_lane_rejected"] = "REACHED_COMMIT"
            except Exception as exc:  # noqa: BLE001
                snap["unregistered_lane_rejected"] = getattr(
                    exc, "error_code", type(exc).__name__
                )
    except Exception as exc:  # noqa: BLE001 - 采集级失败也记录不穿透
        snap["errors"]["collect"] = _err(exc)
    finally:
        await engine.dispose()
    return snap


class _Sampled(RuntimeError):
    """取样点命中的信号（不是失败）。"""


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def _custom(snap: dict[str, Any]) -> dict[str, Any]:
    plan = snap["plans"].get(CUSTOM_LANE)
    assert plan is not None, "采集没有产出 custom lane 的 plan"
    assert plan.get("assembled") is not False, (
        f"custom lane 在真库上装配失败：{plan.get('error_code')} / {plan.get('error')} —— "
        f"若是 `opaque_authority_bundle_not_provisioned`，先跑 "
        f"{OG.PROVISION_HOST_SCRIPT} --apply（AC 6.19：先发布后消费）"
    )
    return plan


# ═══════════════════════════════════════════════════════════════════════════
# §0 采集自检 + 取样点防漂移
# ═══════════════════════════════════════════════════════════════════════════


def test_no_phase_crashed_during_collection(snap: dict[str, Any]) -> None:
    """采集自身不得有未归因失败（禁 fail-open：让守卫红，而不是降级成「无数据」）。"""
    assert not snap["errors"], f"采集阶段有未归因失败: {snap['errors']}"


def test_seam_matches_the_production_signature() -> None:
    """取样点的形参必须与 `ContentMutationService.commit` 的真实签名兼容。

    没有这条时，生产签名一改（比如 `adapter` 改成位置参数），取样点会静默收不到值，
    而所有断言仍然「通过」—— 那正是本 spec 记录的假绿第②源。
    """
    sig = inspect.signature(CM.ContentMutationService.commit)
    kinds = {
        name: p.kind
        for name, p in sig.parameters.items()
        if name != "self"
    }
    assert set(kinds) == {"plan", "mutation", "adapter", "fence"}, (
        f"commit 的形参集合已变: {sorted(kinds)} —— 取样点需同步"
    )
    for name in ("plan", "mutation", "adapter"):
        assert kinds[name] is inspect.Parameter.KEYWORD_ONLY, (
            f"{name} 不再是 keyword-only ⇒ 取样点会收不到它"
        )


# ═══════════════════════════════════════════════════════════════════════════
# §1 custom lane 在真库上真的装配出一个 plan
# ═══════════════════════════════════════════════════════════════════════════


def test_custom_lane_assembles_a_plan_on_the_real_db(snap: dict[str, Any]) -> None:
    """整条链（lane 登记 → gate 五条判据 → bundle snapshot → plan）在真库上跑通一次。"""
    plan = _custom(snap)
    assert plan["authority_model"] == AuthorityModel.custom_authoritative_ooxml.value
    assert plan["is_projection_based"] is False
    assert plan["bundle_state"] == "approved", (
        f"plan 冻结的 bundle 不是 approved: {plan['bundle_state']} —— AC 6.19 要求 approved"
    )


def test_the_committed_payload_is_the_substrate_bytes(snap: dict[str, Any]) -> None:
    """交给统一入口的字节与 substrate 文件逐字节相同，且 projection 侧为空（AC 2.11）。"""
    plan = _custom(snap)
    assert plan["payload_sha256"] == hashlib.sha256(AUTHORITATIVE_BYTES).hexdigest(), (
        "统一入口收到的权威载荷不是原样字节 —— xlsx 本体在途中被改写了"
    )
    assert plan["projection_is_none"] is True, (
        "custom 通道同时交了 projection ⇒ 标准 JSON projection writer 参与了权威内容"
    )
    assert plan["document_type"] == "xlsx"


def test_the_plan_carries_no_adapter_and_no_contract(snap: dict[str, Any]) -> None:
    """`adapter=None` 与 `contract=None` **分开**断言（合成一条时删一个会被另一个顶住）。"""
    plan = _custom(snap)
    assert plan["adapter_is_none"] is True, (
        "custom 通道传了 adapter ⇒ materialize/extract 会介入权威 xlsx（AC 2.11）"
    )
    assert plan["contract_is_none"] is True, (
        "custom plan 携带 per-entry contract ⇒ 转成了 projection 三方协议（AC 6.19）"
    )
    assert plan["extra_kwargs"] == [] or plan["extra_kwargs"] == ["fence"], (
        f"commit 收到了意料之外的实参: {plan['extra_kwargs']}"
    )


def test_the_substrate_is_published_as_a_representation(snap: dict[str, Any]) -> None:
    """custom 的 substrate 进 published representation（「进入统一 representation」的实证）。"""
    plan = _custom(snap)
    assert plan["substrate_role"] == "published_representation"
    assert plan["substrate_kind"] == "canonical"
    assert plan["substrate_state"] == "published"
    assert plan["substrate_path"].endswith("custom.xlsx")


def test_every_frozen_slot_is_a_versioned_typed_null_marker(snap: dict[str, Any]) -> None:
    """plan 冻结的三个 slot 全是版本化 typed null marker（AC 6.19），且三格齐全。"""
    plan = _custom(snap)
    slot_types = plan["slot_types"]
    assert set(slot_types) == {s.value for s in BundleSlot}, (
        f"plan 的 slot 清单不齐: {sorted(slot_types)}"
    )
    for name, slot_type in slot_types.items():
        assert slot_type is not None and slot_type != "definition", (
            f"{name} slot 是 definition child ⇒ projection bundle 被喂进了 custom 通道"
        )
        assert slot_type.startswith(f"{name}:none:v"), (
            f"{name} slot type={slot_type!r} 不是本 slot 的版本化 typed null marker"
        )


def test_the_frozen_digests_are_real_and_non_empty(snap: dict[str, Any]) -> None:
    """两个冻结 digest 非空、非全零、64 位小写 hex —— 它们是 application key 的入参。"""
    plan = _custom(snap)
    for label in ("bundle_sha256", "authority_definition_sha256"):
        value = plan[label]
        assert isinstance(value, str) and len(value) == 64, f"{label} 形态非法: {value!r}"
        assert value == value.lower() and value.strip("0"), f"{label} 是空/全零: {value!r}"
    assert plan["bundle_sha256"] != plan["authority_definition_sha256"], (
        "bundle digest 与 authority digest 相同 ⇒ 两者中有一个没被真正计算"
    )


def test_the_real_frozen_identity_does_not_fold_across_bundles(snap: dict[str, Any]) -> None:
    """用**真库里的真 digest** 验 Property 64：只换 bundle digest ⇒ key 必变。"""
    plan = _custom(snap)
    base = dict(
        wp_id=uuid.UUID(int=7),
        room_id=uuid.UUID(int=8),
        generation=1,
        frozen_client_base_version_id=uuid.UUID(int=9),
        frozen_client_base_representation_id=uuid.UUID(int=10),
        incoming_sha256=hashlib.sha256(AUTHORITATIVE_BYTES).hexdigest(),
        definition_bundle_sha256=plan["bundle_sha256"],
        authority_model_definition_sha256=plan["authority_definition_sha256"],
        adapter_build_digest=plan["adapter_build_digest"],
    )
    same = compute_application_key(**base)  # type: ignore[arg-type]
    other_bundle = compute_application_key(
        **{**base, "definition_bundle_sha256": hashlib.sha256(b"other").hexdigest()}  # type: ignore[arg-type]
    )
    other_authority = compute_application_key(
        **{**base, "authority_model_definition_sha256": hashlib.sha256(b"x").hexdigest()}  # type: ignore[arg-type]
    )
    assert same == compute_application_key(**base)  # type: ignore[arg-type]
    assert same != other_bundle, "相同 incoming + 不同 bundle 折叠成了同一 application key"
    assert same != other_authority, (
        "相同 incoming + 不同 authority model 折叠成了同一 application key"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §2 两种越权在真库上 fail closed
# ═══════════════════════════════════════════════════════════════════════════


def test_empty_payload_is_rejected_before_touching_the_db(snap: dict[str, Any]) -> None:
    """空字节的 digest 是合法但无意义的身份 —— 必须在 resolve 之前就拒。"""
    assert snap.get("empty_payload_rejected") == "WriterMigrationError", (
        f"空载荷未被 fail closed: {snap.get('empty_payload_rejected')!r}"
    )


def test_unregistered_lane_is_rejected_with_its_own_error_code(snap: dict[str, Any]) -> None:
    """未登记 lane ⇒ authority model 没有真源 ⇒ 拒，且错误码是 lane 未登记那一条。"""
    assert snap.get("unregistered_lane_rejected") == "opaque_lane_not_registered", (
        f"未登记 lane 没被专属错误码拒绝: {snap.get('unregistered_lane_rejected')!r}"
    )


def test_the_two_refusals_have_different_identities(snap: dict[str, Any]) -> None:
    """两种越权的标识不同 —— 共用一个时短路其一会被另一个遮蔽。"""
    assert snap.get("empty_payload_rejected") != snap.get("unregistered_lane_rejected")


# ═══════════════════════════════════════════════════════════════════════════
# §3 未闭合的一格如实登记（不假称已接入）
# ═══════════════════════════════════════════════════════════════════════════


def test_room_and_durable_ack_debt_is_still_registered(snap: dict[str, Any]) -> None:
    """custom lane 的 room / durable ack / content application 三格仍登记为未接入。

    本文件证到「统一提交入口收到了正确的 plan」为止。再往前的 room / forcesave durable
    ack / content application 三格由 `CUSTOM_LANE_ROOM_DEBT` 登记为 `UNVERIFIABLE`（归
    Task 71）。这条判据存在的意义是：一旦有人把那三格接上却忘了改登记，或反过来把登记
    改成「已接入」却没接，守卫立刻红。
    """
    debt = OG.CUSTOM_LANE_ROOM_DEBT
    assert debt["lane_id"] == CUSTOM_LANE
    assert debt["verification_status"] == "UNVERIFIABLE"
    assert set(debt["missing_facilities"]) == {
        "unified_room",
        "durable_forcesave_ack",
        "content_application",
    }
    # plan 里确实没有 room / application 绑定 —— 与登记一致（登记与事实双向锁死）。
    # 🔴 两格都必须**存在于快照里**再断言为 None：写成 `"room_id" not in plan` 会是一条
    #    恒真的空判据（本 spec 记录的「等值判据分母为空」形态）。
    plan = _custom(snap)
    for facility in ("room_id", "application_id"):
        assert facility in plan, f"快照缺 {facility} ⇒ 本判据分母为空，需重写采集"
        assert plan[facility] is None, (
            f"plan 已带 {facility}={plan[facility]!r}，但 CUSTOM_LANE_ROOM_DEBT 仍登记为 "
            "UNVERIFIABLE —— 接上了就要改登记，改了登记就要真接上"
        )
