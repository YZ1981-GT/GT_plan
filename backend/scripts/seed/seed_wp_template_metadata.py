"""种子数据脚本：从 wp_account_mapping.json 生成 wp_template_metadata 初始行

读取 backend/data/wp_account_mapping.json 的 88 条映射记录，
根据 wp_code 模式推断 component_type / audit_stage / cycle，
生成 wp_template_metadata 表的初始数据。

用法：
    python scripts/seed_wp_template_metadata.py

输出：
    backend/data/wp_template_metadata_seed.json（可用于 API 加载或直接 INSERT）
"""

import json
import sys
from pathlib import Path

# 确保可以从 backend/ 目录运行
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

# ---------------------------------------------------------------------------
# 审计阶段推断规则
# ---------------------------------------------------------------------------

# wp_code 首字母 → audit_stage 映射
_STAGE_MAP = {
    "B": "planning",       # 初步业务活动 / 风险评估
    "C": "risk_response",  # 风险应对—控制测试
    "D": "substantive",    # 实质性程序—收入循环
    "E": "substantive",    # 实质性程序—货币资金
    "F": "substantive",    # 实质性程序—存货/成本
    "G": "substantive",    # 实质性程序—投资
    "H": "substantive",    # 实质性程序—固定资产
    "I": "substantive",    # 实质性程序—无形资产
    "J": "substantive",    # 实质性程序—职工薪酬
    "K": "substantive",    # 实质性程序—管理/其他
    "L": "substantive",    # 实质性程序—债务
    "M": "substantive",    # 实质性程序—权益
    "N": "substantive",    # 实质性程序—税金
    "A": "completion",     # 完成阶段
    "S": "special",        # 特定项目程序
}

# ---------------------------------------------------------------------------
# 组件类型推断规则
# ---------------------------------------------------------------------------

# 默认所有 D-N 审定表用 Univer（含公式计算）
# 明细表/子表也用 Univer
# B 类用结构化表单
# A 类用混合视图


def _infer_component_type(wp_code: str, wp_name: str) -> str:
    """根据 wp_code 和 wp_name 推断组件类型"""
    first_char = wp_code[0].upper() if wp_code else "U"

    # B 类：业务承接/计划 → 结构化表单
    if first_char == "B":
        return "form"

    # A 类：完成阶段 → 混合视图
    if first_char == "A":
        return "hybrid"

    # C 类：控制测试 → 结构化表单
    if first_char == "C":
        return "form"

    # S 类：特定项目 → 混合视图
    if first_char == "S":
        return "hybrid"

    # D-N 类：实质性程序 → Univer（默认）
    # 函证清单等用 el-table
    if "函证" in wp_name or "清单" in wp_name:
        return "table"

    return "univer"


def _infer_file_format(wp_name: str) -> str:
    """推断文件格式"""
    if any(kw in wp_name for kw in ["约定书", "声明书", "沟通函", "备忘录"]):
        return "docx"
    return "xlsx"


def _infer_audit_stage(wp_code: str) -> str:
    """推断审计阶段"""
    first_char = wp_code[0].upper() if wp_code else "U"
    return _STAGE_MAP.get(first_char, "substantive")


def _infer_cycle(wp_code: str) -> str | None:
    """提取循环代码"""
    if not wp_code:
        return None
    first_char = wp_code[0].upper()
    # B/C/A/S 类没有科目循环
    if first_char in ("B", "C", "A", "S"):
        return None
    return first_char


def generate_metadata(mappings: list[dict]) -> list[dict]:
    """从 wp_account_mapping 生成 wp_template_metadata 种子数据"""
    results = []
    for m in mappings:
        wp_code = m.get("wp_code", "")
        wp_name = m.get("wp_name", "")
        account_codes = m.get("account_codes", [])
        note_section = m.get("note_section")

        metadata = {
            "wp_code": wp_code,
            "component_type": _infer_component_type(wp_code, wp_name),
            "audit_stage": _infer_audit_stage(wp_code),
            "cycle": _infer_cycle(wp_code),
            "file_format": _infer_file_format(wp_name),
            "procedure_steps": [],
            "guidance_text": None,
            "formula_cells": [],
            "required_regions": [],
            "linked_accounts": account_codes,
            "note_section": note_section,
            "conclusion_cell": None,
            "audit_objective": f"验证{wp_name}相关科目余额的真实性和完整性",
            "related_assertions": ["existence", "completeness", "valuation"],
            "procedure_flow_config": None,
        }
        results.append(metadata)

    return results


def main():
    """主入口"""
    mapping_file = DATA_DIR / "wp_account_mapping.json"
    if not mapping_file.exists():
        print(f"ERROR: {mapping_file} not found")
        sys.exit(1)

    with open(mapping_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    mappings = data.get("mappings", [])
    print(f"Loaded {len(mappings)} mappings from wp_account_mapping.json")

    metadata_list = generate_metadata(mappings)
    print(f"Generated {len(metadata_list)} wp_template_metadata entries")

    # 写入种子文件
    output_file = DATA_DIR / "wp_template_metadata_seed.json"
    output = {
        "description": "wp_template_metadata 种子数据（从 wp_account_mapping.json 自动生成）",
        "version": "2025-R1",
        "entries": metadata_list,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Seed data written to {output_file}")
    print(f"Total entries: {len(metadata_list)}")

    # 统计
    by_stage = {}
    by_type = {}
    for m in metadata_list:
        stage = m["audit_stage"]
        ctype = m["component_type"]
        by_stage[stage] = by_stage.get(stage, 0) + 1
        by_type[ctype] = by_type.get(ctype, 0) + 1

    print("\nBy audit_stage:")
    for k, v in sorted(by_stage.items()):
        print(f"  {k}: {v}")

    print("\nBy component_type:")
    for k, v in sorted(by_type.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
