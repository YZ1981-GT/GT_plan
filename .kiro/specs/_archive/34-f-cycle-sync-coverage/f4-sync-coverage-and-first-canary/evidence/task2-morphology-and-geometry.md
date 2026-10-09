# Task 2：形态判定 + 几何逐格实测（F4）

**执行**：2026-09-26　`uuid_col` 共同缺陷的完整说明见
`.kiro/specs/f3-sync-coverage-and-first-canary/evidence/task2-morphology-and-geometry.md` §一。

模板：`F/F4 应付账款.xlsx`　**sha256 `e20e62725c209b716eab4977231f21c627ab92346a72b58c20acdc7a6f1711fd`**
（108,329 B，15 sheets）—— 与 spec 记载逐字一致。

## 🔴 一、`uuid_col` 逐区分配（spec design 的同列声明不可用）

| sheet | 区数 | max_col | 全空列 | 分配 | 备注 |
|---|---|---|---|---|---|
| F4-7 未入账检查表 | **5** | M(13) | 10（L~U） | **L / M / N / O / P** | 🔴 N/O/P 超出 max_col ⇒ instrumentation 需扩列（同 F5-8 的 I 列情形） |
| F4-8 应付账款检查表 | 2 | R(18) | 8（S~Z） | **S / T** | 皆超 max_col，需扩列 |
| F4-1 审定表 | 2 | L(12) | 8（M~T） | **M / N** | 皆超 max_col，需扩列 |

spec design 原写 F4-7 五区全 **L**、F4-8 双区全 **S**、F4-1 两区全 **M** ⇒ 三处都会让
`spec_to_contract_sheet_payload` 的兄弟区配对匹配 0 张并抛 `ProviderCapabilityError`。
provider 的 `build_contract_payload()` 已加重复检测，声明错会**在生成契约时就抛**。

## 二、canary：`关联方及交易检查表F4-6`（已声明并验通）

| 项 | 实测 | 与 spec |
|---|---|---|
| 尺寸 | 25r × **15c（O）** | 🔴 spec 写「25r×Q」，实测 max_col=O；不影响声明（受管止于 L） |
| 公式总数 | **17** = 7 页眉 + 5 数据行（F7..F11）+ 5 footer | ✅ |
| 表头 | **单级 R6**，12 列 A-L | ✅ |
| 数据区 | **R7-11**（5 行） | ✅ |
| footer | **R12**，A12 = `'合计'` | ✅ |
| UUID 列 | 全空列 M~S ⇒ 取 **M** | ✅ |
| `formula_columns` | **`("F",)`** | ✅ |

表头逐列：`A 关联方名称 · B 关联关系 · C 期初余额 · D 本期借方 · E 本期贷方 · F 期末余额(公式) ·
G 账龄 · H 定价政策 · I 发生原因（款项性质） · J 期后付款金额 · K 索引号 · L 备注`

### 🔴 公式是负债类方向，与 F1-6 镜像

逐格实测 F7..F11 全部为 `=C{r}+E{r}-D{r}`（期初 + **贷方** − **借方**）。
F1-6 是 `=C{r}+D{r}-E{r}`（资产类，借方在前）。**同型不等于同式**（FC-4）——
判据 `TestProperty4TriadAndMirroredFormula::test_formula_is_liability_direction_not_asset`
直接断言「不得等于 F1-6 的式子」，并逐格比对模板五行。

### FC-10 逐格取证：F4 canary **零命中**

`关联方及交易检查表F4-6` 全表（不只数据区）`number_format` 含 `%` 的格数 = **0**。
⇒ 需求 7.6 的「F4 不需要 FC-10 前置」结论**有实测支撑**，不是「以为不命中」。
判据 `TestProperty16Fc10NotApplicable::test_canary_sheet_has_zero_percent_format_cells` 守住。

### 🔴 新发现模板缺陷：数据验证悬空引用

| 区间 | `formula1` | 判定 |
|---|---|---|
| `B7` | `$B$18:$B$25` | ✅ 正确 —— footer 之下的「勿改、勿删」关联方类型源（实际控制人 / 控股股东 / 控股股东、实际控制人的附属企业 / 持有5%以上股份的法人或其他组织 / 联营企业 / 合营企业 / 董高监等关键管理人员 / 其他关联方，共 8 项） |
| `B8:B11` | **`$N$7:$N$14`** | 🔴 **N 列全空**（逐格实测非空计数 0）⇒ R8-R11 四行的关联关系下拉是**空列表** |

即模板只给第一个数据行配了可用下拉。与 F5-7!G31 引越界空区同型（引用一片不存在的数据）。
**不改模板字节**（`backend/wp_templates/` 运行时只读 + sha 冻结），登记在
`phase5_f4_06_related_party.TEMPLATE_DEFECT_F406`，判据
`test_template_defect_is_real` 逐格证明它属实（N7:N14 全 None）。

受管不受影响：UUID 列取 M 不碰 N 列。

## 三、多区几何（逐格实测，待 Task 13/14/19 声明）

### F4-7 五区（101r × 13c，max_col=M）

