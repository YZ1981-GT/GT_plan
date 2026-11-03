# 需求文档：S5　取数结果的来源信封

> **本 spec 由 `formula-hub-integrity-closure` 按需求 17.5 创建（design §8.1 的 S 系列交接）。**
> 本文在 2026-10-31 设计复核后收窄并补齐验收边界：本 spec 负责报表、附注和公式推送三个已经具备运行入口的域；底稿公式值的信封延后到 S1 完成有效定义统一后处理，不把未统一的底稿来源误记成可审计事实。

## 1. 负责范围

### R1：最终值来源信封

对本 spec 范围内的自动计算结果，持久化并可读取以下信息：

- **定义身份**：`definition_version`、`definition_hash`、`definition_layer`；
- **计算运行**：`run_id`、`computed_at`、`computed_by`、`calc_version`；
- **实际输入**：有界展示输入 `inputs`、完整输入数量 `input_count`、是否截断 `inputs_truncated`、顺序无关的 `input_digest`；
- **值语义**：`value_slot`（例如报表 `current` / `prior`）、`value_state`（例如 `auto` / `manual` / `locked` / `kept`）和 `calculation_applied`，避免把公式尝试结果误报成最终值来源。

本 spec 具体覆盖：

1. **报表域**：`financial_report` 的本期最终金额。全量生成、affected 重算、stale 重算三条写入路径使用同一运行上下文；失败行保留旧金额和旧信封。
2. **附注域**：附注表格中实际由自动公式写入的单元格；人工、锁定、底稿投影保留值和公式失败不被错误标成公式结果。
3. **公式推送域**：公式推送目标的公式求值结果和最终目标状态。公式没有实际写入目标时，信封必须明确标记 `calculation_applied=false`，不能把公式结果当成当前值来源。

### R2：附注溯源改读权威注册表

- `report_trace_service.trace_section` 不再读取不存在的 `note_wp_mapping` 表；
- 章节到 `wp_code` 使用 `note_workpaper_sync_registry.json` 的统一访问器；
- 项目 `wizard_state.note_wp_mapping` 自定义映射优先；
- 模板类型、一个章节对应多个底稿、复数章节和注册表缺失均按明确契约处理；
- `note_account_mappings` 只按其真实字段提供报表行次 / 章节 / 底稿关系，不凭字段名推导不存在的 `account_codes`；
- UnifiedLineage 的附注子源在映射成功时不再因为旧表缺失而恒为 partial；映射缺失、注册表不可用和数据库异常仍须区分并留痕。

### R3：最终值展示面接入来源信封

前序 spec 已完成 `components/formula` 零挂载组件清零，本 spec 不重复裁决零挂载组件。本 spec 的 R3 是：

- 报表当前金额最终展示面可查看来源信封；
- 附注自动公式单元格可查看来源信封；
- 展示层必须保留现有校验提示、批注、编辑和已有底稿 / 试算表穿透能力，不通过嵌套 tooltip 破坏触发元素；
- 当前值和上期值不得复用不匹配的信封。若本期不扩展上期信封，界面必须明确只对本期值显示本 spec 的来源信封；
- 空信封、历史存量行、人工值、锁定值和公式失败值要显示准确的中文状态，而不是显示为“公式已计算”。

## 2. 依赖与先后

- 依赖 `formula-hub-integrity-closure` 的 ADR-FHIC-04（计算版本）与 ADR-FHIC-16（溯源子源隔离）已落地；
- 报表、附注、推送三个域可以在本 spec 内按任务依赖实施；
- **底稿域信封不是本 spec 的实施前置，也不在本 spec 内完成**。它依赖 `formula-grammar-resolver-unification`（S1）完成底稿公式全轨读取有效定义后，再由后续任务接入同一信封契约；S1 的底稿有效定义任务不反向等待本 spec 全部完成；
- 附注执行器的已有入口依赖 S2 的执行器改造部分，具体接线在任务中标明；
- 任何新 API、迁移和 ORM 字段必须同时满足迁移、模型、service / router 三层一致。

## 3. 触发条件

满足以下任一条件时实施本 spec：

- 审计留痕要求用户能够回答“这个值按哪版定义、哪次运行、哪些输入计算”；
- S3 的 stale 判据需要稳定的定义 hash 或输入摘要；
- 报表 / 附注 / 公式推送最终值页面需要显示可审阅的来源信封。

触发条件是启动依据，不替代本 spec 的验收标准。

## 4. 承接自 `formula-hub-integrity-closure` 的具体欠账

母 spec 当前的 `calc_version` 只能判断计算语义是否当前，不能记录具体定义版本、定义层级、运行身份和实际输入摘要。本 spec 补齐这些信息，并把“公式求值结果”和“最终值来源”区分开。

