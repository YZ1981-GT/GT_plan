-- V121: related_party_registry 增加 detail JSONB 列
-- 承载源模板 B19-1 管理层关联方清单的描述性字段：
--   企业类型 / 注册地 / 法人代表 / 业务性质 / 注册资本 / 持股比例%
-- 这些字段不参与各循环关联方核对（核对仅用 name），仅供披露与台账展示。
-- 幂等：information_schema.columns 检测列存在性；additive nullable，drift 检测视为兼容。

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
    WHERE table_name = 'related_party_registry' AND column_name = 'detail') THEN
    ALTER TABLE related_party_registry ADD COLUMN detail JSONB;
  END IF;
END $$;
