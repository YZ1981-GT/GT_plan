# Implementation Plan: sampling-compliance-closure

## Overview

抽样/抽凭合规闭环 + 多轨清理 + 宿主收口，共 3 波 24 个任务。

**canonical 抽凭链路不重构**：抽样算法、两阶段全量框、覆盖率口径、批次状态机、
历史/撤销/对比全部保持逐字节不变，本 spec 只做加法与删除 legacy。

波次与用户给定顺序一致：
- **Wave 1（合规闭环）** = R1 dataset 绑定 → R2 评价持久化 → R3 A13 projected 通路。
  三者缺任一环，「样本错报 → 总体错报 → 与重要性比较」都不成立，必须整波交付。
- **Wave 2（多轨清理）** = R4 删 legacy 引擎 + 守卫扩面；R5 两张准则记录表接入 + V139 迁移。
- **Wave 3（宿主收口）** = R6 共享件 + bar + 42 个宿主接线 + 平台守卫。

**Wave 4（抽凭表共享层，19 份 `useXVoucherCheck` 收敛）不在本 spec**，另立
`voucher-check-shared-layer` spec —— 它要统一 `VoucherCheckRow` 行模型与核对项声明，
半径覆盖 D/F/G/K/L 五大类循环，且与本 spec 的 R6 有文件重叠（先做 R6 让宿主侧稳定，
再动 composable 层）。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "合规闭环：dataset 绑定 + 评价持久化 + A13 推断错报通路",
      "tasks": ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
    },
    {
      "wave": 2,
      "name": "多轨清理：删 legacy 引擎 + 准则记录表接入",
      "tasks": ["10", "11", "12", "13", "14", "15", "16"]
    },
    {
      "wave": 3,
      "name": "宿主收口：共享件 + 方法学 bar + 42 宿主 + 平台守卫",
      "tasks": ["17", "18", "19", "20", "21", "22"]
    },
    {
      "wave": 4,
      "name": "收口：CI 挂载 + 浏览器实测 + 数据复原",
      "tasks": ["23", "24"]
    }
  ]
}
```

## Tasks

### Wave 1 — 合规闭环

- [x] 1. `voucher-extract` 返回抽样框数据集版本
  - `voucher_sampling.py` 引入 `get_active_dataset_id_or_none`，在 `_authorize_and_validate_extract`
    之后、取数之前解析一次；写入返回值 `stats.dataset_id`（`str | None`）
  - 无 active 数据集时为 `null`，**禁用任何兜底**（不取「最近一个 dataset」、不取当前时间）
  - 不改 `stats` 既有字段，不改 `methodology` 快照结构
  - _Requirements: 1.1, 7.2_

- [x] 2. `voucher-history` 增 `dataset_id` / `dataset_stale` / `evaluation` 三字段
  - 抽纯函数 `compute_dataset_stale(record_dataset_id, current_dataset_id) -> bool`
    实现三态判定（空 ⇒ false，相等 ⇒ false，不等 ⇒ true）
  - year 从底稿所属项目 `audit_year` 解析；解析不到则 `dataset_stale` 一律 `false`
  - 不改 history 端点签名（仍只有 `wp_id`），新增字段向后兼容
  - _Requirements: 1.4, 1.6_
  - _Properties: 2_

- [x] 3. `POST /sampling/voucher-evaluation` 端点 + `_normalize_evaluation`
  - 新增 `VoucherEvaluationRequest`；`_authorize_and_validate_evaluation` 复用编辑权 +
    底稿归属 pid 校验，**置于 try 之外**
  - `_resolve_target_log`：`log_id` 缺省时取该底稿最近一条未撤销 `voucher_sampling` 记录，
    不存在返 404
  - `_normalize_evaluation`：key 白名单（未知 key 丢弃）、金额转 Decimal 字符串、
    `evaluated_at` / `evaluated_by` 服务端覆盖
  - **`log.extraction_criteria` 必须赋新 dict**（原地 mutate 不触发 SQLAlchemy 脏检测）
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Properties: 3, 4_

- [x] 4. 后端守卫：dataset 绑定 + evaluation upsert
  - 新建 `backend/tests/test_sampling_dataset_binding.py`：Property 1（连库，单
    `asyncio.run` 快照）+ Property 2（纯函数参数化，含三态与反向自检）
  - 新建 `backend/tests/test_sampling_evaluation_endpoint.py`：Property 3（幂等 + 其余 key
    不变）、Property 4（授权先于写入，断言 `updated_at` 未变）
  - _Requirements: 1.1, 1.4, 2.1, 2.4, 7.3_
  - _Properties: 1, 2, 3, 4_

- [x] 5. 前端：extract 消费 `dataset_id` + confirmFill 留痕 + 历史告警
  - `useVoucherSampling`：新增 `datasetId` ref；`triggerSampling` 从 `stats.dataset_id` 读取；
    `dataset_id` 为 null 时 `ElMessage.info` 提示未绑定抽样框版本（不阻断）
  - `confirmFill` 的 `extraction_criteria` 增 `dataset_id`
  - `SamplingHistoryDrawer.vue`：`dataset_stale` 行渲染「抽样框已变更」danger tag + tooltip
    说明「以相同随机种子重跑不会得到相同样本，需重抽或书面说明」
  - _Requirements: 1.2, 1.3, 1.5_

- [x] 6. 前端：评价持久化与回读
  - `useVoucherSampling` 新增 `loadedFromBatch` / `loadLatestEvaluation()` / `persistEvaluation()`
  - `inferMisstatement` / `recordActualMisstatement` 触发后调 `persistEvaluation()`，
    失败 `ElMessage.error` 明示（**禁 `catch {}` 静默吞**）
  - 引擎挂载时若本会话未执行新抽样 → `loadLatestEvaluation()` 还原
    `misstatementResult` / `samplingConclusion` / `conclusionConfirmed`
  - `triggerSampling` 的重置分支同时清 `loadedFromBatch`（Property 5）
  - `confirmFill` 若已有推断结果，随 criteria 一并发 `evaluation`
  - `GtVoucherSamplingEngine.vue` 推断区标注「读自批次 xxxxxxxx（2026-xx-xx 评价）」
  - _Requirements: 2.5, 2.6, 2.7, 2.8, 2.9_
  - _Properties: 5_

- [x] 7. A13 桥支持 `misstatementType`（缺省 factual 保零回归）
  - `MisstatementDraft` 增 `misstatementType`；导出 `MisstatementTypeValue` 与 `normalizeType`
  - `normalizeMisstatementPushPayload`：行级 > 顶层 > `'factual'`；非法值归一为 `'factual'`
  - bridge 的 `createMisstatement` 改传 `d.misstatementType`，删硬编码 `'factual'`
  - 去重 `draftHash` 增类型维度
  - `Misstatements.vue` 类型下拉补「推断错报」`value="projected"`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.9_
  - _Properties: 6, 9_

- [x] 8. 引擎「推送推断错报至 A13」
  - `useVoucherSampling.pushProjectedToA13()`：门控 `conclusionConfirmed && projected > 0`；
    构造单行 payload（`misstatementType:'projected'`，金额 = `projected`，描述内嵌
    方法/样本量/种子/批次号，`known_high_value > 0` 时追加高值层提示语）
  - `evaluation.a13_pushed_at` 非空时 `ElMessageBox.confirm` 二次确认
  - 推送成功后调 `persistEvaluation()` 写回 `a13_pushed_at`
  - `GtVoucherSamplingEngine.vue` 结论区加按钮（未确认结论时 `disabled` + tooltip 说明原因）
  - _Requirements: 3.5, 3.6, 3.7, 3.8_
  - _Properties: 7, 8_

- [x] 9. 前端守卫：A13 类型通路 + 评价回读
  - 扩 `useA13MisstatementBridge.spec.ts`：Property 6（PBT + 既有四形态缺省等价）、
    Property 9（factual/projected 不互吞）
  - 新建 `voucherSamplingEvaluation.spec.ts`：Property 5（新抽样清空回读）、
    Property 7（推送草稿的金额与类型与描述四项标识）、Property 8（未确认不可推送）
  - _Requirements: 3.1~3.8, 2.7, 2.8_
  - _Properties: 5, 6, 7, 8, 9_

### Wave 2 — 多轨清理

- [x] 10. 删除 legacy 抽样引擎与其两个端点
  - 删 `backend/app/services/wp_sampling_engine.py`
  - 删 `sampling_enhanced.py` 的 `SamplingExecuteRequest` + `/sampling/execute`
  - 删 `wp_functional_actions.py` 的 `elif endpoint == "sampling/execute"` 分支
  - 删测试：`test_wp_sampling_engine_seed.py` 整文件、
    `test_voucher_sampling_characterization.py::TestWpSamplingEngineCharacterization`、
    `test_wp_functional_actions.py` 的 4 个 `test_sampling_engine_*`
  - **canonical 段断言一律保留，不得放宽**
  - _Requirements: 4.1, 4.2, 4.6_

- [x] 11. canonical 守卫扩面到全仓
  - `test_voucher_sampling_canonical_guard.py` 增：`backend/app/**` 全仓对
    `WpSamplingEngine` / `wp_sampling_engine` 零引用；无生产代码写 `parsed_data.action_data`
  - 读源码前 `_strip_comments()`（否则守卫自己的说明注释会被数成真实引用），
    并加 `_strip_comments` 自身的反向自检
  - 反向自检：给定含 legacy 引用的替身源码字符串时判定必须为违规
  - _Requirements: 4.3, 4.4, 4.5_
  - _Properties: 10_

- [x] 12. 迁移 V139：两张登记表补列与唯一索引
  - 新建 `backend/migrations/V139__sampling_registry_batch_binding.sql`，全部
    `IF NOT EXISTS` 幂等
  - `sampling_records` 加 `batch_id` / `sampling_method` / `random_seed` / `dataset_id` + batch 索引
  - `sampled_vouchers` 加 `batch_id` + 部分唯一索引（`WHERE is_deleted = false`）
  - **应用需重启后端**（`MigrationRunner` 只在启动时跑）；任务完成前须实测
    `schema_version` 出现 139 且两表新列存在
  - _Requirements: 5.3, 5.4_

- [x] 13. `sampling_registry_service.py`：两表接入
  - `register_sampling_batch` / `register_sampled_vouchers` /
    `update_sampling_record_evaluation` / `project_level_extracted_voucher_nos`
  - 字段映射按 design 的映射表；`sampled_vouchers` 批量插入走 ON CONFLICT DO NOTHING
  - 全部 fail-open + `logger.warning`（不得静默）
  - 在 `cutoff_fill`（仅 `extraction_type='voucher_sampling'` 分支）与 `voucher_evaluation`
    中调用
  - _Requirements: 5.1, 5.2_
  - _Properties: 11, 12, 14_

- [x] 14. 跨底稿排除 + 项目级抽样概览端点
  - `VoucherExtractRequest.filters` 增 `exclude_scope: 'workpaper' | 'project'`，
    **缺省 `'workpaper'` 保零回归**；`'project'` 时排除集合取
    `project_level_extracted_voucher_nos`
  - `GET /sampling/voucher-coverage`：按底稿汇总批次数/样本数 + 被 ≥2 底稿抽取的凭证清单
  - `SamplingConfigDialog.vue` 增「排除范围」点选（当前底稿 / 全项目），默认当前底稿
  - _Requirements: 5.5, 5.6_

- [x] 15. `sampling_config` 软弃用标注
  - `sampling_service.py` 模块 docstring 加 `.. deprecated::` 说明（样本量计算的单一真源
    已是 `sampling_methodology`，本 service 的 config CRUD 无消费方且全库 0 行）
  - **不删表、不删端点**（破坏性操作需用户单独授权），只禁新增写入点
  - _Requirements: 5.7_

- [x] 16. Wave 2 守卫
  - 新建 `backend/tests/test_sampling_registry_service.py`：Property 11（连库唯一索引防重）、
    Property 12（caplog 断言 fail-open 必留 WARNING）、Property 14（构造点存在 + 反向自检）
  - 新建 `backend/tests/test_sampling_config_deprecation.py`：Property 13
    （`SamplingConfig(` 计数不增 + docstring 含 deprecated 标注）
  - _Requirements: 5.1, 5.2, 5.7, 5.8_
  - _Properties: 11, 12, 13, 14_

### Wave 3 — 宿主收口

- [x] 25. 跨底稿重复抽凭的显式确认（R8，用户 2026-08-04 追加要求）
  - 后端 `cross_workpaper_duplicate_vouchers`（排除当前底稿 + 只算 `batch_id` 非空的引擎
    登记行 + JOIN `wp_index` 取 wp_code + fail-open）；`voucher-extract` 返回
    `cross_workpaper_duplicates`
  - 前端 `confirmCrossWpDuplicates()` 在**打开预览之前**弹框，三出口
    保留全部／剔除重复项／取消；`buildDuplicateSummary` >10 条截断
  - `recomputeCoverageAfterRemoval()`：剔除后按剩余样本重算覆盖率，**分母（总体）不变**
  - 处置随回填留痕：`duplicate_decision` + `duplicate_voucher_nos`
  - 守卫 `crossWorkpaperDuplicateConfirm.spec.ts`(17) + 后端 4 例
  - _Requirements: 8.1~8.9_
  - _Properties: 19, 20, 21_

- [x] 17. 共享件 `composables/shared/samplingFillTarget.ts`
  - `SamplingMethodologySnapshot` 类型 + `samplingMethodologyItemKey(wpCode)` +
    `buildMethodologySummary(m)` + `mapSampledToGenericRow(v)`
  - 零 Vue 依赖纯函数（便于 PBT 与守卫交叉读取）
  - _Requirements: 6.1_

- [x] 18. `WpSamplingMethodologyBar.vue`
  - 紧凑单行 bar（方法 · 间隔 · 样本量(建议 N) · 可容忍错报 · 种子 · 批次 · 账套版本）
  - `methodology` 空时整条不渲染
  - 金额走 `displayPrefs.fmtAmount()`：**setup 顶层** `inject(DisplayPrefs_Key, null) ??
    useDisplayPrefsStore()` 再取成员，禁 `import { fmtAmount } from '@/stores/displayPrefs'`
    （不存在该导出，会让整页崩）
  - _Requirements: 6.2_
  - _Properties: 17_

- [x] 19. 宿主接线（D/E/F 类，共 14 个）
  - `D3TabVoucherCheck` / `D5TabDetail` / `D6TabInspection` / `D7TabVoucherCheck` /
    `E1TabBankFlowReconcile` / `E1TabLargeCheck` / `F1TabComprehensiveCheck` /
    `F2TabMaterialUsageCheck` / `F2TabPurchaseInboundCheck` / `F2ValuationTestSheet` /
    `F2TabContractCostCheck` / `F3TabVoucherCheck` / `F4TabVoucherCheck` /
    `F5TabMajorAdjustment`
  - 每个：`handleVoucherFilled` 持久化 `payload.methodology` 到 `samplingMethodologyItemKey`；
    样本映射补齐最小字段集；模板加 `WpSamplingMethodologyBar`
  - **✅ 已交付 methodology 消费 + 固定 item key + bar 渲染（14/14）**
  - **⛔ 剩「样本映射补齐最小字段集」**：13 个宿主缺 `accountCode`，映射在 per-cycle
    composable 的行模型里 → 见 Progress Log 与 allowlist 逐条理由。**勿重做接线**
  - _Requirements: 6.3, 6.4, 6.5_

- [x] 20. 宿主接线（G 类，共 12 个）
  - `G1TabDerivativeCheck` / `G1TabVoucherCheck` / `G2TabVoucherCheck` /
    `G3TabCalcCheck` / `G4TabVoucherCheck` / `G5TabVoucherCheck` / `G6TabVoucherCheck` /
    `G7TabVoucherCheck` / `G7VoucherSampleSection` / `G8TabVoucherCheck` /
    `G9TabVoucherCheck` / `G10TabVoucherCheck`
  - **✅ 已交付 methodology 消费 + 固定 item key + bar 渲染（11/11）**
  - **🔴 `G3TabCalcCheck` 不是宿主**（文件存在但全文无 `GtVoucherSamplingEngine`）→ G 类实际 11 个
  - **⛔ 剩「最小字段集」**：同 Task 19，见 Progress Log。**勿重做接线**
  - _Requirements: 6.3, 6.4, 6.5_

- [x] 21. 宿主接线（H/I/K 类，共 16 个）
  - `H1TabAdditionCheck` / `H1TabDisposalCheck` / `H10TabCheck` / `H2TabAdditionCheck` /
    `H2TabDecreaseCheck` / `H3TabAdditionCheck` / `H4TabAdditionCheck` /
    `H4TabDisposalCheck` / `H5TabAdditionCheck` / `H5TabDisposalCheck` /
    `H8TabDisposalCheck` / `I2TabCutoffBackward` / `I2TabCutoffForward` /
    `I6TabCutoffBackward` / `I6TabCutoffForward` / `K1TabReceivableCheck`
  - **✅ 已交付 methodology 消费 + 固定 item key + bar 渲染（16/16）**
  - **⛔ 剩「最小字段集」**：同 Task 19，见 Progress Log。**勿重做接线**
  - _Requirements: 6.3, 6.4, 6.5_

- [x] 22. 平台守卫 `samplingHostMethodologyCoverage.spec.ts`
  - 扫全部含 `GtVoucherSamplingEngine` 的 `.vue`；Property 15（覆盖率单调收敛 +
    allowlist 每条带理由 ≥10 字 + 条目数只许变短）、Property 16（最小字段集）
  - 薄壳 `v-bind="$props"` 委托解析为已满足
  - 反向自检：构造丢弃 methodology / 只读 summary 的替身宿主源码时断言必红
  - **`REPO_ROOT` 用哨兵文件向上查找，禁写死回退级数**，哨兵须是具体文件不能是目录
  - 新建 `samplingFillTarget.spec.ts` 覆盖 Property 17 的字段集与格式化
  - _Requirements: 6.6, 6.7, 6.8_
  - _Properties: 15, 16, 17_

### Wave 4 — 收口

- [x] 23. CI 挂载
  - `.github/workflows/governance-checks.yml` 增 job `sampling-compliance-backend`
    （Wave 1/2 的后端守卫）与 `sampling-compliance-frontend`（Wave 1/3 的前端守卫）
  - **提交前确认 yml 不引用任何未提交的测试文件**（否则 CI 立刻红；memory 已记该踩坑）
  - _Requirements: 7.5_

- [ ] 24. 浏览器实测 + 真实库验证 + 数据复原
  - 抽样 → 录实际错报 → 推断 → 确认结论 → 推送 A13 → `postgres` 查到
    `misstatement_type='projected'` 行（Property 18）
  - 关弹窗重开 → 推断区还原且标注来源批次（R2.7）
  - 历史抽屉：切换 active dataset 后「抽样框已变更」告警出现（R1.5）
  - `sampling_records` / `sampled_vouchers` 落库校验 + 同批次重复回填行数不增（Property 11）
  - `voucher-coverage` 返回跨底稿重复凭证
  - **实测三件套缺一不算实测**：录真实数据 + 看目标区域真出数 + postgres 查落库
  - 测完逐字段复原（含删除 projected 错报行、清 evaluation、恢复 `last_sync`/`parsed_data`）
  - _Requirements: 7.3, 7.4_
  - _Properties: 18_

## Progress Log

### Wave 1 Task 1~4 已交付（2026-08-04）

**后端产出**：`voucher_sampling.py` 新增 —— `_resolve_sampling_dataset_id`（镜像
`get_active_filter` 的 rollback 失败处理，禁兜底）· `compute_dataset_stale`（纯函数三态）·
`_resolve_project_year`（history 端点反解年度，全 try 包裹降级 None）·
`VoucherEvaluationRequest` + `POST /voucher-evaluation` 端点 · `_normalize_evaluation`
（key 白名单 / 金额 2 位小数 / 计数非负 / 结论代码取值域 / 服务端覆盖 actor+time /
a13 标记未提供时保留）· `merge_evaluation_into_criteria`（纯函数，只写一个 key）·
`_authorize_and_validate_evaluation` · `_resolve_target_log`；extract 返回
`stats.dataset_id`，history 增 `batch_id`/`dataset_id`/`dataset_stale`/`evaluation`。

**测试**：`test_sampling_dataset_binding.py` **14 passed**（含 9 个真实 active 数据集逐个
比对 + superseded→stale 实证 + 朴素实现反向自检）· `test_sampling_evaluation_endpoint.py`
**20 passed**（含 a13 标记保留的反向自检 + 授权顺序源码级断言）。

**零回归基线（`-k "sampling or voucher"` 全量 = 8 failed / 325 passed）**：8 个全部预存在
—— `test_voucher_sampling_batch_wiring.py` ×4 + `test_wp_sampling_engine_seed.py` ×3 是
`asyncio.get_event_loop()` 与其它测试的事件循环互相污染（**单独跑全过**，且移除本 spec
新增测试文件后仍失败）；`test_voucher_sampling_pbt.py::test_mus_sampling_count_within_tolerance`
是 PBT 极小金额边界（`total_amount=0.15` → sample count 9 不在 [10,12]），与算法未改动无关。

**🔴 本轮踩坑（已修）**：`_resolve_project_year` 首版直接 `audit_year, period_end = row`
解包 → 集成测试用 MagicMock db 时 `ValueError: not enough values to unpack` 让
`voucher-history` 整个 500（2 个既有测试打红）。修法不是"迁就 mock"而是**语义上正确**：
history 是只读端点、版本比对只是增强，任何解析失败都应降级为 `dataset_stale=false`
而不是打掉整个列表。

**🔴 判归属的错误方法（记录以免重犯）**：我用「`--ignore` 掉自己新增的测试文件再跑，看失败
是否仍在」来判基线 —— **这是错的**，忽略测试文件不会回退源码改动，那 2 个 history 失败因此
被误判成预存在。正确判据只有一条：**看 traceback 指向的行号是不是自己新加的**
（本例 `voucher_sampling.py:916` 正是新增解包行）。

**🔴 `get_diagnostics` 对本仓库 Python 文件不报类型/名称错误**：新增 `datetime.now(timezone.utc)`
时顶层只 `from datetime import date`，`get_diagnostics` 返回 No diagnostics，靠
`python -c "import app.routers.voucher_sampling"` 才发现。**后端改动一律以真实 import 收尾**。

### Wave 1 Task 5~9 已交付（2026-08-04）—— Wave 1 全部完成 9/9

**前端产出**：
- `useVoucherSampling.ts`：新增 `datasetId` / `loadedFromBatch` / `conclusionConfirmed` /
  `a13PushedAt` 四个状态 + `buildEvaluationPayload` / `persistEvaluation` /
  `loadLatestEvaluation` / `confirmConclusion` / `countDeviations` /
  `pushProjectedToA13` / `buildProjectedMisstatementDescription`；`triggerSampling` 消费
  `stats.dataset_id`（null 时如实提示不阻断）并清 `loadedFromBatch`；`confirmFill` 的
  criteria 增 `dataset_id` + `evaluation`；options 增可选 `wpCode`。
- **`conclusionConfirmed` 从组件收进 composable 作单一真源** —— 回读评价必须能还原确认状态，
  组件级 ref 随 `destroy-on-close` 消失。「结论变化 ⇒ 确认失效」的 watch 一并移入，并加
  **一次性抑制标志** `suppressConfirmInvalidateOnce`：回读时先写结论会触发该 watch，
  把刚还原的确认状态立刻打回 false（表现为"上次确认过的结论重开又要再确认"）。
- `useA13MisstatementBridge.ts`：新增 `MisstatementTypeValue` / `MISSTATEMENT_TYPES` /
  `normalizeMisstatementType`；`MisstatementDraft` 增 `misstatementType`（行级 > 顶层 >
  `factual`，非法值回退而非透传 —— 透传会让后端 enum 拒绝**整批**推送）；
  `draftHash` 增类型维度；删掉硬编码 `misstatement_type: 'factual'`。
- `GtVoucherSamplingEngine.vue`：`onMounted` 回读评价 · 推断/录错报/确认结论三处触发
  `persistEvaluation` · 「记入未更正错报汇总（推断错报）」按钮 + 禁用原因 tooltip +
  已推送时间 tag · 结论区来源批次标注 · 新增可选 `wpCode` prop。
- `Misstatements.vue`：类型下拉补「推断错报」（`typeLabel`/`typeTagType` 本就支持 projected）。

**测试**：新建 `voucherSamplingEvaluation.spec.ts` **30 passed**（Property 5/7/8 + R1.2/R1.3/
R2.5~2.9 全覆盖，含"金额不并入高值层已知错报""持久化失败回滚已推送标记以便重试"
"回读的确认状态不被 watch 打回"三条关键断言）· 新建 `a13MisstatementType.spec.ts`
**21 passed**（Property 6/9 + 2 条 PBT + 源码级"不得再硬编码 factual" + 旧 hash 反向自检
证明类型维度必要 + REPO_ROOT 哨兵文件向上查找）。

**回归**：`voucherSampling / useVoucherSampling / samplingAlgorithms / cutoffAutoSampling /
useA13 / a13Misstatement / confirmationRiskPush / voucherSamplingEvaluation` 共 12 文件
**250 passed / 0 failed**（含既有 `useVoucherSampling.spec.ts` 45 例与
`confirmationRiskPush.spec.ts` 31 例全绿 = 缺省 factual 行为零回归）。
4 个改动文件 Vite transform **全 200**。

**🔴 本轮踩坑（已修）**：
1. `useVoucherSampling.ts` 加 `watch` 未加 import、`voucher_sampling.py` 加
   `datetime.now(timezone.utc)` 未加 import —— **两次 `get_diagnostics` 都返回
   No diagnostics**。前端靠 `python` 读 import 行确认，后端靠真实 `import` 确认。
   → **凡新增用到的模块/函数，收尾必须用「真实执行」验证，不能只看 diagnostics**。
2. 测试 fixture 忘设 `coverageStats.populationAmount` → `inferMisstatement` 的经典比率法
   分母为 0 → `projected` 恒 0 → 7 个断言变成空转（表现为 `expected 0 to be greater
   than 0`）。**构造"已完成推断"的 fixture 必须同时给总体金额**。

**Wave 1 遗留**（不阻塞 Wave 2）：
- 浏览器实测归 Task 24（Wave 4 收口）统一做，届时须验 projected 真落库 + 关弹窗重开还原 +
  历史抽屉「抽样框已变更」告警。
- `wpCode` prop 目前 81 个宿主都没传 → 推断错报的 `source_wp_code` 暂为 null（如实留空，
  不用科目码冒充）。Wave 3 宿主收口时一并补传。

### Wave 2 Task 10/11/15 已交付（2026-08-04）

**删除清单（Task 10）**：`backend/app/services/wp_sampling_engine.py` 整文件 ·
`sampling_enhanced.py` 的 `SamplingExecuteRequest` + `POST /{project_id}/sampling/execute` ·
`wp_functional_actions.py` 的 `elif endpoint == "sampling/execute"` 分支 ·
`backend/tests/test_wp_sampling_engine_seed.py` 整文件 ·
`test_voucher_sampling_characterization.py::TestWpSamplingEngineCharacterization`
（canonical 段一字未动）· `test_wp_functional_actions.py` 的 4 个 `test_sampling_engine_*`。
三处删除点均留下说明注释写明口径差异（金额 `debit+credit` vs canonical `GREATEST`、
分层写死 `0.33/0.66` + 权重 `0.2/0.3/0.5`、MUS 固定 interval、不落日志/不入批次/不可撤销）。

**验证**：真实 import `app.routers.sampling_enhanced` / `app.routers.wp_functional_actions`
通过；`sampling_enhanced.router.routes` 只剩 `cutoff-test` / `aging-analysis` /
`monthly-detail` 三条，`/sampling/execute` **已消失**。

**守卫扩面（Task 11）**：`test_voucher_sampling_canonical_guard.py` 5 → **12 例**。
新增 `_strip_comments()` + `_violating_files()`，断言：模块文件已删 · `backend/app/**`
全仓对 `WpSamplingEngine`/`wp_sampling_engine` 零引用 · legacy 底稿写入点
（`fill_sampling_to_workpaper`/`associate_ocr_evidence`）零残留 · 两个 router 不再暴露
`sampling/execute`；三条反向自检（替身源码必判违规 / `_strip_comments` 真剥注释 /
扫描集合 >100 文件防假绿）。既有 5 条 canonical 断言保留，其中
`test_voucher_extract_does_not_use_legacy_engine` 改为先剥注释再断言。

**🔴 R4.4 判据在实现时被修正**：spec 原写「`backend/app/**` 无生产代码写入
`parsed_data.action_data`」，实测 `wp_functional_actions._fill_parsed_data` 也写它 ——
但那是 functional-actions（截止测试/账龄/月度明细）自身的填充路径，与本次下线的 legacy
抽样引擎无关。强行按原文实现会要求删掉一个不相关的活功能。→ 守卫改为断言**legacy 专有
写入点零残留**，`_fill_parsed_data` 是否也是 dead write 登记为独立议题（见 Notes）。

**软弃用（Task 15）**：`sampling_service.py` 模块 docstring 加 `.. deprecated::`，写明
替代真源是 `sampling_methodology.py`、`sampling_config` 全库 0 行、以及
**`SamplingRecord` 不在弃用范围**（它是 R5.1 定性的 canonical 评价记录表，避免后来者
连它一起弃用）。新建 `test_sampling_config_deprecation.py`（5 例，Property 13）。

**🔴 本轮踩坑（已修）**：`SamplingConfig(` 直接计数会把 ORM 的
`class SamplingConfig(Base):` 类声明算成写入点 → 基线断言首版必红。判据改用
`(?<!class )\bSamplingConfig\(` 只数实例化。

**回归**：`-k "sampling or voucher or functional_actions"` = **5 failed / 343 passed**
（改造前 8 failed / 325 passed）。5 个全预存在：`test_voucher_sampling_batch_wiring.py` ×4
（事件循环污染，单独跑全过）+ `test_voucher_sampling_pbt.py::test_mus_sampling_count_within_tolerance`
×1（PBT 极小金额边界）。原 3 个 `test_wp_sampling_engine_seed.py` 失败随文件删除消失，
**零新增失败**。

### Wave 2 Task 12/13/14/16 已交付（2026-08-04）—— Wave 2 全部完成 7/7

**迁移**：`V139__sampling_registry_batch_binding.sql`（14 条语句，全幂等）—— `sampling_records`
加 `batch_id`/`sampling_method`/`random_seed`/`dataset_id` + 2 索引；`sampled_vouchers` 加
`batch_id` + 部分唯一索引 `uq_sampled_vouchers_batch` + 重复检测索引。ORM 侧
`workpaper_models.py` 同步加了这 5 个 `mapped_column`（**只改 DB 不改 ORM 则写不进去**）。
**已用平台自带 `python -m app.core.migration_runner` 应用**（`schema_version` 已记 139/140）。

**🔴🔴 应用后实测发现设计输入缺陷 → 追加 `V140__sampled_vouchers_manual_scope_unique.sql`**：
既有索引 `uq_sampled_voucher_project_year_no` 是
`UNIQUE (project_id, year, voucher_no) WHERE NOT is_deleted`，即**同一项目同一年度同一
凭证号全库只能有一行**。两个后果：①抽凭登记会撞它抛 `UniqueViolation`（我的
`on_conflict_do_nothing` 只声明了五列索引，撞另一个唯一索引不会 DO NOTHING）→ 除首次
外全部失败且被 fail-open 吞成 WARNING；②「同一凭证被多个底稿重复抽取」这一**需要被
发现的事实**在数据层不可表达 → R5.6 的 `duplicated` 永远为空。
→ V140 把旧索引**放宽**为 `uq_sampled_voucher_manual_project_year_no`
（加 `AND batch_id IS NULL`，只约束 `ledger_penetration` 穿透页的手工标记），抽凭引擎侧
由 V139 的批次索引约束。**不删数据、既有 1 行零违规零变更**。守卫加 4 条钉死两索引语义正交。
**教训：加唯一索引前必须先 `pg_indexes` 查既有唯一约束**，否则 `on_conflict` 目标声明错。

**登记服务**：`backend/app/services/sampling_registry_service.py` —— 5 个纯函数
（`build_population_description` / `build_sampling_purpose` / `build_method_description` /
`build_record_fields` / `resolve_project_year`）+ 4 个写入/查询
（`register_sampling_batch` 按 batch_id upsert · `register_sampled_vouchers` 走
`ON CONFLICT DO NOTHING` · `update_sampling_record_evaluation` · `project_sampling_coverage`）。
**权威/投影分工写进模块 docstring**：权威 = `extraction_criteria`，本模块写的两表是
可查询侧投影。全部写入 fail-open + `logger.warning`（守卫用 caplog 钉死，防静默黑洞）。
`resolve_project_year` 收为单一真源，`voucher_sampling._resolve_project_year` 改为委托。

**接线**：`cutoff_fill` 仅在 `extraction_type == "voucher_sampling"` 时写登记（截止测试
回填不写抽样表）+ 新增 `_load_log_row`（`record_extraction_log` 只返精简 dict，需回读
ORM 行）；`voucher_evaluation` 在 flush 后投影评价；`voucher-extract` 的
`filters.exclude_scope`（**缺省 `'workpaper'` 零回归**）叠加项目级排除；新增
`GET /voucher-coverage`。前端 `SamplingConfig.excludeScope` + 配置弹窗「排除范围」
radio（`excludeScopeModel` computed 默认 workpaper，不写死进 buildDefaultConfig 以免既有
持久化配置被判成"已显式选择"）。

**软弃用**：`sampling_service.py` docstring 加 `.. deprecated::`，明确 **`SamplingRecord`
不在弃用范围**（避免后来者连它一起弃用）。

**测试**：`test_sampling_registry_service.py` **32 passed**（字段映射 11 + fail-open
caplog 4 + 接线 7 + 迁移 4 + 连库 6，含「未评价→None 而非 0」「项目级排除只取 batch_id
非空」「两索引语义正交」）· `test_sampling_config_deprecation.py` **5 passed**（Property 13）。

**回归**：`-k "sampling or voucher or functional_actions or migration_runner"` =
**5 failed / 434 passed / 10 skipped**。5 个全预存在（batch_wiring ×4 事件循环污染 +
PBT MUS 极小金额 ×1），**零新增失败**。

**🔴 本轮踩坑**：①`SamplingConfig(` 直接计数会把 ORM `class SamplingConfig(Base):`
算成写入点 → 判据改 `(?<!class )\b...\(` ②`migration_runner` CLI 最后一行 `print("✅ ...")`
在 GBK 控制台抛 `UnicodeEncodeError` —— **迁移本身已成功提交**，看日志行不要看 exit code。

### 追加交付：跨底稿重复抽凭显式确认（2026-08-04，用户追加要求 R8）

**需求变化**：用户明确要求「同一凭证被多个底稿抽取，需要弹窗提示用户手动确认」。
这**修正了 R5.5 的设计取向** —— `exclude_scope` 二元开关（静默剔除 / 完全不提示）把本该
由审计师做的判断交给了配置项。重复抽同一张凭证有时是**有意的**（不同循环从不同认定角度
检查同一笔交易），有时是**样本浪费**（覆盖率虚高），必须显式表态并留痕。
`exclude_scope` 保留作为"我就是要一律排除"的快捷选项（缺省仍 `workpaper`）。

**后端**：`cross_workpaper_duplicate_vouchers`（排除当前底稿 R8.2 / 只算 `batch_id` 非空的
引擎登记行 R8.3 —— 穿透页手工标记不是"已执行抽凭程序"，据它提示会全是噪声 /
JOIN `wp_index` 取 wp_code，因 `working_paper` 表无该列 / fail-open + WARNING R8.9）；
`voucher-extract` 新增返回 `cross_workpaper_duplicates`。

**前端**：`confirmCrossWpDuplicates()` 在**打开预览之前**弹框（否则审计师已经在看样本了
才被问，判断顺序颠倒）。三出口用 `ElMessageBox` 的
`distinguishCancelAndClose`：confirm=保留全部 / cancel=剔除重复项 / close=取消本次抽样。
取消时**清空样本且不打开预览**（不留半套样本）；剔除后无剩余样本时同样不打开预览并提示重抽。

**🔴 剔除后覆盖率重算：分母（总体）保持不变**。用剩余样本当分母会让覆盖率虚高到 100% ——
那正是本功能要避免的问题。守卫含一条反向自检断言 `countCoverageRate !== '100.00'`。

**留痕**：`extraction_criteria.duplicate_decision`（`keep_all|removed|none`）+
`duplicate_voucher_nos`（**removed 时也记**，便于复核追溯"哪些被剔了"）。

**测试**：`crossWorkpaperDuplicateConfirm.spec.ts` **17 passed**（三出口后果 / 覆盖率分母
反向自检 / 文案截断 / 项目级排除下不重复提示 / 重抽状态重置 / 后端未返回该字段的向后兼容）
+ 后端 4 例（接线 / 范围 / fail-open caplog / 空输入不查库）。
`test_sampling_registry_service.py` **36 passed**；前端 9 文件 **267 passed / 0 failed**；
`useVoucherSampling.ts` Vite 200。

### Wave 3 Task 17/18 已交付（2026-08-04）

**共享件** `composables/shared/samplingFillTarget.ts`（零 Vue 依赖纯函数）：
`SamplingMethodologySnapshot` · `SAMPLING_METHOD_LABELS`（与后端
`sampling_registry_service._METHOD_LABELS` 键集一致，守卫钉死）·
`samplingMethodologyItemKey(wpCode)`（`{wpCode}-sampling-methodology`，空 wpCode 回退无前缀
而非产出 `-sampling-methodology`）· `buildMethodologySummary`（**只渲染有值项** ——
归档件上的「间隔: -」无法与「取不到」区分）· `hasMethodologyContent`（bar 渲染门控）·
`serializeMethodology`/`parseMethodology`（空内容不落库、解析失败返 null 而非半个对象）·
`mapSampledToGenericRow`/`mapSampledRows`（6 字段最小集，camelCase 与 snake_case 双兼容，
非法金额归 0 不产 NaN，非对象输入不抛错）。

**展示组件** `shared/WpSamplingMethodologyBar.vue`：紧凑单行 bar（13px、左侧主色边线、
`tabular-nums`），`methodology` 无内容时整条不渲染；种子/批次/账套版本带 tooltip；
**未绑定账套版本时显示 info tag**（如实提示不可复算）。

**🔴 本轮踩坑（已修）**：
1. `DisplayPrefs_Key` **不在** `@/stores/displayPrefs`，而在
   `components/workpaper/composables/displayPrefsKey.ts`（全平台 20+ 处都从那里 import）。
   memory 记的是通用范式，具体符号位置须实测。
2. **PowerShell 双引号字符串里反引号是转义符** —— `python -c "...'- [ ] 17. 共享件
   \`composables/...\`'..."` 里的反引号被 PS 吃掉，替换静默不命中（`done` 计数没变才发现）。
   → 含反引号的文本替换一律用 `str_replace`，不用 `python -c`。

**测试**：`samplingFillTarget.spec.ts` **29 passed**（含 3 条 PBT + 「样本量 0 且其余全空
不算抽过样」+ 「缺省项不出现 `-`」+ 「往返无损」+ 「非法金额不产 NaN」）。
两个新件 Vite transform **200**。

**Wave 3 剩余**：Task 19/20/21（42 个宿主接线，按 D/E/F ×14、G ×12、H/I/K ×16 分批）
+ Task 22（平台守卫 `samplingHostMethodologyCoverage.spec.ts`）。
**建议先做 Task 22 再做 19~21** —— 守卫会打红全部 42 个未接宿主并给出**权威工作清单**，
避免"接了但没接对"（如只渲染 bar 没持久化、或映射漏字段）。

### Wave 3 Task 22 已交付（2026-08-04）—— 并修正三处立项数字

**产出**：`components/workpaper/__tests__/samplingHostMethodologyCoverage.spec.ts`（**24 例**）
+ `shared/__tests__/WpSamplingMethodologyBar.spec.ts`（**14 例**，覆盖 Property 17 的
**渲染侧** —— 门控 / 字段集 / 金额千分符两位小数 / 批次与账套版本截断 8 位而 tooltip 给全量 /
未绑定账套版本如实提示；纯函数侧由既有 `samplingFillTarget.spec.ts` 29 例覆盖，两者不重叠）。
回归：`voucherSampling / samplingFillTarget / samplingAlgorithms / cutoffAutoSampling /
a13Misstatement / crossWorkpaperDuplicate / WpSamplingMethodologyBar / samplingHostMethodology`
共 **15 文件 306 passed / 0 failed**。

**守卫形态**：单一 allowlist `HOST_WIRING_ALLOWLIST`（宿主文件名 → {未满足要求 → 理由}），
四个要求键 `methodology`（R6.3 消费）/ `persist`（R6.3 落 `samplingMethodologyItemKey`）/
`bar`（R6.4）/ `fields`（R6.5 最小字段集）。单调收敛靠**豁免总数**
`ALLOWED_EXCUSE_BASELINE`（当前 **275**）只许调小，外加「allowlist 不得残留已修好的豁免」
一条强制变短。薄壳 `v-bind="$props"` 视为已满足。字段集判定会跟进 `@filled` 处理函数
**一级相对 import**（D3 这类把映射交给 `useD3VoucherCheck.fillFromSampling` 的宿主，
不跟进去看会把「映射写在 composable 里」误判成「没映射」）。

**🔴🔴 守卫自己抓到一个真缺陷（先打红自己）**：第一版用正则
剥块注释，模板里 `accept="image/*,.pdf"` 的斜杠星号被当成块注释起点，一直吞到几千字符后的
结束符 → **`G6TabVoucherCheck.vue` 与 `K8TabSellingCheck.vue` 两个真实宿主静默逃出扫描面**
（少扫 2 个文件守卫还是绿的 = 典型假绿）。改为**带字符串状态的扫描器** + 分区处理
（`<style>` 整段丢 / 模板只剥 HTML 注释 / 只在 `<script>` 区剥 JS 注释），并留两条回归断言
钉死这两个文件必须在册。**同族教训**：JSDoc 里不要写含块注释结束符的正则字面量 ——
`\*\//g` 会提前闭合注释，esbuild 报 `Expected ";" but found "https"`（错误位置指向几行后的
无关字符串，极易误判）。

**🔴 修正立项时的三处数字（守卫是数据驱动的，以它为准）**：
1. **宿主是 78 个不是 81 个**（判据 = 模板里真实出现 `<GtVoucherSamplingEngine`；只在注释或
   文档里提到引擎名的不算，如 `L8TabCutoffTest.vue`）。
2. **真正消费 `methodology` 的只有 9 个，不是「81 个里 42 个丢弃」** —— 立项数字是按
   「源码出现 methodology 字样」判的，把说明注释与 CSS 类名 `methodology-context`
   （多个宿主用它做方法论提示块的琥珀色边线）都算成了消费。实测 78 个宿主里 **69 个完全不消费**。
   在册的 9 个：`D2TabVoucherCheck` / `D4TabOccurrence` / `G12TabVoucherCheck` /
   `I2TabTargetedCheck` / `I3TabTargetedCheck` / `I4TabTargetedCheck` / `I5TabTargetedCheck` /
   `K4TabCheck` / `K8TabSellingCheck`。
3. **Task 20 列的 `G3TabCalcCheck.vue` 不是宿主**（文件存在但全文无 `GtVoucherSamplingEngine`）
   → G 类实际待接 **11 个**不是 12 个。

**因此 Task 19/20/21 的 42（实为 41）个宿主只覆盖真实缺口的一部分**：另有 **37 个宿主**
（K/M/N/I/J/D1/D2/D4/G11/G12/H6 等）同样未满足 R6.3~R6.5，已在 allowlist 里以
「归抽凭表共享层 spec」登记理由。是否把它们纳入本 spec 需用户裁决 —— 它们的行模型由 19 份
per-cycle `useXVoucherCheck` 各自定义，正是 `voucher-check-shared-layer` 的半径。

**诊断出口**：守卫支持 `SAMPLING_HOST_SCAN_OUT=<abs path>` 落盘 JSON（Task 19~21 取权威
工作清单用；不设该变量时是空操作，CI 零副作用）。理由：控制台中文在 GBK 终端会被腌坏，
逐个 grep 又容易漏。

### Wave 3 Task 19 部分交付（2026-08-04）—— methodology/persist/bar 已接，字段集留残

**新增共享接线件** `composables/shared/useSamplingMethodologyPersist.ts`（+ 守卫 9 例）：
收口「键名 / 序列化 / 读回 / 只读门控」四件确定的事，**持久化动作由宿主注入**。
理由：实测各循环写库机制并不统一 —— D/F1 是 `props.saveImmediate(itemId, data)`、
E1 是 `props.saveImmediate(items[])`（**同名不同签名**）、F2/F3/F4/F5 各走自己的
`window.dispatchEvent('f2-val|f2-spe|f3|f4|f5:save-items')`。硬把某一种写进共享件，
等于让另外两种循环无法接入。另两条防线：只读态不写库；**载荷无实质内容不写空壳**
（「没抽过样」与「抽了但没留痕」必须可区分）。

**14 个宿主已接 R6.3 消费 + R6.3 固定 item key + R6.4 bar**（D3 手工接作范式，其余 12 个
走幂等脚本 + F2ValuationTestSheet 单独处理）。验证：`get_diagnostics` 全绿 + **漏 import
专项核查 13/13 OK**（平台已知 `get_diagnostics` 查不出漏 import）+ **15 个文件 Vite
transform 全 200**。定向回归 16 文件 **316 passed / 0 failed**。

**F2ValuationTestSheet 是「向上再抛」的展示件**（`emit('samplingFilled')`，无 `allResponses`）
→ 加 `methodology` prop + 渲染 bar + emit 类型带上 methodology 原样上抛，落库留在父级
（F2-38/39/40 宿主）。这一条在 allowlist 里以「展示件无落库能力」显式登记。

**🔴 未完成项（Task 19 因此仍标未完成，不得当已交付）**：13 个宿主的**样本映射缺
「科目编码」**（`accountCode`），仅 `E1TabLargeCheck` 有。原因不是漏写一行 —— 这些宿主的
映射写在 per-cycle composable 里（`useD3VoucherCheck.fillFromSampling` /
`useF3VoucherCheck.applySamplingResults` / `useF2*Check.fillFromSampling` /
`adj.mergeSamplingRows` 等约 10 个），补字段要动**各自的行模型与列定义**，
正是 `voucher-check-shared-layer` 的半径。已在 allowlist 逐条登记理由，**豁免总数
275 → 255**（只许继续变短）。

**🔴🔴 守卫第二版自己又抓到一个假绿（已修）**：宿主为类型断言写了
`import type { SamplingMethodologySnapshot } from '.../samplingFillTarget'`，而该符号出现在
`filled` 处理函数体里 → 一级委托解析把 `samplingFillTarget.ts`（**最小字段集的定义方**）
拉进来当「字段来源」→ **任何接过线的宿主都自动通过字段集判定**。修法 = 类型 import 一律
不计 + `FIELD_SCAN_EXCLUDED` 排除两个共享定义件，并留一条替身反向自检钉死。
**教训：跟进委托解析时必须区分「谁在映射」与「谁在定义字段」**。

**零回归判定**：`src/components/workpaper` 全量 **22767 例 / 427 failed / 39 文件**，
逐个核对后**427 个失败的 traceback 无一落在本次改动的文件上**（失败集中在
K3~K13 / L4·L6·L7 / B23 / J2 / G7 / `runtimeImportSmoke` 的 K 类 componentType 动态加载，
本次一个都没碰）。判据 = 把全部 failureMessages 里的文件路径与本次改动清单求交集 = 空集。
**不用 `--ignore` 自己的测试文件当基线**（忽略测试文件不会回退源码改动）。

### Wave 3 Task 20/21 + Wave 4 Task 23 已交付（2026-08-04）

**27 个宿主接线完成**（G 类 11 + H/I/K 类 16），三件齐备：methodology 消费 + 落
`samplingMethodologyItemKey` + 渲染 `WpSamplingMethodologyBar`。**27/27 Vite transform 200**，
漏 import / 多行 import 被切断 / bar 重复渲染 三项专项核查 **0 问题**。
守卫豁免总数 **275 → 174**（4 个宿主已全绿）。

**共享件补两个出口**（因 Task 20/21 宿主写库机制比 Task 19 更杂）：
- `buildChecklistDirectPersist({wpId, projectId})` —— 走平台既有 checklist-responses
  端点（全仓 40+ 处同形），给**既无 save prop 也无 `emit('save')`** 的 18 个宿主兜底
  （G4/G5/G6/G7/H1~H5/I2/I6 这批把持久化封在 per-cycle composable 里、对外不暴露写入口）。
  **有 save prop 的宿主不用它** —— 那会绕过父级的批量/防抖与 autoSnapshot。
- `snapshotToResponseMap(htmlData)` —— 从 render-config 的 `responses_snapshot` 构造只读
  响应表，给**没有 `allResponses` prop** 的 5 个宿主（G4/G5/G6/G7×2）提供读回通道；
  数组与对象两种形态都认，解析不出返回空表（读回是增强，失败不阻塞抽凭）。

**写库形态实测分布**：`PROP_DEBOUNCED` 7 · `EMIT_SAVE` 2（H8/K1，签名 `(itemId, value)`）·
`DIRECT` 18。

**🔴 批量插 import 的坑（3 个文件被打崩，已修）**：按「最后一条 `^import ...` 行」定位插入点，
而 G4/G6/H1TabAdditionCheck 有**多行 import**（`import {` 换行续写）→ 三行新 import 被插进
那条语句中间 → `[vue/compiler-sfc] Unexpected keyword 'import'`。**`get_diagnostics` 全绿，
只有 Vite transform 500 暴露**。正解 = 插到**第一条完整单行 import**之后（它一定是
`import { ... } from 'vue'` 这类不会被切断的语句），并加「`import {` 行之后不得紧跟另一条
import」的专项核查。

**Task 23 CI**：`governance-checks.yml` 新增 `sampling-compliance-backend` 与
`sampling-compliance-frontend` 两个 job（jobs 113 → 115）。按 job 里声明的命令**逐段实跑**：
前端 7 文件 **148 passed**；后端 14 + 47 + 37 = **98 passed 零 skip**。

**🔴🔴 CI 挂载时抓到一个假绿（这条最重要）**：把 5 个后端守卫文件放进**同一个 pytest 进程**
时结果是 `91 passed, 7 skipped` —— 那 7 个是 `test_sampling_registry_service.py` 的**连库断言**
（Property 11 唯一索引防重等），被 fixture 以「数据库不可用（`AttributeError: 'NoneType'
object has no attribute 'send'`）」静默跳过。根因是连接池绑定首个事件循环，同进程第二个连库
文件必炸。**单独跑该文件是 47 passed 零 skip**。→ CI 里把两个连库文件各自拆成独立进程，
并各加一条「输出中不得出现『数据库不可用』」的断言步骤，否则守卫挂了也是空转。

**🟡 顺带发现（非本次引入，登记为独立议题）**：`governance-checks.yml` 里
`note-m-equity-structure` **job 名重复两次**（HEAD 就有），YAML 静默保留最后一个 →
其中一个 job 从未运行过。属 M 循环 spec 侧。

**遗留 Task 24**（浏览器实测 + 真实库验证 + 数据复原）：需完整浏览器交互与 postgres 落库
核查（抽样 → 录实际错报 → 推断 → 确认结论 → 推送 A13 → 查 `misstatement_type='projected'`
→ 逐字段复原），未做。**实测三件套缺一不算实测**。

### 字段集（R6.5）归属裁决依据 + 彻底解决路径（2026-08-04）

**先修了守卫两处精度缺陷，才拿到可信数字**（此前 `fields` 缺 71 是低报）：

1. **🔴🔴 `extractFunctionBody` 把参数的内联类型字面量当函数体**（低报主因）：
   抽凭宿主的处理函数普遍写成
   `function onSampleFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode })`，
   而旧实现取「声明之后的第一个 `{`」→ 命中的是**参数类型**，截出来的"函数体"是那段类型
   声明 → **委托解析恒为空** → 把「映射写在 composable 里」全判成「没映射」。
   正解 = 先用**圆括号配对**跳过整个参数列表再找 `{`。
2. **跟不进 setup 层解构**：`filled` 处理函数体里出现的是 `applySamplingResults`
   （解构出的成员名），相对 import 的却是 `useF3VoucherCheck` → 只按 import 符号匹配跟不进去。
   新增 `destructuredComposableMap`（支持 `a` / `loading: x` / `b = 1` 三形态）。

修后：`fields` 缺 **71 → 48**，全绿宿主 **4 → 14**，豁免总数 **174 → 151**。

**41 个在册宿主的准确残留**（全绿 14 / 仅剩 fields 26 / F2ValuationTestSheet 是 persist+fields）：

| 缺失组合 | 宿主数 | 性质 |
|---|---|---|
| 仅缺「科目编码」 | **17** | **判据问题**，见下 |
| 缺 凭证日期 + 金额 + 科目编码 | 4（F2 四个，委托 0 = 映射就在宿主内） | 真缺口 |
| 缺 凭证日期 + 科目编码 | 4（G6 / H4TabDisposalCheck / H5×2） | 真缺口（日期） |
| 缺 金额 + 科目编码 | 1（H10TabCheck） | **判据不适用**，见下 |
| 仅缺 凭证日期 | 1 | 真缺口 |

**37 个范围外宿主**：全绿 0（methodology 28 / persist 37 / bar 37 / fields 21）。

#### 判据本身的两处偏差（这是「17 个只缺科目编码」的根因，非实现缺口）

- **「科目编码」是抽样参数不是逐样本属性**：**41/41 宿主都把本科目码作为常量传给引擎**
  （`account-code="1601"` / `:account-code="G9_ACCOUNT_CODE"` / `:account-code="codes.join(',')"`），
  且已由 `methodology.accountCodes` 承载并经 bar 渲染到底稿正文（R6.4 本轮已交付）。
  逐样本再存一遍是冗余。**25/41 宿主读的 `counterpartAccount` 是「对方科目」**
  （序时账来源、memory 记填充率仅 ~9%），与本科目码不可互替。
- **四要素对部分行模型语义不成立**：`H10CheckRow` 是**合规检查项行**
  （`CHECK_FIELDS` 取值 `non_compliant`），只保留 `${date}/${no}` 复合标签 + 资产名 ——
  金额/科目码在该模型里没有位置，塞进去是加错列。`F2ValuationTestSheet` 的行是
  「存货品种 × 重算差异」，同理。

#### 🔴🔴 追查后结论升级：所谓「真缺口」大部分是守卫低报，共 **4 条低报通道**

按「先核实再动手」逐个查下去，前面列的 9 个「真缺口」里绝大多数**不是缺口**：

| # | 低报通道 | 实证 |
|---|---|---|
| 1 | **`extractFunctionBody` 把参数的内联类型字面量当函数体** | `function onSampleFilled(payload: { samples: ... })` 的第一个 `{` 是参数类型 → 委托解析恒为空。**低报主因** |
| 2 | 跟不进 **setup 层解构** | `const { applySamplingResults } = useF3VoucherCheck(...)` |
| 3 | 跟不进 **对象式 composable** | `const ic = useF2MaterialUsageCheck(...)` 后 `ic.fillFromSampling(...)` —— F2 四个宿主全是这形态，而 `useF2InspectionCheck.mapVoucherToRow` **确实映射了借贷金额**（`amount = preferDebit ? ... : ...`） |
| 4 | 跟不进 **`@/` 别名 import** | G6 的映射件在 `@/composables/useG6EclVoucherCheck`，其第 471 行写着 `sample.voucherDate ?? sample.date` —— **日期本来就映射了** |

四条全修后：`fields` 缺口 **71 → 44**，全绿宿主 **4 → 16**，豁免 **275 → 147**。
每条都配了替身反向自检钉死（复现旧行为必打红）。

**修完后的字段集缺失分布（全 78 宿主）**：27 只缺科目编码 / 9 缺日期+科目 /
3 缺金额+科目 / 2 只缺日期 / 2 缺日期+金额+科目 / 1 缺全四类。

**另一条独立结论：即便是真缺的，也多半不该按现判据补**。逐个查行模型：
- `PurchaseInboundRow` / `MaterialUsageRow`（F2）**没有凭证日期字段** ——
  只有 `recvDateNo` / `invoiceDateNo` / `docDateNo`（**源单据**日期号，不是记账凭证日期）
- `useH4DisposalCheck` 只有 `disposalDate`；`useH5AdditionCheck` 只有
  `approvalDate` / `paymentDate` —— 全是**业务事件日期**，与记账凭证日期是不同维度
- `D5TabDetail` 的行是「明细项目 × 期初/期末/本期增减」的**科目明细表行**，不是凭证明细行
- `H10CheckRow` 是**合规检查项行**，金额/科目码在该模型里没有位置

→ 往这些行里加「凭证日期」列，得先回源模板确认该表有没有这一列，否则是**自造披露/底稿列**
（违反「增强打磨禁止自造内容」铁律）。

#### 彻底解决 = 三块，按依赖排序

**第一块（本 spec 内）—— 已做完：修守卫 4 条低报通道**
原本以为是「补 6~9 个宿主的真缺口」，逐个核实后发现绝大多数是低报（见上表）。
四条通道已全部修好 + 反向自检，豁免 275 → 147。
**剩下的字段集残留没有一条能在不动 per-cycle 行模型（且不先回源模板核对列）的前提下补掉。**

**第二块（需用户裁决）—— 判据分层，且必须是「收紧」不是「放宽」**
建议落法（不是简单删掉科目编码这条）：
- **层 1「样本可回溯」，全体 78 个宿主强制**（新增，收紧）：凭证号 或 `date/no`
  复合标签至少其一 —— 直接拦住立项描述的「只做 `addRow(v.summary || v.voucherNo)`」。
- **层 2「凭证明细四要素」，仅凭证明细型宿主强制**：凭证号 + 日期 + 金额 +
  **科目来源**（判据 = 逐行 `accountCode` **或** 该宿主已渲染方法学 bar）。
- 宿主类型**声明式登记** `HOST_ROW_MODEL_KIND`（`voucher-detail` / `compliance-checklist` /
  `valuation-test`），每条写理由，且**登记为非凭证明细型的宿主数量只许变少**
  （防判据被当逃逸阀）。配反向自检：把 H10 强标 `voucher-detail` 时必须打红。

**第三块（另立 `voucher-check-shared-layer`）—— 37 个范围外宿主 + 19 份 `VoucherCheckRow` 统一**
必须另立：要动 19 个 per-cycle 行模型 + 列定义 + 持久化键，且核对项形态已漂移
（D2 是 `check1..check5: string`，D3 是 `checkItems: [boolean×5]`）。

**⛔ 明确不建议的做法**：把 17 个「只缺科目编码」按现判据逐个补一行 `s.accountCode` ——
那是往行里塞一个整批恒等的常量，既冗余又会让守卫从此失去区分力（真缺日期/金额的宿主
和只缺冗余字段的宿主变成同一档）。

### 追加交付：确认填充门控可达性 + 往来单位自动带出（2026-08-04 浏览器实测驱动）

本轮由 Task 24 实测暴露两个真实缺陷（都不是「没实现」，是「实现了但用户到不了」）。

#### 缺陷 1：R18.7 结论确认门禁的提示是死信

现象：预览弹窗里点「确认填充」→ 顶部飘一条「请先在下方『错报推断与总体结论』区确认结论」，
但**预览弹窗盖在上面且不关闭**，那个区域既看不到也点不到 → 用户只能关弹窗，而关掉后
**没有重开入口**，只能重抽（换 seed 破坏留痕，正是 R1 要防的事）。

门控本身是审计正确的（UML 未经确认不得定稿回填），错的是可达性。三处修复：

1. `SamplingPreviewDialog.vue` 把门控**前置**为 `:disabled` + tooltip（复用同文件
   「年审阶段不可覆盖预审数据」范式），新增可选 prop `confirmBlockedReason`
   —— **缺省 `''` 时行为逐字不变**（零回归支点）。
2. `GtVoucherSamplingEngine.vue` 派生 `confirmBlockedReason`，命中时**先关预览再提示**
   （否则提示指向的区域仍被遮挡）。
3. 操作栏新增「查看抽样结果」按钮（`sampledVouchers.length > 0` 时可用）→ 确认结论后
   可重开同一批样本继续填充，不必重抽。

守卫 `samplingConfirmFillReachability.spec.ts`（**16 例，含 6 条反向自检**）：
tooltip 与关闭后提示指向**不同动作**（前者「先确认结论」/后者「已关闭预览」）·
缺省空串必须行为不变 · 重开按钮门控 · 「先关弹窗后提示」的语句顺序（源码级，
`stripComments()` + 反向自检）。

#### 缺陷 2：抽凭回填后「客户名称」列永远空白（真缺陷，可修）

用户报「客户名称 / 对方科目 / 对方明细三列回填后都是空的」。逐列查完**三条成因各不相同**，
只有第一条是代码缺陷：

| 列 | 前端映射 | 数据层实证 | 判定 |
|---|---|---|---|
| 客户名称 | `customerName: ''` **写死** | `tb_aux_ledger` 该项目 **273 万行**，含 `voucher_no`/`voucher_date`/`account_code`/`aux_name` | **真缺陷：有来源没接** |
| 对方科目 | `counterAccount: s.counterpartAccount` 已正确接线 | `tb_ledger.counterpart_account` 全库 **1,118,735 行 0 填充** | 数据层缺失，非 bug |
| 对方明细 | `counterDetailAccount: ''` 写死 | 全库无对应列 | 无来源 |

**「按同凭证其它分录派生对方科目」这条路已实证不可行**：`voucher_no + voucher_date`
不是凭证身份键 —— 63 个凭证组平均 **94.8 行**、其中 **40 组有多条对方分录** → 必然算错。
故对方科目/对方明细如实留空（宁缺勿造），不做启发式猜测。

**客户名称落法**：后端新增 `enrich_items_with_aux_party`（`ledger_sampling_service.py`），
按「凭证号 + 日期 + 科目 + 借方 + 贷方」**五元组**匹配 `tb_aux_ledger`：
- 只加法：不改 canonical 查询、不改 `_ledger_row_to_item`，挂在 `voucher-extract` 返回前
- **歧义不猜**：一键多名时只标 `party_ambiguous=True`，不写名称
- fail-open + WARNING，且**缺省键先声明**（让「查询失败」与「本项目无辅助明细」表现一致）
- 维度类型白名单 `AUX_PARTY_TYPES = (客户, 供应商, 往来单位, 职员)`

**真实库实测（项目 `2aa00f57` / 2025）**：

| 科目 | 命中 | 歧义 | 说明 |
|---|---|---|---|
| 2203 预收账款 | **170/170 = 100%** | 0 | 截图里那张表 |
| 2202 应付账款 | **300/300 = 100%** | 0 | |
| 1122 应收账款 | 281/300 = 93% | **19（正确地不写）** | |
| 1002 银行存款 | 0/300 | 0 | 该科目本无客户维度，如实留空 |

唯一性旁证：全项目 52.8 万个五元组键里 **527,575 组唯一 / 1,293 组多义（99.76% 唯一）**；
只用「凭证号+日期+科目」四元组则 2203 下就有 19 个键歧义 → **金额必须进匹配键**。

前端三处接线：`SampledVoucher` 增 `partyName`/`partyAuxType`/`partyAmbiguous` ·
`useVoucherSampling` 映射 snake/camel 双兼容 · `useD3VoucherCheck.mapSampledToVoucherRow`
写入 `customerName`（歧义时留空并在 remark 标注）· 共享 `mapSampledToGenericRow` 同步
（**全部宿主受益**）。

**🔴🔴 只有真实库能暴露的 bug（已修）**：`sa.table()` 的裸 `sa.column()` **无类型信息**
→ asyncpg 把 `project_id` 当 VARCHAR 传参 → PG 报
`operator does not exist: uuid = character varying`，整个补全被 fail-open 吞成一条 WARNING
（界面表现与「本项目没有辅助明细」**完全一样**）。修法 = 显式声明列类型
（`sa.column("project_id", PGUUID(as_uuid=True))` / `Date` / `Numeric` / `Boolean`）。
自造 fixture 与替身 session 测不出这类问题 —— **凡用 `sa.table()` 拼查询必须真实库直跑一次**。

#### 字段集判据分层已落地（原「待用户裁决」的方案 A）

`missingFieldCategories` 拆两层：
- **层 1「样本可回溯」全体 78 个宿主强制**（新增，是**收紧**）：凭证号 或 `date/no`
  复合标签至少其一 —— 直接拦住「只 `addRow(v.summary || v.voucherNo)`」
- **层 2「凭证明细四要素」仅 `voucher-detail` 型强制**：凭证号 + 日期 + 金额 +
  **科目来源**（逐行 `accountCode` **或**已渲染方法学 bar —— `accountCodes` 已在 bar 上）
- 宿主类型走 `HOST_ROW_MODEL_KIND` **声明式登记**（`compliance-checklist` /
  `valuation-test` / `no-voucher-date`），每条写源模板依据，且**非凭证明细型登记数只许变少**

源模板核对结论（openpyxl 直读，**这是分层的依据不是借口**）：
- `H10TabCheck` = 合规检查项行（`CHECK_FIELDS` 取值 `non_compliant`），源模板该表无金额列
- `F2TabPurchaseInboundCheck` / `F2TabMaterialUsageCheck` —— 源模板 `F2-33`/`F2-34` 表头
  只有 `凭证编号`，**没有凭证日期列**（有的是 `入库单/验收单 日期/编号` 等源单据日期）
- `H4TabDisposalCheck`（源 `减少检查表H4-5` 表头 `入账凭证号`，无日期列）/
  `H5TabAdditionCheck`（`增加检查表H5-7` 的 `增加日期` 是业务事件日期）/ `H5TabDisposalCheck`
- `F2ValuationTestSheet` = 计价测试（源 `F2-38`~`F2-40` 行是月份/日期 × 数量单价金额）

→ 往这些行里加「凭证日期」列**先要回源模板确认该表有这一列**，否则是自造底稿列。

结果：41 个在册宿主 **`fields` 全部满足**；豁免总数 **147 → 122**；剩 19 个带 fields
豁免的全是范围外宿主（归 `voucher-check-shared-layer`）。守卫新增 8 例分层断言，
含 3 条反向自检（H10 强标 `voucher-detail` 必红 / F2 两表强标必因缺日期红 /
层 1 确实抓到「样本一条都不进底稿」）。

**回归**：前端 `samplingHostMethodologyCoverage` + `samplingFillTarget` +
`samplingConfirmFillReachability` 等 **21 文件 88 passed 0 failed**；抽样全链
**125 文件 393 passed 0 failed**；后端 `test_sampling_dataset_binding` +
`test_sampling_evaluation_endpoint`（51）与 `test_sampling_registry_service`（47）
**全绿零 skip**。6 个改动前端文件 Vite transform 全 **200**。

**🔴 本轮踩坑**：①改分层判据后，守卫**自己的一条反向自检过时**（断言 F3 替身应缺 fields，
而分层下它已合格）→ 改为断言「委托解析确实生效」（三类字段不再缺）+ 显式说明科目来源
由 bar 满足。**改判据必须同步复核自己的反向自检**，否则会误判成回归。
②`toEqual` 严格比对会因新增字段打红（`mapSampledToGenericRow` 加 `partyName` 后）——
那是测试镜像旧结构，补字段并加一条往来单位专项断言。

## Notes

- **零回归铁律**：每波结束跑既有测试全绿；任一断言不符即停在该步，禁止放宽断言 / 换参数 /
  跳过用例绕过（R7.1）。判「失败是否预存在」：**看 traceback 行号是否落在本次新增/修改的
  行上**（`--ignore` 自己的测试文件不构成有效实验，见 Progress Log）。
- **🟡 对方科目/对方明细两列如实留空（数据层缺失，已实证，非本 spec 可修）**：
  `tb_ledger.counterpart_account` 全库 0 填充。若将来导入侧补齐该列，前端映射
  （`counterAccount: s.counterpartAccount`）**已接好、无需改动**即自动生效。
  「按同凭证其它分录派生」已被实证否决（凭证键不唯一，40/63 组有多条对方分录）。
- **🟡 新登记的独立议题（不属本 spec）**：`wp_functional_actions._fill_parsed_data` 把
  截止测试/账龄/月度明细的取数结果写进 `working_paper.parsed_data.action_data`，而前端全仓
  grep `action_data` **只有 `useWpFunctionalActions.ts` 里一条注释**（无真实读取点）→ 疑似
  与已删除的 legacy `fill_sampling_to_workpaper` 同款 dead write。需单独核实
  functional-actions 的回填在前端到底从哪读，再决定处置。
- **canonical 链路不动**：`execute_sampling` / `locate_sampling_units` /
  `fetch_by_unit_ids` / `build_methodology_snapshot` / `record_extraction_log`
  的行为逐字节不变。`test_voucher_sampling_*` 的 canonical 段是零回归锚点。
- **并发会话风险**：本 spec 会改 `voucher_sampling.py`、`useVoucherSampling.ts`、
  `useA13MisstatementBridge.ts`。改前先看 mtime；`read_file` 对并发改动的文件会返回陈旧
  版本，判磁盘真相用 `python -c "open(p,encoding='utf-8').read()"`。
- **迁移取号**：磁盘最高 V138 且 `schema_version` 已记 138 → 本 spec 用 **V139**。
  建迁移前复查一次（并发会话可能已占号）。
- **Wave 边界**：Wave 1 三个任务组必须整波交付才有合规意义（缺 R3 则评价存了但进不了错报
  汇总；缺 R2 则 R3 没有可推送的持久化来源；缺 R1 则整条留痕不可复算）。
- **不在本 spec**：19 份 per-cycle 抽凭表共享层（另立 `voucher-check-shared-layer`）；
  `checkCAS1314Compliance` 的 60% 阈值硬编码与 MUS 规则 3 语义打架（需先浏览器实测确认是否
  恒不触发，再决定归属）；总体完整性核对失败的阻断策略、未检查样本「视同偏差」处置、
  偏差性质结构化字段（三者属 CAS 1314 细项增强，建议合并为一个后续 spec）。
- **待用户裁决（不阻塞 Wave 1/2/3）**：`sampling_config` 是否最终删表删端点（本 spec 只做
  软弃用）；跨底稿排除是否应改为默认开启（本 spec 默认关闭保零回归）。
