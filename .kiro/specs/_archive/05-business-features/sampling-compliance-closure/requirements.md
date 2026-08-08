# Requirements Document

## Introduction

审计抽样（CAS 1314）与抽凭的 canonical 链路本身已相当成熟：`voucher_sampling.py` →
`voucher_sampling_algorithms.py`（5 方法 + seed）+ `sampling_methodology.py`（泊松可信赖度
系数单一真源）+ `sampling_batch_service.py`（批次状态机），已覆盖两阶段全量框、诚实覆盖率
分母、独立账面完整性核对、高值必选、行级排除、预审→年审排重、结论确认门禁、推断错报/UML
计算、备忘导出、历史/撤销/版本对比。

但 2026-08-04 的复盘（源码 + 生产库双向实证）发现**准则主线断在最后一环**，且存在多轨残留：

1. **推断错报从不进入错报汇总**。`useA13MisstatementBridge.ts` 把 `misstatement_type`
   硬编码为 `'factual'`；PG enum `misstatement_type` 的 `judgmental` / `projected` 两值
   **零使用**（全库 1 行错报且是 factual）。CAS 1314 算出的 projected/UML 无法进入 A13，
   CAS 1251 要求的三类错报分别汇总评价也无从做起。
2. **错报推断结果不持久化**。`misstatementResult` / `samplingConclusion` /
   `conclusionConfirmed` 都是 `useVoucherSampling` 内的裸 ref，而 81 个宿主的抽凭 dialog
   全是 `destroy-on-close` → 关弹窗即丢；`confirmFill` 写入 `extraction_criteria` 的字段
   里**没有** projected / knownHighValue / basicPrecision / incrementalAllowance /
   upperLimit / 已检查样本数 / 偏差笔数。且时序上 `confirmFill` 早于逐笔核查。
3. **抽样未绑定序时账数据集版本**。抽样链路全文无 `dataset_id`，查询走
   `get_active_filter`（当前 active）。序时账重导后同 seed 同参数复跑得到不同样本且无提示
   → 「seed 可复现」在数据集变更后不成立，CAS 1131 的可复算要求落空。平台已有正确先例：
   `unadjusted_misstatements.bound_dataset_id`。
4. **legacy `WpSamplingEngine` 仍挂两个活端点**（前端零调用），金额口径 `debit + credit`
   与 canonical 的 `GREATEST(debit, credit)` 不同，分层写死 `max*0.33/0.66` + 权重
   `0.2/0.3/0.5`，MUS 用固定 interval，不落日志/不入批次/不可撤销；
   `fill_sampling_to_workpaper` 写 `parsed_data.action_data` 而前端零消费（dead write）。
   现有 canonical guard 只断言「`voucher_sampling.py` 不引用 legacy」，未覆盖全仓。
5. **CAS 1314 正式记录三表是孤儿**。`sampling_config` 0 行 / `sampling_records` 0 行 /
   `sampled_vouchers` 1 行（10 项目、`tb_ledger` 697 万行）。`sampling_records` 的
   `deviations_found` / `projected_misstatement` / `upper_misstatement_limit` /
   `conclusion` 正是准则记录项却空置；`sampled_vouchers` 唯一写入点是
   `ledger_penetration.py`（穿透页手工标记），与抽凭引擎完全不通 → 重复抽凭只在同一
   `workpaper_id` 内排除，同一凭证被多循环重复抽取项目层面发现不了。
6. **81 个宿主接引擎、42 个丢弃 `methodology`**（最极端者只保留摘要文本，凭证号/日期/
   金额/科目全丢）→ 底稿正文（打印/归档件）不体现抽样方法学。

本 spec 覆盖上述 1~6，按「合规闭环 → 多轨清理 → 宿主收口」三波推进。
**抽凭表共享层**（19 份 per-cycle `useXVoucherCheck` 收敛）半径过大，另立 spec，不在本范围。

## Glossary

