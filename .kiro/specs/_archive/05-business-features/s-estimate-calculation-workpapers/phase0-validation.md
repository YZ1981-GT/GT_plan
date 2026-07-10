# Phase0 双源核对：S3/S15/S20/S21 底稿公式与 sheet 落定

> 交叉验证来源：`analyze_s_category.py` + `dump_s_special_content.py` + `dump_s_calc_phase0_v2.py` + `wp_render_schema/generated/S15.yaml` + `wp_code_overrides.json`

## 1. S15 每股收益和净资产收益率

### 源模板信息

| 属性 | 值 |
|------|-----|
| 文件 | `S15 每股收益和净资产收益率.xlsx` |
| Sheet 数 | 6（含表头） |
| 当前 override | `"S15": "audit-sheet"` |
| 目标 override | `"S15": "s15-eps-roe"` |

### sheetName 分发表

| sheetName | 性质 | 尺寸 | 公式数 | 组件分发目标 |
|-----------|------|------|--------|-------------|
| 表头（请先填写） | 占位/参数 | 20×8 | 0 | skip（不分发） |
| 审计程序S15 | 审计程序 | 30×8 | 4 | `sheet-audit-program` |
| 审定表S15-1 | 审定表 | 9×8 | 4 | `sheet-adjudication` |
| 基本每股收益计算表S15-2 | 计算表 | 32×8 | 6 | `sheet-basic-eps` |
| 稀释每股收益计算表S15-3 | 计算表 | 32×8 | 4 | `sheet-diluted-eps` |
| 净资产收益率计算S15-4 | 计算表 | 60×11 | 29 | `sheet-roe` |

### 公式引擎 I/O 规格

#### useS15FormulaEngine — 基本每股收益（S15-2）

**输入（EpsInput）：**

| 变量 | 含义 | 来源行 |
|------|------|--------|
| a1 | 归母净利润 | row6 |
| a2 | 扣非归母净利润 | row7 |
| b0 | 期初股份总数 | row9 |
| b1 | 公积金转增/股票股利增加 | row10 |
| c1 | 发行新股增加股份数 | row13 |
| c2 | 新股下一月份起至期末月份数 | row14 |
| d1 | 债转股增加股份数 | row16 |
| d2 | 债转股下一月份起至期末月份数 | row17 |
| e1 | 回购股份数 | row19 |
| e2 | 回购下一月份起至期末月份数 | row20 |
| b4 | 并股数 | row21 |
| m0 | 报告期月份数 | row22 |

**核心公式（D8/F8）：**
```
加权平均股数 b = b0 + b1 + (c1×c2/m0 + d1×d2/m0) - (e1×e2/m0) - b4
```
Excel: `=D9+D10+D11-D18-D21` where D11=c1*c2/m0+d1*d2/m0, D18=e1*e2/m0

**输出：**
- `basicEps = a1 / b`（row23）
- `basicEpsEx = a2 / b`（row24）
- 配股调整后 EPS（row27-28, f = 配股调整后加权平均股数）

#### useS15FormulaEngine — 净资产收益率（S15-4）

**输入（RoeInput）：**

| 变量 | 含义 | 来源行 |
|------|------|--------|
| NP(C9) | 归母净利润 | row9 |
| C10 | 已确认为费用的稀释性潜在普通股利息 | row10 |
| C11=NP-C10 | 归属公司普通股股东净利润 | row11 |
| C12=C11-C13 | 扣非后归属 | row12 |
| C13 | 非经常性损益 | row13 |
| F15 | 所得税率 | row14 |
| E0(C15=D18) | 期初净资产 | row15 |
| C16 | 期末净资产 | row16 |
| C17 | 少数股东权益 | row17 |
| E(C18=C16-C17) | 归属公司普通股股东期末净资产 | row18 |
| M0(C19) | 报告期月份数 | row19 |
| Ei(C20) | 新发新股/债转股等新增净资产 | row20 |
| Mi(C21) | 新增净资产下月起至期末月份 | row21 |
| Ej(C22) | 回购/分红等减少净资产 | row22 |
| Mj(C23) | 减少净资产下月起至期末月份 | row23 |
| Ek(C24) | 其他交易/事项增减变动 | row24 |
| Mk(C25) | 其他增减下月起至期末月份 | row25 |

**核心公式（C26/D26）：**
```
加权平均净资产 = E0 + NP/2 + Ei×Mi/M0 - Ej×Mj/M0 + Ek×Mk/M0
```
Excel: `=C15+C11/2+C20*C21/C19-C22*C23/C19+C24*C25/C19`

