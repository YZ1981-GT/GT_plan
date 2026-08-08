# Requirements Document

## Introduction

本 spec 收口抽样/抽凭模块在 `sampling-compliance-closure`（24/25）之后仍然存在的评价环节缺口、
判据错误、监管闸门空转与数据一致性缺陷。

前序 spec 已解决的（**本 spec 不重做**）：抽样框 dataset 绑定与 stale 三态、评价结果持久化
（`extraction_criteria.evaluation`）、A13 `projected` 类型通路、legacy 抽样引擎删除、
CAS 1314 记录表两张投影接入（`sampling_records` / `sampled_vouchers`）、跨底稿重复抽凭显式确认、
78 个宿主的方法学 bar 与样本最小字段集。

本 spec 的立项事实基线（2026-08-05 逐个实证，**不是照搬前序 spec 或 memory**）：

| # | 事实 | 证据 |
|---|---|---|
| F1 | `voucher_undo` 只写 `is_undone`/`status`，完全不触碰两张投影表 | `voucher_sampling.py:714-716` 全函数无 `SampledVoucher`/`SamplingRecord` 引用 |
| F2 | 投影表已在产出真实数据 | 真实库 `sampling_records`=1 行 / `sampled_vouchers`=22 行（21 行 `batch_id` 非空=引擎登记，1 行为穿透页手工标记） |
| F3 | 撤销与投影的交互零测试覆盖 | `test_sampling_registry_service.py`（657 行）`undo` 零命中；`test_voucher_sampling_batch_wiring.py` 有 undo 但零 registry 引用 |
| F4 | `checkCAS1314Compliance` 调用方传 `(selectedCount, sampledVouchers.length)` | `useVoucherSampling.ts:1378-1387` |
| F5 | 60% 覆盖率阈值写死在函数体内，是唯一覆盖率告警口径 | `useSamplingAlgorithms.ts:275-283` |
| F6 | `projectMisstatement` 无 strata 参数，`stratified` 与经典法合并计算 | `useSamplingAlgorithms.ts:667-673` 签名 |
| F7 | `strata` 已进留痕，形态 `{lower_bound, upper_bound, sample_size}`（金额区间） | `useVoucherSampling.ts:837-844` |
| F8 | 前端 `SampledVoucher` 无层标识字段 | 接口无 `stratumIndex`/`stratum` 相关字段 |
| F9 | 未检查样本只有计数 + 一句 warning，无处置字段 | `_EVAL_COUNT_KEYS` 含 `unchecked_sample_count`；`GtVoucherSamplingEngine.vue:436-437` |
| F10 | 评价字段无偏差性质/原因；C 类控制测试侧已有偏差决策树 | `_EVAL_TEXT_KEYS = ("conclusion_message","algo_version")`；`composables/useDeviationDecisionTree.ts`（298 行） |
| F11 | 完整性核对失败不阻断，`confirmBlockedReason` 只看 `conclusionConfirmed` | `GtVoucherSamplingEngine.vue:248,457,464` |
| F12 | 属性抽样三个纯函数零生产消费方 | `computeAttributeSampleSize` / `evaluateDeviationRate` / `DEFAULT_TOLERABLE_DEVIATION_RATE` 全仓仅 `useSamplingAlgorithms.ts` 自身 + 2 个测试文件 |
| F13 | 控制测试用的是 `useSampleSizeEngine`（频率×次数查表） | `CControlTestSubPage.vue` / `CControlTestSummaryTable.vue` |
| F14 | QC-12 双重失效 | 遍历 `SamplingConfig`（真实库 **0 行**，已软弃用）；且 `build_record_fields` 不含 `sampling_config_id`，真实库 `sr_with_config`=0 |
| F15 | **QCEngine 全部 20 条规则静默不执行** | `qc_rule_definitions` 表存在但真实库 **0 行** → `_get_enabled_rule_codes` 返回空集（非 except 分支，故无 WARNING）→ `active_rules=[]` |
| F16 | 归档完整性完全不感知抽样 | `archive_completeness_service.py` / `completeness_service.py` / `archive_manifest_service.py` 的 `sampling`/`抽样`/`抽凭` 提及数均为 0 |
| F17 | 抽凭引擎零复核入口 | `GtVoucherSamplingEngine.vue`（1163 行）`GtReviewTrigger`/`openReviewDialog` 均 0 命中 |
| F18 | 已登记批次无评价 | 真实库 `sr_with_conclusion`=0 / `sr_with_projected`=0 —— 正是 QC 应抓而抓不到的情形 |

