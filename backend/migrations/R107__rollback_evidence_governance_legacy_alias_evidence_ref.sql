-- R107: 回滚 V107。
-- V107 对 attachments.audit_year 做了历史回填，并建立 legacy alias/evidence graph；没有迁移前快照，
-- 无法安全恢复哪些值原来为 NULL，因此拒绝自动回滚，避免破坏证据引用。
DO $$ BEGIN
    RAISE EXCEPTION 'R107 拒绝自动回滚：包含附件年度回填与证据引用图迁移，请使用迁移前备份恢复';
END $$;
