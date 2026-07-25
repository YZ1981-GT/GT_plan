# Design Document

## Overview

把「审计检查」从「精细化提取快照旁路展示」升级为「反映最新编制成果、聚合平台运行时校验源、可收口的复核检查面板」。

**用户已确认的三项关键决策（据本会话）**：

1. **单一缓存一处读（聚合口径 a）**：无论检查由后端计算还是前端上报，最终都写进底稿 `parsed_data` 的统一字段，`summary` 端点一处读合并结果。不在前端旁路拼装多源。
2. **签认只提示不阻断**：存在阻断项（`severity=blocking` 且 `passed=false`）时签认前明确提示，但不禁止签认、不阻断完成复核推进。
3. **覆盖全部 10 条需求**（分 M0-M3 迁移阶段落地）。

**核心设计判断（据 codegraph 调研，非臆测）**：

- 平台运行时校验源分两类：
  - **后端可计算**（聚合器直接算）：精细化检查 `fine_checks`（Excel/OnlyOffice）、审定↔明细↔TB 勾稽（`cycle_review_context`/`d2_review_context`，覆盖 K1-K13/N1-N5/D2）、附注校验（`NoteValidationEngine.validate_all`）、QC 28 条（`QCEngine`）、未更正错报（`UnadjustedMisstatementService.list_misstatements`）。
  - **纯前端 composable、后端无等价**：`tbReconcile`/`adjustmentReconcile`/`useReportCrossCheck`/`useXCrossSheet`（D1/D3-D7/E/F/G/H/I/J/L/M 大部分循环）。这些在编制态由前端 computed 产出。
- 要满足决策 1「一处读」，采用**双通道写入同一缓存**：后端可算真源由聚合器算并写；前端 composable 真源由前端在保存/进入面板时**上报**（`report` 端点 upsert），后端按 `source` 命名空间存入同一 `parsed_data.audit_checks`。`summary` 端点读合并结果——满足「后端统一写缓存、一处读」，同时不臆造后端算不了的前端勾稽。
- 保留 legacy `fine_checks`/`fine_summary`/`fine_extracted_at` 字段与其读取路径（QC-27/28、既有消费者）**逐字节不变**；新增独立字段 `audit_checks`/`audit_checks_at`，聚合器把 `fine_checks` 归并为 `audit_checks` 中 `source=fine_rule` 的子集，二者并存零回归。

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│ 前端 AuditCheckDashboard.vue（复核收口面板）                            │
│  · GET  /audit-checks/summary          读合并 checks + 新鲜度 + 汇总    │
│  · POST /audit-checks/recompute        主动重算（全部/单张）           │
│  · POST /audit-checks/export           导出 xlsx 留痕                   │
│  · POST /audit-checks/signoff          复核签认（只提示不阻断）        │
│  · 点击 check → 复用 GtWpRenderer 跳转定位到底稿 sheet                  │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
        ┌────────────────────────┴───────────────────────────┐
        │ 前端底稿组件（编制态）                                │
        │  保存/进入面板时上报 composable 真源判定：            │
        │  POST /workpapers/{wp_id}/audit-checks/report        │
        │  （tbReconcile/adjustmentReconcile/reportCrossCheck/ │
        │    useXCrossSheet → 统一 AuditCheckItem[]）           │
        └────────────────────────┬───────────────────────────┘
                                 │ 写入同一缓存（source 命名空间）
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│ 后端 AuditCheckAggregator（新服务）                                     │
│  recompute_project(db, pid, year) / recompute_workpaper(db, wp)         │
│  ├─ (S1) fine_checks         ← 既有 parsed_data.fine_checks（Excel）    │
│  ├─ (S2) cycle_recon         ← cycle_review_context/d2_review_context  │
│  ├─ (S3) note_validation     ← NoteValidationEngine.validate_all       │
│  ├─ (S4) qc                  ← QCEngine（阻断/警告）                    │
│  ├─ (S5) unadjusted_misstat  ← UnadjustedMisstatementService           │
│  └─ (S6) reported            ← 前端上报的 composable 真源（不重算）     │
│  合并 + 去重（同一勾稽单一口径）→ 写 parsed_data.audit_checks/_at       │
└───────────────────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
        WorkingPaper.parsed_data.audit_checks (统一缓存, 一处读)
        audit_check_signoff 表 (V126, 签认留痕)
