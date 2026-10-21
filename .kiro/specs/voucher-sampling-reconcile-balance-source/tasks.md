# 抽凭总体完整性核对接入科目余额表 + 预览内就地放行 — 任务

## Phase 1：后端核对改用余额表

- [ ] 1. 新建 `backend/app/services/sampling_population_reconcile.py`
  - `PopulationReconcileFacts` frozen dataclass（available / basis / ledger_debit / ledger_credit / book_debit / book_credit / unavailable_reason）+ `to_stats()` → dict
  - `select_top_level_rows(account_codes_in_range: list[str]) -> list[str]`：纯函数，输入所选范围内**余额表实际存在的** account_code 集合，输出最高层行的 code（没有"也在范围内的更短前缀"的行）
  - `async resolve_population_reconcile(db, project_id, year, account_codes, dataset_id)`：两条只读查询包在 `begin_nested()` 内；返回 `PopulationReconcileFacts`
  - _Requirements: R1.1, R1.2, R1.3, R1.4, R2.1, R2.2_

- [ ] 2. 路由 `voucher_sampling.py` 接入
  - 删除 `_resolve_independent_book_amount` 函数
  - 在 `sampling_dataset_id` 解析后调用 `resolve_population_reconcile`
  - `stats` 保留 `book_amount`/`reconcile_available`/`reconcile_basis`（向后兼容），新增 `reconcile_ledger_debit`/`reconcile_ledger_credit`/`reconcile_book_debit`/`reconcile_book_credit`/`reconcile_unavailable_reason`
  - 若 `TrialBalance` import 无其他引用则一并删除
  - _Requirements: R1.1, R1.5, R2.1_

- [ ] 3. 后端测试
  - 新建 `backend/tests/test_sampling_population_reconcile.py`：SQLite 真 ORM 行
    - 最高层行选取（父子层级、单层、叶子无父在范围内）
    - 科目前缀匹配（`1122` 匹配 `1122.01`；`1122,1221` 多码）
    - 数据集过滤（非 active 行不纳入）
    - 年度窗口（跨年度凭证不纳入）
    - 不可用原因三类：无科目 / 余额表无行 / 取数异常
    - 取数异常后外层会话仍可继续用
  - 重写 `test_voucher_sampling_reconcile.py`：端点契约
    - 资产类科目返回 `reconcile_available=true`（不再恒 false）
    - `reconcile_basis` = `tb_balance_movement`
    - `book_amount` 为余额表借+贷合计（非 null）
    - 新逐方向字段存在且类型正确
  - 更新 `test_voucher_sampling_unit.py` 的 mock 路径（`_resolve_independent_book_amount` → `resolve_population_reconcile`）
  - _Requirements: R5.1_

## Phase 2：前端核对模块改造

- [ ] 4. 新建 `composables/samplingPopulationReconcile.ts`
  - `parseReconcileInfo(stats)` → `PopulationReconcileInfo`（含逐方向金额 + 不可用原因 + 向后兼容旧响应）
  - `resolvePopulationReconcile(opts)` → `PopulationReconcileResult | null`（手工优先 → 自动逐方向 → null）
  - `describeReconcileIssue(result, info, pct)` → `string | null`（门控原因文案）
  - `reconcilePresetsFor(result)` → `string[]`（仅未执行核对时给预置理由）
  - `formatMovementPair(d, c)` → `string`
  - _Requirements: R1.4, R2.1, R3.4_

- [ ] 5. `useVoucherSampling.ts` 接入
  - `reconcileInfo` 产出改走 `parseReconcileInfo`
  - 新增 `conclusionBlockedSource` computed（`'unchecked'|'deviation'|'reconcile'|'other'|null`），与 `conclusionBlockedReason` 同链
  - _Requirements: R1.1, R3.3_

- [ ] 6. `GtVoucherSamplingEngine.vue` 改造
  - `populationReconcile` / `reconcileIssue` 改调新模块
  - 校验卡片增「序时账发生额（所选科目·全年）」行，差异按逐方向显示
  - `confirmBlockedReason` 后缀按来源分文案：`reconcile` → 「可直接在本窗口下方填写说明」
  - 向预览组件传入 `reconcile-issue` / `v-model:reconcile-override-reason` / `reconcile-presets`
  - _Requirements: R1.4, R3.1, R3.2, R3.3, R3.4_

- [ ] 7. `SamplingPreviewDialog.vue` 就地放行
  - 新 props `reconcileIssue`（缺省 null）/ `reconcileOverrideReason`（双向绑定）/ `reconcilePresets`
  - 底部操作区上方渲染「总体完整性校验」块（原因 + 文本框 + 预置 + 字数状态）
  - 确认按钮 disabled 仍由 `confirmBlockedReason` 控制（逻辑不变，视觉上用户有填写入口了）
  - _Requirements: R3.1, R3.2_

## Phase 3：前端测试 + 验收

- [ ] 8. 前端纯函数测试 `samplingPopulationReconcile.spec.ts`（新）
  - 逐方向判定、负数账面、手工口径、旧响应回落、文案生成、预置理由
  - _Requirements: R5.3_

- [ ] 9. 前端接线测试 `samplingReconcilePreviewOverride.spec.ts`（新）
  - composable `conclusionBlockedSource` 映射
  - 预览弹窗就地放行：reconcileIssue 非空 → 块可见 → 填 ≥10 字 → 按钮非 disabled
  - 引擎 `confirmBlockedReason` 文案按来源区分
  - _Requirements: R3.1, R3.3, R5.3_

- [ ] 10. 浏览器实测
  - 安徽 D2 1122 抽凭：核对显示一致 + 确认填充可用
  - 构造不符场景（手工输入差异大的账面金额）：预览内填说明 ≥10 字 → 解除
  - _Requirements: R5.4_

- [ ] 11. 回归 + 行数门
  - 后端 `python -m pytest backend/tests/test_voucher_sampling*.py backend/tests/test_sampling_population_reconcile.py -v`
  - 前端 `npx vitest run --reporter=verbose` 相关 spec 文件
  - whitelist 基线按实际行数更新（如有膨胀须拆分）
  - _Requirements: R5.1, R5.2, R5.3_
