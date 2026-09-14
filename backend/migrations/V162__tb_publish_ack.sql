-- V162: 审定表→试算表"发布"耐久确认/幂等表（tb_publish_ack）
--
-- 背景（P0-项3 · spec d4-dual-mode-formula-governance）：
--   `_on_d_audit_determination_saved` 此前把任意 WORKPAPER_SAVED（wp_code ~ [D-N]\d+-1）
--   都当作"发布"直接回写 trial_balance.audited_amount，无显式确认门、无幂等。普通保存/
--   模式切换会误触发 TB 回写并向下游级联。改为：仅当携带显式发布确认信号才回写，并以本表
--   做**耐久幂等 ack**——同一确认（publish_token 唯一）重复投递只生效一次。
--
-- 幂等：CREATE TABLE IF NOT EXISTS + ADD 唯一约束靠建表内联；重复执行安全。
-- 可回滚：见 R162（DROP TABLE）。

CREATE TABLE IF NOT EXISTS tb_publish_ack (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    year INTEGER NOT NULL,
    wp_code VARCHAR(32) NOT NULL,
    publish_token VARCHAR(128) NOT NULL,   -- 幂等键：同一确认重复投递共用同一 token
    confirmed_by UUID,                     -- 发布确认者（服务端可校验其权限）
    accounts_updated INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (publish_token)
);

CREATE INDEX IF NOT EXISTS idx_tb_publish_ack_project_year
    ON tb_publish_ack (project_id, year);

COMMENT ON TABLE tb_publish_ack IS
    '审定表→试算表发布的耐久确认/幂等 ack（P0-项3）：publish_token 唯一，重复确认只生效一次';
