-- R108: 回滚 V108。
-- OCR、人工确认、写回、引用快照、复核关闭、归档 manifest、法律保留和 outbox 都是合规/审计事实，
-- 不允许用 DROP 表伪造无损回滚。
DO $$ BEGIN
    RAISE EXCEPTION 'R108 拒绝自动回滚：Evidence Governance OCR/引用/复核/归档/LegalHold 数据须使用备份恢复';
END $$;
