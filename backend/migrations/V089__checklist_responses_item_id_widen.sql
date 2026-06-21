-- V089: 扩大 checklist_responses.item_id — 支持自定义条目 id（CUSTOM-Sxx-timestamp 格式）
-- 原 VARCHAR(20) 不足以存放 CUSTOM-S02-1781957820961（25+字符）

ALTER TABLE checklist_responses
    ALTER COLUMN item_id TYPE VARCHAR(64);

COMMENT ON COLUMN checklist_responses.item_id IS '条目ID: Q001~Q014(标准)/TOC-S01(章节适用性)/CUSTOM-Sxx-xxx(自定义)';
