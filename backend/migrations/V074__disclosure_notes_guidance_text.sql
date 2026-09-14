-- V074: disclosure_notes 新增 guidance_text（附注指引文字，不参与导出）
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS guidance_text TEXT;
