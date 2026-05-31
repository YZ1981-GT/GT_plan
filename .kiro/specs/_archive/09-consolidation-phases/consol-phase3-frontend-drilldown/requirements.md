# 需求文档：consol-phase3-frontend-drilldown（合并模块 Phase 3 前端联动 + 附注穿透）

> 关联设计：#[[file:.kiro/specs/consol-phase3-frontend-drilldown/design.md]]
> 前置依赖：consol-phase0（B1/breakdown）+ consol-phase1（锁定/banner）+ consol-phase2（报表穿透后端/V2/refresh-all）
> 工作流：Design-First。EARS 风格，关联设计 §六 属性 T1~T6。

## 引言（Introduction）

Phase 3 把后端能力暴露为用户可用的联动体验：①统一穿透组件 ConsolBreakdownDialog（report+note）②附注级穿透后端（disclosure_notes 加 provenance 字段 + V2 写入 + 端点）+ UI ③双向导航（单体↔合并跳转 + 锁定标签）④自动建树 + scope 联动 ⑤子公司完整度校验 ⑥F5 合并页 stale 实时感知。

**范围内**：ConsolBreakdownDialog / 附注穿透后端+UI / 双向导航 / 自动建树+scope 事件 / 完整度校验 / F5 合并页 stale 实时感知。
**范围外**：真实集团数据 UAT / 审计师真实章节映射替换 mock / 上年数结转 + 衔接3 跨年抵销转回（留 Phase 4）。

**全程铁律**：穿透组件统一复用 / 附注 provenance 依赖 V2 / UI 全中文化 / 改动后必 Playwright 实测 / 溯源跳转支持 Backspace。

---

## 需求 1：统一穿透组件 ConsolBreakdownDialog

**用户故事**：作为合并执行人，我希望右键合并报表行或合并附注章节就能看到该数由哪些子公司贡献多少、抵销多少，并能点进去看单体明细，以便核查合并数来源。

### 验收标准
1. THE 系统 SHALL 新建 `ConsolBreakdownDialog.vue`（`props.source = 'report' | 'note'`），渲染各子公司金额 + 占比 + 抵销额 + 合并数。
2. WHERE `source == 'report'` THE 组件 SHALL 调 Phase 2 的 `report/{account_code}/consol-breakdown`；WHERE `source == 'note'` SHALL 调 Phase 3 新建的 `notes/{section_id}/consol-breakdown`。
3. THE 组件对 report/note 两 source SHALL 渲染同一结构契约（列/合并数/跳转一致，关联属性 **T1**）。
4. WHEN 点击某子公司行 THEN 系统 SHALL 跳转该单体报表/附注，并纳入 Backspace 返回栈（关联属性 **T3**）。
5. WHERE 调用方无目标单体项目访问权 THE 系统 SHALL 跳转前校验（Phase 0 P5）并 ElMessage 提示不跳（关联错误场景 **EH2**）。
6. THE 所有文本 SHALL 中文，金额用 `.gt-amt`/GtAmountCell。

---

## 需求 2：附注级穿透后端（disclosure_notes provenance）

**用户故事**：作为合并执行人，我希望合并附注章节能反查由哪些子公司哪些章节汇总而来，以便附注层也能溯源（不只报表层）。

### 验收标准
1. THE 系统 SHALL 为 `disclosure_notes` 新增 `source_project_id UUID` + `consolidation_breakdown JSONB` 字段（迁移 + ORM `Mapped` 三层一致，关联属性 **T6**）。
2. THE V2 `generate_full_consol_notes`（Phase 2 接线）SHALL 在汇总每章节时写入 `consolidation_breakdown` provenance（哪些子公司哪些章节贡献多少）。
3. THE 系统 SHALL 新建 `note_consol_drilldown_service` + `GET /api/consolidation/notes/{project_id}/{year}/{section_id}/consol-breakdown`。
4. THE 附注穿透 `Σ by_company[*].amount`（同口径）SHALL 与该合并章节汇总值一致（provenance 自洽，关联属性 **T2**）。
5. IF 章节无 `consolidation_breakdown`（未跑 V2）THEN 系统 SHALL 返回空 + 提示"该章节暂无合并明细，请先用 V2 生成合并附注"（关联错误场景 **EH1/EH3**、风险 **R1**）。

---

## 需求 3：右键菜单接入穿透

**用户故事**：作为合并执行人，我希望在合并报表和合并附注界面通过右键就能打开穿透明细，操作直观。

### 验收标准
1. THE 合并报表视图（ReportView 等）行右键菜单 SHALL 加"查看合并明细"→ ConsolBreakdownDialog(source=report)。
2. THE `DisclosureEditor` / `ConsolNoteTab` 章节右键菜单 SHALL 加"查看合并明细"→ ConsolBreakdownDialog(source=note)。
3. THE 接入 SHALL grep 合并报表/附注相关视图逐一覆盖，不遗漏（关联风险 **R5**）。

---

## 需求 4：双向导航

