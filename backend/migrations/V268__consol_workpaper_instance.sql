-- V268：合并薄底稿壳实例（consolidation-run-and-workpaper-lifecycle-closure 批 6 / ADR-CRW-006）
--
-- consol_workpaper_instance 把每个合并项目/年度与其 A3-CONSOL 薄底稿壳（WpIndex + WorkingPaper）
-- 关联起来，并记录最近一次正式 operation 与 immutable artifact 引用及壳版本号。
-- 业务数据仍以 consol_worksheet_data / consol_trial / financial_report / consol_note_data 为权威，
-- 本表不复制业务 JSON，只做身份与最新产物指针，version 随 artifact/operation 更新单调递增。

CREATE TABLE IF NOT EXISTS consol_workpaper_instance (
    id                  UUID        PRIMARY KEY,
    project_id          UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year                INTEGER     NOT NULL,
    working_paper_id    UUID        NOT NULL REFERENCES working_paper(id) ON DELETE CASCADE,
    wp_index_id         UUID        NOT NULL REFERENCES wp_index(id) ON DELETE CASCADE,
    latest_operation_id UUID        REFERENCES consol_operation(id) ON DELETE SET NULL,
    latest_artifact_id  UUID        REFERENCES consol_artifact(id) ON DELETE SET NULL,
    version             INTEGER     NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_consol_workpaper_instance_version CHECK (version > 0)
);

-- 同项目同年度最多一个合并底稿壳实例
CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_workpaper_instance_project_year
    ON consol_workpaper_instance (project_id, year);

-- 按底稿壳反查实例
CREATE UNIQUE INDEX IF NOT EXISTS ux_consol_workpaper_instance_working_paper
    ON consol_workpaper_instance (working_paper_id);

COMMENT ON TABLE consol_workpaper_instance IS
    '合并项目/年度与 A3-CONSOL 薄底稿壳的关联及最近正式 operation/artifact 指针；不复制业务 JSON';
COMMENT ON COLUMN consol_workpaper_instance.latest_artifact_id IS
    '最近一次 ready 的合并工作底稿 artifact；working_paper.file_path 随之指向该 artifact';
COMMENT ON COLUMN consol_workpaper_instance.version IS
    '壳版本号，随 artifact/operation 指针更新单调递增，用于证据与归档的版本对账';
