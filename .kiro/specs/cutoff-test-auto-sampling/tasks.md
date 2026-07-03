# Implementation Plan: 通用截止测试自动提取组件

## Overview

实现通用截止测试自动提取组件，从 tb_ledger 按条件自动查询凭证并填充到截止测试底稿。按依赖顺序实现：DB迁移 → 后端共享服务 → API端点 → 前端纯函数 → composable → Vue组件 → D2集成 → PBT测试。

## Tasks

- [ ] 1. 数据库迁移 V095
  - [x] 1.1 创建 `backend/migrations/V095_create_workpaper_extraction_log.sql`
    - CREATE TABLE IF NOT EXISTS workpaper_extraction_log（id UUID PK、project_id FK、workpaper_id FK、user_id、extraction_type VARCHAR(50)、extraction_criteria JSONB、total_matched INTEGER、filled_count INTEGER、fill_mode VARCHAR(20)、before_data JSONB、is_undone BOOLEAN DEFAULT FALSE、created_at TIMESTAMP DEFAULT now()）
    - CREATE INDEX IF NOT EXISTS idx_extraction_log_wp_created ON workpaper_extraction_log(workpaper_id, created_at DESC)
    - CREATE INDEX IF NOT EXISTS idx_extraction_log_project ON workpaper_extraction_log(project_id)
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 1.2 在 `backend/app/models/audit_platform_models.py` 中添加 WorkpaperExtractionLog ORM 模型
    - 定义所有列映射 + 类型注解
    - 添加 FK 关系（projects、working_papers）
    - _Requirements: 11.1_

- [ ] 2. 实现 LedgerSamplingService 后端共享服务
  - [x] 2.1 创建 `backend/app/services/ledger_sampling_service.py`
    - 定义 Pydantic 模型：LedgerQueryFilters、StatsResult、ExtractionLogCreate、CutoffExtractRequest
    - 实现 `build_ledger_query(db, project_id, year, filters)` — 调用 get_active_filter + 构建动态 WHERE 条件
    - 实现 account_codes 前缀匹配：`account_code LIKE ANY(:prefixes)`（使用 = ANY + list 避免 asyncpg tuple 问题）
    - 实现 direction_filter 条件：debit → `debit_amount > 0`、credit → `credit_amount > 0`
    - 实现 amount_threshold 条件：`GREATEST(COALESCE(debit_amount,0), COALESCE(credit_amount,0)) >= :threshold`
    - 实现 summary_keyword 条件：`summary ILIKE :pattern`
    - 实现 exclude_voucher_nos 条件：`voucher_no NOT IN (...)`（使用 != ALL）
    - 确保 project_id + year 安全隔离条件始终存在
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 10.1, 10.2, 10.3, 10.4_

  - [x] 2.2 实现 `execute_with_stats(db, query, page, page_size, max_total=500)`
    - 执行 COUNT(*) 获取总数
    - 执行分页查询（OFFSET/LIMIT）
    - 计算统计：debit_total（SUM）、credit_total（SUM）、by_voucher_type（GROUP BY）
    - 超过 max_total 时标记 truncated=true
    - 金额使用 Decimal 精度，序列化为字符串
    - _Requirements: 2.9, 2.10, 2.11_

  - [x] 2.3 实现 `record_extraction_log(db, log_data)` 和 `get_extraction_history(db, workpaper_id)` 和 `undo_extraction(db, log_id, workpaper_id)`
    - record: INSERT into workpaper_extraction_log
    - history: SELECT WHERE workpaper_id ORDER BY created_at DESC
    - undo: 验证 log_id 是最新非撤销记录 → 读取 before_data → 标记 is_undone=true
    - _Requirements: 5.1, 5.5, 5.6, 5.8, 9.1, 9.3, 9.4_

- [ ] 3. 实现截止测试 API 端点
  - [x] 3.1 创建 `backend/app/routers/cutoff_sampling.py`
    - `POST /api/projects/{pid}/sampling/cutoff-extract` — 接收 CutoffExtractRequest → 调用 LedgerSamplingService → 返回 items + stats
    - 日期窗口计算：cutoff_date - days_before 至 cutoff_date + days_after
    - exclude_extracted=true 时查 workpaper_extraction_log 获取已提取凭证号列表
    - `GET /api/projects/{pid}/sampling/cutoff-history?wp_id=` — 返回历史列表
    - `POST /api/projects/{pid}/sampling/cutoff-undo?log_id=` — 执行撤销
    - `POST /api/projects/{pid}/sampling/cutoff-fill` — 记录日志（含 before_data）
    - 注册到 router_registry
    - _Requirements: 2.1, 2.12, 5.2, 5.5, 5.6_

