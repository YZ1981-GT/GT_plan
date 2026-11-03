-- V210: sampled_vouchers 补主体、凭证字与审计阶段，两条唯一索引按凭证键去重
--       （spec voucher-identity-writeback-and-audit-phase 任务 3，ADR-VK-01，design §8 前半，发现 N3）
--
-- ── 为什么 ──────────────────────────────────────────────────────────────────
-- 凭证键 = (年度, 主体, 凭证日期, 凭证字, 凭证号)。2026-10-27 真库现查：
--   · 同日同号混凭证字：四川物流 167 组、宜宾临港 118 组、辽宁卫生 1,247 组
--     （2025-01-07 的「0003」同时是 FY-0003 与 ZZ-0003，两张各自借贷平衡）；
--   · 4 个 active 数据集一套账里有两个主体编码。
-- 本表只有凭证号和日期：
--   · 手工挂凭（batch_id IS NULL）把 FY-0003 与 ZZ-0003 判成同一张，第二张挂不上；
--   · 抽凭批次登记（batch_id 非空）的唯一索引连日期都没有（N3），一个批次里两张
--     同号不同日的凭证只能登记一张。
--
-- ── 处置 ────────────────────────────────────────────────────────────────────
--   1. 加 company_code（主体）、voucher_type（凭证字，空按 ''）、phase（preliminary /
--      final；NULL = 未标，旧行）。
--   2. 手工侧索引在 V166 的列上加 COALESCE(company_code, '') 与 COALESCE(voucher_type, '')。
--   3. 批次索引加 COALESCE(voucher_date, 1900-01-01)、COALESCE(company_code, '')、
--      COALESCE(voucher_type, '')。旧格式回填日志只有凭证号，登记行这三列为空；
--      PG 唯一索引里 NULL 互不相等，不折叠就会让同一批次重复登记。
--   🔴 两个索引名沿用旧名：tests/test_sampling_registry_service.py 按名断言其存在与谓词。
--   🔴 批次索引谓词保持 `is_deleted = false`：register_sampled_vouchers 的 ON CONFLICT
--      index_where 与之一致才推断得到它；表达式列须与 ON CONFLICT 目标逐字相同
--      （同一测试文件交叉核对）。
--
-- 存量：真库本表 0 行（2026-10-27 现查），零违约、零数据变更。
-- 幂等：ADD COLUMN IF NOT EXISTS；约束按名判重；索引只在定义尚不含 voucher_type 时重建。
-- 注：MigrationRunner 只在后端启动时跑（热重载不跑），应用本迁移需重启后端或手动 run_pending。

ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS company_code varchar;
ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS voucher_type varchar(20);
ALTER TABLE sampled_vouchers ADD COLUMN IF NOT EXISTS phase varchar(16);

COMMENT ON COLUMN sampled_vouchers.company_code IS
  '主体编码（凭证键第二元素，与 tb_ledger.company_code 同值）；NULL = 旧行未记录';
COMMENT ON COLUMN sampled_vouchers.voucher_type IS
  '凭证字（凭证键第四元素）。同日同号可有多种凭证字，各是一张凭证；空凭证字写空串，'
  'NULL = 旧行未记录（去重时按空串参与）';
COMMENT ON COLUMN sampled_vouchers.phase IS
  '登记时的审计阶段：preliminary 预审 / final 年审；NULL = 旧行未标';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_sampled_vouchers_phase'
          AND conrelid = 'sampled_vouchers'::regclass
    ) THEN
        ALTER TABLE sampled_vouchers ADD CONSTRAINT ck_sampled_vouchers_phase
            CHECK (phase IS NULL OR phase IN ('preliminary', 'final'));
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'uq_sampled_voucher_manual_project_year_no'
          AND indexdef NOT LIKE '%voucher_type%'
    ) THEN
        DROP INDEX uq_sampled_voucher_manual_project_year_no;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'uq_sampled_vouchers_batch'
          AND indexdef NOT LIKE '%voucher_type%'
    ) THEN
        DROP INDEX uq_sampled_vouchers_batch;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_voucher_manual_project_year_no
  ON sampled_vouchers (
      project_id,
      year,
      voucher_no,
      (COALESCE(voucher_date, DATE '1900-01-01')),
      (COALESCE(company_code, '')),
      (COALESCE(voucher_type, '')),
      (COALESCE(working_paper_id, '00000000-0000-0000-0000-000000000000'::uuid))
  )
  WHERE is_deleted = false AND batch_id IS NULL;

COMMENT ON INDEX uq_sampled_voucher_manual_project_year_no IS
  '手工挂凭（batch_id IS NULL）去重：凭证键 × 底稿。V210 起列为 (project_id, year, voucher_no, '
  'COALESCE(voucher_date), COALESCE(company_code), COALESCE(voucher_type), COALESCE(working_paper_id))；'
  '索引名沿用 V140（既有守卫按名断言）';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sampled_vouchers_batch
  ON sampled_vouchers (
      project_id,
      year,
      voucher_no,
      (COALESCE(voucher_date, DATE '1900-01-01')),
      (COALESCE(company_code, '')),
      (COALESCE(voucher_type, '')),
      working_paper_id,
      batch_id
  )
  WHERE is_deleted = false;

COMMENT ON INDEX uq_sampled_vouchers_batch IS
  '抽凭批次登记去重：同一批次、同一底稿、同一凭证键只登记一次；不同批次的同一凭证允许共存'
  '（那正是「该凭证被抽过两次」这一需要被发现的事实）。V210 起含日期、主体、凭证字';
