"""TemplateCopier — 跨项目模板复制器（纯函数层）

核心职责：
1. copy_single: 复制底稿文件+索引记录到目标项目
2. _strip_business_data: 清除金额/日期/描述，保留结构和程序步骤
3. 重新生成 wp_index 记录（新 UUID、目标 project_id）
4. 目标已存在同 wp_code 时 overwrite=false 提示跳过
5. copy_cycle: 批量复制整个审计循环
6. 复制后状态设为 draft、清除复核状态

设计原则：
- 纯函数：不依赖 DB/IO，接收源底稿 dict + 目标参数
- service 只 flush 不 commit（DB 层由调用方处理）

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class CopyResult:
    """模板复制单项结果"""

    source_wp_code: str
    target_wp_id: UUID | None = None
    status: str = "copied"  # copied | skipped | failed
    message: str | None = None


class TemplateCopier:
    """跨项目模板复制器（纯函数设计，无 DB/IO 依赖）

    接收源底稿数据 dict，返回复制结果。
    """

    def copy_single(
        self,
        source_wp: dict,
        target_project_id: UUID,
        overwrite: bool = False,
        existing_codes: set[str] | None = None,
    ) -> CopyResult:
        """纯函数：给定源底稿数据，生成目标副本。

        Args:
            source_wp: 源底稿数据，包含:
                - wp_code: str
                - wp_name: str
                - audit_cycle: str
                - status: str
                - review_status: str
                - is_deleted: bool
                - file_format: str (xlsx/docx)
                - data: dict (底稿数据/parsed_data，含 dynamic_table 区域)
                - schema: dict | None (render_schema，标识列类型/只读属性)
                - wp_id: UUID (源 wp_id)
                - project_id: UUID (源 project_id)
            target_project_id: 目标项目 ID
            overwrite: 是否覆盖已有同 wp_code 底稿
            existing_codes: 目标项目已有的 wp_code 集合

        Returns:
            CopyResult with:
              - source_wp_code: 源底稿编号
              - target_wp_id: 新生成的底稿 UUID（跳过时为 None）
              - status: copied | skipped
              - message: 跳过原因或成功信息
              - target_record: dict (新底稿记录数据，仅 status=copied 时有)
        """
        wp_code = source_wp["wp_code"]
        existing = existing_codes or set()

        # 目标已存在同 wp_code 且不覆盖 → 跳过
        if wp_code in existing and not overwrite:
            return CopyResult(
                source_wp_code=wp_code,
                target_wp_id=None,
                status="skipped",
                message=f"目标项目已存在 wp_code={wp_code}，overwrite=False 跳过",
            )

        # 生成新 UUID
        new_wp_id = uuid4()

        # 清除业务数据
        source_data = source_wp.get("data") or {}
        schema = source_wp.get("schema")
        stripped_data = self._strip_business_data(
            copy.deepcopy(source_data), schema
        )

        # 构建目标记录
        result = CopyResult(
            source_wp_code=wp_code,
            target_wp_id=new_wp_id,
            status="copied",
            message=None,
        )

        # 附加目标记录数据（作为额外属性供调用方使用）
        result.target_record = {  # type: ignore[attr-defined]
            "wp_id": new_wp_id,
            "wp_code": wp_code,
            "wp_name": source_wp.get("wp_name", ""),
            "audit_cycle": source_wp.get("audit_cycle", ""),
            "project_id": target_project_id,
            "status": "draft",
            "review_status": "not_submitted",
            "is_deleted": False,
            "file_version": 1,
            "data": stripped_data,
            "source_wp_id": source_wp.get("wp_id"),
            "source_project_id": source_wp.get("project_id"),
        }

        return result

    def copy_cycle(
        self,
        source_workpapers: list[dict],
        target_project_id: UUID,
        audit_cycle: str,
        overwrite: bool = False,
        existing_codes: set[str] | None = None,
    ) -> list[CopyResult]:
        """批量复制整个审计循环的全部底稿。

        Args:
            source_workpapers: 源项目底稿列表（含全部循环，由本方法过滤）
            target_project_id: 目标项目 ID
            audit_cycle: 要复制的审计循环代号
            overwrite: 是否覆盖
            existing_codes: 目标项目已有 wp_code 集合

        Returns:
            list[CopyResult] 每份底稿的复制结果
        """
        # 过滤指定循环的非删除底稿
        cycle_wps = [
            wp for wp in source_workpapers
            if wp.get("audit_cycle") == audit_cycle
            and not wp.get("is_deleted", False)
        ]

        results = []
        for wp in cycle_wps:
            result = self.copy_single(
                source_wp=wp,
                target_project_id=target_project_id,
                overwrite=overwrite,
                existing_codes=existing_codes,
            )
            results.append(result)

        return results

    def _strip_business_data(
        self,
        data: dict,
        schema: dict | None = None,
    ) -> dict:
        """清除业务数据，保留结构和程序步骤。

        清除规则：
        - dynamic_table 区域的数值列（金额/余额）→ None
        - 日期列内容 → None
        - 具体描述文字（备注/结论/说明，非只读文本列）→ None

        保留：
        - sheet 结构和名称
        - 固定表头和标题行
        - 程序步骤编号和描述（只读列）
        - 公式（以 = 开头的字符串）
        - 列定义/schema 结构本身
        """
        if not data:
            return data

        if schema:
            # 有 schema 时按列定义精确清除
            self._strip_with_schema(data, schema)
        else:
            # 无 schema 时用启发式规则清除
            self._strip_heuristic(data)

        return data

    def _strip_with_schema(self, data: dict, schema: dict) -> None:
        """按 schema 列定义精确清除业务数据。

        schema 结构示例:
        {
            "sheets": {
                "Sheet1": {
                    "dynamic_table": {
                        "columns": {
                            "B": {"field": "amount", "type": "number", "readonly": false},
                            "C": {"field": "procedure_code", "type": "text", "readonly": true},
                        },
                        "start_row": 3
                    }
                }
            }
        }
        """
        sheets_schema = schema.get("sheets", {})

        for sheet_name, sheet_schema in sheets_schema.items():
            if not isinstance(sheet_schema, dict):
                continue

            table_cfg = sheet_schema.get("dynamic_table", {})
            if not table_cfg:
                continue

            columns = table_cfg.get("columns", {})
            clearable_fields = set()

            for col_letter, col_def in columns.items():
                if isinstance(col_def, dict):
                    is_readonly = col_def.get("readonly", False)
                    col_type = col_def.get("type", "text")
                    field_name = col_def.get("field", "")

                    # 只读列保留（程序编号、描述）
                    if is_readonly:
                        continue

                    # 数值/日期/非只读文本列 → 清除
                    if col_type in ("number", "date", "text"):
                        if field_name:
                            clearable_fields.add(field_name)

            # 清除 data 中对应字段
            self._clear_fields_in_data(data, sheet_name, clearable_fields)

    def _clear_fields_in_data(
        self,
        data: dict,
        sheet_name: str,
        clearable_fields: set[str],
    ) -> None:
        """清除 data 中指定 sheet 的指定字段值。

        data 可能的结构:
        - data[sheet_name]["rows"] = [{field: value, ...}, ...]
        - data["html_data"][sheet_name]["rows"] = [...]
        - data["rows"] = [...] (单 sheet 模式)
        """
        if not clearable_fields:
            return

        # 尝试多种数据布局
        targets = []

        # 布局1: data[sheet_name]["rows"]
        if sheet_name in data and isinstance(data[sheet_name], dict):
            rows = data[sheet_name].get("rows", [])
            if rows:
                targets.append(rows)

        # 布局2: data["html_data"][sheet_name]["rows"]
        html_data = data.get("html_data", {})
        if sheet_name in html_data and isinstance(html_data[sheet_name], dict):
            rows = html_data[sheet_name].get("rows", [])
            if rows:
                targets.append(rows)

        # 布局3: data["rows"]（单 sheet）
        if "rows" in data and isinstance(data["rows"], list) and not targets:
            targets.append(data["rows"])

        # 清除字段
        for rows in targets:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for field_name in clearable_fields:
                    if field_name in row:
                        value = row[field_name]
                        # 保留公式
                        if isinstance(value, str) and value.startswith("="):
                            continue
                        row[field_name] = None

    def _strip_heuristic(self, data: dict) -> None:
        """无 schema 时的启发式清除。

        清除规则：
        - 数值类型值 → None
        - 日期类型值 → None
        - 文本字段名含 amount/date/balance/total/备注/结论/说明 → None
        - 保留公式（= 开头字符串）
        - 保留 code/name/编号/名称 类字段
        """
        _CLEARABLE_PATTERNS = {
            "amount", "balance", "total", "sum", "debit", "credit",
            "unadjusted", "adjustment", "audited", "date", "period",
            "备注", "结论", "说明", "描述", "金额", "余额", "日期",
        }
        _PRESERVE_PATTERNS = {
            "code", "name", "编号", "名称", "procedure", "程序",
            "id", "type", "status", "readonly",
        }

        def should_clear_field(field_name: str) -> bool:
            lower = field_name.lower()
            # 保留类字段不清除
            for pat in _PRESERVE_PATTERNS:
                if pat in lower:
                    return False
            # 清除类字段
            for pat in _CLEARABLE_PATTERNS:
                if pat in lower:
                    return True
            return False

        def should_clear_value(value: Any) -> bool:
            """值级判断：数值/日期清除"""
            if isinstance(value, (int, float)):
                return True
            if isinstance(value, (date, datetime)):
                return True
            return False

        def clear_rows(rows: list) -> None:
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key in list(row.keys()):
                    value = row[key]
                    # 保留公式
                    if isinstance(value, str) and value.startswith("="):
                        continue
                    # 按字段名清除
                    if should_clear_field(key):
                        row[key] = None
                    # 按值类型清除
                    elif should_clear_value(value):
                        row[key] = None

        # 遍历所有可能的 rows 位置
        if "rows" in data and isinstance(data["rows"], list):
            clear_rows(data["rows"])

        if "html_data" in data and isinstance(data["html_data"], dict):
            for sheet_name, sheet_data in data["html_data"].items():
                if isinstance(sheet_data, dict) and "rows" in sheet_data:
                    clear_rows(sheet_data["rows"])

        # 顶层 sheet 直接存储
        for key, value in data.items():
            if key in ("rows", "html_data"):
                continue
            if isinstance(value, dict) and "rows" in value:
                clear_rows(value["rows"])
