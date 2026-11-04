-- V261: 账号「允许修改」开关（spec citar-manual-edit-permission）
--
-- users.allow_manual_edit：是否允许人工修改自动生成的数据（税审底稿公式 / 取数格、报表金额、审核说明、
-- 余额表 / 序时账等）。默认 TRUE：已有账号与新建账号行为不变；管理员在「账号权限」页逐个关闭。
-- 三层一致：ORM backend/app/models/core.py User.allow_manual_edit；判定 backend/app/services/manual_edit_permission.py。
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS allow_manual_edit BOOLEAN NOT NULL DEFAULT TRUE;
COMMENT ON COLUMN users.allow_manual_edit IS '是否允许人工修改自动生成的数据（账号权限页「允许修改」）';
