# Design Document

## Overview

L/M/N 三循环（18 科目）审定表四表库取数公式预设体系设计。后端 L 循环补 TB 取数 + M1/M2 补齐 + Tier A 公式预设注册 + 前端 TB 核对行消费 + surfacing 对齐 + 刷新入口。无 DB 迁移，纯 render 层 + 预设数据 + 前端 UI。

## Architecture

本 spec 遵循平台既有四表取数范式（D 循环/K 循环/F2 已验证），分三层：

1. **后端 render 策略层**：各 `_l*/_m*/_n*` render 策略在 render 时按灰度开关查 tb_balance/trial_balance，输出 `html_data.trial_balance` 供前端消费。
2. **公式预设数据层**：`formula_presets_seed.json` 注册 Tier A 可编辑取数公式（page_key `workpaper:X-1`），`preset_library.build_preset_library` 读时收敛。
3. **前端消费层**：各审定表 composable 加 `tbReconcile` computed 展示 TB 核对行（只读，不覆盖手工审定行）。

### 数据流

```
tb_balance(DB) ──get_active_filter──→ _fetch_tb_data(render策略)
                                         │
                                         ↓
                               html_data.trial_balance
                                         │
                    ┌────────────────────┼────────────────────┐
                    ↓                    ↓                    ↓
          前端 tbReconcile       FormulaStatusPanel     公式管理中心
          (审定合计 vs TB)       (semantic标签)         (Tier A 预设展示)
```

### 灰度开关

`config.py` 新增 `LMN_FOUR_TABLE_EXTRACTION_ENABLED: bool = False`。仅 L 循环新增的 `_fetch_tb_data` 受此开关约束；M/N 已有取数逻辑不受影响。

## Components and Interfaces

### 后端改动文件（8 个 L 循环 render 策略 + 2 个 M 循环）

| 文件 | 改动 |
|------|------|
| `_l1_short_term_loans.py` | 新增 `_fetch_tb_data` (2001, 负债贷方) |
| `_l2_interest_payable.py` | 新增 `_fetch_tb_data` (2231, 负债贷方) |
| `_l3_long_term_loans.py` | 新增 `_fetch_tb_data` (2501, 负债贷方) |
| `_l4_bonds_payable.py` | 新增 `_fetch_tb_data` (2502, 负债贷方) |
| `_l5_long_term_payables.py` | 新增 `_fetch_tb_data` (2701, 负债贷方) |
| `_l6_special_payables.py` | 新增 `_fetch_tb_data` (2601, 负债贷方) |
| `_l7_other_non_current_liabilities.py` | 新增 `_fetch_tb_data` (2801, 负债贷方) |
| `_l8_financial_expenses.py` | 新增 `_fetch_tb_data` (6603, 损益借方发生额) |
| `_m1_dividends_payable.py` | 新增 `_fetch_tb_data` (2232, 负债贷方) |
| `_m2_paid_in_capital.py` | 新增 `_fetch_tb_data` (4001, 权益贷方) |

### 共享后端 helper

新建 `backend/app/routers/wp_render_strategies/_lmn_tb_helper.py`：
- `fetch_tb_balance_for_liability(ctx, account_code)` — 负债/权益/资产类取期初+期末余额
- `fetch_tb_balance_for_income(ctx, account_code)` — 损益类取借方−贷方发生额
- 统一 `get_active_filter` + 精确码优先 + 前缀 LIKE 回退叶子聚合 + fail-open

### 前端改动

| 文件 | 改动 |
|------|------|
| L1-L8 各 `TabAdjudication.vue` | 加 `tbReconcile` computed + TB 核对 el-alert |
| M1/M2 各 `TabAdjudication.vue` | 加 `tbReconcile` computed |
| `formula_presets_seed.json` | +36 条 L/M/N 预设公式 |
| `wp_surfaced_l/m/n.py` | 对齐 Tier A 公式文案 |

### 公式预设结构（每条）

```json
{
  "page_key": "workpaper:L1-1",
  "target_cell": "L1-adj-tb-amount-ending",
  "expression": "TB('2001','期末余额')",
  "category": "auto_calc",
  "description": "L1短期借款审定表TB核对（期末余额，负债贷方，tb_balance科目2001）",
  "refs": ["2001"]
}
```

## Data Models

无新 DB 表/列/迁移。数据变更仅：
- `formula_presets_seed.json`（committed 文件，+36 条）
- `config.py` 加一行 Settings 属性

## Correctness Properties

### Property 1: 负债类期末余额取值正确

负债/权益/资产类科目从 `tb_balance.closing_balance` 取期末余额，get_active_filter 过滤 dataset 版本。精确码优先，无精确码时叶子聚合（`_is_leaf`=该 code 不是任何其它 code 前缀）。