**明确不做（另立 spec）**：20 份 per-cycle 抽凭 composable 的行模型收敛（核对项形态已漂移：
D2 `check1..check5: string` vs D3 `checkItems: boolean[]`），半径覆盖 62 个文件，归
`voucher-check-shared-layer`。

**四个裁决点已按下列默认落地**（用户 2026-08-05 授权「逐一修复」，如需改口径在实现前提出）：
1. 完整性核对失败 → 阻断 + 允许填写理由放行并留痕（硬阻断会让合法例外无法推进）
2. 覆盖率阈值 → 项目级可配 + 底稿级覆盖，**默认仍为 60% 保零回归**，但显式标注「非准则数字」
3. 属性抽样 → 接线到控制测试；`useSampleSizeEngine` 保留作实务快捷表并加边界守卫
4. 分层层内评价 → 灰度开关 + 新旧口径并列展示（会改变已有项目的推断错报数字）

## Requirements

### Requirement 1: 撤销回填时同步撤销抽样登记投影

**User Story:** 作为审计助理，当我撤销一次抽凭回填后，该批次的样本不应再出现在项目级已抽清单、
重复抽凭提示和抽样概览中，否则那些凭证会永久抽不到、且项目级统计虚高。

#### Acceptance Criteria

1. WHEN `POST /voucher-undo` 成功标记 `is_undone=True` THEN 系统 SHALL 按该 log 的 `batch_id` 把 `sampling_records` 与 `sampled_vouchers` 中对应行的 `is_deleted` 置为 `true`
2. WHEN 该 log 的 `batch_id` 为 `NULL` THEN 系统 SHALL 跳过投影撤销并记录 WARNING，不得按 `workpaper_id` 宽范围删除（会误删同底稿其它批次）
3. WHEN 投影撤销失败 THEN 系统 SHALL 记录 WARNING 后继续返回 `before_data`，不得让投影失败使审计师的撤销整体失败
4. WHEN 投影撤销成功 THEN `project_level_extracted_voucher_nos` SHALL 不再返回该批次的凭证号
5. WHEN 投影撤销成功 THEN `cross_workpaper_duplicate_vouchers` SHALL 不再把该批次计入重复来源
6. WHEN 投影撤销成功 THEN `project_sampling_coverage` 的 `batch_count`/`sample_count`/`duplicated` SHALL 不再包含该批次
7. WHEN 撤销后重新回填同一组凭证 THEN 系统 SHALL 能重新登记，且新登记行与被撤销的软删行共存（撤销留痕不丢）
   - **实证修正（2026-08-05）**：立项时以为需要「复活软删行」，实测 `record_extraction_log` 的幂等去重只命中 `is_undone=false` 的 log，撤销后重新回填会新建 log 并生成**新的 uuid4 `batch_id`** ⇒ V139 部分唯一索引（`WHERE is_deleted=false`）下新旧行 batch_id 不同、天然不冲突。本条**无需代码**，守卫只需钉死该不变式防将来把 batch_id 改成复用
8. IF 撤销的 log 不是 `extraction_type='voucher_sampling'` THEN 系统 SHALL 不触碰投影表

### Requirement 2: 合规检查判据修正与阈值可配

**User Story:** 作为现场经理，我需要合规告警反映真实的准则风险而不是「有没有全选」，否则告警会
被当噪声忽略，真正的样本量不足反而看不见。

#### Acceptance Criteria

1. WHEN 抽样方法为 `specific_item` THEN 特定项目占比 SHALL 按「特定项目法抽出的样本数 / 全部样本数」计算，不得使用勾选数作分子
2. WHEN 审计师全选所有样本 AND 方法为 `specific_item` THEN 系统 SHALL NOT 仅因全选而触发 `specific_item_high` 告警
3. WHEN 抽样方法为 `mus` THEN 样本量不足 SHALL 判为「实际样本数 < 系统建议样本量（`computeSuggestedSampleSize`）」，不得判为「实际勾选数 < 抽出总数」
4. IF 系统建议样本量无法推导（缺置信度或可容忍错报）THEN 系统 SHALL NOT 触发 `mus_insufficient` 告警（判据不可用时不告警，而非默认告警）
5. WHEN 计算金额覆盖率告警 THEN 阈值 SHALL 由入参传入，`checkCAS1314Compliance` 函数体内不得出现字面量阈值
6. WHEN 未显式提供阈值 THEN 系统 SHALL 使用默认 `0.60` 并在方法学留痕中记录该阈值来源为「平台默认（非准则规定）」
7. WHEN 项目或底稿配置了自定义覆盖率阈值 THEN 系统 SHALL 优先使用底稿级、其次项目级、最后平台默认
8. WHEN 告警文案展示给审计师 THEN 覆盖率告警 SHALL 明示当前阈值取值与来源，避免被误认为准则硬性要求

