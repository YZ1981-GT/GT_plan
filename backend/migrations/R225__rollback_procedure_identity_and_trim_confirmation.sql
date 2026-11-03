-- R217：撤销 V217（ProcedureInstance 规范化身份约束）并安全恢复迁移前原值。
-- V217 头注释写「R3 的确认投影在同版本后半部分追加」：V217 已在共享开发库按第一部分登记，
-- R3 因此改为独立的 V218 / R218（不改已登记文件，避免 checksum 漂移）。回滚 V218 先于本脚本。

DROP INDEX IF EXISTS uq_procedure_instances_active_identity_norm;

ALTER TABLE procedure_instances
    DROP CONSTRAINT IF EXISTS ck_procedure_instances_audit_cycle_canonical;
ALTER TABLE procedure_instances
    DROP CONSTRAINT IF EXISTS ck_procedure_instances_code_canonical;
ALTER TABLE procedure_instances
    DROP CONSTRAINT IF EXISTS ck_procedure_instances_wp_code_canonical;

DO $$
BEGIN
    IF to_regclass('procedure_instance_identity_v217_backup') IS NOT NULL THEN
        UPDATE procedure_instances AS p
        SET audit_cycle = b.old_audit_cycle,
            procedure_code = b.old_procedure_code,
            wp_code = b.old_wp_code
        FROM procedure_instance_identity_v217_backup AS b
        WHERE p.id = b.instance_id
          AND p.audit_cycle = upper(btrim(b.old_audit_cycle))
          AND p.procedure_code = upper(btrim(b.old_procedure_code))
          AND p.wp_code IS NOT DISTINCT FROM
              CASE WHEN b.old_wp_code IS NULL THEN NULL ELSE upper(btrim(b.old_wp_code)) END;
    END IF;
END
$$;

DROP TABLE IF EXISTS procedure_instance_identity_v217_backup;