**输出：**
- 全面摊薄 ROE = P / E → `=C11/$C$18`
- 加权平均 ROE = P / 加权平均净资产 → `=C11/$C$26`
- 基本 EPS = P / 加权平均股数 → `=C11/$C$36`
- 稀释 EPS = (P+(稀释利息-转换费用)×(1-税率)) / (加权平均股数+稀释股数×月份/M0) → `=(C11+(F11-F13)*(1-F15))/($C$36+F31*F32/C19)`

**加权平均股数（S15-4 row28-36）：**
```
b = S0 + S1 + Si×Mi/M0 - Sj×Mj/M0 - 并股
```
Excel: `=C28+C30+C31*C32/C19-C33*C34/C19-C35`

---

## 2. S20 营业收入扣除情况核查

### 源模板信息

| 属性 | 值 |
|------|-----|
| 文件 | `S20 营业收入扣除情况核查底稿202504.xlsx` |
| Sheet 数 | 1（单 sheet 多区段） |
| 尺寸 | 78×9，merged=94 |
| 当前 override | `"S20": "d-form-table"` |
| 目标 override | `"S20": "s20-revenue-deduction"` |

### sheetName 分发表

| sheetName | 性质 | 组件分发目标 |
|-----------|------|-------------|
| 营业收入扣除情况核查 | 单 sheet 多区段 | 主组件（无内部分发，单页呈现） |

### 区段结构

| 区段 | 行范围 | 内容 |
|------|--------|------|
| 区段1: 核查目标 | row5-6 | 方法论上下文（红字转琥珀块） |
| 区段2: 扣非净利润 | row8-12 | 判断适用条件 |
| 区段3: 营收扣除汇总 | row14-31 | **核心公式区** |
| 区段4: 与主营无关收入明细 | row34-50 | 动态明细行 |
| 区段5: 不具备商业实质收入明细 | row52-63 | 动态明细行 |
| 区段6: 其他核查事项 | row65-78 | 附加说明 |

### 公式引擎 I/O 规格

#### useS20FormulaEngine

**输入（RevenueDeductionInput）：**

| 变量 | 含义 | 公式 |
|------|------|------|
| 主营业务收入(C17) | 主营明细合计 | `=SUM(C18:C21)` |
| 其他业务收入(C22) | 其他明细合计 | `=SUM(C23:C26)` |
| 与主营无关收入(C28=C40) | 区段4合计引用 | `=C40` → `=SUM(C41:C46)` |
| 不具备商业实质收入(C29=C53) | 区段5合计引用 | `=C53` → `=SUM(C55:C59)` |

**核心公式链（22个）：**
```
营业收入 = 主营业务收入 + 其他业务收入
         = SUM(C17, C22) [C16]

扣除项目合计 = 与主营无关 + 不具备商业实质
            = SUM(C28:C29) [C27]

占比 = 扣除合计 / 营业收入 [C30 = C27/C16]

扣除后金额 = 营业收入 - 扣除合计 [C31 = C16-C27]
```

**输出（双列：本年/上年）：**
- `revenue` = C16 (本年), D16 (上年)
- `deductionTotal` = C27/D27
- `deductionRatio` = C30/D30
- `revenueAfterDeduction` = C31/D31

---

## 3. S21 数据资产

### 源模板信息

| 属性 | 值 |
|------|-----|
| 文件 | `S21 数据资产.xlsx` |
| Sheet 数 | 6（含表头） |
| 当前 override | `"S21": "d-form-table"` |
| 目标 override | `"S21": "s21-data-asset"` |

### sheetName 分发表

| sheetName | 性质 | 尺寸 | 公式数 | 组件分发目标 |
|-----------|------|------|--------|-------------|
| 表头（请先填写） | 占位 | 20×7 | 0 | skip |
| 数据资产S21 | 审计程序 | 70×6 | 1 | `sheet-program` |
| 数据资产的基本情况S21-1 | 基本情况 | 56×17 | 6 | `sheet-basic-info` |
| 开发支出资本化分析表S21-2 | 核心计算 | 77×28 | 43 | `sheet-capitalization` |
| 成本归集与分摊检查表S21-3 | 检查表 | 21×24 | 6 | `sheet-cost-allocation` |
| 摊销政策检查表S21-4 | 检查表 | 20×20 | 6 | `sheet-amortization` |

### 公式引擎 I/O 规格

#### useS21FormulaEngine — 开发支出资本化（S21-2）

**区段一：资本化时点判断（row7-15）**
- 5 项条件判断（技术可行/使用出售意图/市场需求/技术财力/单独核算）
- 研究阶段/开发阶段合计：`B15=SUM(C10:C14)`，`C15=SUM(D10:D14)`，`D15=SUM(E10:E14)`

