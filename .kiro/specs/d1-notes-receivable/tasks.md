# Tasks — D1 应收票据专属组件

## 1. 注册与配置

- [x] 1.1 更新 `wp_code_overrides.json`：D1→`d1-notes-receivable`，D1-1→`skip`，D1-4→`skip`（D1-2/D1-3 保留 `audit-sheet`）
  - 验证 D1 底稿打开时渲染专属组件，D1-1/D1-4 不独立渲染
  - _Requirements: 1.2, 1.3, 1.4, 1.5_

- [x] 1.2 在 `htmlRendererRegistry.ts` 注册 `d1-notes-receivable` 条目
  - componentType=`d1-notes-receivable`, icon='📄', label='D1 应收票据', emits=['save','completed'], contextProps='standard'
  - 添加 lazy import: `defineAsyncComponent(() => import('./GtD1NotesReceivable.vue'))`
  - _Requirements: 1.1, 1.8_

- [x] 1.3 后端 `wp_classification_service.py` VALID_COMPONENT_TYPES 白名单新增 `d1-notes-receivable`
  - _Requirements: 1.1_

## 2. 数据层 Composable

- [x] 2.1 创建 `composables/useD1FormData.ts` — 数据加载/保存/辅助
  - 实现 `loadAll()` 从 GET checklist-responses 加载 `D1-*` 数据到 allResponses Map
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存（结论/状态/选择类字段触发）
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存
  - 实现 `flushPendingSave()` 组件卸载时 flush 未保存数据
  - 实现 `getField(itemId)` / `setFieldImmediate(itemId, data)` 辅助方法
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

- [x] 2.2 实现 trial_balance 回写逻辑
  - `writebackTrialBalance(accountCode, auditedAmount)` 通过 API 回写 audited_amount
  - 初始化时从 trial_balance 获取 unadjusted_amount 作为审定表未审数初始值
  - _Requirements: 3.7, 10.2, 10.7_

- [x] 2.3 实现子底稿数据读取（D1-2/D1-3 跨 sheet 引用）
  - `loadSubWorkpaperData(subWpCode)` 读取 D1-2/D1-3 的 audit-sheet 数据
  - 提供 crossSheetValues 计算属性供审定表使用
  - _Requirements: 3.2, 3.3, 3.4, 3.9_

## 3. 核心逻辑 Composable

- [x] 3.1 创建 `composables/useD1NotesReceivable.ts` 基础框架
  - Tab 管理：activeTab + setActiveTab + tabCompletionStatus
  - localStorage 持久化最后访问 Tab
  - linkageRefs 联动面板数据
  - _Requirements: 2.1, 2.5, 2.7, 10.6_

- [x] 3.2 审定表 D1-1 计算逻辑
  - adjudicationRows 计算属性（4行：银行承兑/商业承兑/坏账准备/账面价值）
  - getAuditedAmount: 审定数 = 未审数 + AJE借 - AJE贷 + RJE借 - RJE贷
  - getChangeRate: 变动率三分支（期初=0且审定数=0→''、期初=0→1、其他→(审定数-期初)/期初）
  - crossSheetValues 引用 D1-2/D1-4 数据（B8←D1-2!B14 等映射）
  - refreshCrossSheetData 刷新跨 sheet 数据
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.9_

