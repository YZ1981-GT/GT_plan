# Task 10 / C-9：G14 信用减值损失 —— 固定 9 行对齐模板 + 布尔校验列 + K 列模板缺陷

spec `g-cycle-single-region-detail-lanes` 九条 lane 的**第四条**。commit `24f54fd18`（26 文件）。

---

## 1. 模板逐格实测

`G/G14 信用减值损失.xlsx`：60,094 B / sha256 `5ca770907cfd3723159f4eb45871102f1cee382255e391f3aca0b1d57a287dc6` / 8 sheets。
受管 sheet `明细表G14-2`：`max_row=36` / `max_column=13` / **0 个 definedName**。

### 1.1 几何

两级表头 R9/R10。R9 的**横向**合并区只有两个：`B9:D9` 本期数 · `F9:K9` 对应科目-减值准备。
另四个跨两行的单列合并：`A9:A10` 项目 · `E9:E10` 对应科目 · `L9:L10` 核对 · `M9:M10` 索引号。

数据区 **R11-R19 固定 9 行**，footer R20 合计，R21「三、审计说明」/ R23「四、审计结论」在受管区外。

🔴 有效内容列 **13**（A..M）**恰等于** `max_column` —— 这张表没有空尾列，所以 `uuid_col="N"` 时
「有效列右移一列」与「max_column+1」两个口径**重合**。G10/G8 是 `max_column` 含空列的情形
（必须取有效列口径），此处不构成反例，判据里写明了这点。

### 1.2 四个公式列（每行同型）

```
D11 = =B11+C11           审定数 = 未审 + 调整
J11 = =F11+G11-H11-I11   期末余额 = 期初 + 计提 − 转回 − 转销
K11 = =G11+H11           🔴 计入损益（见 §2.2）
L11 = =D11=K11           布尔核对：审定数 == 计入损益
```

footer R20 逐列 `=SUM(x11:x19)`，🔴 **`L20` 例外**是布尔 `=D20=K20`。

裸 IF **11 格**全在 `审定表G14-1`（受管表零命中），仍按 per-file 保守策略挂中性化。

### 1.3 固定行集（模板 A 列 R11-R19 逐字）

```
应收票据坏账损失 · 应收账款坏账损失 · 应收款项融资坏账损失 · 其他应收款坏账损失 ·
债权投资减值损失 · 其他债权投资减值损失 · 长期应收款坏账损失 · 财务担保预计损失 · 其他
```

---

## 2. 两处需要裁决的缺陷

### 2.1 🔴 前端固定行集与模板不一致（用户拍板选项 A）

| # | 模板 A 列逐字 | 前端 `G14_LINE_ITEMS` |
|---|---|---|
| 3 | 应收款项融资**坏账**损失 | 应收款项融资**减值**损失 ← 文字不同 |
| 8 | （无） | **合同资产减值损失** `ca`（tbPrefixes 1142） ← 🔴 模板无此行 |

前端 **10 行** vs 模板 **9 行**。行表引擎按**数组顺序**映射 R11-R19 ⇒ 第 10 行会触发扩行、
把 footer R20 挤下去。GC-6 裁决「`rowKey` 是最稳一族（源自模板固定行集）」的前提本来就不成立。

给用户的两条路：**A** 前端对齐模板 9 行（删 `ca`）· **B** 走 `template_row_key` 固定行范式
（平台已有先例 `phase5_d4_ipo_related_sheets` 的 D4-23/D4-22，行身份不靠数组顺序，但要手写
contract payload、薄转发用不上）。**用户选 A。**

实施时发现 `ca` 的波及面比预想大（不是简单删一行）：

| 消费方 | 原行为 | 处置 |
|---|---|---|
| `g14Constants.G14_LINE_ITEMS` | 第 10 行定义 | 删；`other` 行收 `tbPrefixes:['1142']` + `tbNameHints` 含「合同资产」 |
| `g14Constants.G14_ECL_CROSS_REF` | `ca: 'wp:D6-1'` | 改 `other: 'wp:D6-1'` |
| `g14Constants.G14_SOE_BAD_DEBT_SOURCES` | 含 `'ca'` | 删（`other` 本就单独成行，留着会双算） |
| `gCycleSourceEcl.G14_SOURCE_TO_ROW_KEY` | `D6: 'ca'` | 改 `D6: 'other'`（**跨循环 ECL 取数链**，不改就断） |
| `g14AdjStorage` | `/合同资产/ → 'ca'` | 改 `'other'` |
| `g14DisclosureSyncPayload` | `ca: { listed: … }` | 删（披露侧复用 `G14_LINE_ITEMS`，留着会多出无来源空行） |

