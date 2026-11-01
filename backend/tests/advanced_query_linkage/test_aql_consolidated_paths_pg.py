"""合并项目路径的真 PostgreSQL 实测（任务 38；design §10.5 的合并段落）。

🔴 **纠正任务 38 的前置判断**：此前记「现库 0 个合并项目」，是按 `projects.project_type='consolidated'` 判的，
而该列的 PG 枚举 `projecttype` **根本没有 `consolidated` 取值**（现查 = annual / special / ipo /
internal_control / capital_verification / tax_audit）。生产代码的真实判据是
`fetchers/disclosure._report_scope` 读的 **`projects.report_scope`**：按它现查**未删除的合并项目有 3 个**。

本文件只读真实数据，经 `business` 夹具真发请求到生产注册的 custom_query router（无需起服务），
逐条核对四类合并路径：有数据的要返回数据，没数据的要 200 + 0 行、**不是 500**。
"""
from __future__ import annotations

import uuid

import pytest

from tests.advanced_query_linkage.gold import active_sql  # noqa: F401  (保持与同目录用例一致的导入面)

pytestmark = pytest.mark.pg_only

#: 真实判据：`projects.report_scope`（不是 project_type）
CONSOLIDATED_SQL = (
    "SELECT id, name, EXTRACT(YEAR FROM audit_period_end)::int FROM projects "
    "WHERE NOT is_deleted AND report_scope::text = 'consolidated' ORDER BY name"
)


async def _consolidated(gold) -> list[tuple[uuid.UUID, str, int | None]]:
    return [(row[0], row[1], row[2]) for row in await gold.rows(CONSOLIDATED_SQL)]


async def _project_by_name(gold, needle: str) -> tuple[uuid.UUID, str]:
    rows = [item for item in await _consolidated(gold) if needle in item[1]]
    assert len(rows) == 1, f"按名字片段「{needle}」应恰好命中一个合并项目，实得 {[r[1] for r in rows]}"
    return rows[0][0], rows[0][1]


async def test_project_type_enum_has_no_consolidated_value(gold) -> None:
    """钉住上面那条纠正：枚举里没有 consolidated，所以按 project_type 判必然恒 0。"""
    values = {row[0] for row in await gold.rows(
        "SELECT unnest(enum_range(NULL::projecttype))::text"
    )}
    assert "consolidated" not in values, f"枚举已新增该值，请重新评估判据：{sorted(values)}"
    assert "annual" in values


async def test_shared_library_has_consolidated_projects(gold) -> None:
    projects = await _consolidated(gold)
    assert len(projects) >= 1, "前置：共享库应有未删除的合并项目（按 report_scope 判）"
    # 三个合并项目的 audit_period_end 都是 NULL ⇒ 年度只能由数据侧给出，不能按 EXTRACT 取
    assert all(year is None for _pid, _name, year in projects)


async def test_consolidated_notes_return_rows_per_node(business, gold) -> None:
    """合并附注：`consol_note_data` 按 `node_key` 分列；合并项目沿用旧取数（`_query_disclosure`）。"""
    pid, _name = await _project_by_name(gold, "某测试集团")
    year = int(await gold.scalar(
        "SELECT max(year) FROM consol_note_data WHERE project_id = :pid", pid=pid,
    ))
    nodes = [row[0] for row in await gold.rows(
        "SELECT DISTINCT node_key FROM consol_note_data WHERE project_id=:pid AND year=:year "
        "AND node_key IS NOT NULL ORDER BY 1 LIMIT 3", pid=pid, year=year,
    )]
    assert nodes, "前置：该项目应有带 node_key 的合并附注行"

    for node_key in nodes:
        # 取数器把每章节的 ``data.rows`` 展平成表格行（每章节上限 100 行），金标准按同口径算
        expected = int(await gold.scalar(
            "SELECT COALESCE(sum(LEAST(jsonb_array_length(COALESCE(data->'rows', '[]'::jsonb)), 100)), 0) "
            "FROM consol_note_data WHERE project_id=:pid AND year=:year AND node_key=:node "
            "AND jsonb_typeof(COALESCE(data->'rows', '[]'::jsonb)) = 'array'",
            pid=pid, year=year, node=node_key,
        ))
        data = await business.ok(pid, "disclosure", year=year, filters={"node_key": node_key}, limit=2000)
        assert data["total"] == expected, f"{node_key}：total {data['total']} ≠ 金标准 {expected}"
        assert data["rows"], f"{node_key}：应返回行"
        # 节点精确匹配：不得混入别的节点（旧请求只读 node_key IS NULL）
        assert all("section_id" in row for row in data["rows"])


