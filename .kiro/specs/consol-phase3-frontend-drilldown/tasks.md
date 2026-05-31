# 任务清单：consol-phase3-frontend-drilldown（合并模块 Phase 3 前端联动 + 附注穿透）

> 关联设计：#[[file:.kiro/specs/consol-phase3-frontend-drilldown/design.md]]
> 关联需求：#[[file:.kiro/specs/consol-phase3-frontend-drilldown/requirements.md]]
> 前置：consol-phase0（B1/breakdown）+ consol-phase1（锁定/banner）+ consol-phase2（报表穿透后端/V2/refresh-all）完成。~3 人天。
> 任务约定：`[ ]` 未开始 / `[x]` 完成 / `[ ]*` 可选。铁律：穿透组件统一复用 / 附注 provenance 依赖 V2 / UI 全中文化 / 改动后必 Playwright 实测 / 溯源支持 Backspace。

---

## 阶段 0：基线核实

- [x] 0. 实证基线
  - [x] 0.1 grep 确认 `ConsolBreakdownDialog.vue` 不存在 + `disclosure_notes` 无 source_project_id/consolidation_breakdown 字段
  - [x] 0.2 readCode Phase 2 `report/consol-breakdown` 端点返回结构（穿透组件 report source 对接）
  - [x] 0.3 readCode `generate_full_consol_notes` V2 汇总逻辑（确认在哪写 provenance）
  - [x] 0.4 grep 合并报表/附注视图（ReportView/DisclosureEditor/ConsolNoteTab）右键菜单接入点
  - [x] 0.5 readCode wizard report_scope 流程 + ConsolidationIndex 树渲染 + MiddleProjectList，作双向导航/自动建树接入点
  - [x] 0.6 确认 DefaultLayout initGlobalBackspace 返回栈接入方式
  - _需求：全部（基线）_ _铁律：彻底解决不绕开 / 触类旁通 grep_

---

## 阶段 1：附注穿透后端（disclosure_notes provenance）

- [x] 1. provenance 字段 + V2 写入 + 端点
  - [x] 1.1 迁移 V0XX：`disclosure_notes` 加 `source_project_id UUID` + `consolidation_breakdown JSONB` + GIN 索引 + 配套 R 回滚
  - [x] 1.2 ORM `DisclosureNote` 同步加 `Mapped` 字段（三层一致，关联 T6）
  - [x] 1.3 V2 `generate_full_consol_notes` 汇总每章节时写 `consolidation_breakdown` provenance（关联 T2）
  - [x] 1.4 新建 `note_consol_drilldown_service` + `GET notes/{project_id}/{year}/{section_id}/consol-breakdown`（挂现有 consol_notes router 或登记）
  - [x] 1.5 无 breakdown 返回空 + "请先用 V2 生成合并附注"（关联 EH1/EH3）
  - _需求：2.1~2.5_ _属性：T2/T6_ _铁律：三层一致 / router_registry 必查_

---

## 阶段 2：统一穿透组件 ConsolBreakdownDialog

- [x] 2. ConsolBreakdownDialog.vue
  - [x] 2.1 新建组件（props.source=report|note，渲染子公司金额+占比+抵销+合并数，GtAmountCell）
  - [x] 2.2 source=report 调 Phase 2 端点，source=note 调 Phase 3 端点（渲染契约统一，关联 T1）
  - [x] 2.3 点子公司行 emit jump → 跳单体报表/附注 + 纳入 Backspace 返回栈（关联 T3）
  - [x] 2.4 跳转前权限校验，无权 ElMessage 不跳（关联 EH2）
  - _需求：1.1~1.6_ _属性：T1/T3_ _铁律：UI 全中文化 / 穿透组件统一复用_

- [x] 3. 右键菜单接入
  - [x] 3.1 合并报表视图行右键加"查看合并明细"→ Dialog(source=report)
  - [x] 3.2 DisclosureEditor/ConsolNoteTab 章节右键加"查看合并明细"→ Dialog(source=note)
  - [x] 3.3 grep 全部相关视图逐一覆盖（关联 R5）
  - _需求：3.1~3.3_ _铁律：触类旁通 grep_

---

## 阶段 3：双向导航

- [ ] 4. 单体↔合并跳转 + 锁定标签
  - [x] 4.1 单体项目 header：parent_project_id 非空显示"所属集团：{名}"链接 → 跳合并项目
  - [x] 4.2 ConsolidationIndex 树节点加"进入项目"按钮 → 路由单体项目
  - [x] 4.3 合并项目列表锁定子公司显示"🔒 已锁定"标签（复用 Phase 1）
  - [x] 4.4 所有跳转纳入 Backspace 返回栈（关联 T3）
  - _需求：4.1~4.4_ _属性：T3_ _铁律：溯源支持 Backspace_

---

## 阶段 4：自动建树 + scope 联动

- [x] 5. wizard 配置合并范围 + scope 事件
  - [x] 5.1 wizard report_scope=consolidated 完成弹"配置合并范围"步骤（选单体挂子公司）
  - [x] 5.2 EventType 加 `CONSOL_SCOPE_CHANGED`；consol_scope 增删发事件 → 失效/重建树缓存
  - [x] 5.3 前端 ConsolidationIndex 监听事件自动刷新树
  - [x] 5.4 手动"刷新树"按钮兜底（事件丢失，关联 EH4）
  - [x] 5.5 wizard 改动仅影响 consolidated 项目，回归测试非合并流程不变（关联 R3）
  - _需求：5.1~5.5_ _属性：T4_

---

## 阶段 4B：母分合并（总分汇总）前端收尾

