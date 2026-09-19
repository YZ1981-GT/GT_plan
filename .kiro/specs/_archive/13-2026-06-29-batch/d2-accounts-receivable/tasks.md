# Tasks — D2 应收账款专属组件

## 1. 注册与配置

- [x] 1.1 更新 `wp_code_overrides.json`：D2→`d2-accounts-receivable`，D2-1→`skip`，D2-3→`skip`，D2-4→`skip`（D2-2/D2-5/D2-6 保留 `audit-sheet`）
  - 验证 D2 底稿打开时渲染专属组件，D2-1/D2-3/D2-4 不独立渲染
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [x] 1.2 在 `htmlRendererRegistry.ts` 注册 `d2-accounts-receivable` 条目
  - componentType=`d2-accounts-receivable`, icon='💰', label='D2 应收账款', emits=['save','completed'], contextProps='standard'
  - 添加 lazy import: `defineAsyncComponent(() => import('./GtD2AccountsReceivable.vue'))`
  - _Requirements: 1.1, 1.9_

- [x] 1.3 后端 `wp_classification_service.py` VALID_COMPONENT_TYPES 白名单新增 `d2-accounts-receivable`
  - _Requirements: 1.1_

## 2. 数据层 Composable

- [x] 2.1 创建 `composables/useD2FormData.ts` — 数据加载/保存/辅助
  - 实现 `loadAll()` 从 GET checklist-responses 加载 `D2-*` 数据到 allResponses Map
  - 实现 `saveImmediate(items)` 通过 PUT 批量保存（结论/状态/选择类字段触发）
  - 实现 `saveDebouncedText(item)` debounce 2000ms 文本保存
  - 实现 `flushPendingSave()` 组件卸载时 flush 未保存数据
  - 实现 `getField(itemId)` / `setFieldImmediate(itemId, data)` 辅助方法
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

- [x] 2.2 实现 trial_balance 回写逻辑
  - `writebackTrialBalance(accountCode, auditedAmount)` 通过 API 回写 audited_amount
  - 初始化时从 trial_balance 获取 unadjusted_amount 作为审定表未审数初始值（科目 1122）
  - _Requirements: 3.7, 10.2, 10.7_

- [x] 2.3 实现子底稿数据读取（D2-2 SUMIF 源数据）
  - `loadSubWorkpaperData(subWpCode)` 读取 D2-2 的 audit-sheet 数据
  - 提供 sumifValues 计算属性：按 AI 列分类（"单项计提"/"账龄组合"/"客户类型组合"）聚合 S/Z/AA 列
  - _Requirements: 3.2, 3.3, 3.4, 3.9_

## 3. 核心逻辑 Composable

- [x] 3.1 创建 `composables/useD2AccountsReceivable.ts` 基础框架
  - Tab 管理：activeTab + setActiveTab + tabCompletionStatus
  - localStorage 持久化最后访问 Tab
  - linkageRefs 联动面板数据（5 个 ref_chip：→trial_balance/→D0函证/→B50风险/→C3控制/→A13错报）
  - _Requirements: 2.1, 2.5, 2.7, 10.6_

- [x] 3.2 审定表 D2-1 SUMIF 联动计算逻辑
  - adjudicationRows 计算属性（6行：单项计提/账龄组合/客户类型组合/坏账准备/账面价值/合计）
  - SUMIF 聚合：F8←SUMIF(D2-2!AI,"单项计提",S列) / F10←SUMIF(AI,"账龄组合",S列) / F11←SUMIF(AI,"客户类型组合",S列)，G/H 列同理(Z/AA列)
  - getAuditedAmount: 审定数 = 期末未审数 + AJE + RJE
  - getChangeRate: 变动率三分支（期初=0且审定数=0→''、期初=0→1、其他→(审定数-期初)/期初）
  - refreshSumifData 刷新 D2-2 SUMIF 源数据
  - confirmationSummary 函证汇总信息显示区
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.9_

