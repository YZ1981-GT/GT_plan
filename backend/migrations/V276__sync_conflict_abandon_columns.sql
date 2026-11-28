-- V273: 冲突记录的「显式作废」三列（spec frozen-contract-read-path-and-legacy-operation-settlement 任务 8）
--
-- 为什么必须新起列而**不复用**已有的 `superseded_at`：
--
-- `superseded_at` 在全仓只有一个写入方 —— `repository.py` 的 `mark_conflicts_superseded`
-- （观测同步，语义 =「本轮不再出现的旧 key」），而同一个函数对**本轮命中**的行执行
-- `row.superseded_at = None` **清零**（`record_conflicts` 的 updated 分支）。
-- 拿它存「人工作废」会被下一次重观测静默抹掉；而且同一列两种含义 = 第二真源。
--
-- 为什么是「作废」而不是「正式裁决」：
--
-- 遗留 operation 的 24 条冲突全部 `conflict_kind='schema'` 且 `schema_anomaly IS NULL`
-- ⇒ `ConflictPreviewItem.adjudicable_by_value_choice` 在成因未知时 fail-closed 返回
-- False ⇒ `apply_resolutions` 抛 `StructuralConflictNotAdjudicableError`。即使补齐成因，
-- `resolve → apply_durable_incoming → _fence_before_publish → assert_final_authorization`
-- 的 `approved_bundle_identity` 判据也会抛 `ApprovedBundleReplacedError`（entry 当前
-- bundle 已换代）。这两道拒绝都是**保护审计链的正确行为**，不是缺陷。
--
-- 三列可空：作废是显式动作，绝大多数冲突行永远为空。三列必须**同生共死**（见下方
-- `ck_wpsc_abandon_triplet`）—— 只写其中一两列等于让「谁在什么时候因为什么作废了」残缺。
ALTER TABLE working_paper_sync_conflict
    ADD COLUMN IF NOT EXISTS abandoned_at TIMESTAMPTZ;
ALTER TABLE working_paper_sync_conflict
    ADD COLUMN IF NOT EXISTS abandon_reason TEXT;
ALTER TABLE working_paper_sync_conflict
    ADD COLUMN IF NOT EXISTS abandoned_by UUID REFERENCES users(id) ON DELETE RESTRICT;

-- 三列同生共死：要么全空（未作废），要么全非空（已作废）。
-- 🔴 不用 `btrim(abandon_reason) <> ''` 以外的方式判「有原因」：空白串与 NULL 在
-- `IS NOT NULL` 下同义会被混为一谈，而「作废但没写原因」正是 R3.3 要禁的形态。
--
-- 🔴 存在性判定必须**按当前 schema 限定**：`pg_constraint` 是**整库**共享的系统目录，
-- 只查 `conname` 会在「同库里另有 schema 有同名约束」时误判为已存在而**静默跳过建约束**
-- （本 spec 的 PG 守卫用临时 schema 建同名表，正是这样抓到它的：约束没加，残缺写入照样成功）。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
         WHERE c.conname = 'ck_wpsc_abandon_triplet'
           AND t.relname = 'working_paper_sync_conflict'
           AND n.nspname = current_schema()
    ) THEN
        ALTER TABLE working_paper_sync_conflict
            ADD CONSTRAINT ck_wpsc_abandon_triplet CHECK (
                (abandoned_at IS NULL) = (abandoned_by IS NULL)
                AND (abandoned_at IS NULL) = (abandon_reason IS NULL)
                AND (abandon_reason IS NULL OR length(btrim(abandon_reason)) > 0)
            );
    END IF;
END
$$;

COMMENT ON COLUMN working_paper_sync_conflict.abandoned_at IS
    '人工作废时刻（spec frozen-contract-read-path 任务 8）；与 superseded_at（观测同步）语义不同，禁复用';
COMMENT ON COLUMN working_paper_sync_conflict.abandon_reason IS
    '作废的中文原因（R3.3 要求必须写）；空白串被 ck_wpsc_abandon_triplet 拒绝';
COMMENT ON COLUMN working_paper_sync_conflict.abandoned_by IS
    '作废操作者（服务端当前用户，不信任请求体）';
