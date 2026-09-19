-- R164: 回滚 V164（未更正错报 durable 幂等键 source_identity）
DROP INDEX IF EXISTS uq_misstatement_source_identity;
ALTER TABLE unadjusted_misstatements DROP COLUMN IF EXISTS source_identity;
