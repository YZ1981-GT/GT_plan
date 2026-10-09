# Task 14 / C-13 — G1 交易性金融资产 lane 交付

commit `0a3133630`（14 文件）

## 前端改造（useG1Detail.ts）

**TradingDetailRow** 58→46+2 字段：删 `addedCost`/`reducedCost`（M 合并），加 `periodCostChange`(M 净额) + `confirmationRequested`(AA)。

6 处口径按模板改齐：

| # | 模板公式 | 改造前 | 改造后 |
|---|---------|--------|--------|
| 1 | `P=C+M` | 审定成本 H + 增−减 | `openingCost + periodCostChange` |
| 2 | `Q=D+N` | 审定累计 FV + 变动 | `openingCumulativeFv + periodFvChange` |
| 3 | `R=P+Q` | 有市价时覆盖 | 恒为双桶合计 |
| 4 | `W=U+V` | 含 aje/rje | 不含 |
| 5 | `L=J+K` | 减 | 加（K 存负数） |
| 6 | `Y=W+X` | 减 | 加（X 存负数） |

受管字段序调整为模板列序（acctClass→A 先于 securityName→B；P→Q→R 连续）。

## 后端三区 spec

`phase5_g1_02_detail.py`：三区各自的 `RowTableSheetSpec`：
- 区① R12-R16，uuid=AB，公式列 13 个（含跨表 T）
- 区② R19-R23，uuid=AC，公式列 12 个（T=editable）
- 区③ R26-R28，uuid=AD，公式列 12 个（T=editable）

🔴 区① 独有差异：T 列引 `公允价值测试表G1-6!H10..H14`，逐行不同，由 `TEMPLATE_CROSS_SHEET_FORMULAS_G102` 记录。

## 判据（test_g1_column_isomorphism.py，80 passed）

五层闭环：
1. ① header_text 逐列 = 模板逐格（两级表头 7 横向组 / 8 纵向合并逐格）
2. ② json_key 双向 = 前端受管字段（27 列 + 序检查）
3. ③ 公式列：区① 13 个 / 区②③ 12 个 / 差集恰 {T} / 跨表逐行比对 / T 在区②③ 8 格全 None
4. ④ 三区几何：区标题/小计/合计不在受管区 / uuid 互不相同 / section_value 映射
5. ⑤ 三区过滤读写成对 / merge 盖章 / 幽灵行防护
6. ⑥ 口径改齐 6 处 + M 合并 + AA 新补

## 非模板列字段决策

29 个非模板字段不删不受管：
- 17 个有生产消费方（5 兄弟表 composable）
- 12 个零消费方（可删清单，本轮不删 —— 受管面已严格 27 列）

## 验证

- G1 判据：80 passed
- 六 lane 全套：758 passed / 4 failed（G3 两条 + P18 两条，符合预期）
- P20 golden digest：12 passed（含 G1）
- 前端 G1 spec：7 passed / 0 failed
- 零回归门唯一 FAIL = f1（已知签名不匹配，非本轮引入）
- 行数门禁：whitelist 更新后全通过
