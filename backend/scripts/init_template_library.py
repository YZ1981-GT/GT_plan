"""模板库初始化脚本

从 gt_template_library.json 和报告模板种子数据批量注册到 template_library 表。

用法：python backend/scripts/init_template_library.py
"""

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DB_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform"
engine = create_engine(DB_URL)

# 确保表存在
from app.models.base import Base
from app.models.template_library_models import TemplateLibraryItem, TemplateLevel, TemplateType
Base.metadata.create_all(engine, tables=[TemplateLibraryItem.__table__])


def load_workpaper_templates():
    """从 gt_template_library.json 加载底稿模板"""
    lib_path = Path(__file__).parent.parent / "data" / "gt_template_library.json"
    if not lib_path.exists():
        print(f"  gt_template_library.json not found, skipping workpaper templates")
        return []

    raw = json.loads(lib_path.read_text(encoding="utf-8"))
    # 支持两种格式：直接数组 或 {templates: [...]} 包装对象
    if isinstance(raw, dict):
        data = raw.get("templates", [])
    else:
        data = raw

    templates = []
    for item in data:
        if not isinstance(item, dict):
            continue
        templates.append({
            "name": item.get("name", item.get("wp_name", "")),
            "template_type": TemplateType.workpaper_preset,
            "level": TemplateLevel.firm_default,
            "wp_code": item.get("code", item.get("wp_code", "")),
            "audit_cycle": item.get("cycle_prefix", item.get("audit_cycle", "")),
            "file_path": item.get("file_path", ""),
            "description": item.get("description", ""),
        })
    return templates


def load_report_templates():
    """注册报告模板（国企版+上市版 × 合并+单体）"""
    return [
        {"name": "审计报告-国企版-合并", "template_type": TemplateType.report_soe,
         "level": TemplateLevel.firm_default, "report_scope": "consolidated",
         "description": "致同标准国企版合并审计报告模板"},
        {"name": "审计报告-国企版-单体", "template_type": TemplateType.report_soe,
         "level": TemplateLevel.firm_default, "report_scope": "standalone",
         "description": "致同标准国企版单体审计报告模板"},
        {"name": "审计报告-上市版-合并", "template_type": TemplateType.report_listed,
         "level": TemplateLevel.firm_default, "report_scope": "consolidated",
         "description": "致同标准上市版合并审计报告模板"},
        {"name": "审计报告-上市版-单体", "template_type": TemplateType.report_listed,
         "level": TemplateLevel.firm_default, "report_scope": "standalone",
         "description": "致同标准上市版单体审计报告模板"},
    ]


def main():
    with Session(engine) as session:
        # 检查是否已初始化
        existing = session.query(TemplateLibraryItem).filter(
            TemplateLibraryItem.level == TemplateLevel.firm_default.value
        ).count()

        if existing > 0:
            print(f"Template library already has {existing} firm templates, skipping.")
            return

        # 加载底稿模板
        wp_templates = load_workpaper_templates()
        print(f"Loading {len(wp_templates)} workpaper templates...")

        for t in wp_templates:
            item = TemplateLibraryItem(
                name=t["name"],
                template_type=t["template_type"],
                level=t["level"],
                wp_code=t.get("wp_code"),
                audit_cycle=t.get("audit_cycle"),
                file_path=t.get("file_path"),
                description=t.get("description"),
            )
            session.add(item)

        # 加载报告模板
        report_templates = load_report_templates()
        print(f"Loading {len(report_templates)} report templates...")

        for t in report_templates:
            item = TemplateLibraryItem(
                name=t["name"],
                template_type=t["template_type"],
                level=t["level"],
                report_scope=t.get("report_scope"),
                description=t.get("description"),
            )
            session.add(item)

        session.commit()
        total = len(wp_templates) + len(report_templates)
        print(f"Done: {total} templates registered ({len(wp_templates)} workpaper + {len(report_templates)} report)")


if __name__ == "__main__":
    main()
    engine.dispose()
