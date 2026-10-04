-- V167: 合并企业树按三码自动构建（spec consol-tree-three-code-autobuild）
--
-- 1. projects.relation_to_parent —— 本企业与上级企业的关系
--    subsidiary = 子公司（独立法人，合并时抵销）/ branch = 分公司（非独立法人，并入母公司汇总）
--    NULL = 未填写（上级企业代码为空时恒为 NULL）。
--    企业树由 company_code / parent_company_code / ultimate_company_code + 本列实时推导，
--    parent_project_id 自本迁移起降为派生值（sync_group_links 重算），不再是树的真源。
--
-- 2. elimination_entries.branch_entity_code —— 分录归属的差额节点
--    NULL = 所在合并项目的「合并差额」节点；非空 = 该企业的「母分差额」节点。
--    related_company_codes 自本迁移起只作留痕与筛选，不参与金额分摊（修双重计数）。
--
-- 3. consol_worksheet.node_company_code 自本迁移起存企业树 node_key（{企业代码}:{角色}），
--    列名沿用（真库该表 0 行，旧纯代码键由全量重算清理）。
--
-- 4. projects.consolidation_type 保留为历史列：合并方式改由下级企业的与上级关系自动识别，
--    业务代码不再读写本列（配置接口写入即 400）。
--
-- 存量安全：2026-09-29 真库现查上级代码全空、elimination_entries 0 行 ⇒ 零回填、零违约。
-- 幂等：ADD COLUMN IF NOT EXISTS / 约束按 pg_constraint 判存 / CREATE INDEX IF NOT EXISTS。

-- ── 1. projects.relation_to_parent ───────────────────────────────────────────
ALTER TABLE projects ADD COLUMN IF NOT EXISTS relation_to_parent VARCHAR(20);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_projects_relation_to_parent'
    ) THEN
        ALTER TABLE projects
            ADD CONSTRAINT ck_projects_relation_to_parent
            CHECK (relation_to_parent IS NULL OR relation_to_parent IN ('subsidiary', 'branch'));
    END IF;
END $$;

COMMENT ON COLUMN projects.relation_to_parent IS
  '与上级企业的关系：subsidiary=子公司（合并时抵销）、branch=分公司（并入母公司汇总），'
  'NULL=未填。企业树按三码与本列实时推导，parent_project_id 为派生值';

COMMENT ON COLUMN projects.consolidation_type IS
  '历史列（V167 起不再读写）：合并方式改由下级企业的与上级关系自动识别';

-- ── 2. elimination_entries.branch_entity_code ─────────────────────────────────
ALTER TABLE elimination_entries ADD COLUMN IF NOT EXISTS branch_entity_code VARCHAR(50);

COMMENT ON COLUMN elimination_entries.branch_entity_code IS
  '分录归属的差额节点：NULL=所在合并项目的合并差额，非空=该企业代码的母分差额。'
  'related_company_codes 只作留痕，不参与金额分摊';

-- ── 3. consol_worksheet 节点键语义 ────────────────────────────────────────────
COMMENT ON COLUMN consol_worksheet.node_company_code IS
  '企业树节点键 node_key（格式 企业代码:角色，如 X:consol / X:consol_elim / X:parent），V167 起';

-- ── 4. 查询路径索引 ──────────────────────────────────────────────────────────
-- 树推导按（年度, 上级代码）逐层取下级
CREATE INDEX IF NOT EXISTS ix_projects_group_parent
  ON projects (audit_year, parent_company_code)
  WHERE is_deleted = false;

-- 差额节点按（合并项目, 年度, 归属企业）取分录
CREATE INDEX IF NOT EXISTS ix_elim_entries_project_year_branch
  ON elimination_entries (project_id, year, branch_entity_code)
  WHERE is_deleted = false;
