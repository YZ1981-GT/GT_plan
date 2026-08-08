# Design Document

## Overview

四波推进，前两波修正在产生错误数字的路径，后两波补监管闸门与收敛。

- **Wave 1（数据正确性）**：撤销同步撤销投影（R1）+ 合规检查判据修正与阈值可配（R2）
- **Wave 2（准则闭环）**：未检查样本处置（R3）+ 偏差性质（R4）+ 完整性阻断（R5）+ 分层层内评价（R6）
- **Wave 3（监管闸门）**：QC 引擎恢复执行 + QC-12 重写（R7）+ 归档章节（R8）
- **Wave 4（收敛与验收）**：属性抽样接线（R9）+ 复核入口（R10）+ 守卫/CI/实测（R11）

设计基调三条：

1. **权威与投影分工不变**。所有新增留痕仍写 `extraction_criteria.evaluation`（权威），投影表只做
   加法式镜像。撤销走软删而非物理删，保住可追溯。
2. **门控一律「前置 disable + tooltip」**。平台已登记铁律：门控提示指向被弹窗遮挡的区域等于死信。
   R3/R4/R5 三处新门控全部收敛到同一个 `confirmBlockedReason` 计算链，不新开提示通道。
3. **改变数字的改动配灰度 + 新旧并列**。只有 R6 会改变已有项目的推断错报值，故单独配开关，
   开启时 UI 并列展示两个口径；其余改动在「无未检查样本 + 无偏差 + 核对通过」时逐位等价。

## Architecture

```
撤销链路（R1，新增虚线部分）
  前端 undoLastExtraction
    → POST /voucher-undo
        → log.is_undone = True / status='undone'          （既有）
        ┄→ undo_sampling_registration(db, batch_id=...)    （新增，fail-open）
              ├ sampling_records.is_deleted = true   WHERE batch_id
              └ sampled_vouchers.is_deleted = true   WHERE batch_id
        → commit

评价链路（R3/R4/R5，新增字段）
  前端 buildEvaluationPayload
    → POST /sampling/voucher-evaluation
        → _normalize_evaluation（白名单扩容：三个结构化 key）
        → merge_evaluation_into_criteria（仍只写 evaluation 一个 key）
        → update_sampling_record_evaluation（投影扩容）

推断链路（R6，分层分支）
  projectMisstatement(samples, method, interval, popAmount, cl)
    → method==='stratified' && strataEvaluationEnabled
        → projectMisstatementByStrata(...)  逐层比率估计 + 未归层桶
        → 并列返回 legacy 口径供 UI 对照
    → 其余方法/开关关闭：既有路径逐位不变

QC 链路（R7）
  QCEngine._get_enabled_rule_codes
    → 查询成功且 rows 非空 → 仅 disabled 的排除（改：未登记视为启用）
    → 查询成功但 rows 为空 → 全部执行 + WARNING（改：原为全部不执行且无日志）
    → 查询失败 → 全部执行 + WARNING（既有）
  SamplingCompletenessRule
    → 改判据：查 workpaper_extraction_log（未撤销的 voucher_sampling 批次）
       缺评价 / 结论未确认 / dataset_stale → finding

归档链路（R8）
  archive_section_registry.register('05', '抽样记录汇总.md', generate_sampling_records_section)
    → 读 sampling_records（未软删）+ 关联 wp_index.wp_code
    → 输出 CAS 1314 记录项清单 + 「记录不完整」分节
  archive_completeness_service → 新增一项缺口检查
```

## Components and Interfaces

### 后端新增/改动

