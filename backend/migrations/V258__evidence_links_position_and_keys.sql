-- V213: 行级证据链接 evidence_links 补齐（spec attachment-evidence-intake 需求 3.5、3.6）。
--
-- 证据采集单一入口把行级位置放在 evidence_links（ADR-AEI-02）：行级附件组件按（底稿, 表页, 单元格 / 槽位）取数。
-- 真库此表只有主键：ORM 声明的两个外键、两个索引从未落库（评估报告 2.3-4）。
--   - 外键 NOT VALID：只约束此后写入，不校验存量行（真库 0 行；别的环境若有孤儿行也不阻断迁移）。
--     按「指向哪张表」判断是否已有外键：ORM 建表的环境里外键名是 evidence_links_*_fkey，不能只看本迁移起的名字。
--   - cell_ref 20 → 100：位置约定 row:{行 id}（留给函证 / 抽凭行）放不下 UUID。
--   - 组合索引 (wp_id, sheet_name, cell_ref)：按位置取。
ALTER TABLE evidence_links ALTER COLUMN cell_ref TYPE VARCHAR(100);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'evidence_links'::regclass AND contype = 'f'
          AND confrelid = 'working_paper'::regclass
    ) THEN
        ALTER TABLE evidence_links ADD CONSTRAINT fk_evidence_links_wp
            FOREIGN KEY (wp_id) REFERENCES working_paper(id) NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'evidence_links'::regclass AND contype = 'f'
          AND confrelid = 'attachments'::regclass
    ) THEN
        ALTER TABLE evidence_links ADD CONSTRAINT fk_evidence_links_attachment
            FOREIGN KEY (attachment_id) REFERENCES attachments(id) NOT VALID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_evidence_wp ON evidence_links (wp_id);
CREATE INDEX IF NOT EXISTS idx_evidence_attachment ON evidence_links (attachment_id);
CREATE INDEX IF NOT EXISTS idx_evidence_links_position ON evidence_links (wp_id, sheet_name, cell_ref);
