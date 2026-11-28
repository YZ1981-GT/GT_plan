-- V213: sys_role / sys_user_role 两表（角色-数据权限体系，权限中心对齐）
-- 对应 ORM：app/models/sys_permission.py::SysRole / SysUserRole（V155 移植）
--
-- sys_role.id 用自增整型（对齐若依 sys_role 结构）；sys_user_role 覆盖写语义、无软删。

CREATE TABLE IF NOT EXISTS sys_role (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role_key VARCHAR(100) NOT NULL,
    data_scope INTEGER NOT NULL DEFAULT 5,
    status VARCHAR(10) NOT NULL DEFAULT '0',
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_role_key
    ON sys_role (role_key)
    WHERE is_deleted = false;

CREATE TABLE IF NOT EXISTS sys_user_role (
    user_id UUID NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, role_id)
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sys_user_role_user'
          AND table_name = 'sys_user_role'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE sys_user_role
        ADD CONSTRAINT fk_sys_user_role_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added fk_sys_user_role_user constraint';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sys_user_role_role'
          AND table_name = 'sys_user_role'
          AND constraint_type = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE sys_user_role
        ADD CONSTRAINT fk_sys_user_role_role
        FOREIGN KEY (role_id) REFERENCES sys_role(id) ON DELETE CASCADE;
        RAISE NOTICE 'Added fk_sys_user_role_role constraint';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sys_user_role_user ON sys_user_role (user_id);
CREATE INDEX IF NOT EXISTS idx_sys_user_role_role ON sys_user_role (role_id);

COMMENT ON TABLE sys_role IS '角色表（数据权限维度）；与 users.role 的 UserRole 枚举双轨并存';
COMMENT ON COLUMN sys_role.data_scope IS '数据权限范围：1=全部 2=自定义项目 6=我参与的 5=仅本人（3/4 已废弃）';
COMMENT ON COLUMN sys_role.status IS '状态：0=正常 1=停用';
COMMENT ON TABLE sys_user_role IS '账号-角色多对多绑定（覆盖写语义，无软删）';
