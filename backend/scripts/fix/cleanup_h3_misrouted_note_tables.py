#!/usr/bin/env python
"""清理 H3 投资性房地产**误推到其它章节**的孤儿子表（存量修复，默认 dry-run）。

**背景**：`h3NoteSectionMap.H3_NOTE_SECTION.soe` 曾误写 `'八、22'`，而 `八、22` 是
**固定资产**章节（投资性房地产 soe 实为 `八、21`）→ H3 国企披露同步把投资性房地产的
子表写进了固定资产章节，污染另一循环的附注。章节号已修（spec Task 2），但**存量污染
不会自愈**（同步只清自己 `_removed_table_keys` 里的键，且新推送已不再落到 八、22）。

**清理范围（保守，宁漏不误杀）**：
仅删除满足**全部**条件的子表键：

1. 所在章节号 **不是** `五、21` / `八、21`（H3 的正确章节）；
2. 键名以 `投资性房地产（` 开头或命中 H3 历史载荷表名白名单 —— 即确定由 H3 旧载荷产生；
3. 该章节 `last_sync_wp_id` 对应底稿的 `wp_code` 为 `H3`（确认是 H3 推的）
   —— 该条可用 `--skip-wp-check` 放宽（历史记录可能缺 last_sync_wp_id）。

同时清理 `_sub_table_columns` 中的同名键。**不动**任何其它表、不动 `_tables`
（读时投影产物，删了也会重算）。

Usage::

    python backend/scripts/fix/cleanup_h3_misrouted_note_tables.py            # dry-run
    python backend/scripts/fix/cleanup_h3_misrouted_note_tables.py --apply    # 实际写库
    python backend/scripts/fix/cleanup_h3_misrouted_note_tables.py --check    # 有残留则非零退出

spec: .kiro/specs/h3-investment-property-disclosure-alignment/ (Task 11)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 支持以脚本路径直接运行（`python backend/scripts/fix/xxx.py`）：把 backend/ 加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402

# H3 的正确章节号（上市 五、21 / 国企 八、21）——**仅作提示，不作判据**。
# 🔴 章节号在不同模板下并非一一对应：实测**国企项目**的 `五、21` 是「其他应付款」
#    （soe 的「五、xx」是另一套压缩编号）。若按章节号白名单放行，H3 上市载荷误推到
#    国企项目 `五、21` 的污染会被当成"正确章节"漏掉。
# → 判据改用 `section_title`：标题不是「投资性房地产」的章节里出现 H3 表即为污染。
H3_CORRECT_SECTIONS = {"五、21", "八、21"}
H3_SECTION_TITLE = "投资性房地产"

# H3 历史载荷自造表名（与前端 H3_LEGACY_OBSOLETE_TABLES 同源）
H3_LEGACY_TABLE_NAMES = {
    "以成本模式计量的投资性房地产（账面原值）",
    "以成本模式计量的投资性房地产（累计折旧和累计摊销）",
    "以成本模式计量的投资性房地产（减值准备）",
    "以公允价值模式计量的投资性房地产",
    "投资性房地产（账面原值）",
    "投资性房地产（累计折旧和累计摊销）",
    "投资性房地产（减值准备）",
    "投资性房地产（公允价值模式）",
}


def _is_h3_orphan(key: str) -> bool:
    return key in H3_LEGACY_TABLE_NAMES or key.startswith("投资性房地产（")


async def run(apply: bool, check: bool, skip_wp_check: bool) -> int:
    eng = create_async_engine(settings.DATABASE_URL)
    findings: list[str] = []
    changed = 0
    try:
        async with eng.begin() as conn:
            rows = (await conn.execute(sa.text(
                """
                SELECT dn.id, dn.project_id, dn.note_section, dn.section_title,
                       dn.table_data, dn.last_sync_wp_id,
                       (SELECT wi.wp_code FROM working_paper wp
                          JOIN wp_index wi ON wp.wp_index_id = wi.id
                         WHERE wp.id = dn.last_sync_wp_id) AS sync_wp_code
                  FROM disclosure_notes dn
                 WHERE dn.is_deleted = false
                """
            ))).fetchall()

            for r in rows:
                section = str(r.note_section or "")
                # 判据 = 章节标题（不是章节号）：标题为「投资性房地产」才是 H3 的正确落点
                if str(r.section_title or "").strip() == H3_SECTION_TITLE:
                    continue
                td = r.table_data
                if isinstance(td, str):
                    td = json.loads(td)
                if not isinstance(td, dict):
                    continue
                sub = td.get("sub_table_data")
                if not isinstance(sub, dict):
                    continue
                orphans = [k for k in sub if _is_h3_orphan(str(k))]
                if not orphans:
                    continue
                wp_code = (r.sync_wp_code or "").strip()
                if not skip_wp_check and wp_code and wp_code != "H3":
                    findings.append(
                        f"[SKIP] {r.project_id} §{section}（{r.section_title}）"
                        f" 命中 {orphans} 但 last_sync wp_code={wp_code!r} ≠ H3"
                    )
                    continue

                findings.append(
                    f"[HIT ] {r.project_id} §{section}（{r.section_title}）"
                    f" wp={wp_code or '?'} → 删除 {len(orphans)} 表：{orphans}"
                )
                if not apply:
                    continue

                for k in orphans:
                    sub.pop(k, None)
                cols = td.get("_sub_table_columns")
                if isinstance(cols, dict):
                    for k in orphans:
                        cols.pop(k, None)

                if sub:
                    # 仍有合法推送子表 → `_tables` 是读时投影产物，删掉让投影器按剩余
                    # `sub_table_data` 重算。
                    td.pop("_tables", None)
                else:
                    # 清空后说明该章节**从未被本章节的正确底稿推送过**（全部子表都是 H3 误推）
                    # → 撤销 workpaper 来源标记，回退到生成时 legacy 快照渲染。
                    # 🔴 此分支**绝不能删 `_tables`**：它持有本章节（如固定资产）的正确
                    #    seed 骨架；删了会让该章节变成"零表"，比污染更糟。
                    for marker in (
                        "_source", "_last_sync_at", "_last_sync_wp_id",
                        "_last_sync_sheet", "_current_standard",
                    ):
                        td.pop(marker, None)
                await conn.execute(sa.text(
                    "UPDATE disclosure_notes SET table_data = CAST(:td AS jsonb), "
                    "updated_at = now() WHERE id = :id"
                ), {"td": json.dumps(td, ensure_ascii=False), "id": str(r.id)})
                changed += 1
    finally:
        await eng.dispose()

    for line in findings:
        print(line)
    hits = sum(1 for f in findings if f.startswith("[HIT "))
    if check:
        print(f"\n--check：{hits} 条残留污染")
        return 1 if hits else 0
    print(f"\n{'[applied] 已更新' if apply else '[dry-run] 待更新'} {changed if apply else hits} 条记录")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="清理 H3 误推到其它章节的孤儿子表")
    ap.add_argument("--apply", action="store_true", help="实际写库（默认只预览）")
    ap.add_argument("--check", action="store_true", help="仅检测残留，有则非零退出")
    ap.add_argument("--skip-wp-check", action="store_true",
                    help="不要求 last_sync wp_code=H3（历史记录可能缺该字段）")
    args = ap.parse_args()
    return asyncio.run(run(args.apply, args.check, args.skip_wp_check))


if __name__ == "__main__":
    sys.exit(main())
