# 平台层契约 — D4 双模式（C0-C3 总口）

> 状态：FROZEN
> 依据：Requirements 5.2, 6.1, 7.1
> 关系：本文件是 C0/C1/C2/C3 四份契约的平台层补充，不重复已冻结内容

## A. 导入 Identity 保留（Requirement 6.1）

### A.1 冻结规则

#### A.1.1 必须保留的 Identity 五元组
导入/导出必须保留以下五项，缺一即拒绝提交：

| Identity 维度 | 载体 | 实现位置 | 状态 |
|--------------|------|---------|------|
| sheet 标识 | `stable_sheet_key` | `SyncContract.sheets[].sheet_key`；`_STABLE_KEY_RE`（小写 ASCII 字符集） | ✅ 已实现 |
| table 标识 | `table_key` | `SyncContract.sheets[].tables[].table_key` | ✅ 已实现 |
| 区域标识 | A1 range（如 `I8:I200`） | `SyncContract.sheets[].tables[].formula_mask[]`；`parse_a1_range()` | ✅ 已实现 |
| 稳定 row key | `row_identity.kind ∈ {field, template_row_key}` | `RowIdentityKind` 枚举；**禁止** `index/ordinal/position/row_number/array_index`（`FORBIDDEN_ROW_IDENTITY_KINDS`） | ✅ 已实现 |
| 公式 mask 身份 | `formula_mask: tuple[str,...]`（A1 区域列表） | `SyncContract.sheets[].tables[].formula_mask`；CS-13 判据：formula 模式 field 的列必须落在已声明 mask 内 | ✅ 已实现 |

#### A.1.2 结构变更必须走 ContentMutationService
- 任何底稿结构变更（增删行列/改公式）必须经 `ContentMutationService.commit()`
- 禁止：位置猜测（position guess）—— `contracts.py` CS-3 无条件拒绝 `col_[a-z]+` 形态；CS-12 拒绝行号作为 footer anchor；CS-10 拒绝 index/ordinal/position 作为行身份
- 禁止：静默扁平化（silent flatten）—— `contracts.py` CS-20 `resolve_extract_carrier()`：当 instrumented identity 与 native structural anchor 均不存在时 `raise ContractCarrierUnavailableError`，**不得降级到中文标题或位置猜测**
- 禁止：按列索引（`col_a, col_b`）替代语义 field_key 导入—— `_GENERATED_COLUMN_PLACEHOLDER` 正则 `^col_[a-z]+$` 在 `assert_stable_key()` 和 `assert_column_key()` 中无条件拒绝（CS-3）

#### A.1.3 导入身份校验（D4 特定）
- D4 导入端点 `/api/workpapers/{wp_id}/d4/import-data` 当前仅做 `Depends(get_current_user)`（认证），**无 CAS 版本校验**
- D4 导入当前**未接入** `ContentMutationService`，直接写 `working_paper.parsed_data`
- **缺口**：D4 导入必须接入 ContentMutationService 以确保单次 commit 原子性（详见 §E）

### A.2 四表取数复用（Requirement 5.2）

#### A.2.1 冻结规则
- 四表取数**必须**复用 `app/services/four_table/` 包及 `ReportLineAccountSpec`
- **禁止**复制科目 SQL 到 D4 专属代码

#### A.2.2 现状（grep 实证）
| 检查项 | 结果 |
|--------|------|
| `app/services/four_table/` 目录存在 | ✅ 17 个 .py 文件 |
| `ReportLineAccountSpec` 定义 | ✅ `report_line_accounts.py:67` |
| `d_cycle_specs.py`（D 循环专用规格） | ✅ 存在 |
| `_d4_operating_revenue.py` 是否复用 four_table | ✅ `from app.services.four_table import LeafRow`（line 48） |
| `_d4_import_export.py` 是否复用 four_table | ❌ **未导入** `four_table` 或 `ReportLineAccountSpec` |
| `_d4_import_export.py` 是否导入 ContentMutationService | ❌ **未导入** |

#### A.2.3 缺口
- `_d4_import_export.py` 的科目取数逻辑需在四表取数端（如 TB 发布/审定表回填）复用 `four_table/`，当前 D4 导入端点仅做数据导入，不触发四表取数 → **UNVERIFIABLE**（需 D4 审定表回填链路实现后才能验证）

---

## B. 权限与 CAS 校验（Requirement 7.1）

### B.1 角色权限规则

#### B.1.1 系统角色定义（grep 实证）
`app/models/base.py:16` — `UserRole(str, enum.Enum)`：