```

**数据流**：编制态前端 composable 判定 → 上报写缓存（S6）；后端可算真源由聚合器 `recompute` 时算并写（S1-S5）；`summary` 端点合并读出 + 新鲜度标记；前端展示按循环分组 + 通过率区分已判定/未覆盖 + 跳转/筛选；导出留痕；签认记快照。

## Components and Interfaces

### 1. 后端 — 统一检查项模型 `AuditCheckItem`

```python
# app/services/audit_check/models.py
@dataclass
class AuditCheckItem:
    code: str                    # 检查项编号（源内唯一，如 "K9-RECON-01" / "D2-CHK-03" / "QC-27"）
    source: str                  # 来源：fine_rule|cycle_recon|note_validation|qc|
                                 #       unadjusted_misstatement|tb_recon|adjustment_recon|
                                 #       report_cross_check|cross_sheet
    wp_code: str                 # 归属底稿编码（项目级来源用 "__PROJECT__"）
    wp_id: str | None            # 归属底稿 id（项目级为 None）
    sheet_hint: str | None       # 跳转定位用的 sheet 名/编码（可空）
    severity: str                # blocking|warning|info
    check_type: str              # balance|cross_ref|reconciliation|note|qc|misstatement|...
    description: str             # 检查项描述
    passed: bool | None          # true=通过 / false=未通过 / null=未覆盖(pending)
    actual: float | None
    expected: float | None
    diff: float | None
    message: str
    produced_at: str             # ISO8601，本项判定时间（新鲜度）
```

统一字典结构与 legacy `fine_checks` 项**字段超集兼容**（`fine_checks` 项没有 `source/wp_code/wp_id/sheet_hint/produced_at`，聚合时补齐 `source=fine_rule`），故前端可统一渲染。

### 2. 后端 — 聚合服务 `AuditCheckAggregator`

```python
# app/services/audit_check/aggregator.py
class AuditCheckAggregator:
    async def recompute_workpaper(self, db, wp, idx, *, year) -> list[AuditCheckItem]:
        """对单张底稿重算后端可算真源(S1-S5 中 per-wp 部分) + 保留已上报(S6)，
        合并去重后写 wp.parsed_data['audit_checks'] / ['audit_checks_at']。"""

    async def recompute_project(self, db, project_id, year) -> ProjectCheckSummary:
        """遍历项目底稿逐张 recompute_workpaper；
        额外产出项目级真源(S3 note_validation 汇总 / S5 未更正错报)挂到 __PROJECT__ 分组。"""
