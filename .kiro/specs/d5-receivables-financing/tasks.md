# Implementation Plan: D5 应收款项融资底稿专属HTML精美组件

## Overview

实现D5应收款项融资底稿专属组件`d5-receivables-financing`。按依赖顺序：注册→公式引擎→基础设施→各sheet composable+Vue组件→后端→双模式→集成测试。主入口GtD5ReceivablesFinancing.vue + 6个子组件 + 8个composable + 后端3个py文件。科目1124借方/资产类/FVOCI，核心贴现公式：票面×利率×天数/360。

## Tasks

- [x] 1. 组件注册与基础配置
  - [x] 1.1 注册componentType和映射
    - 在 `wp_code_overrides.json` 中将D5/D5-1/D5-2/D5-3/D5-4映射为'd5-receivables-financing'
    - 在 `VALID_COMPONENT_TYPES`（wp_classification_service.py）中注册'd5-receivables-financing'
    - 在 `htmlRendererRegistry.ts` 中注册 'd5-receivables-financing' → GtD5ReceivablesFinancing 映射
    - 创建 `GtD5ReceivablesFinancing.vue` 主入口骨架（el-tabs 6个tab-pane + selfLoad逻辑）
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 1.8_

  - [x] 1.2 编写注册契约测试
    - htmlRendererRegistry.spec.ts 中验证'd5-receivables-financing'已注册
    - VALID_COMPONENT_TYPES契约验证
    - wp_code_overrides契约验证D5/D5-1/D5-2/D5-3/D5-4映射
    - _Requirements: 1.5, 1.6, 1.7_

- [x] 2. 实现共享公式引擎 useD5FormulaEngine.ts
  - [x] 2.1 创建 `composables/useD5FormulaEngine.ts`，实现全部纯函数
    - 实现 `parseNum`（安全数值解析：null/undefined/空串/NaN/Infinity → 0）
    - 实现 `calcDiscountInterest`（贴现利息 = 票面 × 利率 × 天数 ÷ 360）
    - 实现 `calcFairValue`（公允价值 = 票面 - 贴现利息）
    - 实现 `calcRemainingDays`（剩余天数 = 到期日 - 计量日）
    - 实现 `calcAuditedAmount`（审定数 = 未审 + AJE + RJE）
    - 实现 `calcChangeAmount`（变动额 = 期末 - 期初）
    - 实现 `calcChangeRate`（变动率，含期初=0特殊处理）
    - 实现 `isChangeRateExceeding`（阈值判定）
    - 实现 `calcSubtotal`（合计 = SUM数组）
    - 实现 `calcFvTotal`（公允价值合计 = 小计 - OCI变动）
    - 实现 `calcEndBalance`（期末余额 = 期初审定 + 增加 - 减少）
    - 实现 `calcEndUnadjusted`（期末未审 = 期末余额 + 重分类）
    - 实现 `calcEndAudited`（期末审定 = 期末未审 + AJE + RJE）
    - 实现 `calcImpairmentEnd`（减值期末 = 上年末 + 计提 - 转回 - 核销）
    - _Requirements: 1.4, 2.3, 2.4, 4.3, 6.2_

  - [x]* 2.2 编写 Property 1 PBT：贴现利息公式正确性
    - 生成器：`fc.float({min:0, max:1e9})` face, `fc.float({min:0, max:1})` rate, `fc.integer({min:0, max:365})` days
    - 断言：calcDiscountInterest(face, rate, days) === face * rate * days / 360
    - **Feature: d5-receivables-financing, Property 1: 贴现利息公式正确性**

  - [x]* 2.3 编写 Property 2 PBT：公允价值 = 票面 - 贴现利息
    - 生成器：`fc.float({min:0, max:1e9})` face, 导出interest = face * rate * days / 360
    - 断言：calcFairValue(face, interest) === face - interest
    - **Feature: d5-receivables-financing, Property 2: 公允价值 = 票面 - 贴现利息**

  - [x]* 2.4 编写 Property 3 PBT：审定数 = 未审 + AJE + RJE
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 3
    - 断言：calcAuditedAmount(u, a, r) === u + a + r
    - **Feature: d5-receivables-financing, Property 3: 审定数 = 未审 + AJE + RJE**

  - [x]* 2.5 编写 Property 4 PBT：公允价值合计 = 小计 - OCI变动
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 2
    - 断言：calcFvTotal(subtotal, oci) === subtotal - oci
    - **Feature: d5-receivables-financing, Property 4: 公允价值合计 = 小计 - OCI变动**

  - [x]* 2.6 编写 Property 6 PBT：合计行 = SUM(明细行)
    - 生成器：`fc.array(fc.float({min:-1e9, max:1e9}), {minLength:1, maxLength:30})`
    - 断言：calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
    - **Feature: d5-receivables-financing, Property 6: 合计行 = SUM(明细行)**

  - [x]* 2.7 编写 Property 9 PBT：变动率阈值判定
    - 生成器：`fc.float({min:-10, max:10})`
    - 断言：isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)；空串/'N/A'→false
    - **Feature: d5-receivables-financing, Property 9: 变动率阈值高亮判定**

