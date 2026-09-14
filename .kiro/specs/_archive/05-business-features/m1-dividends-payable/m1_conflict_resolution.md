# M1 应付股利（利润）双源交叉验证报告

## 验证概述

| 项目 | 说明 |
|------|------|
| xlsx源 | `M1 应付股利（利润）.xlsx`（11 sheet, 338公式） |
| md源 | `M权益循环底稿模板库.md` → M1 section |
| 验证日期 | 2026-07-14 |
| 验证结论 | **一致，无实质冲突** |

---

## 1. 负债类方向验证 ✅ 一致

### xlsx 实际公式（审定表M1-1）

审定表M1-1结构 56×12，关键公式：
- `J7=I7-E7`（变动额=期末审定-期初审定）
- `K7=IF(AND(E7=0,J7=0),0,IF(AND(E7=0,J7>0),1,J7/E7))`（条件变动率）
- `I7='明细表M1-2'!Q25`（审定数引用明细表）
- `B13=SUM(B7:B12)`（按股东分类小计）

**负债类方向体现**：
- 科目2232应付股利为**贷方/负债类**
- 明细表M1-2按股东列示：期末=期初+本期宣告(贷方增加)-本期支付(借方减少)
- 审定数验证：审定表数据全部引用明细表汇总（`='明细表M1-2'!cell`）

### md 业务逻辑

> "企业根据股东大会或类似机构审议批准的利润分配方案，按应支付的现金股利或利润，借记'利润分配'科目，贷记本科目。"

md明确：宣告分配时**贷方增加**（贷记应付股利），实际支付时**借方减少**（借记应付股利）。

### 验证结论

| 维度 | xlsx | md | 一致性 |
|------|------|-----|--------|
| 科目方向 | 贷方/负债类 | 贷方/负债类 | ✅ |
| 期末公式 | 期末=期初+贷方(宣告)-借方(支付) | 宣告贷记增加,支付借记减少 | ✅ |
| 审定数 | I=引用明细合计 | 明细汇总=审定表 | ✅ |

**确认实现公式**：`calcLiabilityEndBalance(begin, credit, debit) = begin + credit - debit`

---

## 2. 外币折算验证 ✅ 一致

### xlsx 实际公式（外币汇率测算表M1-4，25×7）

列结构（从header_rows+公式推断）：
- A: 股本名称
- B: 币种
- C: 原币金额
- D: 折算汇率
- E: 折合人民币 = **C×D**（`E10=C10*D10`, ..., `E15=C15*D15`）
- F: 账面数（用户输入）
- G: 差额 = **E-F**（`G10=E10-F10`, ..., `G15=E15-F15`）
- 合计行：`C16=SUM(C10:C15)`, `E16=SUM(E10:E15)`, `F16=SUM(F10:F15)`, `G16=SUM(G10:G15)`

共16个计算公式（excl 7个header refs）= 6×E + 6×G + 4×SUM

### md 业务逻辑

> "股本名称 | 币种 | 原币金额 | 折算汇率 | 折合人民币 | 账面数 | 差额"
> "非记账本位币的，检查其折算汇率是否正确，会计处理是否正确。"

md列名与xlsx完全对应。

### 验证结论

| 维度 | xlsx公式 | md描述 | design定义 | 一致性 |
|------|----------|--------|-----------|--------|
| 折算本位币 | E=C×D | 原币金额×折算汇率=折合人民币 | calcFxConverted(amt,rate)=amt×rate | ✅ |
| 汇兑差异 | G=E-F | 折合人民币-账面数=差额 | calcFxDiff(conv,booked)=conv-booked | ✅ |
| 合计 | SUM(range) | 合计行 | calcSubtotal(arr)=Σarr | ✅ |

**确认实现公式**：
- `calcFxConverted(amount, rate) = amount × rate`
- `calcFxDiff(converted, booked) = converted - booked`

**列名映射（xlsx列名权威）**：

| xlsx列名 | design变量名 | 备注 |
|----------|-------------|------|
| 原币金额 | amount | C列 |
| 折算汇率 | rate | D列 |
| 折合人民币 | converted | E列（计算值） |
| 账面数 | booked | F列（用户输入） |
| 差额 | diff | G列（计算值） |

---

## 3. 股利测算验证 ✅ 一致

### xlsx 实际公式（应付股利测算表M1-5，29×14）