```

**各来源适配（复用既有服务，不新造判定口径 — Req4.2）**：

| 来源 | 复用的既有服务/字段 | 适配为 AuditCheckItem |
|------|---------------------|----------------------|
| S1 fine_rule | `parsed_data.fine_checks`（既有，Excel/OnlyOffice） | 逐项补 `source=fine_rule`/`wp_code`/`produced_at=fine_extracted_at` |
| S2 cycle_recon | `cycle_review_context._REGISTRY` 判定逻辑（审定↔明细↔TB，K/N）+ `d2_review_context`（D2） | 抽出结构化判定（非文本 prompt）产 3 项：审定↔明细、审定↔TB、未审→审定幅度（info） |
| S3 note_validation | `NoteValidationEngine.validate_all(project_id, year)` | findings → check（passed 由 finding 是否通过决定；skip→null 未覆盖） |
| S4 qc | `QCEngine`（含 QC-27/28 fine_check 规则） | 每条 QCFinding → check（severity 对齐） |
| S5 unadjusted_misstatement | `UnadjustedMisstatementService.list_misstatements(project_id, year)` | 有未更正错报 → warning 提示项（项目级 __PROJECT__） |
| S6 reported | 前端上报（`report` 端点写入的 `parsed_data.audit_checks` 中 `source∈{tb_recon,adjustment_recon,report_cross_check,cross_sheet}` 项） | 直接保留，recompute 时不清除（仅清除自身 source S1-S5） |

**S2 结构化抽取**：`cycle_review_context` 现产出文本 prompt + `alerts`。design 在其模块内**新增结构化产出函数** `build_cycle_reconciliation_findings(wp_id, wp_code) -> list[dict]`（与文本版共用同一 `_REGISTRY` 与计算，返回 `{code,passed,actual,expected,diff,message,severity}`），文本版改为调用它再格式化 → **单一判定口径**，AI 复核与审计检查面板共用（避免第三套口径）。

**去重（Req4.3 / P5）**：同一勾稽同时被 S1（fine_rule 的 balance CHK-01「审定↔TB」）和 S2（cycle_recon 的审定↔TB）覆盖时，按优先级 `cycle_recon > fine_rule`（cycle_recon 读 checklist_responses + trial_balance 为专属组件最新态，fine_rule 读 Excel 快照可能陈旧）保留一条，另一条丢弃。去重键 = `(wp_code, 归一化勾稽语义)`。

### 3. 后端 — 端点（`app/routers/audit_check.py`）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/projects/{pid}/audit-checks/summary` | 项目只读 | 读合并 checks + 每底稿 `checked_at`/`updated_at`/`stale`/`never_checked` + 项目汇总 |
| POST | `/api/projects/{pid}/audit-checks/recompute` | 编制权（可选 body `wp_id` 单张） | 触发聚合器重算，完成返回新汇总 |
| POST | `/api/projects/{pid}/workpapers/{wp_id}/audit-checks/report` | 编制权 | 前端上报 composable 真源，按 source 命名空间 upsert |
| POST | `/api/projects/{pid}/audit-checks/export` | 导出权 | 生成 xlsx，RFC5987 中文名 |
| POST | `/api/projects/{pid}/audit-checks/signoff` | 复核权 | 记签认（快照+人+时间），返回是否含未处理阻断项（只提示） |
| GET | `/api/projects/{pid}/audit-checks/signoff` | 项目只读 | 读最近一次签认 |

**`summary` 向后兼容（P13）**：底稿无 `audit_checks` 字段时退回读 legacy `fine_checks` 展示（补 `source=fine_rule`），保证升级前旧缓存仍可见。旧端点 `GET /fine-checks/summary` 保留不删（QC/既有消费者），新面板改用 `audit-checks/summary`。

### 4. 后端 — 单一新鲜度口径

`summary` 每底稿返回 `checked_at`（`audit_checks_at` 或 legacy `fine_extracted_at`）、`updated_at`（`WorkingPaper.updated_at`）、`stale = updated_at > checked_at`、`never_checked = checked_at is None`。前端不自算陈旧，直接用后端标记（Req1.4）。

### 5. 前端 — `AuditCheckDashboard.vue` 改造

- 数据源改 `GET /audit-checks/summary`；汇总卡增「未覆盖」列与「已判定通过率」（分母不含 null）。
- 每底稿标题显示 `checked_at` + 陈旧/未检查 tag；顶部「重新检查全部」+ 每底稿「重新检查」按钮（`recompute`，进行中禁重复）。
- check 行显示 `source` 标签（来源芯片）；点击未通过项经 `router.push` + `?sheet=` 跳转到底稿（复用既有 `GtWpRenderer initial-sheet` 定位机制，无 sheet_hint 则不可跳并提示）。
- 顶部筛选（全部/未通过/未覆盖/阻断）+ 未通过与阻断项默认置顶排序。
- 「导出」「复核签认」按钮（按权限显隐）；签认前若有阻断项弹提示确认（不阻断）。
- `CYCLE_NAMES` 与依赖图循环列表补 `M: '权益循环'`；依赖图循环列表改为由实际有数据的循环动态生成（Req9.2）。

### 6. 前端 — 上报 composable `useAuditCheckReport`

```ts
// 底稿组件在保存成功后 / 面板触发批量上报时调用
reportAuditChecks(projectId, wpId, items: AuditCheckItemInput[])
// items 由底稿现有 composable 的判定结果映射（tbReconcile/adjustmentReconcile/
// reportCrossCheck/crossSheet），source 明确，不新造判定
```

