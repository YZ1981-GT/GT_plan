# Implementation Plan: 通用抽凭引擎组件

## Overview

实现通用抽凭引擎组件，从 tb_ledger 按5种审计抽样方法自动提取凭证填充到抽凭底稿。按依赖顺序实现：后端抽样算法 → API端点 → 前端纯函数 → composable → Vue组件 → D2集成 → PBT测试。无需新建DB迁移（复用 V095 workpaper_extraction_log）。

## Tasks

- [x] 1. 后端抽样算法模块
  - [x] 1.1 创建 `backend/app/services/voucher_sampling_algorithms.py`（~300行）
    - 定义类型：SamplingMethod（Literal 5种）、StratumConfig（dataclass）、SamplingParams（dataclass）、SamplingResult（dataclass）
    - 实现 `execute_sampling(method, population, params, seed)` 分发函数
    - 若 seed 为 None 则 `seed = random.randint(0, 2**31)`，记录到 SamplingResult.seed_used
    - 实现 `_random_sampling(population, n, rng)` — `rng.sample(population, min(n, len(population)))`
    - 实现 `_stratified_sampling(population, strata, rng)` — 按 GREATEST(debit,credit) 分层 + 每层 rng.sample
    - 实现 `_specific_item_sampling(population, threshold)` — filter GREATEST >= threshold
    - 实现 `_systematic_sampling(population, start, interval)` — 按 voucher_date+voucher_no 排序后取 indices
    - 实现 `_mus_sampling(population, sample_size, rng)` — 累积金额法 PPS，负数取 abs
    - 实现 `_compute_coverage(population, sample)` — 计算笔数覆盖率+金额覆盖率
    - 金额使用 Decimal，GREATEST = max(COALESCE(debit,0), COALESCE(credit,0))
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.12, 12.1, 12.2_

- [x] 2. 后端抽凭 API 端点
  - [x] 2.1 创建 `backend/app/routers/voucher_sampling.py`（~250行）
    - 定义 Pydantic 模型：VoucherExtractRequest（sampling_method、sampling_params JSON、random_seed、phase、filters、workpaper_id）
    - `POST /api/projects/{pid}/sampling/voucher-extract`：
      - 从 filters 构建 LedgerQueryFilters（period_range → date_start/date_end、amount_min/max → amount_threshold）
      - exclude_extracted=true 时查 workpaper_extraction_log WHERE extraction_type='voucher_sampling' 获取已抽凭证号
      - phase='final' 时自动追加预审已抽凭证号到 exclude_voucher_nos
      - 调用 LedgerSamplingService.build_ledger_query + execute_with_stats 获取 population
      - 调用 execute_sampling 执行抽样算法
      - 返回 {items, stats, seed_used, truncated}（超500截断）
    - `GET /api/projects/{pid}/sampling/voucher-history?wp_id=` — 查 extraction_type='voucher_sampling' 按 created_at DESC
    - `POST /api/projects/{pid}/sampling/voucher-undo?log_id=` — 验证最新非 undone + 标记 is_undone + 返回 before_data
    - `POST /api/projects/{pid}/sampling/voucher-compare` — 接收 log_id_a/log_id_b，从 extraction_criteria 或 before_data 取凭证号集合，计算 added/removed/retained
    - 注册到 router_registry
    - _Requirements: 2.2, 2.3, 2.5, 3.1, 3.2, 3.11, 6.3, 6.4, 8.1, 8.2, 13.1, 13.2, 13.3, 13.4, 13.5, 14.1, 14.2_

- [x] 3. Checkpoint - 后端服务验证
  - Ensure service unit tests pass, router registered. Ask user if questions arise.

