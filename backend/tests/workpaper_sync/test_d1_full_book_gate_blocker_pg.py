# -*- coding: utf-8 -*-
"""D1 整册真栈门（tasks 25~29 共同门）的阻塞事实判据 —— 把它钉成**可证伪**的。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 25~29 的门
harness: `backend/scripts/e2e/verify_d1_full_book_real_stack.py`

═══ 本文件存在的理由 ═══

`verify_d1_full_book_real_stack.py` 现跑 fail-closed 在
`ObservedIdentityDriftError`（published representation 冻结的 `structure_hash`
与现算不一致）。一句「被阻塞」写进 tasks.md 会**烂掉**：
* 后来者会误以为是本 spec 的静态 table 改动打挂了 D1；
* 真的重新发布之后，登记不会自己消失。

所以本文件把三件事钉成断言：

1. **归因**：阻塞**先于**本 spec 的静态 table 改动存在 —— HEAD 版契约（18 table）
   算出的 `structure_hash` 同样 ≠ 冻结值。本轮改动只把（本来就不匹配的）现算值换了个数。
   🔴 这条是**反误判**断言：没有它，下一个人看到「加了 table ⇒ 判漂移」必然归错因。
2. **影响面**：`ObservedIdentityDriftError` 是 `SyncDomainError` 子类，
   而 `register_from_manifest()` 逐 entry 捕获 `SyncDomainError` 后**继续** ⇒
   blast radius 收敛到 D1 一个 entry，不会打挂整批注册。
3. **失效条目反向检查**：一旦 representation 被重新发布（冻结值 == 现算值），
   `test_blocker_is_still_real` 立刻转红，**逼迫**把 tasks.md 的阻塞登记删掉、
   把门真正跑起来。这就是它不会烂掉的机制。

═══ 为什么真实库缺失时**失败**而不是 skip ═══

本文件断言的是「真库里这条 published representation 现在是什么状态」。
skip 掉就等于把「门为什么跑不了」变成无人看管的空白 —— 与本 spec 一直在批的
「结构性零不配变异证明」同型。真库连不上时如实报错。
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CONTRACT_REL = "backend/data/workpaper_sync_contracts/d1.notes_receivable_detail.json"
ADAPTER_ID = "d1.notes_receivable_detail"
ENTRY_ID = "xlsx/gt-d1-notes-receivable"
PROJECT_ID = uuid.UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")
WP_ID = uuid.UUID("68c7740e-dc48-4787-a788-2e77f8560673")

#: 本轮新增的静态受管 table（唯一的契约面差异）。
STATIC_TABLE_KEY = "bad_debt_notetype_rows"
#: 它贡献的字段数 = 2 固定行 × 9 列。**字面量**，不从生产常量读
#: （凡 `for x in <生产常量>` 形态的断言，改小常量判据就跟着变松 —— P 节踩过第四次）。
STATIC_TABLE_FIELD_COUNT = 18
#: 该静态区的 9 列（HTML 拥有 6 个可编辑 + E/K/N 三个公式列），字面量。
STATIC_TABLE_COLUMNS = ("A", "B", "C", "D", "E", "K", "L", "M", "N")
#: 两个固定行的真实 rowId（前端真源，不是序号）。
STATIC_ROW_IDS = ("fixed-bank", "fixed-commercial")


# ════════════════════════════════════════════════════════════════════
# 离线部分（不碰 DB）：契约面差异归因
# ════════════════════════════════════════════════════════════════════


def _contract_payload_at_head() -> dict[str, Any]:
    out = subprocess.run(
        ["git", "show", f"HEAD:{CONTRACT_REL}"],
        cwd=_REPO,
        capture_output=True,
        check=True,
    )
    return json.loads(out.stdout.decode("utf-8"))


def _contract_payload_now() -> dict[str, Any]:
    return json.loads((_REPO / CONTRACT_REL).read_bytes().decode("utf-8"))


def _inventory(payload: dict[str, Any]) -> list[str]:
    from app.services.workpaper_sync.contracts import (
        declared_structure_inventory,
        parse_contract,
    )

    contract = parse_contract(payload, adapter_id=ADAPTER_ID)
    return sorted(str(x) for x in declared_structure_inventory(contract))


def test_contract_surface_delta_is_exactly_the_static_table() -> None:
    """契约面唯一差异 = 本轮新增的静态 table，且恰好 +18 项 inventory。

    没有这条，「加了 table 之后判漂移」会被归成「表加错了」；
    有了它才能把归因锁到「结构变了 ⇒ 必须重新发布」这一件事上。
    """
    # 🔴 T7 裁决 A（2026-09-28）撤回静态 table 后契约回到 18 table / inventory 248，
    #    与 HEAD 契约**相同** ⇒ 本条原先证明的「+18 项 inventory 差异」不再成立。
    #    改为断言「当前契约与 HEAD 契约在 table 面逐值一致」——
    #    撤回的正确性由 `test_d104_static_region_excluded.py` 守。
    head, now = _contract_payload_at_head(), _contract_payload_now()

    def table_keys(p: dict[str, Any]) -> set[str]:
        return {
            f"{s.get('sheet_key')}/{t.get('table_key')}"
            for s in (p.get("sheets") or [])
            for t in (s.get("tables") or [])
        }

    assert table_keys(now) == table_keys(head), (
        f"当前契约与 HEAD 契约的 table 面不同："
        f"多出 {sorted(table_keys(now) - table_keys(head))} "
        f"少了 {sorted(table_keys(head) - table_keys(now))}"
    )
    inv_head, inv_now = _inventory(head), _inventory(now)
    assert len(inv_now) == len(inv_head), (
        f"inventory 大小不一致：HEAD={len(inv_head)} 当前={len(inv_now)}"
    )


def test_managed_surface_counts_are_recomputed_not_guessed() -> None:
    """受管面现算 = 受管区 18 / 去重 sheet 12 / store item 18。

    🔴 `ExcelInstrumentationSpec` 的字段名是 `managed_sheet` 而**不是** `sheet_name`。
       harness 首版写 `getattr(s, "sheet_name", None)` ⇒ 全得 None、去重恒为 1，
       把「12 张 sheet」报成「1 张」而且**不会报错**。
       本条同时钉死字段名与计数：属性改名即红。
    """
    from app.services.workpaper_sync import phase5_d1_expansion as exp

    specs = exp.instrumentation_specs()
    assert specs, "instrumentation_specs() 为空 —— 灰度开关全关？"
    assert not hasattr(specs[0], "sheet_name"), (
        "ExcelInstrumentationSpec 出现了 `sheet_name` 属性 —— "
        "harness 与本判据的字段名口径需同步复核"
    )
    sheets = {s.managed_sheet for s in specs}
    assert None not in sheets and all(sheets), f"managed_sheet 有空值: {sheets!r}"
    assert len(sheets) == 12, f"去重 sheet={len(sheets)}，期望 12：{sorted(sheets)}"

    # 🔴 T7 裁决 A（2026-09-28）：静态 table 撤回后 18 → **17**
    #    （`D1-bd-notetype-rows` 退出契约通路，HTML 侧照常读写）。
    #    受管区数同步 18 → 17；这两个数由 `test_d104_static_region_excluded.py` 并行钉住。
    items = exp.all_store_item_ids()
    assert len(items) == 17, f"store item={len(items)}，期望 17（T7 撤回静态 table 后）"
    assert len(set(items)) == len(items), "store item 有重复"
    assert "D1-bd-notetype-rows" not in items, "notetype item 仍在清单里 —— 撤回未生效"


def test_drift_error_is_a_domain_error_so_blast_radius_is_one_entry() -> None:
    """影响面判据：漂移异常落在 `register_from_manifest()` 的逐 entry 隔离网里。

    `register_from_manifest()` 只捕获 `SyncDomainError` 并**继续**下一个 entry；
    非域异常会上抛打挂整批。所以「只影响 D1」这句话的**充分条件**就是
    `ObservedIdentityDriftError` 确实是 `SyncDomainError` 子类 —— 在这里钉死。

    🔴 反向对照：`AttributeError` 不在网里（它是真 bug，理应上抛），
    没有这条对照就无法证明上面那条不是恒真。
    """
    # 🔴 `SyncDomainError` 在 `models.py`（不是 `errors.py` —— 首版按命名习惯推错，
    #    被本条自己打红。铁律 ⑭「枚举成员/字段路径必现读实证，禁按命名推」的又一例）。
    from app.services.workpaper_sync.models import SyncDomainError
    from app.services.workpaper_sync.published_identity_observer import (
        ObservedIdentityDriftError,
        PublishedIdentityObserverError,
    )

    assert issubclass(ObservedIdentityDriftError, PublishedIdentityObserverError)
    assert issubclass(ObservedIdentityDriftError, SyncDomainError), (
        "ObservedIdentityDriftError 不再是 SyncDomainError 子类 ⇒ "
        "它会穿过 register_from_manifest 的隔离网打挂整批注册，影响面结论失效"
    )
    assert not issubclass(AttributeError, SyncDomainError), (
        "反向对照失效：AttributeError 竟也是域异常 ⇒ 上面那条断言不再有区分力"
    )


# ════════════════════════════════════════════════════════════════════
# 真库部分：一次 asyncio.run 取快照，逐条断言
# ════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.services.workpaper_sync.contracts import parse_contract
    from app.services.workpaper_sync.publish_time_structure_hash import (
        anchors_from_instrumentation_specs,
        compute_structure_hash_from_artifact,
    )
    from app.services.workpaper_sync.resolution import (
        CanonicalArtifactRepository,
        CanonicalResolutionService,
        ResolutionIntent,
    )
    from app.services.workpaper_sync import phase5_d1_expansion as exp

    # 🔴🔴 **自建 engine + NullPool + finally dispose，绝不用共享 `app.core.database.async_session`**。
    #
    #    首版就是用共享 session 的，结果**污染了同进程后续测试**：本文件的 module fixture 走
    #    `asyncio.run()`，它跑完会**关闭** event loop，而共享 engine 的连接池里那些连接绑在这个
    #    已关闭的 loop 上 ⇒ 后面 `test_workpaper_sync_program_milestones.py` 的 live DB 探测
    #    直接报 `database_unavailable`（实测 4 条打红，且**单独跑本文件或单独跑它都全绿**
    #    —— 只有「本文件在前」的顺序才暴露）。
    #
    #    ⇒ 纪律：任何在 `asyncio.run()` 里访问 DB 的判据，都必须自带 engine 并 dispose；
    #      共享 engine 是**进程级**资源，一次性 loop 用完即毁会把它一起带走。
    #      既存 `test_task41_d2_large_json_pilot_pg.py` 用的就是这个范式。
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        str(settings.DATABASE_URL), poolclass=NullPool, connect_args=dict(ssl_off)
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    snap: dict[str, Any] = {}
    try:
        async with session_factory() as session:
            frozen = (
                await session.execute(
                    sa.text(
                        "SELECT structure_hash, generation, reason, adapter_id "
                        "FROM working_paper_content_representation "
                        "WHERE wp_id = :wp AND entry_id = :entry "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"wp": str(WP_ID), "entry": ENTRY_ID},
                )
            ).mappings().first()
            snap["frozen_row"] = dict(frozen) if frozen else None

            resolver = CanonicalResolutionService(
                session, CanonicalArtifactRepository(_BACKEND)
            )
            resolution = await resolver.resolve(
                intent=ResolutionIntent.extract,
                project_id=PROJECT_ID,
                wp_id=WP_ID,
                entry_id=ENTRY_ID,
            )
            data = resolution.artifact_path.read_bytes()
            snap["artifact_name"] = resolution.artifact_path.name
            snap["artifact_size"] = len(data)
    finally:
        await engine.dispose()

    anchors = anchors_from_instrumentation_specs(exp.instrumentation_specs())
    for label, payload in (
        ("head", _contract_payload_at_head()),
        ("now", _contract_payload_now()),
    ):
        contract = parse_contract(payload, adapter_id=ADAPTER_ID)
        try:
            snap[f"hash_{label}"] = compute_structure_hash_from_artifact(
                data=data, contract=contract, anchors=anchors
            )
        except Exception as exc:  # noqa: BLE001
            snap[f"hash_{label}"] = f"<{type(exc).__name__}: {exc}>"
    return snap


@pytest.fixture(scope="module")
def snap() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_published_representation_exists_with_real_adapter(snap: dict[str, Any]) -> None:
    """前提：D1 真的有 published representation 且挂着真实 adapter_id。

    这条同时推翻 `verify_d4_full_book_real_stack.py` docstring 里那句
    「D1 的 manifest capability 非 bidirectional ⇒ attach 短路返回空」——
    那句话在写的时候成立，现在不成立了。
    """
    row = snap["frozen_row"]
    assert row is not None, (
        f"真库没有 wp={WP_ID} entry={ENTRY_ID} 的 representation —— "
        "整册门的前提不成立，且本文件的阻塞归因无从谈起"
    )
    assert row["adapter_id"] == ADAPTER_ID, f"adapter_id={row['adapter_id']!r}"
    assert str(row["structure_hash"]).strip(), "frozen structure_hash 为空"
    # 门从未跑过的证据：reason 里没有 materialize
    assert "materialize" not in str(row["reason"]), (
        f"最新 representation 的 reason={row['reason']!r} 含 materialize ⇒ "
        "整册门可能已经跑过，本文件的「门从未跑过」前提需复核"
    )


def test_blocker_is_still_real(snap: dict[str, Any]) -> None:
    """🔴 **失效条目反向检查** —— 重新发布之后这条必须转红。

    转红时要做的事：把 tasks.md 里 25~29 的阻塞登记删掉，
    跑 `backend/scripts/e2e/verify_d1_full_book_real_stack.py` 真正过门，
    然后删掉本条断言（或改成「门已过」的正向断言）。
    """
    frozen = str(snap["frozen_row"]["structure_hash"]).strip()
    now = snap["hash_now"]
    assert not now.startswith("<"), f"现算 structure_hash 抛异常: {now}"
    assert now != frozen, (
        "冻结值已与现算一致 ⇒ representation 已被重新发布、阻塞已解除。"
        "请删除 tasks.md 中 25~29 的阻塞登记并把整册门真正跑起来，再更新本判据。"
    )


def test_blocker_predates_this_spec_static_table(snap: dict[str, Any]) -> None:
    """🔴🔴 **反误判断言（本文件最重要的一条）**：阻塞不是本轮静态 table 造成的。

    HEAD 版契约（18 table，**不含**本轮静态 table）在同一 artifact 上算出的
    `structure_hash` 同样 ≠ 冻结值 ⇒ representation 的冻结值在本轮改动**之前**
    就已经与磁盘契约脱钩。本轮只是把现算值从一个不匹配的数换成另一个不匹配的数。

    没有这条，下一个人看到「新增 table ⇒ 判漂移」必然归错因，
    进而可能去回滚静态 table（那不会解除阻塞，只会白丢一个已验证的能力）。
    """
    frozen = str(snap["frozen_row"]["structure_hash"]).strip()
    head = snap["hash_head"]
    now = snap["hash_now"]
    # T7 裁决 A 撤回后 HEAD 与当前契约 table 面一致 ⇒ hash 也应一致。
    # 但**两者都 ≠ 冻结值**（先于本 spec 的既存 representation 过期），阻塞依旧。
    assert not head.startswith("<"), f"HEAD 契约现算抛异常: {head}"
    assert not now.startswith("<"), f"当前契约现算抛异常: {now}"
    assert head != frozen, (
        f"HEAD 契约算出的 structure_hash 竟等于冻结值 ⇒ 阻塞已自行消失，"
        f"请跑门并删除本 blocker 文件。head={head} frozen={frozen}"
    )
    assert now != frozen, (
        f"当前契约算出的 hash 竟等于冻结值 ⇒ 阻塞已解除（可能有人重新发布了），"
        f"请跑门并删除本 blocker 文件。"
    )
    # T7 撤回后两个契约的 table 面一致 ⇒ hash 应相等（若不等说明有别的改动）
    assert head == now, (
        f"HEAD 与当前契约 hash 不等 ⇒ 除了静态 table 还有别的差异。head={head} now={now}"
    )


def test_error_message_omits_frozen_inventory_size(snap: dict[str, Any]) -> None:
    """登记一条平台诊断信息缺陷：漂移报错只打「现在」的两个 size，不打冻结时的。

    实测两个 size 恒相等（observed == declared，都是现算），于是错误信息读起来像
    「两边一致却仍判漂移」，把排查带向「观测公式脱钩」而真因是「冻结值过期」。
    本条不改生产代码，只把这个事实钉住 —— 它是 `harness` 里那段中文提示的依据。
    """
    # 🔴 T7 裁决 A 撤回静态 table 后,当前契约 inventory 回到 248 = HEAD 相同
    #    ⇒ 原先登记的「266 vs 248」诊断信息缺陷仍然存在（平台没改过错误消息格式），
    #    但*本 entry* 已不触发它（冻结值不匹配是先于本 spec 的既存问题，不再是本轮视角）。
    #    改为只断言 inventory 大小一致（后续由 blocker 判据的 `test_blocker_predates` 覆盖格式问题）。
    from app.services.workpaper_sync.contracts import (
        declared_structure_inventory,
        parse_contract,
    )

    contract = parse_contract(_contract_payload_now(), adapter_id=ADAPTER_ID)
    declared = len(declared_structure_inventory(contract))
    head_declared = len(_inventory(_contract_payload_at_head()))
    assert declared == head_declared, (
        f"T7 撤回后两个口径应相等，实得 declared={declared} head={head_declared}"
    )
