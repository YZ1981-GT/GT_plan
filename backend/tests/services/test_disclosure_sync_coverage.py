"""披露同步覆盖率只读查询 — 口径对账守卫

spec: disclosure-payload-authority-source / Task 2.2 / Q6 Q7

两层覆盖：
  A. 注册表展开逻辑（纯函数，无 DB）
  B. 🔴 真实落库对账（真 ORM 行 + 真 session + 真调 service），
     与直接 SQL 统计逐值相等（Q6）· 未启用底稿不计入分母（Q7）

修复记录：首版本文件 6 个测试**全是纯函数结构检查、零 DB 访问**，
主函数 `get_project_disclosure_sync_coverage` 从未被调用过一次 ⇒ Q6/Q7 实质未覆盖。
本版补齐 B 层（复盘 P0-1）。
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import ContentType, DisclosureNote, NoteStatus
from app.models.workpaper_models import WpIndex, WpStatus
from app.services.disclosure_sync_coverage_service import (
    _build_expectations,
    _load_registry,
    get_project_disclosure_sync_coverage,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

_YEAR = 2025


# ══════════════════════════════════════════════════════════════════════════
# A 层：注册表展开逻辑（纯函数）
# ══════════════════════════════════════════════════════════════════════════


def test_build_expectations_covers_registry():
    """注册表展开结果与 JSON entries 一致：每个有 listed/soe 字段的 entry 各展开一行。"""
    _load_registry.cache_clear()
    exps = _build_expectations()
    entries = _load_registry()

    assert len(exps) > 0
    exp_codes = {e["wp_code"] for e in exps}
    entry_codes = {e["wp_code"] for e in entries if e.get("wp_code")}
    assert exp_codes == entry_codes, f"期望值差异: {exp_codes.symmetric_difference(entry_codes)}"


def test_build_expectations_expands_multi_section():
    """多章节映射（listed_sections/soe_sections）正确展开。"""
    exps = _build_expectations()
    g10_listed = [e for e in exps if e["wp_code"] == "G10" and e["variant"] == "listed"]
    assert len(g10_listed) >= 2, f"G10 listed 应至少 2 条（多章节），实际 {len(g10_listed)}"


def test_expectations_variant_balanced():
    """每个 wp_code 的 listed + soe 条数应相等（注册表结构对称）。"""
    exps = _build_expectations()
    counter: dict[str, dict[str, int]] = {}
    for e in exps:
        code = e["wp_code"]
        counter.setdefault(code, {"listed": 0, "soe": 0})
        counter[code][e["variant"]] += 1

    for code, counts in counter.items():
        assert counts["listed"] == counts["soe"] or counts["listed"] == 0 or counts["soe"] == 0, (
            f"{code}: listed={counts['listed']} soe={counts['soe']} 不对称"
        )


def test_registry_path_exists():
    """注册表文件存在（防路径改后测试空转）。"""
    from app.services.disclosure_sync_coverage_service import _REGISTRY_PATH

    assert _REGISTRY_PATH.exists(), f"注册表不存在: {_REGISTRY_PATH}"


def test_registry_no_empty_wp_code():
    """注册表 entries 不含空 wp_code。"""
    _load_registry.cache_clear()
    entries = _load_registry()
    for i, e in enumerate(entries):
        assert e.get("wp_code"), f"entries[{i}] 缺 wp_code: {e}"


def test_mutation_build_expectations_detects_injection():
    """变异证明：往注册表注入一个假 entry 后 expectations 数量增加。"""
    _load_registry.cache_clear()
    original_count = len(_build_expectations())

    fake_entries = list(_load_registry()) + [
        {"wp_code": "ZZZ_TEST", "listed": "五、999", "soe": "八、999"}
    ]

    with patch(
        "app.services.disclosure_sync_coverage_service._load_registry",
        return_value=fake_entries,
    ):
        mutated = _build_expectations()
        assert len(mutated) == original_count + 2  # listed + soe 各一

    _load_registry.cache_clear()


# ══════════════════════════════════════════════════════════════════════════
# B 层：真实落库对账（真 ORM + 真 session + 真调 service）
# ══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def project_id(db: AsyncSession) -> uuid.UUID:
    p = Project(
        id=uuid.uuid4(),
        name="覆盖率测试_2025",
        client_name="覆盖率测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
    )
    db.add(p)
    await db.flush()
    return p.id


def _pick_codes(n: int) -> list[str]:
    """从注册表现算取前 n 个 wp_code（禁写死码，注册表变了测试不碎）。"""
    seen: list[str] = []
    for e in _build_expectations():
        if e["wp_code"] not in seen:
            seen.append(e["wp_code"])
        if len(seen) >= n:
            break
    return seen


def _expectations_of(codes: set[str]) -> list[dict]:
    """这些 wp_code 对应的全部 (variant, note_section) 期望行。"""
    return [e for e in _build_expectations() if e["wp_code"] in codes]


async def _enable_codes(db: AsyncSession, project_id: uuid.UUID, codes: list[str]) -> None:
    for code in codes:
        db.add(WpIndex(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_code=code,
            wp_name=f"{code} 测试底稿",
            status=WpStatus.not_started,
            is_deleted=False,
        ))
    await db.flush()


async def _add_note(
    db: AsyncSession,
    project_id: uuid.UUID,
    note_section: str,
    *,
    synced: bool,
    stale: bool = False,
) -> None:
    db.add(DisclosureNote(
        id=uuid.uuid4(),
        project_id=project_id,
        year=_YEAR,
        note_section=note_section,
        section_title=f"{note_section} 测试章节",
        content_type=ContentType.table,
        status=NoteStatus.draft,
        is_deleted=False,
        is_stale=stale,
        last_sync_at=datetime.now(timezone.utc) if synced else None,
    ))
    await db.flush()


class TestCoverageAgainstRealDb:
    """Q6：service 结果与直接 SQL 统计逐值相等。"""

    @pytest.mark.asyncio
    async def test_denominator_equals_enabled_codes_only(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """🔴 Q7 核心：分母只含项目启用的底稿，不是注册表全集。"""
        enabled = _pick_codes(3)
        await _enable_codes(db, project_id, enabled)

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)

        expected_rows = _expectations_of(set(enabled))
        assert result["expected"] == len(expected_rows), (
            f"分母应等于已启用 {enabled} 的期望行数 {len(expected_rows)}，"
            f"实际 {result['expected']}"
        )
        # 反向：分母必须显著小于注册表全集（否则等于没排除）
        assert result["expected"] < len(_build_expectations()), (
            "分母等于注册表全集 ⇒ 未启用底稿没被排除（Q7 失效）"
        )

    @pytest.mark.asyncio
    async def test_zero_enabled_means_empty_denominator(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """双向变异：一个底稿都没启用 ⇒ 分母为 0（不是注册表全集）。"""
        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        assert result["expected"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_all_enabled_denominator_equals_full_registry(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """双向变异对侧：全部启用 ⇒ 分母等于注册表**去重后**的章节全集。

        🔴 不是 len(_build_expectations())：那是职责行数，含共享章节的重复
        （见 TestSharedSectionNotDoubleCounted）。
        """
        exps = _build_expectations()
        all_codes = list({e["wp_code"] for e in exps})
        await _enable_codes(db, project_id, all_codes)

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        assert result["expected"] == len({e["note_section"] for e in exps})
        assert result["duty_rows"] == len(exps)

    @pytest.mark.asyncio
    async def test_synced_stale_never_match_direct_sql(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """🔴 Q6 核心：synced / stale / never_synced 与直接 SQL 统计逐值相等。"""
        enabled = _pick_codes(3)
        await _enable_codes(db, project_id, enabled)
        rows = _expectations_of(set(enabled))
        assert len(rows) >= 4, "样本太小无法区分三种状态"

        # 造三类状态：已同步未过期 / 已同步且过期 / 存在但从未同步
        await _add_note(db, project_id, rows[0]["note_section"], synced=True, stale=False)
        await _add_note(db, project_id, rows[1]["note_section"], synced=True, stale=True)
        await _add_note(db, project_id, rows[2]["note_section"], synced=False, stale=False)
        # rows[3:] 连 disclosure_notes 行都没有 → 也算 never_synced

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)

        target_sections = [r["note_section"] for r in rows]
        # 直接 SQL：已同步数
        sql_synced = await db.scalar(
            sa.select(sa.func.count()).select_from(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == _YEAR,
                DisclosureNote.note_section.in_(target_sections),
                DisclosureNote.is_deleted == sa.false(),
                DisclosureNote.last_sync_at.is_not(None),
            )
        )
        # 直接 SQL：stale 数
        sql_stale = await db.scalar(
            sa.select(sa.func.count()).select_from(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == _YEAR,
                DisclosureNote.note_section.in_(target_sections),
                DisclosureNote.is_deleted == sa.false(),
                DisclosureNote.is_stale == sa.true(),
            )
        )

        assert result["synced"] == sql_synced, (
            f"service synced={result['synced']} ≠ 直接 SQL {sql_synced}"
        )
        assert result["stale"] == sql_stale, (
            f"service stale={result['stale']} ≠ 直接 SQL {sql_stale}"
        )
        # never_synced = 分母 - 已同步（含「连行都没有」的情况）
        assert result["never_synced"] == result["expected"] - result["synced"]
        assert result["never_synced"] == len(rows) - sql_synced

    @pytest.mark.asyncio
    async def test_soft_deleted_note_not_counted_as_synced(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """软删的附注行不算已同步（口径必须带 is_deleted=false）。"""
        enabled = _pick_codes(1)
        await _enable_codes(db, project_id, enabled)
        rows = _expectations_of(set(enabled))

        db.add(DisclosureNote(
            id=uuid.uuid4(),
            project_id=project_id,
            year=_YEAR,
            note_section=rows[0]["note_section"],
            section_title="软删章节",
            content_type=ContentType.table,
            status=NoteStatus.draft,
            is_deleted=True,          # ← 软删
            is_stale=False,
            last_sync_at=datetime.now(timezone.utc),
        ))
        await db.flush()

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        assert result["synced"] == 0, "软删行被错算成已同步"

    @pytest.mark.asyncio
    async def test_other_year_note_not_counted(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """别的年度的附注行不算本年度已同步（年度隔离）。"""
        enabled = _pick_codes(1)
        await _enable_codes(db, project_id, enabled)
        rows = _expectations_of(set(enabled))

        db.add(DisclosureNote(
            id=uuid.uuid4(),
            project_id=project_id,
            year=_YEAR - 1,           # ← 上一年度
            note_section=rows[0]["note_section"],
            section_title="上年章节",
            content_type=ContentType.table,
            status=NoteStatus.draft,
            is_deleted=False,
            is_stale=False,
            last_sync_at=datetime.now(timezone.utc),
        ))
        await db.flush()

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        assert result["synced"] == 0, "跨年度行被错算进本年度"

    @pytest.mark.asyncio
    async def test_soft_deleted_wp_index_excluded_from_denominator(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """软删的底稿不计入分母（启用判定须带 is_deleted=false）。"""
        code = _pick_codes(1)[0]
        db.add(WpIndex(
            id=uuid.uuid4(),
            project_id=project_id,
            wp_code=code,
            wp_name=f"{code} 已删底稿",
            status=WpStatus.not_started,
            is_deleted=True,          # ← 软删
        ))
        await db.flush()

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        assert result["expected"] == 0, "软删底稿被计入分母"

    @pytest.mark.asyncio
    async def test_other_project_data_isolated(self, db: AsyncSession, project_id: uuid.UUID):
        """另一个项目的启用底稿与附注行不影响本项目统计。"""
        other = Project(
            id=uuid.uuid4(),
            name="干扰项目_2025",
            client_name="干扰",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
        )
        db.add(other)
        await db.flush()

        all_codes = list({e["wp_code"] for e in _build_expectations()})
        await _enable_codes(db, other.id, all_codes)
        rows = _expectations_of(set(all_codes))
        await _add_note(db, other.id, rows[0]["note_section"], synced=True)

        # 本项目啥都没启用
        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        assert result["expected"] == 0, "他项目的底稿串进本项目分母"
        assert result["synced"] == 0

    @pytest.mark.asyncio
    async def test_items_flags_self_consistent(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """每条 item 的 never_synced 恒等于 not synced（口径自洽）。"""
        enabled = _pick_codes(3)
        await _enable_codes(db, project_id, enabled)
        rows = _expectations_of(set(enabled))
        await _add_note(db, project_id, rows[0]["note_section"], synced=True, stale=True)

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        for item in result["items"]:
            assert item["expected"] is True, "items 内不应出现未启用项"
            assert item["never_synced"] == (not item["synced"]), (
                f"{item['wp_code']}/{item['variant']} never_synced 与 synced 不自洽"
            )
        # 汇总数 = items 按 note_section **去重**后的统计（共享章节不可重复计）
        assert result["synced"] == len(
            {i["note_section"] for i in result["items"] if i["synced"]}
        )
        assert result["stale"] == len(
            {i["note_section"] for i in result["items"] if i["stale"]}
        )
        assert result["expected"] == len({i["note_section"] for i in result["items"]})


class TestSharedSectionNotDoubleCounted:
    """🔴 共享章节去重 —— 真库实测抓到的 bug（复盘 P0-1 追加）。

    8 个 note_section 被多个 wp_code 共用（现算，如「五、8」← G2/G3/K1），
    对应的 disclosure_notes **只有一行**。首版实现按职责行计数，
    使同一行被重复计 2~3 次：真库 service synced=17 而直接 SQL=13。
    """

    @staticmethod
    def _shared_sections() -> dict[str, list[str]]:
        """现算被多条 expectation 共用的 section → 其 owner 列表（禁写死）。"""
        by_section: dict[str, list[str]] = {}
        for e in _build_expectations():
            by_section.setdefault(e["note_section"], []).append(
                f"{e['wp_code']}/{e['variant']}"
            )
        return {k: v for k, v in by_section.items() if len(v) > 1}

    def test_shared_sections_exist_in_registry(self):
        """前提成立：注册表里确实存在共享章节（否则本组测试空转）。"""
        shared = self._shared_sections()
        assert shared, (
            "注册表无共享章节 ⇒ 本组去重测试失去意义。"
            "若注册表结构变更导致共享消失，应删除本组而非留空转。"
        )

    def test_duty_rows_exceeds_distinct_sections(self):
        """职责行数 > 去重章节数，差值 = 共享带来的额外计数。"""
        exps = _build_expectations()
        distinct = len({e["note_section"] for e in exps})
        shared = self._shared_sections()
        extra = sum(len(v) - 1 for v in shared.values())
        assert len(exps) - distinct == extra, (
            f"职责行 {len(exps)} - 去重 {distinct} 应等于共享额外计数 {extra}"
        )

    @pytest.mark.asyncio
    async def test_shared_section_counted_once(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """一个共享章节同步一次 ⇒ synced 只加 1，不是加 owner 个数。"""
        shared = self._shared_sections()
        section, owners = next(iter(shared.items()))
        owner_codes = [o.split("/")[0] for o in owners]
        assert len(owner_codes) >= 2

        await _enable_codes(db, project_id, owner_codes)
        await _add_note(db, project_id, section, synced=True, stale=True)

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)

        # 这一个附注行只能算 1 次
        matching_items = [i for i in result["items"] if i["note_section"] == section]
        assert len(matching_items) == len(owners), "items 应保留每条职责行"
        assert result["synced"] == 1, (
            f"共享章节 {section} 有 {len(owners)} 个 owner，"
            f"但只有 1 个附注行 ⇒ synced 必须是 1，实际 {result['synced']}"
        )
        assert result["stale"] == 1, f"stale 同理必须是 1，实际 {result['stale']}"

    @pytest.mark.asyncio
    async def test_expected_is_distinct_sections_not_duty_rows(
        self, db: AsyncSession, project_id: uuid.UUID
    ):
        """全启用时 expected = 去重章节数，duty_rows = 职责行数，两者不等。"""
        all_codes = list({e["wp_code"] for e in _build_expectations()})
        await _enable_codes(db, project_id, all_codes)

        result = await get_project_disclosure_sync_coverage(db, project_id, _YEAR)
        exps = _build_expectations()
        assert result["expected"] == len({e["note_section"] for e in exps})
        assert result["duty_rows"] == len(exps)
        assert result["duty_rows"] > result["expected"], (
            "存在共享章节时 duty_rows 必须大于 expected（否则去重没生效）"
        )

    @pytest.mark.asyncio
    async def test_service_is_read_only(self, db: AsyncSession, project_id: uuid.UUID):
        """Q：查询只读 —— 调用前后 disclosure_notes 与 wp_index 行数不变。"""
        enabled = _pick_codes(2)
        await _enable_codes(db, project_id, enabled)
        rows = _expectations_of(set(enabled))
        await _add_note(db, project_id, rows[0]["note_section"], synced=True)

        before_notes = await db.scalar(sa.select(sa.func.count()).select_from(DisclosureNote))
        before_wp = await db.scalar(sa.select(sa.func.count()).select_from(WpIndex))

        await get_project_disclosure_sync_coverage(db, project_id, _YEAR)

        after_notes = await db.scalar(sa.select(sa.func.count()).select_from(DisclosureNote))
        after_wp = await db.scalar(sa.select(sa.func.count()).select_from(WpIndex))
        assert (before_notes, before_wp) == (after_notes, after_wp), "只读查询产生了写入"