- [x] 3.3 程序表 D1A 逻辑
  - procedureSteps 计算属性（8 步：获取明细/核对总账/票据验真/到期分析/背书贴现/减值评估/披露检查/结论）
  - setProcedureStatus / setProcedureConclusion 状态管理
  - procedureProgress 完成度计算（已完成+不适用 / 总数）
  - canInputOverallConclusion：全部必要步骤完成后允许录入整体结论
  - overallConclusion 整体审计结论
  - riskIndicators 风险标识（来自 B50 监听）
  - "已完成"步骤校验必须有结论
  - ref_chip 跳转关联 Tab 映射
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 3.4 ECL 坏账准备逻辑
  - eclMethod 切换（组合评估/个别认定）
  - agingBands 6 档账龄段数据
  - migrationRateMatrix 迁徙率矩阵输入
  - calculateExpectedLossRate：各阶段平均迁徙率连乘
  - calculateProvision：余额 × 预期损失率
  - calculateDifference：实际计提 − 应计提
  - isDifferenceExceedsMateriality：对比 B15 重要性水平
  - eclSummary 汇总（总余额/应计提/实际计提/总差异/是否超重要性）
  - 坏账汇总回传审定表 D1-1 坏账准备行
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [x] 3.5 业务模式分析逻辑
  - maturityAnalysis：按到期日分 4 组（未到期/≤30/31-90/>90）+ 金额和占比
  - sppiTestResult：Y/N/null
  - businessModelChoice：3 种业务模式选择
  - suggestedClassification：SPPI+业务模式→分类建议
  - hasOverdue90Plus：是否存在逾期 90 天以上（触发红色警告）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 3.6 背书贴现逻辑
  - endorsementItems CRUD（addEndorsement/removeEndorsement）
  - 终止确认判断字段（DerecognitionResult）
  - endorsementSummary 汇总（已背书未到期/已贴现未到期/终止确认金额/不终止确认金额）
  - 条目上限 100 条
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 3.7 贴息计算逻辑
  - discountInterestItems CRUD
  - calculateInterest(P, R, D) = P × R × D / 360
  - 差异 = 被审计单位贴息 − 审计师复核贴息
  - 差异超限高亮
  - _Requirements: 7.5, 7.6, 7.7_

- [x] 3.8 监盘倒推逻辑
  - inventoryReconciliation 数据管理
  - calculateBSDateBalance = 盘点日余额 + 期间增加 − 期间减少
  - inventoryDifference = 账面余额 − 倒推余额
  - 差异超 100% 警告
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 3.9 质押检查逻辑
  - pledgeItems CRUD
  - pledgeTotalAmount / pledgeRatio 自动汇总
  - isPledgeRatioWarning：比例 >50% 触发警告
  - _Requirements: 8.4, 8.5, 8.6, 8.7_

- [x] 3.10 关联方检查逻辑
  - relatedPartyItems CRUD
  - matchedRelatedParties：从项目已录入关联方清单自动匹配票据出票人/承兑人
  - 关联方金额超重要性水平时标记警告
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 3.11 附注披露逻辑
  - disclosureTemplate：根据项目属性自动选择（上市/国企/一般）
  - disclosureItems 检查清单（结论：已披露且准确/已披露但需修改/未披露需补充/不适用）
  - hasUndisclosedItems：存在"未披露需补充"时触发红色提醒
  - 检查结论汇总到程序表第 7 步
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 3.12 调整分录逻辑
  - adjustmentEntries CRUD（addAdjustment/removeAdjustment/updateAdjustment）
  - ajeTotal = Σ(type='AJE' entries)，rjeTotal = Σ(type='RJE' entries)
  - 审定表双向同步：分录增删改→自动更新审定表 AJE/RJE 调整列
  - "推送至 A13"操作：通过 EventBus 发布 adjustment:created
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 3.13 EventBus 联动
  - 发布 `substantive:adjudicated`（审定数变更时，载荷含 wpCode/accountCode/auditedAmount/priorAmount/changeRate）
  - 发布 `adjustment:created`（新增调整分录时，载荷含分录信息）
  - 监听 `risk:assessed`（B50 风险等级→程序表 riskIndicators）
  - 监听 `control:test-concluded`（C2 控制结论→程序表提示）
  - 组件卸载时注销监听
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

## 4. 复核 Composable

- [x] 4.1 创建 `composables/useD1Review.ts`
  - isReviewed / isReadonly / canReview / pendingItems 计算属性
  - canReview：所有 isRequired=true 的程序步骤为"已完成"或"不适用"
  - doReview()：签字保存 + 全组件只读
  - startAmendment(reason)：填写原因→解锁编辑→需重新复核
  - readonly 模式：外部 prop 或已复核→全禁用
  - reviewInfo：复核人/日期信息
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

## 5. Vue 组件实现

- [x] 5.1 创建 `GtD1NotesReceivable.vue` 主组件骨架
  - script setup + Props(wpId/projectId/wpCode/year/readonly) + Emits(save/completed)
  - 引入 3 个 composables 并初始化
  - el-tabs 18 Tab 框架（底稿目录→转回核销）
  - onMounted: loadAll + loadSubWorkpaperData + 从 trial_balance 获取初始值
  - onBeforeUnmount: flushPendingSave + 注销 EventBus 监听
  - _Requirements: 1.6, 1.7, 2.1_