> 背景：母分合并核心计算 + 合并页类型切换已在 Phase 0 闭环（`consolidation_type` subsidiary/branch + project_config 读写 API + ConsolidationIndex 顶部单选）；本阶段补剩余 UX 缺口，使总分汇总语义完整。

- [x] 5B. 母分合并 UX 完整化
  - [x] 5B.1 总分汇总模式（`consolidation_type=="branch"`）合并工作底稿顶部显示"总分汇总无需抵销"提示条（ConsolWorksheetTabs 读 config 判断 isBranchMode）
  - [x] 5B.2 建项目向导（BasicInfoStep）report_scope=consolidated 时增加"合并类型"单选（母子合并/总分汇总），写入 `consolidation_type`（BasicInfoSchema + _sync_basic_info_to_project，单户报表清空）
  - [x] 5B.3 合并模块页面顶部（ConsolidationIndex GtToolbar）显示当前合并类型单选标识，所有 Tab 之上随时可见可切
  - [ ] 5B.4 Playwright 实测：建总分项目 → 抵销入口隐藏 → 重算 consol_amount==individual_sum（无抵销）（待 start-dev.bat 环境）
  - _需求：母分合并（consolidation_type）_ _铁律：UI 全中文化 / 改动后必 Playwright 实测_

---

- [x] 6. check_subsidiary_completeness
  - [x] 6.1 一键刷新前检查各子公司 TB 审定数 + 附注生成状态
  - [x] 6.2 不全 warning 不阻断刷新（关联 T5）
  - [x] 6.3 子公司过多异步 + 超时降级（关联 EH5）
  - _需求：6.1~6.3_ _属性：T5_

---

## 阶段 5B：F5 合并页 stale 实时感知

- [x] 6A. stale SSE 推送 + 前端感知
  - [x] 6A.1 `consol_note_stale_handler` 标记母项目 stale 时发 SSE 事件
  - [x] 6A.2 合并页通过 SSE 感知 → 提示「子公司数据已更新，建议重新汇总」（warning 不阻断）
  - [x] 6A.3 提示内含"立即重新汇总"快捷入口 → 跳 Phase 2 一键刷新
  - [x] 6A.4 复用既有 SSE 基础设施（不新增轮询打爆 pool，关联 Phase 2 R5）
  - _需求：7.1~7.4_ _铁律：前后端必须联动 / 不轮询打爆 pool_

---

## 阶段 6：测试

- [x] 7. vitest + PBT + 集成
  - [x] 7.1 T1 ConsolBreakdownDialog 对 report/note 渲染契约一致（vitest props 切换）
  - [x] 7.2 T2 附注 provenance 自洽：Σ by_company amount == 章节汇总值（hypothesis）
  - [x] 7.3 T4 scope 变更触发重建树（集成测试）
  - [x] 7.4 T5 完整度校验不阻断（hypothesis：数据不全 warnings 非空但刷新执行）
  - [x] 7.5 T6 disclosure_notes 新字段 drift 0（集成测试）
  - _需求：1/2/5/6_ _属性：T1/T2/T4/T5/T6_ _铁律：hypothesis 调速 / vitest_

- [ ] 8. Playwright 实测
  - [ ] 8.1 T3 报表/附注右键穿透 → ConsolBreakdownDialog → 点子公司跳转 → Backspace 返回
  - [x] 8.2 双向导航：单体 header 跳合并 / 合并树进单体 / 锁定标签
  - [x] 8.3 自动建树：wizard 配置合并范围步骤 + scope 变更树刷新
  - [ ] 8.4 F5 stale 感知：子公司改数 → 合并页 SSE 提示「建议重新汇总」+ 快捷入口（需求 7）
  - _需求：NFR-1.2_ _铁律：改动后必 Playwright 实测_

- [ ] 9.* 真实数据 UAT（外部依赖，待数据）
  - [ ] 9.1* 附注穿透真实子公司数据正确性 + 端到端联动；显式标"待数据"不伪绿
  - _需求：NFR-1.3_ _阻塞：PG consolidated 项目 0_

---

## 阶段 7：收尾

- [ ] 10. 文档与沉淀
  - [x] 10.1 ADR-CONSOL-301/302/303/304 落地 `docs/adr/`（注册前查编号防冲突）
  - [ ] 10.2 更新 INDEX.md + memory Phase 3 完成记录 + 合并模块 4 Phase 全貌
  - [ ] 10.3 单 commit（commit 前 git status 确认无其他 staged）
  - _铁律：单 commit / ADR 编号防冲突_

---

## 完成度判定口径

- **必需完成** = 任务 0~8 + 10（无星号）全绿。
- **可选/外部** = 任务 9（真实 UAT，卡 PG 合并数据）。
- **判定铁律**：T1~T6 全绿 + 穿透/双向导航/自动建树/F5 stale 感知 Playwright 实测；附注穿透以 V2 启用为前提（无 V2 友好提示）；标 completed 必须代码+测试证据，真实 UAT 标"待数据"不伪绿。
- **合并模块 4 Phase 全貌**：Phase 0 止血核心管线 → Phase 1 架构修复+锁定闭环+B6/B7/A3 会计正确性 → Phase 2 编排+接线+报表穿透+cross_template+公式管理+签字冻结 → Phase 3 前端联动+附注穿透+F5 stale；Phase 4 真实数据 UAT 仅 stub（卡外部集团数据）。
- **proposal 范围外显式归属**（不静默丢失）：B8 同一控制企业合并 = 独立大模块（不在本批 4 Phase）；B4 MI·商誉 verify_balance 口径 + B5/衔接3 跨年上年数 = 留 Phase 4 / 审计专业；B6/B7 会计准则修正代码在 Phase 1 但准则符合性判定标 `[ ]* 待审计专业确认`。
