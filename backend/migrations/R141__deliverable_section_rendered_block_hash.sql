-- R141: 回滚 V141 —— 删除 deliverable_section_state.rendered_block_hash
-- Spec: deliverable-lineage-wiring-and-writeback-closure
--
-- 回滚代价：人工编辑检测退化为「无基线 ⇒ 视为无人工编辑」（fail-open），
-- 与 V141 之前的行为一致（那时该判定因哈希域不匹配恒为 True，反而更差）。
-- 幂等：IF EXISTS。

ALTER TABLE deliverable_section_state
    DROP COLUMN IF EXISTS rendered_block_hash;