| 文件 | 改动 | 说明 |
|---|---|---|
| `services/sampling_registry_service.py` | 新增 `undo_sampling_registration(db, *, batch_id) -> dict` | 按 batch_id 软删两张投影行，返回 `{records: n, vouchers: n}`；fail-open + WARNING |
| 同上 | `register_sampled_vouchers` 增 `on_conflict` 后的复活逻辑 | 撤销后重新回填时把软删行 `is_deleted=false` 复活（R1.7），否则唯一索引让 DO NOTHING 静默跳过 |
| 同上 | `build_record_fields` 扩容 | 纳入 `unchecked_disposition` / `deviation_nature_summary` / `reconcile_override_reason` 摘要 |
| `routers/voucher_sampling.py` | `voucher_undo` 调 `undo_sampling_registration` | 仅 `extraction_type=='voucher_sampling'` 且 `batch_id` 非空 |
| 同上 | `_EVAL_*` 白名单扩容 | 新增 `_EVAL_JSON_KEYS`（结构化 dict/list 原样归一）与 `_EVAL_TEXT_KEYS` 追加 |
| 新建 `services/sampling_qc_rules.py` | 抽样 QC 判据纯函数 | `evaluate_sampling_completeness(batches) -> list[Finding]`，不连库便于单测 |
| `services/qc_engine.py` | `_get_enabled_rule_codes` 三态化 + `SamplingCompletenessRule` 重写 | 委托上述纯函数 |
| 新建 `services/archive_generators/sampling_records_generator.py` | 归档章节生成器 | 注册前缀 `05` |
| `services/archive_completeness_service.py` | 新增抽样记录完整性检查项 | 复用 `sampling_qc_rules` 同一判据 |

### 前端新增/改动

| 文件 | 改动 |
|---|---|
| `composables/useSamplingAlgorithms.ts` | `checkCAS1314Compliance` 签名改为 options 对象（`{stats, method, methodSampleCount, totalSampleCount, suggestedSampleSize, coverageThreshold}`）；新增 `projectMisstatementByStrata` / `summarizeDeviationNature` / `resolveUncheckedDisposition` |
| 新建 `composables/samplingCoverageThreshold.ts` | 阈值单一真源：`DEFAULT_COVERAGE_THRESHOLD = 0.60` + `resolveCoverageThreshold({wp, project})` + `THRESHOLD_SOURCE_LABELS` |
| 新建 `composables/samplingDeviationNature.ts` | 偏差性质枚举与提示语，**re-export** 自 `useDeviationDecisionTree` 的口径（不另写判定） |
| `composables/useVoucherSampling.ts` | `checkCompliance` 传对；评价载荷扩容；`confirmBlockedReason` 纳入三处新门控 |
| `voucher-sampling/GtVoucherSamplingEngine.vue` | 未检查处置列 + 偏差性质列 + 完整性放行理由 + 分层明细面板 + 新旧口径对照 + 两处 `GtReviewTrigger` |
| `cControlTest/*` | 统计抽样模式接 `computeAttributeSampleSize` / `evaluateDeviationRate` |

### 关键接口签名

```ts
// R2：阈值与判据入参化
export interface ComplianceCheckInput {
  stats: CoverageStats
  method: SamplingMethod
  /** 该方法抽出的样本数（不是勾选数） */
  methodSampleCount: number
  /** 全部样本数 */
  totalSampleCount: number
  /** 系统建议样本量；null = 判据不可用，不告警 */
  suggestedSampleSize: number | null
  /** 覆盖率阈值（小数），来源由 resolveCoverageThreshold 决定 */
  coverageThreshold: number
  thresholdSource: 'workpaper' | 'project' | 'platform_default'
}

// R6：分层评价
export interface StratumEvaluation {
  index: number            // -1 = 未归层桶
  label: string
  lowerBound: string
  upperBound: string
  populationAmount: string
  sampleCount: number
  sampleAmount: string
  sampleError: string
  projected: string
  unsampled: boolean       // 有总体无样本
}
export interface StratifiedMisstatementResult extends MisstatementResult {
  strataDetail: StratumEvaluation[]
  unclassifiedCount: number
  legacy: MisstatementResult   // 旧口径，供并列对照
}
```

```python
# R1
async def undo_sampling_registration(
    db: AsyncSession, *, batch_id: UUID | None
) -> dict[str, int]:
    """按 batch_id 软删两张投影行。batch_id 为 None 时不做任何事并 WARNING。"""

# R7
def evaluate_sampling_completeness(batches: list[SamplingBatchView]) -> list[str]:
    """纯函数：返回缺口消息列表。无批次返回 []（不适用 ≠ 不合规）。"""
```

