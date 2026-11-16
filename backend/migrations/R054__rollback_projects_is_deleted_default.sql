-- R054: 回滚 V054（只恢复 projects.is_deleted 的默认值）。
ALTER TABLE projects ALTER COLUMN is_deleted DROP DEFAULT;