**区段二：资本化金额按月归集（row16-27）**

**输入（CapitalizationInput）：**

| 类目 | 行号 | 含义 |
|------|------|------|
| 采购成本 | row18 | B18~M18 (1-12月) |
| 人工成本 | row19 | B19~M19 |
| 脱敏清洗标注整合分析支出 | row20 | B20~M20 |
| 数据权属鉴证费 | row21 | (手工输入) |
| 质量评估费 | row22 | (手工输入) |
| 登记结算费 | row23 | (手工输入) |
| 安全管理费 | row24 | (手工输入) |
| …（预留） | row25 | B25~M25 |

**核心公式链（43个）：**
```
类目合计 N{r} = SUM(B{r}:M{r})    — 12个月横向求和
类目占比 O{r} = N{r} / $N$40      — 各类目占总额比例（$N$40=资本化总额）

月合计 {c}26 = SUM({c}18:{c}25)   — 各月纵向求和（B26~M26）
总额  N26 = SUM(B26:M26)          — 资本化总额
总占比 O26 = N26/$N$40            — 应=1（校验）

各月比例 {c}27 = {c}26/$N$40      — 各月占总额比（B27~M27）
```

**输出：**
- `categoryTotals[k]` = SUM(monthly[k]) → N{r}
- `total` = N26 = SUM(categoryTotals)
- `categoryRatios[k]` = categoryTotals[k] / total → O{r}
- `monthlyTotals[m]` = SUM(各类目该月) → {c}26
- `monthlyRatios[m]` = monthlyTotals[m] / total → {c}27

---

## 4. S3 会计政策变更、前期差错、估计变更

### 源模板信息

| 属性 | 值 |
|------|-----|
| 文件 | `S3 会计政策变更、前期差错会计、估计变更2020.xlsx` |
| Sheet 数 | 11（含表头 + 参考sheet） |
| 当前 override | `"S3": "a-program-console"` |
| 目标 override | `"S3": "s3-policy-change"` |

### sheetName 分发表

| sheetName | 性质 | 尺寸 | 公式数 | 组件分发目标 |
|-----------|------|------|--------|-------------|
| 表头（请先填写） | 占位 | 20×7 | 0 | skip |
| 审定表 | 审定表 | 17×7 | 4 | `sheet-adjudication` |
| 会计政策变更和前期差错更正S3-1 | 程序 | 25×5 | 4 | `sheet-policy-change` |
| 会计估计变更审计程序S3-2 | 程序 | 26×5 | 4 | `sheet-estimate-change` |
| 首次执行新金融工具准则的调整S3-4 | 调整表 | 228×10 | 41 | `sheet-ifrs9-adjust` |
| 首次执行新收入准则的调整S3-6 | 调整表 | 154×10 | 4 | `sheet-ifrs15-adjust` |
| 首次执行新租赁准则的调整S3-8 | 调整表 | 115×10 | 6 | `sheet-ifrs16-adjust` |
| 简化的追溯调整法（1）S3-9 | 计算表 | 68×12 | 137 | `sheet-simplified-retro-1` |
| 简化的追溯调整法（2）S3-10 | 计算表 | 65×11 | 132 | `sheet-simplified-retro-2` |
| 简化的追溯调整法（2）S3-10 (2) | 副本 | 66×11 | 131 | 合并入 S3-10 |
| 参考-简化的追溯调整法（首次执行日） | 参考 | 359×20 | 1979 | skip（仅参考） |

### 公式引擎 I/O 规格

#### useS3AdjustmentEngine

**S3-4 首次执行新金融工具准则（41个公式）：**
```
调整差异 G{r} = F{r} - D{r}    — 新准则账面 - 原准则账面
```
Row150-160: `G150=F150-D150`, `G151=F151`, `G152=-D152`, `G153=F153-D153`...

**S3-8 首次执行新租赁准则（6个公式）：**
```
使用权资产初始确认 F55 = F53 - F54
租赁负债初始确认 F63 = F56+F57+F58-F59-F60-F61-F62
```

**S3-9 简化追溯调整法（137个公式）— 折现计算核心：**
```
剩余年限 E10 = (YEAR(C10)-YEAR(B10)) + D10 + (MONTH(C10)-MONTH(B10)+1)/12
调整截止日 F10 = DATE(YEAR(C10)+D10, MONTH(C10), DAY(C10))
现值折现因子 H{r} = 1/(1+$H$10)^G{r}
现值 I{r} = B{r} * H{r}
条件公式 C{r} = IF(E{r}=1, 0, B{r})  — 到期则现值=0
```

