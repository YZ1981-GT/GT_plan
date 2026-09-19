-- V137: 纠正 report_config 中 G 循环 5 行错码（平台级 P0）
--
-- 铁证：
--   BS-022 其他债权投资     现写 TB('1505') = 债权投资减值准备  → 应为 TB('1506')
--   BS-025 其他权益工具投资 现写 TB('1506') = 其他债权投资      → 应为 TB('1507')
--   BS-026 其他非流动金融资产 现写 TB('1507') = 其他权益工具投资 → 应为 TB('1519')
--   IS-016 信用减值损失     现写 TB('6701') = 资产减值损失      → 应为 TB('6702')
--   IS-017 资产减值损失     现写 TB('6702') = 信用减值损失      → 应为 TB('6701')
--
-- 交叉印证：同库 CFSS-003 加：资产减值损失=TB('6701') / CFSS-004 信用减值损失=TB('6702')
-- 与 IS-016/017 **整整互换**（现金流量表补充资料与利润表自相矛盾）。
--
-- 本迁移按 row_code 精确限定每条 UPDATE + AND formula = '<已实证错值>' 防链式命中。
-- 幂等：IF NOT EXISTS 语义（AND formula 条件不命中则 0 行影响）。
-- 不触碰 project: 级覆盖行（WHERE applicable_standard NOT LIKE 'project:%'）。
--
-- spec: g-cycle-extraction-mapping-and-disclosure-alignment Task 1.1

-- BS-022: 1505 → 1506（其他债权投资）
UPDATE report_config
SET formula = REPLACE(formula, '''1505''', '''1506'''),
    updated_at = NOW()
WHERE row_code = 'BS-022'
  AND formula LIKE '%TB(''1505''%'
  AND applicable_standard NOT LIKE 'project:%';

-- BS-025: 1506 → 1507（其他权益工具投资）
UPDATE report_config
SET formula = REPLACE(formula, '''1506''', '''1507'''),
    updated_at = NOW()
WHERE row_code = 'BS-025'
  AND formula LIKE '%TB(''1506''%'
  AND applicable_standard NOT LIKE 'project:%';

-- BS-026: 1507 → 1519（其他非流动金融资产）
UPDATE report_config
SET formula = REPLACE(formula, '''1507''', '''1519'''),
    updated_at = NOW()
WHERE row_code = 'BS-026'
  AND formula LIKE '%TB(''1507''%'
  AND applicable_standard NOT LIKE 'project:%';

-- IS-016: 6701 → 6702（信用减值损失）
UPDATE report_config
SET formula = REPLACE(formula, '''6701''', '''6702'''),
    updated_at = NOW()
WHERE row_code = 'IS-016'
  AND formula LIKE '%TB(''6701''%'
  AND applicable_standard NOT LIKE 'project:%';

-- IS-017: 6702 → 6701（资产减值损失）
UPDATE report_config
SET formula = REPLACE(formula, '''6702''', '''6701'''),
    updated_at = NOW()
WHERE row_code = 'IS-017'
  AND formula LIKE '%TB(''6702''%'
  AND applicable_standard NOT LIKE 'project:%';
