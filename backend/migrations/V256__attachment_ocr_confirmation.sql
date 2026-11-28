-- V211: 附件识别文本确认留痕（spec attachment-security-baseline 需求 3，ADR-ASB-04）。
--
-- 原先「确认识别结果」把弹窗里的文本整体写回 ocr_text，而弹窗拿到的是列表接口截断的 200 字预览
-- ⇒ 确认一次全文就被截成 200 字；确认状态也没有落库（页面上的「待确认」刷新后又出现）。
-- 现在确认走 POST /api/attachments/{id}/ocr-confirm：请求带打开核对时全文的 sha256，服务端比对一致才写。
--   ocr_confirmed_sha256：确认时全文的 sha256（十六进制小写）。确认有效 = 它等于当前全文的 sha256，
--                         任何写入方改写文本后自动失效，不依赖写入方记得清标记。
--   ocr_confirmed_by / ocr_confirmed_at：确认人、确认时间。
--   ocr_confirmed_edited：确认时是否修订了文本。
-- 不放 ocr_fields_cache：该字段被 OCR 写回、OCR 字段服务、函证比对三个写入方整体覆盖。
-- 不回填存量（真库附件 0 行）。
-- 编号：原用 V209，与远端已推送的 V209__widen_business_category_varchar20 撞号，改为 V211（V210 已被 voucher_identity 占用）。
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ocr_confirmed_sha256 VARCHAR(64);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ocr_confirmed_by UUID REFERENCES users(id);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ocr_confirmed_at TIMESTAMPTZ;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS ocr_confirmed_edited BOOLEAN;
