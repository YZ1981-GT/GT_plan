"""附注公式列表/持久化服务（acnr-consumer-wiring P10 / Req 15.6）。

背景（实证复盘）：`NoteFormulaDialog` 的 `formulas = ref([])` 从不加载、编辑不
持久化；后端仅有 `apply-formulas`（`execute_note_formulas` 从 check_presets 重
生成，丢弃用户编辑）/`clear-formulas`，**无 list/save 端点**。本 service 补齐
"列出当前公式（已保存优先，否则 generator 预览）" + "upsert 用户编辑集"。

存储决策（Req 15.6："可复用现有 note 公式表或新增轻量表"）：
- **复用** `DisclosureNote.table_data` JSONB，新增 key ``_user_formulas``（list）。
- 依据：DisclosureNote 以 ``(project_id, year, note_section)`` 唯一（见
  ``uq_disclosure_notes_active``），恰好等于 ``list_by_section`` 的定位维度；
  且 ``table_data`` 已按约定存 ``_formulas`` / ``_check_presets`` / ``_cell_meta``
  等下划线前缀内部键，追加 ``_user_formulas`` 与现有惯例一致，**无需迁移**。

职责：
- ``list_by_section``：已保存用户公式集（``_user_formulas``）优先；否则回退
  generator 预览（``_formulas`` 若已存则直接归一化，否则用
  ``generate_formulas_for_table`` 从 ``_check_presets`` + 表结构现算）。
- ``save_many``：把用户编辑集整体 upsert 到 ``_user_formulas``（覆盖式写入，
  即"这套就是最新集"），只 ``flush`` 不 ``commit``（router 统一 commit）。

工程铁律（遵循 memory）：
- service 只 ``flush`` 不 ``commit``（跨 service 编排由 router 统一 commit）。
- JSONB 原地修改后必须 ``flag_modified`` 让 SQLAlchemy 感知（与
  note_formula_generator / note_wp_mapping_service 一致）。
- 全 async（AsyncSession + select/execute async 风格）。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

# table_data 内持久化用户编辑公式集的 key（与 _formulas 区分：
# _formulas 是 generator 执行态；_user_formulas 是用户在弹窗中管理的编辑集）。
_USER_FORMULAS_KEY = "_user_formulas"

# 归一化后单条公式记录保留的字段（对齐 NoteFormulaDialog 行 shape：
# target / formula / description / category / source，附带内部 type）。
# 剔除前端本地态字段（如 _editing）避免污染存储。
_FORMULA_FIELDS = ("target", "formula", "description", "category", "source", "type")

_VALID_CATEGORIES = ("auto_calc", "logic_check", "reasonability")


def _normalize_record(rec: dict) -> dict | None:
    """把一条公式记录归一化为持久化 shape（剔除本地态字段）。

    - 至少要有 ``formula``（表达式）；否则视为空行跳过（返回 None）。
    - ``category`` 非法时回退 ``auto_calc``。
    - ``target`` 缺失时置空串（前端合计行标识/单元格坐标）。
    """
    if not isinstance(rec, dict):
        return None
    expr = rec.get("formula")
    if expr is None:
        # 兼容 generator 预览用 "expression" 字段
        expr = rec.get("expression")
    expr = (expr or "").strip() if isinstance(expr, str) else expr
    if not expr:
        return None

    category = rec.get("category") or "auto_calc"
    if category not in _VALID_CATEGORIES:
        category = "auto_calc"

    return {
        "target": str(rec.get("target") or rec.get("target_cell") or ""),
        "formula": expr,
        "description": rec.get("description") or "",
        "category": category,
        "source": rec.get("source") or "",
        "type": rec.get("type") or "",
    }


def _preview_from_formulas_dict(formulas: dict) -> list[dict]:
    """把 generator 的 ``_formulas`` dict（key=``row:col``）归一化为列表。

    generator 记录形如 ``{type, expression, description, category, source, ...}``；
    key（``row_idx:col_idx``）作为 ``target`` 单元格标识。
    """
    out: list[dict] = []
    if not isinstance(formulas, dict):
        return out
    for cell_key, fdef in formulas.items():
        if not isinstance(fdef, dict):
            continue
        rec = _normalize_record(
            {
                "target": cell_key,
                "formula": fdef.get("expression"),
                "description": fdef.get("description"),
                "category": fdef.get("category"),
                "source": fdef.get("source"),
                "type": fdef.get("type"),
            }
        )
        if rec is not None:
            out.append(rec)
    # 稳定排序：按 target 单元格坐标（row:col）排序，便于前端展示一致
    out.sort(key=lambda r: r.get("target") or "")
    return out


class NoteFormulaService:
    """附注公式列表/持久化（list_by_section / save_many）。"""

    async def _load_note(
        self, db: AsyncSession, project_id: UUID | str, year: int, note_section: str
    ) -> DisclosureNote | None:
        result = await db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_section(
        self, db: AsyncSession, project_id: UUID | str, year: int, note_section: str
    ) -> list[dict]:
        """列出某附注章节的当前公式集。

        优先级：
        1. 已保存用户编辑集 ``table_data._user_formulas``（非空则直接返回）。
        2. generator 预览：``table_data._formulas`` 若已存则归一化返回；
           否则用 ``generate_formulas_for_table`` 从 ``_check_presets`` + 表结构现算。

        note 不存在 / 无 table_data → 返回空列表（前端弹窗不阻断）。
        """
        note = await self._load_note(db, project_id, year, note_section)
        if note is None or not note.table_data:
            return []

        td = note.table_data

        # 1. 已保存用户编辑集优先
        saved = td.get(_USER_FORMULAS_KEY)
        if isinstance(saved, list) and saved:
            normalized = [_normalize_record(r) for r in saved]
            return [r for r in normalized if r is not None]

        # 2. generator 预览：已有 _formulas 直接用
        existing = td.get("_formulas")
        if isinstance(existing, dict) and existing:
            return _preview_from_formulas_dict(existing)

        # 3. 从 check_presets + 表结构现算预览
        from app.services.note_formula_generator import generate_formulas_for_table

        check_presets = td.get("_check_presets") or []
        table_template = {"headers": td.get("headers", []), "rows": td.get("rows", [])}
        try:
            generated = generate_formulas_for_table(table_template, check_presets)
        except Exception as e:  # generator 现算失败不阻断弹窗
            logger.warning(
                "[NOTE_FORMULA] preview generate 失败 section=%s: %s", note_section, e
            )
            return []
        return _preview_from_formulas_dict(generated)

    async def save_many(
        self,
        db: AsyncSession,
        project_id: UUID | str,
        year: int,
        note_section: str,
        formulas: list[dict],
    ) -> list[dict]:
        """upsert 用户编辑公式集到 ``table_data._user_formulas``（覆盖式）。

        入参 ``formulas`` 为前端提交的完整编辑集（"这套就是最新集"语义），
        整体替换 ``_user_formulas``。空行（无 formula 表达式）被过滤。

        只 ``flush`` 不 ``commit``（router 统一 commit）。

        Returns:
            持久化后的归一化公式列表。

        Raises:
            ValueError: 附注章节不存在（router 转 404/400）。
        """
        note = await self._load_note(db, project_id, year, note_section)
        if note is None:
            raise ValueError(f"附注章节不存在: {note_section}")

        normalized = [_normalize_record(r) for r in (formulas or [])]
        clean = [r for r in normalized if r is not None]

        td = dict(note.table_data) if isinstance(note.table_data, dict) else {}
        td[_USER_FORMULAS_KEY] = clean
        note.table_data = td
        flag_modified(note, "table_data")
        await db.flush()

        logger.info(
            "[NOTE_FORMULA] save_many project=%s section=%s count=%d",
            project_id, note_section, len(clean),
        )
        return clean


# 模块级单例（与 wp_formula_service / address_registry 等一致的使用风格）
note_formula_service = NoteFormulaService()