### Requirement 3: 未检查样本的准则处置出口

**User Story:** 作为业务合伙人，对于无法实施审计程序的样本，我需要审计师明确选择「视同偏差」还是
「实施替代程序」并留痕，否则这部分样本既不计入错报也没有替代证据，抽样结论不成立。

#### Acceptance Criteria

1. WHEN 存在 `checkResult` 为空的样本 THEN 系统 SHALL 要求审计师为每笔未检查样本选择处置方式：`treated_as_deviation`（视同偏差）或 `alternative_performed`（已实施替代程序）
2. WHEN 处置方式为 `treated_as_deviation` THEN 该样本 SHALL 计入 `deviation_count`，且其账面金额 SHALL 按 100% 污染率纳入错报推断
3. WHEN 处置方式为 `alternative_performed` THEN 系统 SHALL 要求填写替代程序说明（非空），该样本 SHALL 按替代程序结论参与推断
4. WHEN 存在未选择处置方式的未检查样本 THEN 系统 SHALL 阻止确认抽样结论，并前置 disable 确认按钮 + tooltip 说明原因
5. WHEN 评价持久化 THEN 系统 SHALL 记录 `unchecked_disposition` 结构（每笔样本的处置方式与说明），并纳入 `sampling_records` 投影
6. WHEN 未检查样本数为 0 THEN 本需求的全部门控 SHALL 不生效（零回归）

### Requirement 4: 偏差性质与原因结构化

**User Story:** 作为质量控制复核合伙人，我需要看到每笔偏差的性质（孤立事件/系统性）、原因和
对总体结论的影响判断，而不是一个偏差笔数加一段自由文本。

#### Acceptance Criteria

1. WHEN 样本 `checkResult` 为 `N` 或 `异常` THEN 系统 SHALL 允许审计师标注偏差性质，取值域为 `systematic` / `human` / `random`，未标注即待判断（`null`）
   - **实证修正（2026-08-05）**：立项时写的 `isolated`/`systematic`/`undetermined` 与 C 类既有口径不同构。`useDeviationDecisionTree` 的 `getStepOptions(2)` 实为三值中文 **`系统性偏差` / `人为偏差` / `随机性偏差`**（多出「人为偏差」一档，「待判断」在 C 类表现为 `null` 而非独立枚举值）。按 R4.4「复用不另写」，取值域改为与之一一对应的三个英文 key，中文标签由 C 类口径派生
2. WHEN 偏差性质为 `systematic` 或 `human` THEN 系统 SHALL 要求填写原因说明与影响评估（非空），并在结论区显著提示「不宜简单外推，应考虑扩大范围或改变审计方法」
3. WHEN 存在未标注性质（`null`）的偏差 THEN 系统 SHALL 阻止确认抽样结论
4. WHEN 偏差性质判断逻辑实现 THEN 系统 SHALL 复用 C 类控制测试既有口径（`useDeviationDecisionTree.getStepOptions(2)` 的中文标签逐字一致），不得另写一套判定
5. WHEN 评价持久化 THEN 系统 SHALL 记录 `deviation_nature_summary`（按性质分组的笔数与金额）+ 逐笔 `deviationNature`/`deviationCause`
6. WHEN 存在系统性偏差 THEN 推送 A13 的错报描述 SHALL 包含该提示，供错报汇总环节看见

### Requirement 5: 总体完整性核对未通过时阻断结论确认

**User Story:** 作为业务合伙人，从不完整的总体中抽样会让整个抽样结论无效，这比「结论未人工确认」
更该阻断，但合法例外（如确无独立账面来源）应能填写理由后推进。

#### Acceptance Criteria

1. WHEN 总体完整性核对不可用（无独立账面且未手工录入）THEN 系统 SHALL 阻止确认抽样结论
2. WHEN 核对差异超出可容忍差异比例 THEN 系统 SHALL 阻止确认抽样结论
3. WHEN 被阻断 THEN 系统 SHALL 提供「填写理由后继续」入口，理由非空且不少于 10 字方可放行
4. WHEN 审计师填写理由放行 THEN 系统 SHALL 把 `reconcile_override_reason` 与操作人、时间写入评价留痕并投影到 `sampling_records`
5. WHEN 阻断提示展示 THEN 系统 SHALL 前置 disable 确认按钮 + tooltip，且不得把提示指向被弹窗遮挡的区域
6. WHEN 核对通过 THEN 本需求门控 SHALL 不生效，且不得要求填写理由（零回归）

