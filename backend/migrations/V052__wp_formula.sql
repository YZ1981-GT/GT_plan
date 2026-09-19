-- V052: 自定义底稿公式绑定独立表（custom-workpaper-formula-binding）
-- 背景：自定义底稿的公式 + 写入目标单元格（target_cell）此前无持久化表，
--   既有手动公式编辑器（wp_user_formulas）将公式内嵌 working_paper.parsed_data["user_formulas"]。
--   用户拍板本特性采用独立 wp_formula 表（三层一致：DB 迁移 + ORM Mapped[] + WpFormulaService），
--   与既有 parsed_data 内嵌路径并存互不破坏。
--
-- 注意：id 主键 DEFAULT gen_random_uuid() 仅作裸 SQL 插入兜底；
--   应用层真正由 ORM `default=uuid.uuid4` 赋值（避免 PK 缺 default bug）。
--   CREATE TABLE / CREATE INDEX 全部 IF NOT EXISTS（幂等，可重复运行）。

CREATE TABLE IF NOT EXISTS wp_formula (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID         NOT NULL REFERENCES projects(id),
    wp_id         UUID         NOT NULL REFERENCES working_paper(id),
    sheet_name    VARCHAR(255) NOT NULL,
    target_cell   VARCHAR(50)  NOT NULL,          -- 写入目标单元格（如 B5）
    expression    TEXT         NOT NULL,           -- 公式表达式
    category      VARCHAR(50),                     -- auto_calc / cross_check / ...
    description   TEXT,
    created_by    UUID         REFERENCES users(id),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 一个目标单元格一条公式（同 wp_id + sheet_name + target_cell 覆盖更新而非新增）
CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_formula_wp_sheet_cell
    ON wp_formula (wp_id, sheet_name, target_cell);

CREATE INDEX IF NOT EXISTS idx_wp_formula_project
    ON wp_formula (project_id);
