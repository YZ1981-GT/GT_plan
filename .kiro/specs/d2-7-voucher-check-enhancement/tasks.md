# Implementation Plan: D2-7 凭证检查表增强

## Overview

将 D2-7 凭证检查表从单区 flat 表格升级为双区检查表（本期增减变动 + 期后收款调整）、源模板五区段对齐、卡片+矩阵双视图、行级附件 OCR+AI 核对确认回填、方法学 AI 辅助（联动 B15/B50）、审计说明统计自动化，以及双区分 sheet 导入导出。实现基于 5 个新建 composable + 主组件重构，复用现有后端端点（/d4/contract-ocr、/ai/generate-text、trial-balance、B15/B50 APIs）。

## Tasks

- [ ] 1. 核心数据层与双区状态管理
  - [ ] 1.1 创建 useD2VoucherCheckEnhanced.ts composable
    - 定义 VoucherCheckRow 接口（17列 + 元数据字段）、AttachmentMeta 接口、DualZoneState 接口
    - 实现双区数据管理：currentRows / postRows 独立 ref 数组
    - 实现 activeZone（'current' | 'post'）切换逻辑，切换时保持另一区数据不变
    - 实现 viewMode（'matrix' | 'card'）切换逻辑
    - 实现 classifyVoucherToZone(voucherDate, bsDate) 纯函数：voucherDate <= bsDate → 'current'，否则 'post'，空值默认 'current'
    - 实现行级 CRUD：addRow / removeRow / updateRow，按 activeZone 操作对应数组
    - 实现持久化：loadFromResponses（读 D2-vc-current-rows / D2-vc-post-rows JSON）、saveToResponses（写对应 item_id）
    - 实现 SampledVoucher → VoucherCheckRow 字段映射函数
    - 实现合并模式填充：mergeVoucherRows（按凭证编号去重，已有行保留 check1~check5）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.1, 10.2, 10.3_

  - [ ]* 1.2 Write property tests for zone data isolation (P1) and date classification (P2)
    - **Property 1: Zone data isolation on switch** — 编辑区A后切换到B再切回A，数据不变
    - **Property 2: Voucher date-based zone classification** — classifyVoucherToZone 纯函数正确分类
    - **Validates: Requirements 1.2, 1.5, 10.1**
    - fast-check numRuns=100

  - [ ]* 1.3 Write property tests for storage prefix isolation (P3) and view mode switch (P4)
    - **Property 3: Storage prefix isolation** — 区1 item_id 以 D2-vc-current- 开头，区2 以 D2-vc-post- 开头
    - **Property 4: View mode switch preserves data** — 切换矩阵/卡片视图不影响底层行数据
    - **Validates: Requirements 1.4, 3.4**
    - fast-check numRuns=100

  - [ ]* 1.4 Write property tests for merge deduplication (P14) and field mapping (P15)
    - **Property 14: Merge deduplication on fill** — 已有行保留 check 值，新行追加，总数正确
    - **Property 15: SampledVoucher field mapping completeness** — 每个非空源字段正确映射到目标列
    - **Validates: Requirements 10.2, 10.3**
    - fast-check numRuns=100

- [ ] 2. 方法学参数管理
  - [ ] 2.1 创建 useD2VcMethodology.ts composable
    - 定义 MethodologyState / PopulationDesc / SpecificSampleItem 接口
    - 实现从 B15 获取可容忍错报值（复用现有 API：allResponses 中 B15 底稿数据）
    - 实现从 B50 获取科目 1122 风险等级（高/中/低）
    - 实现从 trial_balance 获取科目 1122 本期借方发生额合计和交易笔数
    - 实现 AI 推荐抽样方法逻辑：风险等级 + 可容忍错报 → 推荐方法（随机/分层/MUS/特定项目）
    - 实现 MUS 样本量计算：复用 useSamplingAlgorithms.ts 的 computeMusInterval / computeSampleSize
    - 实现随机抽样样本量计算：基于总体规模 × 置信度（高→95%/中→90%/低→80%）查表
    - 实现特定样本 AI 筛选：markSpecificSamples 纯函数（金额≥可容忍错报 / 关联方 / 异常日期）
    - 实现抽样总体计算：computeSamplingPopulation = 测试总体 - 特定样本（金额和笔数同步扣除）
    - 实现样本量偏离指示器：userSampleSize vs recommendedSampleSize → 'below' | 'ok'
    - 实现 AI 生成测试总体描述（调用 /ai/generate-text，section='vc-test-population'）
    - 持久化到 D2-vc-methodology item_id
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 2.2 Write property tests for MUS sample size (P9) and random sampling (P10)
    - **Property 9: MUS sample size computation** — interval = T / reliabilityFactor(confidence, E/T); sampleSize = ceil(P / interval); 单调性
    - **Property 10: Random sampling sample size computation** — 按公式计算，随置信度单调非递减
    - **Validates: Requirements 6.3, 11.2, 11.3**
    - fast-check numRuns=100

  - [ ]* 2.3 Write property tests for specific sample marking (P11), sampling population (P12), and deviation indicator (P16)
    - **Property 11: Specific sample marking rules** — 金额≥T OR 关联方 OR 异常日期 → 标记
    - **Property 12: Sampling population arithmetic invariant** — 测试总体 - 特定样本 = 抽样总体
    - **Property 16: Sample size deviation indicator** — U < R → 'below'; U >= R → 'ok'
    - **Validates: Requirements 8.1, 8.3, 8.4, 11.5**
    - fast-check numRuns=100