| 术语 | 含义 |
|------|------|
| canonical 抽凭链路 | `voucher_sampling.py` 路由 + `voucher_sampling_algorithms.execute_sampling` + `sampling_methodology` 三件套，平台唯一合法抽样口径 |
| legacy 抽样引擎 | `backend/app/services/wp_sampling_engine.py` 的 `WpSamplingEngine`，口径与 canonical 不同，本 spec 予以下线 |
| 抽样框（sampling frame） | 本次抽样所依据的序时账总体，由 (project, year, active dataset, 过滤条件) 唯一确定 |
| dataset 绑定 | 把抽样时点的 `ledger_datasets.id` 记入留痕，用于判定后续能否以同一 seed 复算 |
| 批次（batch） | 一次「抽样 → 回填」形成的 `workpaper_extraction_log` 记录，由 `batch_id` 标识，状态 draft/confirmed/filled/undone |
| evaluation（抽样评价） | CAS 1314 的样本评价输出：推断错报 / 高值层已知错报 / 基本准备 / 增量准备 / 错报上限 / 偏差笔数 / 总体结论 |
| projected（推断错报） | 由样本错报按抽样口径推断到总体的错报，`misstatement_type` 三值之一，与事实错报/判断错报并列汇总 |
| UML（错报上限） | Upper Misstatement Limit = 推断错报 + 基本准备 + 增量准备，用于与可容忍错报比较得出结论 |
| methodology 快照 | 后端 `build_methodology_snapshot` 输出的权威方法学口径（含 `algo_version`），前端以此为准展示与留痕 |
| 宿主（host） | 引入 `GtVoucherSamplingEngine` 的底稿 Tab 组件，共 81 个 |

## Requirements

### Requirement 1: 抽样框数据集绑定（可复算前提）

**User Story:** 作为质量控制复核合伙人，我需要知道某次抽样是在哪一版序时账上执行的，
以便在序时账被重导后识别该抽样已不可复算，而不是误以为同一 seed 就能复现。

#### Acceptance Criteria

1.1 WHEN `POST /sampling/voucher-extract` 执行成功 THEN 响应 `stats` 中 SHALL 包含
    `dataset_id` 字段，取值为该 (project, year) 当前 active 的 `ledger_datasets.id`
    字符串；无 active 数据集时为 `null`。
1.2 WHEN 项目该年度无 active 数据集 THEN 前端 SHALL 显示「未识别到已激活账套版本，本次
    抽样无法绑定抽样框版本」提示，且 SHALL NOT 阻断抽样执行。
1.3 WHEN 前端调用 `POST /sampling/cutoff-fill` 记录抽凭回填 THEN `extraction_criteria`
    中 SHALL 包含 `dataset_id`（来自本次 extract 响应，缺失时为 `null`）。
1.4 WHEN `GET /sampling/voucher-history` 返回记录 THEN 每条记录 SHALL 额外包含
    `dataset_id` 与 `dataset_stale` 两字段；`dataset_stale` 为 `true` 当且仅当该记录的
    `dataset_id` 非空且不等于当前 active 数据集 id。
1.5 WHEN 某条历史记录 `dataset_stale` 为 `true` THEN 抽凭历史抽屉 SHALL 在该行渲染
    「抽样框已变更」告警 tag，并在 tooltip 说明「该批次抽样所依据的序时账版本已被替换，
    以相同随机种子重跑不会得到相同样本，需重抽或书面说明」。
1.6 WHEN `dataset_id` 为 `null`（历史记录改造前的既有数据） THEN `dataset_stale` SHALL
    为 `false`，且 UI SHALL NOT 报告告警（不把「未知」当「已变更」）。

### Requirement 2: 抽样评价结果持久化与回读

**User Story:** 作为现场经理，我需要打开底稿就能看到上一批次的推断错报、错报上限与总体
结论，而不是每次都重新逐笔录入实际错报再重算。

#### Acceptance Criteria

2.1 系统 SHALL 提供 `POST /api/projects/{pid}/sampling/voucher-evaluation` 端点，接收
    `{workpaper_id, log_id?, evaluation}`，把 `evaluation` upsert 进目标
    `workpaper_extraction_log.extraction_criteria.evaluation`。
2.2 WHEN 请求未提供 `log_id` THEN 端点 SHALL 定位该底稿最近一条
    `extraction_type='voucher_sampling'` 且 `is_undone=false` 的记录；不存在时返回 404。
2.3 `evaluation` 载荷 SHALL 至少承载：`projected`、`known_high_value`、
    `basic_precision`、`incremental_allowance`、`upper_limit`、`checked_sample_count`、
    `unchecked_sample_count`、`deviation_count`、`tolerable_misstatement`、
    `conclusion_code`、`conclusion_message`、`conclusion_confirmed`、`algo_version`、
    `evaluated_at`、`evaluated_by`。
