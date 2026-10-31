-- V233：经理按精确 USCC 建项授权；admin 管理，partner 角色直通

CREATE TABLE IF NOT EXISTS project_creation_grants (
    id               UUID         PRIMARY KEY,
    grantee_user_id  UUID         NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    company_code     VARCHAR(18)  NOT NULL,
    valid_from       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    valid_until      TIMESTAMPTZ,
    version          INTEGER      NOT NULL DEFAULT 1,
    source           VARCHAR(48)  NOT NULL DEFAULT 'admin',
    reason           TEXT         NOT NULL,
    granted_by       UUID         REFERENCES users(id) ON DELETE RESTRICT,
    revoked_by       UUID         REFERENCES users(id) ON DELETE RESTRICT,
    revoked_at       TIMESTAMPTZ,
    is_deleted       BOOLEAN      NOT NULL DEFAULT false,
    deleted_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_project_creation_grants_version CHECK (version >= 1),
    CONSTRAINT ck_project_creation_grants_valid_window
        CHECK (valid_until IS NULL OR valid_until > valid_from),
    CONSTRAINT ck_project_creation_grants_code_shape
        CHECK (char_length(company_code) = 18 AND company_code = upper(btrim(company_code)))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_creation_grants_active
    ON project_creation_grants (grantee_user_id, company_code)
    WHERE is_deleted = false;
CREATE INDEX IF NOT EXISTS ix_project_creation_grants_grantee_valid
    ON project_creation_grants (grantee_user_id, valid_until)
    WHERE is_deleted = false;

-- 存量兼容：已有 active edit 项目的 manager 获得该项目企业代码的精确授权。
INSERT INTO project_creation_grants (
    id, grantee_user_id, company_code, source, reason, granted_by
)
SELECT DISTINCT ON (pu.user_id, upper(btrim(p.company_code)))
    gen_random_uuid(), pu.user_id, upper(btrim(p.company_code)),
    'existing_project_edit_backfill', '由现有可编辑项目成员关系回填', NULL
FROM project_users pu
JOIN users u ON u.id = pu.user_id
JOIN projects p ON p.id = pu.project_id
WHERE pu.is_deleted = false
  AND pu.permission_level::text = 'edit'
  AND u.is_deleted = false AND u.is_active = true AND u.role::text = 'manager'
  AND p.is_deleted = false
  AND char_length(btrim(p.company_code)) = 18
  AND upper(btrim(p.company_code)) ~ '^[0-9A-HJ-NPQRTUWXY]{18}$'
ORDER BY pu.user_id, upper(btrim(p.company_code)), p.id
ON CONFLICT (grantee_user_id, company_code) WHERE is_deleted = false DO NOTHING;

COMMENT ON TABLE project_creation_grants IS
    'manager 对精确统一社会信用代码的项目创建授权；不授予既有项目访问权';
COMMENT ON COLUMN project_creation_grants.version IS
    '授权恢复或修改时递增；持久批量计划以此做撤权/变更 CAS';
