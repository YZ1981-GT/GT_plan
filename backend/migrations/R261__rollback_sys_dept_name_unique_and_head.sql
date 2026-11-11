-- R261: 回滚 V261 —— 恢复部门编码列与唯一索引，去掉名称唯一与部门负责人
-- 注意：恢复的 code 列为 NULL，若需重新启用编码唯一约束须先回填去重。

DROP INDEX IF EXISTS uq_sys_dept_name;

ALTER TABLE sys_dept DROP CONSTRAINT IF EXISTS fk_sys_dept_head;
ALTER TABLE sys_dept DROP COLUMN IF EXISTS head_id;

ALTER TABLE sys_dept ADD COLUMN IF NOT EXISTS code VARCHAR(50) NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_dept_code
    ON sys_dept (code)
    WHERE is_deleted = false;
