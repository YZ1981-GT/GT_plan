-- R171: 回滚 V171 —— 恢复 confirmation_action_log 首版的 append-only 触发器与表注释缺省
--
-- 🔴 回滚后表必须仍受保护：先建回首版专用函数与触发器，再删 V171 的触发器（全程不存在「无触发器」窗口）。
-- evgov_forbid_update/delete() 的函数体**不回退**：V171 只是把它们钉回 V108 / V111 原文；
-- 回退会让「按当前 V128 建的新库」回到 UPDATE 拒绝码被翻成 23001 的错误状态（放大错误）。

CREATE OR REPLACE FUNCTION trg_conf_action_log_forbid_update() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION 'confirmation_action_log is append-only: UPDATE forbidden';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION trg_conf_action_log_forbid_delete() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION 'confirmation_action_log is append-only: DELETE forbidden';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_conf_action_log_no_update
    BEFORE UPDATE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION trg_conf_action_log_forbid_update();

CREATE OR REPLACE TRIGGER trg_conf_action_log_no_delete
    BEFORE DELETE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION trg_conf_action_log_forbid_delete();

DROP TRIGGER IF EXISTS trg_conf_action_log_forbid_update ON confirmation_action_log;
DROP TRIGGER IF EXISTS trg_conf_action_log_forbid_delete ON confirmation_action_log;

COMMENT ON TABLE confirmation_attachment_link IS NULL;
COMMENT ON TABLE confirmation_action_log IS NULL;
