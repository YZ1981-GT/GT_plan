-- V139: 抽样登记表批次绑定（sampling-compliance-closure Wave 2 / R5.3 / R5.4）
--
-- 背景（2026-08-04 实证）：CAS 1314 要求的抽样记录项（总体描述 / 样本量依据 / 偏差笔数 /
-- 推断错报 / 错报上限 / 结论）在库里有表却全空 —— `sampling_records` 0 行、
-- `sampled_vouchers` 1 行（唯一写入点是 ledger_penetration 的穿透页手工标记，与抽凭引擎
-- 完全不通），真实留痕全在 `workpaper_extraction_log.extraction_criteria` JSONB 里。
-- 后果：①无法在项目层面查询"所有抽样是否都有总体描述/样本量依据/结论"，归档完整性与 QC
-- 抽查只能逐张底稿点开翻 JSON；②重复抽凭只在同一 workpaper_id 内排除，同一凭证被多个
-- 循环重复抽取在项目层面发现不了。
--
-- 本迁移把两张表接成 canonical 留痕的**可查询侧投影**（权威仍是 extraction_criteria）：
-- 按 batch_id 与抽凭批次一一关联，并为已抽凭证登记加防重唯一索引。
--
-- 幂等：全部 IF NOT EXISTS，可重复执行。
-- 注：MigrationRunner 只在后端启动时跑，应用本迁移需重启后端。

-- ── sampling_records：批次关联 + 方法学快照列 ────────────────────────────────
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS batch_id uuid;
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS sampling_method varchar(32);
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS random_seed bigint;
ALTER TABLE sampling_records ADD COLUMN IF NOT EXISTS dataset_id uuid;

COMMENT ON COLUMN sampling_records.batch_id IS
  '抽凭批次标识，对应 workpaper_extraction_log.batch_id（权威留痕在该表的 extraction_criteria）';
COMMENT ON COLUMN sampling_records.sampling_method IS
  '抽样方法：random/stratified/specific_item/systematic/mus（canonical 算法真源的取值域）';
COMMENT ON COLUMN sampling_records.random_seed IS
  '随机种子，供复核/重跑复现同一抽样结果（须配合 dataset_id 才成立）';
COMMENT ON COLUMN sampling_records.dataset_id IS
  '抽样框数据集版本（ledger_datasets.id）；序时账重导后据此判定该批次已不可复算';

-- 按批次查询评价记录（QC 抽查与归档完整性核对的主路径）
CREATE INDEX IF NOT EXISTS ix_sampling_records_batch
  ON sampling_records (batch_id);

-- 项目级概览：按 (project, working_paper) 汇总批次数/样本数
CREATE INDEX IF NOT EXISTS ix_sampling_records_project_wp
  ON sampling_records (project_id, working_paper_id);

-- ── sampled_vouchers：批次关联 + 同批次防重 ─────────────────────────────────
ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS batch_id uuid;

COMMENT ON COLUMN sampled_vouchers.batch_id IS
  '抽凭批次标识；NULL 表示非抽凭引擎来源（如 ledger_penetration 穿透页手工标记）';

-- 同一批次内同一凭证只登记一次；不同 batch_id 的同一凭证**允许共存**
-- （那正是"该凭证被抽过两次"这一需要被发现的事实）。
-- 部分索引排除软删除行，避免删除后无法重新登记。
CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_vouchers_batch
  ON sampled_vouchers (project_id, year, voucher_no, working_paper_id, batch_id)
  WHERE is_deleted = false;

-- 跨底稿重复抽凭检测：按 (project, year, voucher_no) 聚合找 ≥2 个底稿的凭证
CREATE INDEX IF NOT EXISTS ix_sampled_vouchers_project_voucher
  ON sampled_vouchers (project_id, year, voucher_no);