- [x] 3.3 程序表 D2A 逻辑
  - procedureSteps 计算属性（7 步：获取并核对明细/核对总账/函证/替代程序/坏账准备/截止测试/结论）
  - setProcedureStatus / setProcedureConclusion 状态管理
  - procedureProgress 完成度计算（已完成+不适用 / 7）
  - canInputOverallConclusion：全部必要步骤完成后允许录入整体结论
  - overallConclusion 整体审计结论
  - riskIndicators 风险标识（来自 B50 监听）
  - "已完成"步骤校验必须有结论
  - ref_chip 跳转关联 Tab 映射（函证→D0、坏账→D2-9 Tab 等）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 3.4 ECL 坏账准备逻辑
  - badDebtMethod 三方式切换（单项计提/账龄组合/客户类型组合）
  - agingBands 6 档账龄段数据（1年以内/1-2年/2-3年/3-4年/4-5年/5年以上）
  - migrationRateMatrix 迁徙率矩阵输入
  - calculateExpectedLossRate：各阶段平均迁徙率连乘
  - calculateProvision：余额 × 预期损失率
  - calculateDifference：实际计提 − 应计提
  - isDifferenceExceedsMateriality：对比 B15 重要性水平
  - eclSummary 汇总（总余额/应计提/实际计提/总差异/是否超重要性）
  - 坏账汇总回传审定表 D2-1 坏账准备行
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

- [x] 3.5 截止测试逻辑
  - cutoffTestSamples CRUD（addCutoffSample/removeCutoffSample/updateCutoffSample）
  - determineCutoff(revDate, bsDate)：收入确认日在资产负债表日之后→跨期=true
  - hasCutoffErrors：存在跨期样本时为 true（触发红色提示）
  - 截止测试区域嵌入程序表"截止测试"步骤内
  - _Requirements: 7.4, 7.5, 7.6_

- [x] 3.6 保理分析逻辑
  - factoringItems CRUD（addFactoring/removeFactoring/updateFactoring）
  - 区分两类：质押（限制性资产）与保理出售（终止确认判断）
  - factoringDerecognitionJudge(transferRisk, retainControl)：终止确认判断辅助
  - factoringSummary 汇总（已质押合计/已保理合计/终止确认金额/不终止确认金额）
  - pledgeRatio = 已质押金额 / 应收账款总额（T=0 时返回 0）
  - isPledgeRatioWarning：比例 >50% 触发警告
  - 条目上限 100 条
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

- [x] 3.7 函证联动逻辑
  - 监听 D0 函证模块的 `confirmation:completed` 事件
  - onConfirmationCompleted：接收函证确认结果（发函数/回函数/回函率/确认金额/差异金额）
  - confirmationSummary 显示汇总信息
  - 函证差异标注到审定表对应客户行
  - 替代程序记录区：对未回函客户记录替代审计程序执行情况
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 3.8 分析程序逻辑
  - analysisRatios 计算属性：应收账款周转率/周转天数/上期周转天数/变化率/坏账率/上期坏账率
  - isTurnoverDaysWarning：周转天数同比变化超过 30% 时触发高亮警告
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 3.9 关联方检查逻辑
  - matchedRelatedParties：从项目已录入关联方清单自动匹配应收账款客户名称
  - 关联方金额超重要性水平时标记警告
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 3.10 附注披露逻辑
  - disclosureTemplate：根据项目属性自动选择（上市/国企/一般）
  - disclosureItems 检查清单（结论：已披露且准确/已披露但需修改/未披露需补充/不适用）
  - hasUndisclosedItems：存在"未披露需补充"时触发红色提醒
  - 检查结论汇总到程序表第 7 步（结论步骤）
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 3.11 调整分录逻辑
  - adjustmentEntries CRUD（addAdjustment/removeAdjustment/updateAdjustment）
  - ajeTotal = Σ(type='AJE' entries)，rjeTotal = Σ(type='RJE' entries)
  - 审定表双向同步：分录增删改→自动更新审定表 AJE/RJE 调整列
  - "推送至 A13"操作：通过 EventBus 发布 adjustment:created
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 3.12 EventBus 联动
  - 发布 `substantive:adjudicated`（审定数变更时，载荷含 wpCode="D2"/accountCode="1122"/auditedAmount/priorAmount/changeRate）
  - 发布 `adjustment:created`（新增调整分录时，载荷含分录信息）
  - 监听 `risk:assessed`（B50 风险等级→程序表 riskIndicators）
  - 监听 `control:test-concluded`（C3 销售与收款循环控制结论→程序表提示）
  - 监听 `confirmation:completed`（D0 函证完成→函证汇总更新）
  - 组件卸载时注销监听
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.8_

