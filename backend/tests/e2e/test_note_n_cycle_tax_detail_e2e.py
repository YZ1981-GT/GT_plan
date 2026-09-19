"""N 循环税务类附注章节详情（N2 / N4 / N5）—— 进程内 ASGI 端到端。

验证 `GET /api/disclosure-notes/{project_id}/{year}/{note_section}` 的**真实 router 接线**：
读时投影 + `guidance` 回填两步都落在响应里。

为什么用进程内 ASGI 而不是打 live server：本机 9980 上的 uvicorn `--reload` 实测不生效，
改 `.py` 端点持续返回旧代码结果；重启共享 dev 后端会打断并发会话。`ASGITransport`
直连 `app.main:app`，跑的就是当前磁盘上的代码。

覆盖：
1. 各章节表数 = 该变体子表名全集（N2 各 1 / N4 上市 1 / N5 各 2）
2. **N2 两版列数不同**（上市 3 列双期 / 国企 5 列变动）—— 原被 md 重建压成同一形状
3. **N5 两表名互不重复**（原各自重名 → `sub_table_data` 键互相覆盖丢整表）
4. 全部表 `_column_groups == []`（本批全是单级表头，`flat` 显式表态）
5. 全部表带非空 `guidance`（TAB 编制提示）
6. `source_template` 记错成另一变体时 guidance 仍能填
7. **国企税金及附加章节不存在**（源模板「附注披露信息：无」，不得"补齐"）

spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/` Task 9.5
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.e2e

_DATA = Path(__file__).resolve().parents[2] / "data"
_TEMPLATE = {"listed": "note_template_listed.json", "soe": "note_template_soe.json"}
_YEAR = 2025

# (cycle, variant) → 章节号
_SECTION = {
    ("N2", "listed"): "五、41",
    ("N2", "soe"): "八、41",
    ("N4", "listed"): "五、63",
    ("N5", "listed"): "三、所得税费用",
    ("N5", "soe"): "八、78",
}

_EXPECTED_TABLE_COUNT = {
    ("N2", "listed"): 1,
    ("N2", "soe"): 1,
    ("N4", "listed"): 1,
    ("N5", "listed"): 2,
    ("N5", "soe"): 2,
}

_CASES = sorted(_SECTION.keys())


def _template_tables(variant: str, section: str) -> list[dict]:
    data = json.loads((_DATA / _TEMPLATE[variant]).read_text(encoding="utf-8"))
    sec = next(s for s in data["sections"] if s.get("section_number") == section)
    return sec["tables"]


def _synced_table_data(variant: str, section: str) -> dict:
    """造一份「底稿刚同步完」形状的 table_data（`_source=workpaper`）。"""
    sub: dict[str, list[dict]] = {}
    cols: dict[str, list[dict]] = {}
    for t in _template_tables(variant, section):
        defs = t["columns"]
        cols[t["name"]] = defs
        row = {d["key"]: (None if d.get("format") == "amount" else "") for d in defs}
        row[defs[0]["key"]] = "示例行"
        sub[t["name"]] = [row]
    return {"_source": "workpaper", "sub_table_data": sub, "_sub_table_columns": cols}


@pytest_asyncio.fixture
async def note_project(db_session: AsyncSession, admin_user):
    from app.models.core import Project

    suffix = uuid4().hex[:6]
    project = Project(
        id=uuid4(),
        name=f"n-tax-e2e-{suffix}",
        client_name=f"n-tax-e2e-client-{suffix}",  # NOT NULL
    )
    db_session.add(project)
    await db_session.commit()
    return project


async def _seed_note(
    db_session: AsyncSession,
    project_id,
    variant: str,
    section: str,
    *,
    source_template: str,
) -> None:
    from app.models.report_models import DisclosureNote

    db_session.add(
        DisclosureNote(
            id=uuid4(),
            project_id=project_id,
            year=_YEAR,
            note_section=section,
            section_title=section,
            account_name=section,
            content_type="mixed",
            table_data=_synced_table_data(variant, section),
            source_template=source_template,
            status="draft",
        )
    )
    await db_session.commit()


async def _fetch_tables(client, project_id, section: str) -> list[dict]:
    url = f"/api/disclosure-notes/{project_id}/{_YEAR}/{quote(section)}"
    resp = await client.get(url)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data") or body
    return (data.get("table_data") or {}).get("_tables") or []


@pytest.mark.asyncio
@pytest.mark.parametrize(("cycle", "variant"), _CASES)
async def test_detail_returns_full_table_set(
    client, db_session, note_project, cycle, variant
) -> None:
    section = _SECTION[(cycle, variant)]
    await _seed_note(db_session, note_project.id, variant, section, source_template=variant)
    tables = await _fetch_tables(client, note_project.id, section)
    assert len(tables) == _EXPECTED_TABLE_COUNT[(cycle, variant)]
    assert {t["name"] for t in tables} == {
        t["name"] for t in _template_tables(variant, section)
    }


@pytest.mark.asyncio
async def test_n2_variant_column_shapes_differ(client, db_session, note_project) -> None:
    """🔴 上市 3 列双期 / 国企 5 列变动 —— 两版口径本质不同，不得被"统一"。"""
    heads: dict[str, list[str]] = {}
    for variant in ("listed", "soe"):
        section = _SECTION[("N2", variant)]
        await _seed_note(db_session, note_project.id, variant, section, source_template=variant)
        tables = await _fetch_tables(client, note_project.id, section)
        heads[variant] = tables[0]["headers"]
    assert heads["listed"] == ["税项", "期末余额", "上年年末余额"]
    assert heads["soe"] == ["项目", "期初余额", "本期应交", "本期已交", "期末余额"]


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["listed", "soe"])
async def test_n5_two_tables_have_distinct_names(
    client, db_session, note_project, variant
) -> None:
    """🔴 表名是 `sub_table_data` 的键，重名会互相覆盖**丢整张表**。"""
    section = _SECTION[("N5", variant)]
    await _seed_note(db_session, note_project.id, variant, section, source_template=variant)
    tables = await _fetch_tables(client, note_project.id, section)
    names = [t["name"] for t in tables]
    assert len(names) == 2
    assert len(set(names)) == 2, names
    assert "项  目" not in names  # md 重建把表头首格当表名的旧值


@pytest.mark.asyncio
async def test_n5_soe_reconcile_table_has_three_columns(
    client, db_session, note_project
) -> None:
    """国企表 2 原被压扁成 2 列（丢「上期发生额」）。"""
    section = _SECTION[("N5", "soe")]
    await _seed_note(db_session, note_project.id, "soe", section, source_template="soe")
    t = next(
        x
        for x in await _fetch_tables(client, note_project.id, section)
        if x["name"] == "会计利润与所得税费用调整过程"
    )
    assert t["headers"] == ["项目", "本期发生额", "上期发生额"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("cycle", "variant"), _CASES)
async def test_detail_single_level_headers(
    client, db_session, note_project, cycle, variant
) -> None:
    """本批全是单级表头 → `flat` 显式表态，投影出的分组必须为空。"""
    section = _SECTION[(cycle, variant)]
    await _seed_note(db_session, note_project.id, variant, section, source_template=variant)
    for t in await _fetch_tables(client, note_project.id, section):
        assert t["_column_groups"] == [], f"{section}/{t['name']}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("cycle", "variant"), _CASES)
async def test_detail_all_tables_carry_guidance(
    client, db_session, note_project, cycle, variant
) -> None:
    section = _SECTION[(cycle, variant)]
    await _seed_note(db_session, note_project.id, variant, section, source_template=variant)
    tables = await _fetch_tables(client, note_project.id, section)
    missing = [t["name"] for t in tables if not str(t.get("guidance") or "").strip()]
    assert missing == []


@pytest.mark.asyncio
async def test_detail_guidance_survives_misrecorded_source_template(
    client, db_session, note_project
) -> None:
    """项目用国企版模板生成时上市章节也被标 soe，guidance 仍须填上。"""
    section = _SECTION[("N5", "listed")]
    await _seed_note(db_session, note_project.id, "listed", section, source_template="soe")
    tables = await _fetch_tables(client, note_project.id, section)
    assert len(tables) == 2
    assert all(str(t.get("guidance") or "").strip() for t in tables)


def test_soe_template_has_no_taxes_surcharges_section() -> None:
    """🔴 源模板国企版「附注披露信息：无」→ 不得为国企"补齐"税金及附加章节。"""
    data = json.loads((_DATA / _TEMPLATE["soe"]).read_text(encoding="utf-8"))
    hits = [
        s.get("section_number")
        for s in data["sections"]
        if "税金及附加" in str(s.get("section_title") or "")
    ]
    assert hits == []
