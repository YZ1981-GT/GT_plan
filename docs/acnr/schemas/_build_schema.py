"""Deterministic builder for global_catalog.schema.json (draft-07).

fs_write refuses to write $schema files directly in supervised mode, so we
emit the schema deterministically from a Python dict via json.dump.

Covers Requirements: R8.1-R8.6, R20.1
- SheetCatalogEntry / CellCatalogEntry 完整字段定义
- addr_id pattern 强约束
- 顶层 + 两类条目均带 not.required: [project_id, wp_id] (R6.4)
- additionalProperties: false 防止未声明字段混入
"""
import json
from pathlib import Path

NOT_PROJECT_CTX = {"required": ["project_id", "wp_id"]}


def _build_sheet_entry() -> dict:
    """SheetCatalogEntry definition (R8.1, R8.6)."""
    return {
        "type": "object",
        "description": "L1 主条目，Tab/sheet 粒度；addr_id 无坐标后缀（如 D2/D2-2）",
        "required": [
            "addr_id",
            "domain",
            "parent_wp_code",
            "sheet_code",
            "sheet_name",
        ],
        "not": NOT_PROJECT_CTX,
        "properties": {
            "addr_id": {
                "type": "string",
                "description": "Sheet 级主键，格式 {parent}/{sheet_code}（如 D2/D2-2）",
                "pattern": "^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$",
            },
            "domain": {
                "type": "string",
                "enum": ["wp"],
                "description": "域标识，首期仅 wp 进 L1 JSON",
            },
            "origin": {
                "type": "string",
                "enum": ["standard", "custom"],
                "description": "来源标识：标准底稿或自定义",
            },
            "cycle": {
                "type": "string",
                "description": "循环码（如 D、E、F）",
                "pattern": "^[A-S]$",
            },
            "parent_wp_code": {
                "type": "string",
                "description": "循环 bundle / 父底稿码（= WP() 第一参，如 D2）",
                "pattern": "^[A-S][A-Za-z0-9-]*$",
            },
            "sheet_code": {
                "type": "string",
                "description": "Tab 编码（= API ?sheet=，如 D2-2）",
                "pattern": "^[A-Za-z0-9-]+$",
            },
            "sheet_name": {
                "type": "string",
                "description": "权威中文 Tab 名（源=classification，R20.2 R-NAME）",
            },
            "sheet_name_aliases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "别名反查来源（ingest 自 labels + classification 展示名）",
            },
            "component_type": {
                "type": "string",
                "description": "前端渲染类型（如 d2-accounts-receivable）",
            },
            "class_code": {
                "type": "string",
                "description": "分类码（如 F-明细表）",
            },
            "functional_type": {
                "type": "string",
                "enum": [
                    "procedure_table",
                    "adjudication_table",
                    "detail_table",
                    "check_table",
                    "analysis_table",
                    "directory",
                    "note_disclosure",
                    "custom",
                ],
                "description": "功能类型枚举",
            },
            "editor_engine": {
                "type": "string",
                "enum": ["html", "univer", "onlyoffice", "mixed"],
                "description": "编辑器引擎类型",
            },
            "sheet_key_source": {
                "type": "string",
                "description": "html_data 键 / snapshot 键来源说明",
            },
            "import_export": {
                "type": ["object", "null"],
                "description": "导入导出配置（null 表示不支持导入导出）",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "api_prefix": {"type": "string"},
                    "item_id": {"type": "string"},
                    "storage_field": {"type": "string"},
                    "import_order": {"type": "integer"},
                    "depends_on_sheets": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["enabled", "api_prefix", "item_id"],
            },
            "skip_reason": {
                "type": ["string", "null"],
                "enum": [
                    None,
                    "no_import_export",
                    "univer_only",
                    "onlyoffice_only",
                    "procedure_checkbox",
                    "word_template",
                    "readonly_directory",
                    "custom_univer_only",
                ],
                "description": "非空则 bulk manifest 排除（完全阻止本次 manifest 生成）",
            },
            "display_label": {
                "type": "string",
                "description": "展示路径（如 底稿 > D2 > 明细表D2-2）",
            },
            "jump_route_template": {
                "type": "string",
                "description": "跳转模板，{wp_id} 由 ProjectBinding 填充",
            },
            "registry_version": {
                "type": "string",
                "description": "catalog 版本号",
            },
            "template_version_id": {
                "type": "string",
                "description": "来自 classification 的模板版本 ID",
            },
            "source_of_truth": {
                "type": "string",
                "description": "权威来源标识（如 classification_db）",
            },
        },
        "additionalProperties": False,
    }


