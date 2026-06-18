-- V086: 审计报告增加管理层声明书日期列（CW-76）
--
-- A16 签回时用户必填 sign_date，push 到此字段。
-- 禁止从 docx 元数据读取（不可靠），必须由用户手动输入。

ALTER TABLE audit_report ADD COLUMN IF NOT EXISTS representation_letter_date DATE;

COMMENT ON COLUMN audit_report.representation_letter_date IS '管理层声明书签署日期（CW-76：用户标记 signed 时必填）';
