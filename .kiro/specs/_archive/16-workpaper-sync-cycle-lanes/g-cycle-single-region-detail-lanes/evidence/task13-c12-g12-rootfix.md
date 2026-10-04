# Task 13 / C-12：G12 净敞口套期收益接入双向回写

commit `72cb62721`（12 文件，+2049 / −21）+ 三个共享台账被并发 commit `bb8c0eb70` 带走
（`store_item_registry.py` / `adapters/delivered_contracts_ledger.py` / `adapters/registry.py`，
G12 条目逐项核完整、`git status` 已 clean）。九条 lane 的**第七条**。

## 一句话结论

G12-2 是九条里模板质量最差的一家：**`formula_columns` 为空**（没有一列在数据区每行都有
公式）+ **五处模板缺陷**（一处是数值错）+ footer 的 shared 组被打断 + 有效列少于
`max_column`。spec 原文的「无表头行」前提早在 Task 2 就被推翻。

## 模板实测（`backend/wp_templates/G/G12 净敞口套期收益.xlsx`）

* 79,999 B · sha256 `6645caf0fdfadf38b5cc5919d8b4bc60e59dda7bda54747085a40bdf4b66a8f8`
  · **11** sheets · **0 definedName**（与 slice 的 `authoritative_templates` 逐字一致）
* 受管 sheet `明细表G12-2`：`max_row=25` / **`max_column=15`** / merged 9 个
* **两级表头 R7/R8**：
  * 🔴 横向组**只有一个** `D7:G7`（套期工具公允价值）
  * 纵向合并六列 `A7:A8` `B7:B8` `C7:C8` `H7:H8` `I7:I8` `J7:J8`
  * `R5` 是审计目标、`R6` 是段标题「二、审计过程：」只占 `A6`
* 数据区 **R9-R13（5 行）**：🔴 **只有 R9/R10 有预填**（R9 是 FV 分配行、R10 是摊销行），
  R11-R13 整行全空（样式预留）。`last_data_row=13` 的依据是 footer 的 SUM 区间 `x9:x13`
  —— 模板自己把数据区画到 R13
* footer **R14**「合计」/ `R15` 是「三、审计说明：」+ `E15`「四、审计结论：」
* 🔴 有效内容列 **10**（A..J）**小于** `max_column=15`（5 个空尾列）⇒ `uuid_col="K"`
  （按**有效列**右移一列，GC-3 口径；取 `P` 会把 5 个空列圈进受管区）。
  九条里第二家出现这种情况（另一家是 G8 的 23/24）
* 🔴 **整册裸 IF 7 格，受管 sheet 命中 0 格** ⇒ 中性化不动本表

### 表头逐格

| 行 | A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|---|
| R7 | 项目 | 净头寸 | 套期工具 | 套期工具公允价值（组 D7:G7） | — | — | — | 套期调整摊销（计入净敞口套期损益） | 净敞口套期损益 | 索引号 |
| R8 | — | — | — | 套期工具累计公允价值变动 | 对应预期销售的部分（计入净敞口套期损益） | 对应预期采购的部分（套期调整） | 校验 | — | — | — |

### 数据区公式分布（XML 逐格）

```
A 0 · B 0 · C 0 · D 0 · E 0 · F 0 · G **1**（只 R9）· H 0 · I **2**（只 R9/R10）· J 0
```

`G9 = =D9=SUM(E9:F9)`（布尔校验）· `I9 = =E9+H9` · `I10 = =E10+H10`。三格都是**普通公式**，
不是 shared 主格。

## 🔴 裁决一：spec 的「无表头行」前提不成立

spec 原文说 G12-2「无表头行（R9 即数据）」并据此立了裁决 G1R-H2（要框架层加
`has_header_row`）。Task 2 实测：R7/R8 是两级表头、R9 起才是数据（整册比别家上移两行）。