- [x] 3.13 检查表通用逻辑
  - D2-7 应收账款通用检查（账龄分析合理性/大额异常/长期挂账/期后回款）
  - D2-8 会计政策一致性检查（是否变更/变更原因/影响金额）
  - D2-11 转回核销检查
  - D2-13 业务模式分析检查
  - 每项结论选择：符合/不符合/不适用 + 备注
  - 发现汇总到程序表对应步骤"审计发现"字段
  - _Requirements: 9.4, 9.5, 9.6_

- [x] 3.14 截止测试日期校验与边界处理
  - 日期格式校验（无效格式前端拒绝输入）
  - bsDate 从项目 year 参数自动推导（默认 {year}-12-31）
  - 跨期样本计数 + 整体截止测试结论
  - _Requirements: 7.5, 7.6_

## 4. 复核 Composable

- [x] 4.1 创建 `composables/useD2Review.ts`
  - isReviewed / isReadonly / canReview / pendingItems 计算属性
  - canReview：所有 isRequired=true 的程序步骤为"已完成"或"不适用"
  - doReview()：签字保存 + 全组件只读
  - startAmendment(reason)：填写原因→解锁编辑→需重新复核
  - readonly 模式：外部 prop 或已复核→全禁用
  - reviewInfo：复核人/日期信息
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

## 5. Vue 组件实现

- [x] 5.1 创建 `GtD2AccountsReceivable.vue` 主组件骨架
  - script setup + Props(wpId/projectId/wpCode/year/readonly) + Emits(save/completed)
  - 引入 3 个 composables 并初始化
  - el-tabs 17 Tab 框架（底稿目录→业务模式D2-13）
  - onMounted: loadAll + loadSubWorkpaperData(D2-2) + 从 trial_balance 获取初始值
  - onBeforeUnmount: flushPendingSave + 注销 EventBus 监听
  - _Requirements: 1.9, 1.10, 2.1_

- [x] 5.2 程序表 Tab 渲染
  - 7 步审计程序卡片（步骤名/描述/执行人/日期/底稿索引/发现/结论）
  - 状态 badge（未开始/执行中/已完成/不适用 颜色编码）
  - 进度条 N/7
  - 风险标识（来自 B50 risk:assessed）
  - ref_chip 跳转到关联 Tab（函证→D0、坏账→D2-9、截止→截止测试区域）
  - 整体结论区域（全部必要步骤完成后可录入）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 5.3 审定表 Tab 渲染
  - 表格结构：行(单项计提/账龄组合/客户类型组合/坏账准备/账面价值/合计) × 列(期初未审/期末未审/SUMIF期初/SUMIF变动/SUMIF期末/AJE/RJE/审定数/变动率)
  - SUMIF 引用高亮（D2-2 引用单元格标识）
  - 公式自动计算（审定数/变动率实时更新）
  - 函证汇总信息区（发函数/回函数/回函率/确认金额/差异金额）
  - displayPrefs.fmtAmount 格式化金额
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 6.2_

- [x] 5.4 坏账准备 Tab 渲染
  - 坏账计提方式切换（单项/账龄组合/客户类型组合 el-radio-group）
  - 迁徙率矩阵输入表格
  - 账龄段明细表（6 档 × 列：期初/计提/转回/核销/期末/损失率/应计提/实际计提/差异）
  - 应计提 vs 实际计提差异高亮
  - 差异超 B15 重要性水平红色提示
  - eclSummary 汇总区域
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 5.5 ECL 测算 Tab 渲染（D2-9）
  - 测算方法选择（迁徙率法/组合评估/个别认定）
  - 迁徙率矩阵编辑面板
  - 各账龄段计算结果展示
  - 输入参数和假设记录区
  - _Requirements: 5.3, 5.9_

