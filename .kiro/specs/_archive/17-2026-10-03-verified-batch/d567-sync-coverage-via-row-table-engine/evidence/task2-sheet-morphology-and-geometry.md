# Task 2: 十三张 sheet 形态判定 + 几何实测 + 下游消费方 grep

**measured_at**: 2026-09-26
**method**: openpyxl 直读 + grep 按值实测（`_probe_d567_sheet_geometry.py` 一次性探针）

## §1 模板真名修正（首版 spec 与模板实测不符的名称）

| spec 原名 | 模板实测真名 | 差异 |
|---|---|---|
| 合同资产减值准备测算D6-3 | **合同资产减值准备明细表D6-3** | 「测算」→「明细表」 |
| 合同资产减值准备测算D6-8 | **减值准备测算D6-8** | 去掉「合同资产」前缀 |
| 减值准备转回核销检查D6-9 | **减值准备转回、核销检查表D6-9** | 加顿号「、」+ 尾「表」 |
| 账龄1年以上合同负债检查D7-5 | **账龄1年以上合同负债检查表D7-5** | 尾加「表」 |
| 关联方合同负债检查D7-6 | **关联方关系及交易检查表D7-6** | 「关联方合同负债检查」→完整名 |
| 合同负债凭证检查D7-7 | **合同负债检查表D7-7** | 「凭证检查」→「检查表」 |

🔴 **裁决 G3 实证**：按 spec 原名推演的 `managed_sheet` 有 6 处与模板不符，attach 时会
sheet 找不到。必须用实测真名。

## §2 几何实测总表

| sheet | 真名 | r×c | 公式 | 主公式列 | 合计行 | 候选UUID列 | merged |
|---|---|---|---|---|---|---|---|
| D5-4 | 应收款项融资公允价值测算表D5-4 | 26×13(M) | 18 | K6 I4 J2 E2 A2 | 17(合计) | N/O/P | 11 |
| 审定表D5 | 审定表D5 | 18×12(L) | 52 | E8 H6 I6 J5 K5 | 9(小计) 11(合计) | L/M/N | — |
| D6-3 | 合同资产减值准备明细表D6-3 | 29×14(N) | 63 | N12 E11 K11 B3 C3 | 17(信用风险组合计提) 22(合计) | O/P/Q | — |
| D6-5 | 关联关系及交易检查D6-5 | 30×14(N) | 19 | H6 F4 E3 A2 L1 | 13(合计) | M/N/O | — |
| D6-6 | 合同资产检查表D6-6 | 53×17(Q) | 19 | E5 G5 H3 F3 A2 | 31(合计) 40(合计) | R/S/T | — |
| D6-7 | 合同资产减值准备会计政策检查D6-7 | 58×18(R) | **7** | A2 C2 E2 I1 | **无** | J/K/L | — |
| D6-8 | 减值准备测算D6-8 | 48×15(O) | 58 | D21 F21 E6 B4 C3 | 18(小计) 19(组合计提) 29(小计) 37(小计) 38(合计) | I/J/K | — |
| D6-9 | 减值准备转回、核销检查表D6-9 | 30×8(H) | 10 | E3 A2 C2 H1 F1 | **无** | I/J/K | — |
| D6-1 | 审定表D6-1 | 43×13(M) | **177** | E26 I23 J22 K19 H14 | 多行(6处合计/小计) | M/N/O | — |
| D7-4 | 合同负债分析表D7-4 | 43×8(H) | 32 | E13 D11 C3 A2 B2 | 11(借方合计) 20(贷方合计) 37(小计) | H/I/J | — |
| D7-5 | 账龄1年以上合同负债检查表D7-5 | 20×8(H) | 9 | A2 C2 E2 H1 B1 | **无** | I/J/K | — |
| D7-6 | 关联方关系及交易检查表D7-6 | 31×11(K) | 15 | F6 D3 A2 K1 C1 | **无** | L/M/N | — |
| D7-7 | 合同负债检查表D7-7 | 48×21(U) | 19 | F5 G5 H3 E3 A2 | 31(合计) 40(合计) | R/S/T | — |
| D7-1 | 审定表D7-1 | 32×12(L) | 84 | E18 I15 J14 K14 H5 | 14(小计) 16(合计) 24(合计) | M/N/O | — |

## §3 形态判定

### §3.1 行表型 `excel_table`（UUID 动态行，走位移链）

| sheet | binding_kind | row_identity_key | aging_layout | header行 | 数据行范围 | footer行 | UUID列 | formula_columns |
|---|---|---|---|---|---|---|---|---|
| D5-4 | excel_table | rowId | None | 10-11 | 12-16 | 17 | N | K(=J{r}),G(=F-E),I(=D*H*G/365),J(=D-I) |
| D6-3 | excel_table | rowId | flat | 10-11 | 12-16(单项)/18-21(组合) | 17/22 | O | N,E,K,B,C(部分) |
| D6-5 | excel_table | rowId | flat | 9 | 10-12 | 13 | M | H,F(部分) |
| D6-6 区① | excel_table | rowId | — | 15-16 | 17-30 | 31 | R | E,G(部分) |
| D6-6 区② | excel_table | rowId | — | 32-33 | 34-39 | 40 | S | G(部分) |
| D6-8 | excel_table | rowId | flat | 11/20-21 | 12-17(单项)/22-28(组1)/31-36(组2) | 18/29/37/38 | I | D,F |
| D6-9 区① | excel_table | rowId | — | 13 | 14-16 | 17 | I | E,F(部分) |
| D6-9 区② | excel_table | rowId | — | 19 | 20-22 | 23 | J | B(部分) |
| D7-4 区① | excel_table | rowId | nested | 10 | 12-15(+空行) | 11(借方合计) | H | — |
| D7-4 区② | excel_table | rowId | nested | 18-19 | 21-36(+空行) | 20(贷方合计)/37(小计) | I | D,E(部分) |
| D7-5 | excel_table | rowId | nested | 10 | 11-13 | 14(=SUM) | I | B,F(部分) |
| D7-6 | excel_table | rowId | nested | 11 | 12-14 | 15(合计) | L | F,D(部分) |
| D7-7 区① | excel_table | rowId | — | 15-16 | 17-30 | 31 | R | F,G,H(部分) |
| D7-7 区② | excel_table | rowId | — | 32-33 | 34-39 | 40 | S | G(部分) |