| 区 | 标题行 | 表头 | 数据区 | footer | footer SUM 列 | uuid_col |
|---|---|---|---|---|---|---|
| ① 期后付款是否在平均付款天数内 | R13 | R14（单级） | **R15-24** | R25 | C,D,E,F,H,I | L |
| ② 料到单未到——存货暂估入库 | R26 | R27/R28 | **R29-44** | R45 | F, I | M |
| ③ 截止审计现场结束日未处理的供应商发票 | R46 | R47/R48 | **R49-59** | R60 | F, I | N |
| ④ 应付账款期后付款核对 | R61 | R62/R63 | **R64-75** | R76 | F, I | O |
| ⑤ 应付账款期后增加额核对 | R77 | R78/R79 | **R80-91** | R92 | F, I | P |

与 spec requirements 的五区表**行号逐项一致**（R15-24 / R29-44 / R49-59 / R64-75 / R80-91 ✅）。
spec Notes 里「探针摘要的四个 footer 是 `--max-rows` 截断所致，逐行实测为五区」也得到确认 ——
本次实测五个 footer（R25/R45/R60/R76/R92）齐全。

🔴 区① 的 footer SUM 列集（C,D,E,F,H,I 六列）与区②~⑤（F,I 两列）显著不同 ⇒
区① 是单级表头 11 列、其余两级 ⇒ 五份独立 `field_specs`（裁决 F4-H3）得到实测支持。

### F4-8 双区（68r × 18c，max_col=R）

| 区 | 标题行 | 表头 | 数据区 | footer | footer SUM 列 | uuid_col |
|---|---|---|---|---|---|---|
| ① 本期借方金额检查 | R14 | R15/R16 | **R17-37** | R38 | G, L, **O** | S |
| ② 本期贷方金额检查（可结合 F2-33） | R39 | R40/R41 | **R42-57** | R58 | G, **N** | T |

与 spec 一致（R17-37 / R42-57 ✅）。
🔴 **两区列集确实不同**（区① SUM 到 O 列、区② 到 N 列）⇒ 需求 4.2 的「按 Task 2 逐格实测
（不假设相同）」结论落实：两区必须各自声明。

### F4-1 审定表两区（30r × 12c，max_col=L）

| 区 | 标题行 | 表头 | 数据区 | footer | uuid_col |
|---|---|---|---|---|---|
| 性质区 | R5「一、按照性质分类」 | R6 | **R8-12**（5 行：货款/工程款/设备款/服务费/其他） | R13「合计」`SUM(B8:B12)` | M |
| 账龄区 | R14「二、按照账龄分类」 | R15 | **R17-21** | R22「合计」`SUM(B17:B21)` | N |

其后：R23 试算平衡表数 · R24 差异数 · R25「三、审计说明：」· R30「四、审计结论：」。

🔴 **账龄区 R21 是空槽行**：账龄标签只有 4 个（R17 1年以内（含1年）/ R18 1至2年（含2年）/
R19 2至3年（含3年）/ R20 3年以上），而 footer 的 SUM 覆盖 **R17-21 五行** ⇒ R21 无标签。

这与 **F3-1 的 R9/R10 空槽行同型**，正是裁决 **F3-H4「mask 是行级不是矩形」**的场景：
若账龄区按单个 spec 声明且 `formula_columns` 取 R17-20 的列集，R21 的那些列会被矩形
`formula_mask` 误标 formula（实际可编辑）⇒ 用户在 OO 里填 R21 会被判受保护冲突。
⇒ Task 19 须先实测 R17-20 与 R21 的公式集合是否不同；不同则按 F3-H4 拆两个 spec
（`f41-aging-seed` R17-20 / `f41-aging-slot` R21），此时 uuid_col 需从 M/N 扩到三个。

两区小计的 SUM 都覆盖 B~J 九列（B,C,D,E,F,G,H,I,J）。

## 四、前端三元组实证（canary）

| 维度 | 实测 |
|---|---|
| store 键 | `F4-6-rows`（`useF4RelatedParty.ts` 的 `STORAGE_KEY`）；同文件另有 `DETAIL_KEY='F4-2-rows'`（读明细对账）与 `LEGACY_NOTE_KEY='F4-6-note'` |
| 增删行 | `addRow` / `removeRow` 各 1 |
| 行身份 | **`rowId`**（`RelatedPartyAPRow.rowId`） |
| 判定 | `excel_table` + `rowId` + `StoreKind.rows` |

store-only 字段（已在声明层登记）：`seq` · `sourceRowId` · `linked` ·
`sourceClosingBalance` · `reconciliationDifference` · `concentration` · `riskFlags` · `riskLevel`。

零写入读键（需求 2.4 / Property 18，已登记不修）：`F4-8-debit-note` · `F4-8-credit-note`
（`phase5_f4_accounts_payable.ZERO_WRITER_READ_KEYS`，判据断言它们不在 `all_store_item_ids()`）。

## 五、其余 sheet 的实测策略

F4-5 / F4-2 / F4-9 / F4-4 / F4-3 的逐格几何在各自声明任务中随实测随声明。
本文件已覆盖阻塞面：canary 全量 + 三张多区 sheet 的 `uuid_col` 可行性与区界。
