-- V248: 公式推送目标保存 S5 双层来源信封（计算尝试 + 最终值状态）。
ALTER TABLE formula_push_state ADD COLUMN IF NOT EXISTS provenance JSONB NULL;