- [x] 4. 前端抽样展示纯函数
  - [x] 4.1 创建 `composables/useSamplingAlgorithms.ts`（~200行）
    - 导出类型：SamplingMethod、Phase、FillMode、CheckResult、StratumConfig、SamplingConfig、SampledVoucher、EditTrailEntry、CoverageStats、ComplianceWarning
    - 实现 `computeCoverage(populationCount, populationAmount, sampleCount, sampleAmount)` — 返回 CoverageStats
    - 实现 `checkCAS1314Compliance(stats, method, sampleCount, totalCount)` — 返回 ComplianceWarning[]
      - 金额覆盖率 < 60% → warning
      - specific_item 占比 > 50% → suggestion
      - MUS sample_size < expected → warning
    - 实现 `validateSamplingConfig(config)` — 按 method 校验必填参数，返回 errors Record
    - 实现 `computeVersionDiff(vouchersA, vouchersB)` — 按 voucher_no 计算 added/removed/retained
    - _Requirements: 8.3, 12.1, 12.2, 6.3_

  - [x] 4.2 创建 `composables/useSamplingPhase.ts`（~150行）
    - 导出类型：ViewMode
    - 实现 `useSamplingPhase(options: PhaseOptions)`
    - visibleSamples computed：按 viewMode 过滤 samples
    - isRowEditable(row)：当前 phase='final' 且 row.phase='preliminary' → false
    - isFillModeRestricted：phase='final' → true（强制 append）
    - getPreliminaryVoucherNos()：返回 phase='preliminary' 的全部 voucher_no
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 9.4_

- [x] 5. 实现 useVoucherSampling.ts composable
  - [x] 5.1 创建 `composables/useVoucherSampling.ts`（~500行）
    - 定义接口：VoucherSamplingOptions、ExtractionLogEntry、CompareResult
    - 实现 config 响应式初始化（从 props 解析默认 accountCodes、method）
    - 实现 `validateConfig()` — 委托 validateSamplingConfig
    - 实现 `triggerSampling()` — POST /voucher-extract → 填充 sampledVouchers → 打开预览
    - 实现选中统计 computed：selectedVouchers、selectedCount、selectedDebitTotal、selectedCreditTotal
    - 实现 `confirmFill(mode)` — 按 phase 约束 mode → 生成 before_data 快照 → 按 mode 合并 → emit 'filled' → POST /cutoff-fill（extraction_type='voucher_sampling'）记录日志
    - 实现 fill mode 逻辑：append/replace/merge（replace 时仅清当前 phase 行）
    - 实现 `loadHistory()` — GET /voucher-history
    - 实现 `undoLastExtraction(logId)` — POST /voucher-undo → emit 'filled' with before_data
    - 实现 `compareVersions(logIdA, logIdB)` — POST /voucher-compare
    - 实现 `updateField(index, field, value)` — 更新字段 + 追加 edit_trail entry
    - 实现 `batchMarkChecked(indices)` — 批量设 checkResult='Y' + 追加 trail
    - 实现 `checkCompliance()` — 委托 checkCAS1314Compliance
    - _Requirements: 1.7, 1.8, 2.2, 3.9, 4.2, 4.5, 7.1, 7.2, 7.3, 7.4, 8.3, 9.1, 9.2, 9.3, 10.3, 10.4_

- [x] 6. 实现 GtVoucherSamplingEngine.vue 主组件
  - [x] 6.1 创建 `voucher-sampling/GtVoucherSamplingEngine.vue`（~400行）
    - Props：accountCode、phase、defaultMethod、workpaperId、projectId、year
    - 使用 useVoucherSampling + useSamplingPhase
    - 顶部：当前覆盖率统计卡片（笔数覆盖率+金额覆盖率，实时更新）
    - 中部：三种视图模式切换（el-radio-group：仅预审/仅年审/全量）
    - 主体：el-table 展示已填充 samples（按 visibleSamples 过滤）
      - 列：凭证号/日期/摘要/借方/贷方/科目/凭证类型/核查结果(inline)/异常(switch)/备注(inline)
      - 预审行在年审阶段 disabled 样式
    - CAS 1314 合规警告区（el-alert warning/info）
    - 操作栏："自动抽凭"按钮 → 打开 ConfigDialog | "抽凭历史"按钮 → 打开 HistoryDrawer | "批量标记已核查"按钮
    - 嵌入 SamplingConfigDialog + SamplingPreviewDialog + SamplingHistoryDrawer
    - defineEmits: 'filled', 'phase-changed'
    - _Requirements: 5.4, 8.3, 9.1, 9.3, 10.1, 10.3, 10.4, 10.5, 12.3_

