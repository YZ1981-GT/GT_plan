"""Task 3.1 · 右栏服务端按 `project_id & wp_id & sheet_uid` 精确过滤
（spec formula-manager-closure · ADR-FMC-01 / §5 步骤 3 · 需求 6.2、1.1 服务端口径）。

两层验收：
  1) 集成（TestClient + 真 ORM + 真 SQLite）：`GET /api/workpapers/{wp_id}/formulas?sheet_uid=E1-1`
     只返精确当前 sheet 的行；复刻报告反例 `E1-1` vs `E1-10/E1-14`、`D2-1` vs `D2-10` 不串页；
     省略 `sheet_uid` = 整册视图（返回全部，向后兼容）；返回行均带同一 location identity
     （`project_id`/`wp_id`/`stable_sheet_key`）。
  2) 单元 + 变异反证：直接测服务端过滤真源 `filter_items_by_sheet_uid`。
     变异 = 把服务端过滤放宽为**前缀/子串匹配**，`E1-1` 会串入 `E1-10/E1-14` ⇒ 精确断言打红；
     反向断言 = 精确过滤**不**误红（恰好只保留 `E1-1`）。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpFormula,
    WpIndex,
    WpSourceType,
)
from app.services.formula_management.sheet_identity_filter import (
    filter_items_by_sheet_uid,
    row_matches_sheet_uid,
)
from app.services.formula_management.stable_key import derive_stable_key

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
FAKE_WP_INDEX_ID = uuid.uuid4()
FAKE_WP_ID = uuid.uuid4()
WP_CODE = "E1"
YEAR = 2025

# 报告反例（§1 #1 实测）：这些 sheet 名下各落一条公式行，用于验证 `E1-1` 不串入
# `E1-10/E1-14`、`D2-1` 不串入 `D2-10`。sheet 展示名把结构化编码放在**末尾**（与前端
# `extractSheetCodeFromName` 的末尾 token 口径一致，也是真实底稿命名形态），这样旧 includes
# 子串口径会把 `E1-1` 串入 `E1-10/E1-14`（变异反证才成立）。
_SEED_SHEETS: list[tuple[str, str]] = [
    ("审定表E1-1", "B5"),            # 当前页
    ("银行账户核对表E1-10", "C7"),   # 旧 includes 会被 E1-1 串入
    ("货币资金分析表E1-14", "D9"),   # 旧 includes 会被 E1-1 串入
    ("审定表D2-1", "B3"),            # 另一循环当前页
    ("坏账准备明细D2-10", "B4"),     # 旧 includes 会被 D2-1 串入
]


_TABLES = [
    User.__table__,
    Project.__table__,
    WpIndex.__table__,
    WorkingPaper.__table__,
    WpFormula.__table__,
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sc: Base.metadata.drop_all(sc, tables=_TABLES)
        )
        await conn.run_sync(
            lambda sc: Base.metadata.create_all(sc, tables=_TABLES)
        )
    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    db_session.add(
        User(
            id=FAKE_USER_ID,
            username="suid_user",
            email="suid@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )
    )
    await db_session.flush()
    db_session.add(
        Project(
            id=FAKE_PROJECT_ID,
            name="sheet_uid 过滤测试",
            client_name="客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.planning,
            created_by=FAKE_USER_ID,
            audit_period_end=date(2025, 12, 31),
            template_type="soe",
        )
    )
    await db_session.flush()
    db_session.add(
        WpIndex(
            id=FAKE_WP_INDEX_ID,
            project_id=FAKE_PROJECT_ID,
            wp_code=WP_CODE,
            wp_name="货币资金",
            audit_cycle="E",
        )
    )
    await db_session.flush()
    db_session.add(
        WorkingPaper(
            id=FAKE_WP_ID,
            project_id=FAKE_PROJECT_ID,
            wp_index_id=FAKE_WP_INDEX_ID,
            file_path="storage/x/E1.xlsx",
            source_type=WpSourceType.manual,
            status=WpFileStatus.draft,
            parsed_data={},
            created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        )
    )
    await db_session.flush()
    # 逐 sheet 落一条公式行，带回填 stable_sheet_key（复用单一真源 derive_stable_key）。
    for sheet_name, cell in _SEED_SHEETS:
        sk = derive_stable_key(sheet_name, cell)
        db_session.add(
            WpFormula(
                id=uuid.uuid4(),
                project_id=FAKE_PROJECT_ID,
                wp_id=FAKE_WP_ID,
                sheet_name=sheet_name,
                target_cell=cell,
                expression="1",
                formula_type="auto_calc",
                refs=[],
                stable_sheet_key=sk.stable_sheet_key,
                row_key=sk.row_key,
                field_key=sk.field_key,
                stable_key_needs_review=sk.needs_review,
            )
        )
    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID, "wp_id": FAKE_WP_ID}


# ─────────────────────────────────────────────────────────────────────────────
# 集成：服务端三键精确过滤（router 函数级 + 真 ORM 行 + 真 service list_by_wp + 真 SQLite）
#
# 直接调 `wp_formula.list_formulas` 协程（与 d_cycle_extraction 既有 router-level 集成测试
# 同款），而非走 TestClient：TestClient 路径会被 `wp_visibility` dedicated-subroute 访问门
# 在本测试环境判 not_delegated 返 404（既有 `test_custom_wp_formula_full_chain.py` 同样被
# 此门挡住，与本任务无关），router 函数级能真实覆盖「真 ORM 落多类 sheet 行 → list_by_wp →
# 服务端精确过滤」的端到端路径且不受该门干扰。
# ─────────────────────────────────────────────────────────────────────────────

from app.routers import wp_formula as _router_mod  # noqa: E402


class _User:
    id = FAKE_USER_ID
    username = "suid_user"
    # formula-manager-closure Task 5.2 / ADR-FMC-06：list_formulas 现经
    # `_authorize_wp_project` → `assert_project_permission` 做项目级鉴权（readonly）。
    # 本测试聚焦 sheet_uid 服务端精确过滤口径，用 admin 桩走 admin-bypass 分支（不改变
    # 过滤逻辑，仅让鉴权放行）；admin bypass 只 set_rls_context（SQLite 为 no-op）。
    # 跨项目越权的 403 正面 + 变异反证由 test_fm_p0_05_cross_project_idor 专测覆盖。
    role = UserRole.admin


@pytest.mark.asyncio
async def test_server_filters_to_exact_current_sheet(db_session, seeded):
    """给 sheet_uid=E1-1：服务端只返精确 E1-1 的行，不串入 E1-10/E1-14。"""
    project_id = seeded["project_id"]
    wp_id = seeded["wp_id"]
    body = await _router_mod.list_formulas(
        wp_id, project_id=project_id, sheet_uid="E1-1", db=db_session, user=_User()
    )
    items = body["items"]
    # 恰一行（E1-1 当前页），不串入 E1-10/E1-14
    assert body["count"] == 1
    assert len(items) == 1
    assert items[0]["stable_sheet_key"] == "审定表E1-1"
    assert items[0]["target_cell"] == "B5"
    # 返回行均带同一 location identity（project_id/wp_id），且 sheet_uid 回显
    assert body["project_id"] == str(project_id)
    assert body["wp_id"] == str(wp_id)
    assert body["sheet_uid"] == "E1-1"
    assert items[0]["project_id"] == str(project_id)
    assert items[0]["wp_id"] == str(wp_id)


@pytest.mark.asyncio
async def test_server_filters_d2_does_not_cross_into_d2_10(db_session, seeded):
    """给 sheet_uid=D2-1：只返 D2-1，不串入 D2-10（另一循环同款反例）。"""
    wp_id = seeded["wp_id"]
    body = await _router_mod.list_formulas(
        wp_id, project_id=None, sheet_uid="D2-1", db=db_session, user=_User()
    )
    assert body["count"] == 1
    assert body["items"][0]["stable_sheet_key"] == "审定表D2-1"
    assert body["items"][0]["target_cell"] == "B3"


@pytest.mark.asyncio
async def test_omitting_sheet_uid_returns_whole_workbook(db_session, seeded):
    """省略 sheet_uid = 整册视图（返回全部 5 行，向后兼容）。"""
    wp_id = seeded["wp_id"]
    body = await _router_mod.list_formulas(
        wp_id, project_id=None, sheet_uid=None, db=db_session, user=_User()
    )
    assert body["count"] == len(_SEED_SHEETS)
    assert body["sheet_uid"] is None


@pytest.mark.asyncio
async def test_sheet_uid_with_order_prefix_and_fullwidth_space(db_session, seeded):
    """sheet_uid 传带前导排序前缀 + 全角空格的展示名，仍精确命中（单一真源归一同口径）。"""
    wp_id = seeded["wp_id"]
    # 行 stable_sheet_key = "审定表E1-1"；sheet_uid 传带中文序号前缀 + 全角空格的展示名，
    # 归一后同为 "审定表E1-1"（维度 1 stable_sheet_key 精确等值命中）。
    body = await _router_mod.list_formulas(
        wp_id, project_id=None, sheet_uid="五、1　审定表E1-1", db=db_session, user=_User()
    )
    assert body["count"] == 1
    assert body["items"][0]["stable_sheet_key"] == "审定表E1-1"


@pytest.mark.asyncio
async def test_unknown_sheet_uid_fail_closed_empty(db_session, seeded):
    """sheet_uid 无匹配 sheet → fail-closed 空集（不退回整册、不串页）。"""
    wp_id = seeded["wp_id"]
    body = await _router_mod.list_formulas(
        wp_id, project_id=None, sheet_uid="E1-999 不存在", db=db_session, user=_User()
    )
    assert body["count"] == 0
    assert body["items"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 单元：服务端过滤真源 + 变异反证
# ─────────────────────────────────────────────────────────────────────────────

def _items() -> list[dict]:
    """复刻 §1 #1 实测反例的 items（含 stable_sheet_key）。"""
    out = []
    for sheet_name, cell in _SEED_SHEETS:
        sk = derive_stable_key(sheet_name, cell)
        out.append(
            {
                "sheet_name": sheet_name,
                "target_cell": cell,
                "stable_sheet_key": sk.stable_sheet_key,
            }
        )
    return out


