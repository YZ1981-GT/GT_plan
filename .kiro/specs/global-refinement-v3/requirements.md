# 全平台 V3 收官增强 — 需求文档

> 起草日期：2026-05-26
> 触发场景：基于 `docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md`（v3.8 版本，1949 行，7 轮迭代复盘）的资深合伙人收官建议
> 工作流类型：Requirements-First
> 状态：requirements 阶段（design / tasks 后续单独发起）
> 范围：4 Sprint × 55.5 工时 = 13 个需求主题（8 真 P0 + 4 隐藏痛点 + 全平台中文化）

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v0.1 | 2026-05-26 | 首次起草 13 个需求主题 + Correctness Properties + 已知缺口 | V3 文档 §21 资深合伙人收官复盘锁定范围 |

---

## Introduction

### 背景

致同审计作业平台经过 R7-R9 + Phase 1-8 + ledger-import-view-refactor + workpaper-html-renderer 等多个 spec 落地后，已具备 99 视图 / 381 组件 / 96 composables / 281 路由 / 62 模型 / 369 服务的规模。`docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md`（v3.0 → v3.8）经 7 轮迭代实测复盘，识别出 280+ 条改进建议、累计 190 天工时。

V3 §21 资深合伙人收官复盘明确指出：**"V3 是一份诚实的体检报告，不是一份必须全做的待办清单"**——280 条建议若全做会拖垮团队，真正"不做就上不了线"的硬伤只有 8 条真 P0；另有 4 条合伙人立场认为"V3 没充分覆盖但最痛"的隐藏痛点；外加 v3.7 沉淀的全平台中文化收尾任务。

本 spec 将这 13 个主题按价值密度组织成 4 个 Sprint × 55.5 工时（约 11 周单人 / 5.5 周 2 人并行），是平台投产前的最后一公里。

### 平台规模实测基线（V3 §16.1，2026-05-26）

| 维度 | 实测值 |
|------|--------|
| views / components / composables | 99 / 381 / 96 |
| stores / routers / models / services | 9 / 281 / 62 / 369 |
| `except Exception` | 1162 处 |
| `float()` in services | 420 处 |
| `console.log/.error/.warn` | 74 处 |
| `datetime.utcnow()` 残留 | 19 处 |
| GtAmountCell 接入（views/components） | 5/99 + 1/381 |
| GtPageHeader 接入 | 73/99 |
| statusEnum 硬编码残留 | 17 视图 |
| `year:changed` 订阅 | 仅 3 视图 |
| 表单无 `:rules` | 39 视图 |
| 删除无确认 | 23 处 |
| 路由参数变化 watch | 仅 1 视图（86 视图用 onMounted） |
| GtEmpty / GtStatusTag | 3 / 6 处 |
| 分页 / 虚拟滚动 / 响应式 | 7 / 0 / 7 视图 |
| el-skeleton | 10 视图 |
| AiContentConfirmDialog 接入 | 1 视图 import |
| 归档项目 isArchived 检查 | 0 视图 |
| autoSave 间隔 | 120 秒 |
| 英文 UI 残留（label/btn/title/placeholder） | 123 / 36 / 44 / 6 处 |
| 后端 HTTPException 英文 detail | 16 处 |
| el-table-column 英文表头 | 28 处 |
| PBC router | 仍 stub |

### Sprint 划分（V3 §21.5）

| Sprint | 主题 | 工时 | 包含需求 |
|--------|------|------|---------|
| Sprint 1（合规底线） | "上线必须做" | 18.5 天 | Req 1-7 |
| Sprint 2（高频体验） | "用户每天都遇到" | 15 天 | Req 8 + Req 13 |
| Sprint 3（信任与可解释） | "合伙人最痛" | 12 天 | Req 9-11 |
| Sprint 4（编辑器与性能） | "每天工作 8 小时的工具" | 10 天 | Req 12 |
| 合计 | | **55.5 天** | 13 个需求 |

### 五角色视角

每个需求标注影响哪些角色（与 V3 §4 对齐）：

- **审计助理**（Audit_Assistant）：每天 8 小时高频使用底稿编辑器、序时账、抽凭、调整分录
- **项目经理**（Project_Manager）：关注项目进度、人员分配、底稿完成率、复核状态、工时预算
- **质控人员**（Quality_Control）：关注规则执行率、抽查覆盖率、问题整改闭环、年度质控报告
- **项目合伙人**（Partner）：关注签字风险、项目全局风险、报告质量、归档完整性
- **独立复核合伙人**（EQCR）：关注独立性、重大判断复核、备忘录、与项目组的信息隔离

---

## Glossary

- **System**：致同审计作业平台（前端 Vue 3 + 后端 FastAPI + PG 16 + Redis 6379）
- **Project**：审计项目实例（`projects` 表，含 status / archived_at 字段）
- **Workpaper**：审计底稿，编码遵循致同 2025 修订版 v2025-R5（A/B/C/D-N/S 循环）
- **Adjustment / RJE**：调整分录（Adjustment Journal Entry）/ 重分类分录
- **Misstatement**：错报
- **Reviewer / Sign-off**：复核人 / 签字
- **Trial_Balance**：试算平衡表（含 4 张表 tb_balance/tb_aux_balance/tb_ledger/tb_aux_ledger）
- **Disclosure**：附注披露（国企 14 章 / 上市 17 章）
- **GtAmountCell**：金额单元格统一组件（千分位 + 万元/元切换 + 负数色 + Arial Narrow 字体）
- **GtPageHeader / GtEmpty / GtStatusTag**：页头 / 空状态 / 状态标签的统一组件
- **GtAmountCell**：金额单元格统一组件
- **AiContentConfirmDialog**：AI 生成内容人工审核确认弹窗（已落地组件）
- **statusEnum**：前端状态常量集中表 `frontend/src/constants/statusEnum.ts`
- **manual_override**：用户手动覆盖标记（防止上游联动覆盖手动值）
- **Audit_Context**：审计上下文三元组 (project_id, year, applicable_standard)
- **CAS 1131**：注协 / 中注协《审计工作底稿》准则关于归档后修改限制条款
- **EARS**：Easy Approach to Requirements Syntax（本文档采用的需求格式规范）
- **PBT**：Property-Based Testing（基于属性的测试，用 hypothesis / fast-check）
- **PBC**：Provided By Client（客户提供资料清单，审计起点核心动作）
- **EQCR**：Engagement Quality Control Reviewer（独立复核合伙人）
- **DSL**：Domain-Specific Language（领域专用语言，本平台用于公式 =TB/=ROW/=PRIOR）
- **CAS 1131 合规**：归档后任何变更必须留痕、不允许直接修改原始底稿
- **PCAOB**：Public Company Accounting Oversight Board（美国上市公司会计监督委员会）

---

## 需求约定

- 所有需求遵循 EARS 六模式之一（Ubiquitous / Event-driven / State-driven / Unwanted event / Optional feature / Complex）
- 编号规则：Req {N} → AC {N}.{M}
- 角色影响标注：[助理/经理/质控/合伙人/EQCR] 五选 N
- 实测数据基线：来源于 V3 §16.1（2026-05-26 grep 实测）
- 性质类型注记：可作为属性测试的不变量统一收纳到末尾「Correctness Properties」章节
- 迁移文件位置：`backend/migrations/V0XX.sql`（实施时取 max+1，禁止本 spec 硬编码编号）

---

## Sprint 1（合规底线，18.5 天）— Req 1-7

### Requirement 1：归档项目只读保护（CAS 1131 合规）

**User Story**: As a 项目合伙人，我希望已归档的审计项目自动进入只读状态，避免任何后续编辑动作产生不可解释的"归档后变更"，以满足 CAS 1131 准则与监管抽查要求。

