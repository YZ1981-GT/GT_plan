"""行名对齐映射存储层 `RowNameMappingService` 守卫。

覆盖 Requirement 3.2~3.6 / 1.4：
- 作用域键读写、目标身份明细可查询
- 批量确认单事务全回滚（任一行冲突 → 无任何写入）
- 幂等重试（重复 idempotency_key 不重复写）
- 版本冲突检测（base_mapping_version 不匹配 → MappingConflictError）
- 覆盖历史写新版本 + supersede 旧行留痕
- dataset_fingerprint 随目标身份集/dataset 变化

spec: .kiro/specs/formula-row-name-alignment-confirmation/
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.base import Base  # noqa: E402
# 🔴 必须 import 模型模块，create_all 才会建表
import app.models.workpaper_row_name_mapping_models  # noqa: E402, F401
from app.models.workpaper_row_name_mapping_models import (  # noqa: E402
    WorkpaperRowNameMapping,
    WorkpaperRowNameMappingTarget,
)
from app.services.four_table.row_name_alignment import (  # noqa: E402
    SOURCE_AUX,
    TargetIdentity,
)
from app.services.row_name_mapping_service import (  # noqa: E402
    MappingConflictError,
    MappingScope,
    RowConfirmInput,
    RowNameMappingService,
    compute_dataset_fingerprint,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

_PID = uuid.uuid4()
_DS = str(uuid.uuid4())


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _scope() -> MappingScope:
    return MappingScope(project_id=_PID, year=2025, wp_code="K1-1", sheet_code="K1-1")


def _target(name: str, code: str = "1221", aux_type: str = "客户") -> TargetIdentity:
    from app.services.four_table.row_name_alignment import _dimension_key

    return TargetIdentity(
        source_kind=SOURCE_AUX,
        account_code=code,
        aux_type=aux_type,
        aux_name=name,
        dimension_key=_dimension_key(code, aux_type, name),
        dataset_id=_DS,
    )


async def _count_rows(db) -> int:
    return (await db.execute(sa.select(sa.func.count()).select_from(
        WorkpaperRowNameMapping))).scalar() or 0


async def _count_targets(db) -> int:
    return (await db.execute(sa.select(sa.func.count()).select_from(
        WorkpaperRowNameMappingTarget))).scalar() or 0


# ── 基础读写 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_confirm_then_load_roundtrip(db_session):
    svc = RowNameMappingService(db_session)
    t = _target("应收甲单位")
    await svc.batch_confirm(
        _scope(),
        [RowConfirmInput(row_key="r1", targets=[t], base_mapping_version=None)],
        confirmed_by=None,
        idempotency_key=str(uuid.uuid4()),
        dataset_id=_DS,
    )
    await db_session.commit()

    loaded = await svc.load_active_mappings(_scope())
    assert "r1" in loaded
    assert loaded["r1"].mapping_version == 1
    assert len(loaded["r1"].targets) == 1
    assert loaded["r1"].targets[0].aux_name == "应收甲单位"
    # 目标身份明细可 SQL 查询
    assert await _count_targets(db_session) == 1


# ── 幂等 ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_idempotent_repeat_does_not_double_write(db_session):
    svc = RowNameMappingService(db_session)
    key = str(uuid.uuid4())
    inp = [RowConfirmInput(row_key="r1", targets=[_target("单位A")], base_mapping_version=None)]
    await svc.batch_confirm(_scope(), inp, confirmed_by=None, idempotency_key=key, dataset_id=_DS)
    await db_session.commit()
    n1 = await _count_rows(db_session)

    # 同 key 重复请求 → 幂等短路，不再写
    await svc.batch_confirm(_scope(), inp, confirmed_by=None, idempotency_key=key, dataset_id=_DS)
    await db_session.commit()
    n2 = await _count_rows(db_session)
    assert n1 == n2 == 1


# ── 版本冲突 + 全回滚 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_version_conflict_raises_and_rolls_back_all(db_session):
    svc = RowNameMappingService(db_session)
    # 先建 r1 v1
    await svc.batch_confirm(
        _scope(),
        [RowConfirmInput(row_key="r1", targets=[_target("单位A")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await db_session.commit()
    rows_before = await _count_rows(db_session)

    # 批量：r2 全新 + r1 用错误 base_version（当前是 1，传 0）→ 冲突
    with pytest.raises(MappingConflictError):
        await svc.batch_confirm(
            _scope(),
            [
                RowConfirmInput(row_key="r2", targets=[_target("单位B", code="1231")], base_mapping_version=None),
                RowConfirmInput(row_key="r1", targets=[_target("单位A2")], base_mapping_version=0),
            ],
            confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
        )
    await db_session.rollback()

    # 全回滚：r2 不得写入（校验在写之前完成，冲突即抛，无部分写）
    assert await _count_rows(db_session) == rows_before
    loaded = await svc.load_active_mappings(_scope())
    assert "r2" not in loaded


@pytest.mark.asyncio
async def test_empty_targets_rejected_and_rolls_back(db_session):
    svc = RowNameMappingService(db_session)
    with pytest.raises(ValueError):
        await svc.batch_confirm(
            _scope(),
            [RowConfirmInput(row_key="r1", targets=[], base_mapping_version=None)],
            confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
        )
    await db_session.rollback()
    assert await _count_rows(db_session) == 0


# ── 覆盖历史：写新版本 + supersede 留痕 ───────────────────────────────────


@pytest.mark.asyncio
async def test_override_writes_new_version_and_supersedes_old(db_session):
    svc = RowNameMappingService(db_session)
    scope = _scope()
    # v1
    await svc.batch_confirm(
        scope,
        [RowConfirmInput(row_key="r1", targets=[_target("旧单位")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await db_session.commit()
    # v2 覆盖（base=1）
    await svc.batch_confirm(
        scope,
        [RowConfirmInput(row_key="r1", targets=[_target("新单位")], base_mapping_version=1)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await db_session.commit()

    # active 是 v2
    loaded = await svc.load_active_mappings(scope)
    assert loaded["r1"].mapping_version == 2
    assert loaded["r1"].targets[0].aux_name == "新单位"

    # 两个物理行都在（v1 留痕，is_active=false 且被 v2 superseded_from 指向）
    all_rows = (await db_session.execute(
        sa.select(WorkpaperRowNameMapping).where(
            WorkpaperRowNameMapping.row_key == "r1"
        )
    )).scalars().all()
    assert len(all_rows) == 2
    v1 = next(r for r in all_rows if r.mapping_version == 1)
    v2 = next(r for r in all_rows if r.mapping_version == 2)
    assert v1.is_active is False
    assert v2.is_active is True
    assert v2.superseded_from == v1.id


# ── dataset_fingerprint stale 判据 ────────────────────────────────────────


def test_fingerprint_changes_with_targets():
    t1 = _target("单位A")
    t2 = _target("单位B", code="1231")
    fp_a = compute_dataset_fingerprint(_DS, [t1])
    fp_ab = compute_dataset_fingerprint(_DS, [t1, t2])
    assert fp_a != fp_ab


def test_fingerprint_changes_with_dataset():
    t1 = _target("单位A")
    fp1 = compute_dataset_fingerprint("ds-1", [t1])
    fp2 = compute_dataset_fingerprint("ds-2", [t1])
    assert fp1 != fp2


# ── 跨作用域隔离（作用域键必须完整：漏 wp_code / year 会串）──────────────────


@pytest.mark.asyncio
async def test_scope_isolation_wp_code(db_session):
    """不同 wp_code 同 sheet_code 的映射不得互相串（漏 wp_code 键会串 → 变异必红）。"""
    svc = RowNameMappingService(db_session)
    scope_a = MappingScope(project_id=_PID, year=2025, wp_code="K1-1", sheet_code="S")
    scope_b = MappingScope(project_id=_PID, year=2025, wp_code="D3-1", sheet_code="S")
    # 🔴 用不同 row_key：漏 wp_code 会把 scope_b 的行也捞进来 → len 变大（同 key 会被 dict 覆盖掩盖，故必须异 key）
    await svc.batch_confirm(
        scope_a, [RowConfirmInput(row_key="k1_row", targets=[_target("单位A")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await svc.batch_confirm(
        scope_b, [RowConfirmInput(row_key="d3_row", targets=[_target("单位B", code="1231")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await db_session.commit()

    loaded_a = await svc.load_active_mappings(scope_a)
    # 只拿到 K1-1 的 k1_row；漏 wp_code 会串进 d3_row → 断言打红
    assert set(loaded_a.keys()) == {"k1_row"}
    assert loaded_a["k1_row"].targets[0].aux_name == "单位A"


@pytest.mark.asyncio
async def test_scope_isolation_year(db_session):
    """不同 year 的映射不得互相串（漏 year 键会串 → 变异必红）。"""
    svc = RowNameMappingService(db_session)
    scope_25 = MappingScope(project_id=_PID, year=2025, wp_code="K1-1", sheet_code="S")
    scope_24 = MappingScope(project_id=_PID, year=2024, wp_code="K1-1", sheet_code="S")
    await svc.batch_confirm(
        scope_25, [RowConfirmInput(row_key="y25_row", targets=[_target("本年单位")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await svc.batch_confirm(
        scope_24, [RowConfirmInput(row_key="y24_row", targets=[_target("上年单位", code="1231")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await db_session.commit()

    loaded_25 = await svc.load_active_mappings(scope_25)
    assert set(loaded_25.keys()) == {"y25_row"}
    assert loaded_25["y25_row"].targets[0].aux_name == "本年单位"


@pytest.mark.asyncio
async def test_confirm_baseline_isolated_by_year(db_session):
    """batch_confirm 查基线（_load_active_rows）必须按 year 隔离：同 row_key 不同 year 首次确认
    都应是 v1（base=None 通过）。漏 year 会把上年 active 当本年基线 → base=None 冲突/版本错乱 → 打红。"""
    svc = RowNameMappingService(db_session)
    scope_25 = MappingScope(project_id=_PID, year=2025, wp_code="K1-1", sheet_code="S")
    scope_24 = MappingScope(project_id=_PID, year=2024, wp_code="K1-1", sheet_code="S")
    # 2025 先写 v1（同 row_key）
    r25 = await svc.batch_confirm(
        scope_25, [RowConfirmInput(row_key="r1", targets=[_target("本年")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await db_session.commit()
    assert r25["r1"].mapping_version == 1
    # 2024 首次确认同 row_key（base=None）—— 漏 year 会查到 2025 active 当基线 → 冲突或 v2
    r24 = await svc.batch_confirm(
        scope_24, [RowConfirmInput(row_key="r1", targets=[_target("上年", code="1231")], base_mapping_version=None)],
        confirmed_by=None, idempotency_key=str(uuid.uuid4()), dataset_id=_DS,
    )
    await db_session.commit()
    # year 隔离正确时：2024 的 r1 是全新的 v1，不受 2025 影响
    assert r24["r1"].mapping_version == 1
    assert r24["r1"].targets[0].aux_name == "上年"


def test_fingerprint_stable_for_same_input():
    t1 = _target("单位A")
    t2 = _target("单位B", code="1231")
    # 顺序无关（内部排序）
    assert compute_dataset_fingerprint(_DS, [t1, t2]) == compute_dataset_fingerprint(_DS, [t2, t1])
