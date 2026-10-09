# 任务：试算平衡表调整列取数收口

> 标 `[x]` 必须有**实际代码 + 测试通过**证据。外部依赖/待环境如实标 `[ ]*` 并用
> "代码已改但未实测"措辞。禁假绿。

## Phase 0 — 口径收敛（需求 1，独立可交付，修错误数字）

- [x] 0.1 建立基线：记录 `summary_with_adjustments` 当前对真库项目
      `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`/2025 的完整输出（78 行利润表 + 129 行资产负债表），
      存 `evidence/phase0-baseline.json`。**这是唯一能证明"数字变化是修正而非回归"的依据**
- [x] 0.2 先跑既有测试全量，记录**预存红项**清单到 `evidence/phase0-pre-existing-red.txt`。
      用 `git stash` 验证这些红与本轮无关（铁律㉔归因纪律）
- [x] 0.3 在 `adjustment_amount_source` 新增 `adj_net_batch(db, project_id, year,
      account_codes, *, include_statuses=None, exclude_origins=frozenset())`，
      返回 `dict[str, dict[str, Decimal]]`（`code → {'aje_net','rje_net'}`）。
      实现**必须**复用既有 `adj_net` 的查询构造（ADR-ADJ-001 走 `adjustment_entries`
      + JOIN 主表），禁另写一份聚合 SQL
- [x] 0.4 单测 `adj_net_batch`：P3（draft 不计入）+ P4（origin 过滤）+ 双向变异
      （同一条改 approved 后必须计入；exclude_origins 传空集后 workpaper 必须计入）
- [x] 0.5 单测 `adj_net_batch` 与逐条 `adj_net` 的**等价性**：同一批 account_codes，
      批量结果 == 逐条调用结果（防批量路径与单点路径漂移——consol 封板①抓到过同型 bug）
- [x] 0.6 改 `trial_balance_service.summary_with_adjustments`：删掉 L663-691 自写的
      `adj_q` 聚合，改委托 `adj_net_batch`，传 `include_statuses={approved}` +
      `exclude_origins={workpaper}`
- [x] 0.7 改 `summary_with_adjustments` 的净额→借贷拆分：`adj_net` 返净额，
      按符号进借/贷列。**先验 P1**（净额拆分 ≡ 现有 `aje_dr - aje_cr`），
      若不等价则本任务停下来报告差异，不得擅自改口径
- [x] 0.8 同文件 `_summary_by_mapping`（L899-933，第二处自写聚合）同样收敛。
      🔴 触类旁通：本文件内 `Adjustment.__table__` 的 `account_code`/`debit_amount`/
      `credit_amount` 引用数最终必须为 **0**，grep 验证
- [x] 0.9 P2 守卫：`summary_with_adjustments` 调整合计 == `adj_net_batch` 同参数值。
      必须**调同一函数**比对
- [x] 0.10 跑 0.1 的基线对比，产出 `evidence/phase0-diff.md`，逐行说明每处数字变化的原因
      （预期：含 draft 的项目调整列下降；截图里 IS-001 的 10,000 应消失，因为 1122 不在 6001~6099）
- [x] 0.11 真库实测：重跑真库项目，确认唯一 approved 的 `1122 借方 10,000` 正确落到
      资产负债表应收账款行而非利润表营业收入行

## Phase 1 — 统一内核（需求 2+3）

- [x] 1.1 `FormulaContext` 新增 `adj_data: dict[str, dict[str, Decimal]]`
      （`field(default_factory=dict)`，与既有 5 个数据源字段同构）
- [x] 1.2 实现 `_handle_adj(args, ctx, trace)`：纯同步查 `ctx.adj_data`；
      `adj_type` 归一**复用** `adjustment_amount_source.normalize_adj_type`，禁另写
- [x] 1.3 `_REGISTRY.register("ADJ", _handle_adj, arity=2, ...)`，category="取数"
- [x] 1.4 P6 守卫：`_handle_adj` 非 coroutine + 源码内无 `await` + 无 DB import
- [x] 1.5 验证 `formula_state` 白名单自动生效（它派生于 `_REGISTRY`）：
      `validate_formula("ADJ('6001','aje_net')")` 返 `[]`，且 `_classify` 不判 BLOCKED。
      **双向变异**：`NOSUCHFUNC()` 仍被拒
- [x] 1.6 🔴 删除 `test_k1_formula_presets._KNOWN_ADJ_EXEMPT` 豁免，改正向断言（P9）。
      删前后各跑一次，确认不是靠豁免掩盖问题
