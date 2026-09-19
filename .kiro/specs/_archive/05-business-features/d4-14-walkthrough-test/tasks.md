# D4-14 营业收入发生检查表（穿行测试）升级 — 任务清单

## Phase 1: Composable + 数据结构 + 一致性引擎

- [x] 1.1 创建 `useD4WalkthroughTest.ts` composable
  - [x] 1.1.1 定义 TransactionItem 类型 + 7个维度子类型 + ConsistencyResult 类型
  - [x] 1.1.2 定义 DIMENSION_GROUPS 常量（7维度字段配置）
  - [x] 1.1.3 实现 loadTransactions / addTransaction / removeTransaction / updateDimension
  - [x] 1.1.4 实现 reindexItems（add/remove后重新编号 D4-14-{N}）
  - [x] 1.1.5 实现一致性引擎纯函数: compareAmounts / compareProductNames / compareDates / computeConsistency
  - [x] 1.1.6 实现 isDimensionComplete 纯函数（判断维度是否已填完必填字段）
  - [x] 1.1.7 实现统计 computed: totalVoucherAmount / coverageRate / anomalyRate / samplingProgress
  - [x] 1.1.8 实现 debounce 2s 持久化（D4-14-transactions + D4-14-sampling + D4-14-note + D4-14-conclusion）
  - [x] 1.1.9 实现 auditNote / auditConclusion 读写
  - [x] 1.1.10 实现 mapD4ContractToDimension（D4-12合同→销售合同维度映射）
  - [x] 1.1.11 实现 mapLedgerToTransaction（序时账条目→TransactionItem映射）
  - [x] 1.1.12 实现 mapOcrToDimension（OCR extracted_fields→指定维度字段映射）
  - [x] 1.1.13 实现 collectAiContext（收集所有已填维度数据用于AI分析）

## Phase 2: 事项卡片组件（7维度 + OCR）

- [x] 2.1 创建 `D4WalkthroughCard.vue` 子组件
  - [x] 2.1.1 按 7 维度分组展示字段（el-collapse 可折叠维度区）
  - [x] 2.1.2 每维度区顶部: 维度标题 + 完整性指示(✓/×) + 📎附件上传按钮
  - [x] 2.1.3 记账凭证维度: 7字段（月份/日期/编号/品名/数量/金额/记账日期）
  - [x] 2.1.4 销售合同维度: 5字段 + "引用D4-12合同"按钮 + GtIndexChip(wp:D4-12)
  - [x] 2.1.5 出库单维度: 4字段（日期/品名/金额/仓库保管员）
  - [x] 2.1.6 运输单/签收单/发票/其他维度: 各按字段定义渲染
  - [x] 2.1.7 维度级OCR: 上传后调 /d4/contract-ocr，确认弹窗后只填该维度字段
  - [x] 2.1.8 底部: 一致性校验结果卡片（分数 + 各字段匹配状态 + 红色不一致高亮）
  - [x] 2.1.9 底部: 检查结论下拉（无异常/存在差异已解释/存在重大异常）+ AI穿行分析按钮

## Phase 3: 矩阵视图

- [x] 3.1 创建 `D4WalkthroughMatrix.vue` 子组件
  - [x] 3.1.1 el-table: rows=TransactionItem[], cols=7维度 + 一致性分数 + 结论
  - [x] 3.1.2 每维度列: ✓/× 指示器 + 金额显示 + 金额不一致警告图标
  - [x] 3.1.3 一致性分数列: 百分比 + 颜色编码（100%绿/80-99%黄/<80%红）
  - [x] 3.1.4 底部汇总: 合计金额 + 检查比例 + 异常率 + 结论分布
  - [x] 3.1.5 只读模式（无编辑交互）

## Phase 4: 主组件重写（三模式）