- [x] 3. 实现 useD5FormData.ts 基础数据加载/保存
  - [x] 3.1 创建 `composables/useD5FormData.ts`
    - 实现 allResponses Map加载（GET /checklist-responses）
    - 实现 saveImmediate（PUT单条response）
    - 实现 debouncedSave（2秒debounce版本）
    - 实现 saveBatch（批量保存）
    - 实现 writebackTrialBalance（回写科目1124）
    - 实现 selfLoad逻辑（htmlData为null时调render-config?force_component_type=d5-receivables-financing）
    - _Requirements: 1.8, 12.5, 12.7, 12.8_

- [x] 4. 实现 useD5CrossSheet.ts 跨Sheet联动
  - [x] 4.1 创建 `composables/useD5CrossSheet.ts`
    - 实现 categoryAggregation computed（D5-2按类别聚合endAudited/priorAudited到应收票据/应收账款）
    - 实现 ociChange computed（OCI变动 = 小计 - D5-4公允价值合计）
    - 实现 adjustmentTotals computed（从D5-3行汇总AJE/RJE）
    - 实现 adjudicationForDisclosure computed（审定表数据供附注引用）
    - 实现 fairValueTotal computed（D5-4合计行）
    - _Requirements: 3.1, 3.2, 3.5, 8.3_

  - [x]* 4.2 编写 Property 5 PBT：跨sheet按类别聚合
    - 生成器：自定义 DetailRow[] 生成器（category随机从'应收票据'/'应收账款'取）
    - 断言：各类别sum === 手动filter+reduce结果
    - **Feature: d5-receivables-financing, Property 5: 跨sheet按类别聚合正确性**

- [x] 5. Checkpoint - 公式引擎与基础设施验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 实现 useD5Adjudication.ts 审定表D5-1
  - [x] 6.1 创建 `composables/useD5Adjudication.ts`
    - 定义固定行配置（ADJUDICATION_ROWS: 应收票据/应收账款/小计/减:OCI变动/FV合计/TB数/差异）
    - 实现 rows computed（从allResponses加载 + crossSheet聚合填入 + 公式计算）
    - 实现 trialBalanceAmount（从TB auto_data取数科目1124）+ trialBalanceDiff computed
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - 实现 updateCell（编辑 → 公式重算 → debouncedSave）
    - 实现 publishAdjudicated（EventBus: substantive:adjudicated，payload含1124/auditedAmount）
    - 实现 onAdjustmentCreated监听（AJE/RJE累加）
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率
    - _Requirements: 2.1-2.8, 3.1-3.7, 11.1, 11.2_

- [x] 7. 实现 useD5Detail.ts 明细表D5-2
  - [x] 7.1 创建 `composables/useD5Detail.ts`
    - 定义 DetailRow 类型（17列完整字段 A~Q）
    - 实现 rows reactive（从D5-2-rows加载JSON数组）
    - 实现行内公式自动计算（F=C+D+E, J=F+H-I, L=J+K, O=L+M+N）
    - 实现 subtotalByCategory computed（应收票据小计/应收账款小计）+ totalRow computed
    - 实现 addRow/removeRow/updateCell
    - 实现 importFromD1（EventBus请求D1出售模式票据）
    - 实现 importFromD2（EventBus请求D2出售模式账款）
    - 实现 importFromAuxBalance（调后端API从tb_aux_balance科目1124导入）
    - 对"类别"列应用下拉选择（应收票据/应收账款）
    - _Requirements: 4.1-4.9, 5.1-5.7_

  - [x]* 7.2 编写 Property 10 PBT：D5-2行公式链
    - 生成器：`fc.float({min:-1e9, max:1e9})` × 8 (C,D,E,H,I,K,M,N)
    - 断言：F=C+D+E; J=F+H-I; L=J+K; O=L+M+N
    - **Feature: d5-receivables-financing, Property 10: D5-2行内公式链正确性**

  - [x]* 7.3 编写 Property 7 PBT：动态行添加
    - 生成器：`fc.array(DetailRow生成器, {minLength:0, maxLength:20})`
    - 断言：addRow后length=N+1；新行数值全0
    - **Feature: d5-receivables-financing, Property 7: 动态行添加保持结构不变量**

