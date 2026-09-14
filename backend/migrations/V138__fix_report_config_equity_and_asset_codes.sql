-- V138: report_config 科目码完整性修正（权益段 + 资产/负债/减值段）
--
-- spec: report-config-account-code-integrity（Wave 2 / Task 4）
--
-- ═══════════════════════════════════════════════════════════════════════════
-- 全表对账基线（2026-08-03 建立，2026-08-04 守卫复核）
-- ═══════════════════════════════════════════════════════════════════════════
-- 抽取范围：report_config 全部 TB('code') / SUM_TB('code') 引用，
--           排除 applicable_standard LIKE 'project:%' 与 is_deleted = true。
--   · TB 引用总数            132（按 row_code 去重口径）/ 396（按准则变体展开）
--   · 涉及报表行              102
--   · 判定为错码（本迁移）    12（BS-014 待裁决、BS-052/BS-066 待裁决，均不在本迁移）
--   · 判定为业务事实（白名单）4（BS-004 / BS-007 / BS-037 / BS-068）
--   · 已由 V137 修好          5（BS-022 / BS-025 / BS-026 / IS-016 / IS-017）
--
-- 判据：`account_chart` **双向**对账（① 该码实际叫什么科目 ② 该科目名实际挂哪个码），
--       且**分 source 各判**（client 8 项目 / standard 10 项目；standard 侧并存
--       旧《企业会计制度》(2001) 3xxx权益/4xxx成本/5xxx损益 与 CAS 2006
--       4xxx权益/6xxx损益 两套体系，合并判定会把 4001/4101/4301/4401 误判成一码多名）。
--
-- ═══════════════════════════════════════════════════════════════════════════
-- 🔴 V136 是失效迁移（不修改、不删除该已应用文件 —— 改已应用迁移会触发 checksum 漂移）
-- ═══════════════════════════════════════════════════════════════════════════
-- V136__fix_report_config_bs082_bs117_special_reserve.sql 假设
--   「BS-082 = 专项储备且 formula 含 4103」
-- 实测：BS-082 的 row_name 是**其他权益工具**、formula 是 TB('4003')
--   → 它的 WHERE 从不命中，0 行影响。
-- 真正写 4103 的是 **BS-086 专项储备**，V136 没碰它 —— 本迁移修的就是 BS-086。
-- 另：BS-117 专项储备 的 formula 本就是 NULL，无需修正（已复核）。
--
-- ═══════════════════════════════════════════════════════════════════════════
-- 幂等性：每条 UPDATE 的 WHERE 都带「已实证的错值」，修正后不再命中 → 重复应用 0 行影响。
-- 改码统一用 REPLACE(formula, '''错码''', '''正码''')：只替换被单引号包裹的码字面量，
--   对 TB('x','y') 与 TB('x', 'y') 两种空格形态都成立（实证 BS-* 无空格、EQ/IMP/CFSS 有空格）。
-- ═══════════════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────────────
-- 一、权益段 BS-081~BS-090（整块错位）
-- ───────────────────────────────────────────────────────────────────────────

-- BS-082 其他权益工具：现码 4003 实为**其他综合收益**（client 8 项目）。
-- 其他权益工具实际挂在 4401（client 5 / standard 3 项目；standard 侧另有旧制「工程施工」属体系差异）。
UPDATE report_config
SET formula = REPLACE(formula, '''4003''', '''4401'''),
    updated_at = NOW()
WHERE row_code = 'BS-082'
  AND formula LIKE '%''4003''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- BS-084 减：库存股：现码 4005 **全库零命中**。
-- 库存股实际挂在 4201（client 5 / standard 3 项目）。
UPDATE report_config
SET formula = REPLACE(formula, '''4005''', '''4201'''),
    updated_at = NOW()
WHERE row_code = 'BS-084'
  AND formula LIKE '%''4005''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- BS-085 其他综合收益：现码 4102 **全库零命中**。
-- 其他综合收益实际挂在 4003（client 8 / standard 5 项目）。
UPDATE report_config
SET formula = REPLACE(formula, '''4102''', '''4003'''),
    updated_at = NOW()
WHERE row_code = 'BS-085'
  AND formula LIKE '%''4102''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- BS-086 专项储备：现码 4103 实为**本年利润**（client 8 / standard 5 项目）。
-- 专项储备实际挂在 4301（client 4 / standard 3 项目；standard 侧另有旧制「研发支出」）。
-- 🔴 这一行才是 V136 本想修而没修到的那行。
UPDATE report_config
SET formula = REPLACE(formula, '''4103''', '''4301'''),
    updated_at = NOW()
WHERE row_code = 'BS-086'
  AND formula LIKE '%''4103''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- EQ-015 （五）专项储备：现码 4201 实为**库存股**。
-- 🔴 该行 formula 是 TB('4201', '期末余额') - TB('4201', '期初余额') —— **两处都要换**，
--    REPLACE 会替换全部出现，正是这里需要的行为。
UPDATE report_config
SET formula = REPLACE(formula, '''4201''', '''4301'''),
    updated_at = NOW()
WHERE row_code = 'EQ-015'
  AND formula LIKE '%''4201''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- BS-090 少数股东权益 → NULL。
-- 现码 4201 实为**库存股**；少数股东权益是**合并抵销派生项**，CAS 2006 无对应单一会计科目。
-- 保留 4201 不仅取错，还会与修正后的 BS-084（同样指向 4201）跨行双算。
-- 注：BS-090 的 soe_standalone 变体 row_name 是「△分出再保险合同负债」且 formula 本就 NULL，
--     WHERE 的 formula 条件天然跳过它。
UPDATE report_config
SET formula = NULL,
    updated_at = NOW()
