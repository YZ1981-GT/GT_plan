-- V143: word_export_task_versions 增加 drift_report（xlsx 手工改动差异告警）
--
-- Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 4 Task 21 / 需求 10.2、10.8
--
-- 语义（**三态**，不是布尔）：
--   NULL                        = 未检测 / Cell_Mapping 文件不存在（该报表类型未配映射）→ 放行
--   {"unavailable": "<原因>"}   = 映射文件存在但解析失败（配置损坏）→ **拒绝进入 confirmed**
--   {"diffs": [...]}            = 已完成比对；数组非空即存在手工改动 → 拒绝
--                                 数组为空表示已比对且一致 → **放行**
--
-- 为什么第二态必须 fail-closed（需求 10.6）：若解析失败也按 fail-open 放行，
-- 只要弄坏一个映射配置文件就能绕过需求 10.4 的阻断 —— 那等于给「绕过调整分录
-- 直接改报表数字」开了后门。
--
-- 为什么判据不是「非空即拒绝」：`{"diffs": []}` 是 dict 且非空，但它表示
-- 「已比对、无差异」，必须放行；否则每个配了映射的报表都永远确认不了。
--
-- 编号沿革（两次顺延，勿再复用）：立项 V140 → 被 sampling-compliance-closure 占用
--   → 改 V142 → 又被本 spec Wave 2 的 V142__deliverable_version_editor_identity 占用
--   → 最终 V143。
--
-- 幂等：ADD COLUMN IF NOT EXISTS（MigrationRunner 铁律）。

ALTER TABLE word_export_task_versions
    ADD COLUMN IF NOT EXISTS drift_report JSONB;

COMMENT ON COLUMN word_export_task_versions.drift_report IS
    'xlsx 手工改动差异检测三态：NULL=未检测/未配映射(放行) / {"unavailable":原因}=检测不可用(阻断) / {"diffs":[...]}=差异清单(非空则阻断)';
