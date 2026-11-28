-- R272: 回滚 V272（custom template publication registry）
--
-- R 的无损回滚纪律（spec platform-global-display-settings-closure NFR 数据安全 /
-- design §2）：任何 DROP 之前必须检查「待删数据无法由旧结构无损表示」的情形，
-- 命中即 `RAISE EXCEPTION` 让整单回滚，不得以 warning 后删列。
--
-- 本表族的证据不可重建：publication 的 artifact_digest / authority_ref /
-- candidate_digest 与 pins 的项目绑定都是运行时累积的审计证据，
-- 一旦 DROP 就永久丢失 ⇒ 有任何一行就阻断。
--
-- 顺序：先删 pins（有 FK 指向 publications），再删 publications。

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM custom_template_publications) THEN
        RAISE EXCEPTION
            'R272 拒绝回滚：custom_template_publications 仍有 % 行不可重建的发布证据',
            (SELECT count(*) FROM custom_template_publications);
    END IF;
    IF EXISTS (SELECT 1 FROM custom_template_publication_pins) THEN
        RAISE EXCEPTION
            'R272 拒绝回滚：custom_template_publication_pins 仍有 % 行项目绑定证据',
            (SELECT count(*) FROM custom_template_publication_pins);
    END IF;
END $$;

DROP INDEX IF EXISTS ix_custom_publication_org_state;
DROP TABLE IF EXISTS custom_template_publication_pins;
DROP TABLE IF EXISTS custom_template_publications;
