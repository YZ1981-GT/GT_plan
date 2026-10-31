-- R234：回滚 V234 的 USCC 校验约束与函数。
-- V234 撤销的授权保持撤销状态：它们的企业代码校验码错误，本就无法用于建项。
ALTER TABLE IF EXISTS project_creation_grants
    DROP CONSTRAINT IF EXISTS ck_project_creation_grants_code_checksum;
DROP FUNCTION IF EXISTS gt_is_valid_uscc(text);
