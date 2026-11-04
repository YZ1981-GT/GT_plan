-- R260: 回滚 V260 CITAR 表格人工修改
DROP TABLE IF EXISTS ledger_manual_edits;
ALTER TABLE financial_report DROP COLUMN IF EXISTS manual_amounts;
