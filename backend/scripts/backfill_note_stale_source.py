"""
stale_source 历史数据回填脚本（非迁移文件）。

对 is_stale=true AND stale_source IS NULL 的 disclosure_notes 行，
按保守规则回填 stale_source：
  - 有 REPORT linkage（Cell_Binding 或 report_note_linkage.json 配置）→ 'report'
  - 否则 → 'report_fallback'（保守，绝不臆造 'report'；Req4.4）

用法：
  cd backend
  python -m scripts.backfill_note_stale_source --dry-run   # 默认，只报计数
  python -m scripts.backfill_note_stale_source --apply      # 真正写库

幂等性（Req4.2）：
  WHERE stale_source IS NULL 天然幂等；重跑不改已有非空 stale_source。
  is_stale=false 的行不在 WHERE 集内（Req4.3）。

非迁移文件（Req4.5）：避免与并发迁移编号冲突。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ---------------------------------------------------------------------------
# REPORT linkage 判定（只读）
# ---------------------------------------------------------------------------

_LINKAGE_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "disclosure"
    / "report_note_linkage.json"
)


def _load_linkage_config_sections() -> set[str]:
    """从 report_note_linkage.json 读取有配置映射的 note_section 集合。"""
    try:
        if not _LINKAGE_CONFIG_PATH.exists():
            return set()
        with open(_LINKAGE_CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return set()
        sections: set[str] = set()
        for _row_code, entries in raw.items():
            if not isinstance(_row_code, str) or _row_code.startswith("_"):
                continue
            if not isinstance(entries, list):
                continue
            for e in entries:
                if isinstance(e, dict):
                    ns = e.get("note_section")
                    if isinstance(ns, str) and ns:
                        sections.add(ns)
        return sections
    except Exception as err:
        logger.warning("load linkage config failed: %s; treat as empty", err)
        return set()


async def _load_binding_sections(session: AsyncSession) -> set[str]:
    """
    扫描 disclosure_notes 的 table_data 中含 REPORT Cell_Binding 的 note_section。

    Cell_Binding 在 table_data 的 rows/tables[].rows 里：
      row._cell_meta[col].binding.source == 'report'
    """
    # 用 JSONB 操作符在 DB 侧粗过滤含 "report" 的 table_data，
    # 再在 Python 侧精确验证（避免全量拉取）
    query = text("""
        SELECT DISTINCT note_section
        FROM disclosure_notes
        WHERE is_deleted = false
          AND table_data IS NOT NULL
          AND table_data::text LIKE '%"source"%'
          AND table_data::text LIKE '%"report"%'
    """)
    result = await session.execute(query)
    candidates = {row[0] for row in result.fetchall()}

    # 对候选项做精确验证（检查 _cell_meta.*.binding.source == 'report'）
    if not candidates:
        return set()

    verified: set[str] = set()
    for section in candidates:
        check_q = text("""
            SELECT table_data
            FROM disclosure_notes
            WHERE is_deleted = false
              AND note_section = :section
              AND table_data IS NOT NULL
            LIMIT 1
        """)
        r = await session.execute(check_q, {"section": section})
        row = r.fetchone()
        if row and row[0] and _has_report_binding(row[0]):
            verified.add(section)

    return verified


def _has_report_binding(table_data: dict) -> bool:
    """检查 table_data 中是否含 source=='report' 的 Cell_Binding。"""
    if not isinstance(table_data, dict):
        return False

    def _check_rows(rows: list) -> bool:
        if not isinstance(rows, list):
            return False
        for row in rows:
            if not isinstance(row, dict):
                continue
            meta = row.get("_cell_meta")
            if not isinstance(meta, dict):
                continue
            for _col_key, slot in meta.items():
                if not isinstance(slot, dict):
                    continue
                binding = slot.get("binding")
                if isinstance(binding, dict) and binding.get("source") == "report":
                    return True
        return False

    # 检查顶层 rows
    if _check_rows(table_data.get("rows")):
        return True
    # 检查 _tables[].rows
    tables = table_data.get("_tables")
    if isinstance(tables, list):
        for tbl in tables:
            if isinstance(tbl, dict) and _check_rows(tbl.get("rows")):
                return True
    return False


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def run(*, apply: bool = False) -> None:
    """执行回填。apply=False 为 dry-run 只报计数。"""
    engine = create_async_engine(settings.DATABASE_URL, pool_size=5, max_overflow=0)
    async_session_factory = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session_factory() as session:
            # 1. 加载两类 REPORT linkage 真源
            config_sections = _load_linkage_config_sections()
            binding_sections = await _load_binding_sections(session)
            report_sections = config_sections | binding_sections

            logger.info(
                "REPORT linkage sections: config=%d, binding=%d, union=%d",
                len(config_sections),
                len(binding_sections),
                len(report_sections),
            )

            # 2. 查询需回填的行
            fetch_q = text("""
                SELECT id, note_section
                FROM disclosure_notes
                WHERE is_stale = true
                  AND stale_source IS NULL
                  AND is_deleted = false
            """)
            result = await session.execute(fetch_q)
            rows = result.fetchall()

            if not rows:
                logger.info("No rows to backfill (is_stale=true AND stale_source IS NULL = 0).")
                return

            # 3. 分类
            report_count = 0
            fallback_count = 0
            updates: list[tuple[UUID, str]] = []  # (id, stale_source)

            for row_id, note_section in rows:
                if note_section in report_sections:
                    source = "report"
                    report_count += 1
                else:
                    source = "report_fallback"
                    fallback_count += 1
                updates.append((row_id, source))

            logger.info(
                "Backfill target: %d rows (report=%d, report_fallback=%d)",
                len(updates),
                report_count,
                fallback_count,
            )

            # 4. 执行（dry-run 或 apply）
            if not apply:
                logger.info("[DRY-RUN] No changes written. Use --apply to execute.")
                return

            # 单条 UPDATE（安全，非批量）
            update_q = text("""
                UPDATE disclosure_notes
                SET stale_source = :source
                WHERE id = :id
                  AND stale_source IS NULL
            """)
            applied = 0
            for note_id, source in updates:
                r = await session.execute(
                    update_q, {"id": str(note_id), "source": source}
                )
                applied += r.rowcount

            await session.commit()
            logger.info(
                "[APPLIED] Updated %d rows (report=%d, report_fallback=%d).",
                applied,
                report_count,
                fallback_count,
            )

    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="回填 disclosure_notes.stale_source（is_stale=true AND stale_source IS NULL）"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="只读报告计数，不写库（默认）",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="真正执行回填写库",
    )
    args = parser.parse_args()

    # --apply 显式传入时覆盖 dry-run 默认
    apply = args.apply

    asyncio.run(run(apply=apply))


if __name__ == "__main__":
    main()
