"""一次性脚本：清除已底稿同步章节的残留 AI 草稿 text_content。

条件：
  - last_sync_source = 'workpaper'
  - text_content 非空
  - table_data._note_texts 为空/不存在（底稿没推叙述）

清空后下次打开附注编辑器即为空白文本框（由披露表联动驱动）。

用法：
  cd backend
  $env:PYTHONPATH="."
  python scripts/fix/_fix_clear_stale_ai_text_content.py
"""
import asyncio
import sqlalchemy as sa
from app.core.database import async_session
from app.models.report_models import DisclosureNote


async def main():
    async with async_session() as db:
        # 备份到临时表（可回滚）
        await db.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS _note_ai_text_backup AS
            SELECT id, project_id, year, note_section, text_content, now() AS backup_at
            FROM disclosure_notes
            WHERE last_sync_source = 'workpaper'
              AND text_content IS NOT NULL
              AND text_content <> ''
              AND is_deleted = false
              AND (table_data->>'_note_texts') IS NULL
        """))

        # 清空 text_content
        result = await db.execute(sa.text("""
            UPDATE disclosure_notes
            SET text_content = NULL, updated_at = now()
            WHERE last_sync_source = 'workpaper'
              AND text_content IS NOT NULL
              AND text_content <> ''
              AND is_deleted = false
              AND (table_data->>'_note_texts') IS NULL
        """))
        print(f"[OK] Cleared {result.rowcount} rows")
        print("     Backup table: _note_ai_text_backup")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
