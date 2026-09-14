# Design Document

## Overview

在既有函证台账（`confirmations` 表 + `ConfirmationHub.vue`）、附件模块（`Attachment` 表 + `AttachmentService`）、回函 OCR（`extract_confirmation_reply`）之上，新增一个**编排层**把三者串成完整回函证据链，并补齐**状态撤回**能力。核心原则：

- **复用不重写**：状态机 CRUD 走 `confirmation_service`；附件上传/预览/OCR 走 `AttachmentService`；OCR 抽取算法（`extract_confirmation_reply`）逐字不动，仅在其上叠加"比对 / 匹配 / 回填"编排。
- **AI/OCR 结果仅辅助**：OCR 抽取与比对结论标 `governed=False`，人工确认前**绝不**自动写入台账 `confirmed_amount`/`status`。
- **additive 零回归**：新增可空字段 + 新表 + 新端点；未用新功能时既有创建/编辑/删除/单向状态推进/批量同步/统计端点逐字节等价。

**已确认的关键决策（用户拍板）**：
1. 撤回**允许一步退到底**（matched/discrepancy 可直接退回 pending），回退目标须严格早于当前状态。
2. 权限分层：**撤回终态（相符/差异）或回填改结论 = 现场经理及以上**；相邻非终态撤回 = 助理即可。
3. 相符容差**默认 ±0.01 元**（绝对值），可配置。
4. 一笔函证可挂**多份回函件**，且**每份回函件必须强绑到该函证下具体某份发函件**。

## Architecture

```
                       ┌─────────────────────────────────────────────┐
                       │  ConfirmationHub.vue（函证中心台账 UI）        │
                       │  + 撤回按钮  + 附件抽屉(发函件/回函件)         │
                       │  + OCR识别/比对面板  + 一键回填  + 人工匹配队列 │
                       └───────────────┬─────────────────────────────┘
                                       │ HTTP
                       ┌───────────────▼─────────────────────────────┐
                       │  routers/confirmations.py（新增端点）         │
                       │  reverse / attachments / ocr-extract /        │
                       │  apply-reply / auto-match / match-queue       │
                       └───────────────┬─────────────────────────────┘
                                       │
                       ┌───────────────▼─────────────────────────────┐
                       │  ConfirmationEvidenceService（新编排层）       │
                       │  reverse_status / link_attachment /           │
                       │  extract_and_compare / apply_reply /          │
                       │  auto_match / list_match_queue / assign       │
                       └───┬───────────────┬──────────────────┬───────┘
                           │               │                  │
              ┌────────────▼──┐  ┌─────────▼────────┐  ┌──────▼─────────────┐
              │confirmation_  │  │AttachmentService │  │confirmation_action │
              │service        │  │(上传/预览/OCR/    │  │_log（审计留痕，     │
              │(状态机/CRUD)  │  │ extract_confirm..)│  │ append-only）       │
              └───────────────┘  └──────────────────┘  └────────────────────┘
                           │
              ┌────────────▼──────────────┐
              │ confirmation_attachment_   │  ← 附件角色 + 回函件↔发函件强配对 + 匹配状态
              │ link（新表）                │
              └────────────────────────────┘
```

**数据流（回函闭环）**：
1. 台账某笔函证上传发函件（role=outbound）→ 记 `confirmation_attachment_link`。
2. 上传回函件（role=inbound）→ 强绑到该函证下某份发函件（`paired_outbound_attachment_id`）。
3. 触发 OCR → `extract_confirmation_reply` 抽回函金额/日期/主体 → 与 `book_amount` 比对（容差 ±0.01）+ `counterparty` 名称比对 → 结果暂存 `attachment.ocr_fields_cache`（`governed=False`）。
4. 人工核对无误 → "确认回填" → `apply_reply` 写 `confirmed_amount`/回函日期/`diff_amount`/建议 status（用户确认）→ 留痕。
5. 批量上传时 `auto_match` 按 名称+金额+编号 匹配发函记录：唯一命中→挂载并绑发函件；多义→候选；无命中→人工匹配队列。
6. 撤回：`reverse_status` 按 rank 反向回退（可到底）+ 留痕 + 影响已回填时二次确认。

## Components and Interfaces

### 状态机撤回（core）

现有前进单向表 `_ALLOWED_TRANSITIONS` **保持不变**。新增基于 rank 的反向表，与前进逻辑分离：

```python
_STATUS_RANK = {"pending": 0, "sent": 1, "returned": 2, "matched": 3, "discrepancy": 3}

# 撤回允许目标：任一严格更早状态（支持一步退到底）
_REVERSAL_TARGETS = {
    "sent":        {"pending"},
    "returned":    {"sent", "pending"},
    "matched":     {"returned", "sent", "pending"},
    "discrepancy": {"returned", "sent", "pending"},
    "pending":     set(),   # 初始态，不可再撤回
}
```

