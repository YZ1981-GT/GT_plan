# Design Document: D4 营业收入底稿专属HTML精美组件

## Overview

D4营业收入底稿专属组件`d4-operating-revenue`。平台最大单科目底稿（8个xlsx源模板/42有效sheet/~280+公式）。科目6001主营业务收入+6051其他业务收入（损益类/贷方科目）。

核心架构：
- componentType `d4-operating-revenue`，主入口 GtD4OperatingRevenue.vue
- **无内部el-tabs**：外层GtWpRenderer已有sheet目录行(chips)，专属组件接收`sheetName` prop用`v-if`分发到子组件
- 每个sheet独立子组件(200-700行) + 独立composable
- 16个composable：useD4FormulaEngine(纯函数) + useD4FormData + useD4CrossSheet + 13个sheet/功能域composable
- 跨sheet数据流通过 allResponses Map computed 响应式链（不走API）
- 5+方EventBus联动 + GtIndexChip交叉索引
- 双模式（HTML ↔ OnlyOffice）+ 导入导出三级(useD4ImportExport) + AI审计说明(8 section)
- IPO/舞弊组条件可见性（business_category控制）

## Architecture

### sheetName分发模式（非嵌套Tab）

GtD4OperatingRevenue.vue 接收 `sheetName` prop（完整中文名如"营业收入审定表D4-1"），用正则提取末尾编码(D4-1)，`v-if` 分发到对应子组件。未迁移的sheet走 OnlyOffice fallback（GtOnlyOfficeSheet全高）。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback
```

### 文件结构（实际）

```
audit-platform/frontend/src/components/workpaper/
├── GtD4OperatingRevenue.vue              # 主入口 sheetName v-if分发（defineAsyncComponent lazy）
├── d4/
│   ├── core/
│   │   ├── D4TabIndex.vue                # 统一底稿目录（进度条+42行）
│   │   ├── D4TabAdjudication.vue         # D4-1 审定表
│   │   ├── D4TabRevenueDetail.vue        # D4-2 主营明细22列宽表
│   │   ├── D4TabOtherRevenue.vue         # D4-3 其他明细
│   │   ├── D4TabAdjustment.vue           # D4-4 调整分录
│   │   ├── D4TabDisclosureListed.vue     # 附注上市
│   │   └── D4TabDisclosureSoe.vue        # 附注国企
│   ├── policy/
│   │   └── D4TabPolicyCheck.vue          # D4-5 CAS14五步法（真AI+GtIndexChip+引导6步）
│   ├── analysis/
│   │   ├── D4TabIndicator.vue            # D4-6 指标分析
│   │   ├── D4TabMarginMonthly.vue        # D4-7 月度毛利
│   │   ├── D4TabProductMargin.vue        # D4-8 产品毛利
│   │   ├── D4TabCustomerStructure.vue    # D4-9 客户结构
│   │   ├── D4TabCustomerPrice.vue        # D4-10 客户价格
│   │   └── D4TabProductPrice.vue         # D4-11 产品价格
│   ├── inspection/
│   │   ├── D4TabContract.vue             # D4-12 合同检查（三模式：卡片/矩阵/OO）
│   │   ├── D4ContractCard.vue            # D4-12 合同卡片子组件（5组20+1字段）
│   │   ├── D4ContractMatrix.vue          # D4-12 合同矩阵视图（只读横向对比）
│   │   ├── D4TabErpCheck.vue             # D4-13 ERP核对
│   │   ├── D4TabOccurrence.vue           # D4-14 发生检查（三模式+穿行测试集成）
│   │   ├── D4WalkthroughCard.vue         # D4-14 穿行测试卡片（7维度+OCR）
│   │   ├── D4WalkthroughMatrix.vue       # D4-14 穿行测试矩阵（只读el-table）
│   │   ├── D4TabCompleteness.vue         # D4-15 完整性检查
│   │   ├── D4TabExport.vue               # D4-16 出口核对（三分组表格）
│   │   ├── D4TabCutoffForward.vue        # D4-17 截止正向
│   │   ├── D4TabCutoffBackward.vue       # D4-18 截止反向
│   │   ├── D4TabDiscount.vue             # D4-19 折扣折让
│   │   └── D4TabReturn.vue               # D4-20 退货检查（6大结构区域）
│   ├── related/
│   │   └── D4TabRelatedPrice.vue         # D4-21 关联方价格
│   ├── ipo/
│   │   ├── D4TabIpoProcedure.vue         # D4-22A IPO程序表（包装组件+selfLoad）
│   │   ├── D4TabIpoIndicator.vue         # D4-22 IPO指标
│   │   ├── D4TabInvoiceCompare.vue       # D4-23 发票对比
│   │   ├── D4TabThirdParty.vue           # D4-24 第三方回款
│   │   ├── D4TabDealer.vue               # D4-25 经销商
│   │   ├── D4TabOverseas.vue             # D4-26 境外销售
│   │   ├── D4TabUndisclosedRp.vue        # D4-27 未披露关联方
│   │   ├── D4TabCustomerChecklist.vue    # D4-28 核查清单
│   │   ├── D4TabCustomerDetail.vue       # D4-29 核查详细
│   │   ├── D4TabInterviewSummary.vue     # D4-30 访谈汇总
│   │   ├── D4TabInterviewDetail.vue      # D4-31 访谈详细
│   │   ├── D4TabInterviewTemplate.vue    # 访谈记录与核对示例
│   │   └── D4TabFundFlow.vue             # D4-32 资金流水
│   └── other/
│       ├── D4TabOtherMargin.vue          # D4-33 其他毛利
│       ├── D4TabOtherContract.vue        # D4-34 合同测算
│       ├── D4TabOtherCheck.vue           # D4-35 其他检查
│       └── D4TabOtherCutoff.vue          # D4-36 其他截止
├── composables/
│   ├── useD4FormData.ts                  # 数据加载/保存/selfLoad/writebackTB（~200行）
│   ├── useD4FormulaEngine.ts             # 纯函数公式引擎17函数（~200行）
│   ├── useD4CrossSheet.ts                # 跨sheet联动computed（~300行）
│   ├── useD4Adjudication.ts              # D4-1 审定表
│   ├── useD4RevenueDetail.ts             # D4-2 主营明细
│   ├── useD4OtherRevenue.ts              # D4-3 其他明细
│   ├── useD4Adjustment.ts                # D4-4 调整分录
│   ├── useD4PolicyCheck.ts               # D4-5 政策检查
│   ├── useD4Analysis.ts                  # D4-6~11 分析程序通用
│   ├── useD4ContractInspection.ts        # D4-12 合同检查（20+1字段×N份+OCR）
│   ├── useD4WalkthroughTest.ts           # D4-14 穿行测试（7维度+一致性引擎）
│   ├── useD4CompletenessCheck.ts         # D4-15 完整性检查（3维度+自动√/×）
│   ├── useD4RelatedPrice.ts              # D4-21 关联方价格
│   ├── useD4Ipo.ts                       # D4-22~32 IPO组
│   ├── useD4KeyIndicator.ts              # D4-22 IPO指标定义
│   ├── useD4InvoiceCompare.ts            # D4-23 发票对比
│   ├── useD4CustomerDetail.ts            # D4-29 客户详细
│   ├── useD4OtherGroup.ts                # D4-33~36 其他收入组
│   ├── useD4Disclosure.ts                # 附注上市+国企（variant双版本共用）
│   ├── useD4ImportExport.ts              # 导入导出（axios+三端点复用）
│   └── useD4DualMode.ts                  # 双模式OO健康检查

