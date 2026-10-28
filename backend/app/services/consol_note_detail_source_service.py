"""合并附注明细来源扫描、结构指纹、建议与预览 service（Phase 2 Task 8~14）。

spec: consol-note-detail-template-and-mapping

纯函数不依赖 DB 的部分放模块顶层；需要 DB 的放 async 函数。
Service 只 flush 不 commit。
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_mapping_models import (
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.report_models import DisclosureNote
from app.services.consol_note_detail_suggest import (  # 建议算法拆出；本模块重新导出以兼容原导入路径
    _label_key,
    is_auto_confirmable,
    is_placeholder_label,
    suggest_template_rows,
)
from app.services.consol_note_standalone_reader import SourceTable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 行标签提取（复用 consol_note_formula_service 口径）
# ═══════════════════════════════════════════════════════════════════════════════


def _first_cell(row: Any) -> str:
    """提取行标签——兼容 list 和 dict 两种行形态。"""
    if isinstance(row, dict):
        return str(row.get("label") or row.get("name") or "")
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "")
    return ""


def source_occurrence(row: Any, fallback: int) -> int:
    """来源行的同名出现序号：读取层带出的 ``_occurrence``（R11）；没有（旧调用方 / 测试构造的行）⇒ 调用方按顺序数的值。"""
    value = row.get("_occurrence") if isinstance(row, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else fallback


def _row_type(row: Any) -> str:
    """行类型：声明了合计 / 小计用声明，只有行名时按 ``note_total_terms.label_row_type``（以「小计」结尾 = 小计）。"""
    from app.services.note_total_terms import label_row_type

    if isinstance(row, dict):
        rt = str(row.get("row_type", "data")).strip()
        if rt in ("total", "subtotal"):
            return rt
        if rt not in ("data", ""):
            # 非标准类型（如 header）——不做标签推导，直接归为 data
            return "data"
        return label_row_type(row.get("label"))
    if isinstance(row, (list, tuple)) and row:
        return label_row_type(row[0])
    return "data"


def _row_numbers(row: Any) -> list[float]:
    """来源行里的数值（标准来源行 ``values`` 或 ``[label, v1, ...]``），跳过空 / 非数值。"""
    if isinstance(row, dict):
        raw = row.get("values")
        cells = list(raw) if isinstance(raw, (list, tuple)) else []
    elif isinstance(row, (list, tuple)):
        cells = list(row[1:])
    else:
        cells = []
    out: list[float] = []
    for v in cells:
        if v is None or isinstance(v, bool):
            continue
        try:
            out.append(float(str(v).replace(",", "")))
        except ValueError:
            continue
    return out


def _stable_key(row: Any) -> str:
    """提取稳定行键（row_id / item_id），没有则返回空串。"""
    if isinstance(row, dict):
        for key in ("row_id", "item_id", "id", "uuid"):
            val = row.get(key)
            if val and str(val).strip():
                return str(val).strip()
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 结构指纹（R2.1 / D§三）
# ═══════════════════════════════════════════════════════════════════════════════


def extract_source_rows(rows: list[Any]) -> list[dict[str, str]]:
    """从 table_data.rows 提取结构信息（不含金额）。

    返回 ``[{label, row_type, key, occurrence}]``（``occurrence`` = 同名行出现序号，从 0 起；不进结构指纹）；
    集团下推的行另带 ``_pushed_row_id``。
    """
    items: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    occurrences: dict[str, int] = {}
    for row in rows:
        label = _first_cell(row).strip()
        rt = _row_type(row)
        sk = _stable_key(row)
        if not sk:
            count = seen.get(label, 0)
            seen[label] = count + 1
            sk = f"{label}#{count}"
        occurrence = source_occurrence(row, occurrences.get(label, 0))
        occurrences[label] = occurrences.get(label, 0) + 1
        item = {"label": label, "row_type": rt, "key": sk, "occurrence": occurrence}
        pushed = row.get("_pushed_row_id") if isinstance(row, dict) else None
        if pushed:  # 集团下推的行：带行身份进指纹与建议（exact_id）
            item["_pushed_row_id"] = str(pushed)
        items.append(item)
    return items


def compute_source_structure_hash(section_id: str, rows: list[Any]) -> str:
    """计算来源结构指纹（SHA-256）。排除金额，只含标签/行类型/键。

    数据行排序后再算（行顺序不同但行名集合相同的子企业共用一条映射规则），
    合计/小计行不参与排序（位置固定）。
    """
    # 下推行身份（_pushed_row_id）只给建议做 exact_id，不进指纹：下推不改行名 / 行类型，映射照旧有效 ——
    # 进指纹的话每次「📤 下推模板」都让已确认的企业变成「结构已变化」，重新汇总跳过它（2026-10-26 浏览器实测）
    # 同名行出现序号（occurrence）同理不进指纹：它由行名与顺序决定，key 已含同名序号，加进来只会让已确认的企业全部失效
    items = [{k: v for k, v in it.items() if k not in ("_pushed_row_id", "occurrence")}
             for it in extract_source_rows(rows)]
    # 分离数据行和合计/小计行——合计行位置不参与指纹
    data_items = [it for it in items if it.get("row_type") == "data"]
    other_items = [it for it in items if it.get("row_type") != "data"]
    # 数据行按 label 排序（忽略行顺序差异）
    data_items.sort(key=lambda it: it.get("label", ""))
    sorted_items = data_items + other_items
    payload = json.dumps(
        {"section_id": section_id, "items": sorted_items},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def group_entities_by_structure(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按 source_structure_hash 分组。

    输入：``[{node_key, project_id, company_name, section_id, rows, hash}]``
    输出：``[{hash, section_id, source_rows, entities: [{node_key, project_id, company_name}]}]``
    """
    groups: dict[str, dict[str, Any]] = {}
    for entity in entities:
        h = entity["hash"]
        if h not in groups:
            groups[h] = {
                "hash": h,
                "section_id": entity["section_id"],
                "source_rows": extract_source_rows(entity["rows"]),
                "entities": [],
            }
        groups[h]["entities"].append({
            "node_key": entity["node_key"],
            "project_id": str(entity["project_id"]),
            "company_name": entity.get("company_name", ""),
        })
    return list(groups.values())


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 来源读取（R2.1 / D§五.4 preview 前置）
# ═══════════════════════════════════════════════════════════════════════════════