- [ ] 4. Checkpoint - 后端服务验证
  - Ensure migration runs, service unit tests pass. Ask user if questions arise.

- [ ] 5. 实现前端跨期判定纯函数
  - [x] 5.1 创建 `composables/cutoffJudgment.ts`
    - 导出类型：CutoffDirection、CutoffStatus
    - 实现 `determineCutoffStatus(voucherDate, cutoffDate, direction, amount, daysBefore?, daysAfter?)`
    - post_cutoff：voucherDate > cutoffDate 且 debit(amount>0) → "可能跨期"
    - pre_cutoff：voucherDate < cutoffDate 且 credit(amount<0) → "可能跨期"
    - window：voucherDate 在 [cutoffDate - daysBefore, cutoffDate + daysAfter] → "待检查"
    - 其他 → "正常"
    - 导出 `computeDateRange(cutoffDate, daysBefore, daysAfter)` 辅助函数
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

  - [x]* 5.2 编写 Property 1 PBT：跨期判定纯函数正确性
    - **Property 1: 跨期判定纯函数正确性**
    - 生成器：`fc.date({min, max})` + `fc.oneof('post_cutoff','pre_cutoff','window')` + `fc.float({min:-1e9, max:1e9})`
    - 断言：结果始终为三值枚举之一；各模式判定逻辑与日期/金额比较一致
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x]* 5.3 编写 Property 2 PBT：日期窗口计算正确性
    - **Property 2: 日期窗口计算正确性**
    - 生成器：`fc.date` + `fc.integer({min:0, max:60})` × 2
    - 断言：range_start = cutoffDate - daysBefore 天；range_end = cutoffDate + daysAfter 天；start <= cutoff <= end
    - **Validates: Requirements 1.3, 2.5**

- [ ] 6. 实现 useCutoffAutoSampling.ts composable
  - [x] 6.1 创建 `composables/useCutoffAutoSampling.ts`（~400行）
    - 定义所有 TypeScript 接口：CutoffConfig、ExtractedVoucher、ExtractStats、FillMode、ExtractionLogEntry
    - 实现 config 响应式初始化（从 props.accountCode 解析默认科目、从 props.year 计算默认截止日 12月31日）
    - 实现 `validateConfig()` — 校验 cutoffDate 非空 + accountCodes 非空
    - 实现 `dateRangeText` computed — 显示 "2025-12-26 至 2026-01-10" 格式
    - 实现 `triggerExtraction()` — 调用 POST /cutoff-extract → 填充 extractedVouchers（每条自动计算 cutoffStatus via determineCutoffStatus）→ 打开预览
    - 实现选中统计 computed：selectedVouchers、selectedCount、cutoffErrorCount、selectedDebitTotal、selectedCreditTotal
    - 实现 `confirmFill(mode)` — 按 fill mode 生成新 samples → emit 'filled' → 调用 POST /cutoff-fill 记录日志
    - 实现三种 fill mode 逻辑：append（拼接）、replace（替换）、merge（按 voucher_no 去重）
    - 实现 `loadHistory()` — 调用 GET /cutoff-history
    - 实现 `undoLastExtraction(logId)` — 调用 POST /cutoff-undo → emit 'filled' with before_data
    - _Requirements: 1.2, 1.3, 1.5, 3.3, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.3, 5.6, 5.8, 7.5, 8.4, 9.1, 9.5_

  - [x]* 6.2 编写 Property 8 PBT：填充策略正确性
    - **Property 8: 填充策略正确性**
    - 生成器：自定义 ExtractedVoucher[] + existing samples[] + `fc.oneof('append','replace','merge')`
    - 断言：append → length = N+M; replace → length = M; merge → no duplicates + length = N + (M - overlap)
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6**

  - [x]* 6.3 编写 Property 10 PBT：撤销 Round-Trip
    - **Property 10: 撤销 Round-Trip — before_data 快照与恢复**
    - 生成器：自定义 samples[] 生成器（随机长度 0-20 的凭证数组）
    - 断言：fill 后 log.before_data deep-equals 原 samples；undo 后恢复到原 samples
    - **Validates: Requirements 5.6, 5.8, 9.1, 9.3, 9.4, 9.5**