- [ ] 3. OCR 识别与 AI 核对
  - [ ] 3.1 创建 useD2VcOcrCheck.ts composable
    - 定义 OcrExtractedData / CheckCompareResult 接口
    - 实现 uploadAndOcr(rowId, file)：调用 POST /d4/contract-ocr → 解析 OCR 响应 → 提取关键字段
    - 实现 OCR 字段提取纯函数 extractOcrFields(rawResponse)：解析金额（数字）、日期（归一化）、对方单位（trim）、合同编号
    - 实现 compareOcrWithRow(ocrData, row) 纯函数：金额差 < 0.01 → consistent；日期归一化后相等 → consistent；对方单位模糊相似度 > 阈值 → consistent
    - 实现 showConfirmDialog(result)：ElMessageBox 展示核对摘要，用户可逐项确认/修改
    - 实现 backfillCheckColumns(rowId, confirmed) 纯函数：check1←amountMatch / check2←dateMatch / check3←counterpartyMatch / check4←businessMatch / check5←attachmentComplete
    - 实现取消逻辑：用户取消弹窗时不修改 check 列现有值
    - OCR 服务不可用时降级：ElMessage.warning + 保留附件记录
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 3.2 Write property tests for OCR extraction (P5), comparison (P6), backfill mapping (P7), and cancel (P8)
    - **Property 5: OCR field extraction correctness** — 各种键名/值格式正确解析
    - **Property 6: OCR comparison correctness** — 金额/日期/对方单位按规则判定一致/不一致/无法判定
    - **Property 7: Check result backfill mapping** — 5 项确认结果正确映射到 check1~check5
    - **Property 8: Cancel preserves existing check values** — 取消不修改现有 check 列
    - **Validates: Requirements 4.3, 5.1, 5.2, 5.3, 5.5, 5.6**
    - fast-check numRuns=100

- [ ] 4. 审计说明统计自动化
  - [ ] 4.1 创建 useD2VcAuditSummary.ts composable
    - 定义 AuditSummaryStats 接口
    - 实现 computeAuditSummary 纯函数：从双区行数据计算 checkedAmount / checkedCount / abnormalCount / abnormalAmount / abnormalRate / coverageRatio
    - 实现从 trial_balance 获取 occurrenceAmount（科目 1122 本期发生额）
    - 实现 watch 监听双区行数据变更，2 秒 debounce 后重新计算统计指标
    - 实现 AI 生成审计说明（调用 /ai/generate-text，section='vc-audit-summary'，context 包含统计数据和异常明细）
    - 持久化到 D2-vc-audit-summary item_id
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 4.2 Write property test for audit summary statistics (P13)
    - **Property 13: Audit summary statistics correctness** — checkedAmount / abnormalCount / abnormalRate / coverageRatio 计算公式验证
    - **Validates: Requirements 9.1, 9.2**
    - fast-check numRuns=100

- [ ] 5. Checkpoint - 核心 composable 层验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. 导入导出
  - [ ] 6.1 创建 useD2VcImportExport.ts composable
    - 复用 useD2TabImportExport 模式（后端三端点：export-template / export-data / import-data）
    - 实现导出模板：生成两 sheet xlsx（"本期增减变动检查" / "期后收款调整检查"），每 sheet 17 列表头
    - 实现导出数据：两 sheet + 已填数据序列化
    - 实现导入数据：读两 sheet → 按凭证编号合并或追加到对应区
    - 缺少 sheet 时仅导入存在的 sheet 并 ElMessage.info 提示
    - 列名匹配容忍顺序不同，无法匹配的列跳过并 warn
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 6.2 Write property test for import/export round trip (P17)
    - **Property 17: Import/Export round trip** — 导出再导入后数据等价（按凭证编号 key 比较 17 列值）
    - **Validates: Requirements 12.3, 12.4**
    - fast-check numRuns=100