列结构（从header_rows+公式推断）：
- A: 股东名称
- B: 股东会决议分配基数（可供分配利润）
- C: 分配比例
- D: 分配额 = **B×C**（`D10=B10*C10`, ..., `D17=B17*C17`）
- E: 实际分配额（账面宣告,用户输入）
- F: 差异 = **D-E**（`F10=D10-E10`, ..., `F17=D17-E17`）
- 合计行：`B18=SUM(B10:B17)`, `C18=SUM(C10:C17)`, `D18=SUM(D10:D17)`, `E18=SUM(E10:E17)`, `F18=SUM(F10:F17)`

共21个计算公式（excl 7个header refs）= 8×D + 8×F + 5×SUM

### md 业务逻辑

> "检查应付股利（利润）的计提是否根据董事会或股东会(或股东大会)决定的利润分配方案，从税后可供分配利润中计算确定。"
> "股东名称 | 股东会决议分配基数 | 分配比例 | 分配额 | 实际分配额 | 差异 | 差异原因 | 备注"

md列名与xlsx完全匹配。

### 验证结论

| 维度 | xlsx公式 | md描述 | design定义 | 一致性 |
|------|----------|--------|-----------|--------|
| 应宣告股利 | D=B×C | 分配基数×分配比例=分配额 | calcDeclaredDividend(profit,ratio)=profit×ratio | ✅ |
| 宣告差异 | F=D-E | 分配额-实际分配额=差异 | calcDeclareDiff(estimated,booked)=estimated-booked | ✅ |
| 合计 | SUM(range) | 合计行 | calcSubtotal(arr)=Σarr | ✅ |

**确认实现公式**：
- `calcDeclaredDividend(profit, ratio) = profit × ratio`
- `calcDeclareDiff(estimated, booked) = estimated - booked`

**列名映射（xlsx列名权威）**：

| xlsx列名 | design变量名 | 备注 |
|----------|-------------|------|
| 股东会决议分配基数 | profit | B列（来自M6利润分配） |
| 分配比例 | ratio | C列 |
| 分配额 | declaredDividend | D列（计算值） |
| 实际分配额 | booked | E列（用户输入/账面） |
| 差异 | declareDiff | F列（计算值） |

---

## 4. M6联动验证 ✅ 一致

### xlsx 跨sheet引用

M1-5股利测算表的B列"股东会决议分配基数"为手动输入（无公式引用M6）——**这是因为xlsx是模板，跨工作簿引用在模板中无法体现**。

### md 业务逻辑

> "审阅公司章程、股东会(或股东大会)和董事会会议纪要中有关股利的规定...了解股利分配标准和发放方式是否符合有关规定并经法定程序批准、金额是否正确。"（M1A程序表第4步）
> 
> M1-5索引号指向："检查应付股利（利润）测算"

md确认M1-5的分配基数来源是**M6未分配利润的利润分配方案**（股东大会决议），在系统实现中通过EventBus订阅`m6:profit-distributed`事件接收。

### 联动设计验证

| 联动方向 | xlsx体现 | md体现 | 实现方式 |
|----------|----------|--------|---------|
| M6→M1 | M1-5 B列手动填入 | 分配基数来自利润分配方案 | EventBus subscribe `m6:profit-distributed` |
| M1→TB | 审定表合计→TB回写 | "与总账数核对是否相符" | publish `substantive:adjudicated` + writebackTB(2232) |
| M1-1↔M1-2 | 92个=明细表引用 | 明细核对审定 | adjudicationVsDetail 交叉验证 |
| M1-5→M1-6 | M1-6引用M1-2 | 测算→检查表验证 | declareVsM6 交叉验证 |

**md为联动方向权威**：M6分配股利→M1测算核对，实现为EventBus订阅模式。

---

## 5. 检查表M1-6 交叉引用验证 ✅ 一致

### xlsx 实际公式（检查表M1-6，36×16）

关键计算公式：
- `F20=SUM(F12:F19)`（借方合计）
- `G20=SUM(G12:G19)`（贷方合计）
- `E23='明细表M1-2'!P23`（引用明细表发生额）
- `F23=F20`（检查金额=借方合计）
- `G23=ROUND(F23/E23,4)`（检查比例）
- `E24='明细表M1-2'!O23`
- `F24=G20`
- `G24=ROUND(F24/E24,2)`

