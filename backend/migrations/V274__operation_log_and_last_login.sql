-- V274: 操作日志与最后登录时间（spec operation-log-and-last-login）
-- 1) users 记录最后登录时间与 IP；2) sys_login_log 登录留痕表（成功/失败/锁定/登出）。
-- 全部幂等（IF NOT EXISTS）。

ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(45) NULL;

CREATE TABLE IF NOT EXISTS sys_login_log (
    id         UUID PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id    UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    username   VARCHAR(150) NOT NULL,
    result     VARCHAR(20) NOT NULL,
    ip         VARCHAR(45) NULL,
    user_agent TEXT NULL,
    CONSTRAINT ck_sys_login_log_result CHECK (
        result IN ('success', 'failed', 'locked', 'logout')
    )
);

CREATE INDEX IF NOT EXISTS idx_sys_login_log_ts ON sys_login_log (ts);
CREATE INDEX IF NOT EXISTS idx_sys_login_log_user_ts ON sys_login_log (user_id, ts);

COMMENT ON TABLE sys_login_log IS '登录留痕（操作日志页登录类目数据源；成功/失败/锁定/登出，独立会话写入）';
COMMENT ON COLUMN sys_login_log.result IS 'success=登录成功 failed=密码错误或账号不存在 locked=账号锁定 logout=登出';