- [x] 7. 实现 SamplingConfigDialog.vue 配置弹窗
  - [x] 7.1 创建 `voucher-sampling/SamplingConfigDialog.vue`（~450行）
    - el-dialog（width=700px）
    - 抽样方法选择：el-radio-group 5种方法
    - 条件渲染参数区（v-if method）：
      - random：样本量 el-input-number（min=1, max=500）
      - stratified：动态行列表（下限/上限/样本量）+ 增删行按钮
      - specific_item：重要性水平金额 + 可选自定义条件
      - systematic：起始点 + 间隔K
      - mus：样本量 + 总体金额（只读 computed）
    - 随机种子设置：el-input-number（可选）
    - 通用过滤条件区（el-collapse 默认展开）：
      - 科目范围（el-select 多选，前缀匹配）
      - 期间范围（el-checkbox-group，1-12月）
      - 金额范围（下限/上限）
      - 方向（el-radio-group：借方/贷方/不限）
      - 凭证类型（el-checkbox-group：记/收/付/转/不限）
      - 摘要关键词（el-input）
      - 排除已抽过（el-switch，默认开启）
    - 底部："执行抽样"按钮（校验后 emit execute）
    - 校验失败红色提示
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.4_

- [x] 8. 实现 SamplingPreviewDialog.vue 预览弹窗
  - [x] 8.1 创建 `voucher-sampling/SamplingPreviewDialog.vue`（~350行）
    - el-dialog（width=80vw，max-height=80vh）
    - 统计卡片（表头上方）：总体笔数/金额 | 已勾选样本笔数/金额 | 笔数覆盖率% | 金额覆盖率%
    - el-table 列：勾选框 | 凭证号 | 日期 | 摘要 | 借方 | 贷方 | 科目 | 科目名称 | 对方科目 | 凭证类型 | 会计期间 | 核查结果(inline) | 备注(inline)
    - 默认全部勾选
    - 金额列 displayPrefs.fmtAmount
    - 超100行虚拟滚动
    - truncated 时顶部黄色 el-alert
    - "追加"按钮（搜索框弹出，从序时账搜索追加）
    - 底部：填充策略 el-radio-group（年审时 replace/merge disabled）+ "确认填充"按钮
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 7.5_

- [x] 9. 实现 SamplingHistoryDrawer.vue + ComparePanel
  - [x] 9.1 创建 `voucher-sampling/SamplingHistoryDrawer.vue`（~300行）
    - el-drawer（direction=rtl，width=520px）
    - el-timeline 展示历史（按时间倒序）
    - 每条：操作时间 | 操作人 | 抽样方法 | 样本量 | 覆盖率 | 阶段标签
    - el-collapse 展开完整 extraction_criteria JSON
    - 最新非撤销记录显示"撤销"按钮
    - 已撤销记录灰色删除线 + is_undone 标记
    - "对比"功能：el-checkbox 选择两条记录 → 点击"对比"打开 ComparePanel
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6, 8.5_

  - [x] 9.2 创建 `voucher-sampling/SamplingComparePanel.vue`（~200行）
    - 三栏布局或 tab 切换：新增（绿色）/ 删除（红色）/ 保留（无标记）
    - 每栏 el-table 显示凭证号/日期/金额
    - 统计摘要：新增N笔 / 删除N笔 / 保留N笔
    - _Requirements: 6.3_

- [x] 10. Checkpoint - 前端组件验证
  - Ensure all frontend unit tests pass. Ask user if questions arise.