⇒ 合同资产按 CAS22 仍计入 6702，口径不丢、五条链都不断，只是落点从 `ca` 变 `other`。
K11 的「合同资产减值损失」是 K11 自己的披露行集，与 G14 行集无关，未动。

防回归：新增 `g14Constants.G14_TEMPLATE_ROW_LABELS`（模板行名真源）与 provider 的
`TEMPLATE_ROW_LABELS_G1402` 双向锁 + 模板 A 列**三方**比对（判据
`TestFixedRowSetIsLockedToTemplate` 四条）。

### 2.2 🔴 模板 `K=G+H` 是缺陷（应为 `=G-H`）

同一张表里两个公式对 `H`「本期转回」的符号约定**互相矛盾**：

* `J=F+G-H-I`（期末 = 期初 + 计提 − 转回 − 转销）⇒ 要求 `H` 填**正数**
* `K=G+H`（计入损益 = 计提 **+** 转回）⇒ 把转回当成**增加**损益

判定「`K` 错」的三条依据：

1. **会计口径**：信用减值损失（损益）= 本期计提 − 本期转回，转回冲减损益；
2. **`J` 与准则逐字一致**，它是对的那一式；
3. **平台早已裁定「转回填正数」** —— 前端 `useG14FormulaEngine.migrateReversalToPositive`
   专门把历史负数统一成正数；`useG14Detail` 的 docstring 原文就写「审定数 = 计入损益 =
   计提 − 转回」。

处置同 G8 的模板缺陷口径：

* `K` 在模板**每行都有公式** ⇒ 仍判 `mode=formula`（进 `formula_columns`，受
  `formula_mask` 保护，OO 侧改不了）；
* `formula_templates` **逐字记模板原式** `=G{r}+H{r}` —— 判据逐格比对模板，记成 `=G-H`
  会让 `test_formula_template_renders_to_every_data_row` 必红；
* 会计正确口径由**前端** `calcNetImpairmentLoss` 承担（判据
  `test_frontend_computes_profit_loss_as_provision_minus_reversal` 按值断言它是减法）；
* 缺陷落 `TEMPLATE_ROW_DEFECTS_G1402`，判据 `test_k_defect_still_present_in_template_cell_by_cell`
  逐格复核「缺陷仍在」—— 模板一旦被修成 `=G-H`，判据会红并提示同步更新台账。

**后果如实登记**：有转回时 Excel 侧 `K` 比平台侧多 2×转回。三处登记（provider docstring /
缺陷台账 / 前端编制提示新增一段「与 Excel 的已知差异」）。模板自带的 `L=D=K` 核对列会在
有转回时显示不平 —— 用户看得见，不是静默错。

修根因的两条路都不在本 lane：① 改模板字节（`backend/wp_templates/` 运行时只读 + sha 冻结，
禁止）② 走覆盖层（框架层尚无该机制）+ 会计专业复核。

---

## 3. 🔴 `L` 是布尔校验列（裁决 G1R-H4 首次落地）

`L{r} = =D{r}=K{r}` 求值为 TRUE/FALSE ⇒ `value_type="boolean"` + `mode="formula"`。
`contracts.PROTECTED_MODES` 使其不入 store ⇒ TRUE/FALSE 不会落库。

判据三条（P9，在 `test_g_single_region_p9_p12.py`）+ 本文件的
`test_l_is_a_boolean_check_column` / `test_only_l_is_boolean_among_managed_fields`。

---

## 4. 前端另删 4 个自研派生字段

| 字段 | 归属/理由 |
|---|---|
| `otherMovement` | 模板 J 是 `=F+G-H-I`，**不含**其他变动项 ⇒ 录入值会在 Excel 侧凭空消失 |
| `closingComputed` | 与模板 J 双源：J 本身就是推算式公式，不存在「录入期末 vs 推算期末」两个值 |
| `rollForwardVariance` | 上一条的差额列，随之失去意义（期末的对账对象是**试算余额** `tbClosing`） |
| `rollForwardBalanced` | 同上；滚动自洽由模板公式 J 保证，不需要再校验一遍 |

连带的 UI 改动：