**实测基线**（V3 §19.1）：当前 0 视图检查 `isArchived`，所有 mutation 端点不区分项目状态，已归档项目仍可被编辑。

**角色影响**：[合伙人 / 质控 / EQCR]

**优先级**：🔴 P0（V3 §21.2 #1，最高优先级，监管检查必出问题）

**工时**：2 天

#### Acceptance Criteria

1. WHEN 一个 mutation API 端点（POST/PUT/DELETE/PATCH）接收到 project_id 参数，THE System SHALL 调用 `_check_project_not_archived(project_id)` 守卫函数。
2. IF 目标 Project 的 status 为 archived，THEN THE System SHALL 返回 HTTP 423 Locked，detail 包含 `error_code = "PROJECT_ARCHIVED"` 与中文 message。
3. WHEN 前端 useProjectStore 加载到 status=archived 的 Project，THE System SHALL 在所有项目内编辑器视图顶部显示 banner（"📁 项目已归档（只读）"+ 紫色品牌色调 + 解除归档按钮，仅 admin/合伙人可见）。
4. WHILE 当前 Project 的 isArchived 为 true，THE System SHALL 禁用所有"保存 / 提交 / 删除 / 签字"按钮（disabled + tooltip 说明原因）。
5. WHERE 用户角色为质控独立审阅或法定事后修改流程，THE System SHALL 提供专用例外通道（独立端点 + 强制留痕字段 reason / approver_id），不走 mutation 守卫。
6. THE System SHALL 在审计日志（audit_log 表）记录所有归档后例外通道触发事件，含 user_id / project_id / endpoint / timestamp / reason。
7. THE System SHALL 在归档解除（unarchive）操作前要求二次确认 + 必填解除原因，并写入审计日志。

---

### Requirement 2：金额计算 Decimal 化（精度合规）

**User Story**: As a 项目合伙人，我希望平台所有金额计算路径使用 Decimal 类型而非 float，以避免浮点累加误差导致报表数字偏差，规避法律责任风险。

**实测基线**（V3 §12.1 / §16.1）：services 层 420 处 `float()` 调用（含金额与非金额场景），note_validation_engine.py / note_formula_generator.py / prefill_engine.py 均存在 `abs(expected - closing) > 0.01` 浮点容差判断。10 万行序时账每行 0.01 误差累加可达数千元级。

**角色影响**：[合伙人 / 质控 / 助理]（合规底线，全角色受益）

**优先级**：🔴 P0（V3 §21.2 #2，浮点精度责任）

**工时**：5 天

#### Acceptance Criteria

1. THE System SHALL 在所有金额相关计算路径使用 `decimal.Decimal` 类型，禁用 `float(...)` 处理金额字段（DB 已是 NUMERIC，service 层契合）。
2. WHEN 前端展示金额，THE System SHALL 使用 `decimal.js` 库进行客户端计算，禁止使用 JavaScript 原生 Number 进行金额累加。
3. THE System SHALL 提供 `Quantize_Helper`（按业务场景 0.01/0.001 分位四舍五入），所有金额输出经过该 helper 统一处理。
4. WHEN 校验等值，THE System SHALL 使用按金额规模动态调整的容差（已在 ledger validator 实现，本需求扩展到全平台）。
5. IF service 层代码中出现 `float(<amount_field>)` 模式，THEN THE System SHALL 在 CI 阶段触发 ruff 自定义规则 fail，命中数 baseline 由实施时跑一次确定后只减不增。
6. THE System SHALL 提供 `to_decimal(value, allow_none=False)` 公共转换器，统一处理 str/int/float → Decimal 的边界 case（NaN / Infinity / 科学计数法）。
7. WHEN 金额字段从前端传入后端，THE Backend SHALL 使用 Pydantic Decimal 字段类型校验，拒绝非法 numeric 输入并返回中文错误消息。
8. THE System SHALL 在调整分录、错报、试算表、报表行、附注金额单元格 5 类核心场景下提供单元测试覆盖小数累加（10 万行 0.01 累加 = 1000 元的精确等值断言）。

---

### Requirement 3：表单校验全覆盖（数据质量底线）

**User Story**: As a 审计助理 / 项目经理，我希望所有提交类表单都有完整字段校验，避免空值或非法数据写入数据库污染下游业务流程。

**实测基线**（V3 §18.1）：39 个视图包含 `el-form` 但未绑定 `:rules`。典型场景包括调整分录金额未填、项目年度未填、签字客户名未输入。

**角色影响**：[全角色，数据质量风险]

**优先级**：🔴 P0（V3 §21.2 #3）

**工时**：3 天

#### Acceptance Criteria

1. WHEN 一个 el-form 包含"提交 / 保存 / 创建 / 签字"按钮，THE System SHALL 绑定 `:rules` 校验规则，且提交前调用 `formRef.value?.validate()` 拦截。
2. THE System SHALL 在 `frontend/src/utils/formRules.ts` 提供通用规则集合：required / amount（Decimal 范围）/ accountCode（科目编码格式）/ year（年度范围）/ projectName / dateRange / email / phone。
3. IF 表单字段失败校验，THEN THE System SHALL 在字段下方显示中文错误提示（红色 + 图标），且提交按钮保持启用以允许用户修复后重试。
4. WHEN 同一字段同时触发多条规则失败，THE System SHALL 仅显示第一条失败规则的错误提示（避免提示叠加干扰）。
5. THE System SHALL 在 CI 阶段提供 grep 卡点：`<el-form` 未配 `:rules` 的视图数 ≤ baseline（实施时跑一次定基线后逐步降到 0）。
6. WHERE 表单为查询/筛选场景（非提交），THE System SHALL 不强制要求 `:rules`，但需在 spec 中显式注明该 form 用途。
7. THE System SHALL 在调整分录、错报登记、项目创建、用户管理、底稿提交 5 类核心表单提供 Playwright 端到端校验通过断言。

---

### Requirement 4：删除操作二次确认（误操作防御）

**User Story**: As a 审计助理，我希望所有删除操作必须经过明确的二次确认弹窗，避免在审计旺季疲劳时误触按钮丢失底稿或调整分录。

**实测基线**（V3 §18.2）：33 处使用了 `confirmDelete/ElMessageBox.confirm`，仍有 23 处直接调用 `api.delete` 无任何确认。

**角色影响**：[全角色，数据安全]

**优先级**：🔴 P0（V3 §21.2 #4）

**工时**：1 天

#### Acceptance Criteria

1. WHEN 用户触发 mutation 类型为 DELETE 的操作，THE System SHALL 弹出 ElMessageBox 二次确认对话框，标题"确认删除"+ 内容包含被删除对象名称 / 编码 / 影响范围。
2. THE System SHALL 在 `frontend/src/utils/confirm.ts` 提供 `confirmDelete(name, options?)` 与 `confirmDangerous(action, options?)` 公共方法，所有删除调用方必须复用。
3. IF 用户点击"取消"或按 ESC，THEN THE System SHALL 立即终止删除流程，不发送任何 API 请求。
4. WHILE 删除请求处于 in-flight 状态，THE System SHALL 禁用确认按钮并显示 loading 图标，防止重复点击。
5. WHERE 删除对象为软删除可回收类型（项目 / 底稿 / 附件），THE System SHALL 在确认弹窗内提示"删除后可在回收站恢复"，并同步用户操作到 audit_log。
6. WHERE 删除对象为硬删除不可恢复类型（已归档项目永久清理 / 临时缓存），THE System SHALL 显示红色警告 banner + 要求用户输入对象名称二次校验后才放行。
7. THE System SHALL 在 CI 阶段提供 ESLint / grep 卡点：`api.delete(` 调用前 3 行内无 `confirm` 调用 → warning，命中数 baseline 0。