## Data Models

无新表。三处 JSONB 扩容 + 两张投影表软删语义启用。

### `extraction_criteria.evaluation` 扩容（权威）

```json
{
  "projected": "1234.56",
  "unchecked_sample_count": 2,
  "unchecked_disposition": {
    "V-0012": {"mode": "treated_as_deviation", "note": null},
    "V-0033": {"mode": "alternative_performed", "note": "已核对银行流水与合同"}
  },
  "deviation_nature_summary": {
    "isolated":     {"count": 1, "amount": "500.00"},
    "systematic":   {"count": 2, "amount": "1800.00"},
    "undetermined": {"count": 0, "amount": "0.00"}
  },
  "reconcile_override_reason": "该科目无独立明细表，已与总账核对一致",
  "reconcile_override_by": "<uuid>",
  "reconcile_override_at": "2026-08-05T...",
  "stratified_evaluation": {
    "enabled": true,
    "projected_by_strata": "2100.00",
    "projected_legacy": "1980.00",
    "unclassified_count": 1
  },
  "coverage_threshold": 0.60,
  "coverage_threshold_source": "platform_default"
}
```

三条约束：
- 新 key 全部**可缺省**，缺省时行为与改造前一致（零回归支点）
- `unchecked_disposition` 以凭证号为键；同凭证多分录时以凭证号聚合（与 `filled_voucher_nos` 同粒度）
- `deviation_nature_summary` 是**派生摘要**，逐笔性质存在样本行里随底稿持久化，摘要只为投影与归档可查

### `sampling_records` 投影扩容

复用既有列，不加列：
- `deviations_found` ← `deviation_count`（含视同偏差的未检查样本，语义扩大后需在 `conclusion` 里说明）
- `conclusion` ← `conclusion_message` + 系统性偏差提示 + 完整性放行理由（拼接，带前缀标签）

不新增列的理由：这三项都是**说明性**内容，加列会让 V 号顺延且投影表列数膨胀；而查询场景
（QC/归档）都是整行读出后渲染，不做按列过滤。

### `sampled_vouchers` 软删语义

改造前 `is_deleted` 恒 `false`（无人写）。启用后：
- 撤销 → `is_deleted = true`
- 重新回填同批次 → 复活为 `false`（`register_sampled_vouchers` 在 DO NOTHING 后补一条 UPDATE）
- 全部查询方已带 `is_deleted == false` 条件（已核实四处），无需改查询

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| 投影撤销失败 | WARNING + 继续返回 `before_data` | 撤销是审计师主动操作，投影坏了不能让它失败 |
| `batch_id` 为 NULL | WARNING + 跳过 | 按 `workpaper_id` 宽删会误删同底稿其它批次 |
| 建议样本量不可推导 | 不告警 | 判据不可用 ≠ 不合规 |
| 样本不落任何层区间 | 归入未归层桶 + UI 提示 | 静默丢弃会低估、强塞相邻层会错配 |
| 某层有总体无样本 | 不参与外推 + 提示 | 外推需要样本证据，没有就是覆盖缺口 |
| `qc_rule_definitions` 空表 | 全部执行 + WARNING | 空表是「尚未配置」不是「全部禁用」 |
| 归档章节生成失败 | WARNING + 占位说明 | 不得让归档整体失败 |
| 分层评价异常 | 回退 legacy 口径 + 标注 | 宁可用旧口径也不给错数字 |

## Testing Strategy

- **后端**：`test_sampling_undo_registration.py`（撤销投影，含复活与 NULL batch_id）/
  `test_sampling_qc_rules.py`（纯函数判据 + 不适用场景）/ `test_qc_engine_rule_gating.py`
  （空表三态，含「复现旧行为则 active_rules 为空」反向自检）/
  `test_archive_sampling_records_section.py`
- **前端**：`samplingComplianceCriteria.spec.ts`（规则 2/3 判据 + 全选不误报反向自检）/
  `samplingCoverageThreshold.spec.ts` / `samplingUncheckedDisposition.spec.ts` /
  `samplingDeviationNature.spec.ts`（含与 C 类口径交叉锁死）/
  `stratifiedMisstatement.spec.ts`（含 PBT：层内加总 ≥ 0、未归层不丢金额）/
  `samplingConfirmGating.spec.ts`（三处门控前置 disable）/
  `attributeSamplingWiring.spec.ts`（消费方存在性，防回退孤儿）