- [x] 5.6 计量测试 Tab 渲染（D2-10）
  - 模型输入参数表格
  - 关键假设记录
  - 测试结果比对：预期/实际/差异/是否可接受
  - _Requirements: 5.9_

- [x] 5.7 截止测试 Tab 渲染
  - 截止测试样本 CRUD 表格（发票号/收入确认日期/应收入账日期/金额/是否跨期/结论/备注）
  - 跨期自动判定（日期比较）
  - 存在跨期样本时红色提示"存在截止错误，需评估影响"
  - _Requirements: 7.4, 7.5, 7.6_

- [x] 5.8 保理分析 Tab 渲染（D2-12）
  - 质押/保理明细表 CRUD（客户名称/金额/质押对象或保理商/合同编号/起止日期/终止确认/备注）
  - 类别区分：质押 vs 保理
  - 终止确认判断辅助面板（转移风险Y/N + 保留控制Y/N→自动判断结果）
  - "不终止确认"行提示"应继续在资产负债表确认，同时确认相关负债"
  - 汇总区（已质押合计/已保理合计/终止确认/不终止确认金额/质押比例）
  - 质押比例 >50% 黄色警告"大额质押，需关注流动性和披露"
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

- [x] 5.9 函证联动 Tab 渲染
  - 函证汇总区：发函数/回函数/回函率/确认金额/差异金额
  - 逐客户函证结果列表（客户名/状态/发函金额/确认金额/差异）
  - 差异行红色标注"函证差异"
  - 替代程序记录区（对未回函客户）
  - ref_chip 跳转→D0 函证底稿
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 5.10 分析程序 Tab 渲染
  - 使用 GtWpRenderer 懒加载 D2-5（audit-sheet 模式）
  - 关键比率展示面板：周转率/周转天数/账龄分布变化/坏账率趋势
  - 周转天数变化 >30% 高亮提示"周转效率显著变化，需关注原因"
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 5.11 关联方 Tab 渲染
  - 使用 GtWpRenderer 懒加载 D2-6（audit-sheet 模式）
  - 自动匹配面板（从项目关联方清单匹配客户名称）
  - 金额超重要性水平红色警告"重大关联方应收账款，需充分披露"
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 5.12 检查表 Tab 渲染（D2-7/D2-8/D2-11/D2-13）
  - D2-7 应收账款通用检查表：账龄分析/大额异常/长期挂账/期后回款
  - D2-8 ECL 会计政策一致性检查（变更/原因/影响）
  - D2-11 转回核销检查
  - D2-13 业务模式分析
  - 每项结论选择：符合/不符合/不适用 + 备注
  - _Requirements: 9.4, 9.5, 9.6_

- [x] 5.13 附注披露 Tab 渲染
  - 上市公司/国企子切换（根据项目类型默认选中）
  - 上市公司检查清单（分类/坏账变动三方式/质押/保理/前五名/关联方/账龄/期后回款/政策）
  - 国企检查清单（国资委格式）
  - 结论选择（已披露且准确/已披露但需修改/未披露需补充/不适用）
  - "未披露需补充"项红色提醒
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [x] 5.14 调整分录 Tab 渲染
  - 分录明细 CRUD（类型AJE/RJE/借方科目/贷方科目/金额/摘要/是否已过入审定表）
  - AJE 合计 / RJE 合计
  - "推送至 A13"按钮（触发 EventBus adjustment:created）
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_

- [x] 5.15 子底稿 Tab 渲染（D2-2/D2-5/D2-6）
  - 使用 GtWpRenderer 懒加载（audit-sheet 模式）
  - D2-2 明细表（按客户/账龄双维度）
  - D2-5 分析程序子底稿
  - D2-6 关联方子底稿
  - 子底稿不存在时占位提示
  - _Requirements: 2.3, 2.7_

