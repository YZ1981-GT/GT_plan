# Requirements Document: H0 固定资产循环函证

## Introduction

H0 固定资产循环函证，覆盖科目：固定资产 / 在建工程 / 工程物资 / 使用权资产 / 租赁负债 / 长期资产权属等的第三方函证确认（银行借款抵押物、在建工程进度、融资租赁、权属证明）。源模板 1 个 xlsx、9 个 sheet。

**核心架构决策（对齐 D0 实际实现 + F0/G0/L0 pattern）**：

- 函证模块是**跨循环共享**的 componentType 族；D0/E0/F0/G0/H0/K0/L0 全部复用（铁律：不为每循环重复开发 summary/verify/followup 等）
- H0-1~H0-4 / H0-6 / H0-7 **直接映射**到 D0 已有共享组件（见 `h0_d0_alignment.md`）
- **仅 H0-5 需要新建**：`confirmation-alternative-h05`（固定资产循环替代程序，4 区块，参照 D0-5）
- H0A 程序表复用 `a-program-console`；H0 根底稿复用 `confirmation-hub`

**与 D0 的差异**：

| 维度 | D0（收入循环） | H0（固定资产循环） |
|------|---------------|-------------------|
| 替代程序数量 | D0-5 + D0-6（2 个） | H0-5（1 个） |
| 差异检查表示例 | D0-4b → diff-checklist | 无 |
| 可靠性/舞弊编号 | D0-7 / D0-8 | H0-6 / H0-7 |
| H0-5 区块主题 | 合同负债/销售/收款/出库 | 权属/余额证据/新增资产/抵押融资租赁 |
| 跨底稿联动 | D2/D4/D6 应收收入 | H1/H2 固定资产、L1/L3 借款抵质押 |

**源模板 sheet 清单**：

| # | Sheet 名 | 行×列 | wp_code | componentType | 新建/复用 |
|---|----------|-------|---------|---------------|-----------|
| 1 | 底稿目录 | — | — | b-index | 复用 |
| 2 | 函证程序表H0A | — | H0A | a-program-console | 复用 |
| 3 | 函证结果汇总表H0-1 | 69×33 | H0-1 | confirmation-summary | 复用 D0-1 |
| 4 | 核实被函证单位信息H0-2 | 41×40 | H0-2 | confirmation-entity-verify | 复用 D0-2 |
| 5 | 跟函函证过程控制H0-3 | 37×18 | H0-3 | confirmation-followup | 复用 D0-3 |
| 6 | 差异核对表H0-4 | 21×9 | H0-4 | confirmation-diff-reconcile | 复用 D0-4 |
| 7 | 替代程序H0-5 | 35×29 | H0-5 | confirmation-alternative-h05 | **新建** |
| 8 | 邮件传真回函可靠性验证H0-6 | 39×20 | H0-6 | confirmation-reliability | 复用 D0-7 |
| 9 | 函证程序舞弊风险评价表H0-7 | 31×10 | H0-7 | confirmation-fraud-risk | 复用 D0-8 |

## Glossary

- **confirmation-hub**: 函证统一入口（ConfirmationHub + ConfirmationTabs），`H0` wp_code 触发，按子 sheet 路由
- **D0 共享组件**: D0 spec 已完成的 9 类跨循环 componentType（summary / entity-verify / followup / diff-reconcile / diff-checklist / reliability / fraud-risk + alternative-xxx）
- **替代程序**: 对未回函被询证单位执行的审计程序；H0-5 为 4 区块 Master-Detail 宽表（对标 D0-5）
- **合计行**: 每区块底部 SUM 金额列，由 `calcBlockTotal` 计算

## Requirements

### Requirement 1: H0 overrides 映射对齐 D0（配置层）

**User Story:** As a 开发者, I want to H0 各 sheet 映射到 D0 共享组件, so that H0 函证底稿获得与 D0 相同的专属渲染。

#### Acceptance Criteria

1. THE `wp_code_overrides.json` SHALL 包含完整映射（9 条 wp_code）：
   - H0→confirmation-hub
   - H0A→a-program-console
   - H0-1→confirmation-summary
   - H0-2→confirmation-entity-verify
   - H0-3→confirmation-followup
   - H0-4→confirmation-diff-reconcile
   - H0-5→confirmation-alternative-h05
   - H0-6→confirmation-reliability
   - H0-7→confirmation-fraud-risk
