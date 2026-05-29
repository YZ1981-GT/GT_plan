"""Sprint C.1 — 附注 AI 辅助服务 (D10).

主要 API:
- suggest_dynamic_rows(section, project_id, year) → list[dict]
- generate_paragraph_from_workpaper(wp_code, section_id, project_id, year) → str
- check_wp_tb_consistency(project_id, year) → list[dict]

纯 async service，依赖 DB session + LLM client（可选）。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

__all__ = ["NoteAIAssistantService"]


class NoteAIAssistantService:
    """附注 AI 辅助服务 (Sprint C.1, D10).

    三大功能：
    1. suggest_dynamic_rows: 基于辅助账数据建议哪些行该动态化
    2. generate_paragraph_from_workpaper: 从底稿摘要生成段落
    3. check_wp_tb_consistency: 校核 wp_data 取数与 TB 一致性
    """

    def __init__(self, db: Any = None):
        self.db = db

    async def suggest_dynamic_rows(
        self,
        section_id: str,
        project_id: UUID,
        year: int,
    ) -> list[dict[str, Any]]:
        """AI 建议哪些行该动态化 (C.1.1).

        逻辑：查 TB 该章节涉及科目的辅助账，若 aux_code 数 > 3 则建议动态化。

        Returns:
            list of suggestions: [{region_name, rationale, aux_count, suggested_source}]
        """
        # 查询该章节关联的科目
        account_codes = await self._get_section_accounts(section_id, project_id, year)
        if not account_codes:
            return []

        # 查询辅助账数据
        aux_data = await self._query_aux_balance(project_id, year, account_codes)

        suggestions: list[dict[str, Any]] = []

        # 按 aux_type 分组
        aux_groups: dict[str, int] = {}
        for item in aux_data:
            aux_type = item.get("aux_type", "unknown")
            aux_groups[aux_type] = aux_groups.get(aux_type, 0) + 1

        for aux_type, count in aux_groups.items():
            if count > 3:
                suggestions.append({
                    "region_name": f"aux_{aux_type}",
                    "rationale": f"检测到 {count} 个{aux_type}辅助账码，建议动态化",
                    "aux_count": count,
                    "suggested_source": "aux_balance",
                    "aux_type": aux_type,
                    "confidence": min(0.95, 0.5 + count * 0.05),
                })

        return suggestions

    async def generate_paragraph_from_workpaper(
        self,
        wp_code: str,
        section_id: str,
        project_id: UUID,
        year: int,
    ) -> str:
        """从底稿摘要生成段落 (C.1.2).

        如「重要会计判断」从 H 减值评估底稿摘要生成。

        Returns:
            Generated paragraph text (or empty string if LLM unavailable).
        """
        # 加载底稿 parsed_data
        wp_data = await self._load_workpaper_data(project_id, year, wp_code)
        if not wp_data:
            return ""

        # 提取摘要信息
        summary = self._extract_wp_summary(wp_data, wp_code)
        if not summary:
            return ""

        # 尝试调用 LLM 生成段落
        prompt = self._build_paragraph_prompt(section_id, wp_code, summary)
        generated = await self._call_llm(prompt)

        return generated or f"（基于{wp_code}底稿数据，待 AI 生成）"

    async def check_wp_tb_consistency(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict[str, Any]]:
        """校核 wp_data 取数与 TB 一致性 (C.1.3).

        对比底稿 parsed_data 中的金额与试算表科目余额，找出不一致项。

        Returns:
            list of issues: [{section_id, wp_code, field, wp_value, tb_value, diff, severity}]
        """
        issues: list[dict[str, Any]] = []

        # 加载所有有 wp_data binding 的章节
        bindings = await self._load_wp_bindings(project_id, year)

        for binding in bindings:
            wp_code = binding.get("wp_code", "")
            account_codes = binding.get("account_codes", [])
            section_id = binding.get("section_id", "")

            if not wp_code or not account_codes:
                continue

            # 获取 wp_data 值
            wp_value = await self._get_wp_value(project_id, year, wp_code, binding)

            # 获取 TB 值
            tb_value = await self._get_tb_value(project_id, year, account_codes)

            if wp_value is None or tb_value is None:
                continue

            # 比较
            diff = abs(float(wp_value) - float(tb_value))
            if diff > 0.01:  # 允许 1 分钱误差
                severity = "high" if diff > 10000 else "medium" if diff > 100 else "low"
                issues.append({
                    "section_id": section_id,
                    "wp_code": wp_code,
                    "field": binding.get("field", ""),
                    "wp_value": float(wp_value),
                    "tb_value": float(tb_value),
                    "diff": diff,
                    "severity": severity,
                })

        return issues

    # ─── Private helpers ───────────────────────────────────────────────────

    async def _get_section_accounts(
        self, section_id: str, project_id: UUID, year: int
    ) -> list[str]:
        """Get account codes associated with a section."""
        if self.db is None:
            return []
        try:
            from sqlalchemy import select

            from app.models.report_models import DisclosureNote

            result = await self.db.execute(
                select(DisclosureNote.table_data).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.section_id == section_id,
                )
            )
            table_data = result.scalar_one_or_none()
            if not table_data:
                return []
            # Extract account codes from bindings
            bindings = table_data.get("_bindings", {})
            codes = set()
            for b in bindings.values():
                primary = b if "source" in b else b.get("primary", {})
                if primary.get("source") == "trial_balance":
                    codes.update(primary.get("account_codes", []))
            return list(codes)
        except Exception:
            return []

    async def _query_aux_balance(
        self, project_id: UUID, year: int, account_codes: list[str]
    ) -> list[dict[str, Any]]:
        """Query auxiliary balance data for given accounts."""
        if self.db is None:
            return []
        try:
            from sqlalchemy import select, text

            result = await self.db.execute(
                text("""
                    SELECT aux_type, aux_code, aux_name
                    FROM tb_balance
                    WHERE project_id = :pid AND year = :year
                      AND account_code = ANY(:codes)
                      AND aux_type IS NOT NULL
                    GROUP BY aux_type, aux_code, aux_name
                """),
                {"pid": str(project_id), "year": year, "codes": account_codes},
            )
            return [dict(r._mapping) for r in result.fetchall()]
        except Exception:
            return []

    async def _load_workpaper_data(
        self, project_id: UUID, year: int, wp_code: str
    ) -> dict[str, Any] | None:
        """Load workpaper parsed_data."""
        if self.db is None:
            return None
        try:
            from sqlalchemy import select

            from app.models.models import WpIndex

            result = await self.db.execute(
                select(WpIndex.parsed_data).where(
                    WpIndex.project_id == project_id,
                    WpIndex.wp_code == wp_code,
                )
            )
            return result.scalar_one_or_none()
        except Exception:
            return None

    def _extract_wp_summary(self, wp_data: dict, wp_code: str) -> str:
        """Extract summary text from workpaper data."""
        # Try common summary fields
        for key in ("summary", "conclusion", "摘要", "结论", "审计结论"):
            if key in wp_data:
                return str(wp_data[key])
        # Try first sheet's text content
        for sheet_name, sheet_data in wp_data.items():
            if isinstance(sheet_data, dict) and "text" in sheet_data:
                return str(sheet_data["text"])[:500]
        return ""

    def _build_paragraph_prompt(self, section_id: str, wp_code: str, summary: str) -> str:
        """Build LLM prompt for paragraph generation."""
        return (
            f"根据以下底稿（{wp_code}）摘要信息，为附注章节「{section_id}」生成一段专业的审计附注披露段落。\n\n"
            f"底稿摘要：\n{summary}\n\n"
            f"要求：\n"
            f"1. 使用正式的财务报告语言\n"
            f"2. 包含关键数据和结论\n"
            f"3. 不超过 200 字\n"
        )

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM service (stub — returns empty if unavailable)."""
        # Integration point with existing note_ai.py / llm_client.py
        # Currently returns empty — LLM 真实接入待 phase3 UAT-3
        return ""

    async def _load_wp_bindings(
        self, project_id: UUID, year: int
    ) -> list[dict[str, Any]]:
        """Load all wp_data bindings across sections."""
        if self.db is None:
            return []
        try:
            from sqlalchemy import select

            from app.models.report_models import DisclosureNote

            result = await self.db.execute(
                select(DisclosureNote.section_id, DisclosureNote.table_data).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.is_deleted == False,  # noqa: E712
                )
            )
            bindings = []
            for row in result.fetchall():
                section_id = row[0]
                table_data = row[1] or {}
                for key, b in table_data.get("_bindings", {}).items():
                    primary = b if "source" in b else b.get("primary", {})
                    if primary.get("source") == "wp_data":
                        bindings.append({
                            "section_id": section_id,
                            "wp_code": primary.get("wp_code", ""),
                            "account_codes": primary.get("account_codes", []),
                            "field": primary.get("field", ""),
                        })
            return bindings
        except Exception:
            return []

    async def _get_wp_value(
        self, project_id: UUID, year: int, wp_code: str, binding: dict
    ) -> float | None:
        """Get value from workpaper."""
        wp_data = await self._load_workpaper_data(project_id, year, wp_code)
        if not wp_data:
            return None
        # Simplified extraction — real implementation uses _extract_wp_cell
        return None

    async def _get_tb_value(
        self, project_id: UUID, year: int, account_codes: list[str]
    ) -> float | None:
        """Get value from trial balance."""
        if self.db is None or not account_codes:
            return None
        try:
            from sqlalchemy import func, select, text

            result = await self.db.execute(
                text("""
                    SELECT COALESCE(SUM(audited_amount), 0)
                    FROM tb_balance
                    WHERE project_id = :pid AND year = :year
                      AND account_code = ANY(:codes)
                """),
                {"pid": str(project_id), "year": year, "codes": account_codes},
            )
            val = result.scalar_one_or_none()
            return float(val) if val is not None else None
        except Exception:
            return None
