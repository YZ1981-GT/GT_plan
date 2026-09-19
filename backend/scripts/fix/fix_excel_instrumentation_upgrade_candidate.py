"""为**已发布**的 Excel projection entry 登记 non-current instrumentation upgrade candidate。

**Spec: workpaper-html-onlyoffice-bidirectional-writeback-closure** · Task 17 的生产宿主
（Task 76 的 `--apply` 只能 attach 一个**已存在**的 `awaiting_contract` candidate，它自己
明确拒绝自建第三条 representation 写入路径。）

═══ 为什么需要这个宿主 ══════════════════════════════════════════════════════════

`ProjectionDefinitionProvisioner._settle_representation_stage` 在「已有 current
representation 但它绑的不是本次 approved bundle」时返回 `blocked`，理由原文：

    ②已有 representation 时，纯 definitions 升级须先由 Task 17 的 instrumentation
      upgrader 登记 non-current candidate。

而 Task 17 的 `ExcelInstrumentationUpgrader` 一直**只被测试调用** ——
`working_paper_representation_upgrade_candidate` 全库实测 **0 行**，于是它交付的那条
受控 attach 入口在生产路径上从未被执行过（假绿第①源「additive 注入即死代码」）。
本脚本就是那一步的生产入口。

═══ 边界（刻意窄，且 fail closed）════════════════════════════════════════════════

* **只登记 candidate**，`state=awaiting_contract`，三个 target 全 `None`。
  绑 contract/bundle 归 Task 76 的受控 attach；finalize 归 Task 36 的门。
  三者分离不是流程洁癖：合起来写就绕过了 `assert_candidate_finalizable` 的五条前置。
* **candidate 字节 = 权威模板按新 spec 重新 instrument 的产物**。
  为什么不拿当前已发布的 artifact 再 instrument 一次：`instrument_workbook_bytes` 自己
  就拒绝（「源 artifact 已含 instrumentation 部件 —— 重复注入会产生第二套 identity；
  存量 instrumented artifact 应走 definition 升级」）。
* 🔴 **store 载荷非空即拒**（`store_payload_not_empty`）。候选字节来自模板 ⇒ 不含业务
  数据。对 store 已有数据的 entry 直接 finalize 会**丢数据**；那条路必须重投影
  （`materialize` + `ContentMutationService`），属 Task 36，不在本宿主内。
  H1 实测 `H1-8-rows` 全库 0 行，故本门今天不挡任何需要升级的 entry；写它是为了不让
  下一个人在有数据的 entry 上误用。
* `rollback_source_sha256` 取**当前已发布 artifact** 的 digest（回滚目标），
  与候选字节（新 instrumented 模板）是两个不同输入 —— upgrader 的 API 本就分开。

═══ 用法 ════════════════════════════════════════════════════════════════════

    python backend/scripts/fix/fix_excel_instrumentation_upgrade_candidate.py --check
    python backend/scripts/fix/fix_excel_instrumentation_upgrade_candidate.py --check --json out.json

    $env:PYTHONIOENCODING='utf-8'
    python backend/scripts/fix/fix_excel_instrumentation_upgrade_candidate.py --apply \
        --entry xlsx/gt-h1-fixed-assets --json out.json

🔴 **判成败一律查数据，不看退出码** —— `--apply` 可能被 Ctrl+C 中断而已提交。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.services.workpaper_sync import (  # noqa: E402
    projection_target_resolution as _TARGET_RESOLUTION,
)

#: 结算词表（封闭；自由文本会让守卫只能比字符串）。
SETTLEMENTS: Final[tuple[str, ...]] = (
    "candidate_registered",
    "candidate_already_pending",
    "candidate_already_ready",
    "already_current",
    "blocked_store_payload_not_empty",
    "blocked_no_current_representation",
    "blocked_unresolved_target",
    "failed",
)

#: 阶段词表 —— `--check` 与 `--apply` 逐阶段同名同序（否则预演与真跑不可比）。
STAGES: Final[tuple[str, ...]] = (
    "target_resolved",
    "current_representation_located",
    "desired_bundle_resolved",
    "upgrade_needed",
    "store_payload_empty",
    "published_artifact_read",
    "definitions_published",
    "instrumented",
    "candidate_registered",
    "candidate_is_non_current",
)

#: 本宿主的来源标识（进 candidate 审计事件的 correlation id）。
SOURCE_COMMIT: Final[str] = "fix_excel_instrumentation_upgrade_candidate@v1"


class UpgradeHostError(RuntimeError):
    """宿主自身的装配/判据失败（与被调用服务层的域异常区分开）。"""


@dataclass(frozen=True)
class _DefinitionHandle:
    """`stage_and_register_candidate` 只取 `.definition_id` / `.sha256` 两个字段。

    刻意只带这两个：多带一个字段就等于在宿主里重建 `PublishedDefinition`，而那会给
    「宿主自造 definition 身份」留出空间 —— 两个值都必须来自已 approved 的库行。
    """

    definition_id: uuid.UUID
    sha256: str


@dataclass
class EntrySettlement:
    entry_id: str
    settlement: str = "failed"
    diagnosis: str = ""
    wp_id: str = ""
    project_id: str = ""
    wp_code: str = ""
    store_bytes: int = 0
    current_representation_id: str = ""
    current_generation: int = 0
    current_bundle_sha256: str = ""
    desired_bundle_sha256: str = ""
    candidate_id: str = ""
    stages: dict[str, bool] = field(default_factory=dict)
    outcome: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "settlement": self.settlement,
            "diagnosis": self.diagnosis,
            "wp_id": self.wp_id,
            "project_id": self.project_id,
            "wp_code": self.wp_code,
            "store_bytes": self.store_bytes,
            "current_representation_id": self.current_representation_id,
            "current_generation": self.current_generation,
            "current_bundle_sha256": self.current_bundle_sha256,
            "desired_bundle_sha256": self.desired_bundle_sha256,
            "candidate_id": self.candidate_id,
            "stages": dict(self.stages),
            "outcome": self.outcome,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 装配
# ═══════════════════════════════════════════════════════════════════════════


def _engine() -> Any:
    from app.core.config import settings

    return create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
        echo=False,
    )


def _artifacts() -> Any:
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    # 🔴 BP-29：根必须是 `BACKEND_ROOT`（= `backend/`），**不是** `storage_root()`
    #    （= `backend/storage`）。artifact 的 `relative_path` 自带 `storage/` 前缀 ⇒
    #    用 `storage_root()` 会写出双层 `backend/storage/storage/...`，而全平台其余
    #    10 处读取方（含生产请求路径 `wp_sync_router`）都用 `BACKEND_ROOT`
    #    ⇒ 发布出来的 representation 一律读不到（实测 142 : 4）。
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT

    return CanonicalArtifactRepository(BACKEND_ROOT)


def _pilot_entry_ids(entry_filter: str | None) -> list[str]:
    """交付登记表里的 projection entry（不写第二份 entry 清单）。"""
    from app.services.workpaper_sync.adapters import registry as registry_module

    out: list[str] = []
    for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(row.get("entry_id") or "").strip()
        if not entry_id:
            continue
        if entry_filter and entry_id != entry_filter:
            continue
        out.append(entry_id)
    return out


async def _current_representation(session: Any, *, wp_id: uuid.UUID, entry_id: str) -> Any:
    """entry 的 current published representation 行（经 entry pointer，不按 generation 猜）。"""
    return (
        await session.execute(
            sa.text(
                "SELECT r.id, r.generation, r.content_version_id, r.artifact_id, "
                "       r.definition_bundle_id, r.definition_bundle_sha256, "
                "       a.relative_path, a.sha256 AS artifact_sha256 "
                "FROM working_paper_sync_entry_state es "
                "JOIN working_paper_content_representation r "
                "  ON r.id = es.current_representation_id "
                "LEFT JOIN working_paper_artifact a ON a.id = r.artifact_id "
                "WHERE es.wp_id = :wp AND es.entry_id = :entry"
            ),
            {"wp": str(wp_id), "entry": entry_id},
        )
    ).first()


async def _pending_candidate(session: Any, *, wp_id: uuid.UUID, entry_id: str) -> Any:
    """本 entry 还没 finalize 的 candidate（`awaiting_contract` 或已 attach 的 `ready`）。

    🔴 口径是「未 finalize」而不是「state='awaiting_contract'」：后者会在 Task 76 的
    受控 attach 把状态推到 `ready` 之后失去命中，于是本宿主重跑时又登记一个 candidate。
    """
    return (
        await session.execute(
            sa.text(
                "SELECT id, state FROM working_paper_representation_upgrade_candidate "
                "WHERE wp_id = :wp AND entry_id = :entry "
                "  AND finalized_representation_id IS NULL "
                "  AND state <> 'rejected' "
                "ORDER BY created_at, id LIMIT 1"
            ),
            {"wp": str(wp_id), "entry": entry_id},
        )
    ).first()


async def _store_bytes(session: Any, *, wp_id: uuid.UUID, store_item_id: str) -> int:
    if not store_item_id:
        return 0
    return int(
        (
            await session.execute(
                sa.text(
                    "SELECT COALESCE(LENGTH(remark), 0) FROM checklist_responses "
                    "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                ),
                {"wp": str(wp_id), "item": store_item_id},
            )
        ).scalar_one_or_none()
        or 0
    )


# ═══════════════════════════════════════════════════════════════════════════
# 逐 entry 结算
# ═══════════════════════════════════════════════════════════════════════════


async def settle_entry(
    session: Any,
    *,
    entry_id: str,
    artifacts: Any,
    apply: bool,
) -> EntrySettlement:
    """一个 entry 的十阶段结算。`apply=False` 时在 `instrumented` 之后停手。"""
    from app.services.workpaper_sync.excel_instrumentation import (
        ExcelInstrumentationUpgrader,
    )
    from app.services.workpaper_sync.projection_provisioning import (
        load_projection_supply,
    )
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository

    item = EntrySettlement(entry_id=entry_id, stages={name: False for name in STAGES})
    supply = load_projection_supply(entry_id)
    provider = supply.provider
    store_item_id = str(getattr(provider, "STORE_ITEM_ID", "") or "")

    # ① 目标解析（BP-24 单一真源）
    target = await _TARGET_RESOLUTION.resolve_projection_target(
        session,
        wp_codes=_TARGET_RESOLUTION.adjudicated_wp_codes(entry_id),
        store_item_id=store_item_id,
    )
    if target is None:
        item.settlement = "blocked_unresolved_target"
        item.diagnosis = f"entry {entry_id} 的裁决码族下没有存活底稿"
        return item
    item.stages["target_resolved"] = True
    wp_id = uuid.UUID(str(target.wp_id))
    project_id = uuid.UUID(str(target.project_id))
    item.wp_id, item.project_id = str(wp_id), str(project_id)
    item.wp_code = str(target.wp_code)
    item.store_bytes = int(target.store_bytes or 0)

    # ② current published representation
    current = await _current_representation(session, wp_id=wp_id, entry_id=entry_id)
    if current is None:
        item.settlement = "blocked_no_current_representation"
        item.diagnosis = (
            f"entry {entry_id} 在 wp={wp_id} 上没有 current published representation —— "
            "首版发布走 `fix_projection_first_publication.py`，本宿主只处理**已发布**的"
            "定义升级"
        )
        return item
    item.stages["current_representation_located"] = True
    item.current_representation_id = str(current.id)
    item.current_generation = int(current.generation)
    item.current_bundle_sha256 = str(current.definition_bundle_sha256 or "")

    # ③ 期望 bundle：走 provider 自己的 `publish_pilot_definitions`（复用模式），
    #    不另算一份 digest。`ReusingDefinitionPublisher` 对已 approved 的同 canonical
    #    digest 直接复用 ⇒ `--check` 不产生新行。
    from app.services.workpaper_sync.projection_provisioning import (
        ReusingDefinitionPublisher,
    )

    repository = WorkpaperSyncRepository(session)
    publisher = ReusingDefinitionPublisher(
        session=session,
        artifacts=artifacts,
        repository=repository,
        project_id=project_id,
        wp_id=wp_id,
        source_commit=SOURCE_COMMIT,
    )
    definitions = await provider.publish_pilot_definitions(publisher)
    item.desired_bundle_sha256 = str(definitions.bundle_sha256)
    item.stages["desired_bundle_resolved"] = True
    if publisher.created_stages:
        raise UpgradeHostError(
            f"entry {entry_id}: 期望 bundle 解析竟然**新建**了 "
            f"{list(publisher.created_stages)} —— 定义链未就位时不得由本宿主补发，"
            "请先跑 `fix_task76_provision_projection_definitions.py --apply`"
        )

    # ④ 是否需要升级
    if str(current.definition_bundle_id) == str(definitions.bundle_id):
        item.settlement = "already_current"
        item.diagnosis = (
            f"current representation {current.id} 已绑定期望 bundle "
            f"{definitions.bundle_sha256[:12]} —— 无需升级（幂等）"
        )
        item.stages["upgrade_needed"] = False
        return item
    item.stages["upgrade_needed"] = True

    # ④b 已有未 finalize 的 candidate ⇒ 幂等：不再登记第二个
    #
    # 🔴 判据**不能**只看 `state='awaiting_contract'`：Task 76 的受控 attach 会把它推到
    #    `ready`，此后再跑本宿主就会又登记一个 candidate（实测：H1 attach 完重跑
    #    `--check` 仍报 `candidate_registered`）。幂等的正确口径是「本 entry 有没有一个
    #    还没 finalize 的 candidate」。
    pending = await _pending_candidate(session, wp_id=wp_id, entry_id=entry_id)
    if pending is not None:
        item.candidate_id = str(pending.id)
        if str(pending.state) == "awaiting_contract":
            item.settlement = "candidate_already_pending"
            item.diagnosis = (
                f"entry {entry_id} 已有 `awaiting_contract` candidate {pending.id} —— "
                "幂等不再登记第二个；绑 contract/bundle 请跑 "
                "`fix_task76_provision_projection_definitions.py --apply`"
            )
        else:
            item.settlement = "candidate_already_ready"
            item.diagnosis = (
                f"entry {entry_id} 的 candidate {pending.id} 已是 `{pending.state}`"
                f"（已绑 approved contract/bundle，未 finalize）—— 幂等不再登记第二个；"
                "finalize 归 Task 36 的 `ExcelEntryFinalizeGate`，不在本宿主内"
            )
        return item

    # ⑤ store 载荷必须为空（否则候选字节会丢数据）
    store_bytes = await _store_bytes(session, wp_id=wp_id, store_item_id=store_item_id)
    item.store_bytes = store_bytes
    if store_bytes > 0:
        item.settlement = "blocked_store_payload_not_empty"
        item.diagnosis = (
            f"entry {entry_id} 的 store item {store_item_id!r} 有 {store_bytes} B 业务载荷。"
            "本宿主的候选字节来自**权威模板**重新 instrument ⇒ 不含业务数据，直接升级会丢"
            "数据。有数据的 entry 必须重投影（materialize + ContentMutationService），"
            "属 Task 36，不在本宿主内。"
        )
        return item
    item.stages["store_payload_empty"] = True

    # ⑥ 当前已发布 artifact 字节（回滚目标）
    if not current.relative_path:
        raise UpgradeHostError(
            f"entry {entry_id}: current representation {current.id} 的 artifact 行缺 "
            "relative_path —— 无法确定回滚源"
        )
        # 上面必抛：不得降级成「回滚源用模板字节」，那会把 rollback digest 写成假的
    # `relative_path` 是相对 `base_root` 的；解析走仓储自己的边界校验方法，
    # 不在宿主里拼路径（拼路径会绕过 `assert_within_root` 的越界判定）。
    published_path = artifacts.resolve_relative_path(str(current.relative_path))
    if not published_path.is_file():
        raise UpgradeHostError(
            f"entry {entry_id}: 已发布 artifact 不在磁盘上: {published_path}"
        )
    published_bytes = published_path.read_bytes()
    item.stages["published_artifact_read"] = True

    # ⑦⑧ 发布 template/instrumentation definition + 注入
    upgrader = ExcelInstrumentationUpgrader(
        session=session,
        repository=repository,
        artifacts=artifacts,
        project_id=project_id,
        source_commit=SOURCE_COMMIT,
        gate=provider.excel_carrier_gate(),
    )
    spec = provider.instrumentation_spec()
    template_bytes = provider.read_authoritative_template()
    # 🔴 **不**调 `upgrader.publish_definitions()`：它内部用的是 `DefinitionPublisher`
    #    （非幂等），对已 approved 的同 digest 直接撞
    #    `uq_wpsda_kind_sha256`（实测 template `ef2e9042958a` 唯一键冲突）。
    #
    #    更重要的是**正确性**：candidate 声明的 template/instrumentation 必须正是目标
    #    bundle 的 typed slot 所引用的那两条 definition。否则 finalize 会绑上一个
    #    「slot 指向 A、candidate 声明 B」的 bundle —— 两边各自自洽而合起来不一致。
    #    第 ③ 步的 `publish_pilot_definitions(ReusingDefinitionPublisher)` 返回的就是
    #    bundle 引用的那两条，直接用它。
    template_def = _DefinitionHandle(
        definition_id=uuid.UUID(str(definitions.template_definition_id)),
        sha256=str(definitions.template_definition_sha256),
    )
    instrumentation_def = _DefinitionHandle(
        definition_id=uuid.UUID(str(definitions.instrumentation_definition_id)),
        sha256=str(definitions.instrumentation_definition_sha256),
    )
    item.stages["definitions_published"] = True
    instrumented, equivalence, inventory = upgrader.instrument_source_bytes(
        source=template_bytes, spec=spec
    )
    item.stages["instrumented"] = True

    if not apply:
        item.settlement = "candidate_registered"
        item.diagnosis = (
            "（--check）前八阶段全通过，`--apply` 会登记 "
            f"awaiting_contract candidate；期望 bundle {definitions.bundle_sha256[:12]}，"
            f"当前 {item.current_bundle_sha256[:12]}"
        )
        return item

    # ⑨⑩ 登记 candidate + 非当前性断言（后者在 upgrader 内部已跑，这里只取 outcome）
    outcome = await upgrader.stage_and_register_candidate(
        spec=spec,
        wp_id=wp_id,
        content_version_id=uuid.UUID(str(current.content_version_id)),
        source_representation_id=uuid.UUID(str(current.id)),
        source_bytes=published_bytes,
        instrumented=instrumented,
        equivalence=equivalence,
        inventory=inventory,
        template_definition=template_def,
        instrumentation_definition=instrumentation_def,
        from_definition_bundle_id=uuid.UUID(str(current.definition_bundle_id)),
        from_definition_bundle_sha256=str(current.definition_bundle_sha256 or ""),
    )
    item.stages["candidate_registered"] = True
    item.stages["candidate_is_non_current"] = (
        outcome.revision_unchanged
        and outcome.pointer_unchanged
        and outcome.no_representation_created
    )
    item.candidate_id = str(outcome.candidate_id)
    item.outcome = outcome.as_dict()
    item.settlement = "candidate_registered"
    item.diagnosis = (
        f"candidate {outcome.candidate_id} 已登记（state={outcome.state.value}，三个 target "
        "全 None）。下一步：`fix_task76_provision_projection_definitions.py --apply` 走受控 "
        "attach 绑 approved contract/bundle；finalize 归 Task 36 的门。"
    )
    return item


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════


async def run(*, apply: bool, entry_filter: str | None, json_path: Path | None) -> int:
    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    artifacts = _artifacts()
    results: list[EntrySettlement] = []
    try:
        for entry_id in _pilot_entry_ids(entry_filter):
            # 🔴 逐 entry 独立事务：`engine.begin()` 内一处失败会把前面已成功的 entry
            #    一起回滚（本仓库踩过）。
            async with Session() as session:
                try:
                    item = await settle_entry(
                        session, entry_id=entry_id, artifacts=artifacts, apply=apply
                    )
                    if apply and item.settlement == "candidate_registered":
                        await session.commit()
                    else:
                        await session.rollback()
                except Exception as exc:  # noqa: BLE001 - 逐 entry 记录后继续
                    await session.rollback()
                    item = EntrySettlement(
                        entry_id=entry_id,
                        settlement="failed",
                        diagnosis=f"{type(exc).__name__}: {exc}",
                    )
                results.append(item)
    finally:
        await engine.dispose()

    report = {
        "mode": "apply" if apply else "check",
        "entries": [item.as_dict() for item in results],
        "settlement_counts": {
            name: sum(1 for i in results if i.settlement == name)
            for name in SETTLEMENTS
            if any(i.settlement == name for i in results)
        },
    }
    if json_path is not None:
        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    print(f"mode={report['mode']} | {report['settlement_counts']}")
    for item in results:
        print(f"  {item.entry_id}")
        print(f"    settlement={item.settlement} candidate={item.candidate_id or '—'}")
        print(
            f"    wp={item.wp_id[:8] if item.wp_id else '—'} code={item.wp_code or '—'} "
            f"store={item.store_bytes}B gen={item.current_generation}"
        )
        print(
            f"    bundle 当前={item.current_bundle_sha256[:12] or '—'} "
            f"期望={item.desired_bundle_sha256[:12] or '—'}"
        )
        if item.diagnosis:
            print(f"    {item.diagnosis}")
    failed = [i for i in results if i.settlement == "failed"]
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读预演（一行库都不写）")
    mode.add_argument("--apply", action="store_true", help="真登记 candidate")
    parser.add_argument("--entry", default=None, help="只处理这一个 entry_id")
    parser.add_argument("--json", dest="json_path", default=None, help="报告落盘路径")
    args = parser.parse_args()
    return asyncio.run(
        run(
            apply=bool(args.apply),
            entry_filter=args.entry,
            json_path=Path(args.json_path) if args.json_path else None,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
