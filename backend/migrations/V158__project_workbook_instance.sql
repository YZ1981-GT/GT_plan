-- V158：ProjectWorkbookInstance + child sheet entries（custom Task 10）
--
-- 一份整册一个 current artifact / generation / room；
-- child entries 只承载导航与 G-ID sheet 身份，禁止按 sheet 复制 xlsx/pointer/room。

CREATE TABLE IF NOT EXISTS project_workbook_instance (
    id                          UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    workbook_instance_id        VARCHAR(128)  NOT NULL UNIQUE,
    organization_id             VARCHAR(128)  NOT NULL,
    project_id                  VARCHAR(128)  NOT NULL,
    wp_id                       VARCHAR(128)  NOT NULL,
    workbook_lineage_id         VARCHAR(128)  NOT NULL,
    pinned_template_version_id  VARCHAR(128)  NOT NULL,
    current_artifact_id         VARCHAR(128)  NOT NULL,
    content_revision            VARCHAR(128)  NOT NULL,
    representation_revision     VARCHAR(128)  NOT NULL,
    workbook_generation         INTEGER       NOT NULL DEFAULT 1
                                    CHECK (workbook_generation >= 1),
    onlyoffice_room_id          VARCHAR(256),
    context_fingerprint         VARCHAR(128)  NOT NULL,
    authorization_epoch         BIGINT        NOT NULL DEFAULT 1
                                    CHECK (authorization_epoch >= 1),
    created_at                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pwi_project
    ON project_workbook_instance (project_id);
CREATE INDEX IF NOT EXISTS ix_pwi_wp
    ON project_workbook_instance (wp_id);

COMMENT ON TABLE project_workbook_instance IS
    '自定义模板整册实例：一 workbook 一 artifact/generation/room；child 不复制 xlsx。';
COMMENT ON COLUMN project_workbook_instance.workbook_generation IS
    '任一写入先推进此代际，再刷新 affected child projections。';

CREATE TABLE IF NOT EXISTS project_workbook_sheet_entry (
    id                      UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id                VARCHAR(256)  NOT NULL UNIQUE,
    workbook_instance_id    VARCHAR(128)  NOT NULL
                                REFERENCES project_workbook_instance (workbook_instance_id)
                                ON DELETE CASCADE,
    sheet_uid               VARCHAR(128)  NOT NULL,
    sheet_code              VARCHAR(64),
    wp_code                 VARCHAR(64)   NOT NULL,
    component_type          VARCHAR(64)   NOT NULL,
    projection_mode         VARCHAR(32)   NOT NULL
                                CHECK (projection_mode IN (
                                    'editable_grid', 'read_only_html', 'onlyoffice_only'
                                )),
    manifest_version        VARCHAR(64),
    guidance_revision       VARCHAR(128)  NOT NULL DEFAULT '',
    projection_generation   INTEGER       NOT NULL DEFAULT 1
                                CHECK (projection_generation >= 1),
    created_at              TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ux_pwi_sheet_uid UNIQUE (workbook_instance_id, sheet_uid)
);

CREATE INDEX IF NOT EXISTS ix_pwse_workbook
    ON project_workbook_sheet_entry (workbook_instance_id);

COMMENT ON TABLE project_workbook_sheet_entry IS
    '整册 child entry：sheet_uid 来自 G-ID；rename/reorder 不改 entry_id。';
COMMENT ON COLUMN project_workbook_sheet_entry.entry_id IS
    '统一 namespace：pwi-{workbookInstanceId}:{sheetUid}，不使用 opaque-{wp_code}/opaque-{wp_id} 分裂口径。';