- [x] 5.2 程序表 Tab 渲染
  - 8 步审计程序卡片（步骤名/描述/执行人/日期/底稿索引/发现/结论）
  - 状态 badge（未开始/执行中/已完成/不适用 颜色编码）
  - 进度条 N/8
  - 风险标识（来自 B50 risk:assessed）
  - ref_chip 跳转到关联 Tab
  - 整体结论区域（全部必要步骤完成后可录入）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 5.3 审定表 Tab 渲染
  - 表格结构：行(银行承兑/商业承兑/坏账准备/账面价值) × 列(期初/期末/变动/AJE/RJE/审定数/变动率)
  - 跨 sheet 引用高亮（D1-2/D1-4 引用单元格标识）
  - 公式自动计算（审定数/变动率实时更新）
  - displayPrefs.fmtAmount 格式化金额
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8_

- [x] 5.4 坏账准备 Tab 渲染
  - ECL 方法切换（组合评估/个别认定 el-radio-group）
  - 迁徙率矩阵输入表格
  - 账龄段明细表（6 档 × 8 列）
  - 应计提 vs 实际计提差异高亮
  - 差异超 B15 重要性水平红色提示
  - eclSummary 汇总区域
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 5.5 业务模式 Tab 渲染
  - 到期分析分组（4 组金额+占比）
  - SPPI 检查清单（Y/N + 说明）
  - 业务模式分类选择
  - 分类建议提示面板
  - 逾期 90 天以上红色警告
  - 分析提示参考面板
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 5.6 背书贴现 Tab 渲染
  - 明细表 CRUD（票据编号/出票人/金额/到期日/背书日/受让人/终止确认/备注）
  - 终止确认判断辅助选择
  - "不终止确认"行提示"应作为表外事项披露"
  - 汇总区（已背书未到期/已贴现未到期/终止确认/不终止确认金额）
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 5.7 贴息 Tab 渲染
  - 贴息检查表 CRUD（贴现金额/贴现率/天数/被审计单位贴息/审计师复核/差异）
  - 公式自动计算 P×R×D/360
  - 差异超限高亮
  - _Requirements: 7.5, 7.6, 7.7_

- [x] 5.8 监盘 Tab 渲染
  - 倒推表（盘点日余额 + 期间增加 − 期间减少 = BS日余额）
  - 差异 = 账面余额 − 倒推余额
  - 差异标红 + 超 100% 黄色警告
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 5.9 质押 Tab 渲染
  - 质押清单 CRUD（票据编号/金额/质押对象/用途/解质押日/是否限制性）
  - 质押比例汇总
  - 比例 >50% 黄色警告"大额质押，需关注流动性和披露"
  - _Requirements: 8.4, 8.5, 8.6_

- [x] 5.10 关联方 Tab 渲染
  - 关联方清单 CRUD（名称/关系类型/金额/票据编号/正常商业条款/备注）
  - 自动匹配面板（从项目关联方清单匹配出票人/承兑人）
  - 金额超重要性水平红色警告
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 5.11 检查表 Tab 渲染（D1-13/D1-14/D1-15/D1-16）
  - 通用检查项列表（检查事项 + 结论选择：符合/不符合/不适用 + 备注）
  - D1-14 ECL 会计政策一致性检查
  - D1-15 ECL 测试数据
  - D1-16 转回核销检查
  - _Requirements: 9.4, 9.5, 5.8_

- [x] 5.12 附注披露 Tab 渲染
  - 上市公司/国企子切换（根据项目类型默认选中）
  - 上市公司检查清单（分类/坏账变动/质押/背书/贴现/前五名/关联方/政策）
  - 国企检查清单（国资委格式）
  - 结论选择（已披露且准确/已披露但需修改/未披露需补充/不适用）
  - "未披露需补充"项红色提醒
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 5.13 调整分录 Tab 渲染
  - 分录明细 CRUD（类型/借方科目/贷方科目/金额/摘要/是否已过入审定表）
  - AJE 合计 / RJE 合计
  - "推送至 A13"按钮（触发 EventBus adjustment:created）
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 5.14 子底稿 Tab 渲染（D1-2/D1-3）
  - 使用 GtWpRenderer 懒加载（audit-sheet 模式）
  - D1-2 原值明细表（按类别）
  - D1-3 原值明细表（按客户）
  - 子底稿不存在时占位提示
  - _Requirements: 2.3, 2.7_