---

### Requirement 5：年度切换 + 路由参数响应联动（合并实施）

**User Story**: As a 项目合伙人 / 项目经理，我希望切换顶栏年度或在不同项目间快速跳转后，所有依赖 (project_id, year, applicable_standard) 的视图自动重新加载数据，避免手动 F5 刷新或看到上一个项目的数据残留。

**实测基线**（V3 §17.2 + §18.3 + §5.4）：`year:changed` 事件仅 3 视图订阅；86 视图用 onMounted 一次性加载，仅 1 视图 watch route。

**角色影响**：[全角色，合伙人复核时最痛]

**优先级**：🔴 P0（V3 §21.2 #5 + #7 合并）

**工时**：1.5 天

#### Acceptance Criteria

1. THE System SHALL 提供 `useAuditContext()` composable，统一暴露响应式 (project_id, year, applicable_standard) 三元组及 derived 状态（isArchived / canEdit）。
2. WHEN useAuditContext 内部检测到 project_id 或 year 变化，THE System SHALL 自动 emit `audit-context:changed` 事件并触发订阅视图的 refetch hook。
3. WHEN 用户在顶栏触发 `projectStore.changeYear(newYear)`，THE System SHALL 同步更新 URL query 参数（`?year=newYear`）并 emit `year:changed` 事件。
4. THE System SHALL 强制所有依赖 year 的视图通过 `useAuditContext()` 获取 year，禁止视图内直接读取 `route.query.year` 作为唯一数据源。
5. WHEN 用户从 `/projects/A/...` 路由跳转到 `/projects/B/...`，THE System SHALL 在目标视图自动 watch `route.params.projectId` 并触发数据重新加载。
6. IF 视图 onMounted 加载数据但未 watch projectId/year 变化，THEN THE System SHALL 在 CI 阶段触发 ESLint 自定义规则 warning，命中数 baseline 由实施时跑一次确定。
7. THE System SHALL 在年度切换后 1 秒内完成所有可见视图的 refetch（不阻塞用户其他操作，loading 状态用 v-loading 显示）。
8. WHERE 视图为静态页面（如帮助文档 / 关于页），THE System SHALL 允许标记 `audit-context-irrelevant` 跳过此联动机制。
9. THE System SHALL 在 Adjustments / Misstatements / ReportView / DisclosureEditor / WorkpaperList / TrialBalance / LedgerPenetration 7 个核心视图提供 Playwright 端到端验证（切换年度后数据已变化）。

---

### Requirement 6：AI 内容溯源闭环（注协 / PCAOB 合规）

**User Story**: As a 项目合伙人 / 质控，我希望平台所有 AI 生成的内容都带有水印、确认轨迹、人工审核记录，且任意时刻能 5 秒内回溯"哪段是 AI 写的、谁审核的、几点几分"，以满足注协 / PCAOB 对审计师专业判断负责的合规要求。

**实测基线**（V3 §12.2 / §16.1）：`ai_contribution_watermark` 仅用于归档报告页脚 + QC 年度报告；底稿 / 调整分录 / 错报 / 附注的 AI 生成内容当前无水印；后端 `wrap_ai_output` 已就位、`AiContentConfirmDialog` 组件已建，但前端仅 1 视图 import。

**角色影响**：[合伙人 / 质控 / 助理]

**优先级**：🔴 P0（V3 §21.2 #6）

**工时**：3 天

#### Acceptance Criteria

1. WHEN 后端 service 调用 LLM 生成业务内容（底稿 / 调整分录摘要 / 错报描述 / 附注段落 / 风险评估结论），THE System SHALL 强制经过 `wrap_ai_output(content, prompt, model, confidence, ...)` 包装，返回结构含 `id / generated_at / model / prompt_hash / confirm_action / revised_content`。
2. THE System SHALL 在 DB 新增 `ai_content_log` 表（迁移 V0XX 实施时取 max+1），记录每段 AI 内容的 generation / confirmation / revision / rejection 全轨迹（含 user_id / project_id / wp_id / timestamp / before / after）。
3. WHEN 前端展示包含 AI 内容的字段，THE System SHALL 在内容旁渲染 🤖 标签 + "确认 / 修订 / 拒绝"按钮（复用 AiContentConfirmDialog 组件）。
4. WHILE 一段 AI 内容处于 `confirm_action = pending` 状态，THE System SHALL 标记其为"待确认"并在底稿状态摘要中累计计数。
5. IF 项目内存在未确认的 AI 内容且当前用户尝试 sign_off（签字归档），THEN THE System SHALL 触发 `AIContentMustBeConfirmedRule` 守门规则，返回 422 + 列出未确认条目清单。
6. THE System SHALL 在归档生成报告时自动汇总该项目所有 AI 内容到独立章节"05 AI 贡献明细"（含每段内容的生成时间 / 模型 / 确认人 / 最终是否采纳）。
7. THE System SHALL 在 WorkpaperEditor / Adjustments / Misstatements / DisclosureEditor / ReviewWorkbench 5 个视图全量接入 AiContentConfirmDialog（实测当前仅 1 视图，目标 ≥ 10 视图）。
8. WHERE 用户角色为审计助理，THE System SHALL 仅允许助理执行 confirm / revise，禁止 reject（reject 需经理及以上权限）。
9. THE System SHALL 在审计日志查询页面提供按 "AI 内容" 维度的过滤入口，支持按时间 / 用户 / 模型 / 项目筛选。

---

### Requirement 7：跨模块冲突调解（manual_override 保护）

**User Story**: As a 审计助理 / 项目经理，我希望当我在某个模块手动覆盖了一个值（manual_override），后续上游变更触发自动联动时，系统弹出明确的"调解面板"让我选择保留手动值 / 采用新值 / 合并，避免我的手动工作被无声覆盖。

**实测基线**（V3 §19.10）：22 个 lock service + 21 处乐观锁检查（X-File-Opened-At）已就位；但 `wp_disclosure_sync` / `cross_ref_service` 触发联动时直接覆盖 manual_override 值，无显式调解 UI。

**角色影响**：[助理 / 经理 / 质控]

**优先级**：🔴 P0（V3 §21.2 #8）

**工时**：3 天

#### Acceptance Criteria

1. WHEN 上游数据变更触发跨模块联动（如 D2 应收账款底稿改值 → 附注"五、3"），THE System SHALL 在写入下游前检测目标字段是否带有 `manual_override = true` 标记。
2. IF 目标字段已 manual_override，THEN THE System SHALL 暂停联动写入，将冲突事件入队 `cross_module_conflicts` 表，并通过 SSE / 事件总线通知受影响用户。
3. WHEN 用户打开包含未调解冲突的视图，THE System SHALL 顶部显示蓝色 banner "⚠️ N 处数据存在冲突待调解" + "查看详情"按钮。
4. WHEN 用户点击"查看详情"，THE System SHALL 弹出调解面板，显示：上游变更（新值 + 来源 + 时间）/ 当前手动值（旧值 + 修改人 + 时间）/ 三选一操作（① 保留手动值 ② 采用新值 ③ 合并自定义编辑）。
5. WHEN 用户选择调解结果，THE System SHALL 写入决策到 `cross_module_conflicts.resolution` 字段并记录到 audit_log，同步更新目标字段值。
6. THE System SHALL 在 `wp_disclosure_sync` / `cross_ref_service` 增加 `_check_manual_override_before_propagate` hook，作为联动前置守卫。
7. WHERE 联动来源是系统自动重算（如汇率刷新 / 公式重计算），THE System SHALL 跳过冲突调解直接写入但记录 audit_log（系统行为不需用户介入）。
8. THE System SHALL 在质控规则集合（QcRuleList）中提供"未调解冲突数 ≤ 阈值"规则，签字前阻断未调解冲突堆积。


