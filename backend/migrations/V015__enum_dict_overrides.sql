-- V015__enum_dict_overrides.sql
-- DT-3 方案 B 落地：枚举字典 value 锁定 + label/color 可改
--
-- 设计原则（spec proposal-remaining-18 task 1.5 复盘修复）：
--   - value 与后端枚举（WpFileStatus.draft 等）强绑定，DB 改 value 会破坏代码逻辑 → 不允许改
--   - label / color 仅前端展示用，可由 admin 在线修改 → 用 overrides 表覆盖
--   - 不允许新增 value 或物理删除（仍返 405），避免代码引用悬空
--
-- 合并逻辑：
--   GET /dicts → _DICTS（代码硬编码）+ enum_dict_overrides（DB 覆盖优先）

CREATE TABLE IF NOT EXISTS enum_dict_overrides (
    dict_key VARCHAR(64) NOT NULL,
    value VARCHAR(64) NOT NULL,
    label_override VARCHAR(255),
    color_override VARCHAR(32),
    updated_by UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (dict_key, value)
);

COMMENT ON TABLE enum_dict_overrides
    IS 'DT-3 枚举字典 label/color 覆盖表（value 由代码锁定，仅展示属性可改）';
COMMENT ON COLUMN enum_dict_overrides.label_override
    IS 'NULL 表示用代码默认 label；非 NULL 表示覆盖';
COMMENT ON COLUMN enum_dict_overrides.color_override
    IS 'NULL 表示用代码默认 color；可选值 success/warning/danger/info/空字符串';
