-- R203 回滚 V203（合伙人与经理的编辑级回填，spec partner-manager-edit-permission，design §5.2，需求 4.9）
-- 只把有回填记录、且项目角色与级别仍等于记录中目标值的成员行恢复为记录中的迁移前值
-- 没有回填记录的行，以及迁移后已被其他途径（如委派同步）改成其他值的行，保持现值
-- 执行完成后删除回填记录表，不保留任何回填记录（包括未恢复的行）
-- 正向迁移从未执行时先建一张空的回填记录表，随后两条语句照常执行，不改动任何成员行（需求 4.1）
-- 不用 EXCEPTION 吞错（需求 4.10）。执行器整个脚本一个事务，任一语句报错即全部回滚，schema_version 保留 203
-- 注释只用全角标点，不写半角分号与半角冒号（执行器按半角分号分句，回滚脚本经 SQLAlchemy 的 text 执行，半角冒号后接字母会被当成绑定参数）

CREATE TABLE IF NOT EXISTS project_user_level_backfill (    -- 正向从未执行时也能跑通（4.1）
    project_user_id         UUID PRIMARY KEY,
    prior_role              projectuserrole NOT NULL,
    prior_permission_level  permissionlevel NOT NULL,
    target_role             projectuserrole NOT NULL,
    target_permission_level permissionlevel NOT NULL,
    rule                    VARCHAR(20) NOT NULL,
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

UPDATE project_users pu
SET role = b.prior_role, permission_level = b.prior_permission_level
FROM project_user_level_backfill b
WHERE pu.id = b.project_user_id
  AND pu.role = b.target_role AND pu.permission_level = b.target_permission_level;  -- 4.9：已被他途改动的行保持现值

DROP TABLE IF EXISTS project_user_level_backfill;                                     -- 不保留任何回填记录