| 角色值 | 含义 |
|--------|------|
| `admin` | 系统管理员（跳过项目权限检查） |
| `partner` | 合伙人 |
| `manager` | 现场经理 |
| `auditor` | 审计助理 |
| `qc` | 质控复核合伙人 |
| `eqcr` | 技术复核人 |
| `readonly` | 只读用户 |

#### B.1.2 权限层级（grep 实证）
`app/deps.py:38` — `PERMISSION_HIERARCHY = {"edit": 3, "review": 2, "readonly": 1}`

`require_project_access(min_permission)` 通过 `assert_project_permission()` 执行，admin 跳过项目级检查。
`require_role(allowed_roles)` 校验 `current_user.role.value`。

#### B.1.3 D4 操作权限矩阵（冻结）

| 操作 | 所需最低权限 | scope | 当前实现 | 状态 |
|------|------------|-------|---------|------|
| 读取底稿（render-config / parsed_data） | `readonly`（1） | project_id | `Depends(get_current_user)` | ✅ 认证有；项目权限**未强制** |
| HTML 编辑（save / submit） | `edit`（3） | wp_id | `require_project_access("edit")` 在部分端点 | ⚠️ 部分覆盖 |
| Excel 导出（d4/export-template / export-data） | `readonly`（1） | wp_id | `Depends(get_current_user)`（line 422, 526） | ✅ 认证有 |
| Excel 导入（d4/import-data） | `edit`（3） | wp_id | `Depends(get_current_user)`（line 1054） | ⚠️ 认证有，**缺编辑权限强制** |
| 公式定义修改（wp_formula CRUD） | `edit`（3） | wp_id | 未查到 `require_role` / `require_project_access` | ❌ **UNVERIFIABLE** |
| TB/A13 发布 | `review`（2）或 `edit`（3） | project_id | 由独立发布端点处理 | ⚠️ **UNVERIFIABLE**（需追踪 TB 发布端点） |

#### B.1.4 底稿状态机角色守卫（grep 实证）
`app/services/state_machines/workpaper_sm.py` — `WORKPAPER_SM`：

| 转移 | from | action | to | role_required |
|------|------|--------|-----|--------------|
| 提交复核 | draft | submit | pending_review | {editor, manager, admin} |
| 开始复核 | pending_review | start_review | under_review | {manager, qc, partner} |
| 通过 | under_review | approve | review_passed | {manager, partner} |
| 退回 | under_review | reject | rejected | {manager, partner} |
| 重新提交 | rejected | resubmit | pending_review | {editor, manager} |
| 归档 | review_passed | archive | archived | {partner, admin} |

> ⚠️ **注意**：`workpaper_sm.py` 中的 `role_required` 使用 `{editor, manager, admin}` 等字面量，而 `UserRole` 枚举值为 `{auditor, manager, admin}` 等。**`editor` 不在 `UserRole` 中**——状态机角色名与数据库角色枚举存在漂移，需后续核对。

### B.2 CAS 版本校验规则

#### B.2.1 冻结规则
- 读写**必须**携带 `content_revision`（即 `expected_revision`），CAS 不匹配即拒绝
- 过期 CAS 必须**拒绝并记录审计日志**（不静默覆盖）
- CAS 推进使用 `UPDATE ... WHERE content_revision = :expected RETURNING content_revision`（乐观锁）

#### B.2.2 现状（grep 实证）

| 组件 | CAS 实现 | 位置 |
|------|---------|------|
| `bump_content_revision()` | `UPDATE working_paper SET content_revision = content_revision + 1 WHERE id=:wp AND content_revision=:expected RETURNING content_revision` | `workpaper_sync/repository.py:267` |
| `RevisionConflictError` | CAS 失败时抛出，含 `wp_id` 和 `expected_revision` | `repository.py:279` |
| `ContentCommitPlan.expected_revision` | commit plan 的冻结字段，负值拒绝 | `content_mutation.py:635` |
| `RevisionTargetError` | CAS 推进后 revision ≠ plan.target_revision 时抛出 | `content_mutation.py` |
| `RevisionLockedRepository` | 纯表示路径禁碰 `bump_content_revision` / `set_current_content_version` / `create_content_version` | `content_mutation.py` |

#### B.2.3 D4 端点 CAS 现状
- D4 导入端点 `/d4/import-data` **未传入** `expected_revision` / `If-Match` header
- D4 导入端点**未调用** `ContentMutationService.commit()`，直接写 `parsed_data`
- **缺口**：D4 所有写入端点必须接入 CAS（详见 §E）

---

## C. 幂等迁移（Requirement 7.1 后半）