async def resolve_section_template_type(db: AsyncSession, consol_project_id: UUID) -> str:
    """合并项目附注模板口径（soe / listed）——章节映射与合并模板表都按它取。"""
    from app.services.consol_note_formula_service import resolve_note_template_type

    return await resolve_note_template_type(db, consol_project_id)


def standalone_note_filter(standalone_section: str, standalone_title: str) -> Any:
    """单体附注里与合并章节对应的章节：按章节号，取不到按章节标题。

    子企业附注模板可能与合并口径不同（国企集团含上市子公司：上市版货币资金是「五、1」不是「八、1」）。
    """
    conditions = [DisclosureNote.note_section == standalone_section]
    if standalone_title:
        conditions.append(DisclosureNote.section_title == standalone_title)
    return sa.or_(*conditions)


#: 同一企业命中多节时逐行喂给 ``prefer_standalone_note`` 的次序（后写覆盖先写）
_STANDALONE_NOTE_ORDER = (DisclosureNote.sort_order.desc().nullsfirst(), DisclosureNote.updated_at)


def prefer_standalone_note(held: Any, row: Any, standalone_section: str) -> Any:
    """同一企业命中多节时留哪一节：按号命中优先于按标题命中，同号以最近更新为准；同标题多节取文档里靠前的。

    拉数（``load_source_tables``）与下推（``load_standalone_note``）共用 —— 读的与写的是同一节。
    """
    if held is None or row.note_section == standalone_section or held.note_section != standalone_section:
        return row
    return held


async def load_standalone_note(
    db: AsyncSession, project_id: UUID, year: int, standalone_section: str, standalone_title: str,
) -> DisclosureNote | None:
    """一家企业单体附注里与合并章节对应的那一节（ORM 对象，下推写入用；取舍与拉数相同）。"""
    notes = (await db.execute(
        sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            standalone_note_filter(standalone_section, standalone_title),
            DisclosureNote.is_deleted == sa.false(),
        ).order_by(*_STANDALONE_NOTE_ORDER)
    )).scalars().all()
    held = None
    for note in notes:
        held = prefer_standalone_note(held, note, standalone_section)
    return held


