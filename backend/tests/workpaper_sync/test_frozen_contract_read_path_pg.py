"""Property 1（真库）：对**每一个** approved bundle，读回的契约 digest 必须等于 slot digest。

spec frozen-contract-read-path · Requirements 1.1~1.4 · Property 1

🔴 分母纪律（勘误 E.4）：
* `state='approved'` 的 bundle 里有一类是 **typed null marker**
  （`contract_slot_type='contract:none:v1'`，`contract_slot_ref='marker:...'`）——
  它们**本来就没有** per-entry contract。分母必须先按 `slot.is_definition` 分流，
  否则这 2 条会被误报成「数据缺失」。
* 分母**不许**只挑一个 bundle。本 spec 的整个意义就是「每一个历史 bundle 都能读回」。

🔴 变异纪律（R4.2）：把读路径改回「按 registry 当前 alias 取」⇒ 本判据必须红，
且红的形态必须是「取到了**新**契约」（`canonical_sha256` 变成当前 registry 的 digest），
不是别的失败。

真库依赖：`DATABASE_URL` 指向 PostgreSQL；未设时按 sqlite 判库会 skip（pg_only 语义）。
"""

from __future__ import annotations

import os

import pytest


def _is_pg() -> bool:
    url = os.environ.get("DATABASE_URL") or ""
    return url.startswith("postgresql")


pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.skipif(
        not _is_pg(),
        reason=(
            "需要真实 PostgreSQL（本判据读共享库里的 approved bundle 全集）；"
            "未设 DATABASE_URL 或指向 sqlite 时 skip —— 不是「已通过」"
        ),
    ),
]


@pytest.fixture(scope="module")
def approved_bundles() -> list[dict]:
    """现读全部 approved bundle 的 typed slot（**分母**）。"""
    import asyncio

    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import settings

    url = os.environ.get("DATABASE_URL") or str(settings.DATABASE_URL)

    async def _load() -> list[dict]:
        engine = create_async_engine(url, future=True)
        try:
            async with engine.connect() as conn:
                rows = (
                    await conn.execute(
                        sa.text(
                            "SELECT id, contract_slot_type, contract_slot_ref, "
                            "contract_slot_digest FROM "
                            "public.working_paper_sync_definition_bundle "
                            "WHERE state = 'approved' ORDER BY created_at"
                        )
                    )
                ).mappings().all()
                return [dict(r) for r in rows]
        finally:
            await engine.dispose()

    return asyncio.run(_load())


def _split(bundles: list[dict]) -> tuple[list[dict], list[dict]]:
    """按 `slot.is_definition` 分流：definition child 与 typed null marker。"""
    definitions = [b for b in bundles if b["contract_slot_type"] == "definition"]
    markers = [b for b in bundles if b["contract_slot_type"] != "definition"]
    return definitions, markers


class TestDenominatorIsNotSilentlyEmpty:
    def test_approved_bundles_exist(self, approved_bundles: list[dict]) -> None:
        assert approved_bundles, (
            "共享库里一个 approved bundle 都没有 —— 本判据无分母。"
            "空分母会让「Property 1 全绿」变成恒真"
        )

    def test_definition_slot_denominator_is_not_empty(
        self, approved_bundles: list[dict]
    ) -> None:
        definitions, _ = _split(approved_bundles)
        assert definitions, "没有一个 contract_slot_type='definition' 的 bundle ⇒ 无分母"

    def test_marker_bundles_are_counted_separately(
        self, approved_bundles: list[dict]
    ) -> None:
        """typed null marker 必须被**分流**，不是被当成读取失败。"""
        definitions, markers = _split(approved_bundles)
        assert len(definitions) + len(markers) == len(approved_bundles)
        for m in markers:
            assert str(m["contract_slot_ref"]).startswith("marker:"), (
                f"非 definition 的 slot_ref 必须以 marker: 开头，实得 {m['contract_slot_ref']!r}"
            )