首版接入试点：D2/K/N 已由后端 S2 覆盖无需上报；上报机制在 **G 循环（有 useReportCrossCheck）+ 若干审定表（tbReconcile/adjustmentReconcile）** 试点，其余循环暂由 Req5「未覆盖」口径如实呈现，后续增量铺开（避免一次改几十个底稿）。

## Data Models

### `WorkingPaper.parsed_data`（新增字段，不改表结构）

```jsonc
{
  "fine_checks": [...],          // legacy，保留不动
  "fine_summary": {...},         // legacy，保留不动
  "fine_extracted_at": "...",    // legacy，保留不动
  "audit_checks": [ AuditCheckItem, ... ],   // 新：合并后的统一检查项
  "audit_checks_at": "2026-07-25T..."        // 新：本底稿最近聚合时间
}
```

### `audit_check_signoff` 表（迁移 V126，取号前以 `migration_status` 复核最高号）

```sql
CREATE TABLE IF NOT EXISTS audit_check_signoff (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL,
    year         INT  NOT NULL,
    signed_by    UUID NOT NULL,
    signed_by_name VARCHAR(100),
    signed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary_snapshot JSONB NOT NULL,   -- {decided,passed,failed,uncovered,pass_rate,blocking_count}
    blocking_present BOOLEAN NOT NULL DEFAULT false,
    note         TEXT,
    is_deleted   BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_audit_check_signoff_proj_year
    ON audit_check_signoff(project_id, year) WHERE is_deleted = false;
```

`summary_snapshot` 记签认当时的项目汇总（P10）；`blocking_present` 记签认时是否有未处理阻断项（只提示不阻断，Req8.3/P14）。

### 项目汇总 `ProjectCheckSummary`

```python
@dataclass
class ProjectCheckSummary:
    total: int          # 全部检查项
    decided: int        # passed 非 null
    passed: int
    failed: int
    uncovered: int      # passed == null
    pass_rate: float    # passed / decided（分母不含 uncovered；decided=0 时为 None/0 并标注）
    blocking_open: int  # severity=blocking 且 passed=false
```

## Correctness Properties

### Property 1: 通过率分母不含未覆盖
对任意 checks 集合，`pass_rate` 分母为已判定数（`passed ∈ {true,false}`），未覆盖项（`passed=null`）不进分母也不进分子。
**Validates: Requirements 5.2**

### Property 2: 未覆盖存在时不呈现"全部通过"
WHEN `uncovered > 0`，THEN 汇总不产出「全部通过/全绿」类整体结论字段。
**Validates: Requirements 5.4**

### Property 3: 陈旧判定单调
`stale == (updated_at > checked_at)`；`checked_at is None ⇒ never_checked == true 且 stale == false`。
**Validates: Requirements 1.2, 1.3**

### Property 4: 未检查底稿不计通过率
从未产生检查结果的底稿不贡献任何 check 项到通过/未通过统计，仅计入「未检查」标记。
**Validates: Requirements 1.3, 5.1**

### Property 5: 同一勾稽单一口径
对同一 `(wp_code, 勾稽语义)`，合并后至多一条 check 项（去重优先级 `cycle_recon > fine_rule`）。
**Validates: Requirements 4.3**

### Property 6: 上报按 source 命名空间替换
同一底稿同一 `source` 再次上报时，覆盖该 source 旧项，不累积重复；`recompute` 只清除后端自算 source（S1-S5），不清除已上报 source（S6）。
**Validates: Requirements 4.1, 3.3**

### Property 7: 聚合 fail-open
任一来源（S1-S6）计算/读取异常时被隔离，不影响其余来源产出；异常来源相关项标记为未覆盖而非误判通过。
**Validates: Requirements 4.5, 2.4**

### Property 8: 重算不改底稿数据
`recompute` 仅写 `parsed_data.audit_checks`/`audit_checks_at`，不修改 checklist_responses / 底稿其他字段 / 表结构。
**Validates: Requirements 3.4, 2.1**

### Property 9: 来源标注完整
合并后每个 check 项 `source` 非空且属枚举集合。
**Validates: Requirements 4.4**

