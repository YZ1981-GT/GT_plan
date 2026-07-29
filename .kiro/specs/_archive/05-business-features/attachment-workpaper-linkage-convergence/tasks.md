# Implementation Plan

## Overview

收敛「附件↔底稿」多套并行关联为单一权威真源 + 统一反查视图 + 解除闭环 + 证据声明 + OCR 归一 + stale 前置。全部 additive/幂等/分波可回退。承接已完成的 C（附件页 `?id=` 深链定位）与 B（底稿只读关联附件抽屉），本 spec 在 B 抽屉与两条关联写入路径上增强。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "desc": "安全网 + 幂等基础（V133 唯一索引 + ensure_wp_link）" },
    { "wave": 1, "tasks": ["2.1", "2.2", "2.3"], "desc": "Req1 双写收敛 + 反查去重 + 回填脚本" },
    { "wave": 2, "tasks": ["3.1", "3.2"], "desc": "Req2 统一视图 source 标注 + 函证只读纳入" },
    { "wave": 3, "tasks": ["4.1", "4.2"], "desc": "Req3 解除关联闭环（端点 + B 面板）" },
    { "wave": 4, "tasks": ["5.1", "5.2"], "desc": "Req4 证据类型声明 + 缺证据提示" },
    { "wave": 5, "tasks": ["6.1"], "desc": "Req6 stale 失效前置到底稿面板" },
    { "wave": 6, "tasks": ["7.1"], "desc": "Req5 OCR 双轨归一（识别回流附件）" },
    { "wave": 7, "tasks": ["8.1", "8.2"], "desc": "Req7/Req8 零回归门 + PBT + Playwright" }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 安全网 + 幂等基础
- [x] 1.1 characterization 基线锁定既有行为
  - 编写 characterization 测试锁定 `associate_with_wp`（当前无去重）、`link_attachment_to_workpaper`（UPDATE reference_id）、`get_wp_attachments`（只读链表）的现有行为，作为零回归基线
  - _Requirements: 7.1_
- [x] 1.2 V133 唯一索引 + `ensure_wp_link` 幂等封装
  - 以 `migration_status` 复核最高迁移号（假定 V133），编写迁移：先去重 `attachment_working_paper` 存量重复 (attachment_id, wp_id)（保留最早 created_at），再建 `uq_awp_attachment_wp` 唯一索引；带 R{n} 回滚
  - 新增 `ensure_wp_link(db, attachment_id, wp_id, association_type, notes, created_by)`：先查存在再 INSERT，绝不产生重复行
  - `associate_with_wp` 改委托 `ensure_wp_link`（保持返回结构 + 去重）
  - 迁移测试：存量去重 + 索引生效 + 幂等重跑；`ensure_wp_link` 幂等单测
  - _Requirements: 1.1, 1.2, 8.1_

- [x] 2. Wave 1 — 双写收敛 + 反查去重 + 回填
- [x] 2.1 process-record linkAttachment 双写权威真源
  - `link_attachment_to_workpaper` 在原 `UPDATE reference_id`（保留兼容）后追加 `ensure_wp_link`（fail-open：link 失败不阻断 UPDATE，记 warning）
  - 测试：linkAttachment 后该关联出现在权威链表 + 反查可见
  - _Requirements: 1.1, 1.5, 8.1_
- [x] 2.2 反查统一去重（链表 ∪ reference）
  - `get_wp_attachments` 改为：权威链表(source=associated, 带 association_type) ∪ reference 关联(reference_id==wp_id AND reference_type=='working_paper', source=referenced)，按 attachment.id 去重（多来源合并 sources，优先级 associated>referenced）
  - 响应 envelope `{ items }`；既有字段全保留，additive `source`/`sources`/`association_type`（reference-only 的 association_type=null）
  - 测试：Property 2 去重、Property 3 reference 可见、Property 4 来源标注
  - _Requirements: 1.4, 2.1, 2.3, 8.1_
- [x] 2.3 存量 reference 关联回填脚本
  - 幂等脚本：扫 `attachments.reference_type='working_paper'` → `ensure_wp_link` 补入权威链表（存在则跳过）；带备份表 + `--rollback` + 只读诊断模式
  - 脚本测试：幂等重跑 rowcount=0、回填正确、回滚还原
  - _Requirements: 1.3, 7.3_

- [x] 3. Wave 2 — 统一视图 source 标注
- [x] 3.1 函证附件只读纳入反查视图
  - `get_wp_attachments` best-effort 追加：wp → confirmations → confirmation_attachment_link → attachments（source=confirmation），异常跳过仍返回链表+reference
  - 测试：函证附件纳入 + 异常 fail-open（Property 8）
  - _Requirements: 2.1, 2.2_
