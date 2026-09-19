# Implementation Plan

## Overview

把函证台账升级为完整回函证据链（发函件/回函件上传 → OCR 识别 → 比对账面数 → 自动匹配 → 人工确认回填）+ 状态撤回，全程 additive 零回归、OCR 结果人工确认前不落库。按 M0-M4 分波交付，M1（撤回）独立可用先落地。

所有后端服务只 flush 不 commit（router 统一 commit）；权限校验置于 `try` 外避免 403 被吞成 500；OCR 算法（`extract_confirmation_reply`）不改，仅叠加编排；迁移全 `IF NOT EXISTS` + information_schema 幂等守护。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2", "1.3"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3", "2.4"], "depends_on": [0] },
    { "wave": 2, "tasks": ["3.1", "3.2", "3.3", "3.4"], "depends_on": [0] },
    { "wave": 3, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5"], "depends_on": [2] },
    { "wave": 4, "tasks": ["5.1", "5.2", "5.3", "5.4"], "depends_on": [2, 3] },
    { "wave": 5, "tasks": ["6.1", "6.2"], "depends_on": [1, 2, 3, 4] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 安全网 + 迁移 + ORM 骨架

- [x] 1.1 characterization 基线锁定既有行为
  - 为现有函证端点（list/create/get/update/delete/transition 前进/batch-sync）与 `extract_confirmation_reply` 写 characterization 测试，锁定逐字节基线，作为后续零回归对照
  - 断言前进单向状态机 `_ALLOWED_TRANSITIONS` 行为不变、`extract_confirmation_reply` 抽取输出不变
  - _Requirements: 9.1, 9.3, 9.4_

- [x] 1.2 迁移 + ORM（additive）
  - 执行前以 `migration_status`/磁盘最高号复核版本号（预计 V126+），新建 `V{N}__confirmation_evidence_linkage.sql`
  - `ALTER TABLE confirmations ADD COLUMN IF NOT EXISTS sent_date DATE / reply_date DATE`（information_schema 幂等守护）
  - `CREATE TABLE IF NOT EXISTS confirmation_attachment_link`（role/paired_outbound_attachment_id/match_status/match_evidence + CHECK role∈(outbound,inbound) + 索引 (confirmation_id,role)）
  - `CREATE TABLE IF NOT EXISTS confirmation_action_log`（append-only）+ 复用 evidence-governance 的 `evgov_forbid_update/delete` 触发器禁 UPDATE/DELETE
  - ORM 同步：`confirmation_models.py` 加 sent_date/reply_date + 新增 ConfirmationAttachmentLink / ConfirmationActionLog 模型；SchemaDriftDetector drift=0
  - _Requirements: 2.1, 2.2, 8.3, 9.5, 9.6_

- [x] 1.3 契约测试骨架 + Property 守卫桩
  - 建 `tests/confirmation_evidence/` 目录与共享 fixture；Property 1-12 契约测试文件骨架（先 xfail/占位，随各波转绿）
  - 契约守卫：断言前进状态机与 OCR 算法未被本 spec 修改（防漂移）
  - _Requirements: 10.1, 10.5_

- [x] 2. Wave 1 — M1 状态撤回（独立可用）

- [x] 2.1 reverse_status 服务
  - `confirmation_service` 加 `_STATUS_RANK` + `_REVERSAL_TARGETS`（matched/discrepancy 可退 returned/sent/pending，returned 可退 sent/pending，sent 退 pending，pending 不可退）
  - `reverse_status(db, cid, target, reason, actor)`：校验 `rank[target]<rank[current]` 且 `target∈_REVERSAL_TARGETS[current]`，非法抛中文 ValueError；跨过 returned 回退时清 confirmed_amount/diff_amount/reply_date
  - 写 `confirmation_action_log`（action=reverse，from/to_status，被清字段入 final_value）；publish 状态变化事件复用现有下游刷新链
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7_

- [x] 2.2 reverse 端点 + 权限分层
  - `POST /{cid}/reverse`（body: target_status/reason）；`ValueError→400`（不存在→404），HTTPException 置 `try` 外不被吞成 500
  - 权限：撤回终态（当前 matched/discrepancy）require 现场经理+（manager/partner/signing_partner/admin）；相邻非终态撤回=编辑权
  - _Requirements: 1.6, 8.1, 8.2_

- [x] 2.3 前端撤回按钮
  - `ConfirmationHub.vue` 操作列加"撤回"：ElMessageBox 列出所有可退目标状态 + 原因输入；影响已回填金额时二次确认；成功后刷新台账
  - _Requirements: 1.1, 1.5, 1.7_

- [x] 2.4 撤回 PBT
  - Property 1（撤回单调：rank 严格更早、pending 不可退、前进/同级被拒、matched 可一步退到底）
  - Property 2（reverse 写 action_log + append-only 触发器拒 UPDATE/DELETE，真实 PG16）
  - Property 10 撤回部分（终态撤回低权限被拒且无副作用）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 8.2, 8.3, 10.1, 10.6_

- [x] 3. Wave 2 — M2 台账↔附件链（发函件/回函件强配对）

- [x] 3.1 ConfirmationEvidenceService 附件链
  - 新建 `app/services/confirmation_evidence_service.py`：`link_attachment`（role=inbound 强校验/默认绑发函件：单份自动、多份要求指定；无发函件拒挂回函件）/ `unlink_attachment`（清 reference/删 link，不物删附件，留痕）/ `list_attachments` / `list_attachment_counts`（批量单查询免 N+1）
  - 附件挂载沿用 `attachment_type=confirmation` + `reference_type=confirmation_list` + `reference_id`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3.2 附件链端点
  - `POST /{cid}/attachments`（attachment_id/role/paired_outbound_id）/ `DELETE /{cid}/attachments/{link_id}` / `GET /{cid}/attachments`；编辑权
  - 台账列表返回批量附件计数（发函件数/回函件数）
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3.3 前端附件抽屉
  - 新建 `ConfirmationAttachmentDrawer.vue`：上传发函件/回函件（选角色，回函件选配对发函件）、列附件（角色/配对/OCR状态）、解绑、回函影像预览（复用附件安全预览/下载）
  - `ConfirmationHub.vue` 台账加"发函件/回函件"计数列 + 打开抽屉入口
  - _Requirements: 3.2, 3.5, 7.1, 7.2, 7.3, 7.4_

- [x] 3.4 附件链 PBT
  - Property 9（role=inbound 必有 paired_outbound 且指向同函证 outbound；无发函件不得挂回函件；单份自动/多份指定）
  - Property 12（list_attachment_counts 单查询免 N+1）
  - _Requirements: 3.4, 3.5, 3.6_

- [x] 4. Wave 3 — M3 回函 OCR 识别 + 比对 + 人工确认回填

- [x] 4.1 extract_and_compare
  - `ConfirmationEvidenceService.extract_and_compare(attachment_id)`：调 `extract_confirmation_reply`（算法不改）→ 与所属函证 book_amount 比对（`|diff|≤0.01` 默认容差判相符/不符，任一缺失不判相符）+ counterparty 名称比对（不符 `counterparty_mismatch=true`）
  - 结果写 `attachment.ocr_fields_cache`（含 governed=false/requires_human_confirmation=true/match_verdict/diff），**不**写 confirmations
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 4.2 apply_reply（人工确认回填）
  - `apply_reply(cid, attachment_id, confirmed_amount, reply_date, target_status)`：写 confirmed_amount/reply_date/diff_amount，status 用入参（用户确认值）；人工修正值优先于 OCR 原值
  - 写 `confirmation_action_log`（action=apply_reply，ocr_original + final_value 双值保留）
  - 差异容差内建议 matched、容差外建议 discrepancy（仅建议，最终由入参定）
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6_

- [x] 4.3 OCR/回填端点
  - `POST /attachments/{aid}/extract-compare`（编辑权，不落库）/ `POST /{cid}/apply-reply`（现场经理+，改结论）
  - _Requirements: 4.1, 5.1, 5.3, 8.2_

- [x] 4.4 前端 OCR 面板 + 一键回填
  - 附件抽屉内：触发 OCR、展示比对结果（相符/不符/差异/主体不符预警，全标"AI辅助待确认"）、低置信度提示人工核对原件、可编辑修正金额/日期后"确认回填"
  - _Requirements: 4.3, 4.4, 4.5, 5.1, 5.5_

- [x] 4.5 OCR/回填 PBT
  - Property 3（diff+±0.01容差，任一缺失不判相符）/ P4（名称不符预警不被金额相符掩盖）/ P5（governed=false 不自动落库，无 apply_reply 时台账不变）/ P6（修正值优先+双值留痕）/ P7（状态建议由用户确认不自动定终态）
  - _Requirements: 4.2, 4.3, 4.4, 5.1, 5.2, 5.4, 10.2, 10.3_

- [x] 5. Wave 4 — M4 回函自动匹配 + 人工队列

- [x] 5.1 auto_match + 队列
  - `auto_match(project_id, attachment_id)`：按 OCR 主体名称（精确/模糊）+ 金额容差 + 可选函证编号匹配 status∈{sent,returned} 记录；唯一命中→挂载+绑发函件+待回填（不落库）；多义→候选列表；无命中→ match_status=pending 入队列；命中依据记 match_evidence
  - `list_match_queue(project_id)` / `assign_match(attachment_id, cid, paired_outbound_id)`（人工指派+留痕）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [x] 5.2 匹配端点
  - `POST /auto-match`（编辑权）/ `GET /match-queue`（只读）/ `POST /match-queue/{aid}/assign`（编辑权）
  - _Requirements: 6.1, 6.4, 6.6_

- [x] 5.3 前端人工匹配队列
  - 队列视图：列未匹配回函件，指派到函证 + 选配对发函件；多义候选选择 UI
  - _Requirements: 6.3, 6.4, 6.6_

- [x] 5.4 自动匹配 PBT
  - Property 8（唯一命中才挂载+绑发函件；多义/无命中不落台账正式结论；match_evidence 可解释）
  - _Requirements: 6.2, 6.3, 6.4, 6.5, 10.4_

- [x] 6. Wave 5 — 零回归门 + 端到端

- [x] 6.1 零回归门 + Property 11
  - 全量跑 confirmation/attachment 相关后端测试 + 前端 vitest；Property 11 characterization 对照（未用新功能既有端点逐字节等价、历史空值兼容、syncHubFromSummary/apply_confirmation_result/extract_confirmation_reply 行为不变）
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 10.5_

- [x] 6.2 Playwright 端到端*
  - 实例化含函证数据的项目，走 上传发函件/回函件 → OCR → 比对 → 确认回填 → 撤回改判 round-trip；SSE 环境不稳或无实例化数据时以 PBT + 鉴权 HTTP round-trip 覆盖，诚实留待不假绿
  - _Requirements: 1.1, 3.5, 4.1, 5.1, 6.2, 7.1_

## Notes

- **迁移取号**：Wave 0 执行前必以 `migration_status` 复核磁盘最高版本号（当前 V124/V125 被并发 spec 占用），本 spec 用下一可用号，避免同号冲突。
- **附件底层不动**：仅复用 `attachment_type=confirmation` reference 挂载与既有上传/预览/安全网关；不改 Paperless/本地存储与 OCR 算法。
- **编制侧不动**：`syncHubFromSummary`（编制底稿→台账）与 `apply_confirmation_result`（回函下游 stale 传播）保持行为不变。
- **阶段独立**：M1（撤回，Wave 1）仅依赖 Wave 0，可先落地上线；M3 依赖 M2 附件链，M4 依赖 M2+M3。
- **权限口径**：编辑权沿用平台既有编辑角色集；"现场经理+" = {manager, partner, signing_partner, admin}，与平台权限矩阵一致。
- **PBT**：hypothesis `max_examples=5`；append-only 触发器 / 批量计数 / 强配对 CHECK 用真实 PG16 集成测试验证。