#: 🔴 已知磁盘缺失的 contract blob（棘轮：**只许减少**）。
#:
#: 现算（2026-11-15，共享库只读）：263 个 approved definition-slot bundle 中
#: **254 个磁盘文件在位 / 9 个缺失**。这 9 个是**平台级历史数据缺口**，与本 spec 的
#: 读路径能力无关（`FrozenContractReader` 对它们如实报 `frozen_contract_blob_unreadable`，
#: 这正是 R1.3 要求的「文件缺失」可辨性）。
#:
#: 🔴 为什么登记而不是修：补齐这 9 个文件需要从别处重建内容寻址产物（其中
#: `661bb271…` 是 D2 应收账款**当前生效**的契约）—— 那是数据修复动作，必须单独走
#: 「备份 → 重建 → 逐项对账」的流程，不能混在读侧 spec 里顺手做。
#:
#: 棘轮纪律：**只许变短**。任何人补齐其中一个，就必须同步删掉这里的对应行；
#: 反之出现新缺失（集合变大）即红 —— 那说明有写入方在删 blob。
_KNOWN_MISSING_CONTRACT_BLOBS: frozenset[str] = frozenset(
    {
        "413e2dce9bb1255ca4304f00a3fd6c5b30a92479a4efed24d500b7f02a23d020",
        "e7b7fdd73be32631005963baf6de19907f21c0c14ca1b5905437c03a2e93524f",
        "c0a8f1c9451b6cd5b4801244966c7cdb5162fa2a6196a0a3f012869457f13ce7",
        "b362ae8bc00eb28056d2d219f32a643285bd25ff75de6badd3b6713d0d0246e4",
        "33f9c65390b511722b01b2fca5ca27284f3585bd93a44e7ce822e809834a8f38",
        "843e9880c32c1320c959a9425bfbfa7cf47d609414a68ab08a7d9b6e9d7471f9",
        "6507ff4c43067b3e4ecdace640f616903e1e3d2a0af2ad03705e05e2061e03ed",
        "f8f7f8e5d85ed31c094cd09271db4b81d12dd7cded2548769019fa2f6cca7e1a",
        "661bb271b4f574fa3d56849e6ccdcea0aaebf79e0f34b5a5dc0c77a5fd43e979",
    }
)


class TestProperty1EveryApprovedBundleReadsBackItsFrozenContract:
    """**Property 1**：任意 bundle 的 `contract_slot_ref` 读回后 digest 必须等于 slot digest。

    🔴 分母 = 库里 approved bundle **全集**，不是挑一个（勘误 E.4）。
    已知磁盘缺失的 9 个走独立判据（棘轮），不混进本类的「全绿」里。
    """

    def test_every_readable_definition_bundle_reads_back_exactly(
        self, approved_bundles: list[dict]
    ) -> None:
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import settings
        from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
        from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
        from app.services.workpaper_sync.frozen_contract_reader import (
            FrozenContractBlobUnreadableError,
            FrozenContractReader,
        )
        from app.services.workpaper_sync.resolution import CanonicalResolutionService

        definitions, _ = _split(approved_bundles)
        assert definitions, "无分母"

        url = os.environ.get("DATABASE_URL") or str(settings.DATABASE_URL)

        async def _run() -> tuple[list[str], list[str], int]:
            engine = create_async_engine(url, future=True)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            problems: list[str] = []
            known_missing: list[str] = []
            checked = 0
            try:
                async with Session() as session:
                    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
                    resolution = CanonicalResolutionService(
                        session=session, artifacts=artifacts
                    )
                    reader = FrozenContractReader(session=session, artifacts=artifacts)
                    for row in definitions:
                        bundle_id = row["id"]
                        digest = str(row["contract_slot_digest"]).strip()
                        try:
                            bundle = await resolution.load_bundle_snapshot(bundle_id)
                        except Exception as exc:  # noqa: BLE001
                            problems.append(
                                f"{bundle_id}: load_bundle_snapshot 失败 "
                                f"{type(exc).__name__}: {exc}"
                            )
                            continue
                        try:
                            snap = await reader.read(bundle=bundle)
                        except FrozenContractBlobUnreadableError:
                            known_missing.append(digest)
                            continue
                        except Exception as exc:  # noqa: BLE001
                            problems.append(
                                f"{bundle_id}: reader 失败 {type(exc).__name__}: {exc}"
                            )
                            continue
                        checked += 1
                        if snap.contract.canonical_sha256.strip() != digest:
                            problems.append(
                                f"{bundle_id}: canonical_sha256 "
                                f"{snap.contract.canonical_sha256!r} != slot digest {digest!r}"
                            )
            finally:
                await engine.dispose()
            return problems, known_missing, checked

        problems, known_missing, checked = asyncio.run(_run())
        assert problems == [], (
            f"{len(problems)} 个 approved bundle 读回的契约与冻结 slot digest 不一致"
            f"（或读取方式出错）：\n" + "\n".join(f"  - {p}" for p in problems[:10])
        )
        # 分母非空：真的读回了足够多的契约（防止「全部走 known_missing 分支」的恒真）
        assert checked >= 200, (
            f"只成功读回 {checked} 个契约（分母 {len(definitions)}）—— "
            "过多走 known_missing 分支会让本判据接近恒真"
        )
        # 缺失集合必须恰好等于棘轮登记（不多不少）
        actual_missing = set(known_missing)
        assert actual_missing == _KNOWN_MISSING_CONTRACT_BLOBS, (
            "磁盘缺失的 contract blob 集合与棘轮登记不一致：\n"
            f"  新增缺失（有写入方在删 blob？）: "
            f"{sorted(actual_missing - _KNOWN_MISSING_CONTRACT_BLOBS)}\n"
            f"  已补齐（请同步删掉棘轮里的行）: "
            f"{sorted(_KNOWN_MISSING_CONTRACT_BLOBS - actual_missing)}"
        )

    def test_marker_bundles_are_refused_with_typed_error(
        self, approved_bundles: list[dict]
    ) -> None:
        """typed null marker 必须给出**可辨的拒绝**，不是崩溃也不是空契约。"""
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.config import settings
        from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
        from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
        from app.services.workpaper_sync.frozen_contract_reader import (
            FrozenContractReader,
            FrozenContractSlotNotDefinitionError,
        )
        from app.services.workpaper_sync.resolution import CanonicalResolutionService

        _, markers = _split(approved_bundles)
        if not markers:
            pytest.skip("共享库里没有 typed null marker bundle —— 该分支无分母")

        url = os.environ.get("DATABASE_URL") or str(settings.DATABASE_URL)

        async def _run() -> None:
            engine = create_async_engine(url, future=True)
            Session = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with Session() as session:
                    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
                    resolution = CanonicalResolutionService(
                        session=session, artifacts=artifacts
                    )
                    reader = FrozenContractReader(session=session, artifacts=artifacts)
                    for row in markers:
                        bundle = await resolution.load_bundle_snapshot(row["id"])
                        with pytest.raises(FrozenContractSlotNotDefinitionError):
                            await reader.read(bundle=bundle)
            finally:
                await engine.dispose()

        asyncio.run(_run())


