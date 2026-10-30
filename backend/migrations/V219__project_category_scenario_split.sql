-- V219：质控业务分类与专项场景拆分（spec trim-generation-plan-followup-optimizations R4）
--   projects.business_category 只放质控业务分类码（致同 2025 业务分类参考标准：A / A1~A8、B / B1~B6、C），
--   projects.scenario 只放专项场景登记值。历史上写进分类列的 IPO / refinancing 搬到场景列（仅场景仍为 normal 时），
--   分类清空为未填写（不猜 A2 / A4：质控分类决定专委会 / EQCR 等质控措施，由人确认）。
--   未登记的分类值、与旧值冲突的场景、未登记的场景一律 fail-closed（整份迁移回滚，需人工处理）。
--   改动行逐行备份到 project_classification_v219_backup，R219 只在现值仍等于迁移结果时恢复。
-- 🔴 MigrationRunner 的分句器不识别单引号字符串：字符串里禁用 ASCII 分号与连字符注释符。
-- 🔴 登记值清单与 app.services.project_classification（CATEGORY 参考标准 / SCENARIOS）、ORM CHECK 同步，
--    tests/test_project_classification.py 逐值对拍。

DO $$
DECLARE
    unknown_count integer;
    conflict_count integer;
    bad_scenario_count integer;
BEGIN
    SELECT count(*) INTO unknown_count
    FROM projects
    WHERE business_category IS NOT NULL
      AND btrim(business_category) <> ''
      AND upper(btrim(business_category)) NOT IN (
          'A', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8',
          'B', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'C',
          'IPO', 'REFINANCING');
    IF unknown_count > 0 THEN
        RAISE EXCEPTION 'V219: % projects have unregistered business_category values, resolve manually', unknown_count;
    END IF;

    SELECT count(*) INTO conflict_count
    FROM projects
    WHERE upper(btrim(COALESCE(business_category, ''))) IN ('IPO', 'REFINANCING')
      AND scenario IS DISTINCT FROM 'normal'
      AND scenario IS DISTINCT FROM lower(btrim(business_category));
    IF conflict_count > 0 THEN
        RAISE EXCEPTION 'V219: % projects have legacy scenario categories conflicting with scenario, resolve manually', conflict_count;
    END IF;

    SELECT count(*) INTO bad_scenario_count
    FROM projects
    WHERE scenario IS NULL
       OR scenario NOT IN ('normal', 'ipo', 'listed', 'refinancing', 'transfer', 'restructure', 'fraud_response');
    IF bad_scenario_count > 0 THEN
        RAISE EXCEPTION 'V219: % projects have unregistered scenario values, resolve manually', bad_scenario_count;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS project_classification_v219_backup (
    project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    old_business_category VARCHAR(20),
    old_scenario VARCHAR(20) NOT NULL,
    backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE project_classification_v219_backup IS
    'V219 拆分前的分类 / 场景原值，R219 只在现值仍等于迁移结果时恢复，避免覆盖迁移后的人工修改';

INSERT INTO project_classification_v219_backup (project_id, old_business_category, old_scenario)
SELECT id, business_category, scenario
FROM projects
WHERE business_category IS NOT NULL
  AND (btrim(business_category) = ''
       OR upper(btrim(business_category)) IN ('IPO', 'REFINANCING')
       OR business_category <> upper(btrim(business_category)))
ON CONFLICT (project_id) DO NOTHING;

UPDATE projects
SET scenario = CASE
        WHEN upper(btrim(business_category)) = 'IPO' AND scenario = 'normal' THEN 'ipo'
        WHEN upper(btrim(business_category)) = 'REFINANCING' AND scenario = 'normal' THEN 'refinancing'
        ELSE scenario
    END,
    business_category = CASE
        WHEN btrim(business_category) = '' THEN NULL
        WHEN upper(btrim(business_category)) IN ('IPO', 'REFINANCING') THEN NULL
        ELSE upper(btrim(business_category))
    END
WHERE business_category IS NOT NULL
  AND (btrim(business_category) = ''
       OR upper(btrim(business_category)) IN ('IPO', 'REFINANCING')
       OR business_category <> upper(btrim(business_category)));

-- 未填写 = NULL（与 ORM 一致：ORM 插入时显式写 NULL，库默认值 'C' 只在裸 SQL 漏写列时生效，会伪填 C 类）
ALTER TABLE projects ALTER COLUMN business_category DROP DEFAULT;

-- 约束是否已存在按本表判断（pg_constraint 是全库目录，只按名字查会被其他 schema 的同名约束骗过）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_projects_business_category_registered'
                     AND conrelid = 'projects'::regclass) THEN
        ALTER TABLE projects ADD CONSTRAINT ck_projects_business_category_registered CHECK (
            business_category IS NULL OR business_category IN (
                'A', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8',
                'B', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'C'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_projects_scenario_registered'
                     AND conrelid = 'projects'::regclass) THEN
        ALTER TABLE projects ADD CONSTRAINT ck_projects_scenario_registered CHECK (
            scenario IN ('normal', 'ipo', 'listed', 'refinancing', 'transfer', 'restructure', 'fraud_response'));
    END IF;
END
$$;

COMMENT ON COLUMN projects.business_category IS
    '质控业务分类码（A / A1~A8、B / B1~B6、C），NULL 为未填写（判定时按 C 类并标注默认），IPO 等场景见 scenario';
COMMENT ON COLUMN projects.scenario IS
    '专项场景：normal / ipo / listed / refinancing / transfer / restructure / fraud_response';