- [ ] 7. 实现 GtCutoffAutoSampling.vue 主组件
  - [x] 7.1 创建 `cutoff/GtCutoffAutoSampling.vue`（~300行）
    - 使用 useCutoffAutoSampling composable
    - 条件配置面板：el-form 布局（2列 el-row）
      - 截止基准日（el-date-picker，默认=年度12月31日）
      - 前窗口天数（el-input-number，默认5，min=0，max=60）
      - 后窗口天数（el-input-number，默认10，min=0，max=60）
      - 金额阈值（el-input-number，precision=2，默认0）
      - 科目范围（el-select 多选，支持手动输入前缀）
      - 方向过滤（el-radio-group：借方/贷方/不限）
      - 凭证类型过滤（el-checkbox-group：记/收/付/转/不限）
      - 摘要关键词（el-input）
      - 排除已提取（el-switch，默认开启）
    - 日期范围文字提示（dateRangeText computed）
    - "开始提取"按钮 + "提取历史"按钮
    - 校验失败红色提示
    - 嵌入 CutoffPreviewDialog + CutoffHistoryDrawer
    - defineEmits: 'filled'
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.1, 7.3_

- [ ] 8. 实现 CutoffPreviewDialog.vue 预览弹窗
  - [x] 8.1 创建 `cutoff/CutoffPreviewDialog.vue`（~350行）
    - el-dialog（width=80vw，max-height=80vh）
    - 统计信息卡片（表头上方）：已勾选/总笔数 | 跨期笔数 | 借方合计 | 贷方合计
    - el-table 列：勾选框 | 凭证号 | 凭证日期 | 摘要 | 借方金额 | 贷方金额 | 科目编码 | 科目名称 | 对方科目 | 凭证类型 | 跨期判定 | 备注
    - 默认全部勾选
    - 跨期判定="可能跨期" → 红色字体+背景高亮(:row-class-name)
    - 备注列 inline 编辑（el-input）
    - 金额列 displayPrefs.fmtAmount 格式化
    - 超100行启用 el-table 虚拟滚动
    - 底部：el-radio-group 填充策略（append/replace/merge）+ "确认填充"按钮
    - truncated 时顶部黄色 el-alert 提示
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [ ] 9. 实现 CutoffHistoryDrawer.vue 提取历史侧栏
  - [x] 9.1 创建 `cutoff/CutoffHistoryDrawer.vue`（~200行）
    - el-drawer（direction=rtl，width=480px）
    - el-timeline 展示历史记录列表（按时间倒序）
    - 每条记录显示：操作时间 | 操作人 | 填充模式 | 填充笔数 | 匹配总笔数
    - el-collapse 展开查看完整 extraction_criteria JSON
    - 最新非撤销记录显示"撤销"按钮；其他记录按钮禁用 + tooltip
    - 已撤销记录灰色删除线样式 + is_undone 标记
    - 撤销确认弹窗（el-message-box）
    - _Requirements: 5.3, 5.4, 5.7, 5.8, 9.4_

- [ ] 10. Checkpoint - 前端组件验证
  - Ensure all frontend unit tests pass. Ask user if questions arise.

