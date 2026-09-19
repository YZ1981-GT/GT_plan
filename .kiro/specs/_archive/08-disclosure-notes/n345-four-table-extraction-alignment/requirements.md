# Requirements Document

## Introduction

N3（递延所得税负债）/ N4（税金及附加）/ N5（所得税费用）三个循环的**四表库取数链路**存在
从 P0 到 P2 的系统性缺陷。本 spec 沿用 N1 已验证的范式
（spec `n1-four-table-extraction-and-disclosure-alignment`），以 **`report_config` DB 表为
科目映射唯一真源**（已只读实证），以 **源模板 xlsx 为结构裁决者**，收口以下六类问题。

**披露侧不在范围内**：N3 源模板无「附注披露信息」sheet（披露与 N1 共节 `五、30` / `八、31`，
N1 表(1) 已含负债段）；N4 / N5 的披露结构已由归档 spec `n-cycle-tax-disclosure-alignment`
对齐完毕。本 spec 只做**取数**与**公式预设**。

### 已实证的核心事实

**科目映射真源（`report_config`，四套准则全部一致）**

| row_code | row_name | formula | 归属 |
|---|---|---|---|
| `BS-067` | 递延所得税负债 | `TB('2901','期末余额')` | N3 |
| `IS-003` | 税金及附加 | `TB('6403','本期发生额')` | N4 |
| `IS-023` | 减：所得税费用 | `TB('6801','本期发生额')` | N5 |
| `IS-022` | 三、利润总额 | `ROW('IS-019') + ROW('IS-020') - ROW('IS-021')` | **派生行，非科目** |

**活体科目表（`tb_balance`）**

- `2901` + `.01 公允价值变动` / `.02 固定资产加速折旧` / `.03 经营租赁相关`
- `6403` + 子科目**编码语义在客户间冲突**（`6403.01` 实测为「印花税」，`6403.02` 既是
  「税金及附加_城市维护建设税」也是「车船税」）→ 子科目编码不可作为税种判据
- `6801` + `.01 当期所得税费用` / `.02 递延所得税费用`（**语义清晰且稳定，可用于拆分**）
- **`1812` 在活体 `tb_balance` 中 0 命中**（不存在的科目码；递延所得税负债是 `2901`）
- `6001` = 主营业务收入 / 营业收入（**不是利润总额**）

## Requirements

### Requirement 1: 修复 N5 四表取数的运行期崩溃（P0）

**User Story:** 作为审计助理，我希望 N5 所得税费用底稿在四表入库后能带出未审数，
而不是永远显示 0。

#### Acceptance Criteria

1. WHEN N5 render 执行 TB 取数 THEN 系统 SHALL 以 `await get_active_filter(db, Table.__table__, project_id, year or 0)` 的正确签名调用（现实现传单参 `ctx.project_id`，必然 `TypeError`）。
2. WHEN N5 render 执行审定表预填 THEN 系统 SHALL 同样以正确签名调用。
3. WHEN 四表已入库且科目 `6801` 有发生额 THEN `html_data.trial_balance.period_amount` SHALL 非 0。
4. WHEN 四表已入库且 `6801` 有子科目 THEN `html_data.adjudication_prefill` SHALL NOT 为 `None`。
5. WHEN `get_active_filter` 已含 `project_id` 过滤 THEN 系统 SHALL NOT 再手写 `Table.project_id == str(project_id)` 条件（重复且绕过统一入口语义）。
6. WHEN 守卫运行 THEN 系统 SHALL 以**真实函数签名**调用被测函数（现有 28 个 N5 测试全绿却漏掉该缺陷，因为它们不触发真实调用）。

### Requirement 2: 修复 N4 审定表的 dead output（P0）

**User Story:** 作为审计助理，我希望 N4 审定表打开时未审数已按四表发生额带出，
而不是要我手工把总额再敲一遍。

#### Acceptance Criteria

1. WHEN N4 审定表加载且无持久化行数据 AND `tb_values` 有非零净发生额 THEN 系统 SHALL 把该值 seed 进未审数。
2. WHEN 已有持久化行数据 THEN 系统 SHALL NOT 覆盖（手工优先）。
3. WHEN 无法按税种拆分 THEN 系统 SHALL 只 seed 合计行或「其他」行，并在界面标注该值为总额级、需人工按税种分配。
4. WHEN 守卫运行 THEN 系统 SHALL 断言该 seed 分支不是空 `if` 块（现实现 `N4TabAdjudication.vue` 内只有注释）。

### Requirement 3: 三循环接入 report_config 科目映射

**User Story:** 作为项目经理，我希望项目自定义了报表行公式后，底稿取数能自动跟随，
而不是被代码写死。