**S3-10 简化追溯调整法-变体（132个公式）：**
- 同 S3-9 结构，增加分期计算（月份比例 D17=9/12）

> 注意：`参考-简化的追溯调整法（首次执行日）` sheet 含 1979 个公式（INDEX/VLOOKUP 密集），作为参考资料不纳入专属组件，保留为 OO 兜底。

---

## 5. 交叉验证结论

### 5.1 design.md 对齐确认

| 验证项 | design.md 描述 | 源模板实际 | ✅/❌ |
|--------|---------------|-----------|-------|
| S15 sheets | 审定表S15-1/程序S15/S15-2/S15-3/S15-4 | ✅ 完全匹配（6 sheet 含表头） | ✅ |
| S15 EPS公式 | b=b0+b1+(c1×c2/m0+d1×d2/m0)-(e1×e2/m0)-b4 | `=D9+D10+D11-D18-D21` 匹配 | ✅ |
| S15 ROE公式 | P/(E0+NP/2+Ei×Mi/M0-Ej×Mj/M0+Ek×Mk/M0) | `=C15+C11/2+C20*C21/C19-C22*C23/C19+C24*C25/C19` 匹配 | ✅ |
| S20 单sheet | 营业收入扣除情况核查（多区段） | ✅ 1 sheet, 78×9 | ✅ |
| S20 公式 | revenue=main+other, deduction, ratio, afterDeduction | C16/C27/C30/C31 公式链匹配 | ✅ |
| S21 sheets | 数据资产/S21-1/S21-2/S21-3/S21-4 | ✅ 6 sheet 含表头 | ✅ |
| S21 月归集 | 12月SUM+占比 | N{r}=SUM(B:M), O{r}=N{r}/$N$40, {c}27={c}26/$N$40 | ✅ |
| S3 sheets | 审定/S3-1/S3-2/S3-4/S3-6/S3-8/S3-9/S3-10 | ✅ 11 sheet（含表头+参考+副本） | ✅ |
| S3 追溯公式 | 首执准则调整+简化追溯调整法 | 41+4+6+137+132=320 公式 | ✅ |

### 5.2 componentType 注册规划

| wp_code | 当前 override | 目标 componentType |
|---------|--------------|-------------------|
| S3 | `a-program-console` | `s3-policy-change` |
| S15 | `audit-sheet` | `s15-eps-roe` |
| S20 | `d-form-table` | `s20-revenue-deduction` |
| S21 | `d-form-table` | `s21-data-asset` |

### 5.3 特殊注意事项

1. **S3 参考sheet（1979公式）不纳入专属组件**：`参考-简化的追溯调整法（首次执行日）` 仅作参考，保留 OO 兜底或 skip
2. **S3-10 (2) 副本**：与 S3-10 结构相同，合并处理为一个 sheet 模板
3. **S15-4 本年/上年对比**：row2-26 本年, row43-60 上年（同结构双栏）
4. **S20 双列**：本年审定(C列) + 上年追溯调整后(D列)
5. **S21-2 $N$40 引用**：N40 应为资本化总额（=N26），所有占比引用此绝对单元格
6. **S3 简化追溯调整法**：核心是 NPV/IRR 折现计算，涉及 DATE/YEAR/MONTH 函数和幂运算

### 5.4 公式引擎设计验证

| 引擎 | 纯函数 | 输入类型 | 关键公式 | 分母零保护 |
|------|--------|---------|---------|-----------|
| useS15FormulaEngine.calcWeightedAvgShares | ✅ | EpsInput | b=b0+b1+c-e-b4 | m0=0→unable |
| useS15FormulaEngine.calcBasicEps | ✅ | EpsInput | a1/b, a2/b | b=0→unable |
| useS15FormulaEngine.calcDilutedRoe | ✅ | RoeInput | P/E, P/加权净资产 | E=0→unable |
| useS20FormulaEngine.calcRevenueDeduction | ✅ | RevenueDeductionInput | SUM+ratio+diff | revenue=0→unable |
| useS21FormulaEngine.calcCapitalization | ✅ | CapitalizationInput | SUM(12月)+占比 | total=0→unable |
| useS3AdjustmentEngine | ✅ | 各调整输入 | 差异/折现/IF | 折现分母自然>0 |

---

## 6. 最终确认

✅ **设计文档（design.md）与源模板完全对齐**
- 4 个 componentType 命名确认
- sheetName 分发表与源模板 tab 名一致
- 公式引擎 I/O 规格与 Excel 公式链完全匹配
- 审定表回写规格确认（v2 正数口径）

Phase0 双源核对完成，可进入 Phase1（后端注册）。
