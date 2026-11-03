-- V217：ProcedureInstance active 规范化身份约束（spec trim-generation-plan-followup-optimizations R2）。
-- 冲突时 fail-closed，不自动合并状态、委派或审计历史。
-- R3 的粗裁确认投影是 V218（本文件在共享开发库登记后才修正约束存在性判断，漂移见 migration_drift_ledger）。

DO $$
DECLARE
    conflict_count integer;
BEGIN
    SELECT count(*) INTO conflict_count
    FROM (
        SELECT project_id, upper(btrim(audit_cycle)), upper(btrim(procedure_code))
        FROM procedure_instances
        WHERE NOT is_deleted
        GROUP BY 1, 2, 3
        HAVING count(*) > 1
    ) AS conflicts;
    IF conflict_count > 0 THEN
        RAISE EXCEPTION 'V217: % active normalized procedure identity conflicts; resolve manually', conflict_count;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS procedure_instance_identity_v217_backup (
    instance_id UUID PRIMARY KEY REFERENCES procedure_instances(id) ON DELETE CASCADE,
    old_audit_cycle VARCHAR(10) NOT NULL,
    old_procedure_code VARCHAR(50) NOT NULL,
    old_wp_code VARCHAR(50),
    backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO procedure_instance_identity_v217_backup (
    instance_id, old_audit_cycle, old_procedure_code, old_wp_code
)
SELECT id, audit_cycle, procedure_code, wp_code
FROM procedure_instances
WHERE audit_cycle IS DISTINCT FROM upper(btrim(audit_cycle))
   OR procedure_code IS DISTINCT FROM upper(btrim(procedure_code))
   OR (wp_code IS NOT NULL AND wp_code IS DISTINCT FROM upper(btrim(wp_code)))
ON CONFLICT (instance_id) DO NOTHING;

UPDATE procedure_instances
SET audit_cycle = upper(btrim(audit_cycle)),
    procedure_code = upper(btrim(procedure_code)),
    wp_code = CASE WHEN wp_code IS NULL THEN NULL ELSE upper(btrim(wp_code)) END
WHERE audit_cycle IS DISTINCT FROM upper(btrim(audit_cycle))
   OR procedure_code IS DISTINCT FROM upper(btrim(procedure_code))
   OR (wp_code IS NOT NULL AND wp_code IS DISTINCT FROM upper(btrim(wp_code)));

-- 约束是否已存在按本表（search_path 解析的 procedure_instances）判断：pg_constraint 是全库目录，
-- 只按名字查会被其他 schema 的同名约束骗过而跳过创建（随机 schema 迁移测试即踩到）。
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_procedure_instances_audit_cycle_canonical'
                     AND conrelid = 'procedure_instances'::regclass) THEN
        ALTER TABLE procedure_instances ADD CONSTRAINT ck_procedure_instances_audit_cycle_canonical
            CHECK (audit_cycle = upper(btrim(audit_cycle)) AND btrim(audit_cycle) <> '');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_procedure_instances_code_canonical'
                     AND conrelid = 'procedure_instances'::regclass) THEN
        ALTER TABLE procedure_instances ADD CONSTRAINT ck_procedure_instances_code_canonical
            CHECK (procedure_code = upper(btrim(procedure_code)) AND btrim(procedure_code) <> '');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'ck_procedure_instances_wp_code_canonical'
                     AND conrelid = 'procedure_instances'::regclass) THEN
        ALTER TABLE procedure_instances ADD CONSTRAINT ck_procedure_instances_wp_code_canonical
            CHECK (wp_code IS NULL OR (wp_code = upper(btrim(wp_code)) AND btrim(wp_code) <> ''));
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_procedure_instances_active_identity_norm
    ON procedure_instances (
        project_id,
        upper(btrim(audit_cycle)),
        upper(btrim(procedure_code))
    )
    WHERE NOT is_deleted;

COMMENT ON INDEX uq_procedure_instances_active_identity_norm IS
    '每项目每循环 active 程序编码规范化唯一；软删历史不占 active 身份';
COMMENT ON TABLE procedure_instance_identity_v217_backup IS
    'V217 规范化前原值；R217 仅在现值仍等于迁移目标时恢复，避免覆盖后续人工修改';