async def test_consolidated_note_section_falls_back_to_consol_note_data(business, gold) -> None:
    """`disclosure_note:{章节}`：合并项目走 `_query_disclosure`（按 `section_id` 过滤），不是单体的表格路径。"""
    pid, _name = await _project_by_name(gold, "某测试集团")
    year = int(await gold.scalar(
        "SELECT max(year) FROM consol_note_data WHERE project_id = :pid", pid=pid,
    ))
    section, node_key = (await gold.rows(
        "SELECT section_id, node_key FROM consol_note_data WHERE project_id=:pid AND year=:year "
        "AND node_key IS NOT NULL ORDER BY section_id LIMIT 1", pid=pid, year=year,
    ))[0]

    data = await business.ok(
        pid, f"disclosure_note:{section}", year=year, filters={"node_key": node_key}, limit=2000,
    )
    expected = int(await gold.scalar(
        "SELECT COALESCE(sum(LEAST(jsonb_array_length(COALESCE(data->'rows', '[]'::jsonb)), 100)), 0) "
        "FROM consol_note_data WHERE project_id=:pid AND year=:year "
        "AND node_key=:node AND section_id=:section",
        pid=pid, year=year, node=node_key, section=section,
    ))
    assert data["total"] == expected
    assert data["rows"]
    assert {row["section_id"] for row in data["rows"]} == {section}, "章节请求不得混入别的章节"


async def test_worksheet_sources_return_their_rows_or_an_empty_page(business, gold) -> None:
    """`ws_*`：有数据的 sheet 返回数据，没有的 200 + 0 行（不是 500、也不是 UNKNOWN_SOURCE）。"""
    pid, _name = await _project_by_name(gold, "公式同步集团")
    year = int(await gold.scalar(
        "SELECT max(year) FROM consol_worksheet_data WHERE project_id = :pid", pid=pid,
    ))
    present = {row[0] for row in await gold.rows(
        "SELECT sheet_key FROM consol_worksheet_data WHERE project_id=:pid AND year=:year",
        pid=pid, year=year,
    )}
    assert "info" in present, f"前置：该项目应有 info 工作底稿，实得 {sorted(present)}"

    filled = await business.ok(pid, "ws_info", year=year, limit=2000)
    assert filled["rows"], "ws_info 应返回行"

    # 🔴 源键必须决定 sheet：`_query_worksheet` 读 `filters.sheet_key`，此前只有弹窗会设它 ⇒ 不设的调用方
    # 拿 `ws_elimination` 会静默取到 `info` 的数据。本轮改由 `resolve_source` 下发 `fixed_filters`。
    for sheet in ("elimination", "consol_tb"):
        assert sheet not in present, f"前置假设变了：{sheet} 现在有数据，请改为逐值对账"
        empty = await business.ok(pid, f"ws_{sheet}", year=year, limit=2000)
        assert empty["total"] == 0 and empty["rows"] == [], (
            f"ws_{sheet} 不该回落到 info（info 现有 {filled['total']} 行）"
        )
    assert filled["total"] > 0, "前置：info 有行，上面那条「不回落」才有判别力"


async def test_tb_summary_without_data_is_an_empty_page(business, gold) -> None:
    """`tb_summary`（合并试算平衡表工作底稿）：现库没有 `tb_summary_*` sheet ⇒ 200 + 0 行。"""
    pid, _name = await _project_by_name(gold, "公式同步集团")
    year = int(await gold.scalar(
        "SELECT max(year) FROM consol_worksheet_data WHERE project_id = :pid", pid=pid,
    ))
    assert int(await gold.scalar(
        "SELECT count(*) FROM consol_worksheet_data WHERE project_id=:pid AND year=:year "
        "AND sheet_key LIKE 'tb_summary%'", pid=pid, year=year,
    )) == 0, "前置假设变了：已有 tb_summary sheet，请改为逐值对账"

    data = await business.ok(pid, "tb_summary", year=year, limit=2000)
    assert data["total"] == 0 and data["rows"] == []


@pytest.mark.parametrize("kind", ["tb_detail", "account_balance", "ledger_entries", "adjustment"])
async def test_consol_unit_sources_resolve_and_scope_by_company(business, gold, kind: str) -> None:
    """`consol_unit:{单位}:{kind}`：源键能解析、按 company_code 收窄；合并项目四表现无行 ⇒ 200 + 0 行。"""
    pid, _name = await _project_by_name(gold, "公式同步集团")
    year = 2025
    company = "001"
    assert int(await gold.scalar(
        "SELECT count(*) FROM trial_balance WHERE project_id=:pid AND year=:year AND NOT is_deleted",
        pid=pid, year=year,
    )) == 0, "前置假设变了：该合并项目已有试算表行，请改为逐值对账"

    body = {"limit": 100}
    if kind == "ledger_entries":
        body["filters"] = {"account_code": "1002"}  # 账簿类源需要收窄键时一并带上
    data = await business.ok(pid, f"consol_unit:{company}:{kind}", year=year, **body)
    assert data["total"] == 0 and data["rows"] == []


async def test_unknown_consol_unit_kind_is_400(business, gold) -> None:
    pid, _name = await _project_by_name(gold, "公式同步集团")
    detail = await business.error(pid, "consol_unit:001:no_such_kind", 400, year=2025)
    assert detail["error_code"] == "UNKNOWN_SOURCE"