backend/app/routers/wp_render_strategies/
├── _d4_operating_revenue.py              # render策略+注册RENDERER_DISPATCH
├── _d4_import_export.py                  # 导入导出3端点（export-template/export-data/import-data）
├── _d4_ai_generate.py                    # AI生成8 section
└── _d4_contract_ocr.py                   # D4-12 OCR端点（UnifiedOCR→vLLM结构化提取）

backend/app/services/auto_data_resolvers/
└── _d4_revenue.py                        # 3 resolver（d4_tb_unadjusted/d4_ledger_monthly/d4_analysis_indicators）
```

### 与原设计的关键差异

1. **无内部el-tabs**：原设计7组嵌套Tab→改为sheetName prop v-if分发（外层GtWpRenderer目录行已提供Tab导航）
2. **useD4Inspection已删除**：原设计单个composable覆盖D4-12~20→拆为3个独立composable（useD4ContractInspection/useD4WalkthroughTest/useD4CompletenessCheck）+ 各sheet独立Vue组件
3. **附注合并为单composable**：原设计useD4DisclosureListed+useD4DisclosureSoe两个→改为useD4Disclosure（variant参数区分）
4. **D4-12三模式**：原设计普通表格→升级为卡片/矩阵/OO三模式（D4ContractCard+D4ContractMatrix子组件）
5. **D4-14穿行测试**：原设计简单凭证表→升级为7维度+一致性引擎+维度级OCR（D4WalkthroughCard+D4WalkthroughMatrix）
6. **D4-5政策检查**：原设计段落textarea→升级为真AI接入+GtIndexChip真跳转+引导式6步流程
7. **IPO程序表D4-22A**：原设计直接复用a-program-console→改为包装组件D4TabIpoProcedure.vue（selfLoad带sheet_name参数解决聚合包内非首个程序表数据错误问题）
8. **新增composable**：useD4KeyIndicator/useD4InvoiceCompare/useD4CustomerDetail（IPO组按sheet独立拆分）

### 后端AI Section清单（实际注册）

```
adj-note / adj-conclusion / revenue-change / policy-evaluation /
analysis-note / return-analysis / related-price / interview-questions
```

### EventBus事件（实际）

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | D4-1 | TB回写 |
| `adjustment:created` | D4-4 | D4-1, A13 |
| `analytical:significant-change` | D4-6~11 | A1-13 |
| `risk:updated` | B50 | D4A |
| `disclosure:note-text-updated` | 附注 | 附注模块 |

## Correctness Properties

（17个纯函数property保持原spec不变，全部通过PBT验证）

P1~P20 见 requirements.md 末尾 Correctness Properties 章节。测试覆盖：
- `useD4FormulaEngine.pbt.spec.ts` — P1/P2/P4/P10/P11/P13/P16/P20
- `useD4CoreComposables.pbt.spec.ts` — P3/P5/P6/P7/P8/P17
- `useD4CrossSheet.pbt.spec.ts` — P5跨sheet聚合
- `useD4AnalysisInspection.pbt.spec.ts` — P9/P12/P14/P18
- `useD4ContractInspection.spec.ts` — D4-12覆盖率/汇总/OCR
- `D4WalkthroughTest.spec.ts` — 7维度一致性引擎
- 后端：test_d4_import_export_pbt.py / test_d4_contract_ocr.py / test_d4_ipo_trigger.py / test_d4_validation_rules.py / test_d4_operating_revenue_contract.py
