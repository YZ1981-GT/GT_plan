-- V102: 高级查询模块 — 回写记录 addr_id 身份表（Advanced Query Module · Writeback addr_id Identity）
--
-- 高级查询回写落点为 working_papers.parsed_data.univer_snapshot（cell 值原地更新，无独立回写表）。
-- 为满足「以 ACNR addr_id 作为回写身份存储 + 快照列可下钻」（见 requirements R3.1 / R14.3），
-- 新增 advanced_query_writeback 结构化身份/审计索引表：
--   addr_id = {wp_code}/{sheet_code}/{coordinate_key}，与 WP() 公式引用同一身份（R3.2/R3.3），
--   stale chip 追踪据此对齐；审计明细同时经 audit_logger.log_action 落 audit trail。
--
-- 幂等铁律：CREATE TABLE IF NOT EXISTS 建表，随后用 DO $$ + information_schema.tables 检测表
-- 存在性通过后再 CREATE INDEX IF NOT EXISTS（禁止裸 CREATE INDEX 于表不确定场景），
-- 确保重复运行不报错。

-- ① 回写身份/审计索引表：advanced_query_writeback
CREATE TABLE IF NOT EXISTS advanced_query_writeback (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID NOT NULL,
  addr_id       TEXT NOT NULL,          -- {wp_code}/{sheet_code}/{coordinate_key}（R3.1）
  wp_id         UUID,                   -- resolve_instance 附加
  old_value     JSONB,
  new_value     JSONB,
  operator_id   UUID NOT NULL,
  result        TEXT NOT NULL,          -- success/failed
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ② 表存在性确认通过后再建 addr_id 索引（供 stale chip 追踪 / 下钻按身份检索）
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_name='advanced_query_writeback') THEN
    CREATE INDEX IF NOT EXISTS idx_aqw_addr_id
      ON advanced_query_writeback (addr_id);
  END IF;
END $$;

-- ③ 表存在性确认通过后再建 项目维度 + 时间倒序 复合索引（供按项目查最近回写）
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_name='advanced_query_writeback') THEN
    CREATE INDEX IF NOT EXISTS idx_aqw_project
      ON advanced_query_writeback (project_id, created_at DESC);
  END IF;
END $$;
