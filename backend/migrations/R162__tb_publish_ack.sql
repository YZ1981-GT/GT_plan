-- R162: 回滚 tb_publish_ack 表
--
-- 删除后审定表→试算表发布失去耐久幂等 ack（同一确认可能重复回写 TB）。
-- 仅在确认无需幂等保护时回滚。

DROP INDEX IF EXISTS idx_tb_publish_ack_project_year;
DROP TABLE IF EXISTS tb_publish_ack;
