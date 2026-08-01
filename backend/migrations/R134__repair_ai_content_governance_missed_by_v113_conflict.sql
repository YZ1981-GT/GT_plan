-- R134: 回滚 V134 修复
--
-- 说明：V134 做两件事——(1) 幂等补建 ai_content_governance 表；(2) 校正 schema_version
--   version=113 簿记行（可见性→证据治理）。回滚语义为「返回 V134 之前的状态」：
--   * 还原 version=113 簿记行为可见性文件名（checksum 置回可见性迁移应用时的值不可考，
--     故保留为空标记，交由重跑或运维核对；仅还原 filename 以恢复 pre-V134 归属）。
--   * DROP 补建的 ai_content_governance 表（回滚是显式破坏性操作，生产需 --confirm）。
--     若表内已有治理数据，回滚将连同数据一并删除——这是回滚到「表不存在」状态的必然结果。

-- 1) 删除表（连同索引/约束级联）
DROP TABLE IF EXISTS ai_content_governance CASCADE;

-- 2) 还原 schema_version version=113 簿记行为可见性文件名
UPDATE schema_version
SET filename = 'V113__wp_visibility_delegation_history_audit_epoch.sql'
WHERE version = '113'
  AND filename = 'V113__evidence_governance_ai_content_governance.sql';