### Property 10: 签认快照一致
签认记录的 `summary_snapshot` 等于签认时刻 `summary` 端点计算的项目汇总。
**Validates: Requirements 8.2**

### Property 11: 循环覆盖含 M
分组循环集合包含 `M`（权益循环）；无数据循环显式呈现「暂无检查数据」而非省略。
**Validates: Requirements 9.1, 9.3**

### Property 12: 权限零回归
`summary`/`signoff GET` 仅需项目只读；`recompute`/`report`/`export`/`signoff POST` 按对应角色校验；均不放宽既有授权。
**Validates: Requirements 10.1, 7.4, 2.5, 8.4**

### Property 13: 向后兼容
底稿无 `audit_checks` 字段时，`summary` 退回读 `fine_checks` 展示（补 `source=fine_rule`），不报错。
**Validates: Requirements 10.4**

### Property 14: 阻断项只提示不阻断
存在未处理阻断项时，`signoff` 仍可成功执行（记 `blocking_present=true`），仅在响应/前端提示，不拒绝签认。
**Validates: Requirements 8.1, 8.3**

## Error Handling

- **聚合器**：每个来源 S1-S6 独立 try/except，异常记 warning 并将该来源相关检查标记未覆盖（`passed=null`），绝不整体失败（P7）。
- **前端上报**：`report` 端点校验 `source ∈ 前端可上报枚举`（拒绝伪造后端专属 source），非法 source 返 400。
- **重算并发**：同项目重算加去重/幂等保护，进行中重复触发返当前进行态，不重复启动。
- **跳转**：`sheet_hint` 为空或解析不到底稿目标 → 前端保持不可跳并提示，不导航到错误底稿（Req6.2）。
- **导出**：无检查数据时导出空模板并提示，不报错。
- **签认无数据**：项目无任何检查结果时签认给出提示但仍记录（快照 decided=0）。

## Migration Phases

- **M0（数据模型 + 后端可算聚合骨架）**：`AuditCheckItem`/`AuditCheckAggregator` 骨架 + S1(fine_rule 归并)+S2(cycle_recon 结构化) + `parsed_data.audit_checks` 字段 + `summary` 端点（含新鲜度 Req1）+ 向后兼容（P13）。覆盖 Req1、Req5（通过率口径）、Req3（K/N/D2 专属组件经 S2 覆盖）、Req4 部分。
- **M1（展示 + 定位）**：Dashboard 改造（未覆盖列/来源芯片/陈旧标记）+ 跳转定位（Req6）+ 筛选置顶 + 循环补 M（Req9）+ 「重新检查」按钮触发 `recompute`（Req2）。
- **M2（聚合更多真源 + 前端上报）**：S3(note_validation)+S4(qc)+S5(misstatement) 接入聚合器（Req4）+ `report` 端点 + `useAuditCheckReport` + G 循环/审定表试点上报（Req3 专属组件扩面）+ 去重（P5）。
- **M3（收口动作）**：V126 `audit_check_signoff` + 签认端点（Req8，只提示不阻断 P14）+ 导出（Req7）+ 权限全面校验（Req10）。

## Testing Strategy

- **PBT（hypothesis, max_examples=5）**：P1（通过率分母）/P2（未覆盖不全绿）/P5（去重幂等）/P6（source 命名空间替换幂等）/P7（fail-open：随机来源抛异常不影响其余）/P13（无字段退回）。
- **单测**：S2 结构化抽取与 `cycle_review_context` 文本版口径一致（同一 `_REGISTRY` 同数据同判定）；去重优先级；新鲜度三态；签认快照一致。
- **契约测试**：`report` 端点拒绝后端专属 source；`summary` 汇总字段齐全；权限矩阵（各端点角色门控）。
- **零回归门**：legacy `fine_checks`/`fine_summary`/`fine_extracted_at` 读取路径与 QC-27/28 行为不变；`fine-extract` 对 Excel/OnlyOffice 语义不变。
- **Playwright（可选）**：面板加载 → 重新检查 → 未覆盖口径展示 → 点击未通过项跳转定位 → 导出 → 签认（有阻断项提示不阻断）。