- [x] 5.15 底稿目录 Tab + 备查簿核对 Tab + 分析提示
  - 底稿目录 Tab：21 sheet 清单 + 状态总览
  - 备查簿核对 Tab（D1-7）：核对检查项
  - 分析提示面板：业务模式分析提示指导内容
  - _Requirements: 2.1, 6.6_

- [x] 5.16 联动面板
  - ref_chip 跳转：→trial_balance、→B50 风险评估、→C2 控制测试、→A13 错报汇总
  - 各链接显示当前状态
  - _Requirements: 10.6_

- [x] 5.17 复核签字区
  - 程序表下方"现场经理复核"区域
  - 签字按钮（前置条件不满足时禁用 + 显示 pendingItems）
  - 签字后：全组件只读 + emit completed + 顶部"已复核"绿色横幅
  - Amendment：填写修改原因→解锁→重新复核
  - readonly prop / 已复核 → 全 Tab 禁用
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [x] 5.18 Tab 完成状态标记
  - 每个 Tab 标签显示完成状态：绿色勾(completed) / 蓝色点(in-progress) / 灰色(not-started)
  - 状态判定实时反映底层 checklist_responses 数据变化
  - _Requirements: 2.6_

## 6. 后端白名单

- [x] 6.1 `checklist_responses.py` 新增 D1- 前缀分支
  - allowed tuple 包含所有合法 conclusion 值（未开始/执行中/已完成/不适用/符合/不符合/以摊余成本计量/以公允价值计量且变动计入其他综合收益/以公允价值计量且变动计入当期损益/终止确认/不终止确认/已披露且准确/已披露但需修改/未披露需补充/组合评估/个别认定/Y/N）
  - conclusion 不在 allowed 内时 raise HTTPException 422
  - remark 字段不做限制
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

## 7. Checkpoint

- [x] 7.1 确保所有组件代码编译无错误，TypeScript 类型检查通过
  - getDiagnostics 验证 composables + Vue 组件无报错
  - 确认 VALID_COMPONENT_TYPES 包含 `d1-notes-receivable`
  - 确认 wp_code_overrides.json 映射正确
  - 确保所有 tests pass，如有疑问询问用户

## 8. Property-Based Tests（fast-check）

- [x]* 8.1 Property 1: 审定表公式计算不变式
  - 生成随机未审数/AJE借贷/RJE借贷/期初 → 验证 审定数 = C+E-F+G-H，变动率三分支逻辑
  - **Property 1: 审定表公式计算不变式**
  - **Validates: Requirements 3.5, 3.6**

- [x]* 8.2 Property 2: 跨 sheet 引用一致性
  - 生成随机 D1-2/D1-4 源值 → 设置源值 → 验证审定表目标单元格始终等于源值
  - **Property 2: 跨 sheet 引用一致性**
  - **Validates: Requirements 3.2, 3.3, 3.4, 3.9**

- [x]* 8.3 Property 3: ECL 迁徙率法计算正确性
  - 生成随机迁徙率数组(1~6阶段,∈[0,1]) × 随机余额(≥0) → 验证 lossRate=连乘, provision=余额×rate, diff=actual-should
  - **Property 3: ECL 迁徙率法计算正确性**
  - **Validates: Requirements 5.3, 5.4, 5.5**

- [x]* 8.4 Property 4: 贴息计算正确性
  - 生成随机 P(≥0) × R(∈[0,1]) × D(0~365整数) → 验证 interest = P×R×D/360
  - **Property 4: 贴息计算正确性**
  - **Validates: Requirements 7.6**

- [x]* 8.5 Property 5: 监盘倒推一致性
  - 生成随机盘点日余额(≥0)/期间增加(≥0)/期间减少(≥0) → 验证 bsDate = A+B-C
  - **Property 5: 监盘倒推一致性**
  - **Validates: Requirements 8.2**

