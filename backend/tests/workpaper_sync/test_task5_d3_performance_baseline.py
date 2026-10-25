"""D3 Task 5：性能基线 + adapter_registered 现状登记（判据脚本，非生产代码）。

spec: d3-sync-coverage-via-row-table-engine · Task 5
Requirements: 6.1, 6.4, 7.3

本脚本现测两件事：
1. 真栈三端点（pending-mutations / store-projection / materialize）与整册 materialize
   是否可跑 —— 依赖 `_registration()`（`wp_sync_router.py`）成功解析 D3 的 adapter。
   若不可跑，如实记录失败原因，并给出**引擎层**（跳过 adapter 分派）的合成基线替代口径。
2. `store_field_count` / `field_count` 的实测值（引擎层，非端点层——端点层因①不可达）。

🔴 不得用 store_field_count 与 field_count 作差推断数据丢失（两者口径不同，
   `store_field_count` 是纯 store payload 现算字段数，`field_count` 是叠加 published
   substrate 基线脚手架之后的字段数，差值主要是脚手架占位字段，不是「丢数据」）。

用法（仓库根，需要真库 `audit-postgres` 可连，不需要真后端进程）::

    python -m pytest backend/tests/workpaper_sync/test_task5_d3_performance_baseline.py -v -s
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

D3_ENTRY_ID = "xlsx/gt-d3-prepaid-accounts"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真栈三端点 + 整册 materialize —— 实测尝试（预期因 adapter 未注册而不可达）
# ═══════════════════════════════════════════════════════════════════════════


async def test_real_registration_path_fails_before_reaching_d3() -> None:
    """真实生产路径：`_attach_pilot_adapters` 等价调用（`register_from_manifest`）。

    这是 `store-projection` / `pending-mutations` / `materialize` 三端点共同的唯一前置门
    （`wp_sync_router._registration()`）。本判据只断言「现状确实跑不到 D3」并把具体报错
    记下来，不断言应该修好（那是 provisioning / 契约重发布的范围，不在本 spec）。
    """
    from app.core.database import async_session
    from app.services.workpaper_sync.adapters.registry import (
        RegistryError,
        build_production_registry,
    )
    from app.services.workpaper_sync.models import SyncDomainError

    async with async_session() as session:
        registry = build_production_registry()
        with pytest.raises((RegistryError, SyncDomainError)) as exc_info:
            await registry.register_from_manifest(session=session)
        print(
            f"\n[real-stack] register_from_manifest() 现状真抛出："
            f"{type(exc_info.value).__name__}: {exc_info.value}"
        )
        print(
            "[real-stack] 这是 wp_sync_router._registration() 会捕获并翻译成 HTTP 422 "
            "的同一类异常（RegistryError/SyncDomainError）——三端点与整册 materialize 在"
            "这一步之后一步都走不到，与 D3 本身是否已注册无关（发生在 D3 轮次之前的其他 "
            "entry 的契约漂移就会先炸）。"
        )


async def test_d3_isolated_attach_confirms_not_registered_reason() -> None:
    """跳开共享的全量注册 pass，单独跑 D3 自己的 attach，钉住 D3 真实的未注册原因。

    实测：manifest 声明的 capability 是 `single_onlyoffice`（不是 `bidirectional`），
    `manifest_capability_enabled()` 因此返回 False，`attach_adapters()` 在**任何 DB 查询
    之前**就短路返回 `()`。这与 Task 0 证据文档援引的 `registry.py` 静态注释
    （"D3-det-rows 全库 0 行、无 published representation"）**不是同一个原因**——本次
    实测确认真库其实已经有 3 条 published representation（`generation=1`，`reason` 分别为
    `content_commit` ×2 / `rematerialize` ×1，均带非空 `definition_bundle_id`），
    `_describe_entry_supply()` 的三项供给判据（entry pointer / representation 存在 /
    bundle 绑定）在 DB 层面均已满足。真正卡点是 manifest 层的 capability 声明，
    不是 DB 供给缺口。
    """
    from app.core.database import async_session
    from app.services.workpaper_sync.adapters.registry import (
        RegistryError,
        WorkpaperSyncAdapterRegistry,
    )
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )
    from app.services.workpaper_sync.models import SyncDomainError
    from app.services.workpaper_sync.phase5_d3_prepaid_receipts import (
        attach_pilot_adapters as attach_d3_pilot_adapters,
    )

    raw_manifest = load_entry_manifest()
    entries = manifest_entries_by_id(raw_manifest)
    d3_entry = entries.get(D3_ENTRY_ID)
    assert d3_entry is not None, "manifest 必须含 D3 entry，否则连判定对象都没有"
    capability = str(d3_entry.get("capability") or "")
    print(f"\n[isolated] manifest 里 D3 现状 capability={capability!r}")
    print(f"[isolated] manifest 里 D3 现状 adapter_id={d3_entry.get('adapter_id')!r}")

    registry = WorkpaperSyncAdapterRegistry(manifest=raw_manifest)
    async with async_session() as session:
        try:
            ids = await attach_d3_pilot_adapters(registry, session=session)
        except (RegistryError, SyncDomainError) as exc:
            pytest.fail(
                f"attach_pilot_adapters() 意外抛出而不是静默返回 ()：{type(exc).__name__}: {exc}"
            )
    print(f"[isolated] D3 attach_pilot_adapters() 返回：{ids}")
    assert ids == (), (
        "D3 现状应为未注册（返回空 tuple）——若此断言开始失败，说明 D3 已从别处被裁决为 "
        "bidirectional 并重生 manifest，adapter_registered 现状已变，需回去更新 Task 0 结论"
    )
    assert capability != "bidirectional", (
        f"D3 manifest capability 现状={capability!r}，仍非 bidirectional，"
        "是 attach_adapters() 短路返回 () 的直接原因（manifest_capability_enabled() 检查点）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 合成基线替代口径 —— 引擎层耗时（跳过 adapter 分派，不冒充真栈）
# ═══════════════════════════════════════════════════════════════════════════


def _d3_contract() -> Any:
    from app.services.workpaper_sync.phase5_d3_prepaid_receipts import (
        assert_contract_file_matches_source,
    )

    return assert_contract_file_matches_source()


def _synthetic_rows(n: int) -> str:
    """构造 n 行 D3-2 明细表的合成 JSON payload（字段形状仿真实 rowId+业务字段）。"""
    rows = [
        {
            "rowId": f"GTROW-D32-SYNTH-{i:06d}",
            "customerName": f"synthetic-customer-{i}",
            "openingBalanceCredit": 1000.0 + i,
            "currentCreditAmount": 500.0 + i,
            "currentDebitAmount": 200.0 + i,
            "closingBalanceCredit": 1300.0 + i,
            "agingWithinYear": 800.0 + i,
            "aging1to2Years": 300.0 + i,
            "aging2to3Years": 150.0 + i,
            "agingOver3Years": 50.0 + i,
            "remark": f"synth-remark-{i}",
        }
        for i in range(n)
    ]
    return json.dumps(rows, ensure_ascii=False)


@pytest.mark.parametrize("n_rows", [1, 10, 50, 200])
def test_synthetic_engine_layer_baseline_build_store_projection(n_rows: int) -> None:
    """引擎层耗时基线：`build_store_projection`（跳过 adapter 分派 + DB + HTTP）。

    🔴 这不是端到端真栈耗时——不含 HTTP 往返 / guard / registration / materialize 写盘 /
    OnlyOffice room。只测「provider 把 store payload 现算成 projection」这一段纯函数耗时，
    作为 adapter_registered 解除之前唯一可离线现测的替代信号。
    """
    from app.services.workpaper_sync.phase5_d3_prepaid_receipts import (
        build_store_projection,
    )

    contract = _d3_contract()
    payload = _synthetic_rows(n_rows)
    started = time.perf_counter()
    projection = build_store_projection(payload, contract=contract)
    elapsed_ms = (time.perf_counter() - started) * 1000
    field_count = len(projection.values)
    print(
        f"\n[synthetic-engine] n_rows={n_rows} store_field_count(values)={field_count} "
        f"elapsed_ms={elapsed_ms:.3f}"
    )
    assert field_count > 0, "合成 payload 非空时投影不得为空"


async def test_real_db_payload_engine_layer_store_field_count() -> None:
    """用真库现有的 1 行真实 D3-det-rows 载荷（59 字节）现测 store_field_count。

    这是「引擎层」口径（`len(store_projection.values)`），与端点层 `store-projection` 返回的
    `store_field_count` 定义逐字相同（`store_projection_response.py:234`
    `store_field_count = len(store_projection.values)`），区别只是本判据跳过了
    `_overlay_with_published_substrate`（那一步需要 `_registration()` 先成功，不可达）。

    🔴 环境注意（Windows only）：本文件前两个用例已用 `async_session()` 跨越了 pytest-asyncio
    的函数级事件循环边界，模块级 `engine` 连接池里可能残留绑定在**已关闭**循环上的连接
    （`ProactorEventLoop` + asyncpg 已知交互问题，非本判据的产品代码缺陷）。显式
    `await engine.dispose()` 清空池，强制本测试用当前循环重新建连接。
    """
    from app.core.database import async_session, engine
    import sqlalchemy as sa

    from app.services.workpaper_sync.phase5_d3_prepaid_receipts import (
        STORE_ITEM_ID,
        build_store_projection,
    )

    await engine.dispose()
    async with async_session() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses WHERE item_id = :item LIMIT 1"
                ),
                {"item": STORE_ITEM_ID},
            )
        ).scalar_one_or_none()
        payload = str(row) if row is not None else None
    assert payload is not None, f"真库应有 {STORE_ITEM_ID} 至少一行（Task 1 证据已确认）"
    contract = _d3_contract()
    started = time.perf_counter()
    projection = build_store_projection(payload, contract=contract)
    elapsed_ms = (time.perf_counter() - started) * 1000
    store_field_count = len(projection.values)
    print(
        f"\n[real-db-payload] item={STORE_ITEM_ID!r} payload_bytes={len(payload)} "
        f"store_field_count={store_field_count} elapsed_ms={elapsed_ms:.3f}"
    )
    print(
        "[real-db-payload] 🔴 本值是「引擎层 store_field_count」（跳过 substrate overlay），"
        "不等于端点层 field_count（那个会再叠加 published 基线脚手架字段）——两者不同口径，"
        "不得作差推断丢失字段。"
    )
    assert store_field_count > 0