🔴 **D6-3/D6-8 是多 section 结构**（单项计提 + 组合计提），不是简单双区。需要逐 section 声明。
🔴 **D7-4 的双区是借方发生额分析(区①)+贷方发生额分析(区②)+期末余额(区③)**——实际可能是三段而非两段。
    但 store 只有两个键 `credit-rows`/`debit-rows`，所以 section 归属以 store key 为准。

### §3.2 审定表型 `AdjudicationSheetSpec`（固定行 per-cell 锚点）

| sheet | row_mode | 公式密度 | section 数(实测) | 区块详情 |
|---|---|---|---|---|
| 审定表D5 | fixed_rows | 52/216=24% | **2** | ①应收票据/应收账款(R7-R8,合计R9) ②减:公允价值变动(R10,合计R11) |
| 审定表D6-1 | fixed_rows | 177/559=**32%** | **3** | ①原值(R8-R12,小计R13,含减项R14,合计R15) ②坏账准备(R17-R21,小计R22,含减项R23,合计R24) ③净值(R26-R30,小计R31,减项R32,合计R33) |
| 审定表D7-1 | fixed_rows | 84/384=22% | **2** | ①性质分类(R8-R13,小计R14,减项R15,合计R16) ②账龄分类(R20-R23,合计R24) |

🔴 **D6-1 审定表三区**是本 spec 公式密度最高的一张（32%），三区 × 5 行分类 + 3 行合计/减项 = 最复杂审定表。
🔴 **审定表D5 两区但形态独特**：只有 2 行数据（R7 应收票据 / R8 应收账款），合计 R9 后还有「减：公允价值变动」R10 和第二个合计 R11。
🔴 **审定表D7-1 与 D3-1 结构高度相似**（两区：性质分类+账龄分类），可复制 D3-1 声明骨架。

### §3.3 形态核候选（Task 21 待裁决）

| sheet | 候选形态 | 理由 |
|---|---|---|
| D6-7 | **static_region** (首选) | 58r×18c 但仅 7 公式（密度 0.7%），无合计行，无动态行需求 |

## §4 下游消费方 grep 补全

| store_item_id | 写入方 | 读取方（下游 computed） |
|---|---|---|
| D5-4-rows | useD5FairValue.ts | useD5CrossSheet.ts:135（fairValueRows） |
| D6-3-rows | useD6ImpairmentDetail.ts | useD6CrossSheet.ts:109（impairmentAggregation）, :345（impairmentChangesForDisclosure） |
| D6-5-rows | useD6RelatedParty.ts | d6SheetLabels.ts:111（完成度） |
| D6-6-block1-rows | useD6Inspection.ts | d6SheetLabels.ts:114（完成度双区） |
| D6-6-block2-rows | useD6Inspection.ts | d6SheetLabels.ts:114（完成度双区） |
| D6-8-single-rows | useD6EclCalculation.ts | useD6CrossSheet.ts:220,316（eclReferenceValues/eclForDisclosure） |
| D6-9-reversal-rows | useD6WriteoffCheck.ts | d6SheetLabels 完成度（待确认） |
| D6-9-writeoff-rows | useD6WriteoffCheck.ts | d6SheetLabels 完成度（待确认） |
| D7-4-credit-rows | useD7Analysis.ts:102 | d7SheetLabels.ts:106（完成度双区） |
| D7-4-debit-rows | useD7Analysis.ts:74 | d7SheetLabels.ts:106（完成度双区） |
| D7-5-rows | useD7LongTerm.ts | useD7Disclosure.ts:150（listedSection2Rows），d7SheetLabels:108 |
| D7-6-rows | useD7RelatedParty（推定） | d7SheetLabels:110 |
| D7-7-period-rows | useD7VoucherCheck（推定） | d7SheetLabels:113 |
| D7-7-post-rows | useD7VoucherCheck（推定） | useD7CrossSheet.ts:234（voucherPostTransferTotal），useD7Detail.ts:394（watch） |

## §5 历史残留 sheet 确认

| 册 | 残留 sheet 名 | 行数 | 处置 |
|---|---|---|---|
| D6 | 合同资产实质性程序表 D7A（原） | 104r | 显式排除（非本循环） |
| D7 | 合同负债实质性程序表 D8A（原） | 66r | 显式排除（非本循环） |

## §6 两套 gating 覆盖

三家宿主现状均写死 `isD*DetailSheet = currentSheet === 'D*-2'`（仅明细表），需改为 provider 受管清单派生。