---

## Sprint 2（高频体验，15 天）— Req 8 + Req 13

### Requirement 8：高频体验一致性套件

**User Story**: As a 全平台用户，我希望平台所有金额展示、加载状态、空状态、状态标签、穿透导航、状态枚举使用一致的视觉与交互模式，建立稳定的"系统正在工作 / 数据可信 / 状态清晰"心智模型。

**实测基线**（V3 §17.1 / §17.3 / §17.7 / §18.4 / §18.5 / §1.2）：
- GtAmountCell 仅 5/99 视图 + 1/381 组件接入，其余表格金额列裸显示
- 加载状态 5 种模式并存（v-loading 60+ 视图、el-skeleton 10、GtLoadingOverlay 3、LoadingState 1、GtTableLoading 1）
- usePenetrate 提供 10 种穿透方法但无统一面包屑回溯
- GtEmpty 仅 3 处使用、GtStatusTag 仅 6 处使用
- statusEnum 硬编码字符串残留 17 视图
- handleApiError 已覆盖 53/99 视图，仍有 58 视图 catch 块用 `ElMessage.error` 裸调

**角色影响**：[全角色]

**优先级**：🟡 P1（高频度，每天都遇到）

**工时**：合计 9 天（GtAmountCell 全量 2 + 加载统一 2 + 穿透面包屑 1.5 + GtEmpty/GtStatusTag/分页 4 - 部分重叠）

#### Acceptance Criteria

##### 8.1 GtAmountCell 全量覆盖

1. WHEN 一个 el-table-column 用于展示金额数值（科目余额 / 调整金额 / 报表行 / 错报金额 / 附注金额等），THE System SHALL 使用 GtAmountCell 渲染，禁止使用 `{{ row.amount }}` 裸表达式。
2. THE GtAmountCell SHALL 内部读取 `displayPrefs` store 的 amountUnit / decimalPlaces / negativeStyle / highlightThreshold 配置，自动应用千分位 / 万元元切换 / 负数色 / 变动高亮。
3. THE GtAmountCell SHALL 使用 Arial Narrow + tabular-nums 等宽字体，右对齐，确保多行金额对齐。
4. THE System SHALL 在 CI 阶段提供 grep 卡点：`align="right"` 的 el-table-column 中无 GtAmountCell 包装的命中数 ≤ baseline。
5. WHERE 金额列用于公式计算结果展示，THE GtAmountCell SHALL 支持 tooltip 显示完整原值（避免万元单位下精度损失）。

##### 8.2 加载状态统一

6. THE System SHALL 收敛加载状态为 2 种模式：表格内用 `v-loading` 指令、页面级 / 面板级用 `GtLoadingOverlay` 组件。
7. WHEN 视图首次加载且无缓存数据，THE System SHALL 使用 `el-skeleton` 骨架屏；后续 refetch 使用 v-loading。
8. THE System SHALL 删除 `LoadingState.vue` 与 `GtTableLoading.vue` 死代码（实测各 1 视图使用，归并到 GtLoadingOverlay）。
9. WHILE 一个加载请求超过 5 秒未完成，THE System SHALL 在 loading 容器内显示"加载较慢，请耐心等待"附加提示。

##### 8.3 穿透导航面包屑

10. WHEN usePenetrate 触发任意穿透跳转方法（toLedger / toWorkpaper / toReportRow / toAdjustment / toMisstatement / toNote 等），THE System SHALL 自动 push 当前路由 + 上下文到 `useNavigationStack`。
11. THE System SHALL 在 GtPageHeader 组件统一显示穿透面包屑链路（复用并扩展 DrilldownBreadcrumb 组件），用户可点击任一节点回退。
12. WHEN 用户按 Backspace 键且无聚焦输入框，THE System SHALL 调用 useNavigationStack.pop() 返回上一层（DefaultLayout `initGlobalBackspace` 已有基础，本需求扩展接入率）。

##### 8.4 GtEmpty / GtStatusTag / 分页统一

13. WHEN 列表 / 表格数据为空，THE System SHALL 使用 GtEmpty 组件（含 icon / title / description / action 四 slot），禁止使用 `el-empty` 或纯文字"暂无数据"。
14. THE System SHALL 在 GtEmpty 提供 5 种预设场景：no-data / no-permission / developing / no-search-result / load-failed，按业务调用 `<GtEmpty preset="no-data" />`。
15. WHEN 视图展示业务状态（项目状态 / 底稿状态 / 调整分录状态 / 错报状态等），THE System SHALL 使用 GtStatusTag 组件，传入 `dict-key` + `value`，组件内部从 dictStore 读取 label + color。
16. THE System SHALL 替换 17 视图的 statusEnum 硬编码字符串为 `import { Status } from '@/constants/statusEnum'` 引用，并在 CI 阶段禁止 .vue 文件出现裸状态字符串（ESLint 自定义规则）。
17. WHEN 列表数据条数 > 50，THE System SHALL 提供 el-pagination 标准分页（pageSizes=[20, 50, 100, 200]，位置在表格底部右侧）。
18. WHERE 列表为序时账类大数据（> 万行），THE System SHALL 使用虚拟滚动（el-table-v2 或 vxe-table）替代 el-pagination。

##### 8.5 错误处理统一

19. THE System SHALL 强制所有 catch 块使用 `handleApiError(e, '操作名')` 替换 `ElMessage.error(e.message)` 裸调，命中数 baseline 由实施时跑一次确定，目标降到 0。

---

### Requirement 13：全平台中文化（V3 §20）

**User Story**: As a 中文使用者审计师，我希望平台所有用户可见 UI 文本（按钮 / 表头 / 标签 / 占位符 / 弹窗 / 状态 / API 错误消息）使用中文，技术术语保留英文（SQL / PDF / OCR / LLM / API / UUID / Qwen / CAS / 编号 D2-1 等），获得一致的专业感与可读性。

**实测基线**（V3 §20.0 / §16.1）：
- 表头：28 处英文 el-table-column.label
- 按钮：36 处 `<el-button>英文</el-button>`
- 表单 label：123 处英文
- placeholder：6 处
- 弹窗 title：44 处
- confirm 文案：12 处
- 后端 HTTPException.detail：16 处英文
- 合计 ~270 处需中文化

**角色影响**：[全角色，专业感最直观]

**优先级**：🟡 P1（V3 §21.2 隐含 + §20）

**工时**：5 天（按 V3 §20.4 工时拆分：准备 0.5 + 工具 0.5 + 执行 5 - 部分压缩到 5 天）

#### Acceptance Criteria

