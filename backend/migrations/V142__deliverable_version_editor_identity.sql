-- V142: word_export_task_versions 增加「实际编辑人 / 编辑时间」两列
--
-- Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 2 Task 14 / 需求 7.2, 7.3
--
-- 为什么不复用 created_by：
--   `created_by` 是 NOT NULL + FK users(id)，无法表达「回调未携带可识别编辑人」这一
--   真实状态。历史实现把 `task.created_by`（交付物创建人）当编辑人写进去 → 版本链上
--   所有 OO 编辑版本作者都是创建人，与「谁改的」这一审计事实不符（需求 7.2）。
--
-- 语义：
--   edited_by  = 该版本的**实际编辑人**；NULL 表示未知（不得回退 created_by 展示）。
--   edited_at  = 实际编辑时间；NULL 表示未知或非编辑产生的版本（generate/refresh）。
--   created_by 在 created_via='onlyoffice_edit' 场景降级为「回调处理占位」，
--              展示链路一律读 edited_by（见 Property 14 守卫）。
--
-- 幂等：ADD COLUMN IF NOT EXISTS（MigrationRunner 铁律）。

ALTER TABLE word_export_task_versions
    ADD COLUMN IF NOT EXISTS edited_by UUID REFERENCES users(id);

ALTER TABLE word_export_task_versions
    ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;

COMMENT ON COLUMN word_export_task_versions.edited_by IS
    '实际编辑人（OO 在线编辑）；NULL=未知，禁止回退 created_by 展示';
COMMENT ON COLUMN word_export_task_versions.edited_at IS
    '实际编辑时间；NULL=未知或非编辑产生的版本';