### Requirement 6: 分层抽样的层内单独评价

**User Story:** 作为 EQCR 技术复核人，分层抽样各层抽样比例不同，把全部样本合并做比率估计会产生
系统性偏误，我需要各层单独外推后加总。

#### Acceptance Criteria

1. WHEN 抽样方法为 `stratified` THEN 系统 SHALL 按 `strata` 的金额区间把样本与总体分别归入各层，逐层做比率估计外推后加总为 `projected`
2. WHEN 样本金额不落入任何声明的层区间 THEN 系统 SHALL 归入「未归层」桶单独外推，并在 UI 显式提示未归层样本数（不得静默丢弃，也不得强行塞入相邻层）
3. WHEN 某层无样本但有总体金额 THEN 该层 SHALL NOT 参与外推，且系统 SHALL 提示该层未被抽样（覆盖不足的证据）
4. WHEN 层内评价启用 THEN 系统 SHALL 同时给出层级明细（各层总体金额/样本金额/样本错报/该层外推额），供审计师复核推断过程
5. WHEN 分层信息缺失或为空数组 THEN 系统 SHALL 回退既有合并口径并标注 `stratified_fallback=true`
6. WHEN 灰度开关关闭 THEN 系统 SHALL 使用既有合并口径，结果与改造前逐位一致
7. WHEN 灰度开关开启 THEN UI SHALL 并列展示新旧两个口径的 `projected`/`upperLimit`，差异非零时提示审计师复核
8. WHEN 抽样方法不是 `stratified` THEN 本需求 SHALL 完全不生效

### Requirement 7: QC 引擎恢复执行 + 抽样 QC 规则重写

**User Story:** 作为质量控制复核合伙人，我需要 QC 自检真的在跑，并且抽样相关规则检查的是
「有批次却没有评价/结论」而不是已废弃的 `sampling_config`。

#### Acceptance Criteria

1. WHEN `qc_rule_definitions` 查询成功但返回 0 行 THEN 系统 SHALL 降级为执行全部内置规则并记录 WARNING，不得静默把 `active_rules` 置空
2. WHEN 规则被 `qc_rule_definitions` 显式登记且 `enabled=false` THEN 该规则 SHALL 不执行（保留原有关闭能力）
3. WHEN 内置规则的 `rule_id` 在 `qc_rule_definitions` 中不存在 THEN 该规则 SHALL 执行（未登记视为启用），并记录一次性 INFO 便于补登记
4. WHEN QC-12 执行 THEN 判据 SHALL 改为「该底稿存在未撤销的 `voucher_sampling` 批次，但缺少评价/结论/人工确认」，不得依赖 `SamplingConfig`
5. WHEN 该底稿存在 `dataset_stale=true` 的批次 THEN QC-12 SHALL 产出 finding，提示抽样框已变更需复核
6. WHEN 该底稿存在批次且结论已人工确认 THEN QC-12 SHALL NOT 产出 finding
7. WHEN 该底稿无任何抽凭批次 THEN QC-12 SHALL NOT 产出 finding（不适用而非不合规）
8. WHEN QC-12 产出 finding THEN 消息 SHALL 指明缺失项（缺评价 / 结论未确认 / 抽样框过期）与批次标识，可追溯

### Requirement 8: 归档完整性纳入抽样记录

**User Story:** 作为质量控制复核合伙人，CAS 1314 的记录要求是归档件的组成部分，归档包里应能
一次性看到本项目全部抽样的总体描述、样本量依据、偏差与结论。

#### Acceptance Criteria

1. WHEN 生成归档包 THEN 系统 SHALL 注册一个抽样记录章节，输出本项目全部未撤销抽样批次的 CAS 1314 记录项清单
2. WHEN 抽样记录章节生成 THEN 内容 SHALL 包含：底稿索引、抽样目的、总体描述、样本量与确定依据、抽样框版本、随机种子、偏差笔数、推断错报、错报上限、结论、结论确认人与时间
3. WHEN 存在缺失评价或结论未确认的批次 THEN 该章节 SHALL 单独列出并标注「记录不完整」
4. WHEN 归档完整性检查执行 THEN 系统 SHALL 把「存在记录不完整的抽样批次」作为一项完整性缺口报出
5. WHEN 项目无任何抽样批次 THEN 该章节 SHALL 输出「本项目未执行抽样程序」而非空文件或报错
6. WHEN 章节生成失败 THEN 系统 SHALL 记录 WARNING 并输出占位说明，不得让归档整体失败

### Requirement 9: 属性抽样能力接线或显式豁免