#### Acceptance Criteria

1. WHEN N3 render 取数 THEN 系统 SHALL 经 `resolve_report_line_account_codes(db, pid, 'BS-067', fallback=['2901'])` 解析科目集。
2. WHEN N4 render 取数 THEN 系统 SHALL 经 `'IS-003'`（fallback `['6403']`）解析。
3. WHEN N5 render 取数 THEN 系统 SHALL 经 `'IS-023'`（fallback `['6801']`）解析。
4. WHEN 映射解析失败 / 无配置 / 公式为空 THEN 系统 SHALL 回退 fallback 并继续渲染，不得抛错。
5. WHEN render 返回 THEN 三者 SHALL 各输出 `tb_source_codes`（形如 `{row_code, codes}`）。
6. WHEN `tb_source_codes` 被输出 THEN 前端 SHALL 至少有一个消费点（禁止 dead output）。

### Requirement 4: N3 取数增强（叶子聚合 + 语义分类）

**User Story:** 作为审计助理，我希望客户把递延所得税负债挂在子科目上时，N3 也能取到数并按分类落行。

#### Acceptance Criteria

1. WHEN 存在科目级精确行 THEN 系统 SHALL 只用它（现实现即如此，保留）。
2. WHEN 无科目级行而有子科目 THEN 系统 SHALL 取**叶子**子科目聚合（现实现 `.limit(1)` 精确单行 → 此场景恒 0）。
3. WHEN 取到叶子子科目 THEN 系统 SHALL 按语义槽聚合并预填审定表对应分类行（现实现把 seed **全部塞进「其他」一行**，分类信息全丢）。
4. WHEN 实现 2901 语义分类 THEN 系统 SHALL **复用 N1 已有的分类逻辑**（抽为共享模块），不得新造第三套。
5. WHEN 负债类科目符号约定不一致 THEN 系统 SHALL `abs()` 归一（活体实测 `2901` 期末同时存在负数与绝对值两种约定）。
6. WHEN N3 render 输出 `formula_direction` / `n3_metadata` / `trial_balance` THEN 前端 SHALL 有消费点，否则移除该输出（现三者均为 dead output）。

### Requirement 5: N5 当期/递延拆分

**User Story:** 作为审计助理，我希望 N5 审定表的「当期所得税费用」与「递延所得税费用」两行
能分别按四表叶子科目带出。

#### Acceptance Criteria

1. WHEN `6801` 有叶子子科目 THEN 系统 SHALL 按 `6801.01`/名称含「当期」归当期、`6801.02`/名称含「递延」归递延。
2. WHEN 只有父级 `6801` 无子科目 THEN 系统 SHALL 把总额落在「当期」行并标注需人工拆分（保留现有回退行为）。
3. WHEN 损益类取数 THEN 系统 SHALL 取**发生额**（借−贷），不取期末余额。
4. WHEN 叶子聚合 THEN 系统 SHALL 排除父级科目行，防与子科目双算。

### Requirement 6: 前端接入 TB 核对与「从四表库带入」

**User Story:** 作为现场经理，我希望三个审定表都能显示与试算平衡表的核对结果，
并能一键把四表数带进未审数。

#### Acceptance Criteria

1. WHEN N3 / N4 / N5 审定表渲染 THEN 系统 SHALL 显示 TB 核对行（试算表数 / 审定合计 / 差异数）。
2. WHEN 实现 TB 核对 THEN 系统 SHALL 复用既有共享 composable `useLmnTbReconcile`（该文件已存在 78 行但**全仓 0 消费方**），不得各写一份。
3. WHEN TB 数据全 0 THEN 系统 SHALL 不渲染核对行（避免四表未导入时误报差异）。
4. WHEN 三个审定表渲染 THEN 系统 SHALL 各提供「从四表库带入未审数」按钮（现三者全无，全平台仅 N1 / K1 / K9 有）。
5. WHEN 点击带入 THEN 系统 SHALL 只填空不覆盖（手工优先），并提示带入了几行。
6. WHEN 损益类（N4 / N5）接 TB 核对 THEN 系统 SHALL 以 `isIncome` 口径消费（`end_balance` 存的是净发生额）。

### Requirement 7: 清理 N3 的披露 inert 残留

**User Story:** 作为技术复核人，我希望已删除的 N3 披露 Tab 不留下会渲染出空白页的入口。

#### Acceptance Criteria

