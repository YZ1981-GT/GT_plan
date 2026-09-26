# Task 2 证据：F2 四册形态判定 + 几何逐格实测

**实测工具**：`_probe_f2_four_volumes.py` + `_f2_uuid_cols.py` + context-gatherer grep
**实测日期**：2026-09-26

## 1. main 册（20 sheets）

### canary F2-6（四、自制半成品明细表）

| 属性 | 值 |
|---|---|
| dims | 30r × U |
| header | R6 组表头 / R7 叶子表头 |
| data | R9-R24（16行） |
| footer | R25，标记 **A25**="合计" |
| formula_in_data | F,I,L,N,O,P（6列：单价=IF(qty=0,0,amt/qty), 期末数量=E+H-K, 期末金额=G+J-M） |
| footer_only_formula | G,J,M,Q,R,S,T（SUM 列 + 账龄 SUM） |
| UUID 列 | V（首个全空列） |
| store_item_id | `F2-6-rows`（模板化 `${sheetCode}-rows`） |
| row_identity_key | `id`（🔴 非 rowId） |
| binding_kind | `excel_table`（动态行表） |

### F2-3（一、原材料明细表）—— footer B 列差异

| 属性 | 值 |
|---|---|
| dims | 31r × U |
| data | R9-R24 |
| footer | R25，标记 **B25**="合计"（🔴 A 列无值） |
| formula_in_data | 同 F2-6 |
| UUID 列 | V |

**裁决**：框架层 `search_column` 硬编码 `"A"`（`phase5_row_table_sheet.py:309`）。
F2-3 需要在 `RowTableSheetSpec` 上新增 `footer_search_column: str = "A"` 字段，
或暂不受管并登记。其余明细表（F2-4/6/8/9）footer 均在 A 列，不受影响。

### F2-4（二、材料采购、在途物资明细表）

| 属性 | 值 |
|---|---|
| dims | 30r × W |
| data | R9-R24 |
| footer | A25="合计" |
| formula_in_data | E,H,K,M,N,O,Q（列号偏移，三联结构列起点不同） |
| UUID 列 | X |

### F2-7（五、委托加工物资明细表）

| 属性 | 值 |
|---|---|
| dims | 287r × O |
| data | R8-R16（9行） |
| footer | A17="合计" |
| formula_in_data | G（=E*F） |
| UUID 列 | P（B 列空但在数据区内，不取） |
| 特殊 | 287 行是 max_row 但绝大部分空（实际内容 ~30 行） |

### F2-8（六、库存商品明细表）

| 属性 | 值 |
|---|---|
| dims | 36r × X |
| data | R9-R24 |
| footer | A25="合计" |
| formula_in_data | 同 F2-6 + 在手订单列（V/W/X） |
| UUID 列 | Y |

### F2-9（七、发出商品）

| 属性 | 值 |
|---|---|
| dims | 36r × W |
| data | R9-R24 |
| footer | A25="合计" |
| formula_in_data | 列号偏移，三联起点与 F2-4 同形态 |
| UUID 列 | X |

### F2-12（十、合同履约成本）

| 属性 | 值 |
|---|---|
| dims | 25r × P |
| data | R8-R19 |
| footer | A20="合计" |
| formula_in_data | F,G,H,I,J,K,L,M |
| UUID 列 | Q |
| store_item_id | `F2-12-rows` |
| row_identity_key | `id`（🔴 loadRows 有 `r.id \|\| String(i+1)` 回退 = BP-7 同型） |

## 2. stocktake 册（9 sheets）

### F2-25（抽盘结果汇总表）—— 双区

| 属性 | 区一（账→实） | 区二（实→账） |
|---|---|---|
| 表头 | R14/R15 | R29/R30 |
| data | R16-R26 | R31-R41 |
| footer | A27="合计" | A42="合计" |
| formula_in_data | J,K,L | J,K,L（同列结构） |
| store_item_id | `F2-25-rows` | `F2-25-floor-rows` |
| UUID 列 | Q（两区共用） |

### F2-26（盘点倒轧表）—— 双区无 footer

| 属性 | 区一（日后） | 区二（日前） |
|---|---|---|
| 表头 | R7 | R16 |
| data | R8-R14 | R17-R23 |
| footer | **无合计行** | **无合计行** |
| 锚行 | R15（区二标题行） | R24（审计说明行） |
| formula_in_data | J,L,M | J,L,M |
| store_item_id | `F2-26-after-rows` 🔴 | `F2-26-rows` 🔴 |
| UUID 列 | P（两区共用） |

🔴 **键名陷阱已确认**：`F2-26-rows` = 日前区（区二），`F2-26-after-rows` = 日后区（区一）。
🔴 **F2-26!J9 模板缺陷已确认**：J9=J2+H9-I9（J2 在标题合并区内），同列其余行均为 G{r}+H{r}-I{r}。

### F2-24 —— HTML-only

