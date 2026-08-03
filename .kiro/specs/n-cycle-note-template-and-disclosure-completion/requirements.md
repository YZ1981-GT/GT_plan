# Requirements Document

## Introduction

N 类底稿（N1 递延所得税资产 / N2 应交税费 / N3 递延所得税负债 / N4 税金及附加 / N5 所得税费用）的四表取数链路已基本完成，但：

1. 附注模板中 N 类 5 个章节的 `_tables` 全部为 0（无表格骨架/列定义/guidance）—— 底稿推送虽能建表但 seed 路径残缺
2. 披露 Tab 的公式预设块有 3 个缺失（N2/N4/N5 披露 sheet）
3. 需要系统性核查「四表入库→render 取数→审定表预填→披露 Tab 取数→同步到附注→附注正确渲染」全链路

本 spec 目标 = 补齐上述缺口，使 N 类全 5 循环达到「四表入库后刷新取数有数据 + 点击推送后附注正确渲染表格」的端到端标准。

### 科目→报表行映射真源（DB 实证）

| 循环 | 科目 | 报表行 | 方向/类型 | 公式 |
|------|------|--------|-----------|------|
| N1 | 1811 | BS-036 | 借方/资产 | `TB('1811','期末余额')` |
| N2 | 2221 | — (无独立行) | 贷方/负债 | — |
| N3 | 2901 | BS-067 | 贷方/负债 | `TB('2901','期末余额')` |
| N4 | 6403 | IS-003 | 借方/损益 | `TB('6403','本期发生额')` |
| N5 | 6801 | IS-023 | 借方/损益 | `TB('6801','本期发生额')` |

### 附注章节映射（variant_matrix 实证）

| 循环 | listed | soe | 备注 |
|------|--------|-----|------|
| N1+N3 | 五、30 | 八、31 | 共用章节，N3 负债段数据在 N1 披露 Tab 展示 |
| N2 | 五、41 | 八、41 | |
| N4 | 五、63 | **null** | 国企源模板逐字「无」= 不披露 |
| N5 | **三、所得税费用** (md 截断) | 八、78 | listed 在 variant_matrix 为 null，实际在「三、」章 |

## Requirements

### Requirement 1: 附注模板结构修复

**User Story:** 作为审计助理，我需要在附注模块中看到 N 类各章节的正确表格骨架（表头/列/行集/编制提示），使底稿同步过来的数据能被正确渲染而非落进空壳。

1.1 为 **五、30**（listed 递延所得税）补建 4 张表的 `_tables` 结构：(1)未经抵销 5 列两级表头 (2)抵销后净额 5 列 (3)未确认DTA明细 3 列 (4)亏损到期 4 列，行集/列定义/guidance 逐字取自源 xlsx

1.2 为 **八、31**（soe 递延所得税）补建 5 张表：同上市 4 张 + (2)B 互抵明细表 5 列，列标签按国企口径（「年初余额」非「上年年末余额」）

1.3 为 **五、41**（listed 应交税费）补建 1 张表：3 列 flat（税项/期末余额/上年年末余额）+ 动态税种行（源模板 R8~R22 从审定表取 15 行）+ 合计行 + guidance

1.4 为 **八、41**（soe 应交税费）补建 1 张表：5 列 flat（项目/期初余额/本期应交/本期已交/期末余额）+ 动态税种行 + 合计行 + guidance

1.5 为 **五、63**（listed 税金及附加）补建 1 张表：3 列 flat（项目/本期发生额/上期发生额）+ 动态税种行 + 合计行 + guidance

1.6 为 **三、所得税费用**（listed N5）补建 2 张表：表(1) 所得税费用明细 3 列 3 行+合计 / 表(2) 利润总额→所得税调整 3 列 12 动态行

1.7 为 **八、78**（soe N5）补建 2 张表：表(1) 4 行（多「其他」行）/ 表(2) 14 动态行

1.8 所有表的 `columns` 必须逐字对齐现有 `buildNxListedColumns`/`buildNxSoeColumns` 的 key/label/group/flat 声明

