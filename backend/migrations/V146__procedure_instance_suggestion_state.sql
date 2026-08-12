-- V146: procedure_instances 增加 suggestion_state（裁剪建议态与理由码）
--
-- Spec: procedure-trimming-and-delegation-intelligence — Wave 2 Task 11
-- Requirements: 6.4（驳回不再被重新建议）、8.1（结构化理由码）
--
-- ═══ 为什么落在 procedure_instances 而不是 procedure_trim_schemes ═══
--
-- 本列承载的是**程序实例的当前状态**（这条程序的建议理由码是什么、审计师有没有
-- 驳回过建议），它跟着程序实例走。
--
-- 而 `procedure_trim_schemes.trim_data` 实测是**带日期的多份历史方案快照**
-- （`裁剪方案-D-20260706` 等），键空间 = procedure_instance UUID、值 =
-- `{status, skip_reason}`。把「当前建议态」塞进历史快照语义错位：同一实例会在
-- 多份快照里各有一份互相矛盾的建议态，且新建方案时当前态会凭空消失。
--
-- ═══ 结构（三段各自独立，勿合并）═══
--
-- {
--   "reason_code": "below_materiality",   -- TrimReasonCode 取值；与 skip_reason 并列同事务写入
--   "rejected": false,                    -- true = 审计师驳回过建议 ⇒ 决策内核恒判 keep（R6.4）
--   "rejected_by": null,                  -- 驳回留痕（who）
--   "rejected_at": null,                  -- 驳回留痕（when）
--   "evidence": {                         -- 判定当时实际用到的数值，供理由留痕与复核追溯（R3.10）
--     "account_amount": 12345.67,
--     "threshold_kind": "performance_materiality",
--     "threshold": 500000.0,
--     "risk_level": null,
--     "completeness_source": "cycle_default"
--   }
-- }
--
-- ═══ 三态语义（NULL 不等于「无建议」）═══
--
--   NULL                          = 从未参与过智能裁剪（存量记录全为此态）
--   {"rejected": true, ...}       = 审计师已驳回 ⇒ 永不再被建议
--   {"reason_code": "...", ...}   = 有建议理由码（确认后与 skip_reason 并存）
--
-- 存量记录保持 NULL ⇒ 只有 `skip_reason` 自由文本的裁剪仍按原文显示（R8.4），
-- 不得因引入理由码而显示为空或「未知理由」。
--
-- ═══ 编号沿革 ═══
-- design.md 写 V145 只是示意；落地时实测 V145 已被
-- `V145__report_config_dual_family_rou_lease.sql` 占用（磁盘与 schema_version 双侧一致），
-- 故取 V146。迁移号永不复用。
--
-- 幂等：ADD COLUMN IF NOT EXISTS（MigrationRunner 铁律）。
-- 🔴 新增列必须同步加 ORM mapped_column，否则列在表里存在而代码写不进去
--    （见 app/models/procedure_models.py::ProcedureInstance.suggestion_state）。

ALTER TABLE procedure_instances
    ADD COLUMN IF NOT EXISTS suggestion_state JSONB;

COMMENT ON COLUMN procedure_instances.suggestion_state IS
    '裁剪建议态三态：NULL=未参与智能裁剪 / {"rejected":true,...}=已驳回(永不再建议) / {"reason_code","evidence",...}=建议理由码与判据数值';
