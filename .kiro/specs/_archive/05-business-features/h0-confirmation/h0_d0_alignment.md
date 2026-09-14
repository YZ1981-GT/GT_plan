# H0 ↔ D0 函证架构对齐说明

> Phase 0 产物。H0 固定资产循环函证与 D0 收入循环函证共享同一套 **confirmation-hub + 9 类 componentType** 框架；H0 仅新建 **H0-5 替代程序** 一个循环特有组件。

## 1. Sheet 级映射（铁律：跨循环共享）

| # | H0 sheet（xlsx） | wp_code | 对标 D0 | 目标 componentType | 实现方式 |
|---|------------------|---------|---------|-------------------|----------|
| 1 | 底稿目录 | — | 底稿目录 | `b-index` | 复用（account_package 合成目录） |
| 2 | 函证程序表H0A | H0A | D0A | `a-program-console` | 复用 GtAProgramConsole |
| 3 | 函证结果汇总表H0-1 | H0-1 | D0-1 | `confirmation-summary` | 复用 GtConfirmationSummary |
| 4 | 核实被函证单位信息H0-2 | H0-2 | D0-2 | `confirmation-entity-verify` | 复用 GtConfirmationEntityVerify |
| 5 | 跟函函证过程控制H0-3 | H0-3 | D0-3 | `confirmation-followup` | 复用 GtConfirmationFollowup |
| 6 | 差异核对表H0-4 | H0-4 | D0-4 | `confirmation-diff-reconcile` | 复用 GtConfirmationDiffReconcile |
| 7 | 替代程序H0-5 | H0-5 | D0-5 | `confirmation-alternative-h05` | **新建**（壳层复用 D0-5） |
| 8 | 邮件传真回函可靠性验证H0-6 | H0-6 | D0-7 | `confirmation-reliability` | 复用 GtConfirmationReliability |
| 9 | 函证程序舞弊风险评价表H0-7 | H0-7 | D0-8 | `confirmation-fraud-risk` | 复用 GtConfirmationFraudRisk |

**H0 无对标 sheet**（D0 有、H0 无）：

| D0 | componentType | 说明 |
|----|---------------|------|
| D0-4b / 差异检查表示例 | `confirmation-diff-checklist` | H0 模板无此 sheet（同 G0） |
| D0-6 | `confirmation-alternative-d06` | 收入循环第二替代程序；H0 仅 1 个替代程序 |

## 2. 当前代码缺口（2026-07-05 盘点）

| 项 | 期望（对齐 D0） | 现状 | 优先级 |
|----|----------------|------|--------|
| `wp_code_overrides.json` H0-1~H0-7 | `confirmation-*` | ✅ 已修正（2026-07-05） | — |
| `account_package_registry.json` H0 包 | 9 sheet 聚合 | ✅ 已注册 | — |
| `H0.yaml` component_type | confirmation-* | 草稿仍为 d-form-* / a-program-console | P1 |
| `confirmation-alternative-h05` | 注册 + Vue 组件 | **未实现** | P1 |
| `ConfirmationTabs` / hub 路由 | H0-5 → h05 | 依赖 overrides 修正后生效 | P1 |

## 3. H0-5 对标 D0-5 的实现策略（参照 F0-5）

F0-5 已验证模式：**不 fork D0-5 壳组件**，仅替换列配置与 payload `_format`：

```
alternativeD05/
  AlternativeD05Dashboard.vue   ← H05 直接复用
  AlternativeD05Master.vue    ← H05 直接复用
  CheckBlock.vue              ← H05 直接复用（读 blockColumnConfigsH05）
  alternativeD05Types.ts      ← CheckRow / AlternativeCompany 复用

alternativeH05/
  GtConfirmationAlternativeH05.vue   # 薄壳，参照 GtConfirmationAlternativeF05.vue
  blockColumnConfigsH05.ts           # 4 区块列定义（固定资产循环）
  alternativeH05Types.ts             # _format: alternative-h05-v1
  composables/useAlternativeH05Data.ts
```

## 4. H0-5 四区块（Phase 0 暂定，待 openpyxl 实读确认）

| 区块 | 标题 | 记账凭证列（固定 5 列） | 检查证据列（H 循环特有） |
|------|------|------------------------|-------------------------|
| ① | 期后验收/权属证据检查 | 日期/凭证编号/业务内容/对方科目/金额 | 验收单日期编号/资产名称/规格型号/数量 \| 权属证书编号/权属人/取得日期 \| 索引号/是否异常 |
| ② | 期末余额支持性证据 | 同上 | 采购合同日期编号/供应商/合同金额 \| 采购发票日期编号/金额 \| 付款凭证日期/金额/索引号/是否异常 |
| ③ | 本期新增资产检查 | 同上 | 请购审批单日期编号/是否恰当审批 \| 到货验收单日期/资产名称/数量 \| 转固日期/原值/索引号/是否异常 |
| ④ | 抵押担保/融资租赁证据 | 同上 | 抵押合同编号/抵押权人/担保金额 \| 融资租赁合同编号/出租方/租赁期 \| 他项权证编号/索引号/是否异常 |

## 5. 跨底稿联动（H 循环特有）

| 方向 | 机制 | 对标 D0 |
|------|------|---------|
| H0-1 未回函 → H0-5 | `importFromSummary` + EventBus `confirmation:updated` | D0-1 → D0-5 |
| H0-5 ↔ H1 抵押 | ref_index / GtIndexChip | — |
| H0-5 ↔ L1/L3 借款抵质押 | ref_index chip 跳转 | — |
| 函证完成 → H1/H2 明细 | EventBus `confirmation:completed` | D0 → D2-2 |

## 6. 后端端点命名（对齐 F0/G0）

```
POST /api/workpapers/{wp_id}/h0/export-template?sheet=H0-5
POST /api/workpapers/{wp_id}/h0/export-data?sheet=H0-5
POST /api/workpapers/{wp_id}/h0/import-data?sheet=H0-5
POST /api/workpapers/{wp_id}/h0/ai/{section}
# section: alternative-audit-note | alternative-audit-conclusion
```