def _build_cell_entry() -> dict:
    """CellCatalogEntry definition (R8.2, R8.3, R8.4)."""
    return {
        "type": "object",
        "description": (
            "L1 坐标子条目，单元格/语义锚点粒度；addr_id 含坐标后缀"
            "（如 D2/D2-2/E100 或 note/{note_code}/{row_key}）"
        ),
        "required": ["addr_id", "parent_addr_id", "domain", "formula_ref"],
        "not": NOT_PROJECT_CTX,
        "properties": {
            "addr_id": {
                "type": "string",
                "description": (
                    "Cell 级主键。有 cell_address 时为 {parent}/{sheet_code}/{cell_address}；"
                    "semantic_only 时为 {parent}/{sheet_code}/{slug(semantic_label)}；"
                    "note 子域为 note/{note_code}/{row_key}"
                ),
                "pattern": "^([A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+/[A-Za-z0-9_-]+|note/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+)$",
            },
            "parent_addr_id": {
                "type": "string",
                "description": "FK -> SheetCatalogEntry（如 D2/D2-2）",
                "pattern": "^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$",
            },
            "uri": {
                "type": "string",
                "description": "Standard profile URI（如 wp://D2/明细表D2-2#E100）",
            },
            "domain": {
                "type": "string",
                "enum": ["wp"],
                "description": "域标识，首期仅 wp（note 子域坐标见 R16.2）",
            },
            "cell_address": {
                "type": ["string", "null"],
                "description": "A1 坐标（如 E100）；semantic_only 时为 null",
                "pattern": "^[A-Z]+[0-9]+$",
            },
            "semantic_label": {
                "type": ["string", "null"],
                "description": "语义名（如 合计行-期末余额）",
            },
            "semantic_only": {
                "type": "boolean",
                "description": "true = 尚无可靠 A1，公式仍可引用语义；CI 标记须尽快补 A1",
                "default": False,
            },
            "purpose": {
                "type": ["string", "null"],
                "enum": [
                    None,
                    "balance_verification",
                    "conclusion",
                    "ratio_analysis",
                    "total_row",
                    "adjustment",
                    "cross_reference",
                    "disclosure",
                ],
                "description": "坐标用途分类",
            },
            "formula_ref": {
                "type": "string",
                "description": "公式引用（如 WP('D2','明细表D2-2','合计行-期末余额')）",
            },
            "deprecated": {
                "type": "boolean",
                "description": "弃用标记（保留 >=1 registry_version，R19.3）",
                "default": False,
            },
            "registry_version": {
                "type": "string",
                "description": "catalog 版本号",
            },
        },
        "additionalProperties": False,
    }


def build_schema() -> dict:
    """Build the complete global_catalog.schema.json."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://audit-platform.internal/acnr/global_catalog.schema.json",
        "title": "ACNR Global Catalog",
        "description": (
            "L1 全局目录 schema — 标准底稿全量 sheet + 坐标种子"
            "（首期仅 wp 域静态 JSON）。不含 project_id / wp_id（R6.4）。"
        ),
        "type": "object",
        "required": ["version", "registry_version", "sheets", "cells"],
        "not": NOT_PROJECT_CTX,
        "properties": {
            "version": {
                "const": "1",
                "description": "Schema 版本，当前固定为 1",
            },
            "registry_version": {
                "type": "string",
                "description": "Catalog 版本号，归档项目创建时记录，用于版本锁定解析",
                "pattern": "^\\d{4}\\.\\d+\\.\\d+$",
            },
            "sheets": {
                "type": "array",
                "description": "SheetCatalogEntry 列表（Tab/sheet 粒度）",
                "items": {"$ref": "#/$defs/SheetCatalogEntry"},
            },
            "cells": {
                "type": "array",
                "description": "CellCatalogEntry 列表（单元格/语义锚点粒度）",
                "items": {"$ref": "#/$defs/CellCatalogEntry"},
            },
        },
        "additionalProperties": False,
        "$defs": {
            "SheetCatalogEntry": _build_sheet_entry(),
            "CellCatalogEntry": _build_cell_entry(),
        },
    }


if __name__ == "__main__":
    schema = build_schema()
    out = Path(__file__).with_name("global_catalog.schema.json")
    out.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out.stat().st_size} bytes -> {out}")
