-- V174: 合并签字冻结快照（consol-elimination-single-source-push 任务15）
--
-- ConsolSnapshot ORM 依赖的运行时表。幂等创建，确保 MigrationRunner 与
-- SQLAlchemy metadata.create_all() 的测试/生产 schema 一致。

CREATE TABLE IF NOT EXISTS consol_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year            INTEGER NOT NULL,
    snapshot_data   JSONB NOT NULL,
    trigger_reason  VARCHAR(30) NOT NULL,
    diff_summary    JSONB,
    created_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_consol_snapshots_project_year_created
    ON consol_snapshots (project_id, year, created_at DESC);

COMMENT ON TABLE consol_snapshots IS
    '合并签字时刻全量快照：压缩载荷、哈希与锁定元数据';