- [x] 8. 实现 useD5FairValue.ts 公允价值测算D5-4
  - [x] 8.1 创建 `composables/useD5FairValue.ts`
    - 定义 FairValueRow 类型（13列 A~M）
    - 实现 rows reactive（从D5-4-rows加载JSON数组）
    - 实现行内公式自动计算（G=F-E天数差, I=D×H×G÷360, J=D-I, K=J）
    - 实现 totalRow computed（票面合计/贴现利息合计/公允价值合计）
    - 实现 ociDiffMessage computed（D5-4 FV合计 vs D5-2期末合计差异提示文案）
    - 实现 addRow/removeRow/updateCell
    - 实现 setDefaultRate（全表统一默认利率，用户可逐行覆盖）
    - 实现 measurementDate默认填充period_end
    - 实现 fvHierarchy下拉（第二层次/第三层次）+ tooltip判定规则
    - 实现 auditNotes 双向绑定（explanation/conclusion）
    - _Requirements: 6.1-6.10_

- [x] 9. 实现 useD5Adjustment.ts 调整分录D5-3
  - [x] 9.1 创建 `composables/useD5Adjustment.ts`
    - 定义 AdjustmentRow 类型（10列）
    - 实现 rows reactive（从D5-3-rows加载JSON）
    - 实现 debitTotal/creditTotal/isBalanced/balanceDiff computed
    - 实现 addRow/removeRow/updateCell
    - 实现 publishAdjustment（EventBus adjustment:created，payload含wpCode='D5'/entryType/amount）
    - 实现 pushToA13（EventBus推送选中分录至A13错报汇总）
    - _Requirements: 7.1-7.6_

  - [x]* 9.2 编写 Property 8 PBT：借贷平衡
    - 生成器：`fc.array(fc.record({debit:fc.float({min:0,max:1e9}), credit:fc.float({min:0,max:1e9})}))`
    - 断言：isBalanced === (debitTotal === creditTotal)
    - **Feature: d5-receivables-financing, Property 8: 调整分录借贷平衡检查**

- [x] 10. 实现 useD5Disclosure.ts 附注披露
  - [x] 10.1 创建 `composables/useD5Disclosure.ts`
    - 上市公司版：3子节（分类/减值准备变动/说明）+ 从crossSheet取数 + 动态行(减值)
    - 国企版：1子节（分类）+ 从crossSheet取数
    - 实现 impairmentRows（减值准备变动动态行：上年末/计提/转回/核销/期末=公式）
    - 实现 applicable_standards 适用性判断（listed/soe显示控制）
    - 实现 activeVariant（el-segmented切换）
    - 实现 noteTexts 双向绑定 + EventBus disclosure:note-text-updated
    - _Requirements: 8.1-8.8_

- [x] 11. Checkpoint - 全部composable验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. 实现 D5TabProcedure.vue 程序表
  - [x] 12.1 创建 `d5/D5TabProcedure.vue`（~200行）
    - 复用 GtAProgramConsole componentType（selfLoad：force_component_type=a-program-console）
    - GtIndexChip跳转：D5-1/D5-2/D1-6/D2-13/D0/D1-7/D1-10/D5-4/A1-1/A1-15/A1-16
    - EventBus监听risk:updated更新程序步骤状态
    - _Requirements: 9.1-9.6_

- [x] 13. 实现 D5TabAdjudication.vue 审定表
  - [x] 13.1 创建 `d5/D5TabAdjudication.vue`（~400行）
    - el-table固定行结构（7行）
    - 列：项目|期初(未审/AJE/RJE/审定)|期末(未审/AJE/RJE/审定)|变动额|变动率
    - "减:OCI变动"行浅蓝背景 + tooltip"取自D5-4公允价值测算"
    - 跨sheet自动取数单元格浅蓝色标记
    - 变动率>30%红色高亮 + 差异≠0红色高亮
    - 试算平衡表数行 + 差异行
    - "审计说明"区域：textarea + 🤖AI按钮 + GtIndexChip(→D5-4, →D1-6)
    - "审计结论"区域：textarea + 🤖AI按钮
    - 💬复核入口 + 右键@cell-contextmenu
    - 金额fmtAmount + el-segmented双模式
    - _Requirements: 2.1-2.8, 3.4, 3.6, 3.7, 10.4-10.6_