## 5. 不属于本 spec

- `formula-hub-integrity-closure` 已交付的部分不回填改写，历史档案保持 append-only；
- 底稿自身公式值的 provenance 持久化与底稿公式有效定义统一，延后到 S1 完成后另行接入；
- 存量报表行不批量回填 provenance，重新生成时自然补齐；
- 本 spec 不执行共享库迁移、推送、存量归属行升级、真实项目报表重算、门禁切 enforce、D1~D15 默认值确认等用户决策项；
- 不把当前已有的 `GtFormulaSourceTooltip` 直接视为完整来源信封组件，前端接入必须先满足 R3 的值语义和现有提示兼容性。

## 6. 设计阶段已确认事项

- 现状复核见 design §1；`components/formula` 零挂载组件已清零，R3 改为最终值展示面接入；
- 报表 provenance 只在本 spec 覆盖 `current` 值；上期值若要接入，必须另有 `value_slot` 和独立来源，不得复用本期信封；
- 每个域必须提供定义身份解析器，不能从丢失来源层的 ORM 复制对象直接推导 `definition_version` / `definition_layer`；
- 输入摘要必须保存完整 digest 所需的全量计数，同时只保留有界展示列表；
- 底稿域延后到 S1 后，不影响本 spec 的报表、附注和公式推送交付。

## 7. 待用户拍板

| # | 事项 | 当前建议 |
|---|---|---|
| D1 | 底稿域信封 | 放到 S1 完成后再做，本 spec 不做 |
| D2 | 存量报表行没有信封 | 不回填，重新生成时补齐 |
| D3 | 输入列表保存上限 | 每个最终值最多保留 200 条展示输入；`input_digest` 按全量输入计算，并保存 `input_count` 与 `inputs_truncated` |
| D4 | 报表上期金额 | 本 spec 只接本期值；上期值暂不显示本信封，除非后续补 `value_slot=prior` 的独立来源 |
| D5 | 附注来源展示组件 | 复用现有附注来源读取 / 弹窗链路并扩展响应，避免在校验提示和批注提示外再嵌套通用 tooltip；报表可单独扩展来源浮层 |

## 8. 设计复核后的强制语义（2026-10-31）

以下约束是 R1~R3 的组成部分，优先于本文中任何可能暗示“单一信封同时代表本次计算与当前最终值”的旧表述。

### 8.1 计算尝试与当前最终值分离

- 一个公式计算尝试必须持久化其 `calculated_value`、`calculation_status`、定义身份、运行身份和输入摘要；
- 当前最终值必须独立表达 `value_state`、实际采用的 `applied_attempt` 与最近一次 `last_calculation`；
- 当 manual、locked、kept 或 pending_confirm 目标未采用新计算结果时，不得用未采用的尝试覆盖当前最终值的来源；同时不得丢失该次计算尝试；
- `calculation_applied` 表示 `last_calculation` 是否成为当前最终值的实际来源，而不是“本次公式是否成功求值”。

### 8.2 可重建的定义与运行身份

- 每个计算尝试除 `definition_version`、`definition_hash`、`definition_layer` 外，必须持久化稳定的 `definition_ref`；
- `definition_ref` 必须能定位定义种类、来源记录或稳定目录项。若定义记录可被覆盖或删除，必须同时保存不可变的执行字段快照，其 canonical digest 必须等于 `definition_hash`；
- 每个 `run_id` 必须能解析到持久化、可查询的运行记录。报表复用 `report_generation_run`，公式推送复用 `formula_push_run`；附注必须复用已有可查询运行记录或新增等价记录，不得只生成不可追溯的 UUID。

### 8.3 输入展示与权限

- `input_digest` 和 `input_count` 以完整输入集计算；展示输入最多保留 D3 规定的 200 条；
- 对合并项目或跨项目输入，持久化及读取都不得绕过现有项目级可见性。读取 API 必须按**当前请求人**重新过滤或脱敏原始值、来源引用和主体标签，并显式返回 `inputs_redacted`；
- 无权读取的输入不得因系统任务拥有更高权限而以原始值形式出现在报表、附注或推送来源展示中。

### 8.4 并发、失败与跨 spec 交接

- 报表、附注、推送的最终来源更新必须具备等价的串行、CAS 或 fenced-run 机制。较早运行不得在较晚运行成功后覆盖其最终来源；
- 每个域必须明确部分失败、整体回滚、保存点回滚和目标未写入时的运行记录与来源更新规则；
- S5 Task 1 的公共契约先于 S3 使用 hash / digest 的接线；附注来源信封须在 S2 执行器分类回写完成、并与 S3 stale 状态机约定写入边界后实施；
- 公式推送来源信封不依赖 S2，可与报表域在 Task 1 完成后独立推进。