- [ ] 11. D2 截止测试集成
  - [x] 11.1 在 D2TabCutoff（或 useD2AccountsReceivable 的 cutoff-test 区域）中嵌入 GtCutoffAutoSampling
    - 引入 `<GtCutoffAutoSampling>` 组件，传入 props: accountCode="1122", cutoffDirection="post_cutoff", workpaperId, projectId, year
    - 监听 @filled 事件 → 将 payload.samples 合并到 useD2 的 cutoffTestSamples 数组
    - 合并逻辑复用 filled payload 中的 fillMode
    - 保留现有手动"添加样本"按钮
    - 填充后的样本标记 source: "自动提取"，手动添加标记 source: "手动添加"
    - 填充后触发 debounce 2s 自动保存
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 12. 后端 PBT 测试
  - [x]* 12.1 编写 Property 3 PBT：查询安全隔离不变量
    - **Property 3: 查询安全隔离不变量**
    - 生成器：`st.uuids()` + `st.integers(2020,2030)` + 自定义 LedgerQueryFilters 策略
    - 断言：生成的 SQL WHERE 子句始终包含 project_id 和 year 条件
    - **Validates: Requirements 2.2, 2.3, 10.3**

  - [x]* 12.2 编写 Property 4 PBT：查询过滤条件构建正确性
    - **Property 4: 查询过滤条件构建正确性**
    - 生成器：自定义 LedgerQueryFilters 策略（随机 account_codes/direction/threshold/keyword）
    - 断言：各 filter 条件正确映射到 SQL 子句
    - **Validates: Requirements 1.4, 2.4, 2.6, 2.7, 2.8**

  - [x]* 12.3 编写 Property 5 PBT：统计摘要准确性
    - **Property 5: 统计摘要准确性**
    - 生成器：`st.lists(st.fixed_dictionaries({debit_amount: st.decimals(...), credit_amount: st.decimals(...), voucher_type: st.text(...)}))`
    - 断言：debit_total = sum(debit_amounts)；credit_total = sum(credit_amounts)；by_type counts match
    - **Validates: Requirements 2.9**

  - [x]* 12.4 编写 Property 6 PBT：截断阈值行为
    - **Property 6: 截断阈值行为**
    - 生成器：`st.integers(0,1000)` 控制结果行数
    - 断言：> 500 → truncated=true + items <= 500；<= 500 → truncated=false + items = total
    - **Validates: Requirements 2.10**

  - [x]* 12.5 编写 Property 7 PBT：金额 Decimal 序列化 Round-Trip
    - **Property 7: 金额 Decimal 序列化 Round-Trip**
    - 生成器：`st.decimals(min_value=-1e18, max_value=1e18, places=2, allow_nan=False, allow_infinity=False)`
    - 断言：`Decimal(str(d)) == d`
    - **Validates: Requirements 2.11**

  - [x]* 12.6 编写 Property 9 PBT：排除已提取凭证去重
    - **Property 9: 排除已提取凭证去重**
    - 生成器：`st.lists(st.text(min_size=1, max_size=20))` × 2 (已提取号 + 查询结果号)
    - 断言：过滤后结果与已提取集合交集为空；未被错误排除
    - **Validates: Requirements 2.12**

- [ ] 13. 后端集成测试
  - [x] 13.1 编写完整流程集成测试
    - 测试场景：seed tb_ledger 数据 → POST /cutoff-extract → 验证返回 → POST /cutoff-fill → 验证 log → POST /cutoff-undo → 验证恢复
    - 测试安全隔离：项目A数据不可被项目B查询
    - 测试分页：page=1 size=10 返回前10条
    - 测试空结果：条件过严返回 0 条
    - 测试 dataset 可见性：仅 active dataset 可见
    - _Requirements: 2.1, 2.2, 2.3, 2.12, 5.5, 5.6_

- [ ] 14. 前端单元测试
  - [x] 14.1 编写 cutoffJudgment.spec.ts 单元测试
    - 边界值：voucherDate = cutoffDate（临界点）
    - 无效日期输入返回 "正常"
    - window 模式边界：恰好在窗口边界日期
    - 金额为 0 的处理

  - [x] 14.2 编写 useCutoffAutoSampling.spec.ts 单元测试
    - 配置初始化：accountCode → accountCodes 数组
    - 校验逻辑：缺 cutoffDate 失败、缺 accountCodes 失败
    - 统计计算：选中/取消选中后金额合计变化
    - 填充映射：tb_ledger 字段 → sample 字段对应关系

- [ ] 15. Checkpoint - 全部测试验证
  - Ensure all tests pass (PBT + unit + integration). Ask user if questions arise.

- [ ] 16. 路由注册与契约验证
  - [x] 16.1 注册 cutoff_sampling router 到 router_registry
    - 在 router_registry 对应分组文件中 import 并注册
    - 验证 `test_router_registry_completeness` 通过
    - _Requirements: 2.1_

- [ ] 17. 回归测试
  - [x] 17.1 运行现有 D2 测试套件确保无回归
    - `rtk python -m pytest backend/tests/ -k "d2 or cutoff" -v --tb=short`
    - `rtk npx vitest run --reporter=verbose` (D2 + cutoff 相关测试文件)
    - 确认 D2 现有 76 tests (13 PBT + 89 vitest + 1 hypothesis) 全绿
    - 如有失败修复后重跑

- [ ] 18. Final checkpoint - 全部功能集成验证
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are PBT tasks（optional but user preference is to complete all）
- 每个 Property 对应 design.md 中的一个 correctness property
- 后端 asyncpg 不支持 IN tuple 参数，必须用 `= ANY(:list)` + list 类型
- 金额序列化为字符串避免 JSON 浮点精度损失
- router_registry 注册必须完成否则端点 404
- LedgerSamplingService 设计为无状态静态方法，便于未来 voucher-sampling-engine 复用
- 所有前端 PBT 使用 fast-check numRuns: 100，后端使用 hypothesis max_examples=100