1.9 所有表补 `guidance`（取源模板红字/提示/括注）

1.10 幂等脚本 `fix_note_n_cycle_full_structure.py` 支持 `--dry-run`/`--check`/`--apply`

#### Acceptance Criteria

- `fix_note_n_cycle_full_structure.py --check` exit 0
- 五、30 有 4 张表 / 八、31 有 5 张表 / 五、41 有 1 张表 / 八、41 有 1 张表 / 五、63 有 1 张表 / 三、所得税费用 有 2 张表 / 八、78 有 2 张表
- 所有表 `columns` 非空且与前端 builder 逐字对齐
- 所有表 `guidance` 非空（≥20 字）

### Requirement 2: 公式预设补齐

**User Story:** 作为审计助理，我需要在公式管理界面看到 N2/N4/N5 披露 sheet 的取数公式（从审定表/明细表自动拉值），使披露表金额有来源可查、不必手工抄录。

2.1 N2 补披露 sheet 公式预设块（上市从 N2-1 取审定数/期初；国企从 N2-2 取期初/本期应交/本期已交）

2.2 N4 补披露 sheet 公式预设块（上市从 N4-1 取本期审定数/上期）

2.3 N5 补披露 sheet 公式预设块（表1 从 N5-1 取当期/递延；表2 从 N5-2 取利润总额到所得税调整 12 行）

2.4 公式预设的科目码必须与 render 策略中的 `_resolve_account_codes` 口径一致

#### Acceptance Criteria

- `prefill_formula_mapping.json` 中 N2 有 2 个披露块 / N4 有 1 个 / N5 有 2 个
- `convert_prefill_presets` 能正常加载无报错
- 科目码 6403/6801/2221 与对应 render 策略一致

### Requirement 3: 取数→披露→附注全链路验证

**User Story:** 作为审计助理，我需要四表入库后在底稿披露表看到自动填充的金额，点击「同步到附注」后附注模块正确显示对应表格，实现端到端数据贯通。

3.1 N1 链路核查：render 下发 `adjudication_prefill`/`tb_source_codes`/`trial_balance_liability` → 披露 Tab 读取 → `buildN1SyncPayload` 构造 → 附注侧 4/5 张表正确渲染

3.2 N2 链路核查：render 下发 `tax_prefill`/`tb_source_codes` → 两版披露 Tab 各自读取（上市从审定数/国企从明细表）→ 推送 → 附注 1 张表正确（上市 3 列/国企 5 列）

3.3 N4 链路核查：render 下发 `period_amount`/`tax_prefill` → 上市披露 Tab → 推送 → 附注 1 张表；国企 Tab 显示「本版不适用」

3.4 N5 链路核查：render 下发 `period_amount`/`adjudication_prefill` → 两版披露 Tab → 推送 → 附注 2 张表各自正确

3.5 所有章节推送后附注侧 `_sub_table_columns` 有正确 flat/group 声明，无凭空父表头

#### Acceptance Criteria

- 真实 DB 直跑 render 后各循环 `tb_source_codes` 非空
- 浏览器实测同步后 `last_sync_at` 前移
- 推送后 `_column_groups` 为 `[]` 或正确显式分组

### Requirement 4: 守卫与 CI

**User Story:** 作为开发者，我需要 CI 守卫确保 N 类附注模板结构、公式预设、前端列定义三方一致，防止后续改动引入漂移。

4.1 后端守卫 `test_note_n_cycle_full_structure.py`（openpyxl 交叉比对 + 反向自检）

4.2 前端契约 `nCycleNoteSubtableContract.spec.ts`（共享 helper P1~P6）

4.3 CI job `note-n-cycle-full-structure`

4.4 公式预设守卫 `test_n_cycle_formula_presets.py`（sheet 名三处一致 + 科目码合法）

#### Acceptance Criteria

- `governance-checks.yml` 含 job `note-n-cycle-full-structure`
- 后端守卫 + 前端契约 + 预设守卫全绿
- 守卫含反向自检（文件长度/表数锚点）
