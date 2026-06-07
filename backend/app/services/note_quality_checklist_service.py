"""附注质量清单服务

聚合附注各类质量问题，生成标准化清单。

Categories:
- formula: 公式执行错误
- stale: 数据陈旧（底稿已更新但附注未刷新）
- manual_override: 手工覆盖未确认
- ai: AI 草稿未人工确认
- tieout: 披露与报表不一致
- style: 样式/格式问题
- completeness: 完整性问题（缺失章节/表格/数据）

Levels:
- blocking: 阻止签发
- warning: 需关注但不阻止
- info: 信息提示

Validates: Requirements 9.1, 9.2, 9.3
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

VALID_LEVELS = ("blocking", "warning", "info")

VALID_CATEGORIES = (
    "formula",
    "stale",
    "manual_override",
    "ai",
    "tieout",
    "style",
    "completeness",
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class QualityChecklistItem(BaseModel):
    """质量清单条目

    level: blocking | warning | info
    category: formula | stale | manual_override | ai | tieout | style | completeness
    """

    level: str = Field(..., description="问题级别：blocking | warning | info")
    category: str = Field(
        ..., description="问题分类：formula | stale | manual_override | ai | tieout | style | completeness"
    )
    section_id: str | None = Field(default=None, description="章节 ID")
    table_id: str | None = Field(default=None, description="表 ID")
    row_id: str | None = Field(default=None, description="行 ID")
    col_id: str | None = Field(default=None, description="列 ID")
    message: str = Field(..., description="问题描述")
    route: str | None = Field(default=None, description="跳转路由")
    evidence: dict[str, Any] | None = Field(default=None, description="证据上下文")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NoteQualityChecklistService:
    """附注质量清单服务

    从一组章节的 table_data 生成标准化质量清单。
    聚合 stale、formula error、manual override、AI unconfirmed 四类问题。
    """

    def generate_checklist(
        self, table_data_list: list[dict[str, Any]]
    ) -> list[QualityChecklistItem]:
        """从一组章节的 table_data 生成质量清单

        Args:
            table_data_list: 每个元素是一个章节的 table_data dict，
                             需包含 _semantic.section_id 用于定位。

        Returns:
            质量清单条目列表
        """
        items: list[QualityChecklistItem] = []
        for table_data in table_data_list:
            section_id = self._extract_section_id(table_data)
            items.extend(self._check_formula_errors(table_data, section_id))
            items.extend(self._check_stale_data(table_data, section_id))
            items.extend(self._check_manual_overrides(table_data, section_id))
            items.extend(self._check_ai_unconfirmed(table_data, section_id))
        return items

    # ------------------------------------------------------------------
    # 内部检查方法
    # ------------------------------------------------------------------

    def _extract_section_id(self, table_data: dict[str, Any]) -> str:
        """从 table_data 中提取 section_id"""
        semantic = table_data.get("_semantic") or {}
        return semantic.get("section_id", "unknown")

    def _check_formula_errors(
        self, table_data: dict[str, Any], section_id: str
    ) -> list[QualityChecklistItem]:
        """检查公式执行错误"""
        items: list[QualityChecklistItem] = []
        formulas = table_data.get("_formulas") or {}
        for anchor_key, formula_info in formulas.items():
            if not isinstance(formula_info, dict):
                continue
            last_error = formula_info.get("last_error")
            if last_error:
                # 尝试解析 anchor_key: section.table.row.col
                parts = anchor_key.split(".")
                table_id = parts[1] if len(parts) > 1 else None
                row_id = parts[2] if len(parts) > 2 else None
                col_id = parts[3] if len(parts) > 3 else None
                items.append(
                    QualityChecklistItem(
                        level="blocking",
                        category="formula",
                        section_id=section_id,
                        table_id=table_id,
                        row_id=row_id,
                        col_id=col_id,
                        message=f"公式执行错误：{last_error}",
                        route=f"/projects/{{pid}}/disclosure-notes?section={section_id}",
                        evidence={
                            "formula_id": formula_info.get("formula_id"),
                            "expr": formula_info.get("expr"),
                            "error": last_error,
                        },
                    )
                )
        return items

    def _check_stale_data(
        self, table_data: dict[str, Any], section_id: str
    ) -> list[QualityChecklistItem]:
        """检查数据陈旧（底稿已更新但附注未刷新）"""
        items: list[QualityChecklistItem] = []
        # 检查 _stale 标记
        stale_info = table_data.get("_stale")
        if stale_info:
            # _stale 可以是 bool 或 dict
            if isinstance(stale_info, bool) and stale_info:
                items.append(
                    QualityChecklistItem(
                        level="warning",
                        category="stale",
                        section_id=section_id,
                        message="章节数据陈旧，底稿已更新但附注未刷新",
                        route=f"/projects/{{pid}}/disclosure-notes?section={section_id}",
                    )
                )
            elif isinstance(stale_info, dict):
                reason = stale_info.get("reason", "底稿已更新")
                source_wp = stale_info.get("source_wp")
                items.append(
                    QualityChecklistItem(
                        level="warning",
                        category="stale",
                        section_id=section_id,
                        message=f"章节数据陈旧：{reason}",
                        route=f"/projects/{{pid}}/disclosure-notes?section={section_id}",
                        evidence={"reason": reason, "source_wp": source_wp},
                    )
                )
        return items

    def _check_manual_overrides(
        self, table_data: dict[str, Any], section_id: str
    ) -> list[QualityChecklistItem]:
        """检查手工覆盖未确认"""
        items: list[QualityChecklistItem] = []
        tables = table_data.get("_tables") or []
        for table in tables:
            if not isinstance(table, dict):
                continue
            table_id = table.get("table_id")
            rows = table.get("rows") or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                row_id = row.get("row_id")
                cell_modes = row.get("_cell_modes") or {}
                cell_meta = row.get("_cell_meta") or {}
                columns = table.get("columns") or []
                for col_idx_str, mode in cell_modes.items():
                    if mode == "manual":
                        # 检查是否有 confirmed 标记
                        meta = cell_meta.get(col_idx_str) or {}
                        if not meta.get("confirmed"):
                            col_id = None
                            try:
                                col_idx = int(col_idx_str)
                                if col_idx < len(columns):
                                    col_id = columns[col_idx].get("col_id")
                            except (ValueError, TypeError):
                                col_id = col_idx_str
                            items.append(
                                QualityChecklistItem(
                                    level="warning",
                                    category="manual_override",
                                    section_id=section_id,
                                    table_id=table_id,
                                    row_id=row_id,
                                    col_id=col_id,
                                    message="手工覆盖未确认",
                                    route=f"/projects/{{pid}}/disclosure-notes?section={section_id}",
                                )
                            )
        return items

    def _check_ai_unconfirmed(
        self, table_data: dict[str, Any], section_id: str
    ) -> list[QualityChecklistItem]:
        """检查 AI 草稿未人工确认"""
        items: list[QualityChecklistItem] = []
        # 检查 _ai_draft 标记
        ai_draft = table_data.get("_ai_draft")
        if ai_draft:
            if isinstance(ai_draft, bool) and ai_draft:
                items.append(
                    QualityChecklistItem(
                        level="blocking",
                        category="ai",
                        section_id=section_id,
                        message="AI 草稿未经人工确认，阻止签发",
                        route=f"/projects/{{pid}}/disclosure-notes?section={section_id}",
                    )
                )
            elif isinstance(ai_draft, dict):
                status = ai_draft.get("status", "unconfirmed")
                if status != "confirmed":
                    items.append(
                        QualityChecklistItem(
                            level="blocking",
                            category="ai",
                            section_id=section_id,
                            message="AI 草稿未经人工确认，阻止签发",
                            route=f"/projects/{{pid}}/disclosure-notes?section={section_id}",
                            evidence={"status": status},
                        )
                    )
        # 检查 _policy_clauses 中 AI 来源条款
        policy_clauses = table_data.get("_policy_clauses") or []
        for clause in policy_clauses:
            if not isinstance(clause, dict):
                continue
            if clause.get("confirm_status") == "pending" and clause.get("diff_status") == "changed":
                # AI 修改的条款未确认也列入
                if clause.get("source") == "ai" or "ai" in str(clause.get("variables", [])).lower():
                    items.append(
                        QualityChecklistItem(
                            level="warning",
                            category="ai",
                            section_id=section_id,
                            message=f"AI 生成条款「{clause.get('title', '')}」未人工确认",
                            route=f"/projects/{{pid}}/disclosure-notes?section={section_id}",
                        )
                    )
        return items
