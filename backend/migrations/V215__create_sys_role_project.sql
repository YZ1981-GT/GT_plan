-- V215: sys_role_project —— 角色↔自定义项目绑定表（仅 data_scope=2 使用，权限中心对齐）
-- 对应 ORM：app/models/sys_permission.py::SysRoleProject（V157 移植）
--
-- 语义：data_scope=2 的角色在此登记其可见项目集合；账号的 custom_project_ids =
--   该账号所有 data_scope=2 角色在本表的项目并集。并集为空时 scope=2 返回空可见集。

CREATE TABLE IF NOT EXISTS sys_role_project (
    role_id INTEGER NOT NULL,
    project_id UUID NOT NULL,
    PRIMARY KEY (role_id, project_id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sys_role_project_role'
          AND table_name = 'sys_role_project'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE sys_role_project
        ADD CONSTRAINT fk_sys_role_project_role
        FOREIGN KEY (role_id) REFERENCES sys_role(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added fk_sys_role_project_role constraint';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sys_role_project_project'
          AND table_name = 'sys_role_project'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE sys_role_project
        ADD CONSTRAINT fk_sys_role_project_project
        FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added fk_sys_role_project_project constraint';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sys_role_project_role
    ON sys_role_project (role_id);

COMMENT ON TABLE sys_role_project IS '角色-自定义项目绑定（仅 data_scope=2 使用）';
COMMENT ON COLUMN sys_role_project.role_id IS '角色 id，FK sys_role(id)';
COMMENT ON COLUMN sys_role_project.project_id IS '项目 id，FK projects(id)';