- [x] 14. 实现 D5TabDetail.vue 明细表
  - [x] 14.1 创建 `d5/D5TabDetail.vue`（~350行）
    - el-table横向滚动17列，固定前2列（类别/明细项目）
    - "类别"下拉（应收票据/应收账款）
    - 自动计算列灰底不可编辑（F/J/L/O）
    - "添加明细行"按钮 + 行删除 + 按类别小计行 + 总合计行（不可编辑）
    - "从D1导入(出售模式票据)"按钮 + "从D2导入(出售模式账款)"按钮
    - "从余额表导入"按钮 + "导出空模板"/"导入数据"
    - GtIndexChip：应收票据行→D1-6，应收账款行→D2-13
    - 金额右对齐 + fmtAmount + 零值"-" + 负数红色括号
    - 超30行虚拟滚动
    - "审计说明"textarea + 🤖AI + 💬复核
    - el-segmented双模式
    - _Requirements: 4.1-4.9, 5.1-5.7, 10.9_

- [x] 15. 实现 D5TabFairValue.vue 公允价值测算
  - [x] 15.1 创建 `d5/D5TabFairValue.vue`（~400行）
    - el-table 13列
    - 自动计算列灰底（G/I/J/K）
    - "公允价值层次"下拉（第二层次/第三层次）+ tooltip判定规则
    - "市场贴现利率"列：全表默认利率配置 + 逐行可覆盖
    - "计量日"列默认填充period_end
    - 合计行：票面合计/贴现利息合计/公允价值合计
    - OCI差异提示（黄色el-alert："D5-4公允价值合计≠D5-2期末审定合计，差额=OCI变动：±xxx元"）
    - "添加测算行"按钮 + 行删除
    - "审计说明"textarea + 🤖AI（评价贴现利率合理性+层次判定依据）
    - "审计结论"textarea
    - "市场贴现利率"列右键复核入口（sectionId: D5-4-discount-rate）
    - GtIndexChip：公允价值层次→附注披露
    - el-segmented双模式
    - _Requirements: 6.1-6.10, 10.7_

- [x] 16. 实现 D5TabAdjustment.vue 调整分录
  - [x] 16.1 创建 `d5/D5TabAdjustment.vue`（~250行）
    - el-table 10列 + "新增调整分录"按钮
    - 底部借贷合计行 + 平衡指示（绿色✓平衡/红色✗不平衡：差额xxx）
    - "推送至A13"按钮（多选行）
    - 编制提示details折叠（蓝色左边线+浅蓝背景，默认收起）
    - el-segmented双模式
    - _Requirements: 7.1-7.7_

- [x] 17. 实现 D5TabDisclosure.vue 附注披露
  - [x] 17.1 创建 `d5/D5TabDisclosure.vue`（~300行）
    - el-segmented切换（"上市公司版" | "国企版"）
    - 上市公司版：3子节卡片（分类/减值变动/说明）
    - 国企版：1子节卡片（分类）
    - 跨sheet浅蓝色取数 + tooltip来源
    - 减值准备变动：动态行 + 公式（期末=上年末+计提-转回-核销）
    - 每子节"说明"textarea（双向回写附注模块 EventBus）+ 编制提示折叠
    - 按applicable_standards自动显示/隐藏版本
    - el-segmented双模式（结构化视图/在线编辑）
    - _Requirements: 8.1-8.8_

- [x] 18. Checkpoint - 全部Vue组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. 实现后端导入导出端点
  - [x] 19.1 创建 `backend/app/routers/wp_render_strategies/_d5_import_export.py`
    - POST /api/workpapers/{wp_id}/d5/export-template?sheet=D5-2|D5-4（空白xlsx模板）
    - POST /api/workpapers/{wp_id}/d5/export-data?sheet=D5-2|D5-4（含数据xlsx）
    - POST /api/workpapers/{wp_id}/d5/import-data?sheet=D5-2|D5-4（解析xlsx回写）
    - POST /api/workpapers/{wp_id}/d5/import-aux-balance（从tb_aux_balance科目1124导入）
    - 格式校验：列名不匹配→400+错误列表
    - 注册路由到router_registry
    - _Requirements: 5.5, 5.6, 14.1_

  - [x]* 19.2 编写 Property 11 PBT（后端hypothesis）：导入导出Round-Trip
    - 生成随机DetailRow[]/FairValueRow[]→export→import→验证等价
    - 模板格式校验：随机列名→验证错误检测
    - **Feature: d5-receivables-financing, Property 11: 导入导出Round-Trip**

