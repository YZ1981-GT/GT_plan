"""A9-1 向管理层通报内部控制缺陷沟通函 — 专属渲染策略.

component_type = "a9-1-deficiency-letter"
7 区块组件（收件人/正文引言/独立性声明/内部控制缺陷/审计委员会监督/签发区/管理层回复区）。
核心价值：与 B22B 内控缺陷评价表联动，按 severity 自动分组。
数据持久化在 checklist_responses 表，item_id 前缀 `a91-`。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

import sqlalchemy as sa

from ._context import RenderContext

logger = logging.getLogger(__name__)


@dataclass
class DeficiencyItem:
    """缺陷条目数据结构."""

    id: str
    description: str
    impact: str
    recommendation: str
    index_ref: str | None
    source: str  # "b22b" | "manual"
    severity: str  # "major" | "significant" | "general"


async def _load_section_data(
    ctx: RenderContext, prefix: str = "a91"
) -> tuple[dict, dict[str, list["DeficiencyItem"]]]:
    """加载 checklist_responses 中已保存的 section_data 和 manual_deficiencies.

    参数化 prefix 支持 A9-1 (a91) 和 A9-2 (a92) 共用。
    返回 (section_data, manual_deficiencies)。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    section_data: dict = {
        "addressee": {"client_name": "", "custom_text": None},
        "independence": {
            "team_independent": None,
            "no_relationships": None,
            "no_relationships_detail": None,
            "safeguards_taken": None,
            "non_audit_services": None,
            "non_audit_services_detail": None,
        },
        "committee": {"applicability": None, "description": None},
        "signature": {"date": None},
        "response": {
            "opinion": None,
            "conclusion": None,
            "representative": None,
            "response_date": None,
        },
    }

    manual_deficiencies: dict[str, list[DeficiencyItem]] = {
        "major": [],
        "significant": [],
        "general": [],
    }

    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                f"AND item_id LIKE '{prefix}-%'"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            item_id: str = row.item_id
            _parse_row(item_id, row, section_data, manual_deficiencies, prefix)
    except Exception as e:  # noqa: BLE001
        logger.warning("%s checklist_responses 查询失败 wp_id=%s: %s", prefix.upper(), wp_id, e)

    return section_data, manual_deficiencies


async def _load_project_context(ctx: RenderContext) -> dict:
    """加载项目上下文信息（复用于 A9-1 和 A9-2）."""
    project_context: dict = {
        "client_name": "",
        "firm_name": "致同会计师事务所（特殊普通合伙）",
        "audit_report_date": None,
    }
    try:
        proj_result = await ctx.db.execute(
            sa.text(
                "SELECT client_name, audit_year FROM projects WHERE id = :pid"
            ),
            {"pid": str(ctx.project_id)},
        )
        proj_row = proj_result.fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            year = proj_row.audit_year
            if year:
                project_context["audit_report_date"] = f"{year}年12月31日"
    except Exception as e:  # noqa: BLE001
        logger.warning("project context 查询失败: %s", e)
    return project_context


async def render(ctx: RenderContext) -> dict | None:
    """A9-1 内控缺陷沟通函渲染策略.

    返回 {section_data, deficiency_list, project_context, b22b_warning}
    """
    # ─── 1. 加载 section_data + manual_deficiencies ──────────────────────
    section_data, manual_deficiencies = await _load_section_data(ctx, prefix="a91")

    # ─── 2. 从 B22B 加载缺陷数据 ────────────────────────────────────────
    b22b_result = await _load_b22b_deficiencies(ctx.project_id, ctx.db)
    b22b_deficiencies: dict[str, list] = b22b_result["deficiencies"]
    b22b_warning: str | None = b22b_result["warning"]

    # ─── 3. 合并缺陷列表（B22B + 手动） ─────────────────────────────────
    deficiency_list: dict[str, list] = {"major": [], "significant": [], "general": []}
    for severity in ("major", "significant", "general"):
        deficiency_list[severity] = (
            [asdict(d) for d in b22b_deficiencies.get(severity, [])]
            + [asdict(d) for d in manual_deficiencies.get(severity, [])]
        )

    # ─── 4. 项目上下文 ──────────────────────────────────────────────────
    project_context = await _load_project_context(ctx)

    # 自动填充收件人
    if not section_data["addressee"]["client_name"]:
        section_data["addressee"]["client_name"] = project_context["client_name"]

    return {
        "section_data": section_data,
        "deficiency_list": deficiency_list,
        "project_context": project_context,
        "b22b_warning": b22b_warning,
    }


