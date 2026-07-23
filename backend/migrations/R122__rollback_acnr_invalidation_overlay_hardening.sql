-- R122: 回滚 V122（ACNR 失效传播与 Overlay 治理加固）
-- 安全回滚：drop 新增约束/表；治理列可选保留（additive 列回滚不删数据以防丢失）。
-- 注意：不删除 acnr_project_overlay 既有数据；epoch/outbox 表为纯新增可安全 drop。

-- drop 唯一约束（幂等）
ALTER TABLE acnr_project_overlay DROP CONSTRAINT IF EXISTS uq_overlay_identity;

-- drop 新增表（纯新增，可安全 drop）
DROP TABLE IF EXISTS acnr_invalidation_outbox;
DROP TABLE IF EXISTS acnr_invalidation_epoch;

-- 治理列/revision 列：默认保留（additive nullable / default，不影响旧代码）。
-- 如需彻底回滚列，取消以下注释（会丢失已录治理数据）：
-- ALTER TABLE acnr_project_overlay DROP COLUMN IF EXISTS reason;
-- ALTER TABLE acnr_project_overlay DROP COLUMN IF EXISTS owner;
-- ALTER TABLE acnr_project_overlay DROP COLUMN IF EXISTS expires_at;
-- ALTER TABLE acnr_project_overlay DROP COLUMN IF EXISTS revision;
