-- R078: 回滚 adjustments.passed_reason + passed_communication_date
ALTER TABLE adjustments DROP COLUMN IF EXISTS passed_reason;
ALTER TABLE adjustments DROP COLUMN IF EXISTS passed_communication_date;
