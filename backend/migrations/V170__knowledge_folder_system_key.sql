-- V170: knowledge_folders.system_key —— 系统文件夹（项目知识文件夹等）的稳定定位键
--
-- spec: knowledge-base-retrieval-and-authz-closure（Requirement 5.8，design §六）
--
-- 背景（2026-09-29 现读代码）：AI 笔记转存按 KnowledgeFolder.project_id 定位「AI 对话笔记」
-- 文件夹 —— 该列在 ORM 与真库都不存在 ⇒ 转存恒 internal_error；A17-3 咨询附件上传到一个
-- 不存在的端点。两者都需要「每个项目一个、并发安全、可幂等定位」的系统文件夹，而按
-- 名称定位会被用户同名文件夹劫持。
--
-- 键格式：project:{project_id}（项目根文件夹）/ project:{project_id}:{slot}（子文件夹）。
-- 部分唯一索引只约束**未删除**行：管理员删掉系统文件夹后，下次定位会重建新的一份。
--
-- 幂等：ADD COLUMN / CREATE INDEX 均 IF NOT EXISTS。
ALTER TABLE knowledge_folders ADD COLUMN IF NOT EXISTS system_key VARCHAR(120);

CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_folders_system_key
    ON knowledge_folders (system_key)
    WHERE system_key IS NOT NULL AND is_deleted = false;

COMMENT ON COLUMN knowledge_folders.system_key IS
    '系统文件夹定位键（project:{pid} / project:{pid}:{slot}）；用户文件夹为 NULL';