两区无表头、无承载列（R5/R14 仅标题 + 提示文字），`F2-24-rows` / `F2-24-count-rows` 判 HTML-only。
原因：模板无对应表格区，在线编辑不回写。

### F2-21 —— 问卷形态核

问卷型（fields + rows + note），候选 `static_region`，不属本 spec 行表形态。

## 3. valuation 册（6 sheets）

### F2-48（长库龄 呆滞 超过保质期存货明细表）—— canary V

| 属性 | 值 |
|---|---|
| dims | 22r × N |
| 表头 | R5/R6（两级） |
| data | R7-R16 |
| footer | A17="合计" |
| formula_in_data | H（=F*G） |
| store_item_id | `F2-48-rows`·`products` |
| store_kind | dict（`{products: [...]}`) |
| row_identity_key | `id`（f2imp-… 前缀） |
| UUID 列 | O |

### F2-49（跌价转回）

| 属性 | 值 |
|---|---|
| dims | 36r × X |
| data | R7-R15 |
| footer | A16="合计" |
| formula_in_data | T,X（T=O/F*N, X=U+V+W-T） |
| store_item_id | `F2-49-rows`·`products` |
| UUID 列 | Y |

### F2-47（跌价准备测试表）—— FC-10 命中

| 属性 | 值 |
|---|---|
| dims | 56r × AB |
| 表头 | R18/R19（两级） |
| data | R20-R29 |
| footer | A30="合计" |
| formula_in_data | G,Q,T,U,V,W,X,Z（8列） |
| store_item_id | `F2-47-rows`·`products` |
| UUID 列 | AC |
| 🔴 FC-10 | N 列「销售费用率」/ O 列「税率」前端存百分数，模板参与 T=N*Q 期望小数 |

## 4. special 册（7 sheets）

### F2-57（合同履约成本减值准备测算表）—— canary P

| 属性 | 值 |
|---|---|
| dims | 27r × N |
| 表头 | R5（单级） |
| data | R6-R17 |
| footer | A18="合计" |
| formula_in_data | E,H,I,J,L（5列） |
| store_item_id | `F2-57-rows`·`products` |
| UUID 列 | O |

### F2-58（亏损合同预计损失测算表）

| 属性 | 值 |
|---|---|
| dims | 25r × O |
| 表头 | R5（R6 公式说明行） |
| data | R7-R20 |
| footer | A21="合计" |
| formula_in_data | F,G,H,J（4列） |
| store_item_id | `F2-58-rows`·`products` |
| UUID 列 | P |
| FC-10 | **不命中**（completionRate 存 0~1，模板小数口径一致） |

### F2-55（合同履约成本构成明细表）

| 属性 | 值 |
|---|---|
| dims | 40r × AK |
| 表头 | R5/R6（两级，R6 含 6 个"小计"组标题） |
| data | R7-R24 |
| footer | A25="合计 "（尾含空格） |
| 🔴 footer SUM | `SUM(D6:D24)` 起于 R6（表头叶子行）而非 R7 |
| formula_in_data | 33列（D~AJ 几乎全列公式） |
| store_item_id | `F2-55-rows`·`products` |
| UUID 列 | AL |

### F2-56（合同履约成本检查表）

| 属性 | 值 |
|---|---|
| dims | 37r × W |
| 表头 | R15/R16（两级） |
| data | R17-R31 |
| footer | A32="合计" |
| formula_in_data | D,E,F,G,K,S（6列） |
| store_item_id | `F2-56-rows`·`samples` |
| UUID 列 | X |
| 🔴 id 缺陷 | `fillFromSampling` 用 `` `${Date.now()}-${i}` ``（时间戳+索引，非稳定身份） |

## 5. IPO 门控确认

`GtF2InventorySpecial.vue` 的 `CONTRACT_HTML = ['F2-55A','F2-55','F2-56','F2-57','F2-58']`
与 `IPO_HTML = ['F2-61A','F2-61',...,'F2-72']` 明确分离。
`isIpoSheet` 仅查 `IPO_HTML`，F2-55~58 不受 IPO 门控影响。

## 6. BP-7 行身份退化汇总

| composable | 位置 | 形式 | 严重度 |
|---|---|---|---|
| useF2DetailSheet.loadRows | L235 | `String(r.id \|\| i+1)` | 🔴 真库已发生 |
| useF2DetailOutsourced | L176 | 同上 | 🔴 |
| useF2DetailTurnover | L263 | 同上 | 🔴 |
| useF2BioAssetSheet | L219 | 同上 | 🔴 |
| useF2ContractPerfSheet | L155 | `r.id \|\| String(i+1)` | 🔴 |
| useF2DevCostSheet | L165 | 同上 | 🔴 |
| useF2DevProductSheet | L211 | 同上 | 🔴 |
| useF2ContractCostCheck.fillFromSampling | L252 | `` `${Date.now()}-${i}` `` | 🟡 时间戳+索引 |