- [x] 4.1 重写 `D4TabOccurrence.vue`
  - [x] 4.1.1 顶部工具条: el-segmented三模式(卡片/矩阵/在线编辑) + 导入导出dropdown + GtIndexChip×3 + 复核按钮
  - [x] 4.1.2 概览横幅: 检查比例进度 + 事项数tag + 异常率tag + "添加事项"按钮(ElMessageBox.prompt)
  - [x] 4.1.3 抽样参数区: el-descriptions(总体/特定项目/抽样总体/方法/目标样本量/已检查数量+进度条)
  - [x] 4.1.4 卡片视图: el-tabs card模式 + D4WalkthroughCard per tab + 动态增删tab
  - [x] 4.1.5 矩阵视图: D4WalkthroughMatrix 组件
  - [x] 4.1.6 编制提示折叠区: 6段details（红左边线+浅红背景，默认折叠）
  - [x] 4.1.7 审计意见区: el-card(说明textarea + 结论textarea + AI辅助按钮右对齐)
  - [x] 4.1.8 OnlyOffice模式: GtOnlyOfficeSheet(sheet-name="营业收入发生检查表D4-14")
  - [x] 4.1.9 导入导出: useD4ImportExport复用（export-template/export-data/import-data）

## Phase 5: D4-12 联动 + 序时账导入

- [x] 5.1 D4-12 合同引用
  - [x] 5.1.1 读取 allResponses "D4-12-contracts-v2" 获取合同列表
  - [x] 5.1.2 "引用D4-12合同" 按钮 → el-dialog picker（表格展示合同编号/对方/金额）
  - [x] 5.1.3 选择后调 mapD4ContractToDimension 填充销售合同维度

- [x] 5.2 序时账导入
  - [x] 5.2.1 "从序时账导入" 按钮 → 调后端 `/api/projects/{pid}/auto-data/` 获取凭证数据
  - [x] 5.2.2 选择弹窗: el-table 多选（日期/凭证号/摘要/金额）
  - [x] 5.2.3 确认后批量调 mapLedgerToTransaction 创建 TransactionItem[]

## Phase 6: AI 穿行分析

- [x] 6.1 AI 穿行分析功能
  - [x] 6.1.1 单事项 AI 分析: 调 /d4/ai-generate section="walkthrough-analysis"，传 collectAiContext 结果
  - [x] 6.1.2 AI 返回展示: el-dialog 显示分析结果（交易真实性/证据链完整性/金额一致性/时间线/异常提示）
  - [x] 6.1.3 异常标记: AI识别异常时设 isAnomalous=true 并保存 aiAnalysis

- [x] 6.2 审计说明/结论 AI 辅助
  - [x] 6.2.1 审计说明 AI: section="adj-note"，传抽样参数+异常率+一致性分数汇总
  - [x] 6.2.2 审计结论 AI: section="adj-conclusion"，传说明+统计数据
  - [x] 6.2.3 确认弹窗后填入 textarea

## Phase 7: 集成 + 测试

- [x] 7.1 PBT fast-check 测试
  - [x] 7.1.1 P1: 一致性引擎字段比对正确性（amounts/productNames/dates）
  - [x] 7.1.2 P2: 一致性分数公式正确性
  - [x] 7.1.3 P3: add/remove 后 indexNo 顺序性
  - [x] 7.1.4 P4: 覆盖率/异常率/进度计算正确性
  - [x] 7.1.5 P5: 矩阵行数 = 事项数
  - [x] 7.1.6 P6: isDimensionComplete 判定正确性
  - [x] 7.1.7 P7: 持久化 JSON round-trip
  - [x] 7.1.8 P8: D4-12 合同映射正确性
  - [x] 7.1.9 P9: OCR 字段映射维度隔离性
  - [x] 7.1.10 P10: 序时账导入映射正确性
  - [x] 7.1.11 P11: AI上下文收集完整性

- [ ] 7.2 vitest 单元测试
  - [x] 7.2.1 D4WalkthroughCard: props渲染 + 7维度分组 + OCR触发
  - [x] 7.2.2 D4WalkthroughMatrix: 行数 + ✓/× 指示器 + 金额差异
  - [x] 7.2.3 D4TabOccurrence: 三模式切换 + 添加/删除 + 抽样参数
  - [x] 7.2.4 一致性引擎 edge cases（1维度不计算/全空/部分填充）
  - [x] 7.2.5 D4-12 引用picker + 序时账导入转换
