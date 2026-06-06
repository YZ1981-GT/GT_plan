-- V054: 补充 projects.is_deleted 列的 DEFAULT false
-- ORM 声明 server_default="false" 但 PG 列实际无 DEFAULT，导致 INSERT 不带 is_deleted 时报 NOT NULL violation
ALTER TABLE projects ALTER COLUMN is_deleted SET DEFAULT false;
