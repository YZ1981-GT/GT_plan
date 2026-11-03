-- V207: 底稿生命周期领域事件（移入 / 恢复回收站），只追加
-- spec: procedure-chain-hardening-and-java-contracts R18
-- 原先只记在 wp_index.cross_ref_codes["_recycle_lineage"]（JSON，随行可改、不能按事件查询）；
-- 现在同事务另写一条事件。旧 JSON 照写（兼容）；回收站「删除人」先读事件，没有再回退 JSON。
-- 不对 wp_index 建外键：事件要比被引用的行活得久。对 projects 建外键：项目彻底删除时随项目清掉
-- （recycle_bin._cascade_delete_project 用 session_replication_role=replica，不触发只追加触发器）。
-- 幂等：CREATE TABLE/INDEX IF NOT EXISTS + DROP/CREATE TRIGGER；只追加触发器复用 V115 的 wp_visibility_forbid_mutation()
-- （含受控维护逃生舱 SET LOCAL app.wp_visibility_maintenance = 'on'）。
CREATE TABLE IF NOT EXISTS workpaper_lifecycle_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id),
    wp_index_id UUID NOT NULL,
    wp_code VARCHAR NOT NULL,
    event_type VARCHAR(16) NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    actor_user_id UUID,
    request_id TEXT,
    working_paper_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    trim_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_wp_lifecycle_event_type CHECK (event_type IN ('recycled', 'restored'))
);

CREATE INDEX IF NOT EXISTS idx_wp_lifecycle_events_wp_index
    ON workpaper_lifecycle_events (wp_index_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wp_lifecycle_events_project
    ON workpaper_lifecycle_events (project_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_wp_lifecycle_events_append_only ON workpaper_lifecycle_events;
CREATE TRIGGER trg_wp_lifecycle_events_append_only
    BEFORE UPDATE OR DELETE ON workpaper_lifecycle_events
    FOR EACH ROW EXECUTE FUNCTION wp_visibility_forbid_mutation();
