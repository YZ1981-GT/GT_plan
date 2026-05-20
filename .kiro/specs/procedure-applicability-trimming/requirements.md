# Requirements Document — 程序适用性裁剪 UI

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v0.1 | 2026-05-20 | 初始起草 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| useProcedureStatus composable | 前端 | ✅ 已有 `not_applicable` 状态枚举 |
| WorkpaperAuditNav 组件 | 前端 | ✅ 已有审计导航面板，可扩展 tab |
| wp_procedure_status.py 路由 | 后端 | ✅ 已有 PATCH endpoint 支持 `not_applicable` |
| WpAuditTrailService | 后端 | ✅ 已有 `ACTION_PROCEDURE_TRIMMED` 审计动作 |
| require_role 依赖工厂 | 后端 | ✅ 已有角色校验机制 |
| audit_logger_enhanced | 后端 | ✅ 已有审计日志哈希链 |
| parsed_data.procedure_status | 数据 | ✅ 已有 JSON 结构，需扩展裁剪元数据 |

## Introduction

### 业务痛点

审计实务中，项目经理需要根据风险评估结论裁剪审计程序。典型场景：

1. **无相关业务**：客户无存货 → F 循环全部程序 N/A；客户无海外业务 → 外币程序 N/A
2. **风险评估为低**：某认定风险评估为低 → 对应实质性程序可简化或跳过
3. **控制测试有效**：控制测试结论为有效 → 可减少实质性程序范围
4. **其他业务判断**：如客户无关联方交易、无或有事项等

### 技术根因

- 当前 `useProcedureStatus` 已定义 `not_applicable` 状态，但无 UI 入口让项目经理主动设置
- 现有 `WorkpaperAuditNav` 仅展示程序执行进度，无裁剪操作入口
- `WpAuditTrailService` 已预留 `ACTION_PROCEDURE_TRIMMED` 审计动作但未被调用
- 缺少批量裁剪能力（按循环/按认定/按风险等级）
- 缺少裁剪理由结构化记录和合伙人/质控审阅入口

### 范围边界

**必做（In Scope）：**
- WorkpaperAuditNav 新增"程序适用性"tab
- 单行/批量标记程序为 N/A + 结构化理由
- 标记后 sheet 灰显 + 程序状态自动同步
- 裁剪操作可撤销（恢复为 pending）
- 审计日志完整记录（谁/何时/标记了什么/理由）
- 合伙人/质控裁剪汇总查看面板
- RBAC：manager+ 可操作，assistant 只读

**排除（Out of Scope）：**
- 不改变现有 `procedure_status` 数据结构（在 `parsed_data` 内扩展 `trimming_metadata`）
- 不影响已有 11 个循环的 sheet 分组逻辑
- 不涉及 LLM 自动推荐裁剪（后续 spec）
- 不涉及跨项目裁剪模板复用

## Glossary

- **Trimming_Panel**：程序适用性裁剪面板，嵌入 WorkpaperAuditNav 的新 tab
- **Trimming_Engine**：后端裁剪逻辑服务，负责批量标记/撤销/审计日志
- **Trimming_Summary**：裁剪汇总视图，供合伙人/质控审阅
- **Procedure_Row**：程序行，对应 `parsed_data.procedure_status[sheetKey].{Rxx}`
- **Trimming_Reason**：裁剪理由，结构化枚举 + 自定义文本
- **Batch_Selector**：批量选择器，支持按循环/按认定/按风险等级筛选程序行

## Requirements

### Requirement 1: 程序适用性 Tab 入口

**User Story:** As a 项目经理, I want to 在 WorkpaperAuditNav 中看到"程序适用性"tab, so that 我可以快速进入裁剪操作界面。

#### Acceptance Criteria

1. WHEN 用户打开底稿编辑器且 WorkpaperAuditNav 可见, THE Trimming_Panel SHALL 作为独立 tab 显示在审计导航图内（tab 标题"程序适用性"）
2. THE Trimming_Panel SHALL 展示当前底稿所有程序行的适用性状态列表（行号 + 程序描述 + 当前状态 + N/A 标记）
3. WHILE 程序行状态为 `not_applicable`, THE Trimming_Panel SHALL 在该行显示灰色背景 + "N/A" 标签 + 裁剪理由摘要
4. THE Trimming_Panel SHALL 在顶部显示裁剪统计摘要（总程序数 / 已裁剪数 / 裁剪率百分比）

### Requirement 2: 单行裁剪标记

**User Story:** As a 项目经理, I want to 将单个程序行标记为"不适用", so that 该程序在执行进度中不再计入待完成。

#### Acceptance Criteria

