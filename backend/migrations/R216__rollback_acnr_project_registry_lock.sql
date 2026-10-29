-- R216: 回滚 V216（项目锁定的地址目录版本落库）。
--
-- 两列只由 ACNR 版本锁写，删掉即回到「锁定只在进程内」的旧行为：
-- 归档项目会按当前目录解析。回滚前请确认没有项目依赖按归档版本解析。
ALTER TABLE projects DROP COLUMN IF EXISTS acnr_registry_locked_at;
ALTER TABLE projects DROP COLUMN IF EXISTS acnr_registry_version;