`confirmation_service.reverse_status(db, confirmation_id, target_status, reason, actor)`：
- 校验 `target_status ∈ _REVERSAL_TARGETS[current]` 且 `_STATUS_RANK[target] < _STATUS_RANK[current]`，否则中文 ValueError。
- 若回退跨过 returned（如 matched→sent/pending），**清除**已回填字段（`confirmed_amount`/`diff_amount`/回函日期），留痕记录被清字段。
- 写 `confirmation_action_log`（append-only）；publish 状态变化事件（复用现有 `event_bus`，与前进推进同一下游刷新链）。

### ConfirmationEvidenceService（新编排层，`app/services/confirmation_evidence_service.py`）

| 方法 | 职责 |
|------|------|
| `link_attachment(confirmation_id, attachment_id, role, paired_outbound_id=None)` | 挂附件+记角色；role=inbound 时校验/默认绑定发函件（单份自动、多份要求指定）；写 link + 留痕 |
| `unlink_attachment(link_id)` | 解绑（清 reference/删 link 行），不物理删附件；留痕 |
| `list_attachments(confirmation_id)` | 返回该函证发函件/回函件清单（含角色/配对/OCR状态） |
| `list_attachment_counts(confirmation_ids[])` | **批量**返回每笔发函件数/回函件数（避免 N+1，Req3.4） |
| `extract_and_compare(attachment_id)` | 调 `extract_confirmation_reply` → 与所属函证 book_amount 比对（容差±0.01）+ counterparty 名称比对 → 结果写 `ocr_fields_cache`（governed=False），返回抽取值+比对结论 |
| `apply_reply(confirmation_id, attachment_id, confirmed_amount, reply_date, target_status)` | **人工确认后**回填：写 confirmed_amount/回函日期/diff_amount，状态置用户确认值；人工修正值优先，留痕保留 OCR 原值+最终值 |
| `auto_match(project_id, attachment_id)` | 按 OCR 主体名称+金额容差+可选编号匹配 status∈{sent,returned} 记录：唯一命中→挂载+绑发函件+待回填；多义→候选列表；无命中→入队列 |
| `list_match_queue(project_id)` | 列出未匹配回函件（待人工指派） |
| `assign_match(attachment_id, confirmation_id, paired_outbound_id)` | 人工把队列回函件指派到某函证+绑发函件；留痕 |

### 路由（`routers/confirmations.py` 新增，前缀 `/projects/{project_id}/confirmations`）

| 端点 | 权限 | 说明 |
|------|------|------|
| `POST /{cid}/reverse` | 相邻非终态=编辑权；终态回退=现场经理+ | 撤回，body: target_status/reason |
| `POST /{cid}/attachments` | 编辑权 | 挂附件，body: attachment_id/role/paired_outbound_id |
| `DELETE /{cid}/attachments/{link_id}` | 编辑权 | 解绑 |
| `GET /{cid}/attachments` | 只读 | 附件清单 |
| `POST /attachments/{aid}/extract-compare` | 编辑权 | OCR 识别+比对（不落库） |
| `POST /{cid}/apply-reply` | 现场经理+（改结论） | 人工确认后回填 |
| `POST /auto-match` | 编辑权 | 批量/单件自动匹配 |
| `GET /match-queue` | 只读 | 人工匹配队列 |
| `POST /match-queue/{aid}/assign` | 编辑权 | 人工指派 |

权限用 `require_role`；编辑权沿用平台既有编辑角色集，现场经理+ = `{manager, partner, signing_partner, admin}`。权限校验置于 `try` 外，避免 403 被通用 except 吞成 500（平台踩坑铁律）。

### 前端（`ConfirmationHub.vue` 扩展 + 子组件）

- 操作列加**撤回**按钮：ElMessageBox 选目标状态（列出所有可退目标）+ 原因输入；若影响已回填金额，二次确认提示。
- 新增**附件抽屉** `ConfirmationAttachmentDrawer.vue`：上传发函件/回函件（选角色，回函件选配对发函件）、列附件、触发 OCR、展示比对结果（相符/不符/差异/主体不符预警，全标"AI辅助待确认"）、可编辑修正后"确认回填"。
- **回函影像**预览：复用现有附件预览/下载（安全 opaque locator）。
- **人工匹配队列**视图：列未匹配回函件，指派到函证+发函件。
- 台账列表加"发函件/回函件"计数列（消费 `list_attachment_counts` 批量结果）。

