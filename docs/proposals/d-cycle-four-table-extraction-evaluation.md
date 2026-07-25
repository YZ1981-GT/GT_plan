# D-cycle 四表库提取公式 —— 灰度评估 + 差异矩阵 + 推广参考

> spec: `.kiro/specs/d-cycle-four-table-extraction-formulas/`
> 交付：Wave 0-6（Task 1-7）完成；本文 = Wave 7（Task 8.1 灰度默认开启评估 + 8.2 差异矩阵/锚点-来源对照，供 E/F/G… 循环推广）。
> 更新：2026-07-25

## 一、两层架构回顾

从四表库（`trial_balance` / `tb_balance` / `tb_ledger` / `tb_aux_balance`）自动提取填充 D1-D7 底稿，分两层：

- **Tier B（批量预填，占大头）**：镜像 K/M/N 已证明的 `_build_adjudication_prefill` 范式（`d_cycle_extraction/prefill.py::build_d_adjudication_prefill`）——`get_active_filter`（数据集版本）+ `tb_balance` 叶子级 SUM（只取叶子防双算）+ 跳零/无名 + balance/occurrence 双模式。render 返回 `adjudication_prefill`，前端组件 seed（手工优先，锚点完全空才并入）。
- **Tier A（可编辑公式）**：可表达为单条 `TB('code','列')` 的**简单科目总额核对标量**注册为可编辑 `wp_formula`（预设库 `d_cycle_extraction_presets.json`，读时收敛 `presets.py::resolve_effective`），`target_cell` = checklist_responses item_id 锚点。公式管理面板（`FormulaStatusPanel.vue`）分层展示：Tier A 可编/恢复默认/禁用，Tier B 只读溯源。
- **口径统一**：Tier A 求值（`wp_formula_eval_service` 的 `_resolve_tb`/`_resolve_sum_tb`）与 Tier B 预填共用 `get_active_filter` —— 消除「面板值 ≠ render 填充值」漂移（Property 3）。
- **灰度开关** `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认 **False**）：关闭时 D1-D7 render 逐字节等价当前（Property 9 零回归）；Tier A/GET extraction 均不出现。

## 二、宁缺勿造（R3.4）—— 覆盖到底的诚实边界

**关键发现**：D1/D2/D3/D4/D5/D7 六张审定表都是**分类/明细行 SUMIF 派生**（按信用风险组合 / 性质+账龄 / 产品 / 类别），而 `trial_balance`/`tb_balance` 的科目**只有总额、无对应组合维度**（分类是审计判断或序时账明细维度，非科目结构）→ **无法把 TB 叶子干净映射到分类行**。故这六张审定表 render **不返回 `adjudication_prefill`**（不臆造分类未审数）。

仅 **D6 合同资产** 审定表一、原值（block1）是动态行且可从 `tb_balance` 1402 叶子期初/期末余额干净 seed —— 是唯一真正接入 Tier B `adjudication_prefill` 的循环。

> **诚实的部分覆盖优于臆造**：分类拆分/审计判断/说明**无法从四表库推导**，不生成提取。四表库真正可自动填的是：①科目/子目级未审数或发生额（Tier A 标量或 D6 原值 seed）；②明细表按客户/产品/月归集（Tier B 前端既有一键取数，非单条公式）。

## 三、差异矩阵（四表可填 vs 不可填 + 锚点-来源对照）

> 与 `backend/data/d_cycle_extraction/README.md` 同源；此处为推广速查。

| wp_code | 科目 | 类型 | 审定表 render 策略 | Tier A 可编辑公式（锚点 → 表达式） | Tier B 只读溯源（明细归集来源） |
|---|---|---|---|---|---|
| **D1** 应收票据 | 1121 | balance | 宁缺勿造（票据类型×原值/坏账/净值 SUMIF from D1-2） | `D1-adj-tb-amount` → `TB('1121','期末余额')` | D1-3 客户明细期后兑付 ← 序时账 1121 贷方 |
| **D2** 应收账款 | 1122 | balance | 宁缺勿造（信用风险组合 SUMIF from D2-2） | `D2-adj-tb-amount` → `TB('1122','期末余额')` | D2-2 明细 ← tb_aux_balance 1122 客户维度 + 序时账期后回款 |
| **D3** 预收账款 | 2203 | balance | 宁缺勿造（性质/账龄 SUMIF from D3-2） | `D3-adj-trial-balance-amount` → `TB('2203','期末余额')` | D3-2 明细 ← tb_aux_balance 2203 客户维度 |
| **D4** 营业收入 | 6001/6051 | **occurrence** | 宁缺勿造（产品/项目 SUMIF from D4-2/D4-3） | `D4-1-adj-tb-6001` → `TB('6001','审定数')`；`D4-1-adj-tb-6051` → `TB('6051','审定数')` | D4-2 主营明细 ← 序时账 6001 贷方按产品×月归集 |
| **D5** 应收款项融资 | 1124 | balance | 宁缺勿造（应收票据/应收账款 SUMIF from D5-2；OCI 减项 from D5-4） | `D5-1-tb-amount` → `TB('1124','期末余额')` | D5-2 明细 ← tb_aux_balance 1124 类别维度 + 序时账期后兑现 |
| **D6** 合同资产 | 1402 | balance | **Tier B seed**（block1 原值期初/期末 ← 1402 叶子余额）+ 宁缺勿造（坏账/净值） | `D6-1-tb-amount` → `TB('1402','期末余额')` | D6-2 明细 ← tb_aux_balance 1402 客户/合同维度 + 序时账 |
| **D7** 合同负债 | 2205 | balance | 宁缺勿造（性质/账龄 SUMIF from D7-2，同 D3） | `D7-1-adj-aging-trial-balance-currentAudited` → `TB('2205','期末余额')` | D7-2 明细 ← tb_aux_balance 2205 客户/合同维度 |

**明确不可填（全 D 循环通用）**：所有 AJE/RJE（审计判断）、reasonAnalysis/note/conclusion（文本）、computed 列（小计/合计/净值/差异）、审定表分类行未审（TB 无对应维度）、坏账/减值（来自 ECL 减值模型非 TB）。

> **收入类口径注**：`_COLUMN_MAP` 中「审定数」「期末余额」同映射 `trial_balance.audited_amount`；损益类 audited_amount 存审定发生额，故 D4 用「审定数」语义更清晰（余额类用「期末余额」）。评估器无独立 occurrence 列。

## 四、灰度默认开启评估（Task 8.1）

**当前默认 = False（关）**。开启（改 `settings.D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED = True`）前置条件：

1. **实例化项目 Playwright round-trip（Task 8.3\* 未做，需实例化 D-cycle 项目）**：验证打开 D6 → 审定表 block1 自动 seed「自动取数」标注；打开 D1-D7 → 公式管理列 Tier A 可编 / Tier B 只读；编辑表达式保存生效；手工覆盖后不被回写。
2. **性能**：`build_d_adjudication_prefill` 仅 D6 走一次 tb_balance 叶子聚合查询（单查询，get_active_filter 已缓存数据集版本）；GET extraction 读时收敛不逐条重求值（value=None，无 N+1）。开销可忽略。
3. **零回归保证已就位**：Property 9（灰度关逐字节等价）+ 契约守卫（Property 12，不新造四表读取 + active_filter 同口径）+ 158 d_cycle 测试全绿。

**建议**：可**按循环灰度**——先仅对 D6（唯一真 Tier B seed）默认开启验证 seed 体验，其余循环（宁缺勿造，开关开/关等价）随时可开无风险。全局默认开启待实例化项目 Playwright 验证 D6 seed + 公式面板交互后。

## 五、推广到 E/F/G… 循环的参考

同款两层可推广到其它科目专属组件循环。推广时**逐 sheet 从真实 composable 反查锚点**（禁臆造），判定每字段属：

- **Tier A 候选**：科目/子目级总额核对标量（TB↔审定核对行）→ 注册 `X-cycle_extraction_presets.json` + anchor registry，`TB('科目','列')` 单条公式。
- **Tier B 候选**：审定表动态原值行可从 `tb_balance` 叶子干净 seed（如 D6）→ render 接 `build_d_adjudication_prefill`（复用，不新造）；明细表按维度归集 ← tb_aux_balance/序时账（前端既有一键取数，只登记 Tier B 溯源）。
- **宁缺勿造**：分类/账龄/审计判断/说明 → 不生成，诚实登记 Tier B provenance 声明「不从四表库填 + 由何 SUMIF 派生」。

**铁律**：`get_active_filter` 唯一四表查询入口（禁裸 is_deleted）；锚点必 ∈ `is_known_anchor`；只读四表库、写落 checklist_responses/parsed_data（Property 12 契约守卫覆盖）。

---

## 六、P0-1/P0-2 增量上线评估（`d-cycle-tier-a-writeback-detail-seed`）

> spec: `.kiro/specs/d-cycle-tier-a-writeback-detail-seed/`（前置 spec 复盘 P0 增量）
> 交付：Wave 0-6（Task 1-6）+ Task 7.1 完成；仅 7.2\* Playwright 端到端需实例化 D-cycle 项目留待。
> 更新：2026-07-25

### 6.1 闭合的两个 P0 缺口

前置 spec 复盘实证「提取公式在公式管理可编辑但**编辑基本无效**」「四表库有的内容仍是**手工一键取数**而非自动填充」两个 P0 半成品缺口，本增量将其从半成品变为端到端可用：

- **P0-1：Tier A 可编辑公式真生效（三段闭环）**
  1. **保存跳过写错库 + 返回 evaluated_value（不做 DB 写回）**：`PUT /formulas` auto_calc 分支按 `is_known_anchor(base_wp_code, target_cell)` 路由——D-cycle 锚点（如 `D6-1-tb-amount`）+ 主开关开 → **跳过 `write_cell_to_parsed_data`**（写进 parsed_data 网格对 D-cycle 专属组件无意义、且误导后续读网格者），并在响应返回 `evaluated_value` 供前端即时本地显示；**不新增任何 checklist_responses/DB 写回**。普通网格 cell（非 D-cycle）沿用 `write_cell_to_parsed_data`，逐字节零回归。
  2. **GET /formulas 附 Tier A 求值 value**：`_build_extraction_block` 对每条 Tier A binding 经 `get_active_filter` 求值填 `value`（原本恒 None），公式管理面板「当前值」显示真实求值结果，审计师可核对；单条失败 value=None fail-open，Tier B value 仍 None。
  3. **render transient 公式驱动 TB 核对行 seed（主机制，D1-D7 全铺）**：D-cycle render 用 `resolve_effective` 的有效 Tier A 公式求值，**transient seed** TB 核对行锚点进 `responses_snapshot`（**不落库**，对齐 D6 Tier B `adjudication_prefill`），优先于硬编码 `project_context.tb_amount`。每次打开按当前有效公式重算，编辑公式即在下次 render 生效。DRY：D6 试点后提取共享助手 `app/services/d_cycle_extraction/tier_a_seed.py::seed_tier_a_reconciliation`，D1/D2/D3/D5/D7（单标量）+ D4（6001/6051 双标量）全复用。

- **P0-2：明细维度归集自动 seed（试点 D6-2）**：明细表 render 且主开关 ∧ 子开关 ∧ 明细行完全空时，调既有归集（tb_aux_balance 1402 客户/合同维度）**transient seed** 明细行进 render 返回（`detail_prefill`，**不落库**），复用既有后端函数不新造第 3 套四表库读取；手工优先（有任一行不 seed）+ fail-open 空 + 保留前端手动一键取数按钮。

### 6.2 灰度策略（主开关 + P0-2 子开关，可「发 P0-1、压 P0-2」）

- **主开关** `D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED`（默认 **False**，前置 spec 已有）门控 P0-1 全部新行为（保存跳过写错库 / GET value / render Tier A seed）。
- **子开关** `D_CYCLE_DETAIL_SEED_ENABLED`（默认 **False**，本增量新增）门控 P0-2 明细自动 seed，且**被主开关 AND**（主开关关则子开关无效）。
- 因此可**独立灰度、单独回退**：开主开关、压子开关 = 只发 P0-1（Tier A 真生效）而先压住 P0-2 明细自动 seed；P0-1 与 P0-2 代码路径独立，其一 fail-open 不牵连其二。

**建议上线序**：先开主开关按循环灰度 P0-1（D6 唯一真 Tier B seed，其余循环宁缺勿造开关等价无风险）→ 实例化项目 Playwright 验证 Tier A 公式编辑生效 + 面板 value 核对 → 再开子开关放 P0-2 D6-2 明细自动 seed → 逐循环增量铺明细。

### 6.3 零回归保证

- **双开关默认关逐字节等价**：任一开关关闭时，保存走旧 `write_cell_to_parsed_data`、GET 无 `extraction` 字段、render 无 Tier A seed / 无 detail seed，全部逐字节等价前置 spec 状态（Property 10）。
- **契约守卫 G6/G7/G8 全绿**：G6（D-cycle 锚点 auto_calc 保存跳过 parsed_data 且不做 DB 写回、返回 evaluated_value）/ G7（明细归集复用既有函数不新造四表读取）/ G8（GET value·render seed 同经 `get_active_filter`）。
- **17 条 Property 1-13 PBT**：手工优先、写对存储（checklist_responses vs parsed_data）、口径统一、fail-open、复用不新造、独立可回退、seed 全程 transient 不落库、四表库只读 + logic_check 不改值 等不变量全覆盖。
- **共享 `wp_formula` 端点对非 D-cycle 底稿零回归**：现有 parsed_data 网格写回行为对所有底稿类型逐字节不变，D-cycle 锚点 checklist 通道为新增附加分支（Property 2）。
- **测试**：`tests/d_cycle_extraction/` **332 passed** + 前端 `FormulaStatusPanel` Vite transform 200 + get_diagnostics 全清。

### 6.4 seed 全程 transient 不落库的决策理由（决策 A）

本增量**放弃**「保存时把求值结果 DB 写回 checklist_responses」的初版思路，改由 render transient seed 作「编辑即生效」唯一权威。理由：

1. **避免来源混淆与冻结**：持久化的是「公式派生值」，落进 checklist_responses 后与「真人工值」无法区分 → 决策的手工优先会把它当人工值 → TB 变了也不刷新（冻结）。transient seed 每次打开按当前有效公式重算，无冻结。
2. **对齐 D6 Tier B `adjudication_prefill`**：从不持久化，手工优先只挡真人工编辑，语义一致。
3. **对共享端点侵入更小**：只条件跳过一处 parsed_data 写，不新增任何 DB 写路径。
4. **保存后即时显示**：由 PUT 响应返回的 `evaluated_value` 供前端本地更新核对行，无需 DB 写回 / 无需刷新。

**写对字段**：render transient seed 写入前端 composable 实际读取的 `responses_snapshot` 字段（`remark` 或 `conclusion`，Wave 0 逐锚点从 composable 核实并登记），防 L1 式错列 round-trip 断裂。

### 6.5 后续推广建议

- **P0-2 明细自动 seed 逐循环增量落地**：本增量仅试点 **D6-2**（D6 已是 Tier B 主试点）。其余循环明细表（D2-2/D3-2/D4-2/D5-2/D7-2/D1-3）可复用同款 render transient `detail_prefill` seed——各自复用既有一键取数归集（tb_aux_balance/序时账 resolver），单循环可回退，受子开关统一门控。推广时逐明细表核实归集是否为可复用后端函数（若仅在 `/import-aux-balance` 等 HTTP handler 内则先抽纯函数，不改原端点行为）。
- **E/F/G… 循环推广**：Tier A 真生效三段闭环（保存跳过写错库 + GET value + render transient seed）与 P0-2 明细 seed 机制通用，随第五节两层架构一并推广；锚点逐 sheet 从真实 composable 反查 + `is_known_anchor` 校验，禁臆造。

### 6.6 诚实状态

- **未 commit**：本增量全部改动（含 P0-1 三段 + P0-2 D6-2 明细 seed + 契约守卫 + PBT + 评估文档）尚未提交。
- **未 Playwright（Task 7.2\* 留待）**：端到端浏览器 round-trip（编辑 Tier A 公式保存 → 底稿锚点变化；打开 D6-2 空明细 → 自动 seed；手工覆盖后重开不被回写）需实例化 D-cycle 项目 + 灰度开关开。本增量正确性由 fake-session 集成测试 + 17 条 Property PBT + 契约守卫覆盖，等效验证由前置 spec 的 `scripts/verify_d_cycle_extraction_live.py`（进程内开灰度 + 真实 DB 验证）承担。


---

## 七、审定表 TB 核对科目应参照报表规则映射（report_config）而非硬编码前缀

> 背景：E1 货币资金审定表「试算平衡表数」核对最初硬编码 `1001%/1002%/1012%` 前缀求和 `trial_balance`。
> 平台已有权威的「报表科目 ↔ 具体科目编号」规则映射（`report_config.formula`，项目级可覆盖），审定表 TB 取数应参照它。
> 更新：2026-07-25

### 7.1 规则映射是什么

`report_config` 表每个报表行（`row_code`，如货币资金 `BS-002`）带 `formula`，即该报表行的取数规则：

```
BS-002 货币资金  formula = "TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')"
```

- **项目级可覆盖**：`applicable_standard = 'project:{id}'` 优先于标准级（`listed_standalone` / `soe_consolidated` 等）。企业若自定义货币资金口径（如剔除某受限账户 `1012.09`、并入 `1013`），改的是这里，报表生成与审定表核对应共用同一规则，避免漂移。
- **单一真源**：报表生成（`report_engine`）本就按此 formula 取数；审定表核对若另行硬编码前缀，与报表口径分裂。

### 7.2 落地：可复用解析器 + E1 试点

- **`backend/app/services/report_account_mapping.py`（新增，单一真源，可复用）**：
  - `resolve_report_line_account_codes(db, project_id, row_code, *, fallback)` —— 项目级 → 标准级解析 `report_config.formula`，提取 `TB()`/`SUM_TB()` 科目编号；**无配置回退 `fallback`（零回归）**，异常一律回退不阻断渲染。
  - `build_trial_balance_code_filter(codes)` —— 按科目编号列表构建参数化 SQL 过滤（单码 `LIKE '1001%'`、区间 `BETWEEN`）。
  - 单测 `tests/services/test_report_account_mapping.py`（9 passed）。
- **E1 render 策略试点**（`_e1_monetary_fund.py`）：「试算平衡表数」的科目集从硬编码 `1001/1002/1012` 改为 `resolve_report_line_account_codes(db, project_id, "BS-002", fallback=["1001","1002","1012"])`，并输出 `project_context.tb_source_codes` 供前端/追溯展示规则映射来源。live 实测：`tb_amount=9,182,572.99`、`tb_source_codes=["1001","1002","1012"]`（与硬编码等值，但现由规则映射驱动，差异仍为 0）。

### 7.3 为何这是正确的审计行为

若某项目规则映射把货币资金定义为 `1001/1002/1012/1013`，而审定表明细（四表种子）只覆盖 `1001/1002/1012`：
- 「试算平衡表数」= 规则映射全集（含 1013）；
- 「审定合计」= 明细汇总（缺 1013）；
- → **差异 = 1013 金额**，正确暴露「明细漏了报表口径中的一个科目」，而非硬编码掩盖。

### 7.4 推广建议（各审定表 X-1）

- 每张审定表 X-1 对应一个报表行 `row_code`（E1→BS-002 货币资金 / K9→管理费用 IS 行 / …）。TB 核对科目集统一走 `resolve_report_line_account_codes(db, project_id, <row_code>, fallback=<现硬编码前缀>)`，`fallback` = 各自现有硬编码（保证零回归）。
- 与第五节四表提取（Tier A/B）互补：**Tier A 的 `TB('code','列')` 锚点公式本就是规则映射的子集**——后续可让 Tier A 预设的科目也从 `report_config` 反查生成，进一步收敛「科目编号」这一真源。
- 铁律：`get_active_filter` 唯一四表查询入口；规则映射解析失败一律 `fallback` 不阻断；wp→row_code 映射需逐科目核实（如 E1=BS-002），禁臆造。

### 7.5 诚实状态

- **已完成**：E1 试点（rule-driven TB 核对 + `tb_source_codes` 追溯）+ 可复用解析器 + 9 单测 + live render-config 验证（差异 0 不变）。
- **未 commit**：本节改动（`report_account_mapping.py` + `_e1_monetary_fund.py` + 单测 + 本文）尚未提交。
- **未推广**：其余审定表 X-1 仍硬编码各自前缀；按 7.4 逐循环接入（单文件、附加式、`fallback` 零回归），跨循环批量属独立任务。