- [x] 3.2 前端 B 抽屉来源 tag 渲染
  - `WorkpaperAttachmentsDrawer.vue` 列表行按 `source`/`sources` 渲染来源 tag（关联证据/底稿引用/函证回函；checklist 预留）
  - vitest：来源 tag 渲染正确
  - _Requirements: 2.1, 2.3_

- [x] 4. Wave 3 — 解除关联闭环
- [x] 4.1 后端解除关联端点
  - `DELETE /api/working-papers/{wp_id}/attachments/{attachment_id}/link`：走 `gate_wp` + 编辑权限校验（无权限 403）；删权威链表 (att, wp) 行；若该附件 reference_id==wp_id 且 reference_type=='working_paper' 则清空 reference；不存在的关联 no-op 200
  - 测试：Property 5 解除幂等 + reference 同步清空 + 权限 403
  - _Requirements: 3.1, 3.2, 3.3_
- [x] 4.2 B 面板解除关联按钮 + 权限门控
  - `WorkpaperAttachmentsDrawer.vue` 加解除按钮（`canEdit` 门控，隐藏非编辑角色），调 4.1 端点，成功后 reload；确认弹窗
  - vitest：权限门控 + 解除后刷新
  - _Requirements: 3.1, 3.3, 3.4_

- [x] 5. Wave 4 — 底稿驱动证据收集
- [x] 5.1 证据类型声明配置 + 反查响应附加
  - 新增 `backend/data/workpaper_evidence_requirements.json`（wp_code_prefix → 证据类型清单，仅覆盖有明确要求的底稿类型，宁缺勿造）
  - 反查响应 additive `evidence_requirements`（每类 type/label/satisfied，satisfied=该类是否已有关联附件）；未定义声明的底稿不附加；fail-open
  - 测试：Property 6 缺证据提示仅对有声明底稿触发
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
- [x] 5.2 B 面板证据类型声明清单 + 缺证据提示
  - `WorkpaperAttachmentsDrawer.vue` 顶部展示应收集证据清单（满足 ✓ / 缺失 ⚠️「缺 XX 证据」，不阻断）
  - vitest：有/无声明的渲染门控
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 6. Wave 5 — stale 失效前置
- [x] 6.1 stale 前置到底稿面板
  - 反查响应 additive `stale_info`（只读：inactive evidence_refs from/to 底稿关联 = definite；仅 `prefill_stale` = conservative；fail-open）
  - `WorkpaperAttachmentsDrawer.vue` 展示失效提示（分级，指向治理中心），无 stale 不展示
  - 测试：stale 分级 + fail-open（Property 8）
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 7. Wave 6 — OCR 双轨归一
- [x] 7.1 底稿页 OCR 识别结果回流附件
  - 底稿页 OCR 路径（试点 `/d4/contract-ocr` + `/f2/contract-ocr`）识别后，若传入已关联 `attachment_id`，回流 `ocr_text`/`ocr_fields_cache`；已有结果可复用，`force_reocr` 可重识别
  - 保持 `governed=False`/`requires_human_confirmation=True`；未传 attachment_id 行为不变
  - 测试：Property 7 OCR 回流同源 + 不自动落业务数据
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 8. Wave 7 — 零回归门 + 验证
- [x] 8.1 PBT + 零回归门
  - 汇总 Property 1-8 PBT；跑附件域 + evidence-governance + process-record 全量测试确认零回归（git stash 甄别 pre-existing 失败）
  - _Requirements: 7.1, 7.2, 7.4, 8.1_
- [x]* 8.2 Playwright 端到端
  - 底稿面板显示多来源附件 + 解除关联 round-trip + 缺证据提示 + stale 提示；需实例化含关联的项目（无数据时验空态与提示逻辑），create→verify→cleanup 零污染
  - _Requirements: 2.1, 3.1, 4.2, 6.1_

## Notes

- 全部 additive/幂等/分波可回退；签名与既有字段键名兼容（可见集合可增；反查 `{items}` envelope）。
- 迁移版本号实现时以 `migration_status` 复核（本设计假定 V133）。
- 不改附件存储底层、安全通道（opaque locator）、OCR 识别算法本身、函证编制链路。
- 权威真源 = `attachment_working_paper`（M:N）；reference 关联保留供兼容读取，不删除。
- 承接既有 C（附件页 `?id=` 深链）与 B（只读关联附件抽屉），本 spec 增强 B 抽屉 + 两条写入路径。
- **检查项 checklist**：本 spec 不纳入统一反查 join；OCR 试点仅 `/d4/contract-ocr` + `/f2/contract-ocr`。
- 实现波次以本 tasks.md Wave 0–7 为准。
