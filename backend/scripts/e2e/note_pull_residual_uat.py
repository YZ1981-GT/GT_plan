#!/usr/bin/env python
"""合并附注拉数可逆 UAT 工具。

默认 ``plan`` 只读。数据库写入仅 ``inject`` / ``restore``，且必须同时提供
``--apply --project --year --confirm-project-name``。token 只从 ``GT_UAT_TOKEN`` 读取，
不写备份和日志。备份覆盖映射五表、合并附注数据、公式及两家叶子来源附注。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402

_DB_HOST = os.environ.get("GT_UAT_DB_HOST", "127.0.0.1")
_DATABASE_URL = str(settings.DATABASE_URL)
_DATABASE_URL = _DATABASE_URL.replace("@localhost", f"@{_DB_HOST}")
_DATABASE_URL = _DATABASE_URL.replace("@127.0.0.1", f"@{_DB_HOST}")
async_engine = create_async_engine(_DATABASE_URL, poolclass=NullPool)

FORMAT = "note-pull-residual-uat/v1"
TOKEN_ENV = "GT_UAT_TOKEN"
API_BASE = "http://127.0.0.1:9980"
TEST_MARK = "【测试】"
DETAIL_SECTION = "五-5-6"
TOPN_SECTION = "五-8-18"
TOPN_DENOMINATOR = "五-8-6"
SOURCE_SECTIONS = ("五、5", "五、8")
DETAIL_TABLE = "组合计提项目：应收中央企业客户"
TOPN_TABLE = "按欠款方归集的其他应收款期末余额前五名单位情况"
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True)
class Scope:
    table: str
    where: str
    params: dict[str, Any]


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"$decimal": format(value, "f")}
    raise TypeError(type(value).__name__)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _parsed(raw: str) -> Any:
    return json.loads(raw, parse_float=Decimal)


def table_digest(table: str, scope: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    normalized = [
        {"row": _parsed(item["row"]), "json_null": sorted(item.get("json_null") or [])}
        for item in rows
    ]
    return digest({"schema_version": 1, "table": table, "scope": scope, "rows": normalized})


def _safe_table(name: str) -> str:
    if not _IDENT.fullmatch(name):
        raise ValueError(f"非法表名：{name}")
    return name


def _write_verified(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    if path.read_text(encoding="utf-8") != raw:
        raise RuntimeError("备份写后复读不一致")


def _load_backup(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError("备份格式不支持")
    return data


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload and payload.get("code") in (0, 200):
        return payload["data"]
    return payload


def api_get(path: str, token: str, api_base: str) -> Any:
    request = urllib.request.Request(
        api_base.rstrip("/") + path,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return _unwrap(json.loads(response.read().decode("utf-8")))


def _tree_nodes(node: Any):
    if not isinstance(node, dict):
        return
    yield node
    for child in node.get("children") or []:
        yield from _tree_nodes(child)


def tree_facts(project_id: str, token: str, api_base: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"project_id": project_id})
    tree = api_get(f"/api/consolidation/worksheet/tree?{query}", token, api_base)
    root = tree.get("tree") if isinstance(tree, dict) and isinstance(tree.get("tree"), dict) else tree
    if not isinstance(root, dict) or root.get("role") != "consol":
        raise RuntimeError("企业树根不是 consol，拒绝继续")
    leaves = [
        {
            "node_key": str(node.get("node_key")),
            "project_id": str(node.get("project_id")),
            "company_name": str(node.get("company_name") or node.get("name") or ""),
        }
        for node in _tree_nodes(root)
        if node.get("kind") == "data" and not (node.get("children") or []) and node.get("project_id")
    ]
    if len(leaves) < 2:
        raise RuntimeError(f"企业树只有 {len(leaves)} 个数据叶子，拒绝继续")
    return {
        "root_node_key": str(root.get("node_key")),
        "leaves": leaves,
        "tree_hash": digest(root),
    }
async def _jsonb_columns(conn: AsyncConnection, table: str) -> list[str]:
    rows = (await conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:table AND udt_name='jsonb'
        ORDER BY ordinal_position
    """), {"table": table})).scalars().all()
    return [str(row) for row in rows]


