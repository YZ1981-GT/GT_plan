-- V230: 税审底稿手工填写值（spec tax-workpaper-data-fetch）
--
-- 编号说明：本地库已应用别的分支的 V211（citr_workpaper_edit_versions），
-- 其他分支已占 V211~V219，故取 V230 避免撞号（MigrationRunner 按数字去重）。
--
-- 一行 = 一个项目、一个年度、一张税审底稿（索引编号，如 2-02）的全部手工值；
-- 表头参数存 sheet_code = '__params__'。inputs = {样表 sheet 名: {单元格地址: 值}}。
-- version 每次保存 +1，保存带读到的版本，不一致返回 409。
-- 三层一致：ORM backend/app/models/tax_workpaper_models.py TaxWorkpaperInput；
-- service backend/app/services/tax_workpaper_service.py。

CREATE TABLE IF NOT EXISTS tax_workpaper_inputs (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    sheet_code VARCHAR(64) NOT NULL,
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    version INTEGER NOT NULL DEFAULT 1,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tax_workpaper_inputs_project_year_code
    ON tax_workpaper_inputs (project_id, year, sheet_code);

COMMENT ON TABLE tax_workpaper_inputs IS '税审底稿手工填写值（按项目 + 年度 + 底稿编号）';
COMMENT ON COLUMN tax_workpaper_inputs.inputs IS '{样表 sheet 名: {单元格地址: 数字 / 文字 / null}}';