⇒ 框架层**无需改**，本 lane 走通例分支（`header_group_row=7` / `header_leaf_row=8`），
Task 0 §1.1 登记的缺口对 G12 不适用。判据
`test_header_is_two_level_at_r7_r8_not_absent` 把这件事钉成可执行事实。

## 🔴 裁决二：`formula_columns` 为空，`G`/`I` 判 `editable` 并让前端落库

| 候选 | 后果 |
|---|---|
| `G`/`I` 判 `formula` | `G10:G13` 四格 + `I11:I13` 三格无公式 ⇒ `ProtectedRegionWriteError` |
| 两列**不受管** | 按「派生校验 vs 第二真源」本该如此（前端 `rowCalcs` 能算），**但 R11-R13 那两列在 Excel 里会永远是空格**（模板缺 fill-down、后端又不写）⇒ 用户新增的第 3 行看不到校验与净敞口套期损益 |
| **`editable` + 前端派生值落库** ✅ | 三格模板公式在 materialize 后变字面量（与 G13 父行同型） |

⇒ `G12HedgeDetailRow` 新增 `fvCheck: boolean` + `netHedgePnl: number`：

* **单一真源仍是** `g12NetHedgeDetailCalc` 的 `calcFvAllocationCheck` / `calcNetHedgePnl`
  （在 `enrich()` 里现算，不在别处重写口径）
* `rowCalcs` 改为从行模型读（`fvCheckOk: r.fvCheck`），**对外字段名不变** ⇒ 消费方
  `G12TabHedgeDetail.vue` 的 `rowCalcMap` 零改动
* `persist()` 落库这两列
* 🔴 字段在接口里的**位置就是模板列序**（`fvCheck`(G) 在 `hedgeAdjAmortization`(H) 之前）——
  首版加在末尾，被判据 `test_frontend_field_order_matches_excel_column_order` 打红后挪正

与 G13 的 B/C **同型但结论不同的那一步**：G13 的 B/C 是核心业务列（未审数/调整数）必须受管；
G12 的 G/I 是派生量，「不受管」在字段语义上更干净，但会造成 Excel 侧空格 ⇒ 落库更完整。

## 🔴 五处模板缺陷

| # | 位置 | 缺陷 | 应有形态 |
|---|---|---|---|
| ① | `B14` | `=SUM(B9,B12,B13:B13)` **漏加 B10/B11** —— 数值错 | `=SUM(B9:B13)` |
| ② | `I14` | `=SUM(I7:I13)` 起点越到**表头组行 R7** | `=SUM(I9:I13)` |
| ③ | `G10:G13` | `G` 列公式只填 R9（fill-down 缺失） | 每行 `=D{r}=SUM(E{r}:F{r})`；本轮由 `fvCheck` 落库补齐 |
| ④ | `I11:I13` | `I` 列公式只填 R9/R10 | 每行 `=E{r}+H{r}`；本轮由 `netHedgePnl` 落库补齐 |
| ⑤ | `H14` | footer 漏 H 列合计（B/C/D/E/F/G/I/J 八列都有） | `=SUM(H9:H13)` |

①② 是 Task 2 的发现 G；③④⑤ 本轮新发现。一律逐字记原式落
`TEMPLATE_ROW_FORMULAS_G1202` / `TEMPLATE_FOOTER_FORMULAS_G1202` /
`TEMPLATE_FORMULA_COVERAGE_DEFECTS_G1202`，判据按格比对；**不改模板字节**。

⑤ 是真缺陷而非「本列不该有合计」：`H10 = -240000` 有值，判据
`test_defect_5_footer_misses_the_h_column_total` 一并断言这一点。

## 🔴 footer 的 shared 组被打断

```
B14/C14/D14/E14  plain <f>SUM(x9:x13)</f>
F14              **shared 主格** ref=F14:J14，body=SUM(F9:F13)
G14/J14          shared 成员格（si 同 F14）
H14              🔴 **无公式**（缺陷⑤）
I14              plain <f>SUM(I7:I13)</f>（缺陷②）
```

