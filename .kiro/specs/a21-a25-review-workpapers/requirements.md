# A21~A25 复核底稿配置驱动重构

## 背景

A21~A25 是审计完成阶段 5 个角色的复核检查底稿：

| 底稿 | 角色 | 模板文件 | 子底稿 |
|------|------|----------|--------|
| A21 | 项目现场负责人 | A21-1(财报)/A21-2(内控) | 各含 复核表+复核记录 2 sheet |
| A22 | 项目负责经理 | A22-1(财报)/A22-2(内控) | 同上 |
| A23 | 项目合伙人 | A23-1(财报)/A23-2(内控) | 同上 |
| A24 | 质量复核合伙人 | A24-1(财报×2: 大型国企/非国企)/A24-2(内控) | 同上 |
| A25 | 质量控制复核人 | A25-1(财报×2)/A25-2(内控) | 同上 |

当前 `ReviewChecklistPanel.vue` 是 80 行壳组件：调不存在的 API → 降级硬编码 5 个通用项 → 无持久化。

**核心需求**：配置驱动，根据项目 `business_category`(A/B/C) + `audit_type`(财报/内控/联合) 自动选模板 + 动态标记不适用项。

## 前置依赖

| 依赖 | 来源 | 说明 |
|------|------|------|
| `checklist_responses` 表 | V085 已建 | wp_id + item_id 唯一，UPSERT |
| `review_records` 表 | 已有 | ⚠️ **实为复核批注表**（cell_reference/comment_text/reply），非签字表 |
| `projects.business_category` | 已有字段(varchar) | A/B/C 类判定 |
| `projects.project_type` | 已有字段(enum) | standalone/consolidated |

### 缺失字段（需新增迁移 V086）

| 字段 | 类型 | 说明 |
|------|------|------|
| `projects.audit_type` | VARCHAR(32) DEFAULT 'financial' | financial/internal_control/combined |
| `projects.is_large_soe` | BOOLEAN DEFAULT false | 大型国企标记（影响 A24/A25 模板选择） |

### review_records 表现状

**⚠️ 重要**：`review_records` 实际是**逐单元格复核批注表**（对话式评论+回复+关闭），不是"复核签字/通过/退回"功能表。

签字功能需要：
- 方案A：新增 `review_signing` 表（reviewer_id, wp_id, action=pass/reject, comment, signed_at）
- 方案B：复用 `checklist_responses` 的 `{wp_code}-sign` item_id 存签字 JSON（轻量，P0 先用此方案）

## 适用条件

| 条件 | A21 | A22 | A23 | A24 | A25 |
|------|-----|-----|-----|-----|-----|
| A 类项目 | ✅ | ✅ | ✅ | ✅ | ✅ |
| B 类项目 | ✅ | ✅ | ✅ | ❌ | ❌ |
| C 类项目 | ✅ | ✅ | ❌ | ❌ | ❌ |

- A24/A25 仅 A 类项目自动生成
- A23 仅 A/B 类项目生成
- 联合审计（财报+内控）同时生成 -1 和 -2 子底稿

## 分期

| 分期 | 等价 | 范围 | DoD |
|------|------|------|-----|
| **P0/lite** | 模板解析+重写组件+保存 | A21-1 解析 → JSON 定义 + `GtReviewChecklist.vue` 重写 + checklist_responses 保存 | 填复核项→刷新不丢 |
| **P1/core** | 多角色配置驱动 | 5 角色×(财报+内控+国企) 全部配置化 + 复核记录区 + 签字联动 | 签字→A1 状态同步 |
| **P2/plus** | 智能辅助+导出 | 自动预填建议(底稿完成度→勾选推荐) + Word 导出 + E2E | 导出含签字日期 |

---

## 需求

### 1. 模板解析与定义文件

- 解析 A21-1 xlsx 模板的"复核表" sheet → 提取 15+ 条检查项
- 生成 `a21_a25_review_definitions.json`：按角色+审计类型组织
- 结构示例：