2.4 端点 SHALL 在任何写入之前复用与 `voucher-extract` 相同的授权与跨项目校验
    （编辑权 + 底稿归属 pid），拒绝时返回 403/404 且目标记录零变化。
2.5 WHEN `confirmFill` 提交回填且此时已存在推断结果 THEN 该结果 SHALL 以同一
    `evaluation` 形状随 `extraction_criteria` 一并落库（避免必须二次调用）。
2.6 WHEN `GET /sampling/voucher-history` 返回记录 THEN 每条 SHALL 额外包含
    `evaluation` 字段（无则为 `null`）。
2.7 WHEN 抽凭引擎打开且本会话尚未执行新抽样 THEN 引擎 SHALL 从最近一条未撤销批次回读
    `evaluation`，据此还原 `misstatementResult` / `samplingConclusion` /
    `conclusionConfirmed`，并在错报推断区标注来源批次与评价时间。
2.8 WHEN 用户执行了新抽样 THEN 回读的旧评价 SHALL 被清空（不得把上一批次的结论挂到新
    批次上）。
2.9 WHEN 用户在预览区录入/修改 `actualMisstatement` 并触发推断 THEN 引擎 SHALL 调用
    2.1 的端点持久化最新评价，失败时提示且不静默吞错。

### Requirement 3: 推断错报进入 A13 错报汇总

**User Story:** 作为业务合伙人，我需要把抽样推断出的总体错报与已识别错报一并汇总后再与
重要性比较，这是形成审计意见的必要步骤。

#### Acceptance Criteria

3.1 `MisstatementDraft` SHALL 新增可选字段 `misstatementType`，取值域
    `'factual' | 'judgmental' | 'projected'`。
3.2 `normalizeMisstatementPushPayload` SHALL 识别行级 `misstatementType` /
    `misstatement_type`，行级缺失时回退顶层，两者皆缺时 SHALL 取 `'factual'`
    （既有 ~35 个推送点行为逐字节不变）。
3.3 `useA13MisstatementBridge` SHALL 以 `draft.misstatementType` 作为
    `createMisstatement` 的 `misstatement_type` 实参，SHALL NOT 再硬编码 `'factual'`。
3.4 WHEN 载荷携带非法 `misstatementType` 值 THEN 归一化 SHALL 回退 `'factual'` 而非
    透传非法值（避免后端 enum 报错把整批推送打掉）。
3.5 抽凭引擎 SHALL 在「错报推断与总体结论」区提供「推送推断错报至 A13」操作，
    仅当结论已确认（`conclusionConfirmed`）且 `projected > 0` 时可用。
3.6 该操作 SHALL 推送**一条** `misstatementType='projected'` 的错报，金额取 `projected`
    （不含高值层已知错报），描述 SHALL 内嵌抽样方法、样本量、抽样间隔、随机种子、批次号，
    并在 `known_high_value > 0` 时追加「另有高值层已知错报 X 元应按事实错报单独记入」。
3.7 WHEN 同一批次已推送过推断错报（`evaluation.a13_pushed_at` 非空） THEN 系统 SHALL
    二次确认后才允许重复推送，避免错报汇总重复计入。
3.8 推送成功后 SHALL 把 `a13_pushed_at` 写回该批次 `evaluation`（复用 R2 端点）。
3.9 `Misstatements.vue` 的新增/编辑错报类型下拉 SHALL 补齐「推断错报」选项
    （现仅有事实/判断两项，而 `typeLabel`/`typeTagType` 已支持 projected）。

### Requirement 4: legacy 抽样引擎下线与守卫扩面

**User Story:** 作为技术复核人，我需要平台只有一套抽样算法口径，避免后续接入者在两套
不同的金额口径与分层规则之间产生不可裁决的结论分歧。

#### Acceptance Criteria

4.1 系统 SHALL 删除 `POST /api/projects/{pid}/sampling/execute`
    （`sampling_enhanced.py`）与 `wp_functional_actions.py` 的 `sampling/execute` 分支。
4.2 系统 SHALL 删除 `backend/app/services/wp_sampling_engine.py`，包含其
    `fill_sampling_to_workpaper`（写 `parsed_data.action_data`，前端零消费）与
    `associate_ocr_evidence`。