- **真实库**：`backend/scripts/diagnose/verify_sampling_governance_live.py`（只读 + `--apply` 自动复原）
- **浏览器**：三件套（录数据 / 目标区出数 / postgres 查落库），测后逐字节复原

## Correctness Properties

### Property 1: 撤销后投影不再暴露该批次

对任意已登记批次，调用撤销后，`project_level_extracted_voucher_nos`、
`cross_workpaper_duplicate_vouchers`、`project_sampling_coverage` 三者的输出均不含该批次的凭证号与统计。

**Validates: Requirements 1.1, 1.4, 1.5, 1.6**

### Property 2: 撤销不越界

`undo_sampling_registration` 只影响 `batch_id` 相等的行；同底稿其它批次的投影行 `is_deleted` 保持不变。
`batch_id` 为 None 时两张表零行受影响。

**Validates: Requirements 1.2, 1.8**

### Property 3: 撤销后可重新登记且撤销留痕不丢

撤销后重新回填同一组凭证时，`record_extraction_log` 生成**新的 batch_id**（不复用），
新登记行以 `is_deleted=false` 插入且与被撤销的软删行共存；
`project_level_extracted_voucher_nos` 只返回新批次的凭证号一次（不重复）。

**Validates: Requirements 1.7**

### Property 4: 投影失败不阻断撤销

投影撤销抛异常时，`voucher_undo` 仍返回 `success=True` 与 `before_data`，且日志含 WARNING。

**Validates: Requirements 1.3**

### Property 5: 特定项目占比判据与勾选无关

对同一组样本，改变勾选集合不改变 `specific_item_high` 告警的产生与否；分子恒为特定项目法抽出的样本数。

**Validates: Requirements 2.1, 2.2**

### Property 6: MUS 样本量判据基于建议样本量

`mus_insufficient` 当且仅当 `totalSampleCount < suggestedSampleSize` 且后者非 null 时产生。

**Validates: Requirements 2.3, 2.4**

### Property 7: 覆盖率阈值无字面量

`checkCAS1314Compliance` 函数体内不含数字阈值字面量；阈值解析优先级为底稿 > 项目 > 平台默认，
默认值 0.60 且来源标签为 `platform_default`。

**Validates: Requirements 2.5, 2.6, 2.7, 2.8**

### Property 8: 未检查样本必须有处置才能确认结论

存在 `checkResult` 为空且未选择处置方式的样本时，`confirmBlockedReason` 非空且确认按钮 disabled；
未检查样本数为 0 时该门控不产生任何阻断。

**Validates: Requirements 3.1, 3.4, 3.6**

### Property 9: 视同偏差按 100% 污染率计入

处置为 `treated_as_deviation` 的样本，其对推断错报的贡献等于按 `actualMisstatement = 账面金额`
计算的结果，且计入 `deviation_count`。

**Validates: Requirements 3.2**

### Property 10: 替代程序须有说明

处置为 `alternative_performed` 且说明为空时，`confirmBlockedReason` 非空。

**Validates: Requirements 3.3**

### Property 11: 偏差性质口径与 C 类一致

`samplingDeviationNature` 的三个中文标签与 `useDeviationDecisionTree.getStepOptions(2)`
返回的 `label` 集合**逐字相等**（守卫运行时调用 C 类导出函数交叉锁死，非硬编码副本）；
取值域恰为 `systematic` / `human` / `random` 三个 key。

**Validates: Requirements 4.1, 4.4**

### Property 12: 待判断偏差与需说明性质缺说明均阻断

存在未标注性质的偏差，或存在 `systematic`/`human` 偏差但原因/影响说明为空时，
`confirmBlockedReason` 非空。

**Validates: Requirements 4.2, 4.3**

### Property 13: 系统性偏差提示随 A13 推送

存在系统性偏差时，`buildProjectedMisstatementDescription` 的输出包含该提示文本。