def _parse_row(
    item_id: str,
    row,
    section_data: dict,
    manual_deficiencies: dict[str, list[DeficiencyItem]],
    prefix: str = "a91",
) -> None:
    """解析单条 checklist_response 行并填入对应结构.

    参数化 prefix 支持 a91/a92 共用。
    """
    # addressee
    if item_id == f"{prefix}-addressee-client_name":
        section_data["addressee"]["client_name"] = row.conclusion or row.remark or ""
        section_data["addressee"]["custom_text"] = row.remark or None

    # independence
    elif item_id.startswith(f"{prefix}-independence-"):
        key = item_id.removeprefix(f"{prefix}-independence-")
        if key in ("team_independent", "no_relationships", "safeguards_taken", "non_audit_services"):
            section_data["independence"][key] = row.conclusion or None
            # detail fields stored in remark
            if key == "no_relationships" and row.remark:
                section_data["independence"]["no_relationships_detail"] = row.remark
            elif key == "non_audit_services" and row.remark:
                section_data["independence"]["non_audit_services_detail"] = row.remark

    # deficiency (manual entries stored as JSON in remark)
    elif item_id.startswith(f"{prefix}-deficiency-"):
        severity = item_id.removeprefix(f"{prefix}-deficiency-")
        if severity in ("major", "significant", "general") and row.remark:
            try:
                items = json.loads(row.remark)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            manual_deficiencies[severity].append(
                                DeficiencyItem(
                                    id=item.get("id", ""),
                                    description=item.get("description", ""),
                                    impact=item.get("impact", ""),
                                    recommendation=item.get("recommendation", ""),
                                    index_ref=item.get("indexRef") or item.get("index_ref"),
                                    source="manual",
                                    severity=severity,
                                )
                            )
            except (json.JSONDecodeError, TypeError):
                logger.warning("%s deficiency JSON 解析失败 item_id=%s", prefix.upper(), item_id)

    # committee
    elif item_id == f"{prefix}-committee-applicability":
        section_data["committee"]["applicability"] = row.conclusion or None
        section_data["committee"]["description"] = row.remark or None

    # signature
    elif item_id == f"{prefix}-signature-date":
        section_data["signature"]["date"] = row.conclusion or None

    # response
    elif item_id.startswith(f"{prefix}-response-"):
        key = item_id.removeprefix(f"{prefix}-response-")
        if key in ("opinion", "conclusion", "representative"):
            section_data["response"][key] = row.remark or row.conclusion or None
        elif key == "date":
            section_data["response"]["response_date"] = row.conclusion or None


# Backward-compatible alias for tests that reference the old name
_parse_a91_row = _parse_row


# 中文严重程度 → 英文分组键（B22B / B22C 共用，保持 P5 分组等价映射）
_SEVERITY_MAP = {"重大缺陷": "major", "重要缺陷": "significant", "一般缺陷": "general"}

# B22C 5 个要素区块 key → 中文区块名（用于 index_ref 定位）
_B22C_BLOCK_KEYS = ("env", "risk", "info", "monitor", "itgc")
_B22C_BLOCK_NAMES = {
    "env": "控制环境",
    "risk": "风险评估过程",
    "info": "信息与沟通",
    "monitor": "监督",
    "itgc": "IT一般控制",
}


