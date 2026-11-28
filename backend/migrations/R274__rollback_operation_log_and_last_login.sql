-- R274: 回滚 V274（操作日志与最后登录时间）。
DROP TABLE IF EXISTS sys_login_log;
ALTER TABLE users DROP COLUMN IF EXISTS last_login_at;
ALTER TABLE users DROP COLUMN IF EXISTS last_login_ip;