### md 业务逻辑

> "本期发生额、期末余额检查比例：方向 | 账面金额 | 检查金额 | 检查比例"
> "如果检查比例较低应扩大检查样本量或说明原因"

检查表列结构确认：记账凭证(日期/凭证编号/业务内容/对方科目/对方明细/借方/贷方) + 支持性文件 + 核对内容(1~5) + 索引号 + 是否异常 + 备注

---

## 6. 冲突解决总结

### 无实质冲突

双源（xlsx结构 vs md业务逻辑）在以下所有维度完全一致：

| 验证项 | 结果 | 说明 |
|--------|------|------|
| 负债类方向 | ✅ | 贷方增加(宣告)/借方减少(支付) |
| 外币折算公式 | ✅ | E=C×D, G=E-F |
| 股利测算公式 | ✅ | D=B×C, F=D-E |
| M6联动方向 | ✅ | M6→M1单向(分配基数) |
| 跨sheet引用 | ✅ | M1-1全引用M1-2 |
| 列名一致性 | ✅ | md列名=xlsx列名 |
| 维度一致性 | ✅ | M1-1(56×12)/M1-2(38×27)/M1-4(25×7)/M1-5(29×14) |

### 微小差异记录（非冲突）

| 差异点 | xlsx | md | 解决 |
|--------|------|-----|------|
| 公式总数 | M1-4=23(含7 header ref)→16 calc | md未提及具体数量 | 以xlsx为准：16 calc公式 |
| 公式总数 | M1-5=28(含7 header ref)→21 calc | md未提及具体数量 | 以xlsx为准：21 calc公式 |
| M1-5维度 | 29×14 | md仅列出8列 | xlsx实际14列包含备注等扩展列 |
| M6联动 | xlsx无跨工作簿引用 | md确认来自利润分配方案 | md为联动方向权威→EventBus实现 |
| design说M1-4 13公式 | xlsx calc=16 | - | 已在design_verification中标注 |
| design说M1-5 13公式 | xlsx calc=21 | - | 已在design_verification中标注 |

---

## 7. 最终确认公式模式（实现依据）

### useM1FormulaEngine.ts

```typescript
// P1: 审定数 = 未审 + AJE + RJE
calcAuditedAmount(unadj, aje, rje) = unadj + aje + rje

// P2: 负债类期末余额（贷方科目！）
calcLiabilityEndBalance(begin, credit, debit) = begin + credit - debit

// P6: 分类小计
calcSubtotal(arr) = Σarr  // SUM(range)
```

### useM1FxEngine.ts

```typescript
// P3: 折算本位币 = 原币金额 × 折算汇率
calcFxConverted(amount, rate) = amount × rate  // xlsx: E=C*D

// P4: 汇兑差异 = 折算本位币 - 账面数
calcFxDiff(converted, booked) = converted - booked  // xlsx: G=E-F
```

### useM1DividendEngine.ts

```typescript
// P5: 应宣告股利 = 分配基数 × 分配比例
calcDeclaredDividend(profit, ratio) = profit × ratio  // xlsx: D=B*C

// 宣告差异 = 测算宣告 - 实际分配额
calcDeclareDiff(estimated, booked) = estimated - booked  // xlsx: F=D-E
```

### 变动额/变动率（审定表M1-1附加）

```typescript
// 变动额 = 期末审定 - 期初审定
calcVarianceAmount(endAudited, beginAudited) = endAudited - beginAudited  // xlsx: J=I-E

// 变动率 = 条件除法
calcVarianceRate(beginAudited, varianceAmount) =
  if (beginAudited === 0 && varianceAmount === 0) return 0
  if (beginAudited === 0 && varianceAmount > 0) return 1
  return varianceAmount / beginAudited  // xlsx: K=IF(AND(E=0,J=0),0,IF(AND(E=0,J>0),1,J/E))
```

---

## 8. 权威来源裁决规则

按双源输入流程规范：

| 冲突类型 | 权威来源 | 原因 |
|----------|---------|------|
| 列名/公式结构 | **xlsx** | 源模板是结构真相 |
| 联动方向/认定映射 | **md** | 业务语义是逻辑真相 |
| 维度/行列数 | **xlsx** | 可直接计量 |
| 审计程序步骤 | **md** | 业务流程权威 |
| 分配基数来源 | **md** | 跨工作簿联动只有md能说明 |
