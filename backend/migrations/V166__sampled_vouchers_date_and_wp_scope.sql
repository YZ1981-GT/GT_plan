-- V166: sampled_vouchers 补 voucher_date 列 + 手工挂凭去重粒度细化到「凭证 × 底稿」
--
-- ── 问题 1：凭证号不唯一，表里却没有可消歧的日期列 ──────────────────────────
-- 2026-09-28 真实库实测（8 个项目 × active dataset）：
--   voucher_no 仅 1 个项目全年唯一（和平物流 14956/14956），其余 7 个严重重复 ——
--   同一凭证号最多对应 **83 个不同日期**（和平药房_2024）。唯一能定位单张凭证的键是
--   `(voucher_date, voucher_no)`：该粒度下陕西华氏 29162 个组合借贷 **100% 平衡**
--   （0 不平衡），证明它恰好对应一张完整凭证。
-- 后果：`sampled_vouchers` 只存 voucher_no，`useAttachedVouchers.fetchVoucherLines`
--   回拉分录时也只传 year → 拉回的可能是**同号别张凭证**的分录，且表里没有任何字段
--   可用于事后消歧（审计留痕指向不明）。
-- 处置：加 `voucher_date` 列（nullable —— 历史行与「抽中本凭证」未传日期的场景保持可用）。
--
-- ── 问题 2：V140 的手工去重键使「一张凭证挂多张底稿」在数据层不可表达 ────────
-- V140 建立 `uq_sampled_voucher_manual_project_year_no`
--   UNIQUE (project_id, year, voucher_no) WHERE is_deleted=false AND batch_id IS NULL
-- 其注释写明「同一凭证手工标记两次无意义」—— 该判断对**当时唯一存在**的入口
-- （穿透页「抽中本凭证」，不指定底稿）成立，V140 时全表仅 1 行。
-- 但此后新增了「挂凭到底稿」入口（带 working_paper_id），业务上同一张凭证完全可能
-- 既属 D2 应收账款检查、又属 E1 货币资金检查。旧索引使第二次挂凭无法插入，
-- 代码侧 `sample_voucher` 便退化为 UPDATE 覆盖 `working_paper_id` →
-- **先挂 D2 再挂 E1，D2 静默失去这张凭证**。这不是代码漏写条件，而是 DB 约束过紧。
--
-- 处置：**放宽而非收紧**（同 V140 的处置取向），把手工侧去重粒度从
--   (project, year, voucher_no) 细化为
--   (project, year, voucher_no, voucher_date, working_paper_id)：
--     · 同一凭证（同号同日）挂到不同底稿      → 允许（working_paper_id 不同）
--     · 同号不同日（真实存在，最多 83 天）    → 允许分别挂（voucher_date 不同）
--     · 同项目+年度+号+日+底稿完全重复        → 仍拒绝（正确去重，语义不变）
--
-- 🔴 索引名保持 `uq_sampled_voucher_manual_project_year_no` 不变：既有守卫
--    `test_sampling_registry_service.py::test_legacy_global_unique_index_narrowed_to_manual_scope`
--    与 `::test_manual_index_predicate_scopes_to_null_batch` 按名断言其存在且含
--    `batch_id IS NULL`。语义是「手工侧去重索引」的延续，只是去重粒度变细；
--    实际列组成以本迁移重写的 COMMENT 为准（名字里的 project_year_no 是 V140 时的列清单）。
--
-- 🔴 NULL 语义：PG 唯一索引中 NULL <> NULL，若直接把两个 nullable 列放进索引，
--    多行 (…, NULL, NULL) 都能插入 → 去重失效。故用 COALESCE 表达式索引把 NULL
--    折叠成哨兵值（两个哨兵都不可能是真实业务值）。
--
-- 存量安全：改造前全表 1 行且 is_deleted=true，新索引 WHERE is_deleted=false 将其排除
-- ⇒ 零违约、零数据变更。
--
-- 幂等：ADD COLUMN IF NOT EXISTS；索引仅在「定义尚未含新列」时重建，重复执行不抖动。
-- 注：MigrationRunner 只在后端启动时跑，应用本迁移需重启后端。

-- ── 1. voucher_date 列 ──────────────────────────────────────────────────────
ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS voucher_date date;

COMMENT ON COLUMN sampled_vouchers.voucher_date IS
  '凭证日期。与 voucher_no 组合唯一定位一张凭证（真实库实测单个凭证号最多对应 83 个'
  '不同日期，仅凭号不可消歧）；NULL = 历史行或未提供日期的手工标记，回拉分录时退化为'
  '按年度匹配，可能命中同号别张凭证';

-- ── 2. 手工挂凭去重索引：粒度细化到「凭证(号+日) × 底稿」 ────────────────────
-- 旧定义只含三列时才重建，避免每次启动都 DROP+CREATE。
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'uq_sampled_voucher_manual_project_year_no'
          AND indexdef NOT LIKE '%working_paper_id%'
    ) THEN
        DROP INDEX uq_sampled_voucher_manual_project_year_no;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_voucher_manual_project_year_no
  ON sampled_vouchers (
      project_id,
      year,
      voucher_no,
      (COALESCE(voucher_date, DATE '1900-01-01')),
      (COALESCE(working_paper_id, '00000000-0000-0000-0000-000000000000'::uuid))
  )
  WHERE is_deleted = false AND batch_id IS NULL;

COMMENT ON INDEX uq_sampled_voucher_manual_project_year_no IS
  '手工挂凭/标记（batch_id IS NULL，来自 ledger_penetration 穿透页）的凭证去重。'
  'V166 起实际列为 (project_id, year, voucher_no, COALESCE(voucher_date,1900-01-01), '
  'COALESCE(working_paper_id, nil-uuid))：同一凭证可挂多张底稿、同号不同日视为不同凭证；'
  '索引名沿用 V140（既有守卫按名断言）。抽凭引擎登记走 uq_sampled_vouchers_batch 按批次唯一';

-- ── 3. 按底稿回拉的查询路径（底稿凭证检查表「从序时账挂入导入」主路径）────────
CREATE INDEX IF NOT EXISTS ix_sampled_vouchers_wp_scope
  ON sampled_vouchers (working_paper_id, project_id, year)
  WHERE is_deleted = false;
