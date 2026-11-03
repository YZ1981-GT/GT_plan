"""W3 十条系统预置的真 PostgreSQL 金标准（任务 44）。

真实项目只读；当前业务数据没有“借贷双方同时有金额”和空摘要，二者在同连接回滚
事务中各造反例。项目 UUID 不写死：共享库曾整体重建，固定 UUID 会造成 403 或空集假绿。
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa

import app.core.redis as core_redis
from app.models.audit_platform_models import TbLedger
from app.models.custom_query_models import CustomQueryTemplate
from app.services.custom_query.param_sql_builder import BLANK_CHARS
from tests.advanced_query_linkage.gold import AUDIT_YEAR, active_sql

pytestmark = pytest.mark.pg_only
CQ = "/api/custom-query"
COLUMNS = [
    "voucher_date", "voucher_no", "account_code", "account_name",
    "debit_amount", "credit_amount", "summary",
]
SELECT_COLUMNS = ", ".join(f"t.{name}" for name in COLUMNS)
ORDER = "t.voucher_date DESC NULLS LAST, t.voucher_no ASC NULLS LAST, t.entry_seq ASC NULLS LAST, t.id ASC"
ACTIVE = active_sql("t")
PROJECTS = {
    "hp": "重庆和平药房连锁有限责任公司_2025",
    "yb": "重庆医药集团宜宾医药有限公司新健康大药房临港店_2025",
    "hs": "陕西华氏医药有限公司_2025",
    "ah": "重药控股安徽有限公司_2025",
}

REAL_CASES = {
    "je_account_ledger": ("hp", "t.account_code LIKE '1002%'", {}),
    "je_reversal": (
        "hp",
        "(t.summary LIKE :r1 OR t.summary LIKE :r2 OR t.summary LIKE :r3 OR t.summary LIKE :r4)",
        {"r1": "%冲销%", "r2": "%红字%", "r3": "%冲红%", "r4": "%冲回%"},
    ),
    "je_negative_amount": ("hp", "(t.debit_amount < 0 OR t.credit_amount < 0)", {}),
    "je_cutoff": ("yb", "t.voucher_date BETWEEN :start AND :end", {}),
    "je_large_amount": (
        "hp", "GREATEST(COALESCE(t.debit_amount,0), COALESCE(t.credit_amount,0)) >= :threshold", {},
    ),
    "je_weekend": ("hp", "EXTRACT(DOW FROM t.voucher_date) IN (0,6)", {}),
    "je_special_event": (
        "ah",
        "(t.summary LIKE :s1 OR t.summary LIKE :s2 OR t.summary LIKE :s3 OR t.summary LIKE :s4 "
        "OR t.summary LIKE :s5 OR t.summary LIKE :s6 OR t.summary LIKE :s7 OR t.summary LIKE :s8)",
        {"s1": "%关联交易%", "s2": "%收购%", "s3": "%合并%", "s4": "%重组%",
         "s5": "%诉讼%", "s6": "%处置%", "s7": "%清算%", "s8": "%破产%"},
    ),
    "je_vague_keywords": (
        "yb", "(t.summary LIKE :v1 OR t.summary LIKE :v2 OR t.summary LIKE :v3 OR t.summary LIKE :v4)",
        {"v1": "%调整%", "v2": "%暂估%", "v3": "%其他%", "v4": "%冲销%"},
    ),
}


async def _project_id(gold, name: str) -> uuid.UUID:
    rows = await gold.rows(
        "SELECT id FROM projects WHERE name=:name AND NOT is_deleted ORDER BY id", name=name,
    )
    assert len(rows) == 1, f"前置：未删除项目「{name}」应恰好一条，实得 {len(rows)} 条"
    return rows[0][0]


def _json_value(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return Decimal(str(value))
    return value


def _row_tuple(row: Any) -> tuple[Any, ...]:
    values = row if isinstance(row, dict) else dict(zip(COLUMNS, row))
    normalized = []
    for name in COLUMNS:
        value = values.get(name)
        if name in {"debit_amount", "credit_amount"} and value is not None:
            value = Decimal(str(value))
        normalized.append(_json_value(value))
    return tuple(normalized)


async def _resolve(business, preset_id: str, project_id: uuid.UUID) -> dict[str, Any]:
    response = await business.http.get(
        f"{CQ}/template-presets/{preset_id}/resolve",
        params={"project_id": str(project_id), "year": AUDIT_YEAR},
    )
    assert response.status_code == 200, response.text[:800]
    return response.json()


def _execute_body(project_id: uuid.UUID, resolved: dict[str, Any], *, limit: int = 100, offset: int = 0,
                  count_token: str | None = None) -> dict[str, Any]:
    config = resolved["config"]
    conditions = [
        {"field": item["field"], "op": item["op"], "value": item.get("value")}
        for item in config.get("conditions") or []
    ]
    return {
        "project_id": str(project_id), "year": AUDIT_YEAR, "source": config["source"],
        "columns": COLUMNS, "conditions": conditions,
        "condition_logic": config.get("condition_logic", "and"),
        "limit": limit, "offset": offset,
        **({"count_token": count_token} if count_token else {}),
    }


async def _execute(business, project_id: uuid.UUID, resolved: dict[str, Any], **page: Any) -> dict[str, Any]:
    response = await business.http.post(f"{CQ}/execute", json=_execute_body(project_id, resolved, **page))
    assert response.status_code == 200, response.text[:800]
    return response.json()


async def _gold(gold, project_id: uuid.UUID, where: str, params: dict[str, Any], *, limit: int | None = None,
                offset: int = 0) -> list[tuple[Any, ...]]:
    sql = f"SELECT {SELECT_COLUMNS} FROM tb_ledger t WHERE {ACTIVE} AND ({where}) ORDER BY {ORDER}"
    if limit is not None:
        sql += " LIMIT :gold_limit OFFSET :gold_offset"
    return await gold.rows(
        sql, pid=project_id, year=AUDIT_YEAR, **params,
        **({"gold_limit": limit, "gold_offset": offset} if limit is not None else {}),
    )


async def _gold_count_and_sums(gold, project_id: uuid.UUID, where: str, params: dict[str, Any]) -> tuple[int, Decimal, Decimal]:
    row = (await gold.rows(
        f"SELECT count(*), COALESCE(sum(t.debit_amount),0), COALESCE(sum(t.credit_amount),0) "
        f"FROM tb_ledger t WHERE {ACTIVE} AND ({where})",
        pid=project_id, year=AUDIT_YEAR, **params,
    ))[0]
    return int(row[0]), Decimal(str(row[1])), Decimal(str(row[2]))


def _resolved_params(preset_id: str, resolved: dict[str, Any]) -> dict[str, Any]:
    conditions = resolved["config"]["conditions"]
    if preset_id == "je_account_ledger":
        conditions[0]["value"] = "1002"
        return {}
    if preset_id == "je_cutoff":
        return {
            "start": dt.date.fromisoformat(conditions[0]["value"][0]),
            "end": dt.date.fromisoformat(conditions[0]["value"][1]),
        }
    if preset_id == "je_large_amount":
        assert resolved["params"][0]["value"] is not None, resolved["params"]
        return {"threshold": Decimal(str(resolved["params"][0]["value"]))}
    return {}


@pytest.mark.parametrize("preset_id", list(REAL_CASES))
async def test_real_presets_match_independent_sql(business, gold, preset_id: str) -> None:
    project_key, where, fixed_params = REAL_CASES[preset_id]
    project_id = await _project_id(gold, PROJECTS[project_key])
    resolved = await _resolve(business, preset_id, project_id)
    dynamic_params = _resolved_params(preset_id, resolved)
    params = {**fixed_params, **dynamic_params}

    result = await _execute(business, project_id, resolved)
    expected_count, debit_sum, credit_sum = await _gold_count_and_sums(gold, project_id, where, params)
    expected_first = await _gold(gold, project_id, where, params, limit=100)
    assert result["total"] == expected_count
    assert [_row_tuple(row) for row in result["rows"]] == [_row_tuple(row) for row in expected_first]

    if expected_count <= 5_000:
        all_rows: list[dict[str, Any]] = []
        token = None
        for offset in range(0, expected_count or 1, 2_000):
            page = await _execute(
                business, project_id, resolved, limit=2_000, offset=offset, count_token=token,
            )
            token = page.get("count_token")
            all_rows.extend(page["rows"])
        assert len(all_rows) == expected_count
        assert sum((Decimal(str(row.get("debit_amount") or 0)) for row in all_rows), Decimal()) == debit_sum
        assert sum((Decimal(str(row.get("credit_amount") or 0)) for row in all_rows), Decimal()) == credit_sum


async def _active_dataset_id(session, project_id: uuid.UUID) -> uuid.UUID | None:
    return (await session.execute(sa.text(
        "SELECT id FROM ledger_datasets WHERE project_id=:pid AND year=:year AND status='active' "
        "ORDER BY activated_at DESC NULLS LAST, created_at DESC LIMIT 1"
    ), {"pid": project_id, "year": AUDIT_YEAR})).scalar_one_or_none()


@pytest.mark.parametrize(
    ("preset_id", "summaries", "amounts"),
    [
        ("je_both_sides", ["【测试】双方金额"], [(Decimal("12"), Decimal("8"))]),
        ("je_no_summary", [None, "", " \t　"], [(Decimal("1"), Decimal("0"))] * 3),
    ],
)
async def test_sparse_presets_match_rollback_rows(business, gold, preset_id: str, summaries, amounts) -> None:
    project_id = await _project_id(gold, PROJECTS["hp"])
    resolved = await _resolve(business, preset_id, project_id)
    dataset_id = await _active_dataset_id(business.session, project_id)
    for index, (summary, (debit, credit)) in enumerate(zip(summaries, amounts)):
        business.session.add(TbLedger(
            id=uuid.uuid4(), project_id=project_id, year=AUDIT_YEAR, dataset_id=dataset_id,
            company_code="AQL_W3_ROLLBACK", voucher_date=dt.date(2025, 12, 20 + index),
            voucher_no=f"AQL-W3-{preset_id}-{index}", entry_seq=index,
            account_code="1002", account_name="银行存款", debit_amount=debit,
            credit_amount=credit, summary=summary,
        ))
    await business.session.flush()
    await core_redis.redis_client.flushdb()

    if preset_id == "je_both_sides":
        where, params = "t.debit_amount > 0 AND t.credit_amount > 0", {}
    else:
        where, params = "t.summary IS NULL OR btrim(t.summary, :blank_chars) = ''", {"blank_chars": BLANK_CHARS}
    raw = await business.session.execute(sa.text(
        f"SELECT count(*) FROM tb_ledger t WHERE {ACTIVE} AND ({where})"
    ), {"pid": project_id, "year": AUDIT_YEAR, **params})
    expected = int(raw.scalar_one())
    result = await _execute(business, project_id, resolved)
    assert result["total"] == expected
    voucher_nos = {row["voucher_no"] for row in result["rows"]}
    assert {f"AQL-W3-{preset_id}-{i}" for i in range(len(summaries))} <= voucher_nos


async def test_parameterized_user_template_rebinds_each_target_project(business, gold) -> None:
    hp = await _project_id(gold, PROJECTS["hp"])
    ah = await _project_id(gold, PROJECTS["ah"])
    yb = await _project_id(gold, PROJECTS["yb"])
    creator = (await business.session.execute(
        sa.text("SELECT id FROM users WHERE username='admin' ORDER BY id LIMIT 1")
    )).scalar_one()
    template = CustomQueryTemplate(
        id=uuid.uuid4(), name="【测试】W3 跨项目参数模板", data_source="ledger_entries", scope="public",
        config={"project_id": str(hp), "source": "ledger_entries", "conditions": [{
            "field": "line_amount", "op": "gte", "value": {"$param": "materiality_performance"},
        }]}, creator_id=creator, created_by=creator,
    )
    business.session.add(template)
    await business.session.flush()

    totals = {}
    for project_id in (hp, ah):
        threshold = Decimal(str((await gold.scalar(
            "SELECT performance_materiality FROM materiality WHERE project_id=:pid AND year=:year "
            "AND NOT is_deleted ORDER BY updated_at DESC LIMIT 1",
            pid=project_id, year=AUDIT_YEAR,
        ))))
        expected = int(await gold.scalar(
            f"SELECT count(*) FROM tb_ledger t WHERE {ACTIVE} AND "
            "GREATEST(COALESCE(t.debit_amount,0),COALESCE(t.credit_amount,0)) >= :threshold",
            pid=project_id, year=AUDIT_YEAR, threshold=threshold,
        ))
        response = await business.http.post(
            f"{CQ}/templates/{template.id}/execute",
            json={"project_id": str(project_id), "year": AUDIT_YEAR, "limit": 100},
        )
        assert response.status_code == 200, response.text[:800]
        assert response.json()["total"] == expected
        totals[str(project_id)] = expected
    assert len(set(totals.values())) == 2, "两个项目应按各自阈值解析，而不是沿用保存时的字面值"

    missing = await business.http.post(
        f"{CQ}/templates/{template.id}/execute",
        json={"project_id": str(yb), "year": AUDIT_YEAR, "limit": 100},
    )
    assert missing.status_code == 400, missing.text
    assert missing.json()["detail"]["error_code"] == "CONDITION_VALUE_REQUIRED"
    assert "未设置重要性水平" in missing.json()["detail"]["message"]