async def _load_b22c_deficiencies(project_id, db) -> dict[str, list["DeficiencyItem"]]:
    """从 B22C 底稿（设计有效性评价·缺陷汇总表）读取缺陷 + 严重程度并分组.

    B22C 为缺陷严重程度的**单一真源**（Wave3 收敛）。
    持久化结构（前端 useB22CDesignEffectiveness.buildItems）：
      B22C-{key}-def-count           remark=该区块缺陷条目数
      B22C-{key}-def-{n}-desc        remark=缺陷描述
      B22C-{key}-def-{n}-severity    conclusion=重大缺陷/重要缺陷/一般缺陷
      B22C-{key}-def-{n}-flags       remark=JSON {cd, sig}
      B22C-{key}-def-{n}-judgment    remark=重要职业判断
    其中 key ∈ {env, risk, info, monitor, itgc}。

    severity 中文经 _SEVERITY_MAP 映射 major/significant/general（与 B22B 同一映射，保持 P5 等价）。
    返回按严重程度分组的 DeficiencyItem 列表（无数据时三组均空）。
    """
    grouped: dict[str, list[DeficiencyItem]] = {"major": [], "significant": [], "general": []}

    # 1. 找同项目 B22C 底稿
    try:
        b22c_result = await db.execute(
            sa.text(
                "SELECT wp.id AS wp_id "
                "FROM wp_index wi "
                "JOIN working_paper wp ON wp.wp_index_id = wi.id "
                "WHERE wi.wp_code = 'B22C' AND wp.project_id = :project_id "
                "LIMIT 1"
            ),
            {"project_id": str(project_id)},
        )
        b22c_row = b22c_result.fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("A9 B22C 底稿查询失败 project_id=%s: %s", project_id, e)
        return grouped

    if not b22c_row:
        return grouped

    # 2. 读取 B22C checklist_responses
    try:
        cr_result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'B22C-%'"
            ),
            {"wp_id": str(b22c_row.wp_id)},
        )
        by_id: dict[str, tuple] = {
            row.item_id: (row.conclusion, row.remark) for row in cr_result.fetchall()
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("A9 B22C checklist_responses 查询失败: %s", e)
        return grouped

    # 3. 逐区块逐条重建缺陷
    for key in _B22C_BLOCK_KEYS:
        count_raw = (by_id.get(f"B22C-{key}-def-count") or (None, "0"))[1] or "0"
        try:
            count = int(count_raw)
        except (TypeError, ValueError):
            count = 0

        for n in range(1, count + 1):
            desc = (by_id.get(f"B22C-{key}-def-{n}-desc") or (None, None))[1] or ""
            desc = desc.strip()
            if not desc:
                continue  # 空占位条目不计入缺陷函

            sev_cn = (by_id.get(f"B22C-{key}-def-{n}-severity") or (None, None))[0]
            severity = _SEVERITY_MAP.get(sev_cn or "", None)
            if severity is None:
                # 未评定严重程度：回退按 flags.sig 判定（值得关注→significant，否则→general）
                sig = False
                flags_raw = (by_id.get(f"B22C-{key}-def-{n}-flags") or (None, None))[1]
                if flags_raw:
                    try:
                        flags = json.loads(flags_raw)
                        sig = bool(flags.get("sig"))
                    except (json.JSONDecodeError, TypeError):
                        sig = False
                severity = "significant" if sig else "general"

            judgment = (by_id.get(f"B22C-{key}-def-{n}-judgment") or (None, None))[1] or ""
            block_name = _B22C_BLOCK_NAMES[key]

            grouped[severity].append(
                DeficiencyItem(
                    id=f"b22c-{key}-{n}",
                    description=desc,
                    impact=judgment,
                    recommendation="",
                    index_ref=block_name,
                    source="b22c",
                    severity=severity,
                )
            )

    return grouped


async def _load_b22b_deficiencies(project_id, db) -> dict:
    """加载内控缺陷（Wave3 repoint）：优先 B22C 单一真源，向后兼容回退旧 B22B.

    🔴 函数名 / 返回结构（{"deficiencies": {major,significant,general}, "warning"}）保持不变，
       避免破坏 A9-1 / A9-2 调用点。

    加载顺序：
    1. **优先** 从同项目 B22C 底稿读缺陷 + severity 并分组（B22C 为缺陷严重程度单一真源）。
    2. **向后兼容双读**：回退读旧 B22B（B22B-def-* / b22b-deficiency-*）。
    3. **去重**：B22B 缺陷若 description 已存在于 B22C（任一分组）则不重复计入。
    4. **P5 分组等价**：severity 中文→英文映射（_SEVERITY_MAP）在 B22B/B22C 一致；
       当 B22C 无数据时，结果与"纯读 B22B"完全等价（旧 fixture 测试保持绿，P6 兼容）。
    """
    # ── 1. 优先读 B22C ──────────────────────────────────────────────────────
    b22c_grouped = await _load_b22c_deficiencies(project_id, db)
    b22c_has_data = any(b22c_grouped.get(s) for s in ("major", "significant", "general"))

    # ── 2. 回退/补充读旧 B22B ───────────────────────────────────────────────
    b22b_result = await _load_legacy_b22b_deficiencies(project_id, db)
    b22b_grouped: dict[str, list[DeficiencyItem]] = b22b_result["deficiencies"]

    # ── 3. 合并（B22C 优先）+ 去重（按 description）────────────────────────────
    b22c_descs: set[str] = set()
    for grp in b22c_grouped.values():
        for it in grp:
            d = (it.description or "").strip()
            if d:
                b22c_descs.add(d)

    merged: dict[str, list[DeficiencyItem]] = {"major": [], "significant": [], "general": []}
    for sev in ("major", "significant", "general"):
        merged[sev].extend(b22c_grouped.get(sev, []))
    for sev in ("major", "significant", "general"):
        for it in b22b_grouped.get(sev, []):
            d = (it.description or "").strip()
            if d and d in b22c_descs:
                continue  # 与 B22C 同一缺陷去重，不重复计入
            merged[sev].append(it)

    # ── 4. warning：B22C 有数据即视为源已找到（None）；否则沿用 B22B 的 warning ──
    warning = None if b22c_has_data else b22b_result["warning"]

    return {"deficiencies": merged, "warning": warning}


async def _load_legacy_b22b_deficiencies(project_id, db) -> dict:
    """从 B22B 底稿的 checklist_responses 中提取已评价缺陷（旧数据源，向后兼容）.

    1. 通过 wp_index JOIN working_paper 找到同项目的 B22B 底稿
    2. 从 checklist_responses (item_id LIKE 'B22B-def-%') 按条目重建缺陷
       （兼容旧格式 b22b-deficiency-% 单条 JSON blob）
    3. 按严重程度（重大/重要/一般→major/significant/general）分组
    4. 返回 {"deficiencies": {...}, "warning": str | None}
    """
    deficiencies: dict[str, list[DeficiencyItem]] = {
        "major": [],
        "significant": [],
        "general": [],
    }

    # Find B22B workpaper for the same project
    try:
        b22b_result = await db.execute(
            sa.text(
                "SELECT wp.id AS wp_id "
                "FROM wp_index wi "
                "JOIN working_paper wp ON wp.wp_index_id = wi.id "
                "WHERE wi.wp_code = 'B22B' AND wp.project_id = :project_id "
                "LIMIT 1"
            ),
            {"project_id": str(project_id)},
        )
        b22b_row = b22b_result.fetchone()
    except Exception as e:  # noqa: BLE001
        logger.warning("A9-1 B22B 底稿查询失败 project_id=%s: %s", project_id, e)
        return {"deficiencies": deficiencies, "warning": "B22B查询失败"}

    if not b22b_row:
        return {"deficiencies": deficiencies, "warning": "未找到B22B内控缺陷评价表"}

    # Load deficiency data from B22B checklist_responses.
    # 🔴 B22B 实际持久化结构为分字段（前端 useB22BDeficiency.persistAll）：
    #   B22B-def-{n}-source (remark=JSON {tab,subPanel,index,controlPoint,deficiencyType,elementName})
    #   B22B-def-{n}-severity (conclusion=重大缺陷/重要缺陷/一般缺陷)
    #   B22B-def-{n}-corrective (conclusion=Y/N, remark=纠正措施描述)
    #   B22B-def-{n}-eliminated (conclusion=Y 表示已消除，跳过)
    #   B22B-def-count (remark=条目总数)
    #   （_SEVERITY_MAP 已提升为模块级，B22B/B22C 共用同一映射保证 P5 分组等价）
    try:
        cr_result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND (item_id LIKE 'B22B-def-%' OR item_id LIKE 'b22b-deficiency-%')"
            ),
            {"wp_id": str(b22b_row.wp_id)},
        )
        by_id: dict[str, tuple] = {}
        legacy_rows: list = []
        for row in cr_result.fetchall():
            if row.item_id.startswith("B22B-def-"):
                by_id[row.item_id] = (row.conclusion, row.remark)
            elif row.item_id.startswith("b22b-deficiency-"):
                legacy_rows.append(row)

        # ── 兼容旧格式：单条 JSON blob（item_id LIKE 'b22b-deficiency-%'）──
        for row in legacy_rows:
            if not row.remark:
                continue
            try:
                data = json.loads(row.remark)
            except (json.JSONDecodeError, TypeError):
                logger.warning("B22B deficiency JSON 解析失败 item_id=%s", row.item_id)
                continue
            if not isinstance(data, dict):
                continue
            severity = data.get("severity", "general")
            if severity not in ("major", "significant", "general"):
                severity = "general"
            deficiencies[severity].append(
                DeficiencyItem(
                    id=data.get("id", row.item_id),
                    description=data.get("description", ""),
                    impact=data.get("impact", ""),
                    recommendation=data.get("recommendation", ""),
                    index_ref=data.get("index_ref"),
                    source="b22b",
                    severity=severity,
                )
            )

        count_raw = (by_id.get("B22B-def-count") or (None, "0"))[1] or "0"
        try:
            count = int(count_raw)
        except (TypeError, ValueError):
            count = 0

        for n in range(1, count + 1):
            # 已消除的缺陷跳过
            elim = by_id.get(f"B22B-def-{n}-eliminated")
            if elim and elim[0] == "Y":
                continue
            sev_item = by_id.get(f"B22B-def-{n}-severity")
            severity_cn = sev_item[0] if sev_item else None
            severity = _SEVERITY_MAP.get(severity_cn or "", None)
            if severity is None:
                continue  # 未评定严重程度的不进入缺陷沟通函

            source_raw = (by_id.get(f"B22B-def-{n}-source") or (None, None))[1]
            control_point = ""
            element_name = ""
            deficiency_type = ""
            if source_raw:
                try:
                    src = json.loads(source_raw)
                    control_point = src.get("controlPoint", "") or ""
                    element_name = src.get("elementName", "") or ""
                    deficiency_type = src.get("deficiencyType", "") or ""
                except (json.JSONDecodeError, TypeError):
                    logger.warning("B22B-def-%s-source JSON 解析失败", n)

            corrective = by_id.get(f"B22B-def-{n}-corrective")
            recommendation = corrective[1] if (corrective and corrective[0] == "Y") else ""

            description = control_point or element_name or f"控制缺陷 {n}"
            impact = f"{element_name}（{deficiency_type}）" if deficiency_type else element_name

            deficiencies[severity].append(
                DeficiencyItem(
                    id=f"b22b-{n}",
                    description=description,
                    impact=impact,
                    recommendation=recommendation,
                    index_ref=element_name or None,
                    source="b22b",
                    severity=severity,
                )
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("A9-1 B22B checklist_responses 查询失败: %s", e)
        return {"deficiencies": deficiencies, "warning": "B22B缺陷数据读取失败"}

    return {"deficiencies": deficiencies, "warning": None}