组 ref 覆盖 F..J 五列，实际成员只有 `G14`/`J14` 两格。
⇒ 按「组 ref 覆盖的列都是成员」去验会有两格假红；按「footer 全列同形态」去验会在 `H14`
与 `I14` 各打一次红。`footer_carries_total_formula=True` 成立，但 roundtrip 判据不得假设
全列同形态。

## 修了两条判据自身

### ① P9 从写死改为按模板覆盖率现算

`test_boolean_column_declared_as_formula_and_boolean_type` 首版写死「三处布尔列都必须
`mode=formula`」。G12 实测推翻其中一处 ⇒ 改名
`test_boolean_column_declared_as_boolean_with_mode_from_template_coverage`，逻辑改为：

```
读模板 → 算该列在数据区的公式覆盖率
  每行都有 ⇒ 断言 mode == "formula"（G13!K / G14!L）
  部分行有 ⇒ 断言 mode == "editable" **且 provider 必须有覆盖缺陷台账**
value_type == "boolean" 三条一律不变
```

🔴 关键是后半句：降级成 `editable` 的那一条必须把「模板缺了哪几格」登记出来，否则
「判据放宽」与「真实缺陷」就分不清了。判据会现算缺失的行号并在台账里找它。

### ② P10 的 G12 docstring 判据首版只扫 entry 层

`test_g12_provider_records_the_template_defects_in_its_docstring` 查两个公式字面量是否出现在
docstring 里，但只扫 `phase5_g12_net_hedge_gains`（entry 层）⇒ 交付后**假红**：本 spec 九条
一律「entry 层 + sheet 层」两模块，**列模型细节（含缺陷台账）归 sheet 层**。

改为扫两个模块 docstring 的**并集** + 结构化缺陷台账常量，并断言台账**至少**覆盖五处
（`len(defects) >= 5` + 位置集合 ⊇ `{B14, I14, H14}` + G/I 两列的覆盖缺失各一条）。

> 这是第二次同类修正（G11 那轮是 `vars(mod)` 扫不到 spec 对象）⇒ **凡判据要从 provider 取
> 东西，先确认它在 entry 层还是 sheet 层**；取不到就扫两个模块的并集，不要假设单模块。

## 🔴 踩坑登记：resync 必须是前端改动的最后一步

时间线：
1. 改前端（加 `fvCheck`/`netHedgePnl`）
2. 跑 `resync --apply` ⇒ 写入点 `#L138 → #L172`
3. **又改前端**（按模板列序把 `fvCheck` 挪到 `hedgeAdjAmortization` 前面，+3 行）
4. `test_payload_column_mode_is_declared_and_matches_the_write_site` 打红 ——
   slice 里的 `#L172` 现在指 `}, { immediate: true })`（watch 的结尾），而
   `debouncedSave` 已经到了 `#L175`
5. 重跑 `resync --apply` ⇒ `#L172 → #L175` / `#L59 → #L62`，红消

⇒ 固化为规矩：**resync 放在前端最后一次改动之后**，且 commit 前必跑 `--check`（本轮
`--check` 返回「无需改动」才提交）。

## resync 新增第二口径

`dynamic_row_identity.…row_identity.source_ref` 的冻结值口径在各 lane 不统一：

| entry | 冻结值 | 声明行 | return 行 | 判断 |
|---|---|---|---|---|
| G11 | `#L71` | `#L71` | `#L72` | 声明行口径 ⇒ `TABLE_TO_ENTRY` |
| G13 | `#L65`（改动前） | `#L84` | `#L85` | 声明行口径 ⇒ `TABLE_TO_ENTRY` |
| **G12** | `#L40`（改动前） | `#L39` | **`#L40`** | **return 行口径** ⇒ 新增 `TABLE_TO_ENTRY_RETURN_LINE` |
| G8/G9/G10/G14 | `#L76`/`#L82`/`#L109`/`#L61` | 差 40~120 行 | 同 | 两种口径都对不上 ⇒ 仍然排除 |

⇒ 混在同一组会把其中一组改错一行。两个白名单各自现算各自的口径。