async def _columns(conn: AsyncConnection, table: str) -> list[str]:
    rows = (await conn.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:table
          AND is_generated='NEVER' AND is_identity='NO'
        ORDER BY ordinal_position
    """), {"table": table})).scalars().all()
    return [str(row) for row in rows]


async def export_scope(conn: AsyncConnection, scope: Scope) -> dict[str, Any]:
    table = _safe_table(scope.table)
    json_cols = await _jsonb_columns(conn, table)
    flags = ", ".join(
        f"CASE WHEN q.\"{column}\" IS NOT NULL AND jsonb_typeof(q.\"{column}\")='null' "
        f"THEN '{column}' END"
        for column in json_cols
    ) or "NULL::text"
    sql = text(
        f"SELECT row_to_json(q)::text AS row_json, "
        f"array_remove(ARRAY[{flags}]::text[], NULL) AS json_null "
        f"FROM (SELECT * FROM public.{table} WHERE {scope.where}) q ORDER BY q.id::text"
    )
    result = await conn.execute(sql, scope.params)
    rows = [{"row": row.row_json, "json_null": list(row.json_null or [])} for row in result]
    public_scope = {key: value for key, value in scope.params.items()}
    return {
        "pk": ["id"],
        "scope": public_scope,
        "count": len(rows),
        "rows": rows,
        "before_hash": table_digest(table, public_scope, rows),
    }


def scopes(target: dict[str, Any]) -> list[Scope]:
    project_id = target["project_id"]
    year = int(target["year"])
    template_type = target["template_type"]
    sections = [target["detail_section"], target["topn_section"]]
    leaves = [leaf["project_id"] for leaf in target["leaves"]]
    common = {"project_id": project_id}
    return [
        Scope("consol_note_data", "project_id=CAST(:project_id AS uuid) AND year=:year", {**common, "year": year}),
        Scope("consol_note_mapping_binding", "project_id=CAST(:project_id AS uuid)", common),
        Scope("consol_note_template_binding", "project_id=CAST(:project_id AS uuid)", common),
        Scope("consol_note_mapping_rule", "project_id=CAST(:project_id AS uuid)", common),
        Scope("consol_note_detail_template_version", "template_id IN (SELECT id FROM public.consol_note_detail_template WHERE template_type=:template_type AND section_id=ANY(CAST(:sections AS text[])))", {"template_type": template_type, "sections": sections}),
        Scope("consol_note_detail_template", "template_type=:template_type AND section_id=ANY(CAST(:sections AS text[]))", {"template_type": template_type, "sections": sections}),
        Scope("consol_note_formula", "template_type=:template_type", {"template_type": template_type}),
        Scope("disclosure_notes", "project_id=ANY(CAST(:leaf_ids AS uuid[])) AND year=:year AND note_section=ANY(CAST(:source_sections AS text[]))", {"leaf_ids": leaves, "year": year, "source_sections": list(SOURCE_SECTIONS)}),
    ]


async def project_facts(conn: AsyncConnection, project_id: str, year: int, confirmed_name: str | None) -> dict[str, Any]:
    row = (await conn.execute(text("""
        SELECT id::text, name, audit_year, template_type, report_scope,
               status::text, consol_lock, is_deleted
        FROM projects WHERE id=CAST(:project_id AS uuid)
    """), {"project_id": project_id})).mappings().one_or_none()
    if row is None:
        raise RuntimeError("项目不存在")
    facts = dict(row)
    name = str(facts.get("name") or "")
    if TEST_MARK not in name:
        raise RuntimeError("项目名称不含【测试】，拒绝继续")
    if confirmed_name is not None and name != confirmed_name:
        raise RuntimeError("--confirm-project-name 与数据库项目名不一致")
    if int(facts.get("audit_year") or 0) != year:
        raise RuntimeError("审计年度不一致")
    if facts.get("template_type") != "listed" or facts.get("report_scope") != "consolidated":
        raise RuntimeError("本 UAT 只允许 listed consolidated 测试集团")
    if facts.get("is_deleted") or facts.get("status") == "archived" or facts.get("consol_lock"):
        raise RuntimeError("项目已删除、已归档或已锁定")
    return facts


async def database_fingerprint(conn: AsyncConnection) -> dict[str, str]:
    row = (await conn.execute(text("SELECT current_database() AS db, current_schema() AS schema"))).mappings().one()
    return {"database": row["db"], "schema": row["schema"], "fingerprint": digest(dict(row))}


async def snapshot(args: argparse.Namespace) -> None:
    token = os.environ.get(TOKEN_ENV, "")
    if not token:
        raise RuntimeError(f"snapshot 需要环境变量 {TOKEN_ENV}")
    tree = tree_facts(args.project, token, args.api_base)
    async with async_engine.connect() as conn:
        project = await project_facts(conn, args.project, args.year, args.confirm_project_name)
        database = await database_fingerprint(conn)
        target = {
            "project_id": args.project,
            "project_name": project["name"],
            "year": args.year,
            "template_type": project["template_type"],
            "root_node_key": tree["root_node_key"],
            "tree_hash": tree["tree_hash"],
            "leaves": tree["leaves"],
            "detail_section": DETAIL_SECTION,
            "topn_section": TOPN_SECTION,
            "topn_denominator": TOPN_DENOMINATOR,
        }
        tables = {scope.table: await export_scope(conn, scope) for scope in scopes(target)}
    payload = {
        "format": FORMAT,
        "run_id": args.run_id or uuid.uuid4().hex[:12],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": database,
        "target": target,
        "tables": tables,
        "after_hashes": None,
        "restored": False,
    }
    _write_verified(args.backup, payload)
    print(f"已写入 UAT 备份：{args.backup}")
    print("before：" + " / ".join(f"{name}={item['count']}:{item['before_hash'][:10]}" for name, item in tables.items()))
async def _current_exports(conn: AsyncConnection, backup: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {scope.table: await export_scope(conn, scope) for scope in scopes(backup["target"])}


def _assert_hashes(exports: dict[str, dict[str, Any]], expected: dict[str, str], stage: str) -> None:
    bad = [name for name, item in exports.items() if item["before_hash"] != expected.get(name)]
    if bad:
        raise RuntimeError(f"{stage} 哈希漂移，拒绝覆盖：{bad}")


async def _advisory_lock(conn: AsyncConnection, target: dict[str, Any]) -> None:
    await conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {
        "key": f"consol_push:{target['project_id']}:{target['year']}"
    })


def _replace_table(table_data: dict[str, Any] | None, table: dict[str, Any]) -> dict[str, Any]:
    data = dict(table_data or {})
    tables = [dict(item) for item in data.get("_tables") or [] if isinstance(item, dict)]
    replaced = False
    for index, item in enumerate(tables):
        if item.get("name") == table["name"]:
            tables[index] = table
            replaced = True
            break
    if not replaced:
        tables.append(table)
    data["_tables"] = tables
    if data.get("name") == table["name"] or not data.get("name"):
        data.update(table)
    return data


def _detail_fixture(multiplier: int) -> dict[str, Any]:
    labels = ["1年以内", "1-2年", "2-3年", "3-4年", "4-5年", "5年以上"]
    rows = [
        {"label": label, "values": [multiplier * (index + 1) * 100, 0, 0, multiplier * (index + 1) * 80, 0, 0], "row_type": "data"}
        for index, label in enumerate(labels)
    ]
    rows.append({"label": "合  计", "values": [sum(r["values"][0] for r in rows), 0, 0, sum(r["values"][3] for r in rows), 0, 0], "row_type": "total", "is_total": True})
    return {
        "name": DETAIL_TABLE,
        "headers": ["账龄", "应收账款", "坏账准备", "预期信用损失率(%)", "应收账款", "坏账准备", "预期信用损失率(%)"],
        "columns": [
            {"key": "label", "label": "账龄", "is_label": True},
            {"key": "end_amount", "label": "应收账款", "group": "期末余额", "format": "amount"},
            {"key": "end_provision", "label": "坏账准备", "group": "期末余额", "format": "amount"},
            {"key": "end_loss_rate", "label": "预期信用损失率(%)", "group": "期末余额", "format": "percent"},
            {"key": "prior_amount", "label": "应收账款", "group": "上年年末余额", "format": "amount"},
            {"key": "prior_provision", "label": "坏账准备", "group": "上年年末余额", "format": "amount"},
            {"key": "prior_loss_rate", "label": "预期信用损失率(%)", "group": "上年年末余额", "format": "percent"},
        ],
        "rows": rows,
    }


def _topn_fixture(run_id: str, leaf_index: int, group_peer: str) -> dict[str, Any]:
    shared = f"NRG-{run_id}-共同客户" if leaf_index == 0 else f"NRG-{run_id}-共同 客户"
    names = [shared, group_peer] + [f"NRG-{run_id}-{leaf_index}-{index}" for index in range(1, 5)]
    amounts = ([600, 9999, 500, 400, 300, 200] if leaf_index == 0 else [700, 9999, 900, 800, 700, 600])
    rows = [
        {"label": name, "values": ["往来款", amount, "1年以内", "", amount / 10], "row_type": "data"}
        for name, amount in zip(names, amounts)
    ]
    rows.append({"label": "合  计", "values": ["", sum(amounts), "", "", sum(amounts) / 10], "row_type": "total", "is_total": True})
    return {
        "name": TOPN_TABLE,
        "headers": ["单位名称", "款项性质", "其他应收款期末余额", "账龄", "占其他应收款期末余额合计数的比例(%)", "坏账准备期末余额"],
        "columns": [
            {"key": "label", "label": "单位名称", "is_label": True, "flat": True},
            {"key": "nature", "label": "款项性质", "format": "text"},
            {"key": "end_amount", "label": "其他应收款期末余额", "format": "amount"},
            {"key": "aging", "label": "账龄", "format": "text"},
            {"key": "ratio", "label": "占其他应收款期末余额合计数的比例(%)", "format": "percent"},
            {"key": "provision", "label": "坏账准备期末余额", "format": "amount"},
        ],
        "rows": rows,
    }


async def _put_source_note(conn: AsyncConnection, *, project_id: str, year: int, section: str,
                           title: str, table_data: dict[str, Any]) -> None:
    existing = (await conn.execute(text("""
        SELECT id::text, table_data, is_deleted FROM disclosure_notes
        WHERE project_id=CAST(:project_id AS uuid) AND year=:year AND note_section=:section
        ORDER BY is_deleted, id LIMIT 1
    """), {"project_id": project_id, "year": year, "section": section})).mappings().one_or_none()
    if existing is not None and existing["is_deleted"]:
        raise RuntimeError(f"叶子 {project_id} 的 {section} 只有软删行，拒绝猜测复活")
    if existing is not None:
        await conn.execute(text("""
            UPDATE disclosure_notes SET table_data=CAST(:data AS jsonb), is_empty=false, updated_at=now()
            WHERE id=CAST(:id AS uuid)
        """), {"id": existing["id"], "data": json.dumps(table_data, ensure_ascii=False)})
        return
    await conn.execute(text("""
        INSERT INTO disclosure_notes
          (id, project_id, year, note_section, section_title, account_name, content_type,
           table_data, source_template, status, is_deleted, is_empty, is_stale)
        VALUES
          (CAST(:id AS uuid), CAST(:project_id AS uuid), :year, :section, :title, :title,
           'table', CAST(:data AS jsonb), 'listed', 'draft', false, false, false)
    """), {
        "id": str(uuid.uuid4()), "project_id": project_id, "year": year,
        "section": section, "title": title, "data": json.dumps(table_data, ensure_ascii=False),
    })


def _reset_after_for_new_injection(backup: dict[str, Any]) -> None:
    """旧轮次的 after/restore 状态不得被下一轮注入继承。"""
    backup["after_hashes"] = None
    backup["after_counts"] = None
    backup["restored"] = False
    backup.pop("captured_after_at", None)
    backup.pop("restored_at", None)


async def inject(args: argparse.Namespace) -> None:
    backup = _load_backup(args.backup)
    target = backup["target"]
    if args.project != target["project_id"] or args.year != target["year"]:
        raise RuntimeError("命令目标与备份目标不一致")
    leaves = target["leaves"]
    if len(leaves) != 2:
        raise RuntimeError("确定性夹具只允许恰好两个数据叶子的【测试】集团")
    async with async_engine.begin() as conn:
        await project_facts(conn, args.project, args.year, args.confirm_project_name)
        await _advisory_lock(conn, target)
        current = await _current_exports(conn, backup)
        _assert_hashes(current, {name: item["before_hash"] for name, item in backup["tables"].items()}, "注入前")
        for index, leaf in enumerate(leaves):
            pid = leaf["project_id"]
            peer = leaves[1 - index]["company_name"]
            for section, title, table in (
                ("五、5", "应收账款", _detail_fixture(index + 1)),
                ("五、8", "其他应收款", _topn_fixture(backup["run_id"], index, peer)),
            ):
                row = (await conn.execute(text("""
                    SELECT table_data FROM disclosure_notes
                    WHERE project_id=CAST(:project_id AS uuid) AND year=:year
                      AND note_section=:section AND is_deleted=false
                """), {"project_id": pid, "year": args.year, "section": section})).scalar_one_or_none()
                await _put_source_note(
                    conn, project_id=pid, year=args.year, section=section, title=title,
                    table_data=_replace_table(row if isinstance(row, dict) else None, table),
                )
        denominator = {
            "headers": ["账 龄", "期末余额", "上年年末余额"],
            "rows": [["小计", "10000", "9000"]],
            "_last_write_source": "uat_fixture",
        }
        await conn.execute(text("""
            INSERT INTO consol_note_data
              (id, project_id, year, section_id, node_key, data, is_stale, cell_state, locked_cells)
            VALUES
              (CAST(:id AS uuid), CAST(:project_id AS uuid), :year, :section, :node_key,
               CAST(:data AS jsonb), false, 'auto', '[]'::jsonb)
            ON CONFLICT (project_id, year, section_id, node_key) WHERE node_key IS NOT NULL
            DO UPDATE SET data=EXCLUDED.data, is_stale=false, cell_state='auto', locked_cells='[]'::jsonb,
                          updated_at=now()
        """), {
            "id": str(uuid.uuid4()), "project_id": args.project, "year": args.year,
            "section": target["topn_denominator"], "node_key": target["root_node_key"],
            "data": json.dumps(denominator, ensure_ascii=False),
        })
    _reset_after_for_new_injection(backup)
    backup["injection"] = {"run_id": backup["run_id"], "injected_at": datetime.now(timezone.utc).isoformat()}
    _write_verified(args.backup, backup)
    print(f"已注入确定性【测试】夹具，run_id={backup['run_id']}")


async def capture_after(args: argparse.Namespace) -> None:
    backup = _load_backup(args.backup)
    target = backup["target"]
    token = os.environ.get(TOKEN_ENV, "")
    if token:
        tree = tree_facts(target["project_id"], token, args.api_base)
        if tree["tree_hash"] != target["tree_hash"]:
            raise RuntimeError("企业树结构已变化，拒绝记录 after")
    async with async_engine.connect() as conn:
        await project_facts(conn, target["project_id"], target["year"], target["project_name"])
        current = await _current_exports(conn, backup)
    backup["after_hashes"] = {name: item["before_hash"] for name, item in current.items()}
    backup["after_counts"] = {name: item["count"] for name, item in current.items()}
    backup["captured_after_at"] = datetime.now(timezone.utc).isoformat()
    _write_verified(args.backup, backup)
    print("after：" + " / ".join(f"{name}={item['count']}:{item['before_hash'][:10]}" for name, item in current.items()))


async def _delete_scope(conn: AsyncConnection, scope: Scope) -> None:
    table = _safe_table(scope.table)
    await conn.execute(text(f"DELETE FROM public.{table} WHERE {scope.where}"), scope.params)


async def _restore_rows(conn: AsyncConnection, table: str, item: dict[str, Any]) -> None:
    if not item["rows"]:
        return
    table = _safe_table(table)
    columns = await _columns(conn, table)
    quoted = ",".join(f'"{column}"' for column in columns)
    payload = "[" + ",".join(row["row"] for row in item["rows"]) + "]"
    await conn.execute(text(
        f"INSERT INTO public.{table} ({quoted}) SELECT {quoted} "
        f"FROM json_populate_recordset(NULL::public.{table}, CAST(:payload AS json))"
    ), {"payload": payload})
    for backed in item["rows"]:
        row = json.loads(backed["row"])
        for column in backed.get("json_null") or []:
            if column not in columns:
                raise RuntimeError(f"{table}.{column} 已不存在")
            await conn.execute(text(
                f'UPDATE public.{table} SET "{column}"=\'null\'::jsonb WHERE id=CAST(:id AS uuid)'
            ), {"id": row["id"]})


async def restore(args: argparse.Namespace) -> None:
    backup = _load_backup(args.backup)
    target = backup["target"]
    if args.project != target["project_id"] or args.year != target["year"]:
        raise RuntimeError("命令目标与备份目标不一致")
    expected_after = backup.get("after_hashes")
    if not isinstance(expected_after, dict):
        raise RuntimeError("备份尚未 capture-after，拒绝恢复")
    order = scopes(target)
    by_name = {scope.table: scope for scope in order}
    delete_order = [
        "consol_note_mapping_binding", "consol_note_template_binding", "consol_note_mapping_rule",
        "consol_note_detail_template_version", "consol_note_detail_template",
        "consol_note_data", "consol_note_formula", "disclosure_notes",
    ]
    insert_order = [
        "consol_note_detail_template", "consol_note_detail_template_version", "consol_note_mapping_rule",
        "consol_note_template_binding", "consol_note_mapping_binding",
        "consol_note_formula", "disclosure_notes", "consol_note_data",
    ]
    async with async_engine.begin() as conn:
        await project_facts(conn, args.project, args.year, args.confirm_project_name)
        await _advisory_lock(conn, target)
        current = await _current_exports(conn, backup)
        _assert_hashes(current, expected_after, "恢复前")
        for name in delete_order:
            await _delete_scope(conn, by_name[name])
        for name in insert_order:
            await _restore_rows(conn, name, backup["tables"][name])
        restored = await _current_exports(conn, backup)
        _assert_hashes(restored, {name: item["before_hash"] for name, item in backup["tables"].items()}, "事务内恢复后")
    async with async_engine.connect() as conn:
        final = await _current_exports(conn, backup)
    _assert_hashes(final, {name: item["before_hash"] for name, item in backup["tables"].items()}, "提交后复核")
    backup["restored"] = True
    backup["restored_at"] = datetime.now(timezone.utc).isoformat()
    _write_verified(args.backup, backup)
    print("恢复完成：全部表主键集合与规范化整行哈希等于 before")
async def plan() -> None:
    async with async_engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT id::text, name, audit_year, template_type, report_scope, status::text, consol_lock
            FROM projects
            WHERE is_deleted=false AND strpos(coalesce(name,''), '【测试】') > 0
              AND report_scope='consolidated' AND status::text <> 'archived'
              AND consol_lock=false AND audit_year IS NOT NULL
            ORDER BY audit_year DESC, name, id
        """))).mappings().all()
    print(f"可用【测试】合并项目：{len(rows)}")
    for row in rows:
        print(f"- {row['id']} | {row['name']} | {row['audit_year']} | {row['template_type']}")