- [ ] 7. 主组件重构与 UI 集成
  - [ ] 7.1 重构 D2TabVoucherCheck.vue 主组件
    - 五区段容器布局：一、审计目标 el-alert → 二、方法学参数区 → 三、测试区（双区 el-tabs + 视图切换 el-segmented）→ 四、审计说明 → 五、审计结论
    - 区段一：el-alert 展示审计目标描述
    - 区段二：MethodologyPanel 方法学参数区（测试总体/特定样本/抽样总体/抽样方法/抽样程序，AI 推荐标签+理由）
    - 区段三：el-tabs（区1本期 / 区2期后）+ el-segmented（矩阵/卡片）+ 对应视图组件
    - 区段四：AuditSummaryPanel（统计指标只读字段：灰底虚线下划线+cursor:help+tooltip 来源 + AI 生成按钮）
    - 区段五：textarea + AI 辅助按钮
    - 接入 GtVoucherSamplingEngine（dialog-mode + @filled → 双区分类回填 + PostFillAiReviewDialog）
    - 接入版本工具栏 useWorkpaperVersionToolbar
    - 接入 GtIndexChip（value="wp:D2-7"）
    - selfLoad 逻辑：从 allResponses/render-config 加载持久化数据
    - 只读模式支持（isReadonly prop 传播到所有子组件）
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.5, 10.4_

  - [ ] 7.2 实现矩阵视图 MatrixView 子组件
    - el-table 17 列完整展示
    - 每行支持性文件列 📎 附件上传按钮（触发 OCR 流程）
    - 核对内容 1~5 列可编辑/显示 AI 回填结果
    - 异常列：el-select filterable allow-create（点选常见异常类型）
    - 行级 GtReviewDot
    - 计算列只读（灰底 + tooltip 来源）
    - 13px 字体，列宽 min-width 自适应
    - _Requirements: 1.3, 3.2, 4.1, 4.5_

  - [ ] 7.3 实现卡片视图 CardView 子组件
    - 每笔凭证一张 el-card：客户名称、凭证日期、凭证编号、借方/贷方金额
    - 核对状态进度条（5 项核对完成率）
    - 附件缩略图预览
    - 是否异常标记 tag
    - 点击卡片可展开编辑详情
    - _Requirements: 3.3, 4.5_

  - [ ] 7.4 实现方法学参数区 MethodologyPanel 子组件
    - 测试总体描述输入框 + AI 生成按钮
    - 特定样本列表（客户名称/金额/标记原因，逐项确认/取消）
    - 抽样总体自动计算展示（只读计算字段）
    - 抽样方法下拉选择 + AI 推荐标签（🤖 建议: ...）
    - 抽样程序描述 textarea
    - 样本量输入 + 推荐值标签 + 偏离标记（⚠️/✓）
    - 用户可覆盖 AI 推荐值
    - _Requirements: 2.3, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 11.4, 11.5_

  - [ ] 7.5 实现审计说明区 AuditSummaryPanel 子组件
    - 统计指标卡片：发生额合计 / 已检查金额 / 覆盖比例 / 异常笔数 / 异常金额 / 异常率
    - 只读计算字段样式（灰底虚线下划线 + cursor:help + tooltip 显示计算来源）
    - AI 生成审计说明按钮（section 标题行右侧）
    - 审计说明 el-card 包裹的 autosize textarea
    - 实时更新（检查表数据变更后 2 秒内刷新）
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 8. Checkpoint - UI 集成验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. 导入导出 UI 与端点接入
  - [ ] 9.1 接入导入导出 UI
    - el-dropdown "导入导出▾" 按钮（导出模板/导出数据/导入数据三项）
    - 放置于区段三工具栏右侧
    - 调用 useD2VcImportExport composable 方法
    - 导入后按凭证编号合并到对应区
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ] 10. 编制提示与辅助信息
  - [ ] 10.1 添加编制提示与方法论上下文
    - 顶部蓝色渐变引导区（操作步骤 2 列 grid：1.配置方法学参数 2.运行抽凭引擎 3.上传附件OCR核对 4.确认核对结果 5.查看统计说明）
    - 方法学区上方琥珀色方法论上下文块（CAS 1314 相关审计准则要点）
    - 底部编制提示 details 折叠（操作细节说明）
    - _Requirements: 2.1, 6.1_

- [ ] 11. Final checkpoint - 全量验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP — 但按用户偏好全部要做
- 每个 composable 的纯函数（classifyVoucherToZone / extractOcrFields / compareOcrWithRow / backfillCheckColumns / computeAuditSummary / markSpecificSamples / computeSamplingPopulation / mergeVoucherRows）独立导出，便于 PBT 直接测试
- PBT 使用 fast-check，numRuns=100
- 后端复用现有端点，无需新建后端 API
- 测试文件路径：`audit-platform/frontend/src/components/workpaper/composables/__tests__/`
- Composable 路径：`audit-platform/frontend/src/components/workpaper/composables/`
- 主组件路径：`audit-platform/frontend/src/components/workpaper/d2/`
- Property tests 标签格式：`Feature: d2-7-voucher-check-enhancement, Property {N}: {title}`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1"] },
    { "id": 3, "tasks": ["3.2", "4.1"] },
    { "id": 4, "tasks": ["4.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "7.4", "7.5"] },
    { "id": 7, "tasks": ["9.1", "10.1"] }
  ]
}
```
