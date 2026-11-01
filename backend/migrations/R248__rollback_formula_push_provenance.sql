-- R248: 回滚 V237；执行前必须先回退公式推送来源代码。
ALTER TABLE formula_push_state DROP COLUMN IF EXISTS provenance;
