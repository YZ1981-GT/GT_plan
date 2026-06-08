# 账表符号约定统一 — 设计文档

## 概述

本设计将四表（tb_balance/tb_aux_balance/tb_ledger/tb_aux_ledger）入库符号约定从 `v1_net_debit_positive`（借正贷负）切换为 `v2_category_natural_positive`（按科目类别存自然正数），并打通 tb_* → trial_balance → 报表全链路的符号一致性，提供存量数据迁移与新旧约定过渡期语义。

设计目标是消除"入库层借正贷负"与"下游期望类别正数"两层约定打架的根因，使负债/权益/收入科目在源头即以正数列示，下游试算表、底稿、报表无需各自临时判方向。

## 现状确认（codegraph 实证，设计据此展开）

### 发现 1：入库层 converter 用 `借-贷` 净额（需求 5 改造点）

`ledger_import/converter.py::convert_balance_rows`：
- `opening_balance = (od or 0) - (oc or 0)`，`closing_balance = (cd or 0) - (cc or 0)`
- 净额+方向模式走 `_resolve_direction(dir, bal)`
- 结果：负债贷方余额存为负数（v1 约定）

### 发现 2：trial_balance 生成层存在"硬编码旧约定 + 二次翻转"（需求 9 关键风险点，已实证）

`trial_balance_service.py`：
- `recalc_unadjusted`（L189-212）：损益类硬编码"收入类取 `-total_cr` 存负数、费用类取 `total_dr` 存正数"，靠编码 `5xxx/6xxx` 前缀判断 → **依赖旧约定的符号假设**。
- `get_summary_with_adjustments`（L527-536）：有补偿逻辑"贷方方向科目（`code[0] in ('2','3','4')` 或特定 5/6 编码）取反为正数"，且 `if is_credit_dir and amount < 0: amount = -amount` → **这正是中间环节的二次翻转**，把 tb 的负数又翻回正数。
- `recalc_audited`：`audited = unadjusted + rje + aje`，符号取决于 unadjusted 与调整列口径一致性。

**结论**：若仅改入库层存正数而不改 trial_balance 生成层，`recalc_unadjusted` 仍会把已是正数的负债当负数处理、`get_summary` 的"取反"补偿会错误翻转，导致符号紊乱。trial_balance 生成层**必须同步改造**，去掉基于旧约定的硬编码符号假设，改为"按类别+名称判方向、统一正数"。

### 发现 3：下游消费 `trial_balance.audited_amount`（需求 6 校验目标态）

`data_quality_service._check_debit_credit_balance` 已按 `account_category` 分方向（asset/expense 为借方类、liability/equity/revenue 为贷方类）汇总 audited_amount——**这是新约定的目标态**。`disclosure_engine`、报表生成、`data_fetch_custom` 均读 audited_amount。

### 发现 4：类别推断已有"名称优先+编码兜底"

`account_chart_service._infer_category(code, name)` 已实现，但只返回大类，**不识别资产备抵方向反向**。备抵识别需新增（参考前端 TrialBalance.vue getDirection 正则）。

### 发现 5：调整分录与合并的独立符号假设（需求 6 扩展点）

- `recalc_adjustments`：rje/aje = `SUM(debit) - SUM(credit)`（净额，借正贷负）。
- `consol_report_service` / `cfs_worksheet_engine`：独立借贷平衡 + "资产=负债+权益"校验，容差 1 元。

### 发现 6：公式取数层也消费 TB 符号（需求 11，codegraph 实证）

`linkage_graph_builder` 显示底稿/报表通过公式从 TB 取数：
- `prefill_formula_mapping.json`：`=TB('1122','期末余额')`、`=TB_SUM('1121~1122','期末余额')`、`=ADJ('1122','aje')`
- `report_config.formula`：`TB('1002','期末余额')` / `SUM_TB('1401~1499',...)` / `ROW('BS-009')`
- 求值器：`data_fetch_custom`（支持 `transform: direct|negate|abs|percentage`）、`module_cell_resolver`（TB 虚拟 sheet 列映射）。

**关键风险**：TB 变正数后所有 `=TB(...)` 预填值变号。`data_fetch_custom` 的 `negate` transform 配置若原为纠正旧约定负数，新约定下会反向纠错 → 底稿/报表预填错。改造须盘点求值器符号假设 + 存量 negate 配置。

### 全下游符号消费点清单（实施前须用 codegraph 补全为 checklist）

已知消费点（按链路顺序）：
1. converter（入库，发现 1）
2. `trial_balance_service.recalc_unadjusted` / `get_summary_with_adjustments`（发现 2，硬编码+二次翻转）
3. `data_quality_service` / `consistency_gate` / `balance_diagnostics`（发现 3，目标态）
4. `adjustment_service` / `consol_report_service` / `cfs_worksheet_engine`（发现 5）
5. 公式取数层 `data_fetch_custom` / `module_cell_resolver` / formula 预填（发现 6）
6. `disclosure_engine` / `disclosure_trace`（读 audited_amount）

