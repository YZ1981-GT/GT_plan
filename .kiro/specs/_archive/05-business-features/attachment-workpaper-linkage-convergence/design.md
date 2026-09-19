# Design Document

## Overview

收敛「附件↔底稿」多套并行关联机制为**单一权威关联真源**（`attachment_working_paper` M:N 链表），并在其上补齐统一反查视图、解除关联闭环、底稿驱动证据收集、OCR 双轨归一、失效提示前置。全部改动 additive + 幂等 + 分波可回退；**签名与既有字段键名兼容**（可见集合可增；反查可为 `{items}` envelope），非逐字节硬兼容。

### 实证基线（代码实测，design 决策依据）

| 事实 | 位置 |
|------|------|
| `associate_with_wp` **无去重**，每次 INSERT 新 link 行 | `attachment_service.py:300` |
| `AttachmentWorkingPaper` **无 (attachment_id, wp_id) 唯一约束** | `attachment_models.py` |
| process-record `link_attachment_to_workpaper` = `UPDATE attachments SET reference_type='working_paper', reference_id=` (1:1 覆盖) | `process_record_service.py:143` |
| 反查 `get_wp_attachments` 只 join `attachment_working_paper`（reference 关联不可见） | `attachment_service.py:324` |
| `_to_dict` 返回 file_name/file_path(opaque locator)/file_type/file_size/attachment_type/reference_id/reference_type/ocr_status/ocr_text(截断)/created_at/version，**无 association_type** | `attachment_service.py:697` |
| Attachment 有 `ocr_text`/`ocr_fields_cache`/`reference_id`/`reference_type` | `attachment_models.py` |
| 函证附件 `confirmation_attachment_link(confirmation_id, attachment_id, role)` | DB 实测 |
| 证据失效走 evidence_ref stale 传播（`query_refs_from_source` source→target） | `evidence_ref_query_service.py:206` |
| 最高迁移 V132（本 spec 用 V133，实现时以 migration_status 复核为准） | `backend/migrations/` |

## Architecture

```
┌─ 关联写入（两入口收敛到同一权威真源）───────────────────────────┐
│  evidence-governance associate ─┐                              │
│  process-record linkAttachment ─┼─► AttachmentLinkAuthority     │
│     (仍写 reference_id 兼容)      │      .link(att, wp, type)     │
│                                  │   幂等 upsert → attachment_working_paper（权威）│
└──────────────────────────────────────────────────────────────┘
                                          │
┌─ 反查（统一视图）──────────────────────▼──────────────────────┐
│  get_wp_attachments(wp_id)                                     │
│    = 权威链表(source=associated, 带 association_type)            │
│    ∪ reference 关联(source=referenced)  ── 去重 by attachment.id │
│    ∪ 函证只读(source=confirmation)      ── best-effort          │
│    → 每行 additive: source / association_type                   │
└──────────────────────────────────────────────────────────────┘
                                          │
┌─ 前端底稿关联附件面板（B 抽屉增强）──────▼──────────────────────┐
│  · 列表 + 来源 tag（关联证据/底稿引用/函证/检查项）              │
│  · 解除关联（Req3，权限双层）                                    │
│  · 证据类型声明清单 + 缺证据提示（Req4）                         │
│  · stale 失效提示（Req6，只读 evidence_ref）                     │
└──────────────────────────────────────────────────────────────┘

┌─ OCR 双轨归一（Req5）─────────────────────────────────────────┐
│  底稿页 OCR(/d4/contract-ocr 类) ─► 回流 attachment.ocr_text    │
│                                     /ocr_fields_cache（同源）    │
│                                     人工确认闸门不变            │
└──────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### C1. 权威关联收敛层（逻辑组件 = `AttachmentService.ensure_wp_link`）

不单独建 `AttachmentLinkAuthority` 类；以 `attachment_service.ensure_wp_link` 为幂等 upsert 真源入口：

```python
async def ensure_wp_link(
    self, attachment_id, wp_id, *, association_type="evidence",
    notes=None, created_by=None,
) -> dict:
    """幂等关联：先查 (attachment_id, wp_id) 是否已存在链行；
    存在则返回既有（可更新 association_type/notes），否则 INSERT。
    绝不产生重复 (att, wp) 行。"""
```

- `associate_with_wp` 委托 `ensure_wp_link`，并**对称双写** `reference_*`（1:1 last-write-wins，供旧消费者；失败 fail-open）。
- process-record `link_attachment_to_workpaper` 在原 `UPDATE reference_id`（保留兼容）后**追加** `ensure_wp_link`，使该关联进入权威真源。fail-open（link 失败不阻断原 UPDATE）。
- fail-open 一律打结构化 warning：`event=awp_*_fail_open`（可观测，不阻断主流程）。

### C2. 反查统一视图（后端 `get_wp_attachments` 增强）

```python
async def get_wp_attachments(wp_id) -> dict:
    # 1. 权威链表（join 带出 association_type + notes）→ source='associated'
    # 2. reference 关联（Attachment.reference_id==wp_id AND reference_type=='working_paper'）→ source='referenced'
    # 3. 函证只读（Wave 2）：wp → confirmations → confirmation_attachment_link → attachments → source='confirmation'（best-effort）
    # 去重 by attachment.id（同一附件多来源 → 取优先级 associated>referenced>confirmation，合并 sources 列表）
    # 返回 envelope: { "items": [ {...既有字段, source, sources, association_type} ] }
    # Wave 4/5 再 additive: evidence_requirements / stale_info（同 envelope 顶层）
