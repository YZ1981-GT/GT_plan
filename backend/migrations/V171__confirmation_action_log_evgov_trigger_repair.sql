-- V171: 补齐 V128「应用后被原地改写」而从未在库里执行的效果
--
-- spec: migration-integrity-and-enum-drift-closure（Requirement 1）
--
-- 事实（2026-09-29 现查真库 + git 历史）：schema_version 记录的 V128 checksum 对应
-- 2026-07-26 00:04 的首版（commit 833a37fa5）。同日 17:06（04580b855）文件被原地改写：
-- 触发器改名并换绑到 evgov_forbid_update/delete()、新增两条表注释。已应用的迁移不会重跑，
-- 改写内容在已有库上从未执行 —— 真库 confirmation_action_log 仍是首版的
-- trg_conf_action_log_no_update/no_delete → 专用函数（RAISE 无 ERRCODE ⇒ SQLSTATE P0001），
-- 与其余 8 张 evgov append-only 表的拒绝码（UPDATE 23514 / DELETE 23001）不一致。
--
-- 本迁移只补「改写版相对首版多出的效果」，不改 schema_version 里 V128 的 checksum
-- （漂移是历史事实，登记在 app/core/migration_drift_ledger.py）。
--
-- 🔴 evgov 函数体钉回 V108 / V111 原文：当前 V128 文件里的 evgov_forbid_update() 写成了
--    restrict_violation —— 新库按当前 V128 执行会把其余 8 张表的 UPDATE 拒绝码一并翻成 23001。
--    这里用 CREATE OR REPLACE 收敛到 V108（check_violation）/ V111（restrict_violation），
--    使「老库」与「新库」两条路径终态一致。
--
-- 幂等：DROP … IF EXISTS / CREATE OR REPLACE；新库（已按当前 V128 建好新触发器、没有旧触发器）
-- 上所有 DROP 都是 no-op。

CREATE OR REPLACE FUNCTION evgov_forbid_update() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION '% 为不可变/append-only 表，禁止 UPDATE (id=%)', TG_TABLE_NAME, OLD.id
        USING ERRCODE = 'check_violation';
END;
$fn$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION evgov_forbid_delete() RETURNS trigger AS $fn$
BEGIN
    RAISE EXCEPTION '% 为不可变表，禁止 DELETE (id=%)', TG_TABLE_NAME, OLD.id
        USING ERRCODE = 'restrict_violation';
END;
$fn$ LANGUAGE plpgsql;

-- 首版触发器与其专用函数（先删触发器再删函数；函数不加 CASCADE —— 若另有依赖应当失败而不是连带删除）
DROP TRIGGER IF EXISTS trg_conf_action_log_no_update ON confirmation_action_log;
DROP TRIGGER IF EXISTS trg_conf_action_log_no_delete ON confirmation_action_log;
DROP FUNCTION IF EXISTS trg_conf_action_log_forbid_update();
DROP FUNCTION IF EXISTS trg_conf_action_log_forbid_delete();

CREATE OR REPLACE TRIGGER trg_conf_action_log_forbid_update
    BEFORE UPDATE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_update();

CREATE OR REPLACE TRIGGER trg_conf_action_log_forbid_delete
    BEFORE DELETE ON confirmation_action_log
    FOR EACH ROW EXECUTE FUNCTION evgov_forbid_delete();

-- 表注释（与当前 V128 文本逐字一致）
COMMENT ON TABLE confirmation_attachment_link IS 'design §Data Models: 函证↔附件关联，role=outbound(发函件)/inbound(回函件)，inbound 强配对到 paired_outbound_attachment_id';
COMMENT ON TABLE confirmation_action_log IS 'design §Data Models: 函证操作审计留痕，append-only（DB 触发器禁 UPDATE/DELETE，复用 evgov_forbid_update/delete 模式）';
