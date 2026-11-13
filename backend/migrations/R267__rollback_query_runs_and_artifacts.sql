-- R267: 回滚高级查询运行记录与查询证据
-- Spec: advanced-query-artifact-and-freshness

DROP TABLE IF EXISTS query_artifacts;
DROP TABLE IF EXISTS query_runs;
DROP FUNCTION IF EXISTS gt_query_artifact_immutable();
DROP FUNCTION IF EXISTS gt_query_run_immutable();
