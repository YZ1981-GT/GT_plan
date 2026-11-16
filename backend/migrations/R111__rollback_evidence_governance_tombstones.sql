-- R111: 回滚 V111（证据 tombstone）。
DO $$
BEGIN
    IF to_regclass('public.evidence_tombstones') IS NOT NULL
       AND EXISTS (SELECT 1 FROM evidence_tombstones LIMIT 1) THEN
        RAISE EXCEPTION 'R111 拒绝回滚：evidence_tombstones 含永久清理审计事实';
    END IF;
END $$;
DROP TRIGGER IF EXISTS trg_evidence_tombstone_update ON evidence_tombstones;
DROP TRIGGER IF EXISTS trg_evidence_tombstone_delete ON evidence_tombstones;
DROP FUNCTION IF EXISTS evgov_forbid_tombstone_update();
DROP FUNCTION IF EXISTS evgov_forbid_tombstone_delete();
DROP TABLE IF EXISTS evidence_tombstones;