- [x]* 8.6 Property 6: trial_balance 回写一致性
  - 生成随机 auditedAmount → writebackTrialBalance → 验证回读值一致
  - **Property 6: trial_balance 回写一致性**
  - **Validates: Requirements 3.7, 10.2**

- [x]* 8.7 Property 7: 数据持久化往返一致性
  - 生成随机 D1- item_id + conclusion(白名单内) + remark → PUT → GET → 验证一致
  - **Property 7: 数据持久化往返一致性**
  - **Validates: Requirements 11.6**

- [x]* 8.8 Property 8: item_id 命名唯一性与确定性
  - 生成随机 (sheet × 序号 × 字段) 组合 ×2 → 验证不同组合→不同 id，相同组合→相同 id，均以 D1- 前缀开头
  - **Property 8: item_id 命名唯一性与确定性**
  - **Validates: Requirements 11.7**

- [x]* 8.9 Property 9: 程序表完成度与复核前置条件
  - 生成随机 8 步状态(∈{未开始,执行中,已完成,不适用}) → 验证 canReview = 所有 isRequired 步骤为已完成/不适用
  - **Property 9: 程序表完成度与复核前置条件**
  - **Validates: Requirements 4.6, 12.2**

- [x]* 8.10 Property 10: EventBus 事件发射正确性
  - 生成随机 oldAmount/newAmount → 验证 old≠new 时发射 substantive:adjudicated，old=new 时不发射
  - **Property 10: EventBus 事件发射正确性**
  - **Validates: Requirements 10.1, 10.5**

- [x]* 8.11 Property 11: 调整分录与审定表双向同步
  - 生成随机分录数组(0~20条,type∈{AJE,RJE},amount≥0) → 验证 AJE合计=Σ(AJE), RJE合计=Σ(RJE)
  - **Property 11: 调整分录与审定表双向同步**
  - **Validates: Requirements 15.3, 15.5**

- [x]* 8.12 Property 12: 后端白名单校验正确性
  - 生成随机 D1- item_id + conclusion(合法/非法混合) → 验证合法→200，非法→422
  - **Property 12: 后端白名单校验正确性**
  - **Validates: Requirements 13.1, 13.2, 13.4**

- [x]* 8.13 Property 13: Tab 完成状态一致性
  - 生成随机 checklist_responses 子集(conclusion/remark 有/无) → 验证状态判定：无数据→not-started，部分→in-progress，全部→completed
  - **Property 13: Tab 完成状态一致性**
  - **Validates: Requirements 2.6**

## 9. Unit Tests（vitest）

- [x]* 9.1 注册契约测试
  - 验证 htmlRendererRegistry 包含 `d1-notes-receivable`
  - 验证 wp_code_overrides D1→d1-notes-receivable, D1-1→skip, D1-4→skip, D1-2/D1-3→audit-sheet
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x]* 9.2 Tab 渲染测试
  - 18 Tab 标签文本 + 顺序正确
  - Tab 切换 + localStorage 记忆
  - 懒加载行为验证
  - _Requirements: 2.1, 2.5, 2.7_

- [x]* 9.3 审定表计算测试
  - 审定数公式验证（多组数据）
  - 变动率三分支验证
  - 跨 sheet 引用正确更新
  - displayPrefs.fmtAmount 格式化
  - _Requirements: 3.1, 3.5, 3.6, 3.8_

- [x]* 9.4 程序表测试
  - 8 步渲染 + 状态切换 + 已完成必须有结论
  - 进度条 N/8
  - ref_chip 跳转
  - 风险标识（mock risk:assessed）
  - 整体结论录入（全必要步骤完成后可录入）
  - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x]* 9.5 ECL 坏账准备测试
  - ECL 方法切换
  - 迁徙率矩阵输入 + 损失率显示
  - 差异超重要性水平高亮
  - 坏账汇总回传审定表
  - _Requirements: 5.1, 5.2, 5.3, 5.6, 5.7_