1. WHEN 项目经理点击程序行的"标记 N/A"按钮, THE Trimming_Engine SHALL 弹出理由选择对话框
2. THE Trimming_Engine SHALL 提供以下预设理由选项：无相关业务 / 风险评估为低 / 控制测试有效 / 其他
3. WHEN 用户选择"其他"理由, THE Trimming_Engine SHALL 要求输入自定义文本（最少 5 字符）
4. WHEN 用户确认裁剪, THE Trimming_Engine SHALL 将该程序行状态更新为 `not_applicable` 并记录裁剪元数据（理由 + 操作人 + 时间戳）
5. IF 用户未选择理由即点击确认, THEN THE Trimming_Engine SHALL 阻止提交并提示"请选择裁剪理由"

### Requirement 3: 批量裁剪标记

**User Story:** As a 项目经理, I want to 按循环/按认定/按风险等级批量标记程序为 N/A, so that 我可以高效完成大范围裁剪。

#### Acceptance Criteria

1. THE Batch_Selector SHALL 提供三种批量筛选维度：按循环（如 F 循环全部）/ 按认定（如"存在"认定相关）/ 按风险等级（如"低风险"程序）
2. WHEN 用户选择批量筛选条件, THE Batch_Selector SHALL 实时预览匹配的程序行列表及数量
3. WHEN 用户确认批量裁剪, THE Trimming_Engine SHALL 对所有匹配程序行执行与单行裁剪相同的理由记录和状态更新
4. THE Trimming_Engine SHALL 在批量操作完成后返回操作结果摘要（成功数 / 跳过数 / 失败数）
5. IF 批量选择包含已处于 `not_applicable` 状态的程序行, THEN THE Trimming_Engine SHALL 跳过这些行并在结果中标注"已跳过（已为 N/A）"

### Requirement 4: 裁剪撤销（恢复为 pending）

**User Story:** As a 项目经理, I want to 撤销已裁剪的程序标记, so that 当业务情况变化时我可以恢复程序为待执行状态。

#### Acceptance Criteria

1. WHEN 项目经理点击已裁剪程序行的"恢复"按钮, THE Trimming_Engine SHALL 将该程序行状态从 `not_applicable` 恢复为 `pending`
2. THE Trimming_Engine SHALL 保留原裁剪记录在审计日志中（不删除历史记录）
3. THE Trimming_Engine SHALL 在恢复操作时写入新的审计日志条目（action="workpaper.procedure_trim_reverted"）
4. WHEN 批量恢复时, THE Trimming_Engine SHALL 支持与批量裁剪相同的筛选维度

### Requirement 5: Sheet 灰显联动

**User Story:** As a 审计助理, I want to 在 sheet 导航中看到被裁剪程序对应的 sheet 灰显, so that 我知道哪些底稿不需要执行。

#### Acceptance Criteria

1. WHILE 程序行状态为 `not_applicable`, THE Trimming_Panel SHALL 通知 sheet 导航组件将对应 sheet 标记为灰显状态
2. THE Trimming_Panel SHALL 通过 `eventBus.emit('procedure-status:changed')` 触发 sheet 导航刷新
3. WHEN 所有关联某 sheet 的程序行均为 `not_applicable`, THE Trimming_Panel SHALL 将该 sheet 整体标记为"不适用"灰显
4. WHEN 裁剪被撤销, THE Trimming_Panel SHALL 立即移除对应 sheet 的灰显状态

### Requirement 6: 审计日志追溯

**User Story:** As a 质控人员, I want to 查看完整的裁剪操作日志, so that 我可以追溯谁在什么时间裁剪了什么程序及理由。

#### Acceptance Criteria

1. WHEN 裁剪操作执行, THE Trimming_Engine SHALL 调用 `WpAuditTrailService.log_procedure_trim` 写入审计日志
2. THE Trimming_Engine SHALL 在审计日志 details 中记录：操作类型（trim/revert）/ 程序行列表 / 理由枚举 / 自定义文本 / 操作人 ID / 时间戳
3. THE Trimming_Summary SHALL 提供按时间倒序的裁剪操作历史列表
4. THE Trimming_Summary SHALL 支持按操作人 / 按理由类型 / 按时间范围筛选审计日志

### Requirement 7: 合伙人/质控裁剪汇总

**User Story:** As a 合伙人/质控, I want to 查看裁剪汇总面板, so that 我可以评估裁剪决策是否充分合理。

#### Acceptance Criteria

