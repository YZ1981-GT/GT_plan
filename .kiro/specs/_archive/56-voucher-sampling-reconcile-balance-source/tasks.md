# 抽凭总体完整性核对接入科目余额表 + 预览内就地放行 — 任务

> **进度（2026-10-21）**：11/12 完成。Task 11 浏览器实测标 `[ ]*`（需启动 dev server + 共享浏览器环境）。
> 后端 41 passed（SQLite 33 + 端点契约 5 + 单元 3）；前端 60 passed（纯函数 41 + 接线 19）。

## Phase 1：后端科目映射反查 + 核对改用余额表

- [x] 1. `sampling_population_reconcile.py` 新增 `resolve_effective_codes`
  - 查 `account_mapping`（`project_id + is_deleted=false + standard_account_code LIKE '{标准码}%'`）
  - 返回 `(original_codes, True)` 或退回 `(standard_codes, False)`
  - SAVEPOINT 隔离（映射表查不到不阻断后续）；异常退回标准编码
  - _Requirements: R1.6, R1.7_

- [x] 2. `sampling_population_reconcile.py` 改造 `resolve_population_reconcile`
  - 开头调 `resolve_effective_codes` 解析 `account_codes` 为 `effective_codes`
  - 余额表和序时账查询都用 `effective_codes` 做前缀匹配
  - `PopulationReconcileFacts` 新增 `mapping_used: bool`，`to_stats()` 输出 `reconcile_mapping_used`
  - 不可用原因：未用映射且查不到行时追加「建议先在『科目映射』中确认映射关系」；有映射但查不到行时不追加（映射已存在，问题在数据）
  - _Requirements: R1.1, R1.2, R1.3, R1.4, R1.6, R2.1_

- [x] 3. 路由 `voucher_sampling.py` 接入
  - 导入 `resolve_effective_codes`；在 `filters` 解析 `account_codes` 后先调映射反查，得到 `(effective_codes, _mapping_used)`
  - `effective_codes` 传入 `LedgerQueryFilters.account_codes`（抽凭总体查询也用映射后编码）
  - `resolve_population_reconcile` 传标准编码 `account_codes`（核对函数内部自包含做映射，保持封装）
  - _Requirements: R1.1, R1.5, R1.6, R2.1_

- [x] 4. 后端测试
  - `test_sampling_population_reconcile.py` 扩展至 33 passed：
    - 原 20 例（纯函数 7 + 核对 13）+ 旧用例 `test_no_balance_rows` 断言更新（不可用原因现含映射建议）
    - 新增 `TestResolveEffectiveCodes`（7 例）：无映射退回 / 空列表 / 有映射 / 部分映射 / 已删除忽略 / 前缀匹配 / 其他项目隔离
    - 新增 `TestReconcileWithMapping`（6 例）：映射后核对 / 无映射直连 / 有映射无数据 / 无映射+建议 / to_stats 含 mapping_used / 映射后最高层行
  - `test_voucher_sampling_reconcile.py` 5 passed + `test_voucher_sampling_unit.py` 3 passed 回归全绿
  - _Requirements: R5.1_

## Phase 2：前端核对模块改造

- [x] 5. `composables/samplingPopulationReconcile.ts` 增量改造
  - 已有纯函数模块无需新建；`PopulationReconcileInfo` 加 `mappingUsed: boolean`
  - `parseReconcileInfo` 解析 `reconcile_mapping_used`（旧后端缺省 false）
  - 不可用原因由后端给出（含映射建议），前端透传不重复追加
  - _Requirements: R1.4, R2.1, R3.4_

- [x] 6. `useVoucherSampling.ts` — 无需改动
  - `conclusionBlockedSource` / `conclusionBlockedReason` / `reconcileBlockedReason` 链已完整
  - `PopulationReconcileInfo` 类型扩展自动兼容
  - _Requirements: R1.1, R3.3_

- [x] 7. `GtVoucherSamplingEngine.vue` 增量改造
  - 核对卡片 basis 行旁加映射状态 `el-tag`（「已通过科目映射」success / 「直接匹配（未使用映射）」info）
  - 其余核对卡片 / confirmBlockedReason / 预览传参均已存在
  - _Requirements: R1.4, R1.6, R3.1, R3.2, R3.3, R3.4_

- [x] 8. `SamplingPreviewDialog.vue` — 无需改动
  - 就地放行块（reconcileIssue / reconcileOverrideReason / reconcilePresets / 字数提示）已完整存在
  - _Requirements: R3.1, R3.2_

## Phase 3：前端测试 + 验收

- [x] 9. 前端纯函数测试 `samplingPopulationReconcile.spec.ts`
  - 41 passed：原 39 例 + 新增 2 例映射状态（新后端含 mapping_used=true / 旧后端默认 false）
  - `mkInfo` 辅助函数补 `mappingUsed: false` 默认值
  - _Requirements: R5.3_

- [x] 10. 前端接线测试 `samplingReconcilePreviewOverride.spec.ts`
  - 19 passed：全通过，无需改动（门控来源 / 文案分发 / props 传参 / CSS 孤儿 / import 扫描）
  - _Requirements: R3.1, R3.3, R5.3_

- [ ]* 11. 浏览器实测
  - 安徽 D2 1122 抽凭：核对显示一致 + 确认填充可用 + 映射状态标签
  - 构造不符场景：预览内填说明 ≥10 字 → 解除
  - **待共享环境**（start-dev.bat 启动后端 9980 + 前端 3030）
  - _Requirements: R5.4_

- [x] 12. 回归 + 行数门
  - 后端 41 passed / 0 failed（三个测试文件），warnings 全是预存 AsyncMockMixin 协程未 await
  - 前端 60 passed / 0 failed（纯函数 41 + 接线 19）
  - 无新增文件超行数门（改动文件均为增量修改）
  - _Requirements: R5.1, R5.2, R5.3_

## 改动文件清单

| 文件 | 改动 |
|------|------|
| `backend/app/services/sampling_population_reconcile.py` | 新增 `resolve_effective_codes` + `PopulationReconcileFacts.mapping_used` + `to_stats` 输出 `reconcile_mapping_used` + 核对主函数接入映射 + 不可用原因增映射建议 |
| `backend/app/routers/voucher_sampling.py` | 导入 `resolve_effective_codes` + 抽凭总体查询用映射后编码 |
| `backend/tests/test_sampling_population_reconcile.py` | 新增 13 例映射反查测试 + 更新 1 例旧断言 |
| `audit-platform/frontend/src/components/workpaper/composables/samplingPopulationReconcile.ts` | `PopulationReconcileInfo.mappingUsed` + `parseReconcileInfo` 解析 `reconcile_mapping_used` |
| `audit-platform/frontend/src/components/workpaper/voucher-sampling/GtVoucherSamplingEngine.vue` | 核对卡片加映射状态 `el-tag` |
| `audit-platform/frontend/src/components/workpaper/composables/__tests__/samplingPopulationReconcile.spec.ts` | 新增 2 例映射状态断言 + `mkInfo` 补默认值 |
