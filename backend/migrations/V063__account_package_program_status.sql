-- V063: 科目工作包程序状态表
-- 关联 Spec: workpaper-account-package-d1-d2-pilot Task 3（程序状态持久化）
-- 跟踪每个审计程序的适用性、执行状态、证据、复核结果和结论

CREATE TABLE IF NOT EXISTS account_package_program_status (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            UUID         NOT NULL REFERENCES projects(id),
    account_package_id    VARCHAR(100) NOT NULL,
    program_code          VARCHAR(50)  NOT NULL,

    -- 3.2: 核心状态字段
    applicable            BOOLEAN      NOT NULL DEFAULT TRUE,
    status                VARCHAR(30)  NOT NULL DEFAULT 'pending',
    evidence              TEXT,
    review_result         VARCHAR(30),
    conclusion            TEXT,

    -- 3.3: 留痕字段
    not_applicable_reason TEXT,
    reviewer              UUID         REFERENCES staff_members(id),
    reviewed_at           TIMESTAMPTZ,
    updated_by            UUID         REFERENCES staff_members(id),

    -- TimestampMixin 铁律：DDL 必须显式写
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 唯一约束：(project_id, account_package_id, program_code)
CREATE UNIQUE INDEX IF NOT EXISTS uq_acct_pkg_program_status
    ON account_package_program_status (project_id, account_package_id, program_code);

-- 查询索引：按项目+工作包查所有程序状态
CREATE INDEX IF NOT EXISTS idx_acct_pkg_program_project
    ON account_package_program_status (project_id, account_package_id);

COMMENT ON TABLE account_package_program_status IS '科目工作包程序状态：跟踪每个审计程序的执行生命周期';
COMMENT ON COLUMN account_package_program_status.applicable IS '是否适用';
COMMENT ON COLUMN account_package_program_status.status IS 'pending|in_progress|completed|reviewed';
COMMENT ON COLUMN account_package_program_status.review_result IS 'pass|fail|conditional';
COMMENT ON COLUMN account_package_program_status.not_applicable_reason IS '不适用理由（applicable=False 时必填）';