class TestProperty1IsFalsifiable:
    """**变异证明**（R4.2）：把读路径改回 registry 当前 alias ⇒ 判据必须红。

    红在**这一条**：`test_every_definition_bundle_reads_back_exactly`。
    形态要求：报出的差异必须是「canonical_sha256 与 slot digest 不一致」，
    而不是「load_bundle_snapshot 失败」之类的别的原因 —— 否则变异证明不成立。
    """

    def test_current_registry_digest_differs_from_at_least_one_frozen_slot(
        self, approved_bundles: list[dict]
    ) -> None:
        """变异能成立的**前提**：库里确实存在「冻结 slot ≠ 当前 registry」的 bundle。

        若所有 bundle 的 slot digest 都等于当前 registry，那「按 registry 取」这个变异
        是**等价**的（不会红）—— 判据就会假绿。本测试把这个前提钉住。
        """
        from pathlib import Path

        from app.services.workpaper_sync.contracts import canonical_digest

        contracts_dir = Path(__file__).resolve().parents[2] / "data" / "workpaper_sync_contracts"
        assert contracts_dir.is_dir(), f"契约目录不存在: {contracts_dir}"
        registry_digests = {
            canonical_digest(__import__("json").loads(p.read_text(encoding="utf-8")))
            for p in contracts_dir.glob("*.json")
            if not p.name.startswith("_example")
        }
        assert registry_digests, "registry 目录里没有契约 ⇒ 变异前提无法验证"

        definitions, _ = _split(approved_bundles)
        frozen = {str(b["contract_slot_digest"]).strip() for b in definitions}
        stale = frozen - registry_digests
        assert stale, (
            "所有 frozen slot digest 都在当前 registry 里 ⇒ 「按 registry 现取」这个变异是"
            "等价变异（永远不会红），Property 1 的变异证明不成立。"
            f"frozen={len(frozen)} registry={len(registry_digests)}"
        )
        # 至少要有 2 个（本 spec 的对象就是这种历史 bundle）
        assert len(stale) >= 2, (
            f"只有 {len(stale)} 个 frozen digest 不在 registry 里 —— 样本过少，"
            "不足以支撑「历史 operation 读旧契约」这条能力的验收"
        )