WHERE row_code = 'BS-090'
  AND formula LIKE '%''4201''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;


-- ───────────────────────────────────────────────────────────────────────────
-- 二、资产段 / 负债段 / 减值段
-- ───────────────────────────────────────────────────────────────────────────

-- BS-033 开发支出：现码 1703 实为**无形资产减值准备**（把备抵当原值，client 5 / standard 8 项目）。
-- 开发支出实际挂在 1704（client 4 / standard 3 项目）。
UPDATE report_config
SET formula = REPLACE(formula, '''1703''', '''1704'''),
    updated_at = NOW()
WHERE row_code = 'BS-033'
  AND formula LIKE '%''1703''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- IMP-008 七、债权投资减值准备：现码 1502 实为**持有至到期投资减值准备**（旧准则科目）。
-- 债权投资减值准备实际挂在 1505（standard 6 项目）。
UPDATE report_config
SET formula = REPLACE(formula, '''1502''', '''1505'''),
    updated_at = NOW()
WHERE row_code = 'IMP-008'
  AND formula LIKE '%''1502''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- BS-043 衍生金融负债 → NULL。
-- 现码 2102 实为**短期应付债券**（client 4 / standard 3 项目）。
-- 🔴 不改指 3201：`3201` 在 standard 侧是**利润分配**（6 项目）、client 侧是**套期工具**（1 项目）
--    = 一码两义；且实测 df5b8403 的「3201 套期工具」带真金额 −4,314,686.92
--    → 任何「按名定位落到 3xxx」的路径都必须先判编码体系，本行宁缺勿造置 NULL。
UPDATE report_config
SET formula = NULL,
    updated_at = NOW()
WHERE row_code = 'BS-043'
  AND formula LIKE '%''2102''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- BS-053 其他流动负债 → NULL。
-- 现码 2901 实为**递延所得税负债**（client 7 / standard 9 项目），
-- 且该码**已由 BS-067 递延所得税负债认领** → 现状是跨行双算（守卫的 D 组断言抓的就是这条）。
UPDATE report_config
SET formula = NULL,
    updated_at = NOW()
WHERE row_code = 'BS-053'
  AND formula LIKE '%''2901''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- IMP-017 十六、商誉减值准备 → NULL。
-- 现码 1711 是**商誉原值**（client 5 / standard 8 项目）—— 把原值当备抵；
-- 商誉减值准备 1712 在全库零命中 → 宁缺勿造置 NULL。
UPDATE report_config
SET formula = NULL,
    updated_at = NOW()
WHERE row_code = 'IMP-017'
  AND formula LIKE '%''1711''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- BS-013 一年内到期的非流动资产 → NULL。
-- 现码 1503 实为**可供出售金融资产**（旧准则科目，client 1 / standard 6 项目）。
-- 该行语义是各非流动资产「一年内到期部分」的**重分类合计**，不对应任何单一科目。
UPDATE report_config
SET formula = NULL,
    updated_at = NOW()
WHERE row_code = 'BS-013'
  AND formula LIKE '%''1503''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;

-- CFSS-016 存货的减少（增加以"－"号填列）→ NULL。
-- 现 formula 是 TB('1401','期初余额') - TB('1401','期末余额')：
--   · `1401` 实为**材料采购**（client 5 / standard 8 项目），存货是区间 1401~1499
--   · 该行是**变动额**不是余额，且区间口径下应走 SUM_TB 差额
-- 两处口径都不对 → 置 NULL，由现金流量表补充资料自身的编制逻辑处理。
UPDATE report_config
SET formula = NULL,
    updated_at = NOW()
WHERE row_code = 'CFSS-016'
  AND formula LIKE '%''1401''%'
  AND applicable_standard NOT LIKE 'project:%'
  AND is_deleted = false;


-- ═══════════════════════════════════════════════════════════════════════════
-- 本迁移**有意不含**的行（各有原因，勿在此文件补）
-- ═══════════════════════════════════════════════════════════════════════════
-- · BS-014 其他流动资产 = TB('1901')[+ TB('1131') listed_standalone]
--     `1901` 实为待处理财产损溢/损益且 tb_balance 该科目余额全库恒 0；
--     listed 侧额外的 `1131` 应收股利已由 BS-009 认领 = 潜在双算。
--     处置需用户裁决（波及 K2 的 22 个文件引用）→ 另开 V139。
--
-- · BS-052 一年内到期的非流动负债 = TB('2501')
--     `2501` 实为长期借款，且已由 BS-061 长期借款认领 → 与 BS-013/BS-053 同型
--     （重分类派生行 + 跨行双算）。2026-08-04 守卫首次跑出，立项清单未含，待裁决。
--
-- · BS-066 递延收益 = TB('2811')
--     `2811` 全库零命中，而「递延收益」实际挂在 **2401**（standard 9 / client 6 项目）
--     → 按判据「码零命中 + 名有归属 = 错码」应改 2811→2401。
--     立项时误将其列入零命中白名单（白名单依据只查了码没查名），待裁决。
--
-- · applicable_standard LIKE 'project:%' 的覆盖行
--     客户自定义公式，改动可能破坏其已出报表 → 由 Task 6 输出清单人工逐项目确认。
-- ═══════════════════════════════════════════════════════════════════════════