* 期末余额 J 由录入列改为**只读公式格**；
* 「推算期末」按钮删除（J 恒由公式算，按钮无意义）；
* 「写入期末」按钮改为「**按试算倒推期初**」—— 原按钮往 J 写值会被 `enrichRow` 立刻重算
  覆盖（**无效按钮**）。新语义：在四项变动已录的前提下，令期末等于试算期末所需的期初
  （`期初 = 试算期末 − 计提 + 转回 + 转销`），供审计人员核对期初是否录错；
* 「滚动不平衡」提示删除（J 恒自洽，不可能不平衡）。

落库只存**可编辑列**（B/C/F/G/H/I/M）+ 行身份 —— 公式列（D/J/K/L）与 A/E（由
`G14_LINE_ITEMS` 按 `rowKey` 派生）都不入 store，避免双源。

---

## 5. 验证

| 判据 | 结果 |
|---|---|
| `test_g14_column_isomorphism.py`（新建） | **57 passed** |
| G14 前端 11 个 spec（含改写的 11 条旧判据） | **92 passed / 0 failed** |
| 六 lane 判据文件 | 19 failed → **16 failed**（G14 三条转绿） |
| `vue-tsc -p tsconfig._g14.json`（新建窄配置） | 15 error 全为既存，G14 相关**零条** |
| 零回归门逐 provider 现算 | 16 家里 15 家算出三个 digest，唯一 FAIL 仍是 f1 |
| 文件行数门禁 | 全过 |

### 5.1 顺带修掉的判据缺陷（触类旁通）

`test_g_single_region_p9_p12` 的布尔列判据扫 `vars(entry_module)` 找 `RowTableSheetSpec`
—— 但交付形态是「entry 层 + sheet 层」两个模块，spec 在 sheet 层 ⇒ **形态正确时会假红**。
改为走 entry 层公开接口 `managed_row_table_specs()`（带 `vars()` 回退，兼容未来可能的单模块形态）。

### 5.2 whitelist 基线更新的正当性

`delivered_contracts_ledger.py` 1360 → 1637。该文件的 whitelist 注释本来就论证了
「按设计 append-only、**不可再拆**」（按循环切分会让「谁已交付」散到十几个文件，而判据
`test_contract_directory_matches_the_delivery_ledger` 要的正是一张可双向比对的完整表）。
⇒ 这是本 whitelist 里唯一「变大是设计意图」的条目，「打磨应让文件变小」对它不成立。
已在注释里写明该例外 + 判据面不放松。

### 5.3 本轮踩过的两个坑（已固化进代码注释）

1. **resync 脚本的固定行集分支**：G14 没有铸造点（行集由常量固定），我最初把
   `row_identity_generator_source` 改指 `g14Constants.ts`（行集常量声明处）—— 判据
   `test_row_identity_key_and_generator_are_source_backed` 要在**同一个文件**里同时回源
   「`rowKey: string` 的行模型声明」与「`createDefaultRows` 的构造点」，指向常量文件会让
   后者找不到。正解：仍指消费方 composable 里的 `createDefaultRows`。
2. **窄配置首次暴露既存类型错**：新建 `tsconfig._g14.json` 后
   `migrateReversalToPositive(raw.currentReversal)` 报 `number | undefined` —— 这是既存
   错误（`raw` 是 `Partial`），只是从未被检出。顺手修成 `migrateReversalToPositive(parseNum(...))`。

---

## 6. 后续 lane 可复用的结论

1. **固定行集的 entry 必须先核「前端行集 == 模板行集」**。行表引擎按数组顺序映射，多一行
   就扩行挤 footer。核的是**逐项 label**，不是行数（G14 的 `rfin` 就是行数对但文字错）。
2. 删一个「看起来只是多余」的行/列之前，先按值 grep 它的**跨循环**消费方。G14 的 `ca`
   牵着 D6→G14 的 ECL 取数链、上市/国企两套披露、调整分录 rowKey 推断共五条链。
3. 「同一张表里两个公式对同一列的符号约定矛盾」= 必有一处模板缺陷。判据要**同时**钉住
   「模板现状」（逐格比对，防漂移）与「前端按正确口径算」（按值断言函数是减法）。
4. 判据扫 `vars(module)` 找声明对象是脆的 —— 交付形态是多模块时会假红。优先走 provider
   的**公开接口**取。
5. append-only 台账的 whitelist 基线该随交付增长；但要在注释里论证「不可再拆」并声明
   判据面不放松，否则就是给膨胀开后门。