2. THE `account_package_registry.json` SHALL 包含 H0 包（7 业务 sheet + 合成底稿目录，顺序同 xlsx）
3. THE `H0.yaml` render schema SHALL 将各 sheet 的 `component_type` 修正为上表（脱离 d-form-table 草稿）
4. THE 底稿目录 SHALL 映射到 `b-index`（account_package 合成）

### Requirement 2: H0-5 固定资产循环替代程序（新建，参照 D0-5）

**User Story:** As a 审计助理, I want to 对未回函的固定资产/在建工程/抵押担保执行替代程序, so that 我能获取充分适当的存在性/权属/计价证据。

#### Acceptance Criteria

1. THE H0-5 SHALL 注册 componentType `confirmation-alternative-h05`
2. THE H0-5 SHALL 多公司 Master-Detail（一公司一检查表，**壳层复用** D0-5 的 Dashboard/Master/CheckBlock，参照 F0-5）
3. THE H0-5 SHALL 顶部余额汇总区：函证项目(固定资产/在建工程) | 年初/借方/贷方/期末 + 本期新增金额 | 权属证据检查比例 | 期后验收检查比例
4. THE H0-5 SHALL 抽样参数区（测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程，6 字段 textarea）
5. THE H0-5 四区块 SHALL（每区块独立 el-table 动态行）：
   - ① 期后验收/权属证据检查
   - ② 期末余额支持性证据（合同/发票/付款凭证）
   - ③ 本期新增资产检查
   - ④ 抵押担保/融资租赁证据
6. THE H0-5 每区块 SHALL 左右视觉分组（记账凭证 5 列 | 检查证据 N 列）
7. THE H0-5 SHALL 每区块合计行 + 索引号列(GtIndexChip) + 是否异常列
8. THE H0-5 SHALL 支持从 H0-1 带入未回函公司（`importFromSummary`，对标 D0-1→D0-5）
9. THE H0-5 SHALL 支持增删行、行级 OCR（`/d4/contract-ocr`）、导入导出
10. THE H0-5 SHALL 底部审计说明 + 审计结论 textarea（AI 辅助）
11. THE H0-5 SHALL ref_index 可跳转 H1 抵押明细、L1/L3 借款抵质押

### Requirement 3: Composable 与导入导出（对标 F0/G0）

1. THE H0-5 SHALL 有 `useAlternativeH05Data.ts`（4 区块 CRUD + loadAll/persistAll，payload `_format: alternative-h05-v1`）
2. THE H0-5 SHALL 有 `useH0ImportExport.ts`（三端点：export-template / export-data / import-data）
3. THE 后端路径 SHALL 为 `/api/workpapers/{wp_id}/h0/...?sheet=H0-5`
4. THE 导出模板 SHALL 4 区块 → 4 个 Excel sheet（含列头与填写说明）

### Requirement 4: 注册契约

1. `confirmation-alternative-h05` ∈ VALID_COMPONENT_TYPES
2. htmlRendererRegistry 含 h05 → GtConfirmationAlternativeH05
3. RENDERER_DISPATCH 含 h05 render 策略（返回 checklist_responses snapshot）

### Requirement 5: 公式引擎

1. `calcBlockTotal(amounts)` — Σ 金额，空数组 → 0
2. `calcCheckRatio(checked, balance)` — balance≤0 → 0
3. `calcRowVariance(book, evidence)` — book − evidence
4. `isAbnormal(variance)` — |variance| > 0

### Requirement 6: 版本链

1. GtConfirmationAlternativeH05 集成 useVersionTrail（保存后 autoSnapshot）
2. 工具栏「版本历史」→ GtWpVersionTrail drawer

### Requirement 7: 复用 D0 共享组件（零新代码）

1. H0-1~H0-4 / H0-6 / H0-7 仅通过 overrides 映射，**不新建 Vue 文件**
2. confirmation-hub 按 wp_code 自动路由 H0 系列各 sheet

## Correctness Properties

**P1** — calcBlockTotal(amounts) === Σ amounts；[] → 0

**P2** — calcCheckRatio(checked, balance) === balance>0 ? checked/balance : 0

**P3** — calcRowVariance(book, evidence) === book − evidence；calcRowVariance(v,v) === 0

**P4** — isAbnormal(calcRowVariance(b,e)) === (b ≠ e)