```

- **响应 envelope**：`{ items: [...] }`（不再裸 list）。既有消费者（B 抽屉 / useOcrAttachmentCache / OcrFieldsDrawer）已兼容 `Array.isArray ? data : data.items`。
- `source` 表来源；`association_type` **仅链表行有值**（evidence/support/…）；reference-only 行 `association_type=null`（**勿**把 `referenced` 写入 association_type 枚举）。
- **检查项 checklist**：本 spec 不 join；枚举预留。
- 实现波次以 `tasks.md` Wave 0–7 为准（Design 原 M0–M4 仅为逻辑分组）。

### C3. 解除关联端点（Req3）

```
DELETE /api/working-papers/{wp_id}/attachments/{attachment_id}/link
```
- 走 `gate_wp`（同 `get_wp_attachments` 的统一门 + 编辑权限校验）。
- 删除权威链表对应 (att, wp) 行；若该附件 `reference_id==wp_id AND reference_type=='working_paper'` 则同步清空 reference（置 NULL）。不删附件本身。
- fail-closed 权限：无编辑权限 403。

### C4. 前端 `WorkpaperAttachmentsDrawer.vue` 增强（B 面板）

- 列表行加**来源 tag**（source: associated=关联证据/referenced=底稿引用/confirmation=函证回函/checklist=检查项证据）。
- 加**解除关联**按钮（`canEdit` 门控，调 C3 端点，成功后 reload）。
- 顶部加**证据类型声明清单 + 缺证据提示**（Req4，来自 C5）。
- 加 **stale 失效提示**（Req6，来自 C6，只读，指向治理中心）。

### C5. 证据类型声明（Req4）

- 新增配置数据 `backend/data/workpaper_evidence_requirements.json`：`{ wp_code_prefix: [{ type, label }] }`，**仅覆盖有明确证据要求的底稿类型**（如凭证检查表需记账凭证影像、函证需回函件），宁缺勿造。
- 反查响应 additive 附 `evidence_requirements`（该底稿应收集的证据类型 + 每类是否已有关联附件）。
- 前端面板展示清单：已满足 ✓ / 缺失 ⚠️「缺 XX 证据」（不阻断）。
- 未定义声明的底稿：无清单无缺证据提示。fail-open。

### C6. stale 失效前置（Req6）

- 反查响应 additive 附 `stale_info`（只读）。
- **实现算法**（`workpaper_attachment_stale.build_stale_info`，与治理中心完整传播图可并存）：
  - `definite`：该底稿作为 source 的 `evidence_refs` 已 `inactive`，或关联附件侧 ref 已 inactive；
  - `conservative`：仅 `working_paper.prefill_stale`（无明确 inactive ref 行）。
  - 未直接调用 `query_refs_from_source` 全图；治理中心仍为详情权威，面板只做前置提示。
- 前端面板展示失效提示（分级，避免噪声），指向治理中心查看详情。
- fail-open：stale 查询失败不阻断面板。

### C7. OCR 双轨归一（Req5）

- **共享回流**：`attachment_ocr_writeback`（`writeback_ocr_to_linked_attachment` / `load_reusable_ocr` / `finalize_linked_ocr_writeback`）。
- **已接线路径**：`/d4/contract-ocr`、`/f2/contract-ocr`，以及 F3/F4/F5/F2-stocktake/F2-special/F2-valuation 等 contract-ocr（传入已关联 `attachment_id` 时回流；未传行为不变）。
- 结构化字段用于底稿取数时保持既有「人工确认后落库」闸门（`governed=False`/`requires_human_confirmation=True`），OCR 回流本身不落业务数据。
- 附件已有 OCR 结果时底稿页可复用（避免重复识别），可选 `force_reocr`。
- 临时上传未关联附件：行为不变（不强制关联）。
- E1 专用 OCR（流水/授信等）仍列 backlog（生成临时 id，非附件表回流）。

## Data Models

### 迁移 V133（additive，幂等）

```sql
-- attachment_working_paper 加 (attachment_id, wp_id) 唯一约束支撑幂等 upsert
-- 先去重存量重复行（保留最早 created_at），再建部分唯一索引
CREATE UNIQUE INDEX IF NOT EXISTS uq_awp_attachment_wp
  ON attachment_working_paper (attachment_id, wp_id);
