"""需求 1.10 的重放世界：把真库里 29 条历史 ``wp_formula`` 及其底稿复制到【测试】项目（原行只读）。

spec formula-hub-integrity-closure 任务 25 / 需求 1.10。不被 pytest 收集（无 `test_` 前缀）。

要点：
- 源项目是软删的 ``辽宁卫生服务有限公司``（F2），只 SELECT，不改一个字节；
- 复制用 ``jsonb_populate_record(NULL::<表>, to_jsonb(src) || 覆盖)``：整行按表类型回灌，
  不手写列清单 —— 手写列清单会在源表加列时静默漏列（而 jsonb 回灌漏列会当场报类型错）；
- 全部写入都在调用方的事务里（``pg_tx`` 结束回滚）。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import text

from app.models.core import Project
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX

#: F2：29 条 wp_formula 全属这个已软删的项目
SOURCE_CLIENT_NAME = "辽宁卫生服务有限公司"
REPLAY_YEAR = 2025


@dataclass
class ReplayRow:
    """复制到【测试】项目后的一条公式及其底稿信息。"""

    formula_id: uuid.UUID
    wp_id: uuid.UUID
    wp_code: str
    sheet_name: str
    target_cell: str
    expression: str
    stable_sheet_key: str | None
    row_key: str | None
    field_key: str | None
    html_keys: tuple[str, ...]
    cells: dict[str, Any] = field(default_factory=dict)

    @property
    def identity_cell(self) -> str:
        """与生产 `_derive_identity` 同口径的格键：field_key + row_key。"""
        return f"{self.field_key or ''}{self.row_key or ''}"


@dataclass
class ReplayWorld:
    project_id: uuid.UUID
    rows: list[ReplayRow]
    #: wp_id → parsed_data（复制后的原始快照）
    parsed: dict[uuid.UUID, dict]


_SOURCE_SQL = text("""
    SELECT f.id            AS formula_id,
           f.wp_id         AS wp_id,
           wi.wp_code      AS wp_code,
           wi.id           AS wp_index_id,
           f.sheet_name    AS sheet_name,
           f.target_cell   AS target_cell,
           f.expression    AS expression,
           f.stable_sheet_key,
           f.row_key,
           f.field_key,
           wp.parsed_data  AS parsed_data
      FROM wp_formula f
      JOIN working_paper wp ON wp.id = f.wp_id
      JOIN wp_index wi      ON wi.id = wp.wp_index_id
      JOIN projects p       ON p.id = f.project_id
     WHERE p.client_name = :client
     ORDER BY wi.wp_code, f.target_cell
""")


async def _copy_row(session, table: str, src_id: uuid.UUID, overrides: dict[str, Any]) -> None:
    """整行按表类型回灌复制：``to_jsonb(src) || overrides`` → ``jsonb_populate_record``。"""
    await session.execute(
        text(
            f"INSERT INTO {table} "
            f"SELECT r.* FROM {table} src, "
            f"     jsonb_populate_record(NULL::{table}, to_jsonb(src) || CAST(:ov AS jsonb)) r "
            f" WHERE src.id = :src_id"
        ),
        {"ov": json.dumps({k: (str(v) if isinstance(v, uuid.UUID) else v)
                           for k, v in overrides.items()}), "src_id": src_id},
    )


async def build_replay_world(session) -> ReplayWorld:
    """在调用方事务里建【测试】项目并复制 29 条公式 + 其底稿；返回复制后的行清单。"""
    src_rows = (await session.execute(_SOURCE_SQL, {"client": SOURCE_CLIENT_NAME})).mappings().all()
    if not src_rows:
        pytest.fail(f"真库里找不到源项目 {SOURCE_CLIENT_NAME} 的 wp_formula 行（需求 1.10 的重放对象）",
                    pytrace=False)

    tag = uuid.uuid4().hex[:10]
    project = Project(
        name=f"{TEST_PROJECT_PREFIX}fh_replay29_{tag}",
        client_name=f"{TEST_PROJECT_PREFIX}Runtime 重放",
        audit_year=REPLAY_YEAR,
    )
    session.add(project)
    await session.flush()

    index_map: dict[uuid.UUID, uuid.UUID] = {}
    wp_map: dict[uuid.UUID, uuid.UUID] = {}
    rows: list[ReplayRow] = []
    parsed: dict[uuid.UUID, dict] = {}

    for src in src_rows:
        if src["wp_index_id"] not in index_map:
            new_index = uuid.uuid4()
            await _copy_row(session, "wp_index", src["wp_index_id"],
                            {"id": new_index, "project_id": project.id})
            index_map[src["wp_index_id"]] = new_index
        if src["wp_id"] not in wp_map:
            new_wp = uuid.uuid4()
            await _copy_row(session, "working_paper", src["wp_id"], {
                "id": new_wp,
                "project_id": project.id,
                "wp_index_id": index_map[src["wp_index_id"]],
            })
            wp_map[src["wp_id"]] = new_wp
        new_formula = uuid.uuid4()
        await _copy_row(session, "wp_formula", src["formula_id"], {
            "id": new_formula,
            "project_id": project.id,
            "wp_id": wp_map[src["wp_id"]],
        })

        pd = src["parsed_data"] if isinstance(src["parsed_data"], dict) else {}
        html = pd.get("html_data") if isinstance(pd.get("html_data"), dict) else {}
        sheet = html.get(src["sheet_name"]) or next(iter(html.values()), {})
        cells = sheet.get("cells") if isinstance(sheet, dict) else {}
        new_wp_id = wp_map[src["wp_id"]]
        parsed[new_wp_id] = pd
        rows.append(ReplayRow(
            formula_id=new_formula,
            wp_id=new_wp_id,
            wp_code=str(src["wp_code"] or ""),
            sheet_name=str(src["sheet_name"] or ""),
            target_cell=str(src["target_cell"] or ""),
            expression=str(src["expression"] or ""),
            stable_sheet_key=src["stable_sheet_key"],
            row_key=src["row_key"],
            field_key=src["field_key"],
            html_keys=tuple(sorted(html.keys())),
            cells=dict(cells) if isinstance(cells, dict) else {},
        ))

    await session.flush()
    return ReplayWorld(project_id=project.id, rows=rows, parsed=parsed)


async def html_key_sets(session, wp_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[str, ...]]:
    """各底稿当前 ``parsed_data.html_data`` 的键集合（排序后）。"""
    out: dict[uuid.UUID, tuple[str, ...]] = {}
    rows = (await session.execute(
        text("SELECT id, parsed_data FROM working_paper WHERE id = ANY(:ids)"),
        {"ids": wp_ids})).all()
    for wp_id, pd in rows:
        html = (pd or {}).get("html_data") if isinstance(pd, dict) else {}
        out[wp_id] = tuple(sorted((html or {}).keys()))
    return out


async def parsed_digests(session, wp_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """各底稿 ``parsed_data`` 规范化 JSON 的 sha256（键排序、无空格）。"""
    import hashlib

    out: dict[uuid.UUID, str] = {}
    rows = (await session.execute(
        text("SELECT id, parsed_data FROM working_paper WHERE id = ANY(:ids)"),
        {"ids": wp_ids})).all()
    for wp_id, pd in rows:
        blob = json.dumps(pd, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
        out[wp_id] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return out