1. WHEN 后端 `N3_SHEETS` 被读取 THEN 系统 SHALL NOT 包含 `附注披露信息` 条目（N3 源模板无该 sheet）。
2. WHEN 宿主 `GtN3DeferredTaxLiabilities.vue` 做 sheet 分发 THEN 系统 SHALL NOT 把 `附注` / `披露` 判定为 HTML 专属 sheet（否则该 sheet 一旦出现即空白 Tab）。
3. WHEN 守卫运行 THEN 系统 SHALL 断言 N3 侧不存在披露相关分发分支与 sheet 声明。

### Requirement 8: 公式预设纠错与补齐

**User Story:** 作为审计助理，我在 N3 / N4 / N5 底稿页打开公式管理时，希望预设的科目与口径都是对的。

#### Acceptance Criteria

1. WHEN 加载 `workpaper:N3` / `workpaper:N5` 预设 THEN 系统 SHALL NOT 出现科目 `1812`（活体 0 命中的不存在科目码），递延所得税负债 SHALL 用 `2901`。
2. WHEN 加载 `workpaper:N3` 预设 THEN 审定表块的 `account_codes` SHALL 为 `['2901']`（现为 `['6801']` 所得税费用），且 `wp_name` SHALL 为递延所得税负债审定表（现为「所得税费用审定表」，系复制粘贴）。
3. WHEN N4 / N5 预设取损益类科目 THEN 系统 SHALL 用 `本期发生额`（现全部用 `期末余额`，与 `report_config` 的 `IS-003` / `IS-023` 口径不符，违反平台铁律「损益取发生额」）。
4. WHEN 预设涉及 `利润总额` THEN 系统 SHALL NOT 用 `TB('6001',...)`（`6001` 是营业收入）；由于 `IS-022 利润总额` 是 `ROW()` 派生行而 prefill 引擎无 `REPORT`/`ROW` 解析器，该 cell SHALL 降级为 `PLACEHOLDER` 并在描述中写明正确来源。
5. WHEN 预设涉及 `法定税率` THEN 系统 SHALL NOT 用 `WP('N5','所得税费用审定表N5-1','审定数')`（税率不等于审定金额）；SHALL 降级为 `PLACEHOLDER`。
6. WHEN 预设按税种取 `6403` 子科目 THEN 系统 SHALL 移除该 cell（活体实测 `6403.01` 是「印花税」而非城建税，子科目编码在客户间冲突，宁缺勿造）。
7. WHEN N5 预设加载 THEN 系统 SHALL 提供 `6801.01 当期` / `6801.02 递延` 的发生额预设。
8. WHEN 同一 `wp_code` 内存在多个块 THEN `cell_ref` SHALL 唯一（`page_key = workpaper:{wp_code}` 忽略 sheet，同名必互相遮蔽）。
9. WHEN 预设表达式被校验 THEN SHALL 经 `validate_formula` 无错误（`ADJ()` 属 prefill 专属函数，按 prefill 词汇表放行）。

### Requirement 9: 守卫与实测

**User Story:** 作为技术复核人，我希望「后端输出了但前端不读」和「函数签名错被 except 吞掉」
这两类缺陷被测试拦住。

#### Acceptance Criteria

1. WHEN 守卫运行 THEN 系统 SHALL 断言 N3 / N4 / N5 render 输出的四表键**均有前端消费点**（源码扫描），或已登记豁免并写明理由。
2. WHEN 守卫运行 THEN 系统 SHALL 以真实签名调用 N5 的取数函数并断言返回非空（拦签名错）。
3. WHEN 守卫运行 THEN 系统 SHALL 断言三循环预设的科目白名单与口径（`本期发生额` vs `期末余额`）。
4. WHEN 守卫运行 THEN 系统 SHALL 断言 `useLmnTbReconcile` 至少有 3 个消费方（防现成件再次闲置）。
5. WHEN 实测执行 THEN 系统 SHALL 在活体项目上验证三个审定表的四表带入与 TB 核对，并在验证后复原测试数据。

## Glossary

| 术语 | 含义 |
|------|------|
| 损益取发生额 | 平台铁律：损益类科目（6xxx）取 `本期发生额`（借−贷），不取期末余额；`report_config` 的 `IS-003` / `IS-023` 即此口径 |
| dead output | 后端 render 输出了某键但前端零消费，等价于没做 |
| 语义槽 | 负债段行位的稳定英文键，N1 已定义 5 个（`depreciation` / `afs_fv` / `investment_property_fv` / `lease` / `other`） |
| 空 if 块 | 只有注释没有语句的条件分支，编译与测试都不报错但功能为零（N4 审定表 seed 即此形态） |
| `useLmnTbReconcile` | 既有共享 composable，为 L/M/N 循环审定表提供「试算表数 / 差异数」核对，当前 0 消费方 |
