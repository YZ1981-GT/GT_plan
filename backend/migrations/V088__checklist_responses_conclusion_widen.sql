-- V088: 扩大 checklist_responses.conclusion — 支持 pass/reject/signed/pending 等 A21/A16 签字态

ALTER TABLE checklist_responses
    ALTER COLUMN conclusion TYPE VARCHAR(32);

COMMENT ON COLUMN checklist_responses.conclusion IS 'Y/N/NA/pass/reject/signed/pending/done 等';