- [x] 1.7 `formula_grammar` 加 `ADJ_PATTERN`（现有 9 个 pattern 的单一真源，
      保持风格一致）。⚠️ 加了 pattern 后必须检查 `report_engine` 的预替换循环
      **不要**把 ADJ 加进 `PREV/NOTE/WP/AUX` 那个"一律替换成 0"的列表
- [x] 1.8 三个 L2 填充 `adj_data`：`trial_balance_service`（P5 的一侧）、
      `report_engine`、`adjudication_writeback`。统一经 `adj_net_batch`
- [x] 1.9 `from_simple_map` 补 `AJE调整`/`RJE调整` 键——⚠️ 需求 3.4：既有 3 键的值与语义
      **不得变**，只增不改。加参数 `adj_map: dict | None = None`，缺省时不产这两键
      （保持既有调用方零回归）
- [x] 1.10 P5 守卫：同一公式跨域等值（报表路径 vs 试算平衡表路径）。
      覆盖 `TB(code,'AJE调整')` 与 `ADJ(code,'aje_net')` 两种写法
- [x] 1.11 需求 3.3：持久化列与实时值不一致时的可观测信号。
      实现为 health/诊断端点或 service 层 warning，**不做**自动 recalc。
      真库现状（持久化全 0、实时非 0）必须能被这个信号发现
- [x] 1.12 文档：在 `adjustment_amount_source` 文件头的口径表补第 4 行
      （试算平衡表调整列），并说明 `TB(code,'AJE调整')`（取持久化快照）与
      `ADJ(code,'aje_net')`（取实时汇总）的语义差异

## Phase 2 — 数据模型（需求 4）

- [x] 2.1 现算确认最高迁移版本（**禁写死**，必须重新扫 `backend/migrations/V*.sql`
      取最大值 +1）。
      🔴 **实测印证**：spec 撰写时现算 V165（故预期 V166），但 Phase 0 收尾时
      并发会话已加入 `V166__sampled_vouchers_date_and_wp_scope.sql` ⇒ **V166 已被占用**。
      本条的「禁写死」不是形式要求 —— 照 spec 文字写死会直接撞号，
      且 `scan_migrations` 的同号检测会抛 `RuntimeError`。
- [x] 2.2 写 `V{n}__report_config_adjustment_formula.sql` + 配对 `R{n}__*.sql`：
      `ALTER TABLE report_config ADD COLUMN IF NOT EXISTS aje_formula TEXT`，
      同样加 `rje_formula`。⚠️ 必须 `IF NOT EXISTS`（D6 MigrationRunner 约定）
- [x] 2.3 P8 守卫：迁移连跑两次不报错；`scan_migrations` 无同号冲突
      （V040 冲突后已加同号检测，确认新号不撞）
- [x] 2.4 ORM `ReportConfig` 加 `aje_formula` / `rje_formula` 的 `Mapped[str | None]`
- [x] 2.5 三层一致校验（需求 4.5）：迁移 + ORM + service 读写全部到位。
      写一个断言"ORM 列集 ⊆ 真实 PG 列集"的守卫（平台已有 drift detector，接进去）
- [x] 2.6 `summary_with_adjustments` 读 `aje_formula`/`rje_formula`：
      有值走公式求值，无值**完全退回**现有反解科目码路径
- [x] 2.7 P7 守卫：761 条既有公式（现算，禁写死）求值结果前后逐条相等。
      🔴 这是 Phase 2 最重要的守卫——它证明"加字段不影响既有配置"
- [x] 2.8 需求 4.4：合计行纯行间引用（如 `ROW('IS-019')-ROW('IS-020')`）配上调整列公式后
      能取到数。先现算确认真库有多少这类行（`formula` 含 `ROW(` 但不含 `TB(`/`SUM_TB(`）
- [x] 2.9 报表配置读写端点（`P_rc.list` 等）支持新字段的读与写
- [x] 2.10 `report_config_baseline`（主模板回填通道）的 diff/apply 逻辑覆盖新字段
      —— 否则新字段永远不会随主模板更新传播（D spec 的 stale 机制）

## Phase 3 — 前端（需求 5）

- [x] 3.1 `FormulaManagerDialog` 的行模型从单 `formula` 扩成含 `aje_formula`/`rje_formula`。
      🔴 先现算 `currentRows` 的消费点数量（编辑/保存/导入/导出/应用自动运算至少 5 处，
      本轮已知 `activeReportType` 收口后有 9 处 report_ 相关调用点）
