-- R271: 仅允许在 ledger_import_attempts 为空时回滚。
-- protect-non-empty: ledger_import_attempts
-- dialect:postgresql-only
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ledger_import_attempts LIMIT 1) THEN
        RAISE EXCEPTION
            'ledger_import_attempts contains rows; clean up attempts before rollback'
            USING ERRCODE = 'check_violation';
    END IF;
END
$$;

DROP TABLE IF EXISTS ledger_import_attempts;