### C.1 冻结规则

#### C.1.1 迁移幂等要求
- 所有 D4 相关 DB 迁移必须**幂等**（`IF NOT EXISTS` / `ON CONFLICT DO NOTHING` / `information_schema` 检测）
- 迁移必须**可回滚**（R*.sql 对应文件）
- D4 迁移**不依赖**平台全局未完成项目（不得用平台未绿作为阻塞理由）
- MigrationRunner 按 version 数字去重，同号检测（重复 version 抛 `RuntimeError`，2026-06-01 V040 修复后新增）

#### C.1.2 幂等模式（grep 实证，V151 为最新参考范式）
```sql
-- 表创建
CREATE TABLE IF NOT EXISTS working_paper_content_version (...);

-- 列添加
ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS content_revision BIGINT NOT NULL DEFAULT 0;

-- 唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS uq_wp_formula_wp_sheet_cell ON wp_formula (wp_id, sheet_name, target_cell);

-- 约束添加（先检测）
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_wp_content_revision_non_negative') THEN
    ALTER TABLE working_paper ADD CONSTRAINT ck_wp_content_revision_non_negative
      CHECK (content_revision >= 0);
  END IF;
END $$;

-- 簿记行校正（幂等 UPDATE）
UPDATE schema_version SET ... WHERE version='113' AND filename='V113__wp_visibility_delegation_history_audit_epoch.sql';
```

### C.2 现状：D4 相关迁移文件（grep 实证）

#### C.2.1 D4 专属迁移（grep `d4|D4` in `backend/migrations/*.sql`）
| 文件 | 内容 | 幂等 | 回滚 |
|------|------|------|------|
| **无 D4 专属迁移文件** | grep `d4|D4` 在 `V*.sql` 中仅命中 V052 注释中的 `d4` 字符（非 D4 语义） | — | — |

#### C.2.2 D4 功能依赖的底层迁移
| 文件 | 内容 | D4 依赖关系 | 幂等 | 回滚 |
|------|------|-----------|------|------|
| `V052__wp_formula.sql` | `wp_formula` 表（公式绑定） | D4 公式管理依赖此表 | ✅ `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` | ✅ `R052__wp_formula_rollback.sql` |
| `V151__workpaper_sync_content_application_bundle_scope.sql` | CAS/ContentMutation 核心表（`content_revision`、`working_paper_content_version`、`working_paper_artifact` 等 20+ 表） | D4 双模式同步依赖此迁移的所有表 | ✅ 全部 `IF NOT EXISTS` | ✅ `R151__rollback_*.sql` |
| `V100__formula_management_library.sql` | 公式管理库（`draft_marker`、`draft_refresh_audit` 等） | D4 公式刷新依赖 | ✅ `IF NOT EXISTS` + `information_schema` 检测 | 未查到 R100 |
| `V104__formula_runtime_outbox.sql` | 公式运行时 outbox | D4 公式运行时依赖 | 未查证 | 未查证 |
| `V134__repair_ai_content_governance_missed_by_v113_conflict.sql` | 修复 AI 内容治理表（checksum `d4` 字符误命中） | 与 D4 循环无直接关系 | ✅ | ✅（幂等 UPDATE） |

#### C.2.3 缺口
- **无 D4 专属迁移文件**：D4 当前未新增任何 `V*.sql`，全部依赖底层 V052/V151/V100/V104
- D4 双模式若需新增表（如 `wp_formula_definition`、`wp_content_identity`），必须新建 `V0XX__d4_*.sql` 并配套 `R0XX__rollback_*.sql`
- **当前状态**：✅ 底层迁移已幂等，无需为 D4 新建迁移（D4 双模式在现有表结构上运行）
- ⚠️ `V100__formula_management_library.sql` 和 `V104__formula_runtime_outbox.sql` 的回滚文件未查证是否存在

---

## D. 不适用（N/A）声明

本契约**不包含**：
- C1 sync 已冻结内容（字段级自动合并、冲突轨迹、durable ack）—— 见 `c1_sync_contract.md`
- C2 formula 已冻结内容（F-SHELL v2、preset/custom、CAS 公式定义 key）—— 见 `c2_formula_contract.md`
- C3 linkage 已冻结内容（真实 DAG、单 writer、TB/A13 发布边界）—— 见 `c3_linkage_contract.md`（待冻结）
- C0 已冻结内容（owner 矩阵、模板 identity）—— 见 `c0_owner_matrix.md` / `c0_gap_register.md`
- 平台全局 77 项任务（不作为 D4 门控，Requirement 7.1 明确：不得把平台全局未完成作为 D4 全局阻塞）
- 合并模块（consolidation，非 D4 循环范围）
- AI 内容治理（evidence_governance，独立模块）