`full_recalc` 的 blast radius：11 个调用方（trial_balance router / chain_orchestrator / data_validation_engine 等），改造后须全回归。

## 架构

```
原始行 → converter（判类别+方向 → 存自然正数 + 标方向）
         ↓ tb_balance/tb_aux_balance/tb_ledger/tb_aux_ledger（v2 约定，正数）
TrialBalanceService.recalc_unadjusted（按方向传递，不二次翻转）
         ↓ trial_balance.unadjusted/audited_amount（v2 约定，正数）
data_quality / consistency_gate / 报表 / 底稿（按类别分方向消费）
```

核心是引入一个**单一权威的方向判定模块** `direction_resolver`，入库层、trial_balance 生成层、迁移脚本三处共用，杜绝各处各判一套。

## 组件与接口设计

### 1. 符号约定版本（需求 1）

`ledger_import/sign_convention_types.py` 扩展：

```python
SignConventionVersion = Literal[
    "v1_net_debit_positive",          # 旧：借正贷负
    "v2_category_natural_positive",   # 新：按类别存自然正数
]
CURRENT_SIGN_CONVENTION = "v2_category_natural_positive"  # 切换默认
```

### 2. 方向判定模块 `direction_resolver`（需求 2、3，单一权威源）

新建 `ledger_import/direction_resolver.py`，纯函数、不访问 DB：

```python
def resolve_account_direction(code: str, name: str) -> tuple[str, str]:
    """返回 (direction, source)。direction ∈ {'debit','credit'}。
    步骤：
    1. 备抵/反向特例优先（名称正则）：累计折旧/摊销、坏账/减值/跌价准备、折耗 → credit；
       库存股 → debit。命中即返回 source='contra_account'。
    2. 否则用 _infer_category(code, name) 取大类 →
       asset/expense → debit；liability/equity/revenue → credit。
       source = 'name_keyword' 或 'code_prefix'（取决于 _infer_category 命中路径）。
    3. name 为空 → 仅编码兜底，source='code_prefix_low_confidence'。
    """

# 备抵正则（与前端 TrialBalance.vue getDirection 对齐）
_CONTRA_CREDIT_PATTERN = re.compile(r"累计折旧|累计摊销|坏账准备|.*减值准备|跌价准备|折耗|减值损失准备")
_CONTRA_DEBIT_PATTERN = re.compile(r"库存股")
```

优先级（需求 3.5）：备抵特例 > 名称类别关键词 > 编码前缀。多关键词命中时备抵正则最高优先。

### 3. converter 改造（需求 4、5）

`convert_balance_rows`：
- 算出净额 `raw = debit_part - credit_part`（或方向+净额）后，调 `resolve_account_direction(code, name)` 得 direction。
- 存储金额 = `abs(raw)` 当 raw 符号与 direction 正常方向一致；若实际方向与正常方向相反（如负债出现借方余额），保留带符号值（需求 1.5）。
- 写 `closing_direction`/`opening_direction` = direction，`*_direction_source` = source。
- `sign_convention_version = v2`。

`convert_ledger_rows`：分录行按同模块标 `entry_direction` + source，金额口径不变（分录借贷本身明确）。

实现策略：在 `converter.py` 内新增一个"符号归一化"后处理步骤，集中调用 direction_resolver，避免散落。

### 4. trial_balance 生成层改造（需求 9，关键）

`TrialBalanceService.recalc_unadjusted`：
- 资产负债类：直接传递 tb_balance 汇总的 closing/opening（已是 v2 正数），**移除任何基于旧约定的符号假设**。
- 损益类（5xxx/6xxx）：仍取单边发生额，但改为调 `direction_resolver` 判方向后存自然正数（收入=贷方正、费用=借方正），不再硬编码 `-total_cr`。
- 新增：trial_balance 行携带方向（可复用 account_category 推导，或新增方向列——设计决策见下）。

`get_summary_with_adjustments`：
- **移除 L527-536 的"取反"补偿逻辑**（`if is_credit_dir and amount < 0: amount = -amount`）。新约定下 tb 已是正数，无需补偿。报表汇总改为按 `account_category` 分方向决定加减，而非靠符号。

`recalc_adjustments` / `recalc_audited`：
- 调整分录 net = `SUM(debit)-SUM(credit)` 保持（调整分录借贷本身明确）。
- 关键：确认 `audited = unadjusted + rje + aje` 在 unadjusted 为 v2 正数时仍成立——需在设计/测试中验证调整对负债类科目的加减方向正确（见需求 6.7）。

**设计决策（已定稿）**：trial_balance **不新增 direction 列**（方案 A）。下游靠 `account_category` + direction_resolver 推方向（trial_balance 已有 account_category），零迁移、与现有 data_quality 口径一致。

