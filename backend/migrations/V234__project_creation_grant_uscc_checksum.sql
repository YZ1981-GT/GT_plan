-- V234：经理建项授权的企业代码与平台统一 USCC 校验（uscc_validator.validate_uscc）对齐
--
-- V233 的存量回填只校验了长度与字符集；字符集合法但 mod-31 校验码错误的代码会生成一条
-- 永远无法使用的授权（建项入口先按统一校验拒绝该代码），却在管理界面显示为「有效」。
-- 本迁移：①提供与 validate_uscc 同算法的不可变函数；②把这类不可用授权按系统撤销处理；
-- ③加数据库约束，未撤销的授权必须通过校验，直接 SQL 写入也不能绕过。
-- 幂等：函数 CREATE OR REPLACE；清理只作用于未撤销且校验失败的行；约束用 pg_constraint 守卫。

CREATE OR REPLACE FUNCTION gt_is_valid_uscc(p_code text) RETURNS boolean
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $fn$
    SELECT p_code ~ '^[0-9A-HJ-NPQRTUWXY]{18}$'
       AND (
           31 - (
               SELECT sum(
                   (strpos('0123456789ABCDEFGHJKLMNPQRTUWXY', substr(p_code, i, 1)) - 1)
                   * (power(3, i - 1)::bigint % 31)
               )
               FROM generate_series(1, 17) AS i
           )::integer % 31
       ) % 31
       = strpos('0123456789ABCDEFGHJKLMNPQRTUWXY', substr(p_code, 18, 1)) - 1
$fn$;

COMMENT ON FUNCTION gt_is_valid_uscc(text) IS
    'V234：统一社会信用代码 mod-31 校验，与 app/services/uscc_validator.validate_uscc 同算法';

UPDATE project_creation_grants
SET is_deleted = true,
    deleted_at = COALESCE(deleted_at, now()),
    revoked_at = COALESCE(revoked_at, now()),
    version = version + 1,
    updated_at = now()
WHERE is_deleted = false
  AND NOT gt_is_valid_uscc(company_code);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_project_creation_grants_code_checksum'
          AND conrelid = 'project_creation_grants'::regclass
    ) THEN
        ALTER TABLE project_creation_grants
            ADD CONSTRAINT ck_project_creation_grants_code_checksum
            CHECK (is_deleted OR gt_is_valid_uscc(company_code));
    END IF;
END
$$;