## Data Models

### Confirmation 表（additive 新增可空字段）

```
sent_date   DATE NULL      -- 发函日期
reply_date  DATE NULL      -- 回函日期
```
（现有 book_amount/confirmed_amount/diff_amount/status/wp_id/counterparty/created_by 不动。）

### confirmation_attachment_link（新表）

| 列 | 类型 | 说明 |
|----|------|------|
| id | uuid PK | |
| confirmation_id | uuid FK→confirmations | |
| attachment_id | uuid FK→attachments | |
| role | varchar(10) | `outbound`(发函件) / `inbound`(回函件) |
| paired_outbound_attachment_id | uuid NULL | role=inbound 时**必填**（强配对到某份发函件）；outbound 时为 NULL |
| match_status | varchar(12) | `manual` / `auto` / `pending`（人工队列）/ `assigned` |
| match_evidence | jsonb NULL | 自动匹配命中依据（名称/金额/编号/置信度），可解释 |
| created_by | uuid NULL | |
| created_at | timestamptz | |

约束：`CHECK (role='inbound' → paired_outbound_attachment_id IS NOT NULL)`（DB CHECK 或服务层强校验，见 Property 9）；`role IN ('outbound','inbound')`；索引 (confirmation_id, role)。

### confirmation_action_log（新表，append-only 审计留痕）

| 列 | 类型 | 说明 |
|----|------|------|
| id | uuid PK | |
| confirmation_id | uuid | |
| project_id | uuid | |
| action | varchar(24) | `reverse` / `apply_reply` / `match_assign` / `attachment_link` / `attachment_unlink` |
| from_status / to_status | varchar(20) NULL | 撤回用 |
| ocr_original | jsonb NULL | 回填时 OCR 原值 |
| final_value | jsonb NULL | 回填最终落库值 / 撤回被清字段 |
| attachment_id | uuid NULL | 依据附件 |
| reason | text NULL | |
| actor_user_id | uuid | 操作人 |
| created_at | timestamptz | |

不可篡改：append-only DB 触发器禁 UPDATE/DELETE（复用 evidence-governance 既有 `evgov_forbid_update/delete` 模式）。

### OCR 抽取暂存

不新增表，写入 `attachment.ocr_fields_cache`（JSONB）：`{reply_amount, reply_date, reply_entity, confidence, diff, match_verdict('matched'/'discrepancy'/'low_confidence'), counterparty_mismatch, governed:false, requires_human_confirmation:true}`。人工确认前仅此处，不入 `confirmations`。

### 迁移

新增 `V{N}__confirmation_evidence_linkage.sql`（**执行时以 `migration_status`/磁盘最高号复核后确定 N**，当前已知 V124/V125 被并发 spec 占用，本 spec 预计 V126+）：
- `ALTER TABLE confirmations ADD COLUMN IF NOT EXISTS sent_date DATE / reply_date DATE`（information_schema 幂等守护）。
- `CREATE TABLE IF NOT EXISTS confirmation_attachment_link / confirmation_action_log`。
- action_log 的 append-only 触发器。
- ORM 同步（`confirmation_models.py` 加两字段 + 两新模型），SchemaDriftDetector drift=0。

## Correctness Properties

### Property 1: 撤回单调回退
撤回目标必须 `_STATUS_RANK[target] < _STATUS_RANK[current]` 且 `target ∈ _REVERSAL_TARGETS[current]`；pending 不可再撤回；前进/同级方向请求被拒。支持 matched/discrepancy 一步退到底至 pending。
**Validates: Requirements 1.1, 1.2, 1.3, 10.1**

### Property 2: 撤回与回填留痕不可篡改
每次 reverse/apply_reply/match_assign/unlink 写一条 `confirmation_action_log`，含操作人/时间/前后值/依据附件；该表 UPDATE/DELETE 被 DB 触发器拒绝。
**Validates: Requirements 1.4, 8.3, 8.5**

### Property 3: 差异计算与容差
`diff = book_amount − confirmed_amount`；`|diff| ≤ 0.01`（默认容差）判相符，否则不符；book_amount 或 confirmed_amount 任一缺失不产生"相符"结论。
**Validates: Requirements 4.2, 4.6, 5.2, 10.2**

### Property 4: 主体名称不符预警
OCR 抽取主体名称与 `counterparty` 不一致时，比对结果含 `counterparty_mismatch=true` 预警，不因金额相符而掩盖。
**Validates: Requirements 4.3**

