-- V047: 将 V046 建的 note_section_locks / data_snapshots 时间列改为 TIMESTAMPTZ
-- 背景：V046 初版用 TIMESTAMP（无时区），但 note_section_lock_service.get_active_locks
--   传入 tz-aware datetime(now(tz=utc)) 比较 heartbeat_at → asyncpg
--   "can't subtract offset-naive and offset-aware datetimes" → notes/locks/active 500。
--   统一为 TIMESTAMPTZ。已应用 V046（TIMESTAMP）的环境靠本迁移修正；
--   V046 已改为 TIMESTAMPTZ 的全新环境本迁移幂等无副作用。

ALTER TABLE note_section_locks ALTER COLUMN acquired_at TYPE TIMESTAMPTZ USING acquired_at AT TIME ZONE 'UTC';
ALTER TABLE note_section_locks ALTER COLUMN heartbeat_at TYPE TIMESTAMPTZ USING heartbeat_at AT TIME ZONE 'UTC';
ALTER TABLE note_section_locks ALTER COLUMN released_at TYPE TIMESTAMPTZ USING released_at AT TIME ZONE 'UTC';
ALTER TABLE data_snapshots ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