- [x] 5.16 底稿目录 Tab + GT_Custom Tab
  - 底稿目录 Tab：20 sheet 清单 + 状态总览
  - GT_Custom Tab：自定义扩展 sheet
  - _Requirements: 2.1_

- [x] 5.17 联动面板
  - ref_chip 跳转：→trial_balance、→D0 函证、→B50 风险评估、→C3 控制测试、→A13 错报汇总
  - 各链接显示当前状态
  - _Requirements: 10.6_

- [x] 5.18 复核签字区
  - 程序表下方"现场经理复核"区域
  - 签字按钮（前置条件不满足时禁用 + 显示 pendingItems）
  - 签字后：全组件只读 + emit completed + 顶部"已复核"绿色横幅
  - Amendment：填写修改原因→解锁→重新复核
  - readonly prop / 已复核 → 全 Tab 禁用
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

## 6. 后端白名单

- [x] 6.1 `checklist_responses.py` 新增 D2- 前缀分支
  - allowed tuple 包含所有合法 conclusion 值（未开始/执行中/已完成/不适用/符合/不符合/单项计提/账龄组合/客户类型组合/终止确认/不终止确认/已披露且准确/已披露但需修改/未披露需补充/组合评估/个别认定/Y/N/是/否/跨期/未跨期）
  - conclusion 不在 allowed 内时 raise HTTPException 422
  - remark 字段不做限制
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

## 7. Checkpoint

- [x] 7.1 确保所有组件代码编译无错误，TypeScript 类型检查通过
  - getDiagnostics 验证 composables + Vue 组件无报错
  - 确认 VALID_COMPONENT_TYPES 包含 `d2-accounts-receivable`
  - 确认 wp_code_overrides.json 映射正确
  - 确保所有 tests pass，如有疑问询问用户

## 8. Property-Based Tests（fast-check）

- [x]* 8.1 Property 1: 审定表公式计算不变式
  - 生成随机期末未审数/AJE/RJE/期初 → 验证 审定数 = I+AJE+RJE，变动率三分支逻辑
  - **Property 1: 审定表公式计算不变式**
  - **Validates: Requirements 3.5, 3.6**

- [ ]* 8.2 Property 2: SUMIF 跨 sheet 引用一致性
  - 生成随机 D2-2 行数组（AI∈{单项计提,账龄组合,客户类型组合}, S/Z/AA∈float）→ 验证 sumif 聚合等于过滤后求和
  - **Property 2: SUMIF 跨 sheet 引用一致性**
  - **Validates: Requirements 3.2, 3.3, 3.4, 3.9**

- [ ]* 8.3 Property 3: ECL 迁徙率法计算正确性
  - 生成随机迁徙率数组(1~6阶段,∈[0,1]) × 随机余额(≥0) → 验证 lossRate=连乘, provision=余额×rate, diff=actual-should
  - **Property 3: ECL 迁徙率法计算正确性**
  - **Validates: Requirements 5.3, 5.4, 5.5**

- [ ]* 8.4 Property 4: 质押比例计算正确性
  - 生成随机 P(≥0) × T(≥0) → 验证 ratio=P/T(T>0), ratio=0(T=0), warning=(ratio>0.5)
  - **Property 4: 质押比例计算正确性**
  - **Validates: Requirements 8.6, 8.7**

- [ ]* 8.5 Property 5: 截止测试跨期判定一致性
  - 生成随机 revDate/bsDate 日期对 → 验证 isCutoff = (revDate > bsDate)
  - **Property 5: 截止测试跨期判定一致性**
  - **Validates: Requirements 7.5, 7.6**

- [ ]* 8.6 Property 6: trial_balance 回写一致性
  - 生成随机 auditedAmount → writebackTrialBalance → 验证回读值一致（科目 1122）
  - **Property 6: trial_balance 回写一致性**
  - **Validates: Requirements 10.2, 10.7**