### 5. 平衡校验统一（需求 6）

- 分录级：复用 `data_quality_service._check_debit_credit_balance`（已按 category：asset+expense=借方类，liability+equity+revenue=贷方类）。新约定下两类合计应相等。
- 报表级：`consistency_gate.check_tb_balance` / `check_bs_balance` 已是"资产=负债+权益"，保持。
- 容差：固化常量 `BALANCE_TOLERANCE = Decimal("1")`（±1 元），**定义在 `sign_convention_types.py`**（与约定版本同模块，单一来源），供 data_quality / consol / cfs 共用，替换散落的硬编码 1 元。
- 调整分录（adjustment_service）：审定数加减方向校验，确保 unadjusted 为 v2 正数后审定数正确。
- 合并（consol_report_service / cfs_worksheet_engine）：盘点符号假设，对齐 v2 + 统一容差。

### 6. 存量数据迁移脚本（需求 7）

`backend/scripts/migrate/migrate_sign_convention_v2.py`（正式工具，非 `_` 前缀）：
- 范围：四表 + trial_balance，按 project+year+dataset。
- 逻辑：对 `sign_convention_version != v2`（或为空）的记录，按 `direction_resolver(code,name)` 判方向：贷方类当前为负数则翻正、补方向字段、标 v2。
- dry-run：只统计 + 样例，不写库。
- 幂等：已 v2 的记录跳过。
- 回退：迁移前对受影响 project+year 的四表做快照（写入 `_sign_migration_backup` 表或导出 JSON），失败可恢复（需求 7.8/7.9）。
- 无法判定类别/方向的记录跳过 + 记入待复核清单。
- 审计留痕：写 app_audit_log（action=sign_convention_migrate）。
- 完成后跑平衡校验断言通过。

### 7. 过渡期语义（需求 10）

- 切换时点：本特性上线后所有新导入 `CURRENT_SIGN_CONVENTION=v2`。
- 版本标识：每条记录 `sign_convention_version` 区分 v1/v2。
- 混存策略（推荐）：**消费前要求迁移**——下游读取时若检测到该 project+year 存在 v1 数据，UI/API 提示"需先运行符号迁移"，避免按错口径解释。dataset 级粒度判断。
- 迁移完成后过渡逻辑可退场。

## 数据模型

无新增表（推荐方案 A）。复用 V064 已有列：
- 四表：`opening_direction` / `closing_direction` / `opening_direction_source` / `closing_direction_source` / `sign_convention_version` / `sign_anomaly_flags`
- 序时账：`entry_direction` / `entry_direction_source`
- trial_balance：复用 `account_category`（不新增 direction 列）

迁移备份：`_sign_migration_backup`（一次性，迁移完可清理）或 JSON 导出到 storage。

## 错误处理

- 类别/方向无法判定：不擅改，记入待复核清单（迁移）或标 `sign_anomaly_flags`（入库）。
- 方向与类别冲突（负债借方余额）：如实保留带符号值 + 标异常，不强制翻正（需求 1.5）。
- 迁移中途失败：事务回滚 + 备份可恢复；按 project+year 分批，单批失败不污染其他批。

## 测试策略

### 单元测试（纯函数，可 SQLite）
- `direction_resolver`：6 大类 + 备抵反向（累计折旧/坏账准备/库存股）+ 名称编码冲突 + 名称缺失兜底 + 多关键词优先级。
- converter：各类科目存储符号正确、方向字段写入、显式方向列优先、借贷分列、幂等。

### 集成测试（真实 PG）
- recalc_unadjusted/get_summary 改造后符号传递无二次翻转。
- 平衡校验：平衡账套分录级 + 报表级通过（±1 容差）。
- 迁移脚本：旧数据迁移后符号正确、幂等、回退、平衡通过。

### PBT（hypothesis，**max_examples=5**）
- 属性：对任意科目，`resolve_account_direction` 返回方向唯一且备抵优先级稳定。
- 属性：converter 转换后，同类科目存储符号一致；幂等（二次转换结果相同）。

### 端到端（Playwright）
- 导入 → 试算表借贷平衡为 0；报表资产=负债+权益；底稿取数符号正确。

## 关键风险

1. **二次翻转漏改**（最高危）：`get_summary_with_adjustments` 的取反补偿、`recalc_unadjusted` 损益硬编码若漏改，符号紊乱。→ 设计已定位，tasks 须逐处覆盖 + 测试守护。
2. **调整分录方向**：unadjusted 变 v2 正数后，audited 加减方向须验证，尤其负债类调整。
3. **存量混存**：迁移未完成时下游误读 → 过渡期"消费前要求迁移"策略兜底。
4. **备抵覆盖不全**：某类备抵科目名称未命中正则 → 迁移待复核清单 + 回退路径兜底。
5. **合并/CFS 符号假设**：独立校验逻辑可能隐含旧约定 → 设计已列入盘点项。