def test_filter_precise_equality_no_cross_page():
    """精确等值：E1-1 只命中 E1-1，不串入 E1-10/E1-14（反向断言：精确不误红）。"""
    kept = filter_items_by_sheet_uid(_items(), "E1-1")
    assert len(kept) == 1
    assert kept[0]["stable_sheet_key"] == "审定表E1-1"


def test_filter_omit_returns_all():
    """省略 sheet_uid = 不过滤（整册）。"""
    assert len(filter_items_by_sheet_uid(_items(), None)) == len(_SEED_SHEETS)
    assert len(filter_items_by_sheet_uid(_items(), "   ")) == len(_SEED_SHEETS)


def test_filter_fail_closed_on_rows_without_structural_identity():
    """缺结构身份的行（stable_sheet_key / sheet_name 均空）→ fail-closed 排除。"""
    rows = [{"stable_sheet_key": None, "sheet_name": None, "target_cell": "B5"}]
    assert filter_items_by_sheet_uid(rows, "E1-1") == []
    assert row_matches_sheet_uid(rows[0], "E1-1") is False


def test_mutation_prefix_match_would_cross_page_and_fail_precise_assertion():
    """变异反证：把服务端编码等值**放宽为子串匹配**（旧 includes 口径），E1-1 串入 E1-10/E1-14。

    - 变异（includes 子串）命中 3 行（E1-1 + E1-10 + E1-14）⇒ 精确断言 `== 1` 打红。
    - 反向断言：生产**精确**过滤恰 1 行（不误红）。
    - 变异命中数 != 精确命中数 ⇒ 精确断言能捕获该变异。
    """
    from app.services.formula_management.sheet_identity_filter import (
        extract_sheet_code_from_name,
        normalize_sheet_code,
    )

    def _mutated_includes_filter(items, sheet_uid):
        """缺陷版：结构化编码用 includes 子串匹配（旧 matchSheetCode 的 a⊂b||b⊂a 口径）。"""
        want = normalize_sheet_code(sheet_uid)
        if not want:
            return list(items)
        out = []
        for row in items:
            code = extract_sheet_code_from_name(
                row.get("stable_sheet_key")
            ) or extract_sheet_code_from_name(row.get("sheet_name"))
            if code and (want in code or code in want):  # ← 缺陷：子串串页
                out.append(row)
        return out

    items = _items()
    crossed = _mutated_includes_filter(items, "E1-1")
    # 旧 includes：E1-1 作为子串命中 审定表E1-1 / 银行账户核对表E1-10 / 货币资金分析表E1-14
    crossed_codes = {
        extract_sheet_code_from_name(r["stable_sheet_key"]) for r in crossed
    }
    assert crossed_codes == {"e1-1", "e1-10", "e1-14"}, (
        "子串匹配应把 E1-1 串入 E1-10/E1-14（证明精确断言能捕获变异）"
    )
    assert len(crossed) == 3

    # 反向断言：生产精确过滤恰 1 行（不误红）。
    precise = filter_items_by_sheet_uid(items, "E1-1")
    assert len(precise) == 1
    assert precise[0]["stable_sheet_key"] == "审定表E1-1"
    # 变异命中数 != 精确命中数 ⇒ 精确断言 `== 1` 会对变异打红。
    assert len(crossed) != len(precise)


def test_single_source_normalization_reuse():
    """服务端归一复用 stable_key 单一真源（禁另写）：row_matches 与 normalize 同口径。"""
    from app.services.formula_management.stable_key import normalize_sheet_key

    row = {"stable_sheet_key": "审定表E1-1", "sheet_name": "五、1　审定表E1-1"}
    # 传入带前缀/全角空格的展示名，归一后与 stable_sheet_key 精确相等 → 命中。
    assert row_matches_sheet_uid(row, "五、1　审定表E1-1") is True
    assert normalize_sheet_key("五、1　审定表E1-1") == "审定表E1-1"
