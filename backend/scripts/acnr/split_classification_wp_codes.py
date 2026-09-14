"""
Split classification records: 把只有父级 wp_code 的底稿拆分为 sheet 级独立 wp_code。

例如: wp_code='D1' 下有 sheet_name='审定表D1-1' → 新增 wp_code='D1-1' 的记录。

用法:
  python -m scripts.acnr.split_classification_wp_codes --dry-run   # 预览
  python -m scripts.acnr.split_classification_wp_codes --apply      # 执行写入
"""
import asyncio
import re
import sys
import uuid
from pathlib import Path

# 确保可以 import app
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.database import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402


# 从 sheet_name 尾部提取编码 (如 D1-1, D1A, K3-7)
_CODE_RE = re.compile(r'([A-Z]\d+(?:-\d+)?[A-Z]?)\s*$')

# 不拆分的 sheet (无编码/通用名)
_SKIP_NAMES = {'底稿目录', 'GT_Custom', '选项', '示例', '不打印'}


async def run(dry_run: bool = True):
    """主逻辑。"""
    async with async_session() as db:
        # 1. 找出全部只有父级 wp_code (X\d+ 无连字符) 且无 sheet 级子 wp_code 的底稿
        q = text("""
            WITH parent_only AS (
                SELECT DISTINCT wp_code
                FROM workpaper_sheet_classification
                WHERE wp_code ~ '^[A-S]\\d+$'
                  AND wp_code !~ '-'
            ),
            has_children AS (
                SELECT DISTINCT SUBSTRING(wp_code FROM '^[A-S]\\d+') as parent
                FROM workpaper_sheet_classification
                WHERE wp_code ~ '^[A-S]\\d+-\\d+'
            )
            SELECT p.wp_code
            FROM parent_only p
            LEFT JOIN has_children h ON p.wp_code = h.parent
            WHERE h.parent IS NULL
            ORDER BY p.wp_code
        """)
        result = await db.execute(q)
        parents_to_split = [r[0] for r in result.fetchall()]
        print(f"[INFO] 需要拆分的父级 wp_code: {len(parents_to_split)} 个")

        # 2. 对每个父级，读取其下全部 sheet，提取编码，生成新记录
        total_new = 0
        all_inserts = []

        for parent_code in parents_to_split:
            q2 = text("""
                SELECT id, wp_code, sheet_name, class_code, "class",
                       is_real_workpaper, exclude_from_archive, exclude_from_progress,
                       is_static_doc, scope, functional_type, template_version_id
                FROM workpaper_sheet_classification
                WHERE wp_code = :parent
                ORDER BY sheet_name
            """)
            result2 = await db.execute(q2, {"parent": parent_code})
            rows = result2.fetchall()

            # 按提取的编码分组
            code_groups: dict[str, list] = {}
            for row in rows:
                sheet_name = row[2]
                if any(skip in sheet_name for skip in _SKIP_NAMES):
                    continue
                m = _CODE_RE.search(sheet_name)
                if m:
                    code = m.group(1)
                    # 排除与父级完全相同的编码 (如 sheet_name='审定表D1' 提取 D1 = 父级本身)
                    if code == parent_code:
                        continue
                    if code not in code_groups:
                        code_groups[code] = []
                    code_groups[code].append(row)

            if not code_groups:
                continue

            # 为每个新 wp_code 生成 INSERT
            for new_code, sheets in sorted(code_groups.items()):
                # 选代表 sheet (优先审定表/明细表)
                representative = sheets[0]
                for s in sheets:
                    if s[3] and 'F-审定表' in s[3]:
                        representative = s
                        break

                # 新记录: 把该 sheet 挂到新 wp_code 下
                new_id = str(uuid.uuid4())
                sheet_name = representative[2]
                class_code = representative[3] or ''
                cls = representative[4] or (class_code.split('-')[0] if class_code else '')
                functional_type = representative[10] or None
                template_version_id = representative[11]

                all_inserts.append({
                    "id": new_id,
                    "wp_code": new_code,
                    "sheet_name": sheet_name,
                    "class_code": class_code,
                    "class": cls,
                    "is_real_workpaper": True,
                    "exclude_from_archive": False,
                    "exclude_from_progress": False,
                    "is_static_doc": False,
                    "scope": "standalone",
                    "functional_type": functional_type,
                    "template_version_id": template_version_id,
                })
                total_new += 1

        print(f"[INFO] 将生成 {total_new} 条新 wp_code 记录")

        if dry_run:
            # 预览前 20 条
            for ins in all_inserts[:20]:
                print(f"  + {ins['wp_code']:12s} <- {ins['sheet_name']}")
            if total_new > 20:
                print(f"  ... 还有 {total_new - 20} 条")
            print("\n[DRY-RUN] 未写入。使用 --apply 执行写入。")
            return

        # 3. 批量 INSERT (跳过已存在的)
        inserted = 0
        skipped = 0
        for ins in all_inserts:
            # 检查是否已存在
            check = text("""
                SELECT 1 FROM workpaper_sheet_classification
                WHERE wp_code = :wp_code AND sheet_name = :sheet_name
                LIMIT 1
            """)
            exists = await db.execute(check, {"wp_code": ins["wp_code"], "sheet_name": ins["sheet_name"]})
            if exists.fetchone():
                skipped += 1
                continue

            insert_q = text("""
                INSERT INTO workpaper_sheet_classification
                  (id, wp_code, sheet_name, class_code, "class", is_real_workpaper,
                   exclude_from_archive, exclude_from_progress, is_static_doc, scope,
                   functional_type, template_version_id)
                VALUES
                  (:id, :wp_code, :sheet_name, :class_code, :cls, :is_real_workpaper,
                   :exclude_from_archive, :exclude_from_progress, :is_static_doc, :scope,
                   :functional_type, :template_version_id)
            """)
            await db.execute(insert_q, {
                **ins,
                "cls": ins["class"],
            })
            inserted += 1

        await db.commit()
        print(f"[OK] 插入 {inserted} 条，跳过已存在 {skipped} 条。")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    if apply:
        print("[MODE] APPLY - 将写入数据库")
    else:
        print("[MODE] DRY-RUN - 仅预览不写入")
    asyncio.run(run(dry_run=not apply))
