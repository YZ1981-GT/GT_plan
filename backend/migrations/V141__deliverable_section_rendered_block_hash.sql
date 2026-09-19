-- V141: deliverable_section_state 增加 rendered_block_hash（Rendered_Block_Hash）
-- Spec: deliverable-lineage-wiring-and-writeback-closure — Task 3 / Requirements 4.1, 12.6
--
-- 背景（实证缺陷）：DeliverableRefreshService._detect_user_edits 原先拿
--   sha256(块内纯文本)
-- 去比
--   source_snapshot_hash = sha256(json{section_code,text_content,table_data,audited_amounts})
-- 两个哈希域根本不同 ⇒ 永远不等 ⇒ refresh_section 恒返回 requires_confirm=True，
-- 用户每次刷新都被要求确认"覆盖人工编辑"。
--
-- 修法：新增独立列承载「生成/刷新时实际写入块内文字的规范化 sha256」，与
-- source_snapshot_hash（源数据域）严格分离。计算入口单一真源 =
-- app.services.section_anchor_utils.block_text_hash。
--
-- NULL 语义：存量交付件（本 spec 接线前生成）无此值 → 判定「无人工编辑」（fail-open，
-- 与引入前行为一致，需求 4.4）。
--
-- 幂等：ADD COLUMN IF NOT EXISTS，可重入。

ALTER TABLE deliverable_section_state
    ADD COLUMN IF NOT EXISTS rendered_block_hash VARCHAR(64);

COMMENT ON COLUMN deliverable_section_state.rendered_block_hash IS
    'Rendered_Block_Hash：生成/刷新时写入块内文字的规范化 sha256（区分人工编辑 vs 上游变化）；NULL=存量交付件，视为无人工编辑';
