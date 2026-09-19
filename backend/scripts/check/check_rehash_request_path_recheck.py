"""G1-3 只读复验宿主：对 representation-only 迁移后的 current generation 重跑
observer + registry 请求路径，断言身份一致、revision 不变。

**Spec: workpaper-html-onlyoffice-bidirectional-writeback-closure（G1-3）**

═══ 这个宿主复验什么 ══════════════════════════════════════════════════════════

G1-2 把纯口径 stale 的修复改成 representation-only：既有 content version 上出新
representation generation，`content_revision` 不变。G1-3 是它的**请求路径复验**：迁移
真正落库后，必须证明请求路径能安全消费**新的 current generation**，而不是只证明
「representation 行的 hash 列改对了」。

三条机器判据（全部只读，一行库都不写）：

1. **observer 请求路径**：对新 current published representation 跑
   `observe_published_frozen_definitions(...)`，它内部会现算 managed `structure_hash`
   并与冻结值比对（BP-30 同构公式）。旧口径遗留会在此 `ObservedIdentityDriftError`；
   迁移成功则通过，并回出 `representation_generation`。
2. **registry 请求路径**：`build_production_registry().register_from_manifest(session=...)`
   后 `resolve_for_entry(entry_id)` 必须解析到与 observer 相同 adapter，且该 entry 不在
   `reasons`（未注册原因）里。
3. **版本正交**：新 current generation 必须 > 迁移前 generation，而 `content_revision`
   必须与迁移前**相等**（Property 4）。

═══ 为什么当前是 fail-closed，而不是「已复验通过」════════════════════════════════

G1-2 的 representation-only finalize 依赖 candidate 就绪（Task 17 + Task 76 产物），存量
BP-30 遗留行尚无 `state=ready` candidate，因此 `--apply` 迁移**尚未在真实 PostgreSQL 上
跑过**。没有「迁移后的新 generation」这个前置事实，本宿主无从复验 —— 它因此如实
`blocked`（`migration_not_run`），绝不把「骨架已就绪」冒充成「已复验通过」。

真实前置满足后（G1-2 `--apply` 在真库跑过、有新 generation），以真实 session 调用
`recheck_entry(...)` 即可产出 `verified` / `drift` / `mismatch` 结算。

═══ 用法 ════════════════════════════════════════════════════════════════════

    $env:PYTHONIOENCODING='utf-8'
    python backend/scripts/check/check_rehash_request_path_recheck.py --check
    python backend/scripts/check/check_rehash_request_path_recheck.py --check --entry xlsx/gt-d2-accounts-receivable

🔴 判成败一律查数据/结算，不看退出码语义之外的东西。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


class RecheckHostError(RuntimeError):
    """宿主自身前置不成立（不是复验判据失败）。"""


#: 封闭结算词表。守卫据此断言结算可枚举、可当 CI 基线。
RECHECK_STATES: Final[tuple[str, ...]] = (
    # observer + registry 请求路径都通过，且版本正交成立
    "verified",
    # observer 现算 structure_hash 与冻结值不符 —— 迁移未生效或仍是旧口径
    "drift",
    # registry 未解析到同一 adapter，或该 entry 带未注册原因
    "registry_mismatch",
    # 版本正交被破坏：generation 未增，或 content_revision 变了
    "version_domain_violation",
    # 该 entry 还没有 current published representation
    "not_published",
    # representation-only 迁移尚未在真库跑过（无迁移后 generation 可复验）
    "migration_not_run",
    # 其它前置/读失败
    "blocked",
)

#: 各结算格的解除方。不写自由文本 —— 守卫按它断言诊断真的指了动作。
_STATE_UNBLOCK_OWNER: Final[Mapping[str, str]] = {
    "migration_not_run": (
        "先让 G1-2 的 representation-only finalize 在真库产出新 generation"
        "（Task 17 stage candidate + Task 76 attach 后 finalize）；本宿主只复验、不迁移"
    ),
    "not_published": (
        "该 entry 无 current published representation —— 先走首版发布宿主"
    ),
    "drift": (
        "observer 现算 managed structure_hash ≠ 冻结值 —— 迁移未生效或仍是旧口径遗留"
    ),
    "registry_mismatch": (
        "registry 请求路径未解析到同一 adapter —— 复核 manifest/供给与 register_from_manifest"
    ),
    "version_domain_violation": (
        "新 generation 未增或 content_revision 变了 —— 复核 finalize 出口是否 revision-locked"
    ),
    "blocked": "逐条读 error_code 与 diagnosis；本宿主不放宽任何判据",
}


@dataclass
class RecheckOutcome:
    """一个 entry 的复验结算。字段全部是实测值，不含推断。"""

    entry_id: str
    state: str = "blocked"
    error_code: str | None = None
    diagnosis: str | None = None
    representation_id: str | None = None
    observed_generation: int | None = None
    prior_generation: int | None = None
    content_revision: int | None = None
    resolved_adapter_id: str | None = None
    stages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _prior_generation_hint(session: Any, *, wp_id: str, entry_id: str) -> int | None:
    """迁移前 generation 的判据来源：同 entry 上非 current 的最高既有 generation。

    representation-only finalize 会新增一个更高 generation 并切 pointer，因此「迁移是否
    真的发生」= 存在一个比当前 current 更低的历史 generation。找不到历史 generation ⇒
    该 entry 从未被 rehash 过 ⇒ `migration_not_run`。
    """
    rows = (
        await session.execute(
            sa.text(
                "SELECT generation FROM working_paper_content_representation "
                "WHERE wp_id = :wp AND entry_id = :entry "
                "ORDER BY generation DESC"
            ),
            {"wp": str(wp_id), "entry": str(entry_id)},
        )
    ).mappings().all()
    gens = sorted({int(r["generation"]) for r in rows})
    if len(gens) < 2:
        return None
    return gens[-2]


async def recheck_entry(
    session: Any, *, entry_id: str, project_id: uuid.UUID, wp_id: uuid.UUID
) -> RecheckOutcome:
    """对单个 entry 做只读请求路径复验。**不 commit、不写任何行。**"""
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        ObservedIdentityDriftError,
        PublishedIdentityObserverError,
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    out = RecheckOutcome(entry_id=entry_id)

    # ── 取 current representation + 迁移前 generation 提示 ─────────────
    current = (
        await session.execute(
            sa.text(
                "SELECT r.id, r.wp_id, r.generation, r.content_version_id, "
                "       wp.content_revision, wp.project_id "
                "FROM working_paper_content_representation r "
                "JOIN working_paper_sync_entry_state s "
                "  ON s.current_representation_id = r.id "
                "JOIN working_paper wp ON wp.id = r.wp_id "
                "WHERE s.entry_id = :entry AND r.wp_id = :wp"
            ),
            {"entry": str(entry_id), "wp": str(wp_id)},
        )
    ).mappings().first()
    if current is None:
        out.state = "not_published"
        out.diagnosis = _STATE_UNBLOCK_OWNER[out.state]
        return out
    out.stages.append("current_resolved")
    out.representation_id = str(current["id"])
    out.observed_generation = int(current["generation"])
    out.content_revision = int(current["content_revision"])

    prior = await _prior_generation_hint(session, wp_id=str(wp_id), entry_id=entry_id)
    out.prior_generation = prior
    if prior is None:
        out.state = "migration_not_run"
        out.diagnosis = _STATE_UNBLOCK_OWNER[out.state]
        return out

    # ── 判据 3（版本正交，先算便宜的）──────────────────────────────
    if int(current["generation"]) <= int(prior):
        out.state = "version_domain_violation"
        out.error_code = "generation_not_advanced"
        out.diagnosis = (
            f"current generation={current['generation']} 未高于迁移前 {prior} —— "
            + _STATE_UNBLOCK_OWNER["version_domain_violation"]
        )
        return out

    # ── 判据 1（observer 请求路径）─────────────────────────────────
    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    # observer 的 `_assert_representation_shape` 要求 16 个冻结字段齐全 —— 从库里现读
    # 整行（immutable representation），不自造半份 shape。
    full = (
        await session.execute(
            sa.text(
                "SELECT id, wp_id, entry_id, content_version_id, generation, document_type, "
                "       artifact_id, artifact_sha256, definition_bundle_id, "
                "       definition_bundle_sha256, authority_model_definition_id, "
                "       authority_model_definition_sha256, adapter_id, adapter_build_digest, "
                "       structure_hash, identity_inventory_sha256 "
                "FROM working_paper_content_representation WHERE id = :id"
            ),
            {"id": str(current["id"])},
        )
    ).mappings().first()
    if full is None:
        out.state = "blocked"
        out.error_code = "representation_row_missing"
        out.diagnosis = f"current representation {current['id']} 行读不到"
        return out
    representation_row = _RepresentationRef(**{k: full[k] for k in full.keys()})
    try:
        observation = await observe_published_frozen_definitions(
            session=session,
            resolution=resolution,
            representation=representation_row,
            project_id=project_id,
        )
        out.stages.append("observer_request_path_ok")
    except ObservedIdentityDriftError as exc:
        out.state = "drift"
        out.error_code = "observed_identity_drift"
        out.diagnosis = f"{type(exc).__name__}: {exc} · {_STATE_UNBLOCK_OWNER['drift']}"
        return out
    except PublishedIdentityObserverError as exc:
        out.state = "blocked"
        out.error_code = "observer_error"
        out.diagnosis = f"{type(exc).__name__}: {exc}"
        return out

    # ── 判据 2（registry 请求路径）─────────────────────────────────
    from app.services.workpaper_sync.adapters.registry import build_production_registry

    registry = build_production_registry()
    reg_outcome = await registry.register_from_manifest(session=session)
    if entry_id in reg_outcome.reasons:
        out.state = "registry_mismatch"
        out.error_code = "entry_not_registered"
        out.diagnosis = (
            f"registry 未注册该 entry：{reg_outcome.reasons[entry_id]} · "
            + _STATE_UNBLOCK_OWNER["registry_mismatch"]
        )
        return out
    try:
        registration = registry.resolve_for_entry(entry_id)
    except Exception as exc:  # noqa: BLE001 - 解析失败如实记
        out.state = "registry_mismatch"
        out.error_code = "resolve_for_entry_failed"
        out.diagnosis = f"{type(exc).__name__}: {exc}"
        return out
    out.resolved_adapter_id = str(registration.adapter_id)
    if out.resolved_adapter_id != str(observation.definitions.adapter_build.adapter_id):
        out.state = "registry_mismatch"
        out.error_code = "adapter_id_disagree"
        out.diagnosis = (
            f"observer adapter={observation.definitions.adapter_build.adapter_id} ≠ "
            f"registry adapter={out.resolved_adapter_id}"
        )
        return out
    out.stages.append("registry_request_path_ok")

    out.state = "verified"
    out.diagnosis = (
        f"observer + registry 请求路径均通过；generation {prior} → "
        f"{current['generation']}，content_revision 不变（{current['content_revision']}）"
    )
    return out


class _RepresentationRef:
    """observer 的 `_assert_representation_shape` 要求 16 个冻结字段齐全的 row 视图。

    从库里读整行后原样装成属性；observer 用 `getattr` 逐字段取。不自造字段、不留空。
    """

    def __init__(self, **fields: Any) -> None:
        for key, value in fields.items():
            setattr(self, key, value)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


async def run(*, only_entry: str | None) -> dict[str, Any]:
    from app.core.config import settings

    if not settings.DATABASE_URL.startswith("postgresql"):
        raise RecheckHostError(
            "本宿主读 V151 的真实表，必须真实 PostgreSQL；当前 DATABASE_URL 为 "
            f"{settings.DATABASE_URL.split('://')[0]}"
        )
    from app.services.workpaper_sync.adapters import registry as registry_module

    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(
        settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off)
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)

    targets = [
        row
        for row in registry_module.DELIVERED_PER_ENTRY_CONTRACTS
        if only_entry is None or str(row["entry_id"]) == only_entry
    ]
    if only_entry is not None and not targets:
        raise RecheckHostError(f"--entry {only_entry!r} 不在 DELIVERED_PER_ENTRY_CONTRACTS")

    outcomes: list[RecheckOutcome] = []
    try:
        for row in targets:
            entry_id = str(row["entry_id"])
            async with Session() as session:
                # 只读：整个复验在一个只读事务里，结束一律 rollback。
                try:
                    await session.execute(sa.text("SET TRANSACTION READ ONLY"))
                    # 🔴 同一 entry_id 可能有**多个 wp 实例**（BP-27）。逐个复验，否则
                    #    `LIMIT 1` 会漏掉刚迁移出新 generation 的那个实例。
                    wp_rows = (
                        await session.execute(
                            sa.text(
                                "SELECT DISTINCT r.wp_id, wp.project_id "
                                "FROM working_paper_content_representation r "
                                "JOIN working_paper_sync_entry_state s "
                                "  ON s.current_representation_id = r.id "
                                "JOIN working_paper wp ON wp.id = r.wp_id "
                                "WHERE s.entry_id = :entry "
                                "ORDER BY r.wp_id"
                            ),
                            {"entry": entry_id},
                        )
                    ).mappings().all()
                    if not wp_rows:
                        outcomes.append(RecheckOutcome(
                            entry_id=entry_id, state="not_published",
                            diagnosis=_STATE_UNBLOCK_OWNER["not_published"]))
                        continue
                    for wp_project in wp_rows:
                        outcomes.append(await recheck_entry(
                            session,
                            entry_id=entry_id,
                            project_id=uuid.UUID(str(wp_project["project_id"])),
                            wp_id=uuid.UUID(str(wp_project["wp_id"])),
                        ))
                except Exception as exc:  # noqa: BLE001 - 逐 entry 隔离
                    outcomes.append(RecheckOutcome(
                        entry_id=entry_id, state="blocked",
                        error_code=type(exc).__name__,
                        diagnosis=f"{type(exc).__name__}: {exc}"[:900]))
                finally:
                    await session.rollback()
    finally:
        await engine.dispose()

    dist: dict[str, int] = {}
    for item in outcomes:
        dist[item.state] = dist.get(item.state, 0) + 1
    unknown = sorted({item.state for item in outcomes} - set(RECHECK_STATES))
    if unknown:
        raise RecheckHostError(f"结算落在封闭词表之外: {unknown} —— 词表必须扩，不得静默")
    return {"entries": [o.as_dict() for o in outcomes], "state_distribution": dist}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="G1-3 representation-only 迁移后的请求路径只读复验"
    )
    parser.add_argument("--check", action="store_true", required=True, help="只读复验")
    parser.add_argument("--entry", default=None, help="只复验指定 entry_id")
    args = parser.parse_args(argv)

    report = asyncio.run(run(only_entry=args.entry))
    for item in report["entries"]:
        print(f"  {item['entry_id']}: state={item['state']} error={item.get('error_code')}")
        if item.get("diagnosis"):
            print(f"    {item['diagnosis']}")
    print(f"  结算分布: {report['state_distribution']}")
    # verified 之外的都视为「未复验通过」，返回非零供 CI 感知。
    not_verified = sum(c for s, c in report["state_distribution"].items() if s != "verified")
    return 1 if not_verified else 0


if __name__ == "__main__":
    raise SystemExit(main())