1. THE System SHALL 在 `docs/i18n/business-glossary.md` 建立业务术语单一真源，覆盖 V3 §20.2A 列出的核心术语（Workpaper → "底稿"、Adjustment → "调整分录"、Misstatement → "错报"、Reviewer → "复核人"、Sign-off → "签字"、Trial Balance → "试算平衡表"、Disclosure → "附注披露"、Reconciliation → "调节"、Variance → "差异"、EQCR → "独立复核合伙人"等）。
2. WHEN 一个 .vue 文件包含 `label="<英文>"` / `title="<英文>"` / `placeholder="<英文>"` 属性，THE System SHALL 替换为中文文案（参照 business-glossary.md 术语表）。
3. WHEN 一个 .vue 文件包含 `<el-button>英文</el-button>` 按钮文字，THE System SHALL 替换为中文（"Save" → "保存"、"Submit" → "提交"、"Cancel" → "取消"、"Edit" → "编辑"、"Delete" → "删除"、"Export" → "导出"、"Import" → "导入"、"Filter" → "筛选"、"Search" → "搜索"等）。
4. WHEN statusEnum 状态值映射展示文案，THE System SHALL 提供中文 label（draft → "草稿"、pending_review → "待复核"、under_review → "复核中"、approved / review_passed → "已通过"、rejected → "已退回"、archived → "已归档"、active → "活动"、disabled → "已禁用"、success → "成功"、failed → "失败"）。
5. WHEN 后端 HTTPException 抛出，THE Backend SHALL 使用 detail 结构 `{error_code, message: 中文, message_en: 英文}`，前端 `parseApiError` 优先取 message。
6. WHERE 文本属于技术术语白名单（SQL / PDF / OCR / LLM / AI / API / URL / UUID / CSV / JSON / YAML / HTTP / .xlsx / .docx / .pdf / UTF-8 / RFC / ISO / WCAG / CAS / PCAOB / Qwen / GPT / Claude / DeepSeek / Ollama / vLLM / 业务编码 D2 / E1 / B-100），THE System SHALL 保留英文不替换。
7. THE System SHALL 提供一次性脚本 `scripts/_chinese_localize.py`（使用后即删，遵循 `_` 前缀规约），自动 grep 英文 UI 文本 + 对照术语表替换 + 输出未匹配项清单 + 生成 dry-run diff。
8. WHEN 一个 PR 引入新的英文 UI 文本（label / title / placeholder / 按钮文字），THE CI SHALL 触发 ESLint 自定义规则 warning（白名单技术术语豁免），baseline 0 只增不减。
9. THE System SHALL 在合并前对全平台跑 Playwright 截图对比 + 真实项目（YG2101 或类似）UAT，确认无英文 UI 残留（不含技术术语白名单）。
10. THE System SHALL 在前端 `apiPaths.ts` 提供错误码到中文文案的映射表，覆盖 16 处后端 HTTPException 已知 error_code。
11. WHERE 用户的浏览器语言为非中文，THE System SHALL 不接入 vue-i18n 框架，所有文本使用硬编码中文（未来需英文支持时再迁移）。
12. THE System SHALL 验证业务术语全平台统一不混用（如不出现"底稿"和"工作底稿"并存的情况）。

---

## Sprint 3（信任与可解释，12 天）— Req 9-11

### Requirement 9：数据信任度可视化（5 层穿透 + 修改历史 + AI 痕迹聚合）

**User Story**: As a 项目合伙人 / EQCR，我希望对任意金额单元格右键即可查看"数字信任度"综合面板，包含 5 层穿透链路、最近修改历史、AI 介入痕迹、公式依赖、一致性状态，5 秒内回答"这个数字到底准不准"。

**实测基线**（V3 §21.4.1）：当前修改历史散落在版本历史 / 审计日志 / 单元格批注，无统一展示。usePenetrate 已支持 10 种穿透方法但缺综合面板。

**角色影响**：[合伙人 / EQCR / 经理]（合伙人复核效率提升 5x，最高频操作）

**优先级**：🔴 P0（V3 §21.4.1，合伙人立场新增）

**工时**：3 天

#### Acceptance Criteria

1. WHEN 用户右键金额单元格，THE System SHALL 在 CellContextMenu 中提供"📋 数字信任度"菜单项，点击弹出综合面板。
2. THE Trust_Score_Panel SHALL 展示 5 层穿透链路：报表行 → 试算表科目 → 底稿 → 序时账明细 → 凭证扫描件，每层可点击跳转。
3. THE Trust_Score_Panel SHALL 展示最近 5 次修改历史，含 timestamp / user_name / before_value / after_value / change_reason（来源于 `audit_log` + workpaper version 表）。
4. THE Trust_Score_Panel SHALL 展示 AI 介入痕迹：是否 AI 生成 / 何时确认 / 确认人 / 模型 / prompt_hash（来源于 `ai_content_log` 表，依赖 Req 6）。
5. WHERE 当前金额来自公式计算，THE Trust_Score_Panel SHALL 展示完整公式树（含上游依赖项金额值），公式树由后端 `formula_dependency_service` 计算返回。
6. THE Trust_Score_Panel SHALL 展示一致性状态：是否与上下游同步 / 是否 stale / 是否 manual_override / 是否 AI 未确认。
7. THE Backend SHALL 提供聚合端点 `GET /api/projects/{pid}/trust-score?context={...}` 返回单 Decimal 单元格的综合信任度信息（5 层链路 + 历史 + AI + 公式 + 一致性）。
8. WHEN Trust_Score_Panel 加载超过 2 秒，THE System SHALL 显示 GtLoadingOverlay 且支持取消加载。
9. THE System SHALL 在 ReportView / TrialBalance / WorkpaperEditor / Adjustments / DisclosureEditor 5 视图全量接入此面板。

---

### Requirement 10：可解释的状态机（"当前可操作"信息面板）

**User Story**: As a 审计助理，我希望对任意底稿 / 调整分录 / 报表实例点击右上角"ℹ️ 当前可操作"按钮即可看到当前状态、允许的操作清单、不允许的操作及原因、状态机流转图，避免"为什么不能 X"的盲猜。

**实测基线**（V3 §21.4.2）：当前状态约束散落在后端 service 层守卫函数，前端只能事后报错。约 80% "为什么不能 X"客服工单可通过此功能消除。

**角色影响**：[助理 / 经理 / 合伙人]

**优先级**：🔴 P0（V3 §21.4.2，合伙人立场新增）

**工时**：2 天

#### Acceptance Criteria

1. WHEN 用户加载一个业务实例（底稿 / 调整分录 / 报表），THE System SHALL 在视图右上角显示"ℹ️ 当前可操作"按钮，hover 显示快速 tooltip。
2. WHEN 用户点击"ℹ️ 当前可操作"按钮，THE System SHALL 弹出状态机面板，展示：当前状态 / 允许的操作清单（编辑 / 删除 / 重新提交 / 打印 / 签字 / 归档）+ 每项 ✓ 或 ✗ / 不允许的操作及中文原因（如"已归档项目不可编辑"）。
3. THE Backend SHALL 提供 `GET /api/{module}/{id}/allowed-actions` 端点返回 `{current_status, allowed: [], denied: [{action, reason_zh, reason_code}]}` 结构。
4. THE Status_Machine_Panel SHALL 展示状态机流转图（当前状态 → 可达状态），使用 mermaid.js 或 ECharts 可视化。
5. THE System SHALL 在 Workpaper / Adjustment / Misstatement / Report / Disclosure 5 类业务实例提供该面板（复用同一 API 端点）。
6. WHERE 当前用户角色不允许执行某操作（如助理执行 sign_off），THE System SHALL 在 denied 列表中标注 `reason_code = "ROLE_INSUFFICIENT"` + 中文消息。
7. THE System SHALL 在状态机面板缓存 5 分钟 TTL（同一实例同一用户在 5 分钟内不重复请求）。

---

### Requirement 11：时光机自动快照（5 分钟快照 + 30 秒恢复）

**User Story**: As a 审计助理，我希望平台自动每 5 分钟为我编辑的底稿 / 调整分录创建轻量级快照，误删 / 误改后能 30 秒内恢复到 5-30 分钟前的状态，不需要等 IT 部门半天起步的备份恢复。

**实测基线**（V3 §21.4.3）：当前备份策略仅每天 02:00 全量备份，恢复粒度为天级。误操作恢复时间从半天 → 30 秒。

**角色影响**：[助理 / 经理]

**优先级**：🟡 P1（V3 §21.4.3，合伙人立场新增）

