-- V212: sys_dept 部门组织架构表（权限中心对齐）
-- 对应 ORM：app/models/core.py::Department（V150 移植，含 FK / partial unique / 父索引）
CREATE TABLE IF NOT EXISTS sys_dept (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,
    parent_id UUID NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    description TEXT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sys_dept_parent'
          AND table_name = 'sys_dept'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE sys_dept
        ADD CONSTRAINT fk_sys_dept_parent
        FOREIGN KEY (parent_id) REFERENCES sys_dept(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added fk_sys_dept_parent constraint';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_dept_code
    ON sys_dept (code)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS idx_sys_dept_parent
    ON sys_dept (parent_id);

COMMENT ON TABLE sys_dept IS '部门组织架构（Department ORM 对应表）';
COMMENT ON COLUMN sys_dept.id IS '主键UUID';
COMMENT ON COLUMN sys_dept.name IS '部门名称';
COMMENT ON COLUMN sys_dept.code IS '部门编码（未软删范围内唯一）';
COMMENT ON COLUMN sys_dept.parent_id IS '父部门ID，自引用外键 sys_dept(id)';
COMMENT ON COLUMN sys_dept.sort_order IS '排序顺序';
COMMENT ON COLUMN sys_dept.description IS '部门描述';
