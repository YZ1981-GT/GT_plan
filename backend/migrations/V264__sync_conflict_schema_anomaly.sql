-- V264: 同步冲突记录持久化 schema 冲突的成因（spec wp-sync-conflict-adjudication-and-d4-32-modeling R1.1）
--
-- 为什么需要：merge 产出的 `ConflictRecord.schema_anomaly` 决定这条冲突能否靠「选一侧 /
-- 输入合并值」收敛（`conflicts.SchemaAnomalyKind.adjudicable_by_value_choice`），但
-- `ConflictRecord.to_row()` 的列投影里没有它 —— 同一个类的 digest 片段**带**了它，只有落库
-- 那一份漏了。于是成因在写库那一刻丢失，读侧再也拿不到，只能一刀切地把全部 schema 冲突
-- 判成"不可裁决"，`type_normalization_failure` 这类本可人工收敛的冲突成了死路。
--
-- 列可空：本次迁移之前落的历史行没有成因，读侧按「成因未知 ⇒ 不可按值裁决」fail closed
-- （R1.4），并与「成因已知且不可裁决」在 payload 上保持可区分。
ALTER TABLE working_paper_sync_conflict
    ADD COLUMN IF NOT EXISTS schema_anomaly VARCHAR(60);

COMMENT ON COLUMN working_paper_sync_conflict.schema_anomaly IS
    'schema 冲突的成因（conflicts.SchemaAnomalyKind 的值）；非 schema 冲突与迁移前的历史行为 NULL';
