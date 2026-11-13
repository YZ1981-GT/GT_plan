-- R248: 回滚 V248（原编号 V237，撞号后改为 V248）；执行前必须先回退公式推送来源代码。
ALTER TABLE formula_push_state DROP COLUMN IF EXISTS provenance;
