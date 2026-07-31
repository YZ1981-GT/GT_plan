"""N1 递延所得税附注章节详情 —— 进程内 ASGI 端到端。

验证 `GET /api/disclosure-notes/{project_id}/{year}/{note_section}` 的**真实 router 接线**：
读时投影 + `guidance` 回填两步都落在响应里。

为什么用进程内 ASGI 而不是打 live server（2026-07-30）：
本机 9980 上同时跑着 `.venv` 与系统 python 两个 uvicorn（均带 `--reload`），实测
改 `.py` **不会热加载**，端点持续返回旧代码结果；而重启共享 dev 后端会打断并发会话。
`ASGITransport` 直连 `app.main:app`，跑的就是当前磁盘上的代码，比 live server 更可靠。

覆盖：
1. `_tables` 表数 = 该变体子表名全集（listed 4 / soe 5）
2. 表 1 两级表头 `_column_groups` 正确，且**两版子列序相反**（源模板 B11:E11）
3. 其余表 `_column_groups == []`（`flat` 显式单级）
4. **全部表带非空 `guidance`**（TAB 编制提示；此前投影路径整体丢弃 → 恒空）
5. `source_template` 被**记错**成另一变体时 guidance 仍能填
   （实证：项目用国企版模板生成 → 连上市章节号 `五、30` 都被标 `soe`）

spec: `.kiro/specs/n1-deferred-tax-disclosure-template-alignment/` Task 10.1
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
_DIFF = "可抵扣/应纳税暂时性差异"
_TAX = "递延所得税资产/负债"
_UNOFFSET = "未经抵销的递延所得税资产和递延所得税负债"

_SECTION = {"listed": "五、30", "soe": "八、31"}
_TEMPLATE = {"listed": "note_template_listed.json", "soe": "note_template_soe.json"}
_SUB_ORDER = {"listed": [_DIFF, _TAX], "soe": [_TAX, _DIFF]}
_PRIOR_GROUP = {"listed": "上年年末余额", "soe": "年初余额"}
_YEAR = 2025


def _template_tables(variant: str) -> list[dict]:
    data = json.loads((_DATA / _TEMPLATE[variant]).read_text(encoding="utf-8"))
    sec = next(s for s in data["sections"] if s.get("section_number") == _SECTION[variant])
    return sec["tables"]


def _synced_table_data(variant: str) -> dict:
    """造一份「底稿刚同步完」形状的 table_data（_source=workpaper）。"""
    sub: dict[str, list[dict]] = {}
    cols: dict[str, list[dict]] = {}
    for t in _template_tables(variant):
        defs = t["columns"]
        cols[t["name"]] = defs
        row = {d["key"]: (None if d.get("format") == "amount" else "") for d in defs}
        row[defs[0]["key"]] = "示例行"
        sub[t["name"]] = [row]
    return {"_source": "workpaper", "sub_table_data": sub, "_sub_table_columns": cols}


@pytest_asyncio.fixture
async def note_project(db_session: AsyncSession, admin_user):
    """建一个项目（附注章节挂在其上）。"""
    from app.models.core import Project

    suffix = uuid4().hex[:6]
    project = Project(
        id=uuid4(),
        name=f"n1-e2e-{suffix}",
        client_name=f"n1-e2e-client-{suffix}",  # NOT NULL
    )
    db_session.add(project)
    await db_session.commit()
    return project


async def _seed_note(
    db_session: AsyncSession, project_id, variant: str, *, source_template: str
) -> None:
    from app.models.report_models import DisclosureNote

    db_session.add(
        DisclosureNote(
            id=uuid4(),
            project_id=project_id,
            year=_YEAR,
            note_section=_SECTION[variant],
            section_title="递延所得税资产和递延所得税负债",
            account_name="递延所得税资产和递延所得税负债",
            content_type="mixed",
            table_data=_synced_table_data(variant),
            source_template=source_template,
            status="draft",
        )
    )
    await db_session.commit()


async def _fetch_tables(client, project_id, variant: str) -> list[dict]:
    url = f"/api/disclosure-notes/{project_id}/{_YEAR}/{quote(_SECTION[variant])}"
    resp = await client.get(url)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    data = body.get("data") or body
    return (data.get("table_data") or {}).get("_tables") or []


@pytest.mark.asyncio
@pytest.mark.parametrize(("variant", "expected"), [("listed", 4), ("soe", 5)])
async def test_detail_returns_full_table_set(
    client, db_session, note_project, variant, expected
) -> None:
    await _seed_note(db_session, note_project.id, variant, source_template=variant)
    tables = await _fetch_tables(client, note_project.id, variant)
    assert len(tables) == expected
    assert {t["name"] for t in tables} == {t["name"] for t in _template_tables(variant)}


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["listed", "soe"])
async def test_detail_unoffset_two_level_header(
    client, db_session, note_project, variant
) -> None:
    await _seed_note(db_session, note_project.id, variant, source_template=variant)
    t = next(x for x in await _fetch_tables(client, note_project.id, variant)
             if x["name"] == _UNOFFSET)
    order = _SUB_ORDER[variant]
    assert t["headers"] == ["项目", *order, *order]
    assert t["_column_groups"] == [
        {"group": "期末余额", "start": 1, "span": 2},
        {"group": _PRIOR_GROUP[variant], "start": 3, "span": 2},
    ]


@pytest.mark.asyncio
async def test_detail_sub_order_mirrored_between_variants(
    client, db_session, note_project
) -> None:
    """两版子列序不得被"统一"（统一后附注列串味）。"""
    for v in ("listed", "soe"):
        await _seed_note(db_session, note_project.id, v, source_template=v)
    heads = {}
    for v in ("listed", "soe"):
        t = next(x for x in await _fetch_tables(client, note_project.id, v)
                 if x["name"] == _UNOFFSET)
        heads[v] = t["headers"][1:3]
    assert heads["listed"] == [_DIFF, _TAX]
    assert heads["soe"] == [_TAX, _DIFF]


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["listed", "soe"])
async def test_detail_single_level_tables_have_empty_groups(
    client, db_session, note_project, variant
) -> None:
    await _seed_note(db_session, note_project.id, variant, source_template=variant)
    for t in await _fetch_tables(client, note_project.id, variant):
        if t["name"] == _UNOFFSET:
            continue
        assert t["_column_groups"] == [], t["name"]


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", ["listed", "soe"])
async def test_detail_all_tables_carry_guidance(
    client, db_session, note_project, variant
) -> None:
    """🔴 核心回归点：投影路径此前整体丢弃模板 guidance → TAB 提示恒空。"""
    await _seed_note(db_session, note_project.id, variant, source_template=variant)
    tables = await _fetch_tables(client, note_project.id, variant)
    missing = [t["name"] for t in tables if not str(t.get("guidance") or "").strip()]
    assert missing == []


@pytest.mark.asyncio
async def test_detail_guidance_survives_misrecorded_source_template(
    client, db_session, note_project
) -> None:
    """项目用国企版模板生成时上市章节也被标 soe，guidance 仍须填上。"""
    await _seed_note(db_session, note_project.id, "listed", source_template="soe")
    tables = await _fetch_tables(client, note_project.id, "listed")
    assert len(tables) == 4
    assert all(str(t.get("guidance") or "").strip() for t in tables)


@pytest.mark.asyncio
async def test_detail_soe_has_offset_detail_table(
    client, db_session, note_project
) -> None:
    """源模板（2）B 互抵明细（本 spec 新增），此前整张缺失。"""
    await _seed_note(db_session, note_project.id, "soe", source_template="soe")
    t = next(x for x in await _fetch_tables(client, note_project.id, "soe")
             if x["name"] == "递延所得税资产和递延所得税负债互抵明细")
    assert t["headers"] == ["项目", "本期互抵金额"]