1. THE Trimming_Summary SHALL 展示裁剪汇总统计：按循环分组的裁剪数 / 按理由分组的裁剪数 / 裁剪率
2. THE Trimming_Summary SHALL 对裁剪率超过 50% 的循环标记黄色警告提示
3. THE Trimming_Summary SHALL 支持展开查看每个被裁剪程序的详细理由和操作人
4. WHEN 质控人员认为裁剪理由不充分, THE Trimming_Summary SHALL 提供"标记待复核"功能（写入复核意见）

### Requirement 8: RBAC 权限控制

**User Story:** As a 系统管理员, I want to 限制裁剪操作仅 manager+ 角色可执行, so that 审计助理不能擅自裁剪程序。

#### Acceptance Criteria

1. THE Trimming_Engine SHALL 使用 `require_role(["admin", "partner", "manager"])` 守卫裁剪和恢复端点
2. WHILE 当前用户角色为 assistant/auditor, THE Trimming_Panel SHALL 隐藏"标记 N/A"和"恢复"按钮（只读模式）
3. IF 非授权角色尝试调用裁剪 API, THEN THE Trimming_Engine SHALL 返回 HTTP 403 "权限不足"
4. THE Trimming_Summary SHALL 对所有角色可见（只读查看不受限制）

## Non-Functional Requirements

### 性能

- 批量裁剪 ≤ 50 行时响应时间 ≤ 500ms
- 裁剪汇总面板加载时间 ≤ 300ms（单底稿维度）

### 兼容性

- 不改变现有 `parsed_data.procedure_status` 结构（裁剪元数据存储在 `parsed_data.trimming_metadata`）
- 已有 11 个循环的 sheet 分组逻辑不受影响
- 已有 `useProcedureStatus` composable 的 `markStatus` 方法兼容裁剪操作

### 可观测性

- 裁剪操作写入 `audit_log_entries` 表（哈希链完整性）
- 后端日志记录每次裁剪/恢复操作的 project_id + wp_id + user_id + 程序行数

## Test Matrix

### 单元测试

| 文件 | 覆盖范围 |
|------|----------|
| `backend/tests/test_procedure_trimming.py` | 裁剪/恢复 API + RBAC + 审计日志 |
| `frontend/src/composables/__tests__/useProcedureTrimming.spec.ts` | 前端裁剪状态管理 + 批量操作 |
| `frontend/src/components/workpaper/__tests__/ProcedureTrimmingPanel.spec.ts` | 面板渲染 + 交互 |

### PBT (Property-Based Tests)

| ID | Property | 描述 |
|----|----------|------|
| PBT-P1 | trim_revert_roundtrip | 裁剪后恢复 = 原始 pending 状态（round-trip） |
| PBT-P2 | batch_trim_idempotent | 对已 N/A 行重复批量裁剪 = 无额外副作用（幂等） |
| PBT-P3 | trim_count_invariant | 裁剪前后 total = trimmed + active（数量守恒） |

### 集成测试

- 裁剪 → sheet 灰显联动 → eventBus 事件传播
- 裁剪 → 审计日志写入 → 汇总面板读取

### UAT

| # | 验收项 | P |
|---|--------|---|
| 1 | 项目经理可在 WorkpaperAuditNav 中看到"程序适用性"tab | P0 |
| 2 | 单行标记 N/A + 理由选择 + 确认后状态变更 | P0 |
| 3 | 批量按循环标记 N/A + 预览 + 确认 | P0 |
| 4 | 撤销裁剪恢复为 pending | P0 |
| 5 | 被裁剪程序对应 sheet 灰显 | P1 |
| 6 | 审计日志完整记录裁剪操作 | P0 |
| 7 | 合伙人/质控可查看裁剪汇总 | P1 |
| 8 | assistant 角色无法执行裁剪操作（403） | P0 |
| 9 | 批量裁剪跳过已 N/A 行 + 结果摘要 | P1 |
| 10 | 裁剪率 > 50% 黄色警告 | P2 |

**上线门槛：P0 全部 ✓ + P1 ≥ 80% ✓**

## Success Criteria

- 项目经理可在 2 步内完成单行裁剪（点击 N/A → 选理由 → 确认）
- 批量裁剪支持 ≤ 100 行一次操作
- 裁剪操作 100% 写入审计日志（零遗漏）
- 合伙人/质控可在裁剪汇总面板一屏内看到全循环裁剪概况

## Terminology

| 术语 | 定义 |
|------|------|
| N/A | Not Applicable，程序不适用 |
| 裁剪 (Trimming) | 将程序标记为不适用的操作 |
| 恢复 (Revert) | 将已裁剪程序恢复为待执行状态 |
| 裁剪率 | 已裁剪程序数 / 总程序数 × 100% |
| manager+ | 项目经理及以上角色（manager / partner / admin） |
