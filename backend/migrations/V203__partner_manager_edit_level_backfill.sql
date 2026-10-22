-- V203 合伙人与经理的编辑级回填（spec partner-manager-edit-permission，design §5.2，需求 4）
-- 版本号写作时为 198，实施时多次被并发会话占用，按需求 4.1 取现扫最高版本加一，最终为 203
--
-- 需求 4.2：成员行未删除，该用户在该项目持有合伙人或经理别名的现行委派，且没有 EQCR 别名的现行委派
--   ⇒ 级别改为 edit，项目角色改为委派角色映射的项目角色（同时持有映射为 partner 与 manager 的委派时取 partner）
-- 需求 4.3：该用户在该项目持有 EQCR 别名的现行委派 ⇒ 其未删除成员行的级别置为 review，项目角色不动
-- 现行委派：委派与人员库记录都未删除，且人员库记录已关联用户。不看项目是否软删，不看全局角色
-- 委派角色与别名按精确字符串比较（大小写与首尾空白都不归一），别名与 ROLE_MAP 逐字一致，由 pg_only 对账测试守护
-- 只改 project_users 的 role 与 permission_level 两列，不增删、不恢复成员行，不碰委派、人员、用户与项目
-- 项目角色与级别已经等于目标值的行不改写、不记录。每个被改动行在同一语句内记入回填记录表，已有记录不覆盖（需求 4.5）
-- 重复执行不改行、不加记录（需求 4.7）。配对回滚脚本 R203 只恢复仍等于目标值的行，随后删表（需求 4.9）
-- 不用 EXCEPTION 吞错（需求 4.10）。执行器整文件一个事务，任一语句报错即全部回滚，版本不登记，失败记入 schema_migration_failures
-- 注释只用全角标点，不写半角分号与半角冒号（执行器按半角分号分句）

CREATE TABLE IF NOT EXISTS project_user_level_backfill (
    project_user_id         UUID PRIMARY KEY,
    prior_role              projectuserrole NOT NULL,
    prior_permission_level  permissionlevel NOT NULL,
    target_role             projectuserrole NOT NULL,
    target_permission_level permissionlevel NOT NULL,
    rule                    VARCHAR(20) NOT NULL,          -- partner_manager（需求 4.2）或 eqcr（需求 4.3）
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

WITH live_assign AS (           -- 现行委派：委派与人员库记录都未删除且已关联用户；不看项目是否软删、不看全局角色
    SELECT pa.project_id, sm.user_id, pa.role
    FROM project_assignments pa JOIN staff_members sm ON sm.id = pa.staff_id
    WHERE pa.is_deleted = false AND sm.is_deleted = false AND sm.user_id IS NOT NULL
), eqcr_users AS (
    SELECT DISTINCT project_id, user_id FROM live_assign WHERE role IN ('eqcr', '独立复核合伙人')
), pm_users AS (
    SELECT project_id, user_id, bool_or(role IN ('signing_partner', 'partner', '合伙人')) AS has_partner
    FROM live_assign WHERE role IN ('signing_partner', 'partner', '合伙人', 'manager', '项目经理')
    GROUP BY project_id, user_id
), targets AS (
    SELECT pu.id AS pu_id, pu.role AS prior_role, pu.permission_level AS prior_level,
           CASE WHEN e.user_id IS NOT NULL THEN pu.role                      -- 4.3：项目角色不动
                WHEN p.has_partner THEN 'partner'::projectuserrole           -- 4.2：同时持有合伙人与经理取 partner
                ELSE 'manager'::projectuserrole END AS target_role,
           CASE WHEN e.user_id IS NOT NULL THEN 'review'::permissionlevel ELSE 'edit'::permissionlevel END AS target_level,
           CASE WHEN e.user_id IS NOT NULL THEN 'eqcr' ELSE 'partner_manager' END AS rule
    FROM project_users pu
    LEFT JOIN eqcr_users e ON e.project_id = pu.project_id AND e.user_id = pu.user_id
    LEFT JOIN pm_users p ON p.project_id = pu.project_id AND p.user_id = pu.user_id
    WHERE pu.is_deleted = false AND (e.user_id IS NOT NULL OR p.user_id IS NOT NULL)
), changed AS (
    SELECT * FROM targets WHERE (prior_role, prior_level) IS DISTINCT FROM (target_role, target_level)
), logged AS (
    INSERT INTO project_user_level_backfill
        (project_user_id, prior_role, prior_permission_level, target_role, target_permission_level, rule)
    SELECT pu_id, prior_role, prior_level, target_role, target_level, rule FROM changed
    ON CONFLICT (project_user_id) DO NOTHING                               -- 4.5：已有记录不覆盖
    RETURNING project_user_id
)
UPDATE project_users pu SET role = c.target_role, permission_level = c.target_level
FROM changed c WHERE pu.id = c.pu_id;
