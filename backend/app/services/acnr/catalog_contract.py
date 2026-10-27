"""ACNR 目录契约——单一机器可读来源（design §4.2 / D3）。

`global_catalog.schema.json` 不再手写：由本模块 `build_schema()` 生成。四类受控常量
（functional_type / purpose 模式 / registry_version 模式 / 枚举集合）只在这里定义一次，
schema、门禁、测试从这里取。现状（段四审计 F4-13 更正）：已提交的 schema 文件由
`tests/acnr/test_catalog_schema_single_source.py` 与 `build_schema()` 逐字节比对；
生成器同批写出 schema 并在 `--check` 里比对随 T07 落地，目前生成器还不读本模块。

只依赖标准库（CI 无需新增依赖）。校验用 `jsonschema==4.26.0`（见 requirements.txt）。
"""
from __future__ import annotations

# ─── 受控常量（唯一来源） ────────────────────────────────────────────────────

#: registry_version 形态：UTC 时间戳 %Y%m%d%H%M%S（14 位数字）。
REGISTRY_VERSION_PATTERN = r"^\d{14}$"

#: functional_type 受控词表（缺省时省略字段）。现算真实目录 10 种 + 838 缺省。
FUNCTIONAL_TYPES: list[str] = [
    "impairment",
    "confirmation",
    "detail_table",
    "sampling",
    "aging",
    "monthly_analysis",
    "cutoff",
    "reconciliation",
    "depreciation",
    "amortization",
]

#: purpose 受控模式（183 种长尾自由值，无按取值分支的消费方，列词表只是冻结噪声）。
PURPOSE_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

#: source_of_truth 受控集合：classification_db（骨架）+ sheet_verdicts（补登/停用）。
SOURCE_OF_TRUTH: list[str] = ["classification_db", "sheet_verdicts"]

#: editor_engine 受控集合（现值 html 1198 / univer 16 / onlyoffice 1）。
EDITOR_ENGINES: list[str] = ["html", "univer", "onlyoffice", "mixed"]

#: skip_reason 受控集合（null + 7 种；现值全为 null）。
SKIP_REASONS: list = [
    None,
    "no_import_export",
    "univer_only",
    "onlyoffice_only",
    "procedure_checkbox",
    "word_template",
    "readonly_directory",
    "custom_univer_only",
]

#: 不允许出现项目态字段（L1 目录不含 project_id / wp_id）。
NOT_PROJECT_CTX = {"required": ["project_id", "wp_id"]}

# ─── 地址形态（与 exact_identity 的 A1 口径一致） ────────────────────────────

_SHEET_ADDR_ID_PATTERN = r"^[A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+$"
_CELL_ADDR_ID_PATTERN = (
    r"^([A-S][A-Za-z0-9-]*/[A-Za-z0-9-]+/[A-Za-z0-9_-]+"
    r"|note/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+)$"
)


# ─── schema 构建 ─────────────────────────────────────────────────────────────


def _sheet_entry() -> dict:
    return {
        "type": "object",
        "description": "L1 主条目，Tab/sheet 粒度；addr_id 无坐标后缀（如 D2/D2-2）",
        "required": ["addr_id", "domain", "parent_wp_code", "sheet_code", "sheet_name"],
        "not": NOT_PROJECT_CTX,
        "properties": {
            "addr_id": {
                "type": "string",
                "description": "Sheet 级主键，格式 {parent}/{sheet_code}（如 D2/D2-2）",
                "pattern": _SHEET_ADDR_ID_PATTERN,
            },
            "domain": {"type": "string", "enum": ["wp"], "description": "域标识，首期仅 wp"},
            "origin": {
                "type": "string",
                "enum": ["standard", "custom"],
                "description": "来源标识：标准底稿或自定义",
            },
            "cycle": {"type": "string", "description": "循环码（如 D、E、F）", "pattern": r"^[A-S]$"},
            "parent_wp_code": {
                "type": "string",
                "description": "循环 bundle / 父底稿码（= WP() 第一参，如 D2）",
                "pattern": r"^[A-S][A-Za-z0-9-]*$",
            },
            "sheet_code": {
                "type": "string",
                "description": "Tab 编码（= API ?sheet=，如 D2-2）",
                "pattern": r"^[A-Za-z0-9-]+$",
            },
            "sheet_name": {"type": "string", "description": "权威中文 Tab 名（源=classification）"},
            "sheet_name_aliases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "别名反查来源（平台底稿名 + labels）",
            },
            "component_type": {"type": "string", "description": "前端渲染类型（如 d2-accounts-receivable）"},
            "class_code": {"type": "string", "description": "分类码（如 F-明细表）"},
            "functional_type": {
                "type": "string",
                "enum": list(FUNCTIONAL_TYPES),
                "description": "功能类型（受控词表；缺省时省略本字段）",
            },
            "editor_engine": {
                "type": "string",
                "enum": list(EDITOR_ENGINES),
                "description": "编辑器引擎类型",
            },
            "sheet_key_source": {"type": "string", "description": "html_data 键 / snapshot 键来源说明"},
            "import_export": {
                "type": ["object", "null"],
                "description": "导入导出配置（null 表示不支持）",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "api_prefix": {"type": "string"},
                    "item_id": {
                        "description": "单值或多值 item_id",
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "uniqueItems": True,
                            },
                        ],
                    },
                    "storage_field": {"type": "string"},
                    "import_order": {"type": "integer"},
                    "depends_on_sheets": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["enabled", "api_prefix", "item_id"],
            },
            "skip_reason": {
                "type": ["string", "null"],
                "enum": list(SKIP_REASONS),
                "description": "非空则 bulk manifest 排除",
            },
            "deprecated": {
                "type": "boolean",
                "description": "停用标记（保留 >=1 registry_version）",
                "default": False,
            },
            "deprecated_at_version": {
                "type": "string",
                "description": "首次停用的 registry_version",
            },
            "replaced_by": {
                "type": "string",
                "description": "停用后建议改用的 addr_id（可解析）",
            },
            "display_label": {
                "type": "string",
                "description": "统一显示名（底稿 > {父} > {sheet}，design §13）",
            },
            "jump_route_template": {"type": "string", "description": "跳转模板，{wp_id} 由 ProjectBinding 填充"},
            "registry_version": {"type": "string", "description": "catalog 版本号"},
            "template_version_id": {"type": "string", "description": "来自 classification 的模板版本 ID"},
            "source_of_truth": {
                "type": "string",
                "enum": list(SOURCE_OF_TRUTH),
                "description": "权威来源标识",
            },
        },
        "additionalProperties": False,
    }


