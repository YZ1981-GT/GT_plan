-- V261: 部门表调整 —— 去掉部门编码、名称唯一、新增部门负责人
-- 对应 ORM：app/models/core.py::Department
-- 1) 删除 code 列及其唯一索引（不再使用部门编码）
-- 2) 部门名称在未软删范围内唯一
-- 3) 新增 head_id（部门负责人，引用 users(id)，置空）

DROP INDEX IF EXISTS uq_sys_dept_code;

ALTER TABLE sys_dept DROP COLUMN IF EXISTS code;

ALTER TABLE sys_dept ADD COLUMN IF NOT EXISTS head_id UUID NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sys_dept_head'
          AND table_name = 'sys_dept'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE sys_dept
        ADD CONSTRAINT fk_sys_dept_head
        FOREIGN KEY (head_id) REFERENCES users(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added fk_sys_dept_head constraint';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_dept_name
    ON sys_dept (name)
    WHERE is_deleted = false;

COMMENT ON COLUMN sys_dept.name IS '部门名称（未软删范围内唯一）';
COMMENT ON COLUMN sys_dept.head_id IS '部门负责人，引用 users(id)';
