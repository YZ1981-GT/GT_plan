-- R133 回滚：移除 attachment_working_paper 唯一索引（V133）
-- 注：V133 去重删除的存量重复行不恢复（数据清理不可逆，符合迁移语义）。
DROP INDEX IF EXISTS uq_awp_attachment_wp;
