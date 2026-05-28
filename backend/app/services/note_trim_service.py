"""附注章节裁剪服务

Phase 9 Task 9.27
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.note_trim_models import NoteSectionInstance, NoteTrimScheme
from app.services.note_template_bindings_loader import get_binding_for_section
from app.services.note_template_service import NoteTemplateService

logger = logging.getLogger(__name__)


def _extract_basic_info(wizard_state: dict | None) -> dict:
    state = wizard_state or {}
    return (
        state.get("steps", {}).get("basic_info", {}).get("data")
        or state.get("basic_info", {}).get("data")
        or {}
    )


class NoteTrimService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_project_basic_info(self, project_id: UUID) -> dict:
        result = await self.db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == False,  # noqa
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            return {}

        template_service = NoteTemplateService()
        wizard_state, _, changed = template_service.backfill_locked_template_snapshot(project.wizard_state)
        if changed:
            project.wizard_state = wizard_state
            await self.db.flush()
        return _extract_basic_info(project.wizard_state)

    async def resolve_template_type(self, project_id: UUID, template_type: str | None) -> str:
        if template_type:
            resolved = template_type
        else:
            basic_info = await self._get_project_basic_info(project_id)
            resolved = basic_info.get("template_type")
            resolved = resolved if isinstance(resolved, str) and resolved else "soe"

        if resolved == "custom":
            await self._load_custom_template(project_id)
        return resolved

    async def get_sections(self, project_id: UUID, template_type: str = "soe") -> list[dict]:
        """获取章节列表（含裁剪状态）"""
        q = (
            sa.select(NoteSectionInstance)
            .where(
                NoteSectionInstance.project_id == project_id,
                NoteSectionInstance.template_type == template_type,
                NoteSectionInstance.is_deleted == False,  # noqa
            )
            .order_by(NoteSectionInstance.sort_order)
        )
        rows = (await self.db.execute(q)).scalars().all()
        sections = await self._load_template_sections(project_id, template_type)

        if template_type == "custom" and rows and self._should_reinitialize(rows, sections):
            for row in rows:
                row.is_deleted = True
            await self.db.flush()
            rows = []

        if not rows and sections:
            rows = await self._init_from_sections(project_id, template_type, sections)

        return [
            {
                "id": str(r.id),
                "section_number": r.section_number,
                "section_title": r.section_title,
                "status": r.status,
                "skip_reason": r.skip_reason,
                "sort_order": r.sort_order,
            }
            for r in rows
        ]

    async def _load_custom_template(self, project_id: UUID) -> dict:
        basic_info = await self._get_project_basic_info(project_id)
        template_service = NoteTemplateService()
        locked_snapshot = template_service.get_locked_template_snapshot(basic_info)
        if locked_snapshot is not None:
            return locked_snapshot

        template_id = basic_info.get("custom_template_id")
        if not template_id:
            logger.warning("project %s has no custom_template_id in wizard_state", project_id)
            raise HTTPException(status_code=400, detail="当前项目未绑定有效的自定义附注模板，请先在项目基本信息中选择")

        template = template_service.get_template(template_id)
        if template is None:
            logger.warning("custom note template %s not found for project %s", template_id, project_id)
            raise HTTPException(status_code=400, detail="当前项目绑定的自定义附注模板不存在或已失效，请重新选择")
        return template

    async def _load_template_sections(self, project_id: UUID, template_type: str) -> list[dict]:
        if template_type == "custom":
            template = await self._load_custom_template(project_id)
            return template.get("sections", [])

        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        tmpl_file = data_dir / f"note_template_{template_type}.json"
        if not tmpl_file.exists():
            return []

        tmpl = json.loads(tmpl_file.read_text(encoding="utf-8-sig"))
        return tmpl.get("sections", [])

    def _should_reinitialize(self, rows: list[NoteSectionInstance], sections: list[dict]) -> bool:
        existing = [(row.section_number, row.section_title) for row in rows]
        desired = [
            (section.get("section_number", f"五、{idx + 1}"), section.get("section_title", ""))
            for idx, section in enumerate(sections)
        ]
        return existing != desired

    async def _init_from_template(self, project_id: UUID, template_type: str) -> list[NoteSectionInstance]:
        """从模版初始化章节实例"""
        sections = await self._load_template_sections(project_id, template_type)
        return await self._init_from_sections(project_id, template_type, sections)

    async def _init_from_sections(
        self,
        project_id: UUID,
        template_type: str,
        sections: list[dict],
    ) -> list[NoteSectionInstance]:
        instances = []
        for i, s in enumerate(sections):
            inst = NoteSectionInstance(
                project_id=project_id,
                template_type=template_type,
                section_number=s.get("section_number", f"五、{i+1}"),
                section_title=s.get("section_title", ""),
                sort_order=i * 10,
            )
            self.db.add(inst)
            instances.append(inst)

        await self.db.flush()
        return instances

    async def save_trim(self, project_id: UUID, template_type: str, items: list[dict]) -> int:
        """保存裁剪结果"""
        updated = 0
        for item in items:
            sid = item.get("id")
            if not sid:
                continue
            await self.db.execute(
                sa.update(NoteSectionInstance)
                .where(NoteSectionInstance.id == sid)
                .values(status=item.get("status", "retain"), skip_reason=item.get("skip_reason"))
            )
            updated += 1

        # 保存裁剪方案
        scheme = NoteTrimScheme(
            project_id=project_id,
            template_type=template_type,
            scheme_name=f"附注裁剪-{template_type}-{datetime.now().strftime('%Y%m%d')}",
            trim_data={item["id"]: {"status": item.get("status"), "skip_reason": item.get("skip_reason")} for item in items if item.get("id")},
        )
        self.db.add(scheme)
        await self.db.flush()
        return updated

    async def get_trim_scheme(self, project_id: UUID, template_type: str) -> dict | None:
        q = (
            sa.select(NoteTrimScheme)
            .where(
                NoteTrimScheme.project_id == project_id,
                NoteTrimScheme.template_type == template_type,
                NoteTrimScheme.is_deleted == False,  # noqa
            )
            .order_by(NoteTrimScheme.created_at.desc())
            .limit(1)
        )
        scheme = (await self.db.execute(q)).scalar_one_or_none()
        if not scheme:
            return None
        return {"id": str(scheme.id), "scheme_name": scheme.scheme_name, "trim_data": scheme.trim_data}

    # ------------------------------------------------------------------
    # Sprint 3 Task 3.7：auto_trim 简化版
    # ------------------------------------------------------------------

    async def auto_trim(
        self,
        project_id: UUID,
        year: int,
        template_type: str | None = None,
    ) -> dict:
        """自动裁剪：检查每个 section 关联的 account_codes 在 TrialBalance 是否全为 0.

        算法：
        1. 解析 template_type（默认从 wizard_state 取）
        2. 通过 ``get_sections`` 拿到所有章节实例（已含 NoteSectionInstance.id）
        3. 加载 ``note_template_bindings.json``（用 ``get_binding_for_section``）
        4. 对每个 section：
           - 收集 binding 中所有 cell.account_codes 的并集
           - 查 TrialBalance：若 audited_amount + opening_balance 全为 0 / NULL → 标
             ``status=not_applicable, skip_reason='auto:all_zero'``
           - 缺 binding 或 account_codes 全空 → 默认保留（不裁剪）
        5. 调 ``save_trim`` 批量保存

        Returns:
            ``{"auto_skipped": int, "retained": int, "errors": list[dict]}``
        """
        resolved_type = await self.resolve_template_type(project_id, template_type)
        sections = await self.get_sections(project_id, resolved_type)

        items: list[dict] = []
        errors: list[dict] = []
        auto_skipped = 0
        retained = 0

        for section in sections:
            section_id = section.get("id")
            section_number = section.get("section_number")
            try:
                binding = get_binding_for_section(section_number)
                account_codes = self._collect_account_codes_for_section(binding)
                if not account_codes:
                    # 缺 binding / 无 account_codes → 默认保留
                    retained += 1
                    continue

                all_zero = await self._is_all_zero_for_codes(
                    project_id, year, list(account_codes)
                )
                if all_zero:
                    items.append({
                        "id": section_id,
                        "status": "not_applicable",
                        "skip_reason": "auto:all_zero",
                    })
                    auto_skipped += 1
                else:
                    retained += 1
            except Exception as exc:  # graceful：单个 section 失败不阻塞整体
                logger.warning(
                    "auto_trim section %s failed: %s", section_number, exc
                )
                errors.append({
                    "section_id": section_id,
                    "section_number": section_number,
                    "error": str(exc),
                })
                retained += 1

        if items:
            try:
                await self.save_trim(project_id, resolved_type, items)
            except Exception as exc:
                logger.exception("auto_trim save_trim failed: %s", exc)
                errors.append({"phase": "save_trim", "error": str(exc)})

        return {
            "auto_skipped": auto_skipped,
            "retained": retained,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Sprint A.3.3：auto_trim_v2 三级裁剪（章节 / 表格 / 段落，CI-8 互斥）
    # ------------------------------------------------------------------

    async def auto_trim_v2(
        self,
        project_id: UUID,
        year: int,
        template_type: str | None = None,
    ) -> dict:
        """三级裁剪：章节 / 表格 / 段落。

        互斥优先级（CI-8）：``section > paragraph > table``
        - 章节级（section_skipped）：TB account_codes 全 0 → ``status='not_applicable'``
        - 段落级（section_deleted）：``is_section_empty(note)`` → ``is_deleted=true``
        - 表格级（table_replaced）：``is_table_data_empty`` → ``table_data._render_as='no_business_paragraph'``

        同一章节最多触发一个级别。

        Returns:
            ``{"section_skipped": int, "section_deleted": int, "table_replaced": int,
               "retained": int, "errors": list[dict]}``
        """
        from app.models.report_models import DisclosureNote
        from app.services.note_is_empty_calc import (
            is_section_empty,
            is_table_data_empty,
        )

        resolved_type = await self.resolve_template_type(project_id, template_type)
        sections = await self.get_sections(project_id, resolved_type)

        # ─── Pass 1：章节级（与 auto_trim 同语义）─────────────────────────
        section_items: list[dict] = []
        section_skipped_numbers: set[str] = set()  # 已被章节级标的 section_number
        errors: list[dict] = []

        for section in sections:
            sid = section.get("id")
            snum = section.get("section_number")
            try:
                binding = get_binding_for_section(snum)
                account_codes = self._collect_account_codes_for_section(binding)
                if not account_codes:
                    continue
                all_zero = await self._is_all_zero_for_codes(
                    project_id, year, list(account_codes)
                )
                if all_zero:
                    section_items.append({
                        "id": sid,
                        "status": "not_applicable",
                        "skip_reason": "auto:all_zero",
                    })
                    if snum:
                        section_skipped_numbers.add(snum)
            except Exception as exc:
                logger.warning(
                    "auto_trim_v2 section %s level-1 failed: %s", snum, exc
                )
                errors.append({
                    "section_id": sid,
                    "section_number": snum,
                    "phase": "level1_section",
                    "error": str(exc),
                })

        if section_items:
            try:
                await self.save_trim(project_id, resolved_type, section_items)
            except Exception as exc:
                logger.exception("auto_trim_v2 save_trim failed: %s", exc)
                errors.append({"phase": "save_trim", "error": str(exc)})

        # ─── 加载剩余章节的 DisclosureNote（CI-8：跳过已章节级标的）─────
        remaining_numbers = [
            s.get("section_number") for s in sections
            if s.get("section_number") and s.get("section_number") not in section_skipped_numbers
        ]
        notes_by_section: dict[str, list[DisclosureNote]] = {}
        if remaining_numbers:
            try:
                q = sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section.in_(remaining_numbers),
                    DisclosureNote.is_deleted == sa.false(),
                )
                rows = (await self.db.execute(q)).scalars().all()
                for n in rows:
                    notes_by_section.setdefault(n.note_section, []).append(n)
            except Exception as exc:
                logger.warning("auto_trim_v2 load notes failed: %s", exc)
                errors.append({"phase": "load_notes", "error": str(exc)})

        # ─── Pass 2：段落级（章节空 → DisclosureNote.is_deleted=true）──
        section_deleted_numbers: set[str] = set()
        section_deleted_count = 0

        for snum, notes in notes_by_section.items():
            if not notes:
                continue
            try:
                # 章节内所有 note 都是空 → 整章节段落级删除
                if all(is_section_empty(n) for n in notes):
                    for n in notes:
                        n.is_deleted = True
                        # 记录删除原因到 template_lineage（无独立列，避免 schema 改动）
                        lineage = dict(n.template_lineage or {})
                        lineage["deletion_reason"] = "auto_trim_v2_empty"
                        from datetime import datetime as _dt, timezone as _tz
                        lineage["deletion_at"] = _dt.now(_tz.utc).isoformat()
                        n.template_lineage = lineage
                        try:
                            from sqlalchemy.orm.attributes import flag_modified
                            flag_modified(n, "template_lineage")
                        except Exception:
                            # 非 ORM 实例（测试 mock）— 跳过 flag_modified
                            pass
                    section_deleted_numbers.add(snum)
                    section_deleted_count += 1
            except Exception as exc:
                logger.warning(
                    "auto_trim_v2 section %s level-2 failed: %s", snum, exc
                )
                errors.append({
                    "section_number": snum,
                    "phase": "level2_paragraph",
                    "error": str(exc),
                })

        # ─── Pass 3：表格级（剩余章节内空 table → _render_as 标记）─────
        table_replaced_count = 0
        for snum, notes in notes_by_section.items():
            if snum in section_deleted_numbers:
                continue  # CI-8：段落级已标，不再标表格级
            for n in notes:
                try:
                    td = n.table_data
                    if not isinstance(td, dict):
                        continue
                    # 单表分支
                    multi = td.get("_tables") if isinstance(td.get("_tables"), list) else None
                    if multi:
                        modified = False
                        for tbl in multi:
                            if isinstance(tbl, dict) and is_table_data_empty(tbl):
                                tbl["_render_as"] = "no_business_paragraph"
                                modified = True
                        if modified:
                            n.table_data = td
                            try:
                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(n, "table_data")
                            except Exception:
                                pass
                            table_replaced_count += 1
                    else:
                        if is_table_data_empty(td):
                            # 跳过 text_content 非空 + table 空的场景：让 paragraph 保留正文
                            td["_render_as"] = "no_business_paragraph"
                            n.table_data = td
                            try:
                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(n, "table_data")
                            except Exception:
                                pass
                            table_replaced_count += 1
                except Exception as exc:
                    logger.warning(
                        "auto_trim_v2 note %s level-3 failed: %s", n.id, exc
                    )
                    errors.append({
                        "note_id": str(n.id),
                        "section_number": snum,
                        "phase": "level3_table",
                        "error": str(exc),
                    })

        try:
            await self.db.flush()
        except Exception as exc:
            logger.exception("auto_trim_v2 flush failed: %s", exc)
            errors.append({"phase": "flush", "error": str(exc)})

        retained = max(
            0,
            len(sections) - len(section_skipped_numbers) - section_deleted_count,
        )

        return {
            "section_skipped": len(section_skipped_numbers),
            "section_deleted": section_deleted_count,
            "table_replaced": table_replaced_count,
            "retained": retained,
            "errors": errors,
        }


    @staticmethod
    def _collect_account_codes_for_section(binding: dict | None) -> set[str]:
        """从 section binding 的所有 cell.account_codes 并集中收集科目代码."""
        if not binding or not isinstance(binding, dict):
            return set()
        codes: set[str] = set()
        tables = binding.get("tables")
        if not isinstance(tables, list):
            return set()
        for tbl in tables:
            if not isinstance(tbl, dict):
                continue
            rows = tbl.get("rows")
            if not isinstance(rows, dict):
                continue
            for row in rows.values():
                if not isinstance(row, dict):
                    continue
                cell_bindings = row.get("binding")
                if not isinstance(cell_bindings, dict):
                    continue
                for cell in cell_bindings.values():
                    if not isinstance(cell, dict):
                        continue
                    cell_codes = cell.get("account_codes")
                    if isinstance(cell_codes, list):
                        for c in cell_codes:
                            if isinstance(c, str) and c:
                                codes.add(c)
        return codes

    async def _is_all_zero_for_codes(
        self,
        project_id: UUID,
        year: int,
        account_codes: list[str],
    ) -> bool:
        """查 TrialBalance：若指定 account_codes 在 audited + opening 全为 0/NULL → True.

        - 该年度无任何相关试算表行 → True（视为全 0）
        - 任一行 audited_amount 或 opening_balance 非 0 / 非 None → False
        """
        from decimal import Decimal

        from app.models.audit_platform_models import TrialBalance

        if not account_codes:
            return True

        try:
            q = sa.select(
                TrialBalance.audited_amount,
                TrialBalance.opening_balance,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == sa.false(),
            )
            result = await self.db.execute(q)
            rows = result.all()
        except Exception as exc:
            # 缺 TrialBalance 数据 / DB 异常 → graceful 返 True（视作全 0，但可被上层降级）
            logger.warning(
                "auto_trim _is_all_zero_for_codes db error for codes=%s: %s",
                account_codes, exc,
            )
            return True

        if not rows:
            return True

        zero = Decimal("0")
        for audited, opening in rows:
            if audited is not None and audited != zero:
                return False
            if opening is not None and opening != zero:
                return False
        return True
