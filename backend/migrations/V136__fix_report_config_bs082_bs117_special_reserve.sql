-- V136: 修正 report_config 中 BS-082/BS-117（专项储备）的科目码误标
--
-- 问题：BS-082/BS-117 的 formula 写的是 TB('4103','期末余额')，
--        但 4103 = 本年利润，专项储备实为 4301。
--        row_name 字段已正确记录为「专项储备」，仅 formula 内科目码错误。
--
-- 影响：resolve_report_line_account_codes 解析 BS-082/BS-117 时返回 ['4103']
--        导致 M7 溯源面板显示错误来源科目。修正后返回 ['4301']。
--
-- 幂等：只更新 formula 仍含 '4103' 的记录，已修正的不重复执行。

UPDATE report_config
SET formula = REPLACE(formula, '''4103''', '''4301'''),
    updated_at = NOW()
WHERE row_code IN ('BS-082', 'BS-117')
  AND formula LIKE '%''4103''%'
  AND is_deleted = false;