- [x]* 9.6 业务模式测试
  - SPPI 检查 Y/N
  - 业务模式分类选择 + 分类建议
  - 逾期 90 天以上红色警告
  - 到期分析分组金额+占比
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x]* 9.7 背书贴现测试
  - 明细 CRUD + 终止确认判断
  - "不终止确认"提示文本
  - 汇总数据正确
  - 条目上限 100 校验
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x]* 9.8 贴息测试
  - P×R×D/360 公式正确
  - 差异超限高亮
  - _Requirements: 7.5, 7.6, 7.7_

- [x]* 9.9 监盘测试
  - 倒推公式 A+B-C
  - 差异标红
  - 超 100% 警告
  - _Requirements: 8.1, 8.2, 8.3_

- [x]* 9.10 质押测试
  - CRUD + 比例汇总
  - >50% 黄色警告
  - _Requirements: 8.4, 8.5, 8.6_

- [x]* 9.11 关联方测试
  - CRUD + 自动匹配
  - 超重要性水平警告
  - _Requirements: 9.1, 9.2, 9.3_

- [x]* 9.12 附注披露测试
  - 上市/国企子切换
  - 结论选择 + "未披露需补充"红色提醒
  - 汇总到程序表第 7 步
  - _Requirements: 14.1, 14.2, 14.4, 14.5, 14.6_

- [x]* 9.13 调整分录测试
  - CRUD + AJE/RJE 合计
  - 审定表同步（新增分录→调整列更新，删除→清除）
  - 推送 A13 按钮触发 EventBus
  - _Requirements: 15.1, 15.3, 15.4, 15.5, 15.6_

- [x]* 9.14 EventBus 联动测试
  - substantive:adjudicated 发射时机 + 载荷正确
  - adjustment:created 发射 + 载荷
  - risk:assessed 监听 + riskIndicators 更新
  - control:test-concluded 监听 + 程序表提示
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x]* 9.15 保存行为测试
  - debounce 2s（fake timers）
  - 结论/状态即时保存
  - emit save
  - 保存失败不回滚
  - _Requirements: 11.2, 11.3, 11.4_

- [x]* 9.16 复核签字测试
  - 前置条件校验（pendingItems 显示）
  - 签字 + emit completed + 只读
  - 已复核绿色横幅
  - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [x]* 9.17 Amendment 测试
  - 启动修改→原因校验→解锁→重新复核
  - _Requirements: 12.6_

- [x]* 9.18 readonly 模式测试
  - prop readonly / 已复核 → 全 Tab 禁用
  - _Requirements: 12.5_

- [x]* 9.19 子底稿 Tab 测试
  - D1-2/D1-3 GtWpRenderer lazy 渲染
  - 子底稿不存在时占位
  - _Requirements: 2.3_

- [x]* 9.20 Tab 完成状态测试
  - 状态标记实时更新
  - 绿色勾/蓝色点/灰色正确对应
  - _Requirements: 2.6_

## 10. 后端 PBT（hypothesis）

- [x]* 10.1 Property 7: 数据持久化往返一致性
  - D1- item_id + 合法 conclusion + 随机 remark → PUT → GET → 一致
  - **Property 7: 数据持久化往返一致性**
  - **Validates: Requirements 11.6**

- [x]* 10.2 Property 12: 后端白名单校验正确性
  - D1- item_id + 随机 conclusion（合法/非法混合）→ 合法 200 / 非法 422
  - **Property 12: 后端白名单校验正确性**
  - **Validates: Requirements 13.1, 13.2, 13.4**

## 11. Final Checkpoint

- [x] 11.1 确保所有测试通过，如有疑问询问用户
  - vitest 单元测试 + fast-check property tests 全绿
  - hypothesis 后端 PBT 全通过
  - getDiagnostics 验证 TypeScript 编译无错误
  - 验证 componentType 契约测试通过（htmlRendererRegistry.spec.ts）
  - 验证 wp_code_overrides 映射无冲突

## Notes

- 任务 1~7 + 11 为必做任务（核心功能），不标星号
- 任务 8~10 为测试任务（optional），标星号 `*`
- 每个任务按依赖顺序排列：注册→数据层→逻辑层→复核→UI→后端→测试
- Property tests 每个 property 单独子任务，标注 property 编号和对应 requirements
- Checkpoints（7.1 + 11.1）确保增量验证
- 总计：41 必做任务 + 35 optional 测试任务 = 76 任务