4.3 `test_voucher_sampling_canonical_guard.py` SHALL 扩展为断言 `backend/app/**` 全仓
    对 `WpSamplingEngine` / `wp_sampling_engine` 零引用（不只 `voucher_sampling.py`）。
4.4 守卫 SHALL 断言 `backend/app/**` 无生产代码写入 `parsed_data.action_data`。
4.5 守卫 SHALL 含反向自检：注入一个引用 legacy 的替身源码时断言必红，证明该守卫非空转。
4.6 锁定 legacy 行为的测试文件（`test_wp_sampling_engine_seed.py`、
    `test_voucher_sampling_characterization.py` 的 legacy 段、`test_wp_functional_actions.py`
    的抽样段）SHALL 随实现一并删除；canonical 段断言 SHALL 保留且不得放宽。
4.7 删除后 `backend/tests` 全量 SHALL 无因本次改动新增的失败。

### Requirement 5: CAS 1314 抽样记录表定性与接入

**User Story:** 作为质量控制复核合伙人，我需要在项目层面一次性查到「本项目所有抽样是否
都有总体描述、样本量依据、评价结论」，以及「同一张凭证被哪些底稿抽过」，而不是逐张底稿
点开翻 JSON。

#### Acceptance Criteria

5.1 `sampling_records` SHALL 被定性为 canonical 抽样评价记录表并接入：回填成功时写入
    一条记录，字段来自本次抽样的方法学与统计快照。
5.2 `sampled_vouchers` SHALL 被定性为项目级已抽凭证登记表并接入：回填成功时按本次实际
    回填的凭证批量登记，与 `ledger_penetration.py` 的手工标记共存。
5.3 迁移 V139 SHALL 幂等（`IF NOT EXISTS`）为 `sampling_records` 增加
    `batch_id` / `sampling_method` / `random_seed` / `dataset_id` 列，为
    `sampled_vouchers` 增加 `batch_id` 列。
5.4 迁移 V139 SHALL 为 `sampled_vouchers` 建立幂等唯一索引
    `(project_id, year, voucher_no, working_paper_id, batch_id)`，防同批次重复登记。
5.5 WHEN 抽凭引擎请求排除已抽凭证且用户选择「跨底稿排除」 THEN 排除集合 SHALL 取自
    `sampled_vouchers`（项目级），默认仍为当前底稿级（零回归）。
5.6 系统 SHALL 提供 `GET /api/projects/{pid}/sampling/voucher-coverage` 返回项目级抽样
    登记概览：按底稿汇总的批次数/样本数，以及被 ≥2 个底稿抽取的凭证清单。
5.7 `sampling_config` SHALL 被定性为**软弃用**：源码标注 `.. deprecated::`、
    不新增写入点、保留既有端点不变；SHALL NOT 在本 spec 内删表或删端点（破坏性操作需
    用户单独授权）。
5.8 守卫 SHALL 断言 `sampling_config` 的写入点数量不增加，且 `sampling_records` /
    `sampled_vouchers` 的接入写入点确实存在（防「加了表不写」再次退化为孤儿）。

### Requirement 6: 宿主抽样方法学收口

**User Story:** 作为审计助理，我需要在底稿正文上就看到本表样本是怎么抽出来的，因为归档
和复核看的是底稿，不是后台日志。

#### Acceptance Criteria

6.1 系统 SHALL 提供共享件 `composables/shared/samplingFillTarget.ts`，导出方法学
    持久化键构造、方法学摘要文本构造，以及 `SampledVoucher` → 通用行的最小字段映射
    （凭证号/日期/借方/贷方/科目编码/摘要）。
6.2 系统 SHALL 提供只读展示组件 `WpSamplingMethodologyBar.vue`，渲染方法、抽样间隔、
    样本量、建议样本量、可容忍错报、随机种子、批次号、抽样框数据集版本。
6.3 全部引入 `GtVoucherSamplingEngine` 的宿主 SHALL 消费 `filled` 载荷中的
    `methodology` 并持久化到固定 item key。
6.4 全部引入 `GtVoucherSamplingEngine` 的宿主 SHALL 在抽凭区渲染
    `WpSamplingMethodologyBar`（有方法学数据时可见，无数据时隐藏）。
6.5 宿主的样本回填 SHALL 至少映射 6.1 的最小字段集，SHALL NOT 只保留摘要文本。
6.6 平台守卫 `samplingHostMethodologyCoverage.spec.ts` SHALL 扫描全部含
    `GtVoucherSamplingEngine` 的 `.vue`，对 6.3~6.5 逐条断言；薄壳委托
    （`v-bind="$props"`）SHALL 被识别为已满足。
