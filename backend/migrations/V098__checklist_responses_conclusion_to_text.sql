-- V098: 扩展 checklist_responses.conclusion 列为 TEXT
-- 原因：C23~C26 专属组件存储自由格式文本（步骤执行结果/分析结论等），VARCHAR(32) 远不够用
-- 影响：无数据丢失，ALTER TYPE VARCHAR→TEXT 是在线操作（PG 不重写表）

ALTER TABLE checklist_responses
    ALTER COLUMN conclusion TYPE TEXT;
