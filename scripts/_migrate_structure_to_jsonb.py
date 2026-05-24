"""一次性迁移脚本：structure.json → parsed_data['univer_snapshot'] 回填 + 删文件

Req 6（P2-10）structure.json 单源化：
  1. 扫描 storage/projects/ 下所有 *.structure.json 文件
  2. 对每个文件，找到对应 working_paper 记录
  3. 若 parsed_data['univer_snapshot'] 缺失，从 structure.json 内容回填
  4. 回填成功后物理删除 structure.json 文件
  5. 输出统计报告

用法：
  python scripts/_migrate_structure_to_jsonb.py [--dry-run]

注意：此脚本为一次性脚本（_ 前缀），执行完成后可删除。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# 确保 backend 在 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _structure_to_slim_snapshot(structure: dict) -> dict:
    """将 structure.json 格式转换为 slim univer_snapshot 格式

    structure.json 格式：
      rows: [{cells: [{value, formula, bold?}]}]  (跨 sheet 扁平化)
      sheets: [{name}]

    slim snapshot 格式：
      sheets: {sheet_name: {cellData: {row_0idx: {col_0idx: {v, f?}}}}}
      sheet_order_names: [name1, ...]
    """
    from datetime import datetime, timezone

    sheets_meta = structure.get("sheets", [])
    rows = structure.get("rows", [])
    sheet_names = [s.get("name", f"Sheet{i+1}") for i, s in enumerate(sheets_meta)]

    if not sheet_names:
        sheet_names = ["Sheet1"]

    # 简单策略：如果只有一个 sheet，所有 rows 归它
    # 多 sheet 时按 rows 均分（structure.json 没有 sheet 边界标记，只能近似）
    slim_sheets: dict[str, dict] = {}
    total_cells = 0

    if len(sheet_names) == 1:
        cell_data, count = _rows_to_cell_data(rows, 0, len(rows))
        slim_sheets[sheet_names[0]] = {"cellData": cell_data, "cell_count": count}
        total_cells += count
    else:
        # 多 sheet：按 sheet 数量均分 rows（近似，因 structure.json 无精确边界）
        rows_per_sheet = max(1, len(rows) // len(sheet_names)) if rows else 0
        offset = 0
        for i, name in enumerate(sheet_names):
            end = offset + rows_per_sheet if i < len(sheet_names) - 1 else len(rows)
            cell_data, count = _rows_to_cell_data(rows, offset, end)
            slim_sheets[name] = {"cellData": cell_data, "cell_count": count}
            total_cells += count
            offset = end

    return {
        "sheets": slim_sheets,
        "sheet_order_names": sheet_names,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "version": 0,
        "total_cells": total_cells,
        "migrated_from": "structure.json",
    }


def _rows_to_cell_data(rows: list, start: int, end: int) -> tuple[dict, int]:
    """将 structure rows[start:end] 转为 cellData 格式 (0-indexed)"""
    cell_data: dict[str, dict] = {}
    count = 0
    for r_idx, row in enumerate(rows[start:end]):
        cells = row.get("cells", [])
        row_dict: dict[str, dict] = {}
        for c_idx, cell in enumerate(cells):
            v = cell.get("value")
            f = cell.get("formula")
            obj: dict = {}
            if v is not None and v != "":
                obj["v"] = v
            if f:
                obj["f"] = f
            if obj:
                row_dict[str(c_idx)] = obj
                count += 1
        if row_dict:
            cell_data[str(r_idx)] = row_dict
    return cell_data, count


async def migrate(dry_run: bool = False) -> dict:
    """执行迁移"""
    from app.core.database import async_session

    storage_root = ROOT / "storage" / "projects"
    stats = {"scanned": 0, "backfilled": 0, "deleted": 0, "skipped": 0, "errors": []}

    # 扫描所有 .structure.json 文件
    structure_files: list[Path] = []
    if storage_root.exists():
        structure_files = list(storage_root.rglob("*.structure.json"))

    logger.info("找到 %d 个 structure.json 文件", len(structure_files))
    stats["scanned"] = len(structure_files)

    if not structure_files:
        logger.info("无需迁移")
        return stats

    async with async_session() as db:
        from sqlalchemy import text

        for sf in structure_files:
            try:
                # 从文件路径推断 wp 文件路径（structure.json 与 xlsx 同目录同名）
                xlsx_path = sf.with_suffix(".xlsx")
                if not xlsx_path.exists():
                    # 尝试 .xlsm
                    xlsx_path = sf.with_suffix(".xlsm")

                # 查找对应的 working_paper 记录
                # file_path 存的是相对或绝对路径，尝试多种匹配
                search_patterns = [
                    str(xlsx_path),
                    str(xlsx_path.relative_to(ROOT)) if xlsx_path.is_relative_to(ROOT) else str(xlsx_path),
                ]

                wp_row = None
                for pattern in search_patterns:
                    result = await db.execute(
                        text("SELECT id, parsed_data FROM working_paper WHERE file_path = :fp AND is_deleted = false LIMIT 1"),
                        {"fp": pattern},
                    )
                    wp_row = result.first()
                    if wp_row:
                        break

                if not wp_row:
                    logger.debug("未找到对应 working_paper: %s", sf)
                    stats["skipped"] += 1
                    continue

                wp_id = wp_row[0]
                parsed_data = wp_row[1] if isinstance(wp_row[1], dict) else {}

                # 检查是否已有 univer_snapshot
                existing_snap = parsed_data.get("univer_snapshot")
                if isinstance(existing_snap, dict) and existing_snap.get("sheets"):
                    logger.debug("已有 univer_snapshot，跳过: wp_id=%s", wp_id)
                    # 仍然删除 structure.json 文件
                    if not dry_run:
                        sf.unlink()
                        stats["deleted"] += 1
                    else:
                        logger.info("[DRY-RUN] 将删除: %s", sf)
                    continue

                # 读取 structure.json 内容
                content = json.loads(sf.read_text(encoding="utf-8"))

                # 转换为 slim snapshot 格式
                slim_snap = _structure_to_slim_snapshot(content)

                if not dry_run:
                    # 回填到 parsed_data
                    parsed_data["univer_snapshot"] = slim_snap
                    await db.execute(
                        text("UPDATE working_paper SET parsed_data = :pd WHERE id = :wid"),
                        {"pd": json.dumps(parsed_data, ensure_ascii=False), "wid": str(wp_id)},
                    )
                    stats["backfilled"] += 1

                    # 删除 structure.json 文件
                    sf.unlink()
                    stats["deleted"] += 1
                    logger.info("迁移成功: %s → wp_id=%s", sf.name, wp_id)
                else:
                    logger.info("[DRY-RUN] 将回填: %s → wp_id=%s (%d cells)", sf.name, wp_id, slim_snap["total_cells"])
                    stats["backfilled"] += 1

            except Exception as e:
                logger.error("迁移失败: %s — %s", sf, e)
                stats["errors"].append({"file": str(sf), "error": str(e)})

        if not dry_run:
            await db.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="structure.json → parsed_data['univer_snapshot'] 迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")
    args = parser.parse_args()

    stats = asyncio.run(migrate(dry_run=args.dry_run))

    print("\n" + "=" * 60)
    print("迁移统计:")
    print(f"  扫描文件数: {stats['scanned']}")
    print(f"  回填成功:   {stats['backfilled']}")
    print(f"  文件删除:   {stats['deleted']}")
    print(f"  跳过:       {stats['skipped']}")
    print(f"  错误:       {len(stats['errors'])}")
    if stats["errors"]:
        for err in stats["errors"][:10]:
            print(f"    - {err['file']}: {err['error']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