**工时**：4 天

#### Acceptance Criteria

1. WHILE 用户正在编辑某业务实例（底稿 / 调整分录 / 报表行 / 附注），THE System SHALL 每 5 分钟自动创建轻量级 diff 快照（仅记录变更的字段，非全量复制）。
2. THE System SHALL 在 DB 新增 `time_machine_snapshots` 表（迁移 V0XX 实施时取 max+1），含 instance_id / instance_type / user_id / timestamp / diff_json / parent_snapshot_id。
3. THE System SHALL 保留每个实例最近 1 小时的快照（5 分钟 × 12 = 12 个），超过 1 小时的快照按 30 分钟粒度合并（节省存储）。
4. WHEN 用户点击业务实例顶部"⏪ 时光机"按钮，THE System SHALL 弹出快照列表，按时间倒序展示最近 12 个快照，每个快照显示时间戳 + 快照预览（diff 摘要）。
5. WHEN 用户点击某快照"恢复"按钮，THE System SHALL 弹出二次确认弹窗（"恢复后当前未保存的变更将丢失"）。
6. WHEN 用户确认恢复，THE System SHALL 将业务实例的状态回滚到目标快照（基于 diff 反向应用），并记录到 audit_log（含 from_snapshot_id / to_snapshot_id）。
7. WHERE 业务实例已归档，THE System SHALL 禁止恢复操作（与 Req 1 归档只读保护配合）。
8. THE System SHALL 提供后端清理任务（每日 03:00 执行），删除超过 7 天的快照（与全量备份配合，避免 DB 膨胀）。
9. THE System SHALL 在 WorkpaperEditor / Adjustments / DisclosureEditor 3 视图提供"⏪ 时光机"入口。

---

## Sprint 4（编辑器与性能，10 天）— Req 12

### Requirement 12：编辑器与性能优化套件

**User Story**: As a 审计助理，我希望每天工作 8 小时使用的核心工具（WorkpaperEditor / 序时账 / autoSave）保持流畅、稳定、低风险，避免编辑器卡顿、自动保存丢失、控制台残留。

**实测基线**（V3 §17.6 / §17.8 / §17.9 / §10.5.1 / §16.1）：
- WorkpaperEditor.vue 2631 行（目标 ≤1000）
- autoSave 间隔 120 秒（目标 60s）
- console.log/.error/.warn 74 处生产代码残留
- 虚拟滚动 0 处（YG2101 65 万行场景必卡）

**角色影响**：[助理 / 维护者]

**优先级**：🟡 P1

**工时**：合计 10 天（瘦身 3 + 虚拟滚动 2 + autoSave 0.5 + console 0.5 + buffer 4）

#### Acceptance Criteria

##### 12.1 WorkpaperEditor 瘦身

1. THE WorkpaperEditor.vue SHALL 经过重构后行数 ≤ 1000，将 6 个 cycle composable 实例化、toolbar 配置、template dialog 配置、auto-save 逻辑、formula 引擎调用、HTML/Univer 双模式切换抽离为独立 composable / 子组件。
2. THE System SHALL 将 toolbar 按钮逻辑从 if/else 改为声明式数组配置（`toolbarButtons: ToolbarButton[]`），通过 v-for 渲染。
3. THE System SHALL 删除 WorkpaperEditor 内冗余别名 ref（多个 computed 指向同一 source）。
4. WHEN 重构完成，THE System SHALL 通过 vue-tsc + 现有 vitest 单测 + Playwright 全量回归（不允许任何用户可见行为变化）。

##### 12.2 序时账虚拟滚动

5. WHEN 序时账（LedgerPenetration）列表数据 > 1 万行，THE System SHALL 使用 el-table-v2 虚拟滚动渲染，避免 65 万行场景下浏览器卡死。
6. THE System SHALL 在虚拟滚动模式下保留以下功能：列宽拖拽（resizable）/ 行选择（checkbox）/ 右键菜单（CellContextMenu）/ 排序 / 筛选。
7. THE Backend SHALL 强制分页 page_size 默认 100、最大 1000（前端禁止"加载全部"操作）。
8. THE System SHALL 提供 LedgerPenetration 在 65 万行真实数据（YG2101 实测样本）下的性能基准测试（首屏渲染 < 500ms、滚动 fps ≥ 30）。

##### 12.3 autoSave 60s

9. THE useWorkpaperAutoSave composable SHALL 默认 intervalMs 设为 60 秒（从当前 120 秒下降）。
10. WHEN 检测到大量编辑操作（10 次以上 cell 变更或 5 分钟内未保存），THE System SHALL 临时缩短 intervalMs 到 30 秒。
11. IF 自动保存请求失败，THEN THE System SHALL 立即重试 1 次，仍失败则在顶栏显示红色"自动保存失败"提示 + 手动保存按钮。
12. THE System SHALL 在用户离开页面前（beforeunload）触发同步保存（与 useEditingLock 配合释放编辑锁）。

##### 12.4 console.log 清零

13. THE System SHALL 替换所有 .vue 文件中的 `console.log/error/warn` 为 `import.meta.env.DEV && console.log(...)` 或直接删除。
14. THE System SHALL 在 ESLint 配置中将 `no-console` 规则设为 error（仅允许 warn 在 DEV 模式）。
15. THE CI SHALL 在 frontend-build 流程后 grep `dist/` 目录确认无 console.log 输出（baseline 0）。
16. WHERE 代码确实需要在生产保留 console.warn / error（如 ErrorBoundary 上报），THE System SHALL 使用统一的 `logger.warn / error` wrapper（带前缀 `[Audit]` 便于过滤）。

---

## Correctness Properties（用于后续 PBT）

以下不变量将在 design.md / tasks.md 阶段细化为具体 hypothesis / fast-check 属性测试。每条 Property 注明覆盖的 Requirement 编号。

### Property 1：归档不变量（Req 1）

**形式化**：∀ project P, ∀ mutation endpoint E, ∀ user U:
  `P.status == archived ∧ E ∈ MUTATION_ENDPOINTS ⇒ E(P, U) returns 423`

**测试策略**：
- 输入 strategy：随机生成 archived Project + 任意 mutation endpoint + 任意角色用户
- 业务不变量：归档项目所有 mutation 端点必返回 423，无例外（除合规专用通道）
- 反例期望：找到任何返回 200 的 mutation = production bug
- max_examples：50（P0 关键 Property）

### Property 2：Decimal 精度不变量（Req 2）

**形式化**：∀ amounts [a₁, a₂, ..., aₙ] where aᵢ ∈ Decimal:
  `sum_decimal(amounts) == quantize(true_sum, 0.01)`
  AND `|sum_decimal(amounts) - sum_float(amounts)| ≤ tolerance(n, scale)`

**测试策略**：
- 输入 strategy：`st.lists(st.floats(0, 1e9), min_size=10000, max_size=100000)` 后转 Decimal
- 业务不变量：10 万行金额累加，Decimal 计算结果精确（误差 ≤ 0.01 元）
- 独立 oracle：用 Python 的 sum() 直接累加 Decimal 作为参考实现
- 反例期望：累加误差 > 0.01 = float 处理金额（违规）
- max_examples：100（P0 关键 Property，金额合规）

### Property 3：表单校验不变量（Req 3）

**形式化**：∀ form submission S:
  `S is submitted ⇒ S has passed validate()`

**测试策略**：
- 输入 strategy：Playwright 模拟随机字段组合（含空值 / 非法格式）
- 业务不变量：no validate → no submit
- 反例期望：找到任何"未经 validate 即提交"的表单 = production bug
- max_examples：50

### Property 4：删除确认不变量（Req 4）