---

## E. 实现缺口（UNVERIFIABLE / TODO）

### E.1 D4 端点未接入 ContentMutationService（Requirement 6.1）
| 缺口 | 严重度 | 说明 |
|------|--------|------|
| `/d4/import-data` 未调用 `ContentMutationService.commit()` | 🔴 高 | 直接写 `parsed_data`，绕过单次 commit 原子性保障；结构变更不走 mutation plan |
| `/d4/import-data` 无 CAS 版本校验 | 🔴 高 | 无 `expected_revision`，并发导入可能静默覆盖 |
| D4 导入无 `ContentCommitPlan` | 🔴 高 | 无 `expected_revision`、无 `adapter_build_digest`、无 `structure_anchors` |

### E.2 D4 端点权限不完整（Requirement 7.1）
| 缺口 | 严重度 | 说明 |
|------|--------|------|
| `/d4/import-data` 无 `require_project_access("edit")` | 🟡 中 | 任何认证用户（含 `readonly`）可执行导入写入 |
| `/d4/export-template` / `/d4/export-data` 无项目权限检查 | 🟢 低 | 导出是只读操作，`get_current_user` 已足够 |
| 公式定义修改端点（`wp_formula` CRUD）无角色校验 | 🟡 中 | 未查到 `require_role` / `require_project_access` 在此类端点 |
| `WORKPAPER_SM` 角色名与 `UserRole` 枚举漂移 | 🟡 中 | `workpaper_sm.py` 使用 `editor` 字面量，`UserRole` 无此成员；`allowed_actions_service.py` 的 `user_role` 参数传入值需核对 |

### E.3 四表取数复用（Requirement 5.2）
| 缺口 | 严重度 | 说明 |
|------|--------|------|
| `_d4_import_export.py` 未导入 `four_table/` | 🟢 低 | 导入端点不触发四表取数，仅写入用户提供的数据 |
| D4 审定表（D4-1）回填 TB 链路未验证 | ⚠️ UNVERIFIABLE | 需 D4-1 审定表回填端点实现后才能验证是否复用 `four_table/` |

### E.4 迁移缺口
| 缺口 | 严重度 | 说明 |
|------|--------|------|
| `V100__formula_management_library.sql` 回滚文件 | 🟡 中 | 未查证是否存在 `R100__rollback_*.sql` |
| `V104__formula_runtime_outbox.sql` 回滚文件 | 🟡 中 | 未查证是否存在 `R104__rollback_*.sql` |
| D4 双模式专用迁移（如需新增表） | 🟢 低 | 当前无 D4 专属迁移；若后续需新增，必须配套 R*.sql |

---

## F. 契约冻结声明

### F.1 已冻结（FROZEN）
- [x] 导入 identity 五元组载体定义（`stable_sheet_key` / `table_key` / A1 range / `RowIdentityKind` / `formula_mask`）
- [x] 禁止形态清单（CS-3 `col_[a-z]+` / CS-10 position guess / CS-12 行号 anchor / CS-20 静默降级）
- [x] CAS 乐观锁语义（`bump_content_revision` UPDATE + `RevisionConflictError`）
- [x] 角色枚举（`UserRole` 7 值）与权限层级（`PERMISSION_HIERARCHY` 3 级）
- [x] 迁移幂等范式（`IF NOT EXISTS` / `information_schema` / 幂等 UPDATE）
- [x] D4 专属迁移现状（无；依赖底层 V052/V151/V100/V104）

### F.2 UNVERIFIABLE（待实现后验证）
- [ ] D4 导入接入 ContentMutationService（Requirement 6.1）
- [ ] D4 导入 CAS 版本校验（Requirement 7.1）
- [ ] D4 导入编辑权限强制（Requirement 7.1）
- [ ] D4 审定表回填复用 four_table（Requirement 5.2）
- [ ] `WORKPAPER_SM` 角色名与 `UserRole` 对齐
- [ ] `V100` / `V104` 回滚文件存在性

### F.3 验证触发条件
上述 UNVERIFIABLE 项在以下条件下变为可验证：
1. D4 导入端点重构接入 `ContentMutationService` + CAS → E.1 全部可验证
2. D4-1 审定表回填端点实现 → E.3 可验证
3. `wp_formula` CRUD 端点接入 `require_project_access("edit")` → E.2 部分可验证
4. grep 确认 `R100` / `R104` 文件存在 → E.4 可验证
