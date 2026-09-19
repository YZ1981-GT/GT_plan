-- R074: 回滚 disclosure_notes.guidance_text 列
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS guidance_text;
