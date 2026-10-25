-- R170：回滚 V170（knowledge_folders.system_key）
--
-- 🔴 回滚后系统文件夹失去定位键：AI 笔记转存 / A17-3 咨询附件会各自再建一份新的项目文件夹
--    （旧文件夹及其文档仍在，只是不再被自动定位）。回滚前如需保留对应关系，请先导出本列。
-- 顺序：先删依赖列的索引，再删列。
DROP INDEX IF EXISTS uq_knowledge_folders_system_key;

ALTER TABLE knowledge_folders DROP COLUMN IF EXISTS system_key;