**用户故事**：作为审计人员，我希望能在单体项目和合并项目之间快速跳转，并一眼看出哪些子公司被锁定，以免导航断裂。

### 验收标准
1. WHERE 单体项目 `parent_project_id` 非空 THE 项目 header SHALL 显示"所属集团：{母项目名}"链接 → 跳转合并项目。
2. THE 合并树节点（ConsolidationIndex）SHALL 加"进入项目"按钮 → 路由该单体项目。
3. WHERE 子公司处于锁定态 THE 合并项目列表 SHALL 显示"🔒 已锁定"标签（复用 Phase 1 锁定态）。
4. THE 所有跳转 SHALL 纳入 Backspace 返回栈（关联属性 **T3**）。

---

## 需求 5：自动建树 + scope 联动

**用户故事**：作为合并执行人，我希望创建合并项目时能直接配置合并范围，且增删子公司后树自动更新，不用手动刷新。

### 验收标准
1. WHEN wizard 完成且 `report_scope == consolidated` THEN 系统 SHALL 弹"配置合并范围"步骤（选已有单体项目挂为子公司）。
2. WHEN `consol_scope` 增删子公司 THEN 系统 SHALL 发 `CONSOL_SCOPE_CHANGED` 事件 → 失效/重建树缓存（关联属性 **T4**）。
3. THE 前端 ConsolidationIndex SHALL 监听该事件自动刷新树。
4. IF 事件丢失 THEN 系统 SHALL 提供手动"刷新树"按钮兜底（关联错误场景 **EH4**、ADR **CONSOL-303**）。
5. THE wizard 改动 SHALL 仅影响 consolidated 项目，非合并项目流程不变（关联风险 **R3**）。

---

## 需求 6：子公司数据完整度前置校验

**用户故事**：作为合并执行人，我希望一键刷新前系统提醒我哪些子公司数据不全，避免拿空数据合并出错。

### 验收标准
1. WHEN 触发一键刷新（Phase 2 refresh-all）前 THEN 系统 SHALL 检查各子公司 TB 审定数（非全 0）+ 附注生成状态。
2. IF 某子公司数据不全 THEN 系统 SHALL warning「子公司 XXX 数据不完整，合并结果可能不准确」但 **不阻断**刷新（关联属性 **T5**）。
3. WHERE 子公司过多校验耗时 THE 系统 SHALL 异步 + 超时降级（部分结果 + 提示），不阻断（关联错误场景 **EH5**）。

---

## 需求 7：合并页 stale 实时感知（F5）

**用户故事**：作为合并执行人，我希望在合并页面能实时看到子公司数据已变更的提示，以便及时重新汇总，而不是看着过时的合并数浑然不觉。

### 验收标准
1. THE 后端 `consol_note_stale_handler`（已订阅 NOTE_UPDATED 标记母项目 stale）SHALL 在标记 stale 时发 SSE 事件通知前端。
2. WHEN 子公司数据变更导致母项目 stale THEN 合并页 SHALL 通过 SSE/轮询感知并提示「子公司数据已更新，建议重新汇总」。
3. THE 提示 SHALL 不阻断当前操作（warning 级，提供"立即重新汇总"快捷入口跳一键刷新）。
4. THE 实现 SHALL 复用既有 SSE 基础设施（不新增轮询打爆 pool，呼应 A5/Phase 2 R5）。

---

## 非功能性需求

### NFR-1：测试与质量
1. THE 属性 T1~T6 SHALL 用对应框架实现（T1 vitest / T2·T5 hypothesis / T3 Playwright / T4·T6 集成）并 CI 全绿。
2. THE 穿透弹窗 + 双向跳转 + 自动建树 SHALL Playwright 实测，不伪绿。
3. THE 附注穿透真实子公司数据正确性 SHALL 标"待数据"（卡 Phase 4）不伪绿。

### NFR-2：兼容与体验
1. THE 穿透跳转 SHALL 纳入 DefaultLayout initGlobalBackspace 返回栈。
2. THE 附注穿透 SHALL 以 V2 启用为前提，无 V2 友好提示（R1）。

---

## 正确性属性 → 需求映射表

| 属性 | 守护需求 | 验收锚点 |
|------|---------|---------|
| T1 穿透组件契约统一 | 需求 1 | 1.3 |
| T2 附注 provenance 自洽 | 需求 2 | 2.4 |
| T3 跳转返回栈完整 | 需求 1/4 | 1.4 / 4.4 |
| T4 scope 变更触发重建树 | 需求 5 | 5.2 |
| T5 完整度校验不阻断 | 需求 6 | 6.2 |
| T6 附注新字段三层一致 | 需求 2 | 2.1 |

## ADR → 需求映射表

| ADR | 落地需求 |
|-----|---------|
| ADR-CONSOL-301 统一穿透组件 | 需求 1 / 3 |
| ADR-CONSOL-302 附注 provenance V2 写入 | 需求 2 |
| ADR-CONSOL-303 自动建树 EventBus 解耦 | 需求 5 |
| ADR-CONSOL-304 合并页 stale SSE 实时感知 | 需求 7 |