**Validates: Requirements 1.1, 2.1, 2.2**

### Property 2: 损益类发生额方向正确

损益借方科目（L8=6603/N4=6403/N5=6801）净发生额 = debit_amount − credit_amount（借正贷负，与 recalc 已修的 closing_direction 带符号求和口径一致）。

**Validates: Requirement 1.2**

### Property 3: 灰度关闭逐字节等价

`LMN_FOUR_TABLE_EXTRACTION_ENABLED=False` 时，L 循环 render 返回 `trial_balance` 全字段为 0（与改前不含该字段时前端 `props.htmlData?.trial_balance` 为 undefined→0 等价）。M/N 不受开关约束。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 4: fail-open 不阻断 render

`_fetch_tb_data` 内部 try/except 捕获全部异常（含 DB 连接失败/表不存在/列名错），result 各字段置 0，log warning，render 正常返回。

**Validates: Requirements 1.4, 2.4**

### Property 5: 前端 hasTb 守卫

`tbReconcile` 的 `hasTb` = `trial_balance.end_balance !== 0 || trial_balance.begin_balance !== 0`。为 false 时不渲染 TB 核对行（避免 TB 未导入时误报差异）。

**Validates: Requirement 4.2**

### Property 6: 手工优先不覆盖

TB 核对行（试算平衡表数/差异数）为只读展示，不写入审定表任何可编辑字段（`beginUnadjusted`/`endUnadjusted`/`aje`/`rje`/`reason` 等）。审计师手工录入的审定行永不被自动取数覆盖。

**Validates: Requirements 6.3, 宁缺勿造边界**

### Property 7: 预设公式格式合法

每条 `formula_presets_seed.json` 新增条目须满足：`page_key` 匹配 `workpaper:{L|M|N}\d+-1`；`expression` 仅含 `TB`/`SUM_TB` 合法函数（`find_unsupported_formula_functions(expr)==[]`）；`category=='auto_calc'`；`refs` 非空数组。

**Validates: Requirements 3.1-3.7, 8.2**

### Property 8: 撞码不双算

M3(4002)/M4(4002) 共用码：预设公式只给合计级 TB 核对（TB('4002','期末余额')），不自动拆分到 M3/M4 分类行。M6(4104)/M8(4104) 同理。

**Validates: 撞码问题章节**

### Property 9: get_active_filter 统一口径

所有新增 `_fetch_tb_data` 必须使用 `await get_active_filter(ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0)` 作为 WHERE 条件（不裸写 `is_deleted==False`）。

**Validates: Requirement 1.3**

### Property 10: tbReconcile 口径一致

前端 `tbReconcile.diff = totalAudited - trial_balance.end_balance`（负债/权益/资产类）或 `totalAudited - (trial_balance.debit_amount - trial_balance.credit_amount)`（损益类）。与后端取数字段对齐。

**Validates: Requirement 4.1**

### Property 11: surfacing 公式文案与预设一致

`wp_surfaced_l/m/n.py` 中 Tier A「取数」分类条目的公式文案须与 `formula_presets_seed.json` 对应条目的 `expression` 逐字相同。

**Validates: Requirement 5.1**

### Property 12: 零回归门

全部 L/M/N 相关后端测试（vitest/pytest）+前端相关 vitest 零新增失败；M/N 现有 `_fetch_tb_data` 行为逐字节不变。

**Validates: Requirements 7, 8**

## Error Handling

- 后端 `_fetch_tb_data`：全部 DB 异常 try/except → result 各字段 0 + `logger.warning`
- 前端 `tbReconcile`：`html_data?.trial_balance` 为 undefined/null → 0（既有 `parseNum` helper）
- 灰度开关读取异常 → `getattr(settings, 'LMN_FOUR_TABLE_EXTRACTION_ENABLED', False)` 兜底 False
- `formula_presets_seed.json` 解析失败 → `preset_library` 已有 fail-open（跳过 bad entry）

## Testing Strategy

- **后端单测**：共享 helper `_lmn_tb_helper.py` 纯函数测试（mock row → 验证 begin/end/debit/credit 各方向正确）
- **后端集成**：L1 render 灰度 ON/OFF 对比测试（ON 返 trial_balance 非 0 / OFF 返全 0）
- **前端 vitest**：tbReconcile computed 测试（mock allResponses + trial_balance prop → 验证 diff/hasTb）
- **公式预设契约**：`check_formula_presets_lmn.py` 断言 36 条预设格式合法 + expression 仅 TB/SUM_TB
- **Playwright**（可选）：L1 审定表渲染 TB 核对行