async def load_source_tables(
    db: AsyncSession,
    project_ids: Sequence[UUID],
    section_id: str,
    year: int,
    *,
    template_type: str,
) -> dict[UUID, SourceTable]:
    """批量读取各企业单体附注里与合并章节 ``section_id`` 对应的表（一次查询）。

    合并章节号先经章节映射换成单体章节号与子表名（如 五-1-1 → 八、1「货币资金」）——
    单体附注里根本没有「五-1-1」这个章节号。读的是单体附注页面实际显示的表
    （``consol_note_standalone_reader``），按合并模板列对齐。没读到的企业带中文原因。
    """
    from app.services.consol_note_formula_service import find_table
    from app.services.consol_note_section_mapping import resolve_mapping_entry
    from app.services.consol_note_standalone_reader import read_source_table

    ids = list(dict.fromkeys(pid for pid in project_ids if pid is not None))
    if not ids:
        return {}
    entry = resolve_mapping_entry(template_type, section_id)
    standalone_section = (entry or {}).get("standalone_note_section")
    if not standalone_section:
        reason = "合并特有章节，没有对应的单体附注" if entry else f"章节映射未覆盖 {section_id}"
        return {pid: SourceTable(reason=reason, status="no_source") for pid in ids}
    standalone_title = str(entry.get("standalone_section_title") or "").strip()

    notes = (await db.execute(
        sa.select(
            DisclosureNote.project_id, DisclosureNote.note_section, DisclosureNote.table_data,
            DisclosureNote.is_empty, DisclosureNote.section_title,
        )
        .where(
            DisclosureNote.project_id.in_(ids),
            DisclosureNote.year == year,
            standalone_note_filter(standalone_section, standalone_title),
            DisclosureNote.is_deleted == sa.false(),
        )
        .order_by(*_STANDALONE_NOTE_ORDER)
    )).all()
    by_project: dict[UUID, Any] = {}
    for row in notes:
        by_project[row.project_id] = prefer_standalone_note(by_project.get(row.project_id), row, standalone_section)

    consol_table = find_table(template_type, section_id)
    out: dict[UUID, SourceTable] = {}
    for pid in ids:
        note = by_project.get(pid)
        if note is None:
            out[pid] = SourceTable(reason=f"单体附注未生成章节 {standalone_section}", status="missing")
        elif note.is_empty:
            out[pid] = SourceTable(reason=f"单体附注 {standalone_section} 标为本期无此情形", status="not_applicable")
        else:
            out[pid] = read_source_table(
                note.table_data,
                consol_table=consol_table,
                table_name=entry.get("standalone_table_name"),
                title=entry.get("consol_title"),
                section_title=note.section_title,
                std=template_type,
                consol_section_id=section_id,
                standalone_section=note.note_section,
            )
    return out


async def scan_all_entities(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    year: int,
    template_type: str | None = None,
    tree: Any = None,
) -> list[dict[str, Any]]:
    """扫描企业树全部数据叶子的来源，返回含 hash 与读取状态的实体列表（``tree`` 传入已建好的企业树可省一次重建）。

    没读到来源行的企业（未生成 / 本期无此情形 / 读不出表）``rows`` 为空，由调用方
    决定是否参与分组；读取状态在 ``source_status``。
    """
    from app.services.consol_calc_basis import data_leaves
    from app.services.consol_tree_service import build_tree

    if tree is None:
        tree = await build_tree(db, consol_project_id)
    if tree is None:
        return []
    if template_type is None:
        template_type = await resolve_section_template_type(db, consol_project_id)

    leaves = [leaf for leaf in data_leaves(tree) if leaf.project_id is not None]
    sources = await load_source_tables(
        db, [leaf.project_id for leaf in leaves], section_id, year, template_type=template_type,
    )
    entities: list[dict[str, Any]] = []
    for leaf in leaves:
        source = sources.get(leaf.project_id)
        rows = source.rows if source is not None else []
        entities.append({
            "node_key": leaf.node_key,
            "project_id": leaf.project_id,
            "company_name": getattr(leaf, "company_name", "") or "",
            "section_id": section_id,
            "rows": rows,
            "hash": compute_source_structure_hash(section_id, rows),
            "source_status": source.to_status() if source is not None else {"status": "missing"},
        })
    return entities


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Preview（R4.1 / D§四）
# ═══════════════════════════════════════════════════════════════════════════════


