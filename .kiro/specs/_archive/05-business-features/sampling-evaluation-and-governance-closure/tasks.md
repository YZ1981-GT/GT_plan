# Implementation Plan: 抽样评价与治理闭环

## Overview

19 个任务分 4 波。Wave 1 修正在产生错误数字与噪声告警的路径（撤销不清理投影、合规判据错、
阈值硬编码）；Wave 2 补 CAS 1314 评价环节四条缺口（未检查样本处置、偏差性质、完整性阻断、
分层层内评价）；Wave 3 恢复 QC 引擎执行并重写抽样 QC 判据、把抽样记录纳入归档；
Wave 4 接线属性抽样、补复核入口、守卫与实测收口。

波次内串行（同一批文件反复改动，并行会互相覆盖）。Wave 1 与 Wave 2 都改
`useSamplingAlgorithms.ts` 与 `GtVoucherSamplingEngine.vue`，必须顺序推进。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "数据正确性（当前正在产生错误）",
      "tasks": ["1", "2", "3", "4"],
      "parallel": false
    },
    {
      "wave": 2,
      "name": "准则闭环（未检查处置 / 偏差性质 / 完整性阻断 / 分层评价）",
      "tasks": ["5", "6", "7", "8", "9", "10"],
      "parallel": false
    },
    {
      "wave": 3,
      "name": "监管闸门（QC 恢复执行 + 归档章节）",
      "tasks": ["11", "12", "13", "14"],
      "parallel": false
    },
    {
      "wave": 4,
      "name": "收敛与验收",
      "tasks": ["15", "16", "17", "18", "19"],
      "parallel": false
    }
  ]
}
```

## Tasks

### Wave 1 — 数据正确性

- [x] 1. 后端：撤销时同步软删抽样登记投影
  - `sampling_registry_service.undo_sampling_registration(db, *, batch_id)`：按 batch_id 软删
    `sampling_records` 与 `sampled_vouchers`，返回受影响行数；`batch_id` 为 None 时零操作 + WARNING
  - `voucher_sampling.voucher_undo`：在 `flush` 后、`commit` 前调用；返回体加
    `undone_registration`；函数内 fail-open 由服务层承担
  - ~~`register_sampled_vouchers` 复活软删行~~ **实证推翻，无需代码**：撤销后重新回填会生成
    新 uuid4 batch_id（幂等去重只命中 `is_undone=false` 的 log）⇒ 部分唯一索引下天然不冲突
  - _Requirements: 1.1, 1.2, 1.3, 1.7, 1.8_

- [x] 2. 后端守卫：撤销投影（Property 1~4）
  - 新建 `backend/tests/test_sampling_undo_registration.py`
  - 覆盖：撤销后三个查询函数不再暴露该批次 / 不越界（同底稿其它批次不受影响）/
    NULL batch_id 零影响 / 撤销后重新登记行数相等 / 投影异常时撤销仍成功且有 WARNING
  - 反向自检：复现旧行为（不调用 `undo_sampling_registration`）时 Property 1 必打红
  - _Requirements: 1.4, 1.5, 1.6, 11.2_

- [x] 3. 前端：合规检查判据修正 + 覆盖率阈值单一真源
  - 新建 `composables/samplingCoverageThreshold.ts`：`DEFAULT_COVERAGE_THRESHOLD = 0.60` +
    `resolveCoverageThreshold({workpaper, project})` + `THRESHOLD_SOURCE_LABELS`（中文标签）
  - `useSamplingAlgorithms.checkCAS1314Compliance` 改 options 对象入参；函数体内消除阈值字面量；
    规则 2 分子改为特定项目法抽出样本数；规则 3 改为 `totalSampleCount < suggestedSampleSize`
    且后者非 null；覆盖率告警文案带阈值取值与来源
  - `useVoucherSampling.checkCompliance` 按新签名传参（含 `suggestedSampleSize`）
  - 评价载荷记录 `coverage_threshold` / `coverage_threshold_source`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 4. 前端守卫：判据与阈值（Property 5~7）
  - 新建 `samplingComplianceCriteria.spec.ts` + `samplingCoverageThreshold.spec.ts`
  - 反向自检：①勾选集合变化不改变 `specific_item_high`（旧实现必打红）
    ②`suggestedSampleSize=null` 时不产生 `mus_insufficient`（旧实现在不全选时必告警）
    ③源码级断言函数体无阈值字面量（配 `stripComments` + 自检）
  - _Requirements: 11.2, 11.3_

### Wave 2 — 准则闭环

- [x] 5. 后端：评价载荷白名单扩容
  - `_EVAL_JSON_KEYS`（`unchecked_disposition` / `deviation_nature_summary` /
    `stratified_evaluation`）按结构归一（丢弃未知子键，金额走 `_eval_amount`、计数走 `_eval_count`）
  - `_EVAL_TEXT_KEYS` 追加 `reconcile_override_reason`；新增服务端权威字段
    `reconcile_override_by` / `reconcile_override_at`（客户端传值不可信）
  - `_EVAL_AMOUNT_KEYS` 不变；全部新 key 缺省时输出与改造前逐位一致
  - `build_record_fields`：把三项摘要拼进 `conclusion`（带前缀标签），不新增列
  - _Requirements: 3.5, 4.5, 5.4_

- [x] 6. 前端：未检查样本处置（R3）
  - `useSamplingAlgorithms.resolveUncheckedDisposition(samples, disposition)`：纯函数，返回
    `{pending: string[], asDeviation: SampledVoucher[], alternative: SampledVoucher[]}`
  - `projectMisstatement` 前置：`treated_as_deviation` 的样本按 `actualMisstatement = 账面金额`
    参与推断并计入 `deviation_count`
  - 引擎 UI：未检查样本行显示处置下拉（视同偏差 / 已实施替代程序）+ 替代说明输入
  - `confirmBlockedReason` 纳入「存在未处置的未检查样本」「替代程序无说明」
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6_

- [x] 7. 前端：偏差性质结构化（R4）
  - 新建 `composables/samplingDeviationNature.ts`，性质枚举与提示语 **re-export**
    `useDeviationDecisionTree` 的口径（不另写判定）
  - `summarizeDeviationNature(samples)` 纯函数产出 `deviation_nature_summary`
  - 引擎 UI：`checkResult` 为 `N`/`异常` 的行显示性质下拉 + 原因/影响输入；
    结论区在存在系统性偏差时显著提示「不宜简单外推」
  - `confirmBlockedReason` 纳入「存在待判断偏差」「系统性偏差缺说明」
  - `buildProjectedMisstatementDescription` 追加系统性偏差提示
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 8. 前端：总体完整性核对阻断 + 理由放行（R5）
  - `confirmBlockedReason` 纳入「核对不可用」「差异超阈值」，前置 disable + tooltip
  - 完整性卡片内新增「填写理由后继续」入口（≥10 字校验），理由写入评价载荷
  - 核对通过时不要求理由（零回归）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 9. 前端：分层抽样层内评价（R6）
  - `projectMisstatementByStrata(samples, strata, populationAmount, confidenceLevel)`：
    按金额区间归层 + 未归层桶 + 逐层比率估计 + 加总；返回 `StratifiedMisstatementResult`
  - `projectMisstatement` 在 `method==='stratified'` 且开关开启时委托，异常回退 legacy 并标注
  - 灰度：`VITE_SAMPLING_STRATA_EVALUATION_ENABLED`（默认关）；`.env.example` 补说明
  - 引擎 UI：分层明细面板（各层总体/样本/错报/外推额 + 未归层提示 + 无样本层提示）+
    新旧口径并列对照（差异非零时提示复核）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 10. 前端守卫：Wave 2（Property 8~17）
  - 新建 `samplingUncheckedDisposition.spec.ts` / `samplingDeviationNature.spec.ts` /
    `samplingConfirmGating.spec.ts` / `stratifiedMisstatement.spec.ts`
  - `samplingDeviationNature.spec.ts` 读 `useDeviationDecisionTree` 源码交叉锁死枚举与提示语
  - `stratifiedMisstatement.spec.ts` 含 PBT：层内样本金额之和 == 全部样本金额之和、
    `projected` == 各层外推额之和且 ≥ 0、未归层不丢金额
  - 反向自检：①无未检查样本时新门控零阻断 ②开关关闭时与 legacy 逐位相等
    ③把未归层桶去掉必打红（金额守恒被破坏）
  - _Requirements: 11.1, 11.2, 11.3_

### Wave 3 — 监管闸门

- [x] 11. 后端：QC 规则门控三态修复（平台级，R7.1~7.3）
  - `qc_engine._get_enabled_rule_codes`：查询成功但 0 行 → 返回全部内置 rule_id + WARNING；
    显式 `enabled=false` → 排除；未登记 → 视为启用（记一次性 INFO）
  - 返回值语义由「启用白名单」改为「禁用黑名单过滤后的集合」，`check` 内的过滤逻辑同步
  - **影响面**：全部 20 条内置 QC 规则将从「静默不执行」恢复为执行 → 需在 Notes 记录
    改造前后 finding 数量对比，避免被误认为新引入告警
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 12. 后端：抽样 QC 判据纯函数 + QC-12 重写
  - 新建 `services/sampling_qc_rules.py`：`SamplingBatchView` dataclass +
    `evaluate_sampling_completeness(batches) -> list[str]`（不连库）
  - 判据：未撤销的 `voucher_sampling` 批次中，缺 `evaluation` / `conclusion_confirmed` 为 false /
    `dataset_stale` 为 true → 各产出一条可追溯消息（含批次标识与缺失项类别）
  - `SamplingCompletenessRule.check` 改为查 `workpaper_extraction_log` 后委托纯函数；
    源码不再引用 `SamplingConfig`
  - _Requirements: 7.4, 7.5, 7.6, 7.7, 7.8_

- [x] 13. 后端：归档抽样记录章节 + 完整性缺口
  - 新建 `services/archive_generators/sampling_records_generator.py`，注册前缀 `05`，
    输出 CAS 1314 记录项清单 + 「记录不完整」分节；无批次输出说明文本；失败输出占位
  - `archive_completeness_service`：新增抽样记录完整性检查项，复用 `sampling_qc_rules` 同一判据
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 14. 后端守卫：Wave 3（Property 18~22）
  - 新建 `test_qc_engine_rule_gating.py`（三态 + 反向自检「复现旧行为则 active_rules 为空」）/
    `test_sampling_qc_rules.py`（纯函数判据 + 无批次不适用）/
    `test_archive_sampling_records_section.py`（章节字段完备 + 无批次 + 失败占位）
  - 源码级断言：`SamplingCompletenessRule` 不引用 `SamplingConfig`；归档与 QC 使用同一判据函数
  - _Requirements: 11.2, 11.3_

### Wave 4 — 收敛与验收

- [x] 15. 属性抽样接线到控制测试（R9）
  - 控制测试底稿新增「统计抽样 / 快捷表」模式切换；统计模式接
    `computeAttributeSampleSize` + `evaluateDeviationRate`，展示置信度/可容忍偏差率/预期偏差率入参
  - 快捷表模式继续走 `useSampleSizeEngine`，结果与改造前逐位一致
  - 新建 `attributeSamplingWiring.spec.ts`：消费方存在性（非测试文件）+ 两套方法学边界登记
    （`SAMPLING_METHOD_BOUNDARY` 常量带理由）+ 禁止合并断言
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 16. 抽样引擎复核入口 + 只读态门控（R10）
  - 引擎配置区与结论区各挂 `GtReviewTrigger`，section_id 形如 `{wp_code}-sampling-config` /
    `-sampling-conclusion`
  - 后端 `review_dialog._SECTION_PROMPTS` 登记专属 prompt（≥40 字 + 「不得虚构」）
  - 只读态（归档/锁定）下配置与回填入口 disabled
  - 守卫：前端 section_id 集合 ⊆ 后端已登记 prompt（交叉锁死）
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 17. 真实库只读诊断脚本
  - 新建 `backend/scripts/diagnose/verify_sampling_governance_live.py`（默认 dry-run，
    `--apply` 真跑并按快照自动复原）
  - 覆盖：撤销后投影状态 / QC 实际执行规则条数 / QC-12 对真实批次的判定 / 归档章节产出 /
    分层评价新旧口径差异
  - _Requirements: 11.4_

- [x] 18. CI 接入
  - `governance-checks.yml` 新增后端 job `sampling-evaluation-governance-backend`（9 步）与
    前端 job `sampling-evaluation-governance-frontend`（7 步），加挂本 spec 全部守卫
  - 验证 YAML 可解析且 job 名不重复（118 → 120 jobs）
  - **每一步本地实跑通过**（不只是写进 CI）：后端 57 + 46 passed；
    前端 41 / 95 / 44 / 70 passed，均 0 failed
  - _Requirements: 11.6_

- [x] 19. 回归 + 浏览器实测 + 数据复原
  - 后端：`sampling or voucher or qc_engine or archive` 作用域全量，对比预存在基线
  - 前端：`sampling`/`voucher`/`cControlTest` 作用域全量 + 改动文件 Vite transform 200
  - 浏览器三件套：撤销后重复提示消失 / 未检查处置门控 / 偏差性质门控 / 完整性理由放行 /
    分层明细与新旧对照 / QC 自检产出 finding
  - 测后逐字节复原数据；清理本轮 `tmp_*`
  - _Requirements: 11.5_

## Notes

### 立项事实基线
见 `requirements.md` 的 F1~F18 表（2026-08-05 逐个实证）。其中 **F15（QCEngine 全部 20 条规则
静默不执行）是平台级 P0，超出抽样范围但直接决定 R7 能否生效**，故纳入 Wave 3 Task 11。

### 与前序 spec 的边界
`sampling-compliance-closure`（24/25，仅剩浏览器实测）已完成 dataset 绑定、评价持久化、
A13 类型通路、legacy 删除、两张投影表接入、跨底稿重复确认、78 宿主方法学 bar。本 spec 不重做。

### 明确移出范围
20 份 per-cycle 抽凭 composable 的行模型收敛 → 另立 `voucher-check-shared-layer`
（半径 62 文件，核对项形态已漂移：D2 `check1..check5: string` vs D3 `checkItems: boolean[]`）。

### 四个裁决点的默认取值
1. 完整性核对失败 → 阻断 + 理由放行（≥10 字）并留痕
2. 覆盖率阈值 → 底稿 > 项目 > 平台默认，默认仍 0.60（零回归），标注「非准则数字」
3. 属性抽样 → 接线到控制测试，快捷表保留并加边界守卫
4. 分层层内评价 → 灰度默认关 + 开启时新旧并列

### Wave 1 交付实录（2026-08-05）

**Task 1/2 后端**：`undo_sampling_registration(db, *, batch_id)` 按 batch_id 软删两张投影表
（fail-open + WARNING，NULL batch_id 零操作），接在 `voucher_undo` 的 flush 后 / commit 前，
返回体加 `undone_registration`。守卫 `test_sampling_undo_registration.py` **20 例**。

**Task 3/4 前端**：新建 `samplingCoverageThreshold.ts`（阈值单一真源，底稿 > 项目 > 平台默认
0.60，非法值如把 60 当小数传会被拒并回退）；`checkCAS1314Compliance` 改 options 对象签名，
函数体消除阈值字面量；`useVoucherSampling.checkCompliance` 按真实语义取数并留痕阈值；
后端 `_normalize_evaluation` 加 `_EVAL_RATIO_KEYS` / `_EVAL_ENUM_KEYS`（比率越界与非法枚举
→ None 而非默认值，「未记录」与「按默认值判的」必须可区分）。
守卫 `samplingCoverageThreshold.spec.ts`(22) + `samplingComplianceCriteria.spec.ts`(19)，
既有 `useSamplingAlgorithms.spec.ts` 合规块诚实改写为新签名并补 5 条新用例（42 例全绿）。

**变异检验 10 个，8 个有效变异全部准确打红**（A 阈值回硬编码 / B 去掉占比判据可用性前提 /
C' MUS 复现旧判据 / C'' 去外层判空+内层兜底数 / D 调用点回传勾选数 / E 分母不含现有样本 /
F 阈值校验放宽 / G 阈值不留痕），源文件字节级还原。

**回归**：后端 `-k "sampling or voucher"` **399 passed / 4 failed**（4 个全在
`test_voucher_sampling_batch_wiring.py`，单独跑 9 passed + 文件 git 干净 = memory 已登记的
事件循环污染基线）；前端 `sampling voucher cutoff` **848 passed / 1 failed**
（`k8-pbt-cutoff.test.ts`，git 干净且单独跑仍红 = 预存在 PBT 基线）。

### Wave 1 期间三处实证纠正（写进 spec 防重犯）

1. **规则 2 的函数实现原本是对的，错的是调用点**。立项时判定「函数判据错」，实测
   `checkCAS1314Compliance` 内 `sampleCount/totalCount` 与既有测试意图一致，是
   `checkCompliance` 传了 `selectedCount`（勾选数）。→ 修调用点 + 加占比判据可用性前提。
2. **撤销后重新回填不需要「复活软删行」**（见 Task 1 划删条目）。
3. **规则 2 的分母需要底稿现有样本数，composable 拿不到** → options 加可选
   `existingSampleCount`，不传时分母==分子 ⇒ 判据不可用 ⇒ 不告警（宁可不告警也不制造噪声）。
   精确判定历史样本的方法构成需要 `SampledVoucher.samplingMethod` 字段，归
   `voucher-check-shared-layer`。

### 踩坑（本轮新增，已同步 memory）

- **`Path.write_text` 在 Windows 把 LF 转成 CRLF**（newline=None → os.linesep）→ 变异脚本
  「内容还原了但哈希不符」。改 `write_bytes` 字节级还原。
- **变异脚本的跨行锚点会被 CRLF 挡住** → 用单行锚点或先归一化行尾。
- **「无效变异」会被误判成守卫缺陷**：`if (a < b)` 在 b 为 null 时 JS 恒 false，故只改外层
  判空或只改内层比较都不改变行为。判「守卫是否缺陷」前先确认该变异**真的改变了行为**。
- **`"DELETE" in sql` 会被列名 `is_deleted` 骗**（`IS_DELETED` 含子串）→ 物理删除判据必须
  `\bDELETE\s+FROM\b` 并配「软删 UPDATE 不得命中」的判据自检。

### Wave 2 交付实录（2026-08-05）

**Task 5 后端**：`_normalize_evaluation` 加 `_EVAL_RATIO_KEYS` / `_EVAL_ENUM_KEYS` +
三个结构化归一函数（`_normalize_unchecked_disposition` / `_normalize_deviation_nature_summary` /
`_normalize_stratified_evaluation`）+ 完整性放行理由三件（理由 + 服务端权威的操作人/时间，
理由清空则三项一并清空防「无理由但有放行签名」残迹）。`build_conclusion_supplements` 把三项
摘要拼进 `sampling_records.conclusion`（**不加列**：说明性内容且 QC/归档都是整行读出后渲染），
`update_sampling_record_evaluation` 走同一拼接（否则每次评价更新都会抹掉摘要）。

**Task 6/7/8/9 前端**：新建 `samplingUncheckedDisposition.ts`（处置二选一 + 视同偏差按
100% 污染率改写，**返回新数组不改原样本**，评价派生须可回退）· `samplingDeviationNature.ts`
（中文标签**运行时**取自 C 类 `getStepOptions(2)`，不做硬编码副本；选项数不一致直接抛错）·
`useSamplingAlgorithms.projectMisstatementByStrata`（逐层比率估计 + 未归层桶 + 无样本层不外推 +
始终返回 `legacy` 供并列）· `useVoucherSampling` 加统一门控 `conclusionBlockedReason`
（三处门控收敛一处，`reconcileBlockedReason` 由组件注入）· 引擎组件加两列（未检查处置 /
偏差性质与原因）+ 完整性放行理由入口 + 分层明细表 + 新旧口径对照 + 确认按钮前置 disabled。
灰度 `VITE_SAMPLING_STRATA_EVALUATION_ENABLED` 默认关，`.env.example` 已补说明。

**守卫 4 个 / 92 例**：`samplingUncheckedDisposition.spec.ts`(26) ·
`samplingDeviationNature.spec.ts`(23，含前后端取值域与标签双向交叉锁死) ·
`stratifiedMisstatement.spec.ts`(19，含 3 条 PBT) · `samplingConfirmGating.spec.ts`(24)。
**变异检验 9/9 全部准确打红**。

**回归**：后端 399 passed / 4 failed（预存在基线）；前端 `sampling voucher cutoff`
**924 passed / 1 failed**（`k8-pbt-cutoff` 预存在），改造前 848/1 ⇒ 净增 76 全通过、零新增失败；
6 个改动文件 Vite transform 全 200。

### Wave 3 交付实录（2026-08-05）

**Task 11（平台级 P0）**：`_get_enabled_rule_codes` 语义由「启用白名单」改为「禁用黑名单
过滤」三态 —— 空表 → 全部执行 + WARNING（改造前返回空集使 **20 条 QC 规则全部静默不执行**）·
显式 `enabled=false` → 排除 · 未登记 → 启用 + 一次性 INFO。SQL 层去掉 `WHERE enabled=true`
（带上它「显式禁用」与「未登记」在结果里不可区分，三态会退化成两态）。

**Task 12**：新建 `sampling_qc_rules.py`（不连库纯函数，QC 与归档共用）。判据 = 未撤销的
`voucher_sampling` 批次缺评价 / 结论未确认 / `dataset_stale`；**无批次零 finding**（不适用 ≠
不合规）；**`"0.00"` 算有效评价**（查了没发现错报），把它当空值会对所有干净抽样误报。
QC-12 重写为委托该纯函数，可执行代码不再引用 `SamplingConfig`。

**Task 13**：新建 `archive_generators/sampling_records_generator.py`，注册前缀 **06**
（05 已被 AI 贡献明细占用，而 `register` 对同前缀是**覆盖**语义，用 05 会静默顶掉该章节）；
无批次输出「未执行抽样程序」说明而非 None；整体 try/except 输出占位不阻断归档。
`archive_completeness_service` 加第 5 类 `sampling_records`（**非阻断**：补齐抽样记录是审计
判断，硬卡会让存量项目全线阻塞归档），判据复用同一纯函数。

**守卫 3 个 / 51 例**：`test_qc_engine_rule_gating.py`(13) · `test_sampling_qc_rules.py`(24) ·
`test_archive_sampling_records_section.py`(14，含「同前缀会覆盖」反向自检与还原)。
**变异检验 12 个：10 个有效变异全部打红**（含行级替换重做的 A1「空表返回空集」与 A2
「WARNING 文案丢失」），2 个经查证为无效变异（黑名单语义下空表天然返回全部；空列表进循环
也返回 `[]`）。

**诚实修改既有测试 1 处**：`test_archive_completeness_report.py::test_report_always_has_4_categories`
→ `_5_categories`，并补一条「其余四类阻断语义不变」的断言。

**回归**：`-k "sampling or voucher or qc_engine or archive"` **741 passed / 10 failed**，
逐个查证 —— 4 个 `test_voucher_sampling_batch_wiring`（事件循环污染基线）+ 5 个
`test_archive_deprecated`/`test_archived_project_guard`/`test_check_git_branch_naming`/
`test_property_archived_invariant`（全部 git 干净 + 零引用本次改动符号 + 单独跑仍失败）
+ 1 个已诚实更新。

### Wave 2/3 期间新增踩坑（已同步 memory）

- **`.py` 是 CRLF，变异脚本的跨行锚点必 MISS**（本轮踩 3 次）→ 用单行锚点，或按**行级**
  定位（`splitlines` + 锚点行号 + 相对偏移），与行尾无关。
- **`blockOf`/`extractFunctionBody` 取「声明后第一个 `{`」会命中内联返回类型注解**
  （`function f(): { a: X } {`）→ 截出来的"函数体"是那段类型，后续断言全在无关文本上求值。
  正解：逐个候选 `{` 配对，取第一个**含语句特征**（`return`/`const`/`if`…）的块，并配自检。
- **含 `\n` 的字面量断言在 CRLF 源码上必失效** → 读文件后统一 `.replace(/\r\n/g, '\n')`。
- **`toContain('x.y.length')` 抓不住「删掉判断」**：把 `if (a.b.length > 0)` 改成 `if (false)`
  后该字符串仍在返回消息的模板串里 → 判据必须断言**条件形态**（`/if\s*\(\s*a\.b\.length\s*>\s*0\s*\)/`）
  并配「弱判据仍通过」的对照自检。同族：`"DELETE" in sql` 被列名 `is_deleted` 骗。
- **新增归档章节前必须 `list_all()` 查已占前缀** —— `register` 对同 `order_prefix` 是覆盖语义，
  撞号会静默删掉别人的章节。

### Wave 4 收口实录（Task 19）（2026-08-08）

**后端回归**（`-k "sampling or voucher or qc_engine or archive"`，785 例）：
**769 passed / 9 failed / 1 error / 6 skipped**。10 项全部逐条查证为**预存在**：
9 个 failed 与 Wave 3 记录的清单逐条相同（`test_archive_deprecated`×2 /
`test_archived_project_guard` / `test_check_git_branch_naming` /
`test_property_archived_invariant` / `test_voucher_sampling_batch_wiring`×4）；
新增的 1 个 error（`evidence_governance/test_wave9_router_wiring_integration::
test_archive_preflight_and_build_invariant` setup 报
`AttributeError: 'NoneType' object has no attribute 'send'`）是 memory 已登记的
**事件循环污染基线** —— 与 `test_voucher_sampling_batch_wiring` 合并单独跑
**22 passed**，且六个文件 `git status` 全干净。

**前端回归**（`sampling voucher cControlTest cutoff`，69 文件）：
改造前 1076 例 / 1074 passed / 2 failed → Task 19 修复后 **1086 例 / 1084 passed /
2 failed**（净增 10 全通过、**零新增失败**）。两个失败均为预存在：
- `k8-pbt-cutoff.test.ts`（Wave 1/2 已登记的 PBT 基线）
- **`useCControlTestData.spec.ts`**（本轮新纳入 `cControlTest` 作用域才暴露）：
  期望 `C5-dev-*` 12 项（注释写「5 steps + 1 conclusion」），实际 14 项 ——
  实现还序列化了 `exceptionDesc`。判**预存在**的依据：该 spec 与
  `useCControlTestData.ts` 及其全部传递依赖（`useDeviationDecisionTree` /
  `useCControlTest` / `apiProxy` / `eventBus`）**git 全干净**，且
  `git show HEAD:useCControlTestData.ts` 里 `exceptionDesc` 命中 12 处
  ⇒ HEAD 侧即失败。属 C 类控制测试侧的陈旧断言，不在本 spec 半径。

**Vite transform**：本 spec 8 个改动/新建前端文件全 200（`non-200 count = 0`）。

**真实库只读验收**（`verify_sampling_governance_live.py`）：**PASS=10 / FAIL=0 /
SKIP=2**，实测后重跑逐字相同。关键取证 —— `qc_rule_definitions` **0 行**而
`_get_enabled_rule_codes` 返回 **20/20** 条（Task 11 前返空集 ⇒ 20 条 QC 规则全部
静默不执行）+ 空表 WARNING 1 条 · QC-12 对 2 个真实批次产出 **2 条 finding** ·
归档章节前缀 `00/01/02/03/04/05/06/99` 无冲突、`06-抽样记录汇总.txt` 已注册、
有批次项目 1198 字节含批次号与总体描述、无批次项目返回 377 字节说明文本 ·
`sampled_vouchers` 孤儿登记行 0。两个 SKIP 是「该库无已撤销批次」（诚实不可判定，
撤销投影由 `test_sampling_undo_registration.py` 的 20 例 + 5 变异保证）。

**🔴 Task 17 描述与实现不符（已按实现为准）**：tasks.md 原写「默认 dry-run，
`--apply` 真跑并按快照自动复原」，实际脚本**全程只读、无 `--apply`**。判定保留只读
形态 —— 撤销真实批次会产生无法逐字节复原的软删痕迹（撤销后重新回填必生成新
`batch_id`），而只读判据已足够覆盖 A/B/D/E/F 五组。

**浏览器实测（chrome-devtools `isolatedContext` 隔离，避免并发会话抢占）**
项目 `2aa00f57` / 底稿 `d35c715a`（D3 预收账款，wp_code=D3，sheet `预收账款检查表D3-7`）：

| 验收项 | 实测结果 |
|---|---|
| 未检查处置列（R3.1/3.4） | 列已渲染；未处置行显示**「须选择处置方式」**；下拉恰为**视同偏差 / 已实施替代程序** |
| 替代程序说明必填（R3.3） | 选「已实施替代程序」后出现**「替代程序说明（必填）」** |
| 偏差性质列（R4.1/4.3） | `核查结果=异常` 后该列变**「须标注偏差性质」**并出现下拉，选项逐字为**系统性偏差 / 人为偏差 / 随机性偏差**（= C 类 `getStepOptions(2)` 口径） |
| 系统性偏差需说明（R4.2） | 选「系统性偏差」后出现**「偏差原因（必填）」+「对审计程序目的的影响评估（必填）」** |
| 系统性偏差结论区提示（R4.2） | 推断后显示**「存在系统性或人为偏差，不宜简单外推：应考虑扩大测试范围、改变审计方法或提请管理层扩大检查」** |
| 完整性核对阻断 + 理由放行（R5.1/5.3/5.5） | 卡片显示**「结论确认已阻断」**+ 原因；理由框 4 字 → **「还需 6 字」**，27 字 → **「已填写放行理由，可继续确认结论」**；「记入未更正错报汇总」按钮 **disabled** |
| 覆盖率阈值留痕（R2.6） | 落库 `coverage_threshold: 0.6` + `coverage_threshold_source: "platform_default"` |
| 分层灰度关闭（R6.6） | 落库 `stratified_evaluation: null` |
| 评价结构化落库（R3.5/R4.5/R5.4） | `unchecked_disposition` 三条（含 mode+note）· `deviation_nature_summary.systematic{count,amount}` · `reconcile_override_reason/by/at` 服务端权威三件 · `deviation_count=3`（1 异常 + 2 视同偏差） |
| 投影表摘要（Task 5） | `sampling_records.conclusion` 落**【未检查样本处置】/【偏差性质】/【总体完整性核对放行理由】**三段 + `projected_misstatement` / `upper_misstatement_limit` / `deviations_found` |

**分层明细与新旧对照未做浏览器实测**（诚实登记）：`VITE_SAMPLING_STRATA_EVALUATION_ENABLED`
默认 false 且 Vite 环境变量是编译期内联，开启需改 env 文件并重启**共享** dev server
（并发会话在用）。该块由 `stratifiedMisstatement.spec.ts` 19 例（含 3 条 PBT：层内金额
守恒 / `projected` == 各层外推额之和 / 未归层不丢金额）+ 变异检验覆盖。

**撤销后重复提示消失未做浏览器实测**（诚实登记）：真实库唯一活跃批次
`59fb3524` 属真实项目，撤销会留下无法逐字节复原的软删痕迹（重新回填生成新
`batch_id`，旧行永久 `is_deleted=true`）。改为由 `test_sampling_undo_registration.py`
20 例 + 5 变异 + 只读脚本 C1 如实 SKIP 三者共同承担。

**数据复原**：`_wip_t19_restore.py`（默认 dry-run / `--apply`）按实测前快照把
`extraction_criteria->'evaluation'` 复原为 **JSON null**、`sampling_records` 的
评价四列 + conclusion 复原为 NULL。两轮实测后各复原一次，postgres 独立复核
**每一项都与基线逐位相同**：`sr_all=1` / `sr_concl=0` / `sr_proj=0` /
`sv_all=22` / `sv_live=21` / `log_all=3` / `cr_wp=3` /
`cr_md5=c26bb5202593be8963c192331773d930` / `wp_updated=2026-06-08 02:00:53.647970` /
`wp_parsed_md5=6c3e226b4d4795d518ab341b0824ec29` / `workpaper_snapshots=164` /
`unadjusted_misstatements=2` / `criteria_len=2258`。
（`sr_concl=0` / `sr_proj=0` 与 requirements F18 的立项实证一致。）

### 收口期修掉的真缺陷：已实施替代程序的样本被静默挤出推断基数（R3.3）

**只有浏览器 + 独立算术复核才会暴露**：`inferMisstatement` 里 `applyDeviationTreatment`
只改写「视同偏差」，`alternative_performed` 的样本 `checkResult` 仍为空 ⇒ 被既有过滤
`treated.filter(v => v.checkResult !== '')`（来自 `voucher-check-sampling-integration` R18）
整体排除 ⇒ **既不进分子也不进分母**，比率估计基数被静默缩小、推断错报被放大。
四层验证全绿：`get_diagnostics` 零诊断 / 既有 92 例守卫全绿（`samplingUncheckedDisposition.spec.ts`
甚至有一条 `it('替代程序处置不改写金额')` 把该行为锁成"正确") / Vite 200 / 后端无从判定。

**取证（第一轮浏览器实测的真实库落库值）**：样本 4 笔账面
13,832.00 / 195.60 / 37,340.20（替代程序）/ 15,655.09，总体 4,857,866.37，
Σ错报 20,850.69 —— 旧口径分母 29,682.69（37,340.20 被排除）⇒ 污染率 0.70245 ⇒
`projected` **3,412,422.05**（DB 落库值逐位相同）；正确分母 67,022.89 ⇒ 污染率 0.31110 ⇒
**1,511,272.73**。**放大 2.26 倍，且方向是虚高** —— 会误触发扩大范围/调整，
或把总体误判为超可容忍错报。

**准则依据**：CAS 1314 只把「无法实施设计的程序**且**无法实施适当替代程序」的项目
视为偏差/错报。替代程序已实施 ⇒ 该项目已取得审计证据，应以其结论进入基数。

**修法**（新增两个纯函数，零 schema 变更、零留痕语义变更）：
- `applyAlternativeTreatment(samples, disposition)`：把 `alternative_performed` 的未检查
  样本改写为 `checkResult='Y'`，**不动 `actualMisstatement`**（留空 = `toDecimal(undefined)`
  = 0 = 替代程序未发现错报；审计师若在替代程序中发现错报，录入值原样参与推断，绝不覆盖）
- `applyUncheckedDisposition = applyAlternativeTreatment ∘ applyDeviationTreatment`
  （两类集合互斥，顺序无关），`inferMisstatement` 改走这一个统一入口
- 返回**新数组**：`buildUncheckedDispositionPayload` / `countTreatedAsDeviation` /
  `checkedSampleCount` / `uncheckedSampleCount` 全部读**原数组** ⇒ 留痕计数与处置记录
  逐位不变（「审计师实际检查 1 笔、3 笔未检查」仍如实记录），只有推断基数变了
- `UNCHECKED_DISPOSITION_HINTS.alternative_performed` 补「实际错报留空即替代程序未发现错报」

**新增 Property 28 守卫 8 例**（`samplingUncheckedDisposition.spec.ts`）+ 诚实改写
`samplingConfirmGating.spec.ts` 的「改写早于过滤」判据（符号换成统一入口 + 新增
「不得只处置视同偏差」防回退）。**变异检验 5/5 全 RED**：M1 调用点回退成
`applyDeviationTreatment`（3 条红）· M2 `applyAlternativeTreatment` 变空操作（3 条）·
M3 覆盖审计师录入的实际错报（2 条）· M4 就地改原样本（1 条）· M5 `fnBody` 不再跳过
内联返回类型注解（2 条）；三个源文件 md5 逐字节还原。

**修复后浏览器复测（固定随机种子 20260808 保可复算）**：样本 4,215.00（异常，
实际错报 1,000）/ 1,308.36（视同偏差）/ 50.00（**已实施替代程序**）/ 2,897.39（视同偏差），
总体 4,857,866.37 ⇒ UI 推断错报 **2,985,430.79**、UML **4,478,146.18**、增量准备
1,492,715.39，与独立 Decimal 复算逐位相同（旧口径会是 3,003,157.42 / 4,504,736.13
⇒ 已不再取旧值）；DB 落库 `projected="2985430.79"`。

**最终守卫状态**：后端本 spec 5 文件 **83 passed**；前端本 spec 11 文件 **260 passed / 0 failed**。

### 收口期新增踩坑（已同步 memory）

- **`voucher-extract` 端点零写库**（`record_extraction_log`/`db.add`/`commit`/`flush`/
  `INSERT`/`UPDATE` 在函数体内命中数全为 0），唯一疑似写入的
  `VersionTrailService.create_snapshot_fire_and_forget` 实测**未增行**
  （`workpaper_snapshots` 164→164）⇒ 抽样预览可安全用于浏览器实测；
  真正写库的是 **`重新推断`**（`POST /voucher-evaluation` 同时写权威 log 与投影表），
  实测前必须先抓 `extraction_criteria->'evaluation'` 的 `jsonb_typeof` 与
  `sampling_records` 五个字段作基线。
- **`.el-overlay` 是嵌套的**：函证/抽凭的子对话框与宿主共用同一个 overlay 节点
  ⇒ `find(o => o.innerText.includes('子对话框标题'))` 会命中**宿主** overlay；
  点它的 `.el-dialog__headerbtn` 会把整个宿主一起关掉（本轮丢掉一次已填样本）。
  正解 = 关最上层对话框用 `press_key Escape`。
- **PowerShell 的 `>` / `Out-File` 都会二次编码 UTF-8 中文**（前者按 GBK 解再存 UTF-8，
  后者更糟）⇒ python 脚本的中文输出要落干净文件必须走 **`cmd /c "python x.py > f 2>&1"`**
  （字节直通）。
- **`fnBody`/`blockOf` 取「参数列表之后第一个 `{`」会命中内联返回类型注解**
  （`function inferMisstatement(): { result: MisstatementResult ... } {`）—— memory 已记
  同族坑，本轮在**新写的守卫**里又踩一次。正解 = 逐个候选块配对，取第一个含语句特征
  （`const|let|return|if|for|await|function`）的块，并配一条内联 fixture 自检。
- **变异脚本的锚点含 `\n` 在 CRLF 工作树必 ANCHOR-MISS**（memory 已记，本轮 M4 再踩）
  ⇒ 一律单行锚点，且脚本要把 ANCHOR-MISS 与 GREEN **显式区分**（把 ANCHOR-MISS 当 GREEN
  会漏掉守卫缺陷）。
- **守卫写下的期望数字必须独立复算，不能拿被测代码的输出当期望**：本轮首版把
  `projected` 手算成 1,511,077.86（实际 1,511,272.73），是 `Decimal` 复算把它纠正的；
  同时用「真实库那次落库的 3,412,422.05」交叉验证旧口径 ⇒ 两个方向都不是自证。
