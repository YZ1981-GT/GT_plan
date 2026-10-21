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

职责（formula-global-settings-sync 起，见 ``formula_settings.note_settings``）：
- ``list_with_versions`` / ``list_by_section``：有效公式集 = 本项目适配 > 全局 > 该表模板公式
  （generator 预览：``_formulas`` 若已存则直接归一化，否则从 ``_check_presets`` + 表结构现算）。
- ``save_many``：按载入版本令牌求差量写本项目适配（``formula_setting``），再把有效集合物化到
  ``_user_formulas``（执行器按目标单元格「用户集优先」合并，不改）；只 ``flush`` 不 ``commit``。

工程铁律（遵循 memory）：
- service 只 ``flush`` 不 ``commit``（跨 service 编排由 router 统一 commit）。
- 全 async（AsyncSession + select/execute async 风格）。
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

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


def preview_records(td: dict | None, note_section: str) -> list[dict]:
    """该附注表自带的模板公式（generator 预览）：已有 ``_formulas`` 直接归一化，否则按
    ``_check_presets`` + 表结构现算；现算失败返回空（不阻断弹窗）。"""
    if not isinstance(td, dict) or not td:
        return []
    existing = td.get("_formulas")
    if isinstance(existing, dict) and existing:
        return _preview_from_formulas_dict(existing)
    from app.services.note_formula_generator import generate_formulas_for_table

    table_template = {"headers": td.get("headers", []), "rows": td.get("rows", [])}
    try:
        generated = generate_formulas_for_table(table_template, td.get("_check_presets") or [])
    except Exception as e:  # generator 现算失败不阻断弹窗
        logger.warning("[NOTE_FORMULA] preview generate 失败 section=%s: %s", note_section, e)
        return []
    return _preview_from_formulas_dict(generated)


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

    async def list_with_versions(
        self, db: AsyncSession, project_id: UUID | str, year: int, note_section: str
    ) -> dict:
        """某附注章节的有效公式集 + 载入版本令牌（formula-global-settings-sync）。

        有效集 = 本项目适配 > 全局 > 该表模板公式（generator 预览）；每条带层级标签。
        ``loaded`` 原样回传给保存接口（缺 428、过期 409）。
        """
        from app.services.formula_settings.note_settings import list_section

        return await list_section(db, _uuid(project_id), year, note_section)

    async def list_by_section(
        self, db: AsyncSession, project_id: UUID | str, year: int, note_section: str
    ) -> list[dict]:
        """列出某附注章节的当前公式集（同 ``list_with_versions`` 的 ``formulas``）。"""
        return (await self.list_with_versions(db, project_id, year, note_section))["formulas"]

    async def save_many(
        self,
        db: AsyncSession,
        project_id: UUID | str,
        year: int,
        note_section: str,
        formulas: list[dict],
        *,
        loaded: dict | None = None,
        user_id: UUID | None = None,
    ) -> list[dict]:
        """保存附注章节的公式集（前端提交完整编辑集，"这套就是最新集"语义）。

        formula-global-settings-sync：按载入时的版本令牌求差量写本项目适配（``formula_setting``），
        再把有效集合物化到 ``table_data._user_formulas``（执行器不改）；与该表模板公式相同的不算适配。
        只 ``flush`` 不 ``commit``（router 统一 commit）。

        Returns:
            保存后的有效公式列表。

        Raises:
            ValueError: 附注章节不存在（router 转 404）。
            FormulaSettingError: 缺版本令牌 428 / 已被他人修改 409。
        """
        from app.services.formula_settings.note_settings import save_section

        result = await save_section(db, _uuid(project_id), year, note_section, formulas or [],
                                    loaded=loaded, user_id=user_id)
        logger.info(
            "[NOTE_FORMULA] save_many project=%s section=%s count=%d",
            project_id, note_section, len(result["formulas"]),
        )
        return result["formulas"]


def _uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


# 模块级单例（与 wp_formula_service / address_registry 等一致的使用风格）
note_formula_service = NoteFormulaService()
