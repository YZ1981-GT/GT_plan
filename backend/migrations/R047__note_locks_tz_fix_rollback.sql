-- R047: 回滚时间列类型（TIMESTAMPTZ → TIMESTAMP）

ALTER TABLE note_section_locks ALTER COLUMN acquired_at TYPE TIMESTAMP;
ALTER TABLE note_section_locks ALTER COLUMN heartbeat_at TYPE TIMESTAMP;
ALTER TABLE note_section_locks ALTER COLUMN released_at TYPE TIMESTAMP;
ALTER TABLE data_snapshots ALTER COLUMN created_at TYPE TIMESTAMP;