**Validates: Requirements 4.6**

### Property 14: 完整性核对未通过即阻断，理由可放行

核对不可用或差异超阈值时 `confirmBlockedReason` 非空；填写 ≥10 字理由后为空，
且理由与操作人、时间进入评价载荷。核对通过时不要求理由。

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**

### Property 15: 分层层内加总不丢金额

启用层内评价时，各层（含未归层桶）的样本金额之和等于全部样本金额之和；
`projected` 等于各层外推额之和且恒 ≥ 0。

**Validates: Requirements 6.1, 6.2**

### Property 16: 无样本层不外推但被提示

某层总体金额 > 0 且样本数为 0 时，该层 `projected` 为 "0.00" 且 `unsampled` 为 true。

**Validates: Requirements 6.3, 6.4**

### Property 17: 分层评价灰度等价与并列

开关关闭或 `strata` 为空时，`projectMisstatement` 输出与改造前逐位一致；
开启时返回 `legacy` 字段供并列展示。非 `stratified` 方法完全不受影响。

**Validates: Requirements 6.5, 6.6, 6.7, 6.8**

### Property 18: QC 规则门控三态

`qc_rule_definitions` 空表 → 全部内置规则执行 + WARNING；显式 `enabled=false` → 该规则不执行；
未登记 → 执行。反向自检：复现旧行为（空表→空集）必须打红。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 19: QC-12 判据不依赖 SamplingConfig

`SamplingCompletenessRule` 源码不引用 `SamplingConfig`；判据基于未撤销的 `voucher_sampling` 批次；
无批次时零 finding；结论已确认时零 finding。

**Validates: Requirements 7.4, 7.6, 7.7**

### Property 20: QC-12 finding 可追溯

产出的 finding 消息包含缺失项类别与批次标识。

**Validates: Requirements 7.5, 7.8**

### Property 21: 归档章节完备且不阻断

归档抽样章节包含全部 CAS 1314 记录项字段；无批次时输出说明文本；生成失败时输出占位且归档整体成功。

**Validates: Requirements 8.1, 8.2, 8.3, 8.5, 8.6**

### Property 22: 归档完整性报出抽样缺口

存在记录不完整批次时，归档完整性检查结果含对应缺口项，且与 QC-12 使用同一判据函数。

**Validates: Requirements 8.4**

### Property 23: 属性抽样有真实消费方

`computeAttributeSampleSize` / `evaluateDeviationRate` 存在非测试文件的生产消费方；
快捷表与统计抽样两套并存有守卫登记边界，禁止合并。

**Validates: Requirements 9.1, 9.2, 9.4, 9.5, 9.6**

### Property 24: 快捷表模式零回归

控制测试选择快捷表模式时，样本量结果与改造前逐位一致。

**Validates: Requirements 9.3**

### Property 25: 抽样引擎有复核入口且只读态受控

引擎模板含 `GtReviewTrigger` 且 section_id 已在后端登记专属 prompt；只读态下配置与回填入口 disabled。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

### Property 26: 全关闭时逐位等价

全部灰度开关关闭、无未检查样本、无偏差、核对通过时，评价与推断结果与改造前逐位一致。

**Validates: Requirements 11.1**

### Property 27: 守卫具备反向自检

每个新增守卫文件至少含一处反向自检，复现旧缺陷时打红。

**Validates: Requirements 11.2, 11.3**

### Property 28: 已实施替代程序的样本进入推断基数

处置为 `alternative_performed` 的未检查样本，必须进入比率估计的分子与分母（错报按审计师
录入值，留空即 0 = 替代程序未发现错报），不得因 `checkResult` 为空而被
`inferMisstatement` 的既有过滤整体排除。

反向自检：仅做视同偏差改写时，替代程序样本被挤出分母 ⇒ 推断错报被放大，方向必须是
「旧口径虚高」。用真实库实测那组数字钉死（旧 3,412,422.05 / 新 1,511,272.73，
总体 4,857,866.37），两个值均经独立 Decimal 复算核对。

**Validates: Requirements 3.3, 11.2, 11.3**
