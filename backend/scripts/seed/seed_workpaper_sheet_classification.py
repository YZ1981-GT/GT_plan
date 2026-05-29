"""
将 workpaper_template_analysis.json 全量灌入 workpaper_sheet_classification 表。

来源数据：.kiro/specs/workpaper-html-renderer/workpaper_template_analysis.json
（由 backend/scripts/analyze_wp_templates.py 扫描全部 xlsx 模板生成）

目标表：workpaper_sheet_classification
字段：(wp_code, sheet_name, class_code, class, scope, is_real_workpaper,
      exclude_from_archive, exclude_from_progress, is_static_doc,
      delegated_module, template_version_id, render_schema_path)

模板文件名 → wp_code 列表的解析规则：
- 单 wp_code: "A1 财务报告程序表.xlsx" → ['A1']
- 嵌套 wp_code: "A1-13 完成阶段分析性复核.xlsx" → ['A1-13']
- 范围（中文 至）: "D2-1至D2-4 应收账款.xlsx" → ['D2-1','D2-2','D2-3','D2-4']
- 范围（无空格）: "D4-13至D4-20主营业务收入...xlsx" → ['D4-13'..'D4-20']
- 子代码: "B22A 业务模式.xlsx" → ['B22A']
- _reference 目录跳过

class_code → componentType 派生由后端 derive_component_type 完成（本脚本只灌 class_code）。

幂等：每次运行先 TRUNCATE workpaper_sheet_classification（保留 template_version_id 关联），再批量 INSERT。
（不是用完即删的一次性脚本，模板更新后可重跑）

用法：
    python -m scripts.seed_workpaper_sheet_classification
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import text

from app.core.database import async_session
from app.models.workpaper_models import WorkpaperSheetClassification
from app.models.workpaper_template_version import WorkpaperTemplateVersion


ANALYSIS_JSON = Path(__file__).resolve().parent.parent.parent / ".kiro" / "specs" / "workpaper-html-renderer" / "workpaper_template_analysis.json"


# ─── class_code → 字段派生规则 ───────────────────────────────────────────────

def derive_extra_fields(class_code: str) -> dict:
    """根据 class_code 派生 is_real_workpaper / exclude_from_archive / is_static_doc / scope"""
    # H 类（辅助说明）和 I 类（占位）= 假底稿
    if class_code.startswith("H-"):
        return {
            "class_": "H",
            "is_real_workpaper": False,
            "exclude_from_archive": False,
            "exclude_from_progress": True,
            "is_static_doc": True,
            "scope": "standalone",
        }
    if class_code.startswith("I-"):
        return {
            "class_": "I",
            "is_real_workpaper": False,
            "exclude_from_archive": True,
            "exclude_from_progress": True,
            "is_static_doc": False,
            "scope": "standalone",
        }
    # A/B/C/D/E/F/G 类 = 真底稿
    return {
        "class_": class_code[0],
        "is_real_workpaper": True,
        "exclude_from_archive": False,
        "exclude_from_progress": False,
        "is_static_doc": False,
        "scope": "standalone",
    }


# ─── 文件名 → wp_code 列表解析 ───────────────────────────────────────────────

# 匹配带"至"的范围："D2-1至D2-4" / "D4-13至D4-20" / "E1-1至E1-11"
RANGE_PATTERN = re.compile(r"^([A-Z])(\d+)(?:-(\d+))?至(?:[A-Z])?(\d+)(?:-(\d+))?")
# 匹配单 wp_code："A1-13" / "A14-1" / "B22A" / "A17-5-1"
SINGLE_PATTERN = re.compile(r"^([A-Z]\d+(?:-\d+)*[A-Z]?)")


def parse_wp_codes_from_filename(filename: str) -> list[str]:
    """从文件名提取所有覆盖的 wp_code

    示例：
    - "A1 财务报告程序表.xlsx" → ['A1']
    - "A1-13 完成阶段...xlsx" → ['A1-13']
    - "D2-1至D2-4 应收账款...xlsx" → ['D2-1','D2-2','D2-3','D2-4']
    - "D4-13至D4-20主营业务收入...xlsx" → ['D4-13'..'D4-20']
    - "A17-5-1 审计工作完成核对表...xlsx" → ['A17-5-1']
    - "B22A 业务模式.xlsx" → ['B22A']
    - "S1 对被审计单位违反法规行为...xlsx" → ['S1']
    """
    # 范围模式（"X1-N至X1-M"）
    m = RANGE_PATTERN.match(filename)
    if m:
        letter = m.group(1)
        first_main = int(m.group(2))
        first_sub = int(m.group(3)) if m.group(3) else None
        last_main = int(m.group(4))
        last_sub = int(m.group(5)) if m.group(5) else None

        # 同一主编号内子编号范围（D2-1 至 D2-4）
        if first_sub is not None and last_sub is not None and first_main == last_main:
            return [f"{letter}{first_main}-{i}" for i in range(first_sub, last_sub + 1)]

        # 跨主编号（如 D2-6 至 D2-13）
        if first_sub is not None and last_sub is not None:
            # 仍按主编号 first_main 内子编号展开（first_main == last_main 是常见情况）
            if first_main == last_main:
                return [f"{letter}{first_main}-{i}" for i in range(first_sub, last_sub + 1)]
            # 极少见：跨主编号无子编号
            codes: list[str] = []
            for main in range(first_main, last_main + 1):
                codes.append(f"{letter}{main}")
            return codes

        # 单主编号范围（如 A1 至 A5）
        if first_sub is None and last_sub is None:
            return [f"{letter}{i}" for i in range(first_main, last_main + 1)]

    # 单 wp_code 模式
    m = SINGLE_PATTERN.match(filename)
    if m:
        return [m.group(1)]

    return []


# ─── 主入库逻辑 ──────────────────────────────────────────────────────────────

async def get_or_create_template_version(s) -> UUID:
    """获取 v2025-R5 当前版本（迁移已建表，但 V018 不会自动插数据，本脚本兜底插入）"""
    r = await s.execute(text("SELECT id FROM workpaper_template_version WHERE is_current = TRUE LIMIT 1"))
    row = r.first()
    if row:
        return row[0]

    # 自动创建 v2025-R5 当前版本
    print("[DB] workpaper_template_version 表为空，插入 v2025-R5 初始版本")
    r = await s.execute(text(
        "INSERT INTO workpaper_template_version (id, version, release_date, source, is_current, created_at) "
        "VALUES (gen_random_uuid(), 'v2025-R5', '2025-01-01', '致同总所', TRUE, NOW()) "
        "RETURNING id"
    ))
    new_id = r.scalar()
    await s.commit()
    return new_id


async def main():
    if not ANALYSIS_JSON.exists():
        print(f"[ERROR] Analysis JSON not found: {ANALYSIS_JSON}")
        print("Run: python backend/scripts/analyze_wp_templates.py")
        sys.exit(1)

    with ANALYSIS_JSON.open("r", encoding="utf-8") as f:
        analysis = json.load(f)

    # ─── Step 1: 收集所有 (wp_code, sheet_name, class_code) 三元组 ─────────
    records: list[dict] = []
    skip_pending = 0
    skip_unparseable = 0
    expanded_codes: set[str] = set()

    for cycle_key, cycle_data in analysis["cycles"].items():
        if cycle_key.startswith("_"):
            # _reference 目录跳过（参考资料，非真底稿）
            continue
        for tpl in cycle_data["templates"]:
            filename = tpl["filename"]
            wp_codes = parse_wp_codes_from_filename(filename)
            if not wp_codes:
                skip_unparseable += 1
                print(f"  [SKIP] 无法解析 wp_code: {cycle_key}/{filename}")
                continue

            for sheet in tpl["sheets"]:
                class_code = sheet["class"]
                if class_code == "_pending":
                    skip_pending += 1
                    continue
                # 同一模板内的 sheet 灌给所有覆盖的 wp_code
                for wp_code in wp_codes:
                    expanded_codes.add(wp_code)
                    records.append({
                        "wp_code": wp_code,
                        "sheet_name": sheet["name"],
                        "class_code": class_code,
                    })

    print(f"\n[STATS] 解析完成")
    print(f"  wp_codes 覆盖: {len(expanded_codes)}")
    print(f"  records: {len(records)}")
    print(f"  跳过 _pending: {skip_pending}")
    print(f"  跳过未解析: {skip_unparseable}")

    # 按 (wp_code, sheet_name) 去重（保留首次出现的 class_code）
    deduped: dict[tuple[str, str], dict] = {}
    for r in records:
        key = (r["wp_code"], r["sheet_name"])
        if key not in deduped:
            deduped[key] = r
    print(f"  去重后: {len(deduped)}")

    # ─── Step 2: 灌入数据库 ───────────────────────────────────────────────
    async with async_session() as s:
        version_id = await get_or_create_template_version(s)
        print(f"\n[DB] template_version_id = {version_id}")

        # 先清空（保留 template_version_id 关联，全量重灌）
        await s.execute(text("DELETE FROM workpaper_sheet_classification WHERE template_version_id = :vid"), {"vid": str(version_id)})
        await s.commit()
        print("[DB] 已清空 workpaper_sheet_classification（template_version_id 关联）")

        # 批量插入
        BATCH = 500
        rows = list(deduped.values())
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            insert_stmt = sa.insert(WorkpaperSheetClassification)
            payload = []
            for r in batch:
                fields = derive_extra_fields(r["class_code"])
                payload.append({
                    "wp_code": r["wp_code"],
                    "sheet_name": r["sheet_name"],
                    "class_code": r["class_code"],
                    "class_": fields["class_"],
                    "is_real_workpaper": fields["is_real_workpaper"],
                    "exclude_from_archive": fields["exclude_from_archive"],
                    "exclude_from_progress": fields["exclude_from_progress"],
                    "is_static_doc": fields["is_static_doc"],
                    "scope": fields["scope"],
                    "template_version_id": version_id,
                })
            await s.execute(insert_stmt, payload)
            await s.commit()
            print(f"  inserted {min(i + BATCH, len(rows))}/{len(rows)}")

        # ─── Step 3: 校验 ────────────────────────────────────────────────
        r = await s.execute(text("SELECT COUNT(*) FROM workpaper_sheet_classification"))
        total = r.scalar()
        print(f"\n[OK] workpaper_sheet_classification total: {total}")

        # 9 类分布
        r2 = await s.execute(text(
            "SELECT class, COUNT(*) FROM workpaper_sheet_classification "
            "WHERE template_version_id = :vid GROUP BY class ORDER BY class"
        ), {"vid": str(version_id)})
        print("\n[STATS] 9 类分布：")
        for row in r2:
            print(f"  {row[0]}: {row[1]}")

        # 抽查 D2-3
        r3 = await s.execute(text(
            "SELECT sheet_name, class_code FROM workpaper_sheet_classification "
            "WHERE wp_code = 'D2-3' AND template_version_id = :vid "
            "ORDER BY sheet_name"
        ), {"vid": str(version_id)})
        print("\n[CHECK] D2-3 sheets:")
        for row in r3:
            print(f"  {row[0]:<40} {row[1]}")


if __name__ == "__main__":
    asyncio.run(main())