async def verify(args: argparse.Namespace) -> None:
    backup = _load_backup(args.backup)
    target = backup["target"]
    async with async_engine.connect() as conn:
        current = await _current_exports(conn, backup)
    if args.expected == "before":
        expected = {name: item["before_hash"] for name, item in backup["tables"].items()}
    else:
        expected = backup.get("after_hashes") or {}
    _assert_hashes(current, expected, f"verify-{args.expected}")
    print(f"verify-{args.expected}：全部表哈希一致")


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"参数错误：{message}\n")


def parser() -> Parser:
    p = Parser(description="合并附注拉数可逆 UAT（默认 plan 只读）")
    p.add_argument("action", nargs="?", choices=("plan", "snapshot", "inject", "capture-after", "verify", "restore"), default="plan")
    p.add_argument("--project")
    p.add_argument("--year", type=int)
    p.add_argument("--confirm-project-name")
    p.add_argument("--backup", type=Path)
    p.add_argument("--run-id")
    p.add_argument("--api-base", default=API_BASE)
    p.add_argument("--expected", choices=("before", "after"), default="before")
    p.add_argument("--apply", action="store_true")
    return p


def _validate_args(args: argparse.Namespace) -> None:
    targeted = args.action in {"snapshot", "inject", "restore"}
    if targeted and (not args.project or not args.year or not args.confirm_project_name):
        raise ValueError(f"{args.action} 必须提供 --project --year --confirm-project-name")
    if args.action != "plan" and args.backup is None:
        raise ValueError(f"{args.action} 必须提供 --backup")
    if args.action in {"inject", "restore"} and not args.apply:
        raise ValueError(f"{args.action} 会写数据库，必须显式提供 --apply")
    if args.run_id and not re.fullmatch(r"[A-Za-z0-9_-]{4,32}", args.run_id):
        raise ValueError("--run-id 只允许 4~32 位字母、数字、下划线或短横线")


async def _main(args: argparse.Namespace) -> None:
    if args.action == "plan":
        await plan()
    elif args.action == "snapshot":
        await snapshot(args)
    elif args.action == "inject":
        await inject(args)
    elif args.action == "capture-after":
        await capture_after(args)
    elif args.action == "verify":
        await verify(args)
    else:
        await restore(args)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        _validate_args(args)
        asyncio.run(_main(args))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI 必须给中文失败原因并返回非零
        print(f"UAT 工具失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