async def preview_detail_refresh(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    year: int,
    tree: Any = None,
) -> dict[str, Any]:
    """预览明细刷新——只读，不写数据，生成 preview_token。

    返回 ``{preview_token, section_id, year, groups, stale_entities, suggestions, template_binding}``
    """
    # 1. 扫描来源（只有读到来源行的企业参与分组与映射；其余在 entity_sources 里说明原因）
    scanned = await scan_all_entities(
        db, consol_project_id=project_id, section_id=section_id, year=year, tree=tree,
    )
    entities = [e for e in scanned if e["rows"]]
    entity_sources = _entity_source_report(scanned)
    groups = group_entities_by_structure(entities)

    # 2. 读取当前模板绑定
    binding = (await db.execute(
        sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == project_id,
            ConsolNoteTemplateBinding.section_id == section_id,
        )
    )).scalar_one_or_none()

    template_version_id: str | None = None
    template_rows: list[dict[str, Any]] = []
    if binding is not None:
        template_version_id = str(binding.template_version_id)
        from app.models.consol_note_mapping_models import ConsolNoteDetailTemplateVersion
        version = (await db.execute(
            sa.select(ConsolNoteDetailTemplateVersion).where(
                ConsolNoteDetailTemplateVersion.id == binding.template_version_id,
            )
        )).scalar_one_or_none()
        if version is not None and isinstance(version.rows, list):
            template_rows = version.rows

    # 3. 检测 stale 绑定（只读——标记在返回值中，不写数据库；实际 stale 标记在 confirm/apply 阶段）
    bindings_by_key = {
        b.entity_node_key: b
        for b in (await db.execute(
            sa.select(ConsolNoteMappingBinding).where(
                ConsolNoteMappingBinding.project_id == project_id,
                ConsolNoteMappingBinding.section_id == section_id,
            )
        )).scalars().all()
    }
    stale_entities: list[dict[str, Any]] = []
    for entity in entities:
        existing_binding = bindings_by_key.get(entity["node_key"])
        if existing_binding is not None:
            if existing_binding.bound_source_hash != entity["hash"]:
                stale_entities.append({
                    "node_key": entity["node_key"],
                    "company_name": entity.get("company_name", ""),
                    "old_hash": existing_binding.bound_source_hash,
                    "new_hash": entity["hash"],
                    "status": "stale",
                })

    # 4. 读取历史映射
    history: list[dict[str, Any]] = []
    rules: list[Any] = []
    if template_version_id:
        rules = (await db.execute(
            sa.select(ConsolNoteMappingRule).where(
                ConsolNoteMappingRule.project_id == project_id,
                ConsolNoteMappingRule.section_id == section_id,
                ConsolNoteMappingRule.is_active == sa.true(),
            )
        )).scalars().all()
        for rule in rules:
            for m in (rule.mappings if isinstance(rule.mappings, list) else []):
                history.append(m)

    # 5. 生成建议
    suggestions = suggest_template_rows(
        groups,
        existing_template_rows=template_rows,
        history_mappings=history,
    )

    # 5.5 标记可自动确认的建议（下推行 / 精确 / 别名 / 通用别名 / 历史，且有目标行）；其余都要人工看一眼
    for s in suggestions:
        s["auto_confirmable"] = is_auto_confirmable(s)
    auto_confirmable_count = sum(1 for s in suggestions if s["auto_confirmable"])
    needs_review_count = len(suggestions) - auto_confirmable_count

    # 6. 为每组标注映射状态
    for group in groups:
        group_hash = group["hash"]
        # 查找该组是否已有规则
        existing_rule = None
        for rule in (rules if template_version_id else []):
            if rule.source_structure_hash == group_hash:
                existing_rule = rule
                break
        group["has_rule"] = existing_rule is not None
        group["rule_id"] = str(existing_rule.id) if existing_rule else None
        # 所有企业都已确认且非 stale？
        stale_keys = {se["node_key"] for se in stale_entities}
        group["all_confirmed"] = (
            existing_rule is not None
            and all(e["node_key"] not in stale_keys for e in group["entities"])
        )

    # 7. 生成 preview_token
    token_data = {
        "project_id": str(project_id),
        "section_id": section_id,
        "year": year,
        "entity_hashes": {e["node_key"]: e["hash"] for e in entities},
        "template_version_id": template_version_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    preview_token = hashlib.sha256(
        json.dumps(token_data, sort_keys=True).encode()
    ).hexdigest()[:32] + secrets.token_hex(8)

    return {
        "preview_token": preview_token,
        "project_id": str(project_id),
        "section_id": section_id,
        "year": year,
        "template_version_id": template_version_id,
        "template_rows": template_rows,
        "groups": groups,
        "stale_entities": stale_entities,
        "suggestions": suggestions,
        "auto_confirmable_count": auto_confirmable_count,
        "needs_review_count": needs_review_count,
        "entity_count": len(entities),
        "group_count": len(groups),
        "stale_count": len(stale_entities),
        # 每家企业的来源读取状态（含未参与映射的企业及原因、未对上的列）
        "entity_sources": entity_sources,
        "missing_count": sum(1 for s in entity_sources if s["status"] != "found"),
        # 存 token_data 供 apply 校验
        "_token_data": token_data,
    }


def _entity_source_report(scanned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """扫描结果 → 前端可读的逐企业来源状态。"""
    return [
        {
            "node_key": e["node_key"],
            "project_id": str(e["project_id"]),
            "company_name": e.get("company_name", ""),
            **(e.get("source_status") or {"status": "missing"}),
        }
        for e in scanned
    ]


async def suggest_template_for_section(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    year: int,
    tree: Any = None,
) -> dict[str, Any]:
    """模板行建议：以合并附注模板该表的行（顺序 / 行类型）为骨架，标出每行在子企业来源里
    出现的频率与金额；来源里有而模板没有的明细行按来源出现顺序替换模板的「……」占位行（没有占位行插在
    首个合计行之前），全局别名库认得的写法并进模板行别名。

    明细模板与合并附注模板同行序，「按公式填入」与明细映射写的才是同一批行。
    合并模板缺该表时退回按来源频率排序。
    """
    from app.services.consol_note_formula_service import find_table

    template_type = await resolve_section_template_type(db, project_id)
    scanned = await scan_all_entities(
        db, consol_project_id=project_id, section_id=section_id, year=year,
        template_type=template_type, tree=tree,
    )
    entities = [e for e in scanned if e["rows"]]
    groups = group_entities_by_structure(entities)

    # 统计来源行标签出现频率和金额（按规范化标签合并，展示取首次出现的写法）
    label_stats: dict[str, dict[str, Any]] = {}
    for entity in entities:
        for row in entity["rows"]:
            label = _first_cell(row).strip()
            key = _label_key(label)
            if not key:
                continue
            stats = label_stats.setdefault(
                key, {"label": label, "count": 0, "row_type": _row_type(row), "total_amount": 0.0},
            )
            stats["count"] += 1
            stats["total_amount"] += sum(abs(float(v)) for v in _row_numbers(row))

    skeleton: list[dict[str, Any]] = []
    table = find_table(template_type, section_id) or {}
    row_types = table.get("_row_types") or []
    for i, trow in enumerate(table.get("rows") or []):
        label = _first_cell(trow).strip()
        key = _label_key(label)
        if not key:
            continue
        declared = row_types[i] if i < len(row_types) else ""
        rt = declared if declared in ("total", "subtotal") else _row_type([label])
        stats = label_stats.get(key)
        canonical = key if key in ("合计", "小计") else label
        skeleton.append({
            "canonical_name": canonical,
            "aliases": [stats["label"]] if stats and stats["label"] != canonical else [],
            "row_type": rt,
            "origin": "template",
            "_key": key,
            # 「……」可扩位占位：动态行区（下推不写进子企业附注；有来源独有行时由它们替换）
            **({"category": "dynamic_zone"} if is_placeholder_label(label) else {}),
        })

    template_keys = {r["_key"] for r in skeleton}
    # 全局别名库认得的写法（「现金」→「库存现金」）并进模板行别名，不单列一行（否则合并附注两行各算一半）
    from app.services.consol_note_detail_suggest import _load_global_aliases

    variants = _load_global_aliases()
    by_key = {r["_key"]: r for r in skeleton}
    for key, stats in label_stats.items():
        target = by_key.get(variants.get(key, "")) if key not in template_keys else None
        if target is not None:
            if stats["label"] not in target["aliases"]:
                target["aliases"].append(stats["label"])
            template_keys.add(key)
    extras = [
        {
            "canonical_name": stats["label"],
            "aliases": [],
            "row_type": stats["row_type"],
            "origin": "source",
            "_key": key,
        }
        for key, stats in label_stats.items()  # 来源出现顺序（企业树先序、表内行序）
        if key not in template_keys and stats["row_type"] == "data"
    ]
    holder = next((i for i, r in enumerate(skeleton) if r.get("category") == "dynamic_zone"), None) if extras else None
    if holder is not None:  # 来源独有的明细行替换模板的「……」占位行（模板的意思是「此处按实际列示」）
        ordered = skeleton[:holder] + extras + skeleton[holder + 1:]
    elif skeleton:
        cut = next((i for i, r in enumerate(skeleton) if r["row_type"] == "total"), len(skeleton))
        ordered = skeleton[:cut] + extras + skeleton[cut:]
    else:  # 合并模板缺该表：按来源频率，合计行放最后
        ordered = extras + [
            {"canonical_name": s["label"], "aliases": [], "row_type": s["row_type"], "origin": "source", "_key": k}
            for k, s in label_stats.items() if s["row_type"] != "data"
        ]

    suggested_rows: list[dict[str, Any]] = []
    for i, r in enumerate(ordered):
        stats = label_stats.get(r.pop("_key"))
        suggested_rows.append({
            **r,
            "sort_order": i * 10,
            "frequency": stats["count"] if stats else 0,
            "total_amount": round(stats["total_amount"], 2) if stats else 0.0,
            "entity_total": len(entities),
        })

    return {
        "section_id": section_id,
        "entity_count": len(entities),
        "group_count": len(groups),
        "suggested_rows": suggested_rows,
        "entity_sources": _entity_source_report(scanned),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 上年同集团项目映射匹配（V200 spec: consol-note-mapping-reuse-and-reference-push）
# ═══════════════════════════════════════════════════════════════════════════════


async def find_previous_year_rules(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    source_structure_hash: str,
) -> list[dict[str, Any]]:
    """查找同集团上年项目的确认过的映射规则。

    ⚠ projects 表无 client_id 字段，按双条件定位同集团：
    1. 主条件：projects.client_name 精确匹配（同一审计客户名称相同）
    2. 辅条件：projects.ultimate_company_code 非空且一致（最终控制方代码）
    两个条件取 OR。

    步骤：
    1. 读当前项目的 client_name + ultimate_company_code
    2. 查满足双条件的其他合并项目，按 audit_period_end DESC 排序
    3. 在上年项目中查 section_id + source_structure_hash 匹配的 active rule

    返回 ``[{source_label, suggested_target, confidence, match_type}]``
    格式与 suggest_template_rows 的 suggestions 兼容，可直接传入 previous_year_suggestions。
    """
    from app.models.core import Project
    from app.models.consol_note_mapping_models import ConsolNoteMappingRule

    # 1. 读当前项目信息
    current = (await db.execute(
        sa.select(Project.client_name, Project.ultimate_company_code).where(
            Project.id == consol_project_id
        )
    )).one_or_none()
    if current is None:
        return []

    client_name, ultimate_code = current.client_name, current.ultimate_company_code

    # 2. 查同集团其他合并项目
    conditions = [
        Project.id != consol_project_id,
        Project.is_deleted == sa.false(),
    ]
    # 双条件 OR：client_name 或 ultimate_company_code
    or_clauses = [Project.client_name == client_name]
    if ultimate_code:
        or_clauses.append(
            sa.and_(
                Project.ultimate_company_code.isnot(None),
                Project.ultimate_company_code == ultimate_code,
            )
        )
    conditions.append(sa.or_(*or_clauses))

    peer_projects = (await db.execute(
        sa.select(Project.id).where(*conditions)
        .order_by(Project.audit_period_end.desc().nullslast())
        .limit(10)  # 性能限制：只查最近 10 个项目
    )).scalars().all()

    if not peer_projects:
        return []

    # 3. 查上年项目中匹配的 active rule
    rules = (await db.execute(
        sa.select(ConsolNoteMappingRule).where(
            ConsolNoteMappingRule.project_id.in_(peer_projects),
            ConsolNoteMappingRule.section_id == section_id,
            ConsolNoteMappingRule.source_structure_hash == source_structure_hash,
            ConsolNoteMappingRule.is_active == sa.true(),
        ).order_by(ConsolNoteMappingRule.confirmed_at.desc().nullslast())
        .limit(1)
    )).scalars().all()

    if not rules:
        return []

    rule = rules[0]
    mappings = rule.mappings if isinstance(rule.mappings, list) else []

    # 转换为 suggestions 格式
    suggestions: list[dict[str, Any]] = []
    for m in mappings:
        sl = str(m.get("source_label", "")).strip()
        target_row_id = m.get("target_row_id")
        if not sl or not target_row_id:
            continue
        if m.get("mapping_action") == "ignore":
            continue
        suggestions.append({
            "source_label": sl,
            "suggested_target": {
                "target_row_id": target_row_id,
                "canonical_name": m.get("canonical_name"),
            },
            "confidence": 0.88,
            "match_type": "previous_year",
            "candidates": [],
        })

    return suggestions