- [ ]* 8.7 Property 7: 数据持久化往返一致性
  - 生成随机 D2- item_id + conclusion(白名单内) + remark → PUT → GET → 验证一致
  - **Property 7: 数据持久化往返一致性**
  - **Validates: Requirements 11.6**

- [ ]* 8.8 Property 8: item_id 命名唯一性与确定性
  - 生成随机 (sheet × 序号 × 字段) 组合 ×2 → 验证不同组合→不同 id，相同组合→相同 id，均以 D2- 前缀开头
  - **Property 8: item_id 命名唯一性与确定性**
  - **Validates: Requirements 11.7**

- [ ]* 8.9 Property 9: 程序表完成度与复核前置条件
  - 生成随机 7 步状态(∈{未开始,执行中,已完成,不适用}) → 验证 canReview = 所有 isRequired 步骤为已完成/不适用
  - **Property 9: 程序表完成度与复核前置条件**
  - **Validates: Requirements 4.6, 12.2**

- [ ]* 8.10 Property 10: EventBus 事件发射正确性
  - 生成随机 oldAmount/newAmount → 验证 old≠new 时发射 substantive:adjudicated(wpCode="D2",accountCode="1122")，old=new 时不发射
  - **Property 10: EventBus 事件发射正确性**
  - **Validates: Requirements 10.1, 10.5**

- [ ]* 8.11 Property 11: 调整分录与审定表双向同步
  - 生成随机分录数组(0~20条,type∈{AJE,RJE},amount≥0) → 验证 AJE合计=Σ(AJE), RJE合计=Σ(RJE)
  - **Property 11: 调整分录与审定表双向同步**
  - **Validates: Requirements 15.3, 15.5**

- [ ]* 8.12 Property 12: 后端白名单校验正确性
  - 生成随机 D2- item_id + conclusion(合法/非法混合) → 验证合法→200，非法→422
  - **Property 12: 后端白名单校验正确性**
  - **Validates: Requirements 13.1, 13.2, 13.4**

- [ ]* 8.13 Property 13: Tab 完成状态一致性
  - 生成随机 checklist_responses 子集(conclusion/remark 有/无) → 验证状态判定：无数据→not-started，部分→in-progress，全部→completed
  - **Property 13: Tab 完成状态一致性**
  - **Validates: Requirements 2.6**

## 9. Unit Tests（vitest）

- [ ]* 9.1 注册契约测试
  - 验证 htmlRendererRegistry 包含 `d2-accounts-receivable`
  - 验证 wp_code_overrides D2→d2-accounts-receivable, D2-1/D2-3/D2-4→skip, D2-2/D2-5/D2-6→audit-sheet
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [ ]* 9.2 Tab 渲染测试
  - 17 Tab 标签文本 + 顺序正确
  - 附注 Tab 子切换（上市公司/国企）
  - Tab 切换 + localStorage 记忆
  - 懒加载行为验证
  - _Requirements: 2.1, 2.2, 2.5, 2.7_

- [ ]* 9.3 审定表 SUMIF 计算测试
  - 审定数公式验证（多组数据）
  - 变动率三分支验证
  - SUMIF 聚合值正确计算（mock D2-2 数据按分类过滤求和）
  - displayPrefs.fmtAmount 格式化
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8_

- [ ]* 9.4 程序表测试
  - 7 步渲染 + 状态切换 + 已完成必须有结论
  - 进度条 N/7
  - ref_chip 跳转
  - 风险标识（mock risk:assessed）
  - 整体结论录入（全必要步骤完成后可录入）
  - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.8_

- [ ]* 9.5 ECL 坏账准备测试
  - 坏账方式三切换（单项/账龄/客户类型）
  - 迁徙率矩阵输入 + 损失率显示
  - 差异超重要性水平高亮
  - 坏账汇总回传审定表
  - _Requirements: 5.1, 5.2, 5.3, 5.6, 5.7_

- [ ]* 9.6 截止测试测试
  - 样本 CRUD
  - 跨期自动判定（revDate > bsDate → 跨期）
  - 存在跨期样本时红色提示
  - 日期格式校验
  - _Requirements: 7.4, 7.5, 7.6_