**User Story:** 作为审计助理，做控制测试时我需要能用统计口径确定样本量并评价偏差率上限，而不是
只有一张频率×次数快捷表。

#### Acceptance Criteria

1. WHEN 控制测试底稿选择「统计抽样」模式 THEN 系统 SHALL 使用 `computeAttributeSampleSize` 推导样本量，并展示置信度、可容忍偏差率、预期偏差率入参
2. WHEN 控制测试录入偏差笔数 THEN 系统 SHALL 使用 `evaluateDeviationRate` 给出偏差率上限与「是否可依赖该控制」的结论
3. WHEN 控制测试选择「快捷表」模式 THEN 系统 SHALL 继续使用 `useSampleSizeEngine`，行为与改造前逐位一致
4. WHEN 两套方法学并存 THEN 系统 SHALL 有守卫说明边界：`useSampleSizeEngine` 服务频率×次数快捷表、`computeAttributeSampleSize` 服务统计抽样，禁止后来者合并
5. WHEN 属性抽样纯函数被消费 THEN 守卫 SHALL 断言其存在真实生产消费方（非测试文件），杜绝回退为孤儿
6. IF 控制测试统计抽样接线因超出范围而暂不实施 THEN 该决定 SHALL 在基线文件中登记理由，且守卫断言登记项与实际孤儿集合一致

### Requirement 10: 抽样引擎复核入口

**User Story:** 作为现场经理，抽样是审计判断最集中的环节（总体界定、样本量、种子、未检查样本
处置、结论采纳），我需要能对它做一级复核并留痕。

#### Acceptance Criteria

1. WHEN 打开抽凭引擎 THEN 系统 SHALL 在配置区、结论区各提供复核入口（`GtReviewTrigger`）
2. WHEN 发起复核 THEN `section_id` SHALL 能定位到具体底稿与区段，并在后端登记专属复核 prompt
3. WHEN 底稿处于只读态（归档/锁定/年审阶段的预审行）THEN 抽样配置与回填入口 SHALL disabled
4. WHEN 复核 prompt 登记 THEN 每条 SHALL 明示源模板/准则口径并含「不得虚构」约束

### Requirement 11: 零回归与守卫

**User Story:** 作为平台维护者，我需要这批改动可验证、不破坏既有行为，且缺陷不会静默回退。

#### Acceptance Criteria

1. WHEN 全部灰度开关关闭 AND 无未检查样本 AND 无偏差 AND 核对通过 THEN 抽样评价结果 SHALL 与改造前逐位一致
2. WHEN 编写守卫 THEN 每条 SHALL 配至少一处反向自检（复现旧缺陷必须打红）
3. WHEN 守卫编写完成 THEN SHALL 逐条执行变异检验（改一字看是否变红），变异未打红视为守卫缺陷
4. WHEN 真实库验证 THEN SHALL 提供只读诊断脚本，覆盖撤销后投影状态、QC 规则实际执行条数、归档章节产出
5. WHEN 浏览器实测 THEN SHALL 满足三件套（录入真实数据 + 目标区域出数 + postgres 查落库），并在测后逐字节复原数据
6. WHEN CI 接入 THEN 后端与前端守卫 SHALL 各挂 job，且 workflow YAML 可解析

## Glossary

| 术语 | 含义 |
|------|------|
| 权威留痕 | `workpaper_extraction_log.extraction_criteria` JSONB，抽样时点的可复算依据，唯一权威 |
| 投影表 | `sampling_records` / `sampled_vouchers`，供项目级与 QC 级查询的可查询侧投影，与权威同一次写入 |
| batch_id | 抽凭批次标识，投影行与权威 log 的唯一关联键（`working_paper_id` 粒度太粗，同底稿可有多批次） |
| 未检查样本 | `checkResult` 为空的样本；准则要求「视同偏差」或「实施替代程序」二选一 |
| 偏差性质 | 孤立事件 vs 系统性；系统性偏差不宜简单外推，需扩大范围或改变审计方法 |
| 层内评价 | 分层抽样时各层单独外推后加总，替代把全部样本合并做比率估计 |
| 未归层桶 | 样本金额不落入任何声明层区间时的独立归集，单独外推且必须在 UI 提示 |
| UML | Upper Misstatement Limit，错报上限 = 推断错报 + 基本准备 + 增量准备 |
| 快捷表 | `useSampleSizeEngine` 的控制频率×测试次数区间表，实务经验值而非统计抽样 |
| 属性抽样 | CAS 1314 附录的控制测试统计抽样（泊松系数推样本量 + 偏差率上限评价） |