- [x] 11. D2 凭证抽样集成
  - [x] 11.1 在 D2TabVoucherCheck 中嵌入 GtVoucherSamplingEngine
    - 引入组件，传入 props: accountCode="1122", phase=currentPhase, defaultMethod="random", workpaperId, projectId, year
    - 监听 @filled 事件 → 将 payload.samples 映射到 D2-7 凭证抽样明细表列结构
    - 映射：voucher_no→凭证号、voucher_date→日期、debit_amount→借方金额、credit_amount→贷方金额、summary→摘要、counterpart_account→对方科目、account_code→科目编码
    - 保留现有手动"添加样本"按钮
    - 填充后的样本标记 source: "自动抽凭"
    - 抽样参数区数据（总体/样本量/方法/覆盖率）回写底稿参数区字段
    - 填充后触发 debounce 2s 自动保存
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 12. 后端 PBT 测试
  - [x]* 12.1 编写 Property 1 PBT：随机抽样产生恰好 N 笔
    - **Property 1: 随机抽样产生恰好 N 笔**
    - 生成器：`st.lists(ledger_entry_strategy(), min_size=1, max_size=200)` + `st.integers(min_value=1, max_value=len)`
    - 断言：len(result) == min(N, len(population))；result 全部 ∈ population
    - **Validates: Requirements 3.3**

  - [x]* 12.2 编写 Property 2 PBT：金额分层抽样尊重层级边界
    - **Property 2: 金额分层抽样尊重层级边界**
    - 生成器：自定义 population + non-overlapping strata 策略
    - 断言：每个 item 的 amount ∈ [lower, upper]；per-stratum count <= configured size；total = sum(per-stratum)
    - **Validates: Requirements 3.4**

  - [x]* 12.3 编写 Property 3 PBT：特定项目选取恰好捕获 >= 阈值
    - **Property 3: 特定项目选取恰好捕获 >= 阈值的全部凭证**
    - 生成器：`st.lists(ledger_entry_strategy())` + `st.decimals(min_value=Decimal('0'), max_value=Decimal('1000000'), places=2)`
    - 断言：所有 result item >= threshold；所有 population item >= threshold 在 result 中；所有 result item ∈ population
    - **Validates: Requirements 3.5**

  - [x]* 12.4 编写 Property 4 PBT：系统抽样间隔正确性
    - **Property 4: 系统抽样间隔正确性**
    - 生成器：`st.lists(ledger_entry_strategy(), min_size=2, max_size=500)` + `st.integers(1, len)` + `st.integers(2, 50)`
    - 断言：选中的 indices == {start-1, start-1+K, start-1+2K, ...} ∩ [0, len)
    - **Validates: Requirements 3.6**

  - [x]* 12.5 编写 Property 5 PBT：MUS 累积金额选取覆盖
    - **Property 5: MUS 累积金额选取覆盖**
    - 生成器：`st.lists(ledger_entry_strategy(positive=True), min_size=1, max_size=200)` + `st.integers(1, 50)`
    - 断言：sample_count ∈ [sample_size-1, sample_size+1]；所有 result ∈ population
    - **Validates: Requirements 3.7, 3.8**

  - [x]* 12.6 编写 Property 7 PBT：排除已抽凭证正确性
    - **Property 7: 排除已抽凭证正确性**
    - 生成器：`st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=50)` × 2
    - 断言：filtered ∩ excluded == ∅；filtered ∪ excluded ⊇ original（无误排除）
    - **Validates: Requirements 2.2, 2.3, 2.5**

  - [x]* 12.7 编写 Property 9 PBT：覆盖率计算准确性
    - **Property 9: 覆盖率计算准确性**
    - 生成器：`st.integers(1,1000)` (pop_count) + `st.integers(1, pop_count)` (sample_count) + `st.decimals(...)` × 2
    - 断言：count_rate == round(S/P×100, 2)；amount_rate == round(B/A×100, 2)
    - **Validates: Requirements 3.9, 12.1, 12.2**

  - [x]* 12.8 编写 Property 11 PBT：随机种子可复现性
    - **Property 11: 随机种子可复现性**
    - 生成器：`st.integers(0, 2**31)` + population + method + params
    - 断言：execute_sampling 两次调用结果完全相同
    - **Validates: Requirements 1.7, 3.12**

- [ ] 13. 前端 PBT 测试
  - [x]* 13.1 编写 Property 6 PBT：阶段隔离 — 年审永不覆盖预审
    - **Property 6: 阶段隔离 — 年审永不覆盖预审**
    - 生成器：自定义 SampledVoucher[]（mixed phases）+ fill operation（mode forced append）
    - 断言：fill 后 preliminary 行 deep-equal 原值；new rows phase='final'；view filtering 正确
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.5, 9.4**

  - [x]* 13.2 编写 Property 8 PBT：填充策略正确性
    - **Property 8: 填充策略正确性**
    - 生成器：自定义 existing SampledVoucher[] + selected[] + `fc.oneof('append','replace','merge')` + phase
    - 断言：append → current_phase_count grows by M; replace → current_phase = M; merge → no dup voucher_no
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [x]* 13.3 编写 Property 10 PBT：版本对比 diff 正确性
    - **Property 10: 版本对比 diff 正确性（完全分割）**
    - 生成器：`fc.array(fc.string({minLength:1, maxLength:10}))` × 2
    - 断言：added ∪ removed ∪ retained == A ∪ B；三集合两两无交集
    - **Validates: Requirements 6.3**

  - [x]* 13.4 编写 Property 12 PBT：编辑留痕不可变性
    - **Property 12: 编辑留痕不可变性（仅追加）**
    - 生成器：自定义 edit sequence（field + value pairs）
    - 断言：每次 edit 后 trail.length +1；旧 entries 不变；new entry.old_value == 编辑前值
    - **Validates: Requirements 9.2**