- [ ]* 9.7 保理分析测试
  - 明细 CRUD + 终止确认判断辅助
  - "不终止确认"提示文本
  - 汇总数据正确（质押合计/保理合计/终止确认/不终止确认）
  - 质押比例计算 + >50% 警告
  - 条目上限 100 校验
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [ ]* 9.8 函证联动测试
  - D0 函证完成事件监听 + 汇总数据更新
  - 函证差异标注
  - 替代程序记录
  - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [ ]* 9.9 分析程序测试
  - 关键比率计算
  - 周转天数变化 >30% 警告
  - _Requirements: 7.2, 7.3_

- [ ]* 9.10 关联方测试
  - 自动匹配 + 超重要性水平警告
  - _Requirements: 9.2, 9.3_

- [ ]* 9.11 附注披露测试
  - 上市/国企子切换
  - 结论选择 + "未披露需补充"红色提醒
  - 汇总到程序表第 7 步
  - _Requirements: 14.1, 14.2, 14.4, 14.5, 14.6_

- [ ]* 9.12 调整分录测试
  - CRUD + AJE/RJE 合计
  - 审定表同步（新增分录→调整列更新，删除→清除）
  - 推送 A13 按钮触发 EventBus
  - _Requirements: 15.1, 15.3, 15.4, 15.5, 15.6_

- [ ]* 9.13 EventBus 联动测试
  - substantive:adjudicated 发射时机 + 载荷正确（wpCode="D2", accountCode="1122"）
  - adjustment:created 发射 + 载荷
  - risk:assessed 监听 + riskIndicators 更新
  - control:test-concluded 监听 + 程序表提示（C3 销售与收款）
  - confirmation:completed 监听 + 函证汇总更新
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.8_

- [ ]* 9.14 保存行为测试
  - debounce 2s（fake timers）
  - 结论/状态即时保存
  - emit save
  - 保存失败不回滚
  - _Requirements: 11.2, 11.3, 11.4_

- [ ]* 9.15 复核签字测试
  - 前置条件校验（pendingItems 显示）
  - 签字 + emit completed + 只读
  - 已复核绿色横幅
  - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ]* 9.16 Amendment 测试
  - 启动修改→原因校验→解锁→重新复核
  - _Requirements: 12.6_

- [ ]* 9.17 readonly 模式测试
  - prop readonly / 已复核 → 全 Tab 禁用
  - _Requirements: 12.5_

- [ ]* 9.18 子底稿 Tab 测试
  - D2-2/D2-5/D2-6 GtWpRenderer lazy 渲染
  - 子底稿不存在时占位
  - _Requirements: 2.3_

- [ ]* 9.19 Tab 完成状态测试
  - 状态标记实时更新
  - 绿色勾/蓝色点/灰色正确对应
  - _Requirements: 2.6_

- [ ]* 9.20 检查表通用测试
  - D2-7/D2-8/D2-11/D2-13 结论选择
  - 发现汇总到程序表
  - _Requirements: 9.4, 9.5, 9.6_

## 10. 后端 PBT（hypothesis）

- [ ]* 10.1 Property 7: 数据持久化往返一致性
  - D2- item_id + 合法 conclusion + 随机 remark → PUT → GET → 一致
  - **Property 7: 数据持久化往返一致性**
  - **Validates: Requirements 11.6**

- [ ]* 10.2 Property 12: 后端白名单校验正确性
  - D2- item_id + 随机 conclusion（合法/非法混合）→ 合法 200 / 非法 422
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
- D2 相对 D1 的差异：SUMIF 三分类聚合（非简单跨sheet引用）、截止测试（3.5+3.14）、保理分析（替代背书贴现）、函证联动（替代贴息计算）、分析程序（替代监盘倒推）、程序表 7 步（非 8 步）、科目 1122（非票据科目）、联动面板 5 ref_chip（多→D0函证）
- 总计：41 必做任务 + 35 optional 测试任务 = 76 任务