**形式化**：∀ delete operation D:
  `D is executed ⇒ D was preceded by confirm() within last 3s`

**测试策略**：
- 静态扫描：grep `api.delete(` 前 3 行内必有 `confirm` 调用
- 运行时验证：Playwright 拦截 DELETE 请求，确认前置弹出 ElMessageBox
- 反例期望：找到任何"无 confirm 直接 delete"的代码路径 = production bug

### Property 5：年度切换响应不变量（Req 5）

**形式化**：∀ view V depending on year, ∀ year change Y → Y':
  `Y → Y' triggers V.refetch() within 1s`

**测试策略**：
- 输入 strategy：随机选取 7 个核心视图 + 随机 year 切换序列
- 业务不变量：year 切换后 1 秒内所有可见视图已更新数据
- 反例期望：找到任何视图切换 year 后数据不变 = production bug（即 onMounted 一次性加载）
- max_examples：50

### Property 6：AI 内容确认不变量（Req 6）

**形式化**：∀ project P, ∀ sign_off attempt S:
  `∃ ai_content c in P with c.confirm_action == pending ⇒ S returns 422`

**测试策略**：
- 输入 strategy：随机生成项目 + 0~N 个未确认 AI 内容
- 业务不变量：未确认 AI 内容存在 → 签字必须被阻断
- 反例期望：找到任何"未确认 AI 内容存在但签字成功"的场景 = AIContentMustBeConfirmedRule 失效
- max_examples：50

### Property 7：manual_override 保护不变量（Req 7）

**形式化**：∀ field F with manual_override=true, ∀ upstream change U:
  `U → F should NOT silently overwrite F.value`
  `instead, conflict event is enqueued`

**测试策略**：
- 输入 strategy：构造 D2 底稿改值 → 附注联动场景，附注字段 manual_override=true
- 业务不变量：联动写入被拦截 + 调解事件入队 + audit_log 留痕
- 反例期望：找到任何"manual_override=true 字段被自动覆盖且无调解记录"= production bug
- max_examples：50

### Property 8：金额展示一致性（Req 8）

**形式化**：∀ amount cell A in any table:
  `A renders via GtAmountCell ⇔ A respects displayPrefs (unit, decimal, color)`

**测试策略**：
- 静态扫描：grep `align="right"` 的 el-table-column，应使用 GtAmountCell 包装
- 运行时验证：切换 displayPrefs 后所有金额展示统一变化
- 反例期望：找到任何金额裸渲染 `{{ row.amount }}` 的视图 = baseline 违规
- max_examples：5（探索类，主要靠静态扫描）

### Property 9：穿透面包屑可逆性（Req 8.3）

**形式化**：∀ navigation chain v₁ → v₂ → ... → vₙ via usePenetrate:
  `Backspace pops to vₙ₋₁` AND `Click breadcrumb[i] returns to vᵢ`

**测试策略**：
- 输入 strategy：随机生成 1-5 层穿透链路
- 业务不变量：navigation stack push/pop 对称，面包屑点击与 Backspace 行为一致
- 反例期望：找到任何"穿透后无法返回"或"返回到错误层级"的场景 = production bug
- max_examples：50

### Property 10：中文化覆盖不变量（Req 13）

**形式化**：∀ vue file V containing label/title/placeholder/btn-text:
  `text matches /^[A-Za-z0-9 ]+$/ ⇒ text ∈ TECHNICAL_WHITELIST`

**测试策略**：
- 静态扫描：grep 所有英文 UI 文本，对照技术术语白名单（SQL/PDF/OCR/LLM/API/UUID/CAS/PCAOB/编号/...）
- 业务不变量：非白名单英文文本数 = 0
- 反例期望：找到任何未豁免的英文 UI 文本 = 中文化未达标

### Property 11：状态机一致性（Req 10）

**形式化**：∀ instance I, ∀ action A:
  `A ∈ allowed_actions(I) ⇔ execute(A, I) succeeds`
  `A ∈ denied_actions(I) ⇒ execute(A, I) returns 403/422/423`

**测试策略**：
- 输入 strategy：随机生成业务实例不同状态 + 随机 action 调用
- 业务不变量：API 与状态机面板的"允许 / 不允许"判断完全一致
- 反例期望：找到任何"显示允许但实际拒绝"或"显示拒绝但实际允许"= 状态机面板不可信
- max_examples：100（P0 关键 Property）

### Property 12：时光机恢复幂等性（Req 11）

**形式化**：∀ instance I, ∀ snapshot S:
  `restore(I, S) followed by restore(I, S) == restore(I, S)`
  AND `state(I after restore) == state(I at snapshot S timestamp)`

**测试策略**：
- 输入 strategy：随机生成业务实例编辑序列 + 随机选取快照恢复
- 业务不变量：恢复操作幂等（多次恢复同一快照结果一致）+ 恢复后状态等于快照时状态
- 反例期望：找到任何"恢复后状态与快照不一致"= diff 反向应用算法 bug
- max_examples：50

### Property 13：autoSave 不丢失不变量（Req 12.3）

**形式化**：∀ edit session E with > 60s duration:
  `at least one auto_save fired during E`
  `last_saved_state covers all confirmed edits before t = E.end - 60s`

**测试策略**：
- 输入 strategy：模拟编辑会话（fake-timers）+ 随机编辑事件
- 业务不变量：60 秒间隔触发 autoSave + 失败时立即重试
- 反例期望：找到任何"60 秒内无 autoSave 触发"或"重试失败但无提示"= production bug
- max_examples：50

---

## 已知缺口与技术债（不在本 spec 范围）

以下条目明确**不在本 spec 范围内**，列出避免范围蔓延 / 后续按需独立 spec 处理：

### V3 §10 测试 / CI 强化

- 前端单测覆盖率（vitest 覆盖率从 4 个 composable 扩展到 80%）
- 前端 E2E CI（Playwright spec 已建但 CI 未跑）
- 性能回归检查（YG36/YG2101 耗时 baseline 监控）
- 安全扫描（npm audit / pip-audit 集成）
- 测试 fixture 复用 `make_session_for(*model_modules)`
- **触发条件**：完成本 spec 后下一个 Sprint，或 CI 工具升级窗口
- **后续 spec**：`v3-ci-test-strengthening`

### V3 §13 业务延伸

- 跨期事项独立工作流（C1，2 天）
- 客户沟通模板库（C2，1 天）
- 离线工作能力（C5，5 天）
- 风险评估工作底稿 RAS（C7，3 天）
- **触发条件**：合伙人提出业务需求后启动
- **后续 spec**：`audit-cross-period-events` / `client-communication-templates` / `audit-offline-pwa` / `risk-assessment-summary`

### V3 §19.2 PBC + 客户协作

- PBC router 完整实现（清单生成 / 状态跟踪 / SLA 提醒）
- 客户端 mini portal（手机号/邮箱验证码登录 + 文件上传）
- 通知集成（邮件 + 企业微信 + 钉钉）
- **触发条件**：客户协作流程被列为下季度优先级
- **后续 spec**：`pbc-client-portal`（独立 12-15 天 Sprint）

### IT 部门职责

- §10.7.2 备份恢复 DR 演练（IT 部门职责）
- §10.7.3 监控告警体系 Grafana / Prometheus / Alertmanager
- §10.3.3 API 速率限制全局（中型事务所攻击模型不同于公网 SaaS）
- **触发条件**：IT 部门排期
- **后续 spec**：N/A（运维责任）

### V3 §21.3 第一波延后条目

- 全平台深色模式完善（已有基础，6000 用户中真正用的不到 5%）
- 字号超大档（19px）扩展
- 国际化 i18n 全量接入（Req 13 已用硬编码替代）
- Storybook 组件文档自动生成
- Bundle visualizer 监控
- iPad 适配
- **触发条件**：用户反馈驱动 / 团队规模 > 20 人
- **后续 spec**：按需独立立项