```json
{
  "A21-1": {
    "role": "现场负责人",
    "audit_type": "financial",
    "applicable_categories": ["A", "B", "C"],
    "items": [
      {"seq": 1, "content": "具体审计计划已经实施…", "auto_na_condition": null},
      {"seq": 10, "content": "对于利用组成部分注册会计师的工作…", "auto_na_condition": "no_component_auditor"}
    ]
  }
}
```

- `auto_na_condition`：当项目不满足该条件时自动标 N/A
  - `no_component_auditor`：无组件单位审计师
  - `no_internal_control_audit`：非内控审计项目
  - `not_large_soe`：非大型国企
  - `no_it_audit`：无 IT 审计程序

### 2. 配置驱动模板选择

- 根据项目上下文自动确定使用哪些子底稿：
  - `business_category` = A → A21~A25 全生成
  - `business_category` = B → A21~A23
  - `business_category` = C → A21~A22
  - `audit_type` = financial → 使用 -1 后缀模板
  - `audit_type` = internal_control → 使用 -2 后缀模板
  - `audit_type` = combined → 两者都生成
- A24/A25 额外判定：`is_large_soe` → 选大型国企版/非国企版

### 3. 前端组件 GtReviewChecklist.vue（替换 ReviewChecklistPanel）

- **三段式布局**：
  1. **角色信息栏**：显示当前复核角色 + 适用审计类型 + 项目类别
  2. **检查项列表区**：勾选(Y/N/NA) + 每项可展开填写备注 + auto_na 自动灰化
  3. **复核记录区**：自由文本 textarea（对应模板"复核记录" sheet）
  4. **签字区**：复核人签字 + 日期 + 通过/退回按钮

- 进度条：已完成/总计（NA 不计入）
- 提示：未勾选全部适用项时，通过按钮禁用

### 4. 持久化

- 复用 `checklist_responses` 表（与 A17/A18/A1-15 一致）
- item_id 命名契约：`{wp_code}-chk-{seq:02d}`
  - 示例：`A21-1-chk-01`, `A21-1-chk-15`, `A22-1-chk-01`
- conclusion 值：`Y`(已勾选) / `N`(未勾选) / `NA`(不适用)
- remark：备注文本
- 复核记录：item_id = `{wp_code}-record`，remark = 记录正文
- debounce 1500ms 自动保存

### 5. 签字联动

- 复核通过 → 写入 `checklist_responses` 的 `{wp_code}-sign` item（conclusion="pass", remark=JSON{signer,date}）
- P1 可升级为独立 `review_signing` 表
- 复核状态同步到 A1 程序表的对应步骤 status
- 退回 → 记录退回原因(conclusion="reject") + 通知项目组

### 6. Word 导出（P2）

- 从 checklist_responses 读取数据 → 填入对应 xlsx 模板
- 已勾选项标 "√"，NA 项标 "N/A"，备注填入对应列
- 签字区填入签字人+日期

### 7. 自动预填建议（P2）

- 读取项目底稿完成度（working_papers 表 status = completed 比例）
- 底稿完成率 > 95% → 建议勾选"底稿编制完整性"
- 调整分录已复核 → 建议勾选"调整分录正确"
- 建议值仅为提示，用户可覆盖

---

## 现状与差距

| 能力 | 目标 | 代码现状 | 分期 |
|------|------|----------|------|
| 模板解析 | JSON 定义 | ❌ 无 | P0 |
| GtReviewChecklist | 配置驱动多角色 | ❌ 壳(5 硬编码项) | P0 |
| checklist_responses 保存 | UPSERT | ❌ 无调用 | P0 |
| 多角色配置 | 10+ 子底稿 | ⚠️ _WP_CODE_OVERRIDE 已映射 | P1 |
| 签字联动 | review_records | ⚠️ 表存在但未接入 | P1 |
| Word 导出 | xlsx 回填 | ❌ | P2 |
| 自动预填 | 底稿完成度 | ❌ | P2 |

## 关联模块

- A1 程序表（复核步骤 status 联动）
- review_records 表（签字状态源）
- checklist_responses 表（数据存储）
- completion-phase-infra（持久化契约）
