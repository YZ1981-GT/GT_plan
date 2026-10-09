-- R168: 回滚 V168（补回 knowledge_source_type_enum 的 'knowledge_doc'）
-- PostgreSQL 不支持从 enum 类型移除已加入的值（无 DROP VALUE）。
-- 'knowledge_doc' 由 V042 声明、ORM KnowledgeSourceType 也声明；V168 只是修复 V042
-- 未真正生效的问题。单独回滚 V168 时 V042 仍登记为已应用，若删掉该值会让 ORM 与库再次不一致，
-- 故回滚为**有意的 no-op**。确需移除请走 R042（离线重建 enum，高风险人工操作）。
SELECT 1;
