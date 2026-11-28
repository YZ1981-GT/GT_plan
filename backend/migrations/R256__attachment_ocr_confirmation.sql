-- R211: 回滚 V211 —— 去掉附件识别文本确认留痕四列（ocr_text 不受影响）。
ALTER TABLE attachments DROP COLUMN IF EXISTS ocr_confirmed_edited;
ALTER TABLE attachments DROP COLUMN IF EXISTS ocr_confirmed_at;
ALTER TABLE attachments DROP COLUMN IF EXISTS ocr_confirmed_by;
ALTER TABLE attachments DROP COLUMN IF EXISTS ocr_confirmed_sha256;
