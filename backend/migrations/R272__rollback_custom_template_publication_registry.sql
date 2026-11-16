-- R272: 回滚 V272（custom template publication registry）
-- 顺序：先删 pins（有 FK 指向 publications），再删 publications。

DROP INDEX IF EXISTS ix_custom_publication_org_state;
DROP TABLE IF EXISTS custom_template_publication_pins;
DROP TABLE IF EXISTS custom_template_publications;