### V3 §17.10 except Exception 治理

- backend 1162 处 `except Exception` 分类治理（合理降级 vs 粗糙吞没）
- ruff 自定义规则 `except Exception` 后必须有 logger 调用或 raise
- **触发条件**：CI/lint 强化窗口
- **后续 spec**：合并到 `v3-ci-test-strengthening` 或独立 `backend-exception-cleanup`

### V3 §17.4 displayPrefs 后端持久化

- 后端 `user_preferences` 表 + GET/PUT 端点
- 前端 displayPrefs store 初始化拉取 + debounce 写回
- **触发条件**：用户报告设置丢失 > 5 例
- **后续 spec**：`user-preferences-persistence`（独立 1 天）

### V3 §17.5 cross_wp_references 实时化

- cross_wp_references.json → DB 表迁移
- 实时事件触发（已有 cross-ref:updated 事件，触发条件不完整）
- **触发条件**：底稿数据同步问题集中爆发
- **后续 spec**：`cross-wp-refs-realtime`

### V3 §10.1.1 中间件双份代码清理

- `audit_log_middleware.py`（死代码）删除（main.py 引用 `audit_log.py`）
- **触发条件**：触碰相关代码时顺手做（不立 spec）
- **后续 spec**：N/A

### V3 §17.11 五角色专项细化

- 经理：复核进度汇总 + 团队负荷可视化
- 质控：规则有效性分析（从未触发的规则标黄）
- 合伙人：签字 checklist 强制确认
- EQCR：KAM 过滤独立视图
- **触发条件**：完成本 spec 后角色体验 Sprint
- **后续 spec**：`v3-role-experience-polish`

---

## 实施策略

### Sprint 顺序与依赖

```
Sprint 1（合规底线，18.5 天）
├── Req 1 归档只读保护（独立）
├── Req 2 Decimal 化（独立）
├── Req 3 表单校验（独立）
├── Req 4 删除确认（独立）
├── Req 5 年度切换 + 路由响应（独立，但被 Req 8 / 9 / 12 间接依赖）
├── Req 6 AI 溯源闭环（被 Req 9 数据信任度依赖）
└── Req 7 跨模块冲突调解（独立）

Sprint 2（高频体验，15 天）
├── Req 8 体验一致性套件（依赖 Req 5 已落地）
└── Req 13 中文化（依赖 statusEnum 清零，与 Req 8.4 协同）

Sprint 3（信任与可解释，12 天）
├── Req 9 数据信任度可视化（依赖 Req 6 ai_content_log 表）
├── Req 10 状态机解释（独立）
└── Req 11 时光机快照（独立）

Sprint 4（编辑器与性能，10 天）
└── Req 12 编辑器与性能（独立）
```

**关键依赖**：
- Req 9 必须等 Req 6 的 `ai_content_log` 表落地后实施
- Req 8.4（statusEnum 清零）与 Req 13（中文化）必须协同进行（statusEnum label 需中文）
- Req 5 的 `useAuditContext()` 是 Req 8.3 穿透面包屑、Req 9 数据信任度面板的隐式前提

### 实施原则

1. **数据安全 > 合规底线 > 体验一致 > 功能完整 > 锦上添花**——按这个顺序排
2. **每 Sprint 结束做真实 UAT**：技术指标 ≠ 业务指标，挑 1-2 个真实项目（YG2101 或类似）跑全流程
3. **CI 卡点优先于代码改动**：先建立 baseline 防退化，再逐批清理
4. **小步快跑**：每 Sprint 1-2 周，避免长 Sprint 失控
5. **可审计的状态变更**：所有 task 标 [x] 前必须跑 pytest + vitest + Playwright 验证

### 上线检查清单（V3 §21.6）

合伙人在签字"系统可上线"前会检查的硬指标：

✅ **数据完整性**：
- [ ] 所有金额计算路径 Decimal 化（grep `float()` in services 命中数 < 50）— Req 2
- [ ] 归档项目所有 mutation 端点返回 423（黑盒测试 5 个端点）— Req 1
- [ ] 跨模块 manual_override 不被自动覆盖（Playwright 测试用例）— Req 7

✅ **合规可追溯**：
- [ ] AI 生成内容 100% 有水印 + 确认轨迹（grep AiContentConfirmDialog 接入 ≥ 10 视图）— Req 6
- [ ] 操作审计日志覆盖核心操作（删除 / 签字 / 归档）— Req 1 / 4 / 7
- [ ] 数字溯源链路完整（点任意金额能回到原始凭证）— Req 9

✅ **基础体验**：
- [ ] 切换年度所有视图响应（Playwright 自动化跑 7 视图）— Req 5
- [ ] 表单校验全覆盖（grep `el-form` 无 `:rules` 视图数 = 0）— Req 3
- [ ] 全平台 UI 中文化（grep 英文 label/title 命中数 < 10）— Req 13
- [ ] 删除操作 100% 二次确认 — Req 4

✅ **性能底线**：
- [ ] 序时账 65 万行流畅滚动（虚拟滚动）— Req 12.2
- [ ] 首屏加载 < 5s（移动 4G 环境）
- [ ] autoSave 60s 不丢失 — Req 12.3

不达标项不上线，达标项自动归档到"已完成"章节。

---

## 项目约定遵守清单

本 spec 严格遵守 `.kiro/steering/conventions.md` 既有约定：

- [x] 编号规则：Req {N} → AC {N}.{M}，与既有 spec 一致
- [x] UI 视觉规范：紫色主品牌色 #4b2d77、按钮圆角 8px、表格 border + resizable、危险按钮 text 模式
- [x] 表格规范：金额列用 GtAmountCell（Req 8.1 强化）、字号 12px、行高 26px、选中样式统一 gt-ucell--selected
- [x] 后端编码规范：所有金额走 Decimal（Req 2）、`datetime.utcnow()` 保持 naive、UTF-8 BOM 防御、SoftDeleteMixin、`Depends(get_current_user)` 强制
- [x] 前端编码规范：禁止直接 import http 拼 URL、apiProxy 单层解构、SSE 用 sse.ts 封装
- [x] 迁移文件位置：`backend/migrations/V0XX.sql`（Req 6 ai_content_log / Req 11 time_machine_snapshots / Req 7 cross_module_conflicts 实施时取 max+1，禁止本 spec 硬编码编号）
- [x] router_registry 注册铁律：新建 router（如 trust-score / allowed-actions / time-machine）必须在 `backend/app/router_registry/{group}.py` 注册
- [x] 全平台中文化铁律：UI 文本中文，技术术语保留英文（Req 13 全量执行）
- [x] 三层一致校验：DB 迁移 + ORM Mapped[] + service 方法（Req 6 / 7 / 11 三个新表必须三层齐全）
- [x] B' 视图四表查询规约：所有 Tb* 查询走 `get_active_filter`（Req 9 数据信任度面板的试算表层）
- [x] 删除二次确认 + 先进回收站（Req 4 强化）
- [x] PowerShell 中文/emoji 写入用 fsWrite / strReplace（中文化批量替换工具用 Python 字节级读写绕 GBK）
- [x] 一次性脚本用完即删（Req 13 的 `_chinese_localize.py` 遵循 `_` 前缀规约）
- [x] Spec 起草铁律：design.md 必须代码锚定（本 requirements 阶段已引用具体文件 / 行 / 函数 / 实测数字 / baseline）

---

*文档结束。下一步：用户确认 requirements 范围后，单独发起 design.md 阶段。*