def _cell_entry() -> dict:
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
                "pattern": _CELL_ADDR_ID_PATTERN,
            },
            "parent_addr_id": {
                "type": "string",
                "description": "FK -> SheetCatalogEntry（如 D2/D2-2）",
                "pattern": _SHEET_ADDR_ID_PATTERN,
            },
            "uri": {"type": "string", "description": "Standard profile URI（如 wp://D2/明细表D2-2#E100）"},
            "domain": {"type": "string", "enum": ["wp"], "description": "域标识，首期仅 wp"},
            "cell_address": {
                "type": ["string", "null"],
                "description": "A1 坐标（如 E100）；semantic_only 时为 null",
                "pattern": r"^[A-Z]+[0-9]+$",
            },
            "semantic_label": {"type": ["string", "null"], "description": "语义名（如 合计行-期末余额）"},
            "semantic_only": {
                "type": "boolean",
                "description": "true = 尚无可靠 A1，公式仍可引用语义",
                "default": False,
            },
            "purpose": {
                "type": ["string", "null"],
                "pattern": PURPOSE_PATTERN,
                "description": "坐标用途分类（受控模式）",
            },
            "formula_ref": {"type": "string", "description": "公式引用"},
            "deprecated": {
                "type": "boolean",
                "description": "停用标记（保留 >=1 registry_version）",
                "default": False,
            },
            "replaced_by": {"type": "string", "description": "停用后建议改用的 addr_id（父 sheet）"},
            "display_label": {"type": "string", "description": "统一显示名（design §13）"},
            "cell_label": {"type": "string", "description": "单元格显示标签（如 {A1}（语义待核对））"},
            "registry_version": {"type": "string", "description": "catalog 版本号"},
        },
        "additionalProperties": False,
    }


def build_schema() -> dict:
    """生成 global_catalog.schema.json（Draft-07）。唯一来源。"""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://audit-platform.internal/acnr/global_catalog.schema.json",
        "title": "ACNR Global Catalog",
        "description": (
            "L1 全局目录 schema — 标准底稿全量 sheet + 坐标种子"
            "（首期仅 wp 域静态 JSON）。不含 project_id / wp_id。"
        ),
        "type": "object",
        "required": ["version", "registry_version", "sheets", "cells"],
        "not": NOT_PROJECT_CTX,
        "properties": {
            "version": {"const": "1", "description": "Schema 版本，当前固定为 1"},
            "registry_version": {
                "type": "string",
                "description": "Catalog 版本号（UTC 时间戳，14 位数字），用于版本锁定解析",
                "pattern": REGISTRY_VERSION_PATTERN,
            },
            "alias_policy": {
                "type": "object",
                "description": "顶层别名处置：禁止别名集合（design §7.2）",
                "properties": {
                    "forbidden": {
                        "type": "object",
                        "description": "{parent_wp_code: {alias: [sheet_code...]}}",
                        "additionalProperties": {
                            "type": "object",
                            "additionalProperties": {"type": "array", "items": {"type": "string"}},
                        },
                    }
                },
                "additionalProperties": False,
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
            "SheetCatalogEntry": _sheet_entry(),
            "CellCatalogEntry": _cell_entry(),
        },
    }


def schema_json(schema: dict | None = None) -> str:
    """确定性序列化（与生成器输出口径一致：indent=2、保留中文、尾换行）。"""
    import json

    return json.dumps(schema or build_schema(), indent=2, ensure_ascii=False) + "\n"


__all__ = [
    "REGISTRY_VERSION_PATTERN",
    "FUNCTIONAL_TYPES",
    "PURPOSE_PATTERN",
    "SOURCE_OF_TRUTH",
    "EDITOR_ENGINES",
    "SKIP_REASONS",
    "NOT_PROJECT_CTX",
    "build_schema",
    "schema_json",
]
