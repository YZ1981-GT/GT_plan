-- V178：合并工作底稿 Runtime CAS、公式来源绑定与刷新审计扩展
--
-- consol_worksheet_data 继续保持项目/年度/sheet_key 作用域；version 是可靠的
-- 整数 CAS 标识，不把 node_key 拼进 worksheet 地址。公式 source_scope/binding
-- 作为 JSONB 保存，供 runtime 在执行前解析并审阅。DraftRefreshSnapshot 保存
-- source_formula_id/source_scope，refresh_id 作为本次运行的 run identity。
-- 所有 DDL 幂等；回滚见 R178。

ALTER TABLE consol_worksheet_data
    ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;

ALTER TABLE draft_refresh_snapshot
    ADD COLUMN IF NOT EXISTS source_formula_id UUID;

ALTER TABLE draft_refresh_snapshot
    ADD COLUMN IF NOT EXISTS source_scope JSONB;

ALTER TABLE wp_formula
    ADD COLUMN IF NOT EXISTS source_scope JSONB;

ALTER TABLE wp_formula
    ADD COLUMN IF NOT EXISTS binding JSONB;

COMMENT ON COLUMN consol_worksheet_data.version IS
    '工作底稿 JSON 的单调 CAS 版本；公式 Runtime 只在 expected version 命中时写入';

COMMENT ON COLUMN draft_refresh_snapshot.source_formula_id IS
    '产生本次业务写入的 WpFormula；NULL 表示非公式来源的刷新单元';

COMMENT ON COLUMN draft_refresh_snapshot.source_scope IS
    '公式执行时解析出的结构化来源范围快照';

COMMENT ON COLUMN wp_formula.source_scope IS
    '公式来源范围：project/year/node_key/include_descendants/domains 等结构化绑定';

COMMENT ON COLUMN wp_formula.binding IS
    '公式来源绑定的可审阅配置，例如 template/kind/参数；不存拼接伪地址';
