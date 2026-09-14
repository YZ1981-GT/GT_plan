-- V163: wp_formula 稳定键三列 + 回填（P0-项1 · spec d4-dual-mode-formula-governance）
--
-- 背景：既有 identity (wp_id, sheet_name, target_cell) 里 sheet_name 是展示名（可重命名 →
--   公式失联）。新增稳定键三列：stable_sheet_key（规范化 sheet 名，展示重命名不改键）+
--   row_key/field_key（A1 地址拆行/列）。preset_version 不进 identity（无该列）；
--   definition_version 是定义版本（既有列，正交，保留不动）。
--
-- 过渡策略：新增列**可空**，旧列 (sheet_name/target_cell) + 旧唯一索引
--   uq_wp_formula_wp_sheet_cell **保留一版**（不删），双写并存。新唯一索引对已回填行生效。
--
-- 幂等：ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS，重复执行安全。
-- 可回滚：见 R163（DROP 新列与新索引，旧键不受影响）。

-- 逐列独立语句（每条一列，非多子句合并）：便于三层一致守卫逐列抽取列名。
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS stable_sheet_key VARCHAR(255);
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS row_key VARCHAR(50);
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS field_key VARCHAR(50);
ALTER TABLE wp_formula ADD COLUMN IF NOT EXISTS stable_key_needs_review BOOLEAN NOT NULL DEFAULT false;

-- ── 回填（仅回填尚未填的行；与 app.services.formula_management.stable_key 逻辑对齐）──
-- stable_sheet_key：剥离前导排序前缀（中文数字顿号 / "1." / "（一）"）+ 折叠空白 + trim。
-- row_key/field_key：A1 地址拆列字母 + 行号；列统一大写。无法解析为 A1 → 标 needs_review。

UPDATE wp_formula
SET
    stable_sheet_key = btrim(
        regexp_replace(
            regexp_replace(
                COALESCE(sheet_name, ''),
                '^\s*([一二三四五六七八九十]+[、.．]?[0-9]*[、.．]?|[0-9]+[、.．]|[（(][一二三四五六七八九十0-9]+[)）])\s*',
                ''
            ),
            '[\s\u3000]+', ' ', 'g'
        )
    ),
    field_key = CASE
        WHEN target_cell ~ '^[A-Za-z]+[0-9]+$' THEN upper(substring(target_cell from '^([A-Za-z]+)[0-9]+$'))
        ELSE COALESCE(btrim(target_cell), '')
    END,
    row_key = CASE
        WHEN target_cell ~ '^[A-Za-z]+[0-9]+$' THEN substring(target_cell from '^[A-Za-z]+([0-9]+)$')
        ELSE NULL
    END,
    stable_key_needs_review = CASE
        WHEN target_cell ~ '^[A-Za-z]+[0-9]+$'
             AND btrim(COALESCE(sheet_name, '')) <> '' THEN false
        ELSE true
    END
WHERE stable_sheet_key IS NULL;

-- 新唯一索引：对已回填（stable_sheet_key 非空）的行生效；needs_review 行（row_key 可能 NULL）
-- 用 COALESCE 兜底进索引，避免 NULL 使唯一性失效。旧唯一索引保留一版共存。
CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_formula_stable_key
    ON wp_formula (wp_id, stable_sheet_key, COALESCE(row_key, ''), field_key)
    WHERE stable_sheet_key IS NOT NULL;

COMMENT ON COLUMN wp_formula.stable_sheet_key IS
    '稳定 sheet 键（规范化 sheet_name，展示重命名不改键）；identity 组成，preset_version 不入';
COMMENT ON COLUMN wp_formula.stable_key_needs_review IS
    'target_cell 无法安全解析为 A1（命名单元等）→ true，供人工复核；不静默丢';