```
- 执行前先删除重复 (att, wp) 行（保留最早一条），否则建索引失败。
- **实现时以 `migration_status` 复核最高版本号**（本设计假定 V133，若已被占用则顺延）。
- 无新表、无新业务列。

### 反查响应 additive 字段

响应 envelope：`{ "items": [ ... ] }`（Wave 4/5 顶层再加 `evidence_requirements` / `stale_info`）。

既有字段全保留于 items 行内，每行新增：
- `source: string`（associated / referenced / confirmation；checklist 预留）
- `sources: string[]`（同一附件多来源时合并）
- `association_type: string | null`（仅权威链表有值；reference-only 为 null）

响应体（wp 级）additive（Wave 4/5）：
- `evidence_requirements: [{ type, label, satisfied }]`（Req4）
- `stale_info: { has_stale, level, items }`（Req6）

## Correctness Properties

### Property 1: 双写幂等
对同一 (attachment_id, wp_id) 连续调用 associate + linkAttachment（任意次序/次数），权威链表 SHALL 只有一行该关联。
**Validates: Requirements 1.1, 1.2, 8.1**

### Property 2: 反查去重
反查统一视图对同一 attachment.id SHALL 只返回一行（多来源合并 sources），无重复。
**Validates: Requirements 1.4, 2.1, 8.1**

### Property 3: reference 关联可见
仅通过 process-record reference 关联的附件 SHALL 出现在反查结果（source='referenced'）。
**Validates: Requirements 1.1, 1.4**

### Property 4: 来源标注正确
反查每行 `source` SHALL 与其真实来源一致（链表→associated / reference→referenced / 函证→confirmation）。
**Validates: Requirements 2.1, 2.3**

### Property 5: 解除关联幂等
解除 (att, wp) 关联后再次解除 SHALL 为 no-op（不报错），且该附件不再出现在反查；reference 关联同步清空。
**Validates: Requirements 3.1, 3.2**

### Property 6: 缺证据提示仅对有声明的底稿
底稿类型未定义证据要求时 SHALL 无缺证据提示；有声明且缺失时 SHALL 提示；有声明且满足时标 ✓。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 7: OCR 回流同源
底稿页 OCR 对已关联附件的识别结果 SHALL 写入该 attachment 的 ocr_text/ocr_fields_cache（与附件页同一字段）；结构化字段 SHALL 不自动落业务数据。
**Validates: Requirements 5.1, 5.2**

### Property 8: 兼容 + fail-open
既有 associate/linkAttachment/反查调用 SHALL 签名与既有字段键名兼容（可见集合可增；反查可为 `{items}` envelope）；权威写入/stale/证据声明任一失败 SHALL fail-open 不阻断主流程。
**Validates: Requirements 1.5, 4.4, 6.4, 7.1, 8.1**

## Error Handling

- 权威 link 写入失败 → warning 日志 + fail-open（不阻断 associate/linkAttachment 主流程，Req1.5）。
- 函证只读纳入异常 → 跳过函证来源，仍返回链表+reference（Req2.2 best-effort）。
- 证据声明/stale 查询失败 → 只返回已关联附件，无清单/无提示（Req4.4/Req6.4）。
- 解除关联无权限 → 403（Req3.3）；不存在的关联 → no-op 200（Req3 / Property 5）。
- 迁移建唯一索引前存量重复 → 先去重（保留最早）再建，避免失败。

## Testing Strategy

- **后端 PBT/单测**：Property 1-8（双写幂等/反查去重/reference 可见/来源标注/解除幂等/证据声明门控/OCR 回流/零回归）。characterization 先锁 associate/linkAttachment/get_wp_attachments 现有行为基线。
- **迁移测试**：V133 存量重复去重 + 唯一索引生效 + 幂等重跑。
- **前端 vitest**：来源 tag 渲染、缺证据提示门控（有/无声明）、解除关联权限门控、stale 提示分级。
- **Playwright**：底稿面板显示多来源附件 + 解除关联 round-trip + 缺证据提示（需实例化含关联的项目；无数据时验空态与提示逻辑）。
- **零回归门**：附件域 + evidence-governance + process-record 全量测试通过。

## Migration & Rollout（M0-M4）

- **M0**：安全网 characterization + V133 唯一索引（去重存量）+ `ensure_wp_link` 幂等基础。
- **M1**：Req1 双写收敛 + 反查去重 + 回填脚本（幂等/备份/回滚）。
- **M2**：Req2 统一视图 source 标注 + 函证只读纳入。
- **M3**：Req3 解除关联闭环（端点+面板+权限）+ Req4 证据声明 + Req6 stale 前置。
- **M4**：Req5 OCR 双轨归一 + 零回归门 + PBT + Playwright。
- 各波 additive、独立可回退（灰度：反查去重/来源标注对既有消费者透明；证据声明/stale 无数据时无副作用）。

## Post-convergence ops（运维）

详见 `docs/runbooks/attachment-wp-linkage.md`：回填 dry-run/apply/rollback/reconcile、fail-open 事件名、reference 退役条件。