### Property 5: OCR 结果不自动落库
`extract_and_compare` 输出恒 `governed=false`/`requires_human_confirmation=true`，仅写 `ocr_fields_cache`，在无 `apply_reply` 人工确认时 `confirmations.confirmed_amount`/`status` 不变。
**Validates: Requirements 4.4, 4.5, 5.3, 10.3**

### Property 6: 回填人工修正优先 + 双值留痕
`apply_reply` 落库用人工确认/修正后的值；`confirmation_action_log.ocr_original` 与 `final_value` 同时保留（可对比 OCR 原值与最终值）。
**Validates: Requirements 5.1, 5.4, 5.5, 10.3**

### Property 7: 回填状态建议由用户确认
差异容差内建议 matched、容差外建议 discrepancy，但最终 status 以 `apply_reply` 入参（用户确认值）为准，不自动定终态。
**Validates: Requirements 5.2**

### Property 8: 自动匹配唯一命中才落
`auto_match` 唯一命中才挂载并绑发函件；多义返回候选不挂载；无命中入 `match_status=pending` 队列；均不写台账正式结论；命中依据记入 `match_evidence` 可解释。
**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 10.4**

### Property 9: 回函件强绑发函件
`role=inbound` 的 link 必有 `paired_outbound_attachment_id`（且指向同一函证下的 outbound 附件）；无发函件时不得挂回函件；单份发函件自动绑定、多份要求指定。
**Validates: Requirements 3.5, 3.6**

### Property 10: 权限门控
撤回终态（matched/discrepancy）或 `apply_reply`（改结论）要求现场经理及以上；相邻非终态撤回与上传/OCR/请求匹配允许编辑权；低权限执行受限动作被拒且留痕未产生副作用。
**Validates: Requirements 1.6, 8.1, 8.2, 10.6**

### Property 11: 向后兼容 additive
未使用新功能时，既有 create/update/delete/transition(前进)/batch-sync/stats 端点行为逐字节等价；历史记录无 sent_date/reply_date/link 时台账正常展示（空值）；`syncHubFromSummary`/`apply_confirmation_result`/`extract_confirmation_reply` 行为不变；新增字段/表为 additive、迁移幂等。
**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 10.5**

### Property 12: 附件计数批量无 N+1
`list_attachment_counts(ids[])` 单次查询返回全部函证的发函件/回函件计数，不随函证数线性增加查询次数。
**Validates: Requirements 3.4**

## Error Handling

- **OCR 文本空/低置信**：`extract_and_compare` 返回 `confidence=low` + `match_verdict=low_confidence`，不产生虚假"相符"；UI 提示需人工核对原始影像（Req4.5）。
- **留痕写入失败**：`confirmation_action_log` 写入失败不阻断主动作（撤回/回填仍成功），但记录告警日志，不静默丢失（Req8.4，best-effort）。
- **强配对违规**：role=inbound 无 paired_outbound 或指向非同函证 outbound → 服务层拒绝 400 + 明确提示。
- **自动匹配多义/失败**：不抛错，分别返回候选列表 / 入人工队列。
- **撤回非法方向**：中文 ValueError → 路由映射 400（"不能从『X』撤回到『Y』"）；权限不足 → 403（置于 try 外不被吞成 500）。
- **迁移**：ALTER/CREATE 全 `IF NOT EXISTS` + information_schema 守护，幂等可重放；触发器 `CREATE OR REPLACE`。

## Migration & Rollout Phases

- **M0（安全网）**：characterization 测试锁定现有 confirmation 端点 + `extract_confirmation_reply` 逐字节基线；建迁移骨架 + ORM 字段/模型 + Property 契约测试骨架。
- **M1（撤回）**：`reverse_status` + `_REVERSAL_TARGETS` + action_log + reverse 端点 + 前端撤回按钮（最小刚需，独立可用）。
- **M2（附件链）**：link 表 + link/unlink/list/counts + 前端附件抽屉（发函件/回函件强配对）。
- **M3（OCR 比对+回填）**：extract_and_compare + apply_reply + 前端 OCR 面板/一键回填。
- **M4（自动匹配）**：auto_match + match-queue + assign + 前端队列视图。

各阶段 additive、独立可回退；M1 交付即满足用户最刚需的"撤回"。

## Testing Strategy

- **后端**：Property 1-12 用 PBT（hypothesis，`max_examples=5`）+ 契约测试；characterization 基线锁定既有端点零回归；append-only 触发器用真实 PG16 集成测试。
- **前端**：撤回目标计算/差异容差判定/强配对校验抽纯函数 vitest；组件挂载 smoke。
- **端到端**：Playwright 需实例化含函证数据的项目（上传回函件→OCR→比对→回填→撤回 round-trip）；无条件时以 PBT + HTTP round-trip 覆盖，诚实留待。