6.7 守卫的 allowlist SHALL 要求每条写明理由，且条目数只许变短不许变长。
6.8 守卫 SHALL 含反向自检：构造一个丢弃 methodology 的替身宿主源码时断言必红。

### Requirement 8: 跨底稿重复抽凭的显式确认

**User Story:** 作为审计助理，当我抽到的凭证已经被本项目其它底稿抽查过时，我需要系统弹窗
告诉我是哪几张、被哪些底稿抽过，由我判断是保留（有意交叉复核）还是剔除，而不是系统替我
静默决定。

**背景**：R5.5 的 `exclude_scope` 是二元开关 —— 开则静默剔除、关则完全不提示。两者都把
本该由审计师做的判断交给了配置项：重复抽同一张凭证有时是**有意的**（不同循环从不同认定
角度检查同一笔交易），有时是**样本浪费**（覆盖率虚高）。这个判断必须显式留痕。

#### Acceptance Criteria

8.1 WHEN `voucher-extract` 抽样完成 THEN 响应 SHALL 包含
    `cross_workpaper_duplicates`：本次样本中已被**其它底稿**抽取登记过的凭证清单，
    每项含 `voucher_no`、`wp_codes`（抽过它的底稿编码，去重排序）、`batch_count`。
8.2 该检测 SHALL 排除当前底稿自身的登记记录（同一底稿内的重复由既有
    `exclude_extracted` 处理，不属跨底稿议题）。
8.3 该检测 SHALL 只统计抽凭引擎的登记行（`batch_id IS NOT NULL`），
    SHALL NOT 把 `ledger_penetration` 穿透页的手工标记当作「已执行抽凭程序」。
8.4 WHEN `cross_workpaper_duplicates` 非空 THEN 前端 SHALL 在预览弹窗打开**之前**
    弹出确认框，列出凭证号与抽过它的底稿编码（超过 10 条时截断显示并给出总数）。
8.5 确认框 SHALL 提供三个出口：**保留全部**（有意交叉复核）／**剔除重复项**
    （从本次样本中移除）／**取消**（放弃本次抽样结果）。
8.6 WHEN 用户选择「剔除重复项」THEN 系统 SHALL 从 `sampledVouchers` 移除这些凭证并
    按剩余样本重算覆盖率展示，且 SHALL 提示实际样本量已减少。
8.7 用户的选择 SHALL 随回填留痕落库：`extraction_criteria.duplicate_decision`
    取值 `keep_all | removed | none`，并记录涉及的凭证号清单。
8.8 WHEN `exclude_scope === 'project'`（用户已选择项目级排除） THEN 重复项在抽样阶段
    已被排除，`cross_workpaper_duplicates` 自然为空，SHALL NOT 再弹框。
8.9 跨底稿检测查询失败 THEN SHALL 降级为空清单并记 WARNING，SHALL NOT 阻断抽样
    （检测是增强，不是抽样的前置条件）。

### Requirement 7: 零回归与守卫（横切）

**User Story:** 作为技术复核人，我需要这轮改造不引入任何既有行为变化，并且每条新增合规
能力都有能真实打红的守卫，而不是靠「测试全绿」这种可能空转的信号。

#### Acceptance Criteria

7.1 每波结束 SHALL 跑既有测试全绿；任一断言不符即停在该步，SHALL NOT 以放宽断言 /
    换参数 / 跳过用例的方式绕过。
7.2 本 spec 的所有新增后端字段 SHALL 为 additive：既有调用方不传新字段时行为
    逐字节等价（`dataset_id` / `evaluation` / `misstatementType` 均有缺省语义）。
7.3 R1 / R2 的守卫 SHALL 在真实库上验证，而非仅用替身：`dataset_id` 取值须来自
    `ledger_datasets` 实际 active 记录。
7.4 R3 的 `misstatement_type` 通路 SHALL 有一条端到端断言证明 `projected` 真能落库
    （现状全库仅 factual，改造后须能查到 projected 行）。
7.5 CI SHALL 新增 job 挂载本 spec 的后端与前端守卫。
7.6 会话结束前 SHALL 清理本 spec 产生的 `tmp_*` 诊断产物。
