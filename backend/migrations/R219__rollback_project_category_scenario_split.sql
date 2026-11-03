-- R219：撤销 V219（质控业务分类与专项场景拆分）。
-- 先去掉 CHECK 再恢复原值：原值里可能有 IPO / refinancing / 小写码，这些在 CHECK 下写不进去。
-- 只恢复现值仍等于 V219 迁移结果的行（迁移后被人工改过的行保持现值）。

ALTER TABLE projects DROP CONSTRAINT IF EXISTS ck_projects_business_category_registered;
ALTER TABLE projects DROP CONSTRAINT IF EXISTS ck_projects_scenario_registered;
ALTER TABLE projects ALTER COLUMN business_category SET DEFAULT 'C';

DO $$
BEGIN
    IF to_regclass('project_classification_v219_backup') IS NOT NULL THEN
        UPDATE projects AS p
        SET business_category = b.old_business_category,
            scenario = b.old_scenario
        FROM project_classification_v219_backup AS b
        WHERE p.id = b.project_id
          AND p.business_category IS NOT DISTINCT FROM (CASE
                  WHEN b.old_business_category IS NULL THEN NULL
                  WHEN btrim(b.old_business_category) = '' THEN NULL
                  WHEN upper(btrim(b.old_business_category)) IN ('IPO', 'REFINANCING') THEN NULL
                  ELSE upper(btrim(b.old_business_category))
              END)
          AND p.scenario = (CASE
                  WHEN upper(btrim(COALESCE(b.old_business_category, ''))) = 'IPO' AND b.old_scenario = 'normal' THEN 'ipo'
                  WHEN upper(btrim(COALESCE(b.old_business_category, ''))) = 'REFINANCING' AND b.old_scenario = 'normal' THEN 'refinancing'
                  ELSE b.old_scenario
              END);
    END IF;
END
$$;

DROP TABLE IF EXISTS project_classification_v219_backup;
