# Design Document

## Overview

纯数据规格：为 F 循环 5 科目（F1 预付账款 / F2 存货 / F3 应付票据 / F4 应付账款 / F5 营业成本）创建 ~85 个 sheet-level 复核提示词 Markdown 文件 + 1 个验证脚本。

**零代码变更**——复用 D2/E1 试点已建的 ReviewPromptService / BatchReviewService / LlmResponseParser / ReviewPanel 全部基础设施。服务层通过目录扫描自动发现 `F/` 下新文件，无需注册或配置修改。

**源文件**（均位于 `backend/data/tsj_review_prompts/` 父目录）：
| 源文件 | 目标科目 |
|--------|---------|
| 预付账款审计复核提示词.md | F1 |
| 存货审计复核提示词.md | F2 |
| 应付票据审计复核提示词.md | F3 |
| 应付账款审计复核提示词.md | F4 |
| 成本审计复核提示词.md | F5 |

## Architecture

```
ReviewPromptService（已有，零改动）
    ↓ directory scan
backend/data/tsj_review_prompts/F/
    ├── F1-1-adjudication.md       ← sheet-level prompt
    ├── F1-2-detail.md
    ├── ...
    ├── F2-1-adjudication.md
    ├── F2-22-stocktake-plan.md     ← 盘点分组（共享骨架；勿用旧 F2-4 映射）
    ├── ...
    └── F5-note-soe.md
    ↓ fallback (Three_Level_Fallback)
backend/data/tsj_review_prompts/预付账款审计复核提示词.md  ← subject-level
backend/data/tsj_review_prompts/存货审计复核提示词.md
...
```

三级降级逻辑（已有服务实现）：
1. `F/{wp_code}-{sheet_suffix}.md` — sheet-level（本 spec 产出）
2. `{科目名}审计复核提示词.md` — subject-level（已存在）
3. 通用提示词 — generic（兜底）

## Components and Interfaces

### 文件树（~85 files）

```
backend/data/tsj_review_prompts/F/
├── F1-1-adjudication.md
├── F1-2-detail.md
├── F1-3-adjustment.md
├── F1-4-analysis.md
├── F1-5-aging.md
├── F1-6-policy.md
├── F1-7-voucher-check.md
├── F1-note-listed.md
├── F1-note-soe.md
├── F2-1-adjudication.md
├── F2-2-detail-summary.md
├── F2-3-raw-materials.md
├── F2-4-material-in-transit.md
├── F2-5-revolving-materials.md
├── F2-6-semi-finished.md
├── F2-7-outsourced-processing.md
├── F2-8-finished-goods.md
├── F2-9-goods-in-transit.md
├── F2-10-dev-products.md
├── F2-11-dev-costs.md
├── F2-12-contract-performance.md
├── F2-13-consumable-bio.md
├── F2-14-adjustment.md
├── F2-16-policy.md
├── F2-18-overall-analysis.md
├── F2-19-production-sales.md
├── F2-20-cost-comparison.md
├── F2-21A-stocktake-procedure.md
├── F2-21-questionnaire.md
├── F2-22-stocktake-plan.md
├── F2-23-stocktake-summary.md
├── F2-24-book-reconcile.md
├── F2-25-sample-result.md
├── F2-26-rollforward.md
├── F2-29-cutoff-inbound-voucher-to-source.md
├── F2-30-cutoff-inbound-source-to-voucher.md
├── F2-31-cutoff-outbound-voucher-to-source.md
├── F2-32-cutoff-outbound-source-to-voucher.md
├── F2-33-purchase-inbound-check.md
├── F2-34-material-usage-check.md
├── F2-35-subcontract-check.md
├── F2-38-weighted-average.md
├── F2-39-fifo.md
├── F2-40-standard-cost.md
├── F2-41-production-cost.md
├── F2-42-direct-labor.md
├── F2-43-overhead.md
├── F2-44-allocation.md
├── F2-47-impairment-nrv.md
├── F2-48-obsolete-inventory.md
├── F2-49-impairment-reversal.md
├── F2-52-related-party-purchase.md
├── F2-55A-contract-procedure.md
├── F2-55-contract-cost-detail.md
├── F2-56-contract-cost-check.md
├── F2-57-contract-impairment.md
├── F2-58-loss-contract.md
├── F2-61A-ipo-procedure.md
├── F2-61-purchase-price.md
├── F2-62 ~ F2-72（IPO 各子表，对齐 wp_code_overrides）
├── F2-note-listed.md
├── F2-note-soe.md
# 保留未实现（不写 prompt）：F2-15/17/27/28/36/37/45/46/50/51
├── F3-1-adjudication.md
├── F3-2-detail.md
├── F3-3-adjustment.md
├── F3-4-interest.md
├── F3-5-overdue.md
├── F3-6-related-party.md
├── F3-7-voucher-check.md
├── F3-note-listed.md
├── F3-note-soe.md
├── F4-1-adjudication.md
├── F4-2-detail.md
├── F4-3-adjustment.md
├── F4-4-analysis.md
├── F4-5-long-outstanding.md
├── F4-6-related-party.md
├── F4-7-unrecorded-check.md
├── F4-8-voucher-check.md
├── F4-9-supplier-financing.md
├── F4-note-listed.md
├── F4-note-soe.md
├── F5-1-adjudication.md
├── F5-2-monthly-detail.md
├── F5-3-other-cost.md
├── F5-4-adjustment.md
├── F5-5-comparative-analysis.md
├── F5-6-quantity-reconciliation.md
├── F5-7-cost-rollback.md
├── F5-8-major-adjustment.md
├── F5-note-listed.md
└── F5-note-soe.md
```