- [x] 3.2 右侧表格加调整列公式列；未配置时显式区分「未配置（走默认推导）」vs「配置为空」（需求 5.2）
- [x] 3.3 修「N 个公式 / 健康度 X%」的分母口径说明（需求 5.3）：
      界面明示是"未审数列"还是"全部列"。现状 `37 个公式 / 51%` 只算未审数列却未说明
- [x] 3.4 公式编辑弹窗支持编辑调整列公式，且函数选择器能列出 `ADJ`
      （它在 Phase 1 已注册进 `_REGISTRY`，前端若有独立函数清单需同步——
      先 grep 确认前端是否有第二份函数清单）
- [x] 3.5 前端类型检查：用单区域 tsconfig（先例 `tsconfig._g-single-region.json`）。
      🔴 **必配变异证明**（注入 `number = string` 应报 TS2322）——本仓库全量 `vue-tsc`
      在 4GB/8GB 堆均 OOM，stdout 的 `error TS` 计数为 0 **不等于**通过（铁律㉔）
- [x]* 3.6* Playwright 实测：试算平衡表利润表 tab → 公式管理 → 能看到并编辑调整列公式。（2026-10-06 验证通过：试算表 174 科目加载 + 公式管理中心打开 + AJE/RJE 列头可见 + 编辑对话框含 TB/ADJ 等函数按钮 + 保存按钮可用）
      覆盖 4 个 tab（资产负债表/利润表/现金流量表/现金流量附表）+ 科目明细回归 + 报表域回归

## 收尾

- [x] 4.1 清理本轮所有 `_` 前缀一次性探针（`backend/scripts/analyze/_*`）
- [x] 4.2 更新 `memory.md`：勘误最高迁移版本（V044 → 实际值），
      并记录「口径第四处已收敛」与「`TB(code,'AJE调整')` vs `ADJ(code,'aje_net')` 语义差异」
- [x] 4.3 登记 `.kiro/specs/INDEX.md`。⚠️ 该文件是**纯 CRLF**，插入须
      `read_bytes().decode('utf-8')` + `write_bytes()`；表格第三格内禁裸 pipe；
      校验"每行恰 4 个未转义 pipe"
- [x] 4.4 判据引用闭合性检查（铁律⑳）：脚本化验证每条需求判据与每个 Property
      至少被某个任务引用一次。**光数任务编号连续不算**
- [x] 4.5 PR 说明必须写明：**Phase 0 会改变现有显示数字**（含 draft 分录的项目调整列下降），
      附 `evidence/phase0-diff.md` 逐行说明

## 任务与判据对照（闭合性自检）

| 需求判据 | 承接任务 |
|---|---|
| 1.1 委托 adj_net / 遗留列引用为 0 | 0.3, 0.6, 0.8 |
| 1.2 draft 不计入 | 0.4（P3） |
| 1.3 workpaper 不计入 | 0.4（P4） |
| 1.4 调同一函数比对 | 0.9（P2） |
| 1.5 独立最先交付 | Phase 0 整体 |
| 2.1 validate 返 [] | 1.5（P9 正向） |
| 2.2 L1 纯同步 | 1.4（P6） |
| 2.3 底稿域零变化 | 1.8, 1.12 |
| 2.4 复用 normalize_adj_type | 1.2 |
| 2.5 删豁免 | 1.6（P9） |
| 3.1 ctx 填调整键 | 1.1, 1.9 |
| 3.2 跨域等值 | 1.10（P5） |
| 3.3 不一致可观测 | 1.11 |
| 3.4 from_simple_map 只增不改 | 1.9 |
| 4.1 迁移版本+配对+IF NOT EXISTS | 2.1, 2.2, 2.3（P8） |
| 4.2 未配置时零回归 | 2.6, 2.7（P7） |
| 4.3 配置后以公式为准 | 2.6 |
| 4.4 合计行纯行间引用 | 2.8 |
| 4.5 三层一致 | 2.5 |
| 5.1 展示调整列 | 3.1, 3.2 |
| 5.2 区分未配置/配置为空 | 3.2 |
| 5.3 分母口径明示 | 3.3 |
| 5.4 禁百分比阈值 | 贯穿（各 Property 均为逐条断言，无阈值） |
| P1 净额拆借贷等价 | 0.7 |
| P8 迁移可重入 | 2.3 |

## 起点建议

Phase 0 的 **0.1 / 0.2** 必须最先做——没有基线就无法区分"修正"与"回归"，
而 Phase 0 一定会改变现有数字。