- [x] 14. 后端集成测试
  - [x] 14.1 编写完整流程集成测试
    - 测试场景：seed tb_ledger 数据 → POST /voucher-extract（5种方法各一次）→ 验证返回 → POST /cutoff-fill（extraction_type='voucher_sampling'）→ 验证 log → POST /voucher-undo → 验证恢复
    - 测试阶段隔离：预审填充 → 切年审 → 验证预审行不被覆盖 + 年审排除预审凭证号
    - 测试版本对比：两次抽凭 → POST /voucher-compare → 验证 added/removed/retained
    - 测试种子复现：同参数同种子两次调用结果相同
    - 测试排除去重：第一次抽凭 → 第二次排除已抽凭证
    - 测试安全隔离：项目A数据不可被项目B查询
    - _Requirements: 3.1, 3.2, 5.3, 6.3, 6.4, 13.1, 13.4_

- [x] 15. 前端单元测试
  - [x] 15.1 编写 useSamplingAlgorithms.spec.ts 单元测试
    - computeCoverage：边界值（population=0 → 0%，sample=population → 100%）
    - checkCAS1314Compliance：各阈值边界触发验证
    - validateSamplingConfig：各方法缺必填 → errors 非空
    - computeVersionDiff：空集/完全相同/完全不同

  - [x] 15.2 编写 useSamplingPhase.spec.ts 单元测试
    - viewMode 切换：preliminary/final/all 各返回正确子集
    - isRowEditable：年审+预审行 → false；年审+年审行 → true
    - isFillModeRestricted：phase=final → true
    - getPreliminaryVoucherNos：正确提取

  - [x] 15.3 编写 useVoucherSampling.spec.ts 单元测试
    - 配置初始化：accountCode → config.accountCodes
    - 校验逻辑：各方法缺必填参数
    - updateField：字段更新 + trail 追加
    - batchMarkChecked：批量标记 + trail
    - fill mode 逻辑：含阶段约束

- [x] 16. Checkpoint - 全部测试验证
  - Ensure all tests pass (PBT + unit + integration). Ask user if questions arise.

- [x] 17. 路由注册与契约验证
  - [x] 17.1 注册 voucher_sampling router 到 router_registry
    - 在 router_registry 对应分组文件中 import 并注册
    - 验证 `test_router_registry_completeness` 通过
    - _Requirements: 13.1_

- [x] 18. 回归测试
  - [x] 18.1 运行现有 D2 + cutoff 测试套件确保无回归
    - `rtk python -m pytest backend/tests/ -k "d2 or cutoff or voucher" -v --tb=short`
    - `rtk npx vitest run --reporter=verbose`（D2 + voucher 相关测试文件）
    - 确认无回归

- [x] 19. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are PBT tasks
- 每个 Property 对应 design.md 中的一个 correctness property
- 无需新建 DB 迁移文件：复用 V095 workpaper_extraction_log（extraction_type='voucher_sampling'）
- 后端 asyncpg 不支持 IN tuple 参数，必须用 `= ANY(:list)` + list 类型
- 金额序列化为字符串避免 JSON 浮点精度损失
- router_registry 注册必须完成否则端点 404
- LedgerSamplingService 由 cutoff spec 定义，本 spec 仅复用（build_ledger_query / execute_with_stats / record_extraction_log）
- 所有前端 PBT 使用 fast-check numRuns: 100，后端使用 hypothesis max_examples=100
- phase 阶段隔离是本 spec 核心差异点：年审永不覆盖预审行，强制 append
- edit_trail 存入行 JSON 的 edit_trail 字段（checklist_responses 内），不额外建表
- 版本对比基于 voucher_no 集合匹配，不涉及字段级 diff
