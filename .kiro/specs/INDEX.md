# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-06-29
**当前分支**：`work/2026-05-30-wp-specs`
**Spec 总数**：**229**（active 10 + archived 219）
**当前 active = 10**（3 全局治理 + 6 D1拆分 + 1 通用复核对话）
**最高迁移**：V094
**测试总数**：~17500+（含 PBT 40+ properties）
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

---

## 一、Active Specs（10个）

### 全局治理（3，未启动）

| Spec | 说明 |
|------|------|
| `display-format-single-source` | P0金额/时间/百分比格式化收口displayPrefs+CI守卫 |
| `cycle-palette-single-source` | P0循环色板单一真源cyclePalette.ts+--gt-cycle-* |
| `stale-propagation-cleanup-doc` | P2删死代码+分层文档 |

### D1应收票据拆分（6，三件套齐全待执行）

| Spec | 覆盖Sheet | 需求 | Property |
|------|-----------|------|----------|
| `d1-adjudication-table` | D1-1/2/3/4 审定+明细+坏账 | 11 | — |
| `d1-disclosure-note` | 附注披露(上市+国企) | 20+2 | — |
| `d1-endorsement-discount` | D1-6/7/8/9 业务模式+备查簿+贴现+贴息 | 18 | — |
| `d1-inspection-check` | D1-10/11/12/13 监盘+关联方+质押+抽样 | 20 | 8 |
| `d1-ecl-provision` | D1-14/15 政策检查+ECL测算 | 18 | 8 |
| `d1-writeoff-check` | D1-16 坏账转回+核销 | 14 | 6 |

### 通用组件（1，三件套齐全待执行）

| Spec | 说明 |
|------|------|
| `audit-review-dialog` | 通用审计复核对话(GtReviewDialog+后端V095) 13需求14P39任务 |

---

## 二、已归档 Spec（219个，14 分类）

```
_archive/
├── 01-phase-foundation/         24
├── 02-workpaper-cycles/         16
├── 03-refinement-rounds/         9
├── 04-infra-architecture/       29
├── 05-business-features/        40   (+word-template-dual-mode)
├── 06-engineering-governance/    6
├── 07-workpaper-slimdown/       15
├── 08-disclosure-notes/          5
├── 09-consolidation-phases/      4
├── 10-A~S-workpaper-all-cycles-complete/ 13
├── 11-confirmation-d0-module/   10
├── 12-2026-06-23-batch/         12
├── 13-2026-06-29-batch/         33   (A类专属+B类专属+C控制+D1/D2+聚合bundle)
└── 99-superseded/                5   (+b40-sampling-strategy)
```

### 13-2026-06-29-batch/（33个，本轮归档）

| Spec | 类型 | 任务 | 测试 |
|------|------|------|------|
| a1-11-signing-control-form | A类专属 | 26/26 | 39 PBT+vitest |
| a1-12-dual-mode-checklist | A类专属 | 9/9 | 99 |
| a1-15-disclosure-checklist | A类专属 | 10/10 | 111 |
| a1-dashboard-bundle-upgrade | Bundle | 14/14 | — |
| a10-1-governance-communication | A类专属 | 22/22 | 77 |
| a11-1-subsequent-events-inquiry | A类专属 | 17/17 | 103 |
| a12-1-legal-confirmation | A类专属 | 19/19 | 91 |
| a16-representation-bundle | Bundle | 11/11 | — |
| a17-1-audit-summary | A17专属 | 22/22 | 85 |
| a17-2-1-kam | A17专属 | 18/18 | 92 |
| a17-3-consultation-record | A17专属 | 16/16 | 88 |
| a17-3-1-consultation-execution | A17专属 | 16/16 | 69 |
| a17-4-disagreement-record | A17专属 | 17/17 | 75 |
| a17-6-closing-meeting | A17专属 | — | — |
| a17-7-independence-declaration | A17专属 | 22/22 | 102 |
| a17-audit-summary-bundle | Bundle | 17/17 | — |
| a18-1-regulatory-submission | A类专属 | 15/15 | 26 |
| a18-2-regulatory-communication | A类专属 | 15/15 | 80 |
| a27-1-it-audit-memo | A类专属 | 22/22 | 83 |
| a3-8-goodwill-impairment | A3合并 | 9/9 | 47 |
| a5-1-cashflow-audit | A类专属 | 22/22 | 57 |
| a8-1-other-info-representation | A类专属 | 17/17 | 106 |
| a9-1-deficiency-letter | A类专属 | 22/22 | 84 |
| a9-2-deficiency-letter-governance | A类专属 | 13/13 | 119 |
| b1-4-due-diligence-report | B类专属 | 24/24 | 97 |
| b22a-control-matrix | B类专属 | 38/38 | 48 |
| b22b-deficiency-evaluation | B类专属 | 42/42 | 57 |
| b23-process-control | B类专属 | 59/59 | 79 |
| b30-group-audit | B类专属 | 25/25 | 37 |
| b50-risk-assessment | B类专属 | 35/35 | 32 |
| c-control-test-component | C类控制 | 25/25 | — |
| d1-notes-receivable | D类专属 | 76/76 | 102 |
| d2-accounts-receivable | D类专属 | 76/76 | 103 |

---

## 三、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| 最高迁移 | `ls backend/migrations/V*.sql | sort | tail -1` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 四、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 归档移到 `_archive/{分类}/`，同步更新本文件
3. 分类：01地基 / 02循环 / 03打磨 / 04架构 / 05业务 / 06工程 / 07底稿瘦身 / 08附注 / 09合并 / 10全循环 / 11函证 / 12 2023-06-23批 / 13 2026-06-29批 / 99取代
4. **凭印象禁令**：完成度必须实证
5. 迁移系统 = `backend/migrations/V*.sql`（MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
