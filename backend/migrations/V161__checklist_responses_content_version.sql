-- V161: checklist_responses 乐观锁版本列（content_version）
--
-- 背景（P0-项4 · spec d4-dual-mode-formula-governance）：
--   D4（及其它循环）导入把整张 sheet 的行以单条 JSON blob 按 (wp_id,item_id) upsert 进本表，
--   `ON CONFLICT ... DO UPDATE` 是 last-write-wins。两名有编辑权的项目成员并发导入同一 sheet 时，
--   后写者静默覆盖先写者，无任何冲突提示。加乐观锁版本列以支持 If-Match 式冲突检测（409）。
--
-- 幂等：ADD COLUMN IF NOT EXISTS，重复执行安全。
-- 可回滚：见 R161（DROP COLUMN）。旧写路径（不传 base_version）按"首次创建/覆盖"语义，兼容存量数据。

ALTER TABLE checklist_responses
    ADD COLUMN IF NOT EXISTS content_version INTEGER NOT NULL DEFAULT 1;

COMMENT ON COLUMN checklist_responses.content_version IS
    '乐观锁版本号（每次成功写入 +1）；导入可选带 base_version 做 If-Match 冲突检测，不匹配返 409';