### F2 子分组（7 组，共享骨架模板）

| 子分组 | 文件范围 | 共享骨架 | 最小文件数 |
|--------|----------|----------|-----------|
| 核心 | F2-1, F2-2, F2-3 | — | 3 |
| 盘点 | F2-4 ~ F2-12 | 盘点程序骨架 | 9 |
| 截止 | F2-29 ~ F2-32 | 截止测试骨架 | 4 |
| 计价 | F2-33 ~ F2-40 | 计价测试骨架 | 8 |
| 成本分析 | F2-41 ~ F2-44 | — | 4 |
| 减值 | F2-47 ~ F2-49 | — | 3 |
| IPO | F2-61 ~ F2-68 | — | 8 |

**骨架复用方式**：同组文件头部包含共同的"审计程序框架"段落（复制而非 include），然后各文件追加 sheet 特有的检查项。

## Data Models

### 提示词文件格式规范

每个 `.md` 文件必须满足：

```markdown
# {底稿中文名}复核提示词

## 审计目标
{该 sheet 的审计认定与目标}

## 复核要点
### {要点分组 1}
- [ ] 检查项 1
- [ ] 检查项 2
...

### {要点分组 N}
- [ ] 检查项 M
```

**Lint 规则**：
1. 首行必须是 `# ` 开头的标题
2. 至少包含一个 `##` 或 `###` 分组标题
3. 每文件至少 5 个 checklist item（`- [ ]` 或 `· [ ]` 格式）
4. 文件编码 UTF-8，无 BOM

### 覆盖率期望值

| 科目 | 期望文件数 |
|------|-----------|
| F1 | ≥ 9 |
| F2 | ≥ 45 |
| F3 | ≥ 9 |
| F4 | ≥ 11 |
| F5 | ≥ 10 |
| **合计** | **≥ 84** |

## Error Handling

- **文件缺失**：Three_Level_Fallback 确保降级到 subject-level 源文件，不会 404
- **格式错误**：Lint_Script 在 CI 阶段拦截，不允许 malformed 文件进入 main
- **编码损坏**：脚本检测 UTF-8 可读性，不可读则报 malformed

## Testing Strategy

**本 spec 不适用 Property-Based Testing**——纯数据文件 + lint 脚本，无函数 I/O 行为。

测试策略：
1. **Lint_Script（check_f_review_prompts.py）** — 作为 CI 门禁：
   - 格式检查：标题/分组/checklist 密度
   - 覆盖率检查：per-subject 文件计数 vs 期望值
   - F2 子分组检查：每组最小文件数
   - Exit code 0/1 CI 兼容

2. **手工抽检** — 内容质量由 QC 合伙人审阅源拆分是否准确

### 验证脚本规格

```
backend/scripts/check/check_f_review_prompts.py
```

**验证属性（V1-V5）**：

- **V1 文件完整性**：F/ 目录下文件数 ≥ 84
- **V2 per-subject 覆盖率**：F1≥9, F2≥45, F3≥9, F4≥11, F5≥10
- **V3 F2 子分组结构**：核心≥3, 盘点≥9, 计价≥8, 截止≥4, 减值≥3, 成本分析≥4, IPO≥8
- **V4 格式 lint**：每文件 title + section + ≥5 checklist items
- **V5 checklist 密度**：平均每文件 ≥ 8 个 checklist item

**脚本输出格式**：
```
=== F-Cycle Review Prompts Validation ===
[PASS] V1: Total files: 85 (expected ≥84)
[PASS] V2: F1=9/9  F2=47/45  F3=9/9  F4=11/11  F5=10/10
[PASS] V3: F2 subgroups: 核心=3/3  盘点=9/9  计价=8/8  截止=4/4  减值=3/3  成本分析=4/4  IPO=8/8
[PASS] V4: Lint: 85/85 files pass format check
[PASS] V5: Density: avg 12.3 items/file (min 5)

Result: ALL PASS (exit 0)
```
