# Implementation Plan

## Overview

行为保持式重构：每波结束跑零回归门（后端 `test_voucher_sampling_integration` + `test_cutoff_sampling_pbt`/`integration` + 前端 `useVoucherSampling.spec`/`useSamplingAlgorithms.spec` 全绿）。动手前重读最新源码防并发覆盖。金额一律 Decimal 字符串。四轴（抽样正确性 / 数据治理 / 架构收敛 / 安全）互不阻塞、各自内部有序，可选轴（Task 13/14）末位。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "name": "安全网+脚手架", "tasks": ["1", "2"], "dependsOn": [] },
    { "wave": 1, "name": "抽样正确性轴", "tasks": ["3", "4", "5", "6"], "dependsOn": [0] },
    { "wave": 2, "name": "数据治理轴", "tasks": ["7", "8"], "dependsOn": [0] },
    { "wave": 3, "name": "架构收敛轴", "tasks": ["9", "10"], "dependsOn": [0] },
    { "wave": 4, "name": "安全轴", "tasks": ["11"], "dependsOn": [0] },
    { "wave": 5, "name": "方法学正确性", "tasks": ["12"], "dependsOn": [0] },
    { "wave": 6, "name": "可选", "tasks": ["13", "14"], "dependsOn": [1, 2] },
    { "wave": 7, "name": "收尾", "tasks": ["15", "16", "17"], "dependsOn": [1, 2, 3, 4, 5] }
  ]
}
```

## Tasks

- [x] 1. Characterization 安全网
  - 为 `WpSamplingEngine`(`sampling-execute`) 补 characterization 测试锁定当前响应形状与确定性方法（后端）。
  - 前端方法学口径由既有 `useSamplingAlgorithms.spec`(37)/`useVoucherSampling.spec`(45) 锁定；`WorkpaperExtractionLog` 读写由既有 `test_voucher_sampling_integration`/`test_cutoff_sampling_integration` 锁定。
  - 新增 `test_voucher_sampling_characterization.py`（12 passed）锁定 `execute_sampling` seeded 确定性 + `WpSamplingEngine` 确定性方法。
  - _Requirements: 12.5_

- [x] 2. 全量抽样框脚手架（不改抽样结果）
  - [x] 2.1 `LedgerSamplingService` 新增 `locate_sampling_units`/`fetch_by_unit_ids`/`_build_locate_projection`（阶段 A 最小投影 + 阶段 B 取回，`_ledger_row_to_item` 共享 helper 保样本行结构一致），`test_ledger_sampling_full_frame.py` 3 passed，未接线到 `voucher_extract`。
  - [x] 2.2 新增 `useSamplingAlgorithms.methodology.spec.ts`（11 passed）：权威向量 + 不变量 PBT（同时覆盖 Task 12）。
  - _Requirements: 1.1, 1.2, 10.1_
  - _Properties: Property 1, Property 22_

- [x] 3. DB 级全量抽样框接线
  - [x] 3.1 `voucher_extract` 抽样路径分流：`total_count ≤ _SAMPLING_FRAME_LIMIT(10000)` → 现状内存路径（逐字节等价，36 集成+characterization passed）；`> 上限` → 两阶段全量框（locate_sampling_units 全量最小投影 → synthetic_pop 同 seed execute_sampling → fetch_by_unit_ids 取回）。
  - [x] 3.2 高值必选在样本行上按全量 sampling_interval 识别；specific_item 阈值下全量高值必被选（test 验证 idx 11500 高值必选）。
  - [x] 3.3 残留上限透明：`_SAMPLING_FRAME_MAX_UNITS` 命中 → `frame_capped=true` 返回 stats。
  - [x] 3.4 `test_voucher_sampling_full_frame_selection.py` 6 passed（P1 系统/随机/MUS 触达 >10000 单位、P3 高值必选、P4 种子可复现、_unit_id 保留）。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - _Properties: Property 1, Property 2, Property 3, Property 4_

- [x] 4. 总体完整性独立数据源
  - [x] 4.1 后端 `_resolve_independent_book_amount`（trial_balance 审定汇总，独立于序时账）；取不到 → `book_amount=null` + `reconcile_available=false` + graceful 降级（Req2.5）。响应新增 `reconcile_available`/`reconcile_basis`，`book_amount` 不再=population 自身比对。
  - [x] 4.2 前端 `useVoucherSampling.reconcileInfo` + `GtVoucherSamplingEngine` `effectiveBookAmount`（手工优先→独立账面→null）+ "未执行总体完整性核对" alert + 来源 tag；不再默认以序时账总体自身比对。
  - [x] 4.3 `test_voucher_sampling_reconcile.py` 4 passed（空科目→无源、异常降级、无源不自身比对 book_amount≠population、有源 reconcile_available=true）。前端 93 spec 零回归。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Properties: Property 5_

- [x] 5. 抽样单位显式化
  - [x] 5.1 `SamplingConfig` 加 `samplingUnit`（默认 ledger_line）；`triggerSampling` 发 `sampling_unit`；后端 `voucher_extract` 两阶段(locate/fetch voucher 分支)+内存路径(按 voucher_no 聚合 items→抽凭证→展开完整分录) 均支持；配置弹窗加"抽样单位"选择器。
  - [x] 5.2 voucher 单位排除/排重键为 voucher_no（filled_voucher_nos 已 voucher 级，一致）；ledger_line 保持现状（跨科目 voucher_no 排除为既有行为，行级键留待后续）。
  - [x] 5.3 覆盖率/MUS 间隔分母按 stats 全量口径；voucher 聚合金额=行 GREATEST 之和。
  - [x] 5.4 `test_voucher_sampling_unit.py` 3 passed（voucher 抽 3 张带出 6 行成对、ledger_line 抽 3 行、sampling_unit 标签）。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Properties: Property 6, Property 7_

- [x] 6. 关键词 LIKE 元字符转义
  - `build_ledger_query` 的 `summary_keyword` 经 `_escape_like_pattern`（转义 `\`/`%`/`_`）+ `.ilike(pattern, escape='\\')`；普通文本行为不变。
  - `test_ledger_keyword_escape.py` 8 passed（转义纯函数 5 + 查询构造 3）；cutoff+voucher 既有过滤测试保持全绿（45 passed）。
  - _Requirements: 11.1, 11.2, 11.3_
  - _Properties: Property 21_

- [x] 7. 抽样批次治理迁移
  - [x] 7.1 `V123__voucher_sampling_batch_governance.sql`（下一可用号，前查迁移目录 highest=V122）：`WorkpaperExtractionLog` 加 `batch_id`/`idempotency_key`/`row_version`/`status` + CHECK（fill_mode/extraction_type/status，NOT VALID 仅约束未来）+ `user_id` FK（NOT VALID）+ `UNIQUE(workpaper_id,idempotency_key) WHERE not null` + `UNIQUE(batch_id) WHERE status='undone'`；全部 information_schema/pg_indexes 幂等守护 + `R123` 回滚；ORM 同步 4 新列。
  - [x] 7.2 `sampling_batch_service.py` 状态机（draft→confirmed→filled→undone 合法转移 + is_valid_transition/assert）；撤销路径（undo_extraction + voucher_undo）设 `status='undone'`（配合部分唯一索引强制撤销唯一）。
  - [x] 7.3 `test_sampling_batch_governance.py` 8 passed（状态机 P10 + ORM 新列同步 + V123 幂等/NOT VALID/部分唯一索引结构 + R123 回滚）；45 sampling 套件零回归。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - _Properties: Property 9, Property 10, Property 11, Property 12_
  - 注：DB 级约束强制（P9 幂等唯一/P11 撤销唯一/P12 CHECK 拒绝）由 V123 索引/CHECK 在 **apply 后**强制，需 live PG 应用 + 后端重启验证。

- [x] 8. 真实操作者留痕 + 原子回填
  - [x] 8.1 后端 `cutoff_fill` 已以 `current_user.id` 记权威 actor（非客户端声明）；前端 `resolveActor()`（读 authStore userId/username，无 Pinia graceful 回退）替换 3 处硬编码 `'current_user'`。
  - [x] 8.2 回填原子性：`confirmFill` 日志写入失败 → 返回 [] → `handleConfirmFill` 检查 `result.length>0` 才 emit（既有行为，日志失败不 emit + before_data/filled_voucher_nos 保持 P0）。
  - [x] 8.3 `test_voucher_sampling_actor.py` 1 passed（Property 16：日志 actor=认证用户 id，非占位符）；前端 47 spec 零回归。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 9.1, 9.2, 9.3_
  - _Properties: Property 8, Property 16_

- [x] 9. 后端方法学单一真源
  - [x] 9.1 新建 `sampling_methodology.py`（Python 精确移植 CAS1314 表 + compute_mus_interval/compute_sample_size + `build_methodology_snapshot` + `ALGO_VERSION`）；`voucher_extract` 优先用权威口径间隔（缺参回退 _derive）+ 返回 `methodology` 快照；前端发送置信度/可容忍/预期错报 + 消费后端间隔/建议样本量覆盖展示（前端计算降级为兜底）。
  - [x] 9.2 `confirmFill` extraction_criteria 记 `algo_version`（`methodologySnapshot.algo_version`）。
  - [x] 9.3 `test_sampling_methodology.py` 9 passed（权威向量与前端 methodology.spec 逐位一致 + 快照契约）；前端 45 spec 零回归。
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Properties: Property 13_

- [~] 10. 抽样 API 收敛（canonical 已达成；🔴 stakeholder 已拍板权威语义 2026-07-24：**分层=审计师显式定层（canonical 语义）、MUS=直接给间隔+上限截断（WpSamplingEngine 语义）**；全量收敛因同时改动 D0 MUS（改为间隔驱动）+ wp-functional 分层（改为显式层）两消费方结果，属跨功能大重构 → 留作独立收敛 spec，携此决策落地）
  - [x] 10.1 canonical = `voucher_sampling_algorithms.execute_sampling`（D0 抽凭路径 voucher-extract 全部使用，单一算法真源）。
  - [-] 10.2 **🔴 实测发现语义分叉**：`WpSamplingEngine`(`sampling/execute`，wp-functional-actions + sampling_enhanced 消费) 的 stratified（自动3层权重）/mus（interval 语义）与 canonical **审计语义实质不同**，强制委托会改变另一功能抽样结果（违反零回归 Req12 + 涉审计正确性判断）→ 暂缓全量合并，作为需 stakeholder 定权威分层/MUS 语义的 spec 明示后续项；二者并存 + Task 1 characterization 锁定防漂移。
  - [x] 10.3 `test_voucher_sampling_canonical_guard.py` 5 passed（voucher-extract 用 canonical 算法 + 不混用 legacy WpSamplingEngine + 方法学单一真源 + 全量框两阶段 + 授权前置）。
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - _Properties: Property 14_

- [x] 15. 差异矩阵文档
  - `docs/proposals/voucher-sampling-hardening-diff-matrix.md`：抽样框/总体核对/抽样单位/方法学/关键词/批次治理/API 收敛 七轴各原实现→canonical 映射 + 语义差异 + 保留决策（含 Task 10 语义分叉发现）。
  - _Requirements: 12.6_

- [x] 16. 零回归门与契约守卫汇总
  - 后端全套 102 passed（canonical 守卫 + 全部新增 + 既有 + cutoff PBT）+ 前端 95 passed（algorithms37+methodology11+useVoucherSampling45+inference2）；契约守卫 `test_voucher_sampling_canonical_guard` 防绕过 canonical；P0 已修行为经既有测试逐条回归确认。
  - _Requirements: 12.1, 12.2, 12.3_
  - _Properties: Property 2, Property 14, Property 20_

- [x] 11. 服务端授权校验
  - `deps.py` 抽出可复用 `authorize_wp_edit`（require_wp_edit_permission 委托它，零重复）；`voucher_extract` 入口（置于 try 外，避免 403/400 被 except 吞成 500）调 `_authorize_and_validate_extract`：编辑权 + wp 归属(属于 pid) + 年度∈审计期(audit_year 精确/回退审计期区间)；失败明确 403/404/400。
  - `test_voucher_sampling_auth.py` 6 passed（跨项目 403/年度 400/无编辑权 403 透传/happy/无项目行不阻断/审计期区间回退）；3 流程测试文件加 autouse bypass fixture 保持零回归（28 passed）；既有 `test_checklist_responses` require_wp_edit_permission 3 passed。
  - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - _Properties: Property 15_

- [x] 12. 核心方法学权威向量 + 属性测试
  - 权威向量 + P3/P17/P18/P19/P22 由 Task 2.2 `useSamplingAlgorithms.methodology.spec.ts`(11) 覆盖；P4 种子可复现由 `test_voucher_sampling_full_frame_selection`+characterization 覆盖；后端权威向量 `test_sampling_methodology.py`(9)。
  - 新增 `useVoucherSampling.inference.spec.ts`(2) 收口 P20（未检查样本不参与推断 + checked/unchecked 计数）。
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Properties: Property 3, Property 4, Property 17, Property 18, Property 19, Property 20, Property 22_

- [x] 13. 属性抽样接入 C 类控制测试（可选）*
  - `computeAttributeSampleSize`（n=ceil(R(conf,0)/(tol−exp))）/`evaluateDeviationRate`（CUDR=R(conf,devs)/n）已实现，复用与 MUS 同源 CAS1314 泊松表；纯附加不改金额法。
  - 新增 `useSamplingAlgorithms.attribute.spec.ts`（17 passed）：权威向量（60/75/30/47、CUDR 0.05/0.079167/0.03、精度余量≤0→0、样本量≤0→上限1）+ 不变量 PBT（可容忍↑→样本量不增、置信度↑→样本量不减、CUDR≥实测偏差率、恒非负整数）。
  - **修真实边界**：`computeAttributeSampleSize` 对极小精度余量（denormalized `5e-324`）返回 `Infinity` → 加 `Number.isFinite(n)` 守卫返回 0（视同无法推导），确保恒返回非负整数。
  - 注：C 类控制测试 UI 接入属 C 模块后续（纯函数与测试已就绪）。
  - _Requirements: 13.1, 13.2, 13.3_

- [x] 14. 正式抽样备忘归档（可选）*
  - `SamplingMemoInput` 加 `batchId`/`algoVersion`；`buildSamplingMemo` 附段落输出「批次标识」「方法学算法版本」（缺失/空串→占位符不臆造）；`GtVoucherSamplingEngine.handleExportMemo` 从 `methodologySnapshot.value?.algo_version`/`batch_id` 传入。
  - `useSamplingMemo.spec.ts` 追加 3 case（13 passed）：批次/版本展示、缺失占位、空串占位。
  - 注：`batchId` 前端 wiring 依赖 confirmFill 回填 batch_id（Task 7 dormant），当前从后端快照透传，无值时占位。
  - _Requirements: 14.1, 14.2, 14.3_

- [x] 17. Playwright 关键路径实测*
  - 实例化项目 `2aa00f57`（重庆和平药房 2025，1.1M 序时账行）D2 wp `ef7f88e3`，account 1122（312,096 行总体），admin 登录后经认证 fetch 实测（避 SSE 跳转，单次 evaluate 内完成）：
  - ✅ **全量框大总体抽样**：MUS status 200 / total_count=312096（>>10000 触发两阶段全量框）/ population_amount=2,396,207,452.45（**全量非截断**）/ frame_capped=false / sampling_interval 由全量总体推导 / algo_version=cas1314-mus-v1。
  - ✅ **独立核对显示**：reconcile_available=true / reconcile_basis=trial_balance_audited（Task 4 独立源，非序时账自身比对）。
  - ✅ **授权拒绝**：跨项目 403「底稿不属于该项目」/ 年度越界（1999）400「不属于项目审计期」。
  - ✅ **批次治理 DB 约束 live**：V123 `uq_extraction_log_wp_idempotency`（幂等部分唯一）+ `uq_extraction_log_batch_undone`（撤销部分唯一）已应用强制；状态机由 Task 7 单测（8）覆盖。
  - 0 应用报错（2 console error 为测试预期的 403/400 拒绝）；voucher-extract 为预览态不写日志→无测试数据污染。
  - 注：批次幂等/撤销的 UI round-trip 依赖 confirmFill 前端 batch_id/idempotency_key wiring（Task 7 dormant），DB 约束+服务状态机已就绪，前端接入为后续。
  - _Requirements: 1.1, 2.2, 5.1, 5.3, 8.1_
  - _Properties: Property 1, Property 5, Property 9, Property 11, Property 15_

## Notes

- **零回归铁律**：每波结束跑既有测试全绿；任一步失败或断言不符即停在该步（可回退），禁止放宽断言/跳过用例绕过（Req12.1/12.3）。
- **P0 已修行为清单（必须保持）**：`filled_voucher_nos` 提交、未检查样本不参与推断、结论确认门禁、传父底稿真实前态、`amount_max`/离散月份过滤、非法 phase 已迁移（Req12.2）。
- **边界**：不触碰 `cutoff-extract`/`cutoff-test`、跨期判定、CutoffRow 模型、截止全量框——归 `cutoff-test-architecture-convergence` spec。共享 `LedgerSamplingService` 的改动（全量框、LIKE 转义）须保持截止侧测试全绿。
- **迁移取号**：Task 7.1 建迁移前查 `migration_status` 取下一可用 `V` 号，避免同号冲突；幂等守护 + rollback。
- **可选任务**（Task 13/14/17 带 `*`）：按用户偏好 optional 也做完；Task 17 需含 >10000 行总体的实例化项目，无此环境则如实说明不伪造。