## 验证

| 门 | 结果 |
|---|---|
| `test_g12_column_isomorphism.py` | **57 passed**（五层闭环） |
| 六 lane 判据（13 文件） | 10 → **6 failed / 676 passed**（G12 四条转绿） |
| 零回归门逐 provider 现算 | 19 家 **18** 家出 digest；g12 `contract=05e9567142a7` / `projection=256747815306` |
| 契约双向锁 | `--apply` 后 recheck OK（`canonical_digest=05e9567142a7…`） |
| `resync --check` | 无待改 |
| 行数门禁（10 暂存文件，pre-commit 真跑） | 绿 |
| 前端 G12 16 spec / 142 tests | **141 passed / 1 failed**（唯一红是既存，见下） |

### 剩余 6 条红的归属（全非本 lane）

* G3/G1 各 2 条（provider 未交付 + store merge 未注册）= 4 → Task 14
* P18 两条（九条 adapter 全进 digest / 九条契约全发布）→ Task 15

### 前端唯一红是既存失败（三条证据）

`g12NoteSubtableContract.spec.ts` 的「P1 listed main → 『净敞口套期收益』存在于 五、40」：

1. 该 spec **零引用**本轮改动的任何符号（grep `useG12HedgeDetail` / `fvCheck` /
   `netHedgePnl` / `hedge-detail` 全无命中）
2. 最后一次改动是 **2026-07-30** commit `a2a4feb2d`（附注子表契约守卫），不在本轮
3. 工作树里该文件**未被修改**（`git status` 无它）

⇒ 属附注披露子表契约链（`note_template` 子表名与模板 tab 名的比对），登记不修。

### 未做的事（如实登记）

* **未修 `H14` 等五处模板缺陷的字节** —— `backend/wp_templates/` 运行时只读 + sha 冻结；
  会计正确口径由前端承担，缺陷进台账供后续「模板治理」立项
* **未给 G12 加前端骨架/固定行集** —— G12 的行模型本来就是动态明细（`G12_NET_HEDGE_DETAIL_SEED`
  只是默认种子行），与 G13 的「模板固定 10 行」情形不同，不需要 G13 那种载体改造
* **未做真实 OO 栈 / Playwright 实测** —— 需 `start-dev.bat` 环境，归 Task 15 收口
* **`adapter_registered=False`** —— 与 D/E/F/G 系列同一平台级缺口（umbrella BP-61-1）

## 一次性件已删

`_g12_probe.py` / `_g12_slice_probe.py` / `_gd_per_provider.py` / `_g12_entry_from_g13.py`
（共 26 个临时件含中间输出）。保留 `backend/scripts/check/_vt_report.py`。

## 给后续 lane 的可复用结论

1. **`formula_columns` 可以是空的** —— 「每行都有公式」是进该表的门槛，不满足就一列都不进。
   空 `formula_mask` 被 `parse_contract` 接受（本轮实证）
2. **「派生列该不该受管」要看 Excel 侧的后果**：按字段语义「派生就不声明」是对的，但如果
   模板对应列的公式覆盖不全，不声明 = Excel 侧永远空格。这时落库更完整，代价是丢几格公式
3. **前端字段的位置就是模板列序** —— 加字段别图方便加在末尾；判据逐位比对
4. **判据要从 provider 取东西时，先确认它在 entry 层还是 sheet 层**（第二次踩）⇒ 扫两模块并集
5. **判据把期望值写死 = 每条 lane 都要来手改一次**（第三次遇到）⇒ 改成从模板/台账现算，
   并对「降级」路径附加「必须登记缺陷」的约束，让「放宽」与「真缺陷」可区分
6. **resync 放在前端最后一次改动之后**，commit 前必跑 `--check`
7. **shared 组的 ref 区间 ≠ 实际成员集合**：中间可能夹着无公式格或独立公式格（G12 的
   `F14:J14` 五列只有两格是成员）⇒ 逐格读 XML，不要按 ref 推成员