- [x] 20. 实现后端Resolver和AI生成端点
  - [x] 20.1 创建 `backend/app/routers/wp_render_strategies/_d5_resolvers.py`
    - 注册`d5_tb_unadjusted` resolver到_REGISTRY（从trial_balance科目1124取期初/期末未审数）
    - _Requirements: 14.3, 11.1_

  - [x] 20.2 创建 `backend/app/routers/wp_render_strategies/_d5_ai_generate.py`
    - POST /api/workpapers/{wp_id}/d5/ai-generate 端点
    - 支持5个section（adj-explanation/adj-conclusion/detail-change/fv-rate-analysis/fv-conclusion）
    - 自动加载D5-1变动数据 + D5-4测算结果 + 业务模式判断 + project_context作为LLM context
    - 注册到router_registry "AI与辅助"组
    - _Requirements: 11.4-11.7_

  - [x] 20.3 实现后端render策略函数和account_package_registry更新
    - 在RENDERER_DISPATCH注册'd5-receivables-financing'→`_render_d5_receivables_financing`策略函数
    - 实现`_render_d5_receivables_financing`返回审定表OCI结构+明细表行数据+FV测算行数据+各sheet配置
    - 更新account_package_registry.json添加D5_receivables_financing工作包（含7个有效sheet：D5A/D5-1/D5-2/D5-3/D5-4/附注上市/附注国企）
    - 读取D5.yaml render schema生成初始结构化数据
    - _Requirements: 14.1, 14.2, 14.4, 14.5_

- [x] 21. 集成主入口与双模式切换
  - [x] 21.1 完善 GtD5ReceivablesFinancing.vue 主入口
    - el-tabs 6个tab-pane引用6个子组件
    - Tab顺序对齐源模板sheet顺序：D5A→D5-1→D5-2→D5-3→D5-4→附注
    - 传递allResponses/wpId/projectId/isReadonly/crossSheet等props
    - provide openReviewDialog（inject模式零成本集成复核）
    - _Requirements: 1.1, 1.2, 13.5_

  - [x] 21.2 在所有子组件中实现HTML ↔ OnlyOffice双模式切换
    - 每个Tab页头部el-segmented（"结构化视图"|"在线编辑"）
    - 切OO：获取onlyoffice-config → GtOnlyOfficeSheet → 隐藏非当前sheet(SetVisible(false))
    - 切回HTML：重新加载checklist_responses刷新
    - OO不可用时禁用+tooltip
    - _Requirements: 12.1-12.4_

- [x] 22. Checkpoint - 后端与双模式验证
  - Ensure all tests pass, ask the user if questions arise.

- [x] 23. 回归测试与全量验证
  - [x] 23.1 运行全量测试确保无回归
    - vitest run 所有D5相关spec文件
    - python -m pytest backend/tests/ -k d5
    - 验证htmlRendererRegistry注册数量更新
    - 验证VALID_COMPONENT_TYPES含'd5-receivables-financing'
    - 验证wp_code_overrides D5/D5-1/D5-2/D5-3/D5-4映射正确
    - 验证RENDERER_DISPATCH含'd5-receivables-financing'策略
    - 验证auto_data_resolvers._REGISTRY含d5_tb_unadjusted
    - 验证account_package_registry含D5工作包7个sheet
    - _Requirements: all_

- [x] 24. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional PBT tests
- 每个Property对应design.md中的一个correctness property
- 所有PBT使用fast-check（前端）或hypothesis（后端），numRuns: 100
- 借方科目核心公式：期末余额 = 期初审定 + 本期增加 - 本期减少
- 贴现公式：贴现利息 = 票面 × 利率 × 天数 / 360；公允价值 = 票面 - 贴现利息
- 跨sheet全部通过allResponses computed链，不走API调用
- selfLoad必须支持（bundle内嵌场景htmlData为null）
- 程序表D5A复用a-program-console componentType，不需单独实现公式
- D5特色：审定表"减:OCI公允价值变动"行是扣减项（非D1/D2模式的简单合计）
- D5来源交叉：D1票据出售模式 + D2应收账款出售模式 → D5-2明细
- 公允价值层次：可观察输入值(银行公布贴现利率)→第二层次；不可观察→第三层次
- AI生成端点复用B14/A17-1模式：project_context + 底稿数据snapshot + CPA system prompt
- 附注上市(21公式)比附注国企(8公式)复杂：含减值准备变动子节（动态行+公式）
